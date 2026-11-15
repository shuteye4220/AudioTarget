#include "audio.h"
#include "proto.h"

#include <math.h>
#include <string.h>

#include <zephyr/devicetree.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

#include <hal/nrf_gpio.h>
#include <nrfx_pwm.h>

LOG_MODULE_REGISTER(audio, LOG_LEVEL_INF);

#define USER_NODE DT_PATH(zephyr_user)
#define AUDIO_PIN(i)                                                                           \
	NRF_GPIO_PIN_MAP(DT_PROP(DT_GPIO_CTLR_BY_IDX(USER_NODE, audio_gpios, i), port),         \
			 DT_GPIO_PIN_BY_IDX(USER_NODE, audio_gpios, i))

BUILD_ASSERT(DT_PROP_LEN(USER_NODE, audio_gpios) == 2,
	     "zephyr,user audio-gpios needs exactly two pins: left, right");

/* 16 MHz / 500 = 32 kHz sample rate, ~9 bit resolution. */
#define PWM_TOP 500
#define SAMPLE_RATE 32000
#define MID (PWM_TOP / 2)
#define AMP_MAX (MID - 2)
#define HALF_LEN 256 /* samples per half buffer = 8 ms */
#define POLARITY BIT(15)

#define SINE_BITS 8
#define SINE_LEN (1 << SINE_BITS)

/* Ramp the DC midpoint over ~100 ms on start/stop to avoid pops. */
#define MID_STEP_PER_BUF (MID / 12 + 1)
#define IDLE_STOP_MS 300

static nrfx_pwm_t pwm = NRFX_PWM_INSTANCE(NRF_PWM1);
static nrf_pwm_values_grouped_t bufs[2][HALF_LEN];
static int16_t sine[SINE_LEN];

struct params {
	uint32_t phase_inc;
	int32_t gl; /* Q15 */
	int32_t gr;
	uint8_t flags;
};

static struct k_spinlock lock;
static struct params target;

/* ISR-owned synthesis state */
static uint32_t phase;
static int32_t cur_gl, cur_gr, cur_mid;
static uint32_t sample_clock;
static volatile bool stopping;
static volatile bool ramp_done;

static bool running;
static int64_t silent_since;

static bool gate_on(uint8_t flags, uint32_t t_ms)
{
	bool on = true;

	if (flags & TONE_FLAG_CANT) {
		on = on && ((t_ms / 62) & 1) == 0; /* 8 Hz flutter */
	}
	if (flags & TONE_FLAG_LOST) {
		on = on && (t_ms % 500) < 150; /* 2 Hz beeps */
	}
	return on;
}

static void fill(nrf_pwm_values_grouped_t *dst)
{
	struct params p;
	k_spinlock_key_t key = k_spin_lock(&lock);

	p = target;
	k_spin_unlock(&lock, key);

	uint32_t t_ms = (uint32_t)(((uint64_t)sample_clock * 1000U) / SAMPLE_RATE);
	bool gate = gate_on(p.flags, t_ms);
	int32_t tgt_l = (gate && !stopping) ? p.gl : 0;
	int32_t tgt_r = (gate && !stopping) ? p.gr : 0;
	int32_t tgt_mid = stopping ? 0 : MID;
	int32_t mid0 = cur_mid;
	int32_t mid1 = mid0 + CLAMP(tgt_mid - mid0, -MID_STEP_PER_BUF, MID_STEP_PER_BUF);

	for (int i = 0; i < HALF_LEN; i++) {
		int32_t gl = cur_gl + ((tgt_l - cur_gl) * i) / HALF_LEN;
		int32_t gr = cur_gr + ((tgt_r - cur_gr) * i) / HALF_LEN;
		int32_t mid = mid0 + ((mid1 - mid0) * i) / HALF_LEN;
		/* Amplitude can't exceed the current midpoint while ramping. */
		int32_t amp = (AMP_MAX * mid) / MID;
		int32_t s = sine[phase >> (32 - SINE_BITS)];
		int32_t l = mid + (((s * gl) >> 15) * amp >> 15);
		int32_t r = mid + (((s * gr) >> 15) * amp >> 15);

		phase += p.phase_inc;
		dst[i].group_0 = (uint16_t)CLAMP(l, 0, PWM_TOP) | POLARITY;
		dst[i].group_1 = (uint16_t)CLAMP(r, 0, PWM_TOP) | POLARITY;
	}
	cur_gl = tgt_l;
	cur_gr = tgt_r;
	cur_mid = mid1;
	sample_clock += HALF_LEN;
	if (stopping && cur_mid == 0) {
		ramp_done = true;
	}
}

static void pwm_handler(nrfx_pwm_event_type_t ev, void *ctx)
{
	ARG_UNUSED(ctx);

	if (ev == NRFX_PWM_EVENT_END_SEQ0) {
		fill(bufs[0]);
	} else if (ev == NRFX_PWM_EVENT_END_SEQ1) {
		fill(bufs[1]);
	}
}

int audio_init(void)
{
	nrfx_pwm_config_t cfg = {
		.output_pins = {AUDIO_PIN(0), NRF_PWM_PIN_NOT_CONNECTED, AUDIO_PIN(1),
				NRF_PWM_PIN_NOT_CONNECTED},
		.irq_priority = 2,
		.base_clock = NRF_PWM_CLK_16MHz,
		.count_mode = NRF_PWM_MODE_UP,
		.top_value = PWM_TOP,
		.load_mode = NRF_PWM_LOAD_GROUPED,
		.step_mode = NRF_PWM_STEP_AUTO,
	};
	int err;

	for (int i = 0; i < SINE_LEN; i++) {
		sine[i] = (int16_t)lrintf(32767.0f * sinf(6.28318531f * (float)i / SINE_LEN));
	}

	IRQ_CONNECT(PWM1_IRQn, 2, nrfx_pwm_irq_handler, &pwm, 0);
	err = nrfx_pwm_init(&pwm, &cfg, pwm_handler, NULL);
	if (err < 0) {
		LOG_ERR("PWM init failed: %d", err);
		return err;
	}
	silent_since = k_uptime_get();
	return 0;
}

static void start(void)
{
	static const nrf_pwm_sequence_t seq0 = {
		.values.p_grouped = bufs[0],
		.length = HALF_LEN * 2,
	};
	static const nrf_pwm_sequence_t seq1 = {
		.values.p_grouped = bufs[1],
		.length = HALF_LEN * 2,
	};

	stopping = false;
	ramp_done = false;
	cur_gl = 0;
	cur_gr = 0;
	cur_mid = 0;
	fill(bufs[0]);
	fill(bufs[1]);
	nrfx_pwm_complex_playback(&pwm, &seq0, &seq1, 1,
				  NRFX_PWM_FLAG_LOOP | NRFX_PWM_FLAG_SIGNAL_END_SEQ0 |
					  NRFX_PWM_FLAG_SIGNAL_END_SEQ1 |
					  NRFX_PWM_FLAG_NO_EVT_FINISHED);
	running = true;
}

void audio_set(float freq_hz, float gain_l, float gain_r, uint8_t flags)
{
	struct params p;

	freq_hz = CLAMP(freq_hz, 20.0f, 8000.0f);
	p.phase_inc = (uint32_t)(freq_hz * (4294967296.0f / SAMPLE_RATE));
	p.gl = (int32_t)(CLAMP(gain_l, 0.0f, 1.0f) * 32767.0f);
	p.gr = (int32_t)(CLAMP(gain_r, 0.0f, 1.0f) * 32767.0f);
	p.flags = flags;

	k_spinlock_key_t key = k_spin_lock(&lock);

	target = p;
	k_spin_unlock(&lock, key);

	if (p.gl > 0 || p.gr > 0) {
		silent_since = -1;
		if (!running) {
			start();
		} else if (stopping) {
			stopping = false; /* ramp back up instead of stopping */
			ramp_done = false;
		}
	} else if (silent_since < 0) {
		silent_since = k_uptime_get();
	}
}

void audio_poll(void)
{
	if (!running) {
		return;
	}
	if (!stopping && silent_since >= 0 && k_uptime_get() - silent_since > IDLE_STOP_MS) {
		stopping = true;
	}
	if (stopping && ramp_done) {
		nrfx_pwm_stop(&pwm, true);
		running = false;
		stopping = false;
		ramp_done = false;
	}
}

void audio_shutdown(void)
{
	if (running) {
		nrfx_pwm_stop(&pwm, true);
		running = false;
	}
}
