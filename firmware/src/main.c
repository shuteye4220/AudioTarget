/*
 * AudioTarget gun module: control loop.
 *
 * 100 Hz: read IMU -> fuse with camera samples -> map to tone -> play on the
 * wired output and/or forward to the Pi for Bluetooth playback.
 */
#include <math.h>
#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/poweroff.h>

#include "audio.h"
#include "buttons.h"
#include "cues.h"
#include "events.h"
#include "fusion.h"
#include "imu.h"
#include "link.h"
#include "mount.h"
#include "proto.h"
#include "store.h"
#include "tonemap.h"

LOG_MODULE_REGISTER(main, LOG_LEVEL_INF);

#define TICK_MS 10
#define TONE_TX_EVERY 4    /* 25 Hz tone updates to the Pi */
#define HELLO_EVERY_MS 2000
#define CAL_TIMEOUT_MS 30000
#define CAL_SETTLE_MS 1500
#define CAL_SAMPLES 100
#define CAL_STILL_RAD_S 0.05f
#define CAL_MIN_RAISE_COS 0.866f /* 30 degrees */

#define ROUTE_WIRED 0x1
#define ROUTE_BT 0x2

K_MSGQ_DEFINE(app_q, sizeof(struct app_evt), 24, 4);

void app_post(const struct app_evt *evt)
{
	(void)k_msgq_put(&app_q, evt, K_NO_WAIT);
}

static const float vol_levels[4] = {0.12f, 0.25f, 0.5f, 1.0f};

enum cal_state { CAL_IDLE, CAL_LEVEL, CAL_RAISED };

static struct {
	enum cal_state state;
	uint32_t started;
	uint32_t step_t0;
	float sum[3];
	int n;
	float level[3];
} cal;

static struct fusion fus;
static struct fusion_cfg fcfg;
static struct mount mnt;
static struct tonemap_cfg tcfg;
static bool muted;
static uint32_t last_activity;

static void send_line(const char *buf, int n)
{
	if (n > 0) {
		link_send(buf, (size_t)n);
	}
}

static void send_status(void)
{
	char buf[PROTO_MAX_LINE];

	send_line(buf, proto_fmt_hello(buf, sizeof(buf)));
	send_line(buf, proto_fmt_route(buf, sizeof(buf), g_store.route));
}

static void reset_tilt(void)
{
	struct fusion_zero keep = fus.zero;

	fusion_init(&fus, &fcfg);
	fus.zero = keep;
	fus.zero.tilt_valid = false; /* tilt zero belongs to the old mount */
}

static void handle_line(const struct app_evt *evt, uint32_t now)
{
	struct proto_msg m;

	if (proto_parse(evt->line, &m) != 0) {
		LOG_DBG("bad line from %u", evt->src);
		return;
	}
	switch (m.type) {
	case PROTO_CAM:
		fusion_cam_update(&fus, m.az_mdeg, m.el_mdeg, m.age_ms, now);
		break;
	case PROTO_HELLO:
	case PROTO_NOTARGET:
		fusion_pi_alive(&fus, now);
		break;
	default:
		break;
	}
}

static void handle_btn(enum btn_evt b, uint32_t now)
{
	char buf[PROTO_MAX_LINE];

	last_activity = now;
	switch (b) {
	case BTN_ZERO_SHORT: {
		unsigned int bits = fusion_zero(&fus, now);

		if (bits == 0) {
			cue_play(CUE_ERROR, now);
			break;
		}
		store_save_zero(&fus.zero);
		cue_play((bits & FUSION_ZERO_CAM) ? CUE_ZERO_CAM : CUE_ZERO_TILT, now);
		send_line(buf, proto_fmt_zero(buf, sizeof(buf), bits & FUSION_ZERO_CAM));
		break;
	}
	case BTN_ZERO_LONG:
		store_save_volume((g_store.volume + 1) % ARRAY_SIZE(vol_levels));
		cue_play(CUE_VOLUME, now);
		break;
	case BTN_ZERO_VLONG:
		fusion_clear_zero(&fus);
		store_save_zero(&fus.zero);
		cue_play(CUE_ZERO_CLEARED, now);
		break;
	case BTN_MODE_SHORT:
		muted = !muted;
		cue_play(muted ? CUE_MUTE_ON : CUE_MUTE_OFF, now);
		break;
	case BTN_MODE_LONG:
		store_save_route(g_store.route % 3 + 1);
		cue_play(CUE_ROUTE_1 + g_store.route - 1, now);
		send_line(buf, proto_fmt_route(buf, sizeof(buf), g_store.route));
		break;
	case BTN_MODE_VLONG:
		if (IS_ENABLED(CONFIG_AT_LINK_BLE)) {
			link_pairing_open(CONFIG_AT_PAIRING_WINDOW_S);
			cue_play(CUE_PAIRING, now);
		} else {
			cue_play(CUE_ERROR, now);
		}
		break;
	case BTN_BOTH_VLONG:
		memset(&cal, 0, sizeof(cal));
		cal.state = CAL_LEVEL;
		cal.started = now;
		cal.step_t0 = now;
		cue_play(CUE_CAL_STEP1, now);
		break;
	case BTN_TICK:
		cue_play(CUE_TICK, now);
		break;
	}
}

static void handle_event(const struct app_evt *evt, uint32_t now)
{
	switch (evt->type) {
	case EVT_LINE:
		handle_line(evt, now);
		break;
	case EVT_BTN:
		handle_btn((enum btn_evt)evt->btn, now);
		break;
	case EVT_BLE_SECURED:
		cue_play(CUE_BLE_UP, now);
		send_status();
		break;
	case EVT_BLE_DISCONNECTED:
		cue_play(CUE_BLE_DOWN, now);
		break;
	default:
		break;
	}
}

static float norm3(const float v[3])
{
	return sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

/* Audio-guided two-pose mount calibration. Uses raw sensor-frame readings. */
static void cal_update(const float acc[3], const float gyro[3], uint32_t now)
{
	bool still = norm3(gyro) < CAL_STILL_RAD_S;

	if (now - cal.started > CAL_TIMEOUT_MS) {
		cal.state = CAL_IDLE;
		cue_play(CUE_ERROR, now);
		return;
	}
	if (now - cal.step_t0 < CAL_SETTLE_MS) {
		return;
	}
	if (cal.state == CAL_RAISED) {
		float c = (acc[0] * cal.level[0] + acc[1] * cal.level[1] + acc[2] * cal.level[2]) /
			  (norm3(acc) * norm3(cal.level) + 1e-6f);

		still = still && c < CAL_MIN_RAISE_COS;
	}
	if (!still) {
		cal.n = 0;
		memset(cal.sum, 0, sizeof(cal.sum));
		return;
	}
	for (int i = 0; i < 3; i++) {
		cal.sum[i] += acc[i];
	}
	if (++cal.n < CAL_SAMPLES) {
		return;
	}

	float avg[3] = {cal.sum[0] / cal.n, cal.sum[1] / cal.n, cal.sum[2] / cal.n};

	if (cal.state == CAL_LEVEL) {
		memcpy(cal.level, avg, sizeof(avg));
		cal.state = CAL_RAISED;
		cal.step_t0 = now;
		cal.n = 0;
		memset(cal.sum, 0, sizeof(cal.sum));
		cue_play(CUE_CAL_STEP2, now);
		return;
	}

	struct mount m;

	cal.state = CAL_IDLE;
	if (mount_from_poses(&m, cal.level, avg) == 0) {
		mnt = m;
		store_save_mount(&m);
		reset_tilt();
		store_save_zero(&fus.zero);
		cue_play(CUE_CAL_OK, now);
	} else {
		cue_play(CUE_ERROR, now);
	}
}

static void output(uint32_t now, uint32_t tick)
{
	struct tone t = {.freq_hz = 440.0f};
	uint16_t cue_hz;
	float vol = vol_levels[g_store.volume % ARRAY_SIZE(vol_levels)];

	if (cue_current(now, &cue_hz)) {
		t.freq_hz = cue_hz ? cue_hz : 440.0f;
		t.gain_l = t.gain_r = cue_hz ? vol : 0.0f;
		t.flags = 0;
	} else if (muted || cal.state != CAL_IDLE) {
		t.gain_l = t.gain_r = 0.0f;
	} else {
		struct tonemap_in in;

		fusion_output(&fus, now, &in);
		tonemap_compute(&tcfg, &in, &t);
		t.gain_l *= vol;
		t.gain_r *= vol;
	}

	/* Bluetooth route needs the Pi; fall back to the wire if it's gone. */
	bool bt = (g_store.route & ROUTE_BT) && fusion_pi_present(&fus, now);
	bool wired = (g_store.route & ROUTE_WIRED) || !bt;

	if (wired) {
		audio_set(t.freq_hz, t.gain_l, t.gain_r, t.flags);
	} else {
		audio_set(t.freq_hz, 0.0f, 0.0f, 0);
	}
	if (bt && (tick % TONE_TX_EVERY) == 0) {
		char buf[PROTO_MAX_LINE];

		send_line(buf, proto_fmt_tone(buf, sizeof(buf), (uint32_t)lroundf(t.freq_hz * 10.0f),
					      (unsigned int)lroundf(t.gain_l * 100.0f),
					      (unsigned int)lroundf(t.gain_r * 100.0f), t.flags));
	}
	audio_poll();
}

static void power_off(void)
{
	uint32_t t0 = k_uptime_get_32();
	uint16_t hz;

	LOG_INF("idle: powering off");
	cue_play(CUE_POWEROFF, t0);
	while (cue_current(k_uptime_get_32(), &hz)) {
		audio_set(hz ? hz : 440.0f, hz ? 0.5f : 0.0f, hz ? 0.5f : 0.0f, 0);
		k_msleep(TICK_MS);
	}
	audio_shutdown();
	imu_suspend();
	link_suspend();
	k_msleep(100);
	while (buttons_any_pressed()) {
		k_msleep(TICK_MS); /* a held wake button would wake us at once */
	}
	if (buttons_arm_wakeup() == 0) {
		sys_poweroff();
	}
	LOG_ERR("could not arm wake button; staying on");
}

int main(void)
{
	float raw_acc[3], raw_gyro[3], acc[3], gyro[3];
	uint32_t last_cyc, tick = 0, last_hello = 0, imu_errs = 0;
	struct app_evt evt;
	int err;

	err = store_init();
	if (err) {
		LOG_ERR("settings init: %d", err);
	}
	err = link_init();
	if (err) {
		LOG_ERR("link init: %d", err);
	}
	(void)settings_load();
	link_start();
	if (IS_ENABLED(CONFIG_AT_LINK_BLE) && link_bond_count() == 0) {
		/* First boot: let the Pi pair without any button gymnastics. */
		link_pairing_open(CONFIG_AT_PAIRING_WINDOW_S);
	}

	tonemap_default_cfg(&tcfg);
	tcfg.base_hz = (float)CONFIG_AT_BASE_NOTE_HZ;
	tcfg.mdeg_per_semitone = CONFIG_AT_MDEG_PER_SEMITONE;
	tcfg.quantize = IS_ENABLED(CONFIG_AT_QUANTIZE);

	fusion_default_cfg(&fcfg);
	fcfg.link_latency_ms = CONFIG_AT_LINK_LATENCY_MS;
	fusion_init(&fus, &fcfg);
	if (g_store.have_zero) {
		fus.zero = g_store.zero;
	}
	if (g_store.have_mount) {
		mnt = g_store.mount;
	} else if (mount_from_axes(&mnt, CONFIG_AT_IMU_FWD_AXIS, CONFIG_AT_IMU_UP_AXIS)) {
		LOG_ERR("bad AT_IMU_*_AXIS config; using +X forward, +Z up");
		(void)mount_from_axes(&mnt, 1, 3);
	}

	if (audio_init() || imu_init() || buttons_init()) {
		LOG_ERR("hardware init failed");
	}

	uint32_t now = k_uptime_get_32();

	last_activity = now;
	cue_play(CUE_BOOT, now);
	last_cyc = k_cycle_get_32();

	struct k_timer timer;

	k_timer_init(&timer, NULL, NULL);
	k_timer_start(&timer, K_MSEC(TICK_MS), K_MSEC(TICK_MS));

	while (true) {
		k_timer_status_sync(&timer);
		now = k_uptime_get_32();
		tick++;

		while (k_msgq_get(&app_q, &evt, K_NO_WAIT) == 0) {
			handle_event(&evt, now);
		}

		uint32_t cyc = k_cycle_get_32();
		float dt = (float)(cyc - last_cyc) / (float)sys_clock_hw_cycles_per_sec();

		last_cyc = cyc;
		if (imu_read(raw_acc, raw_gyro) == 0) {
			imu_errs = 0;
			mount_apply(&mnt, raw_acc, acc);
			mount_apply(&mnt, raw_gyro, gyro);
			fusion_imu_update(&fus, acc, gyro, now, dt);
			if (cal.state != CAL_IDLE) {
				cal_update(raw_acc, raw_gyro, now);
			}
		} else if (++imu_errs == 50) {
			cue_play(CUE_ERROR, now);
		}

		output(now, tick);

		if (now - last_hello >= HELLO_EVERY_MS) {
			last_hello = now;
			send_status();
		}

		if (!fusion_is_still(&fus, 1)) {
			last_activity = now;
		}
		if (CONFIG_AT_IDLE_OFF_MIN > 0 &&
		    now - last_activity > (uint32_t)CONFIG_AT_IDLE_OFF_MIN * 60000U) {
			power_off();
			last_activity = k_uptime_get_32();
		}
	}
	return 0;
}
