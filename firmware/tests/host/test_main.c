/* Host unit tests for the pure-C firmware modules. Run: make -C firmware/tests/host */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fusion.h"
#include "mount.h"
#include "proto.h"
#include "tonemap.h"

static int failures;

#define CHECK(cond)                                                                            \
	do {                                                                                   \
		if (!(cond)) {                                                                 \
			printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                 \
			failures++;                                                            \
		}                                                                              \
	} while (0)

static void test_proto_parse(void)
{
	struct proto_msg m;

	CHECK(proto_parse("C 12 -1500 250 2000 40", &m) == 0);
	CHECK(m.type == PROTO_CAM && m.seq == 12 && m.az_mdeg == -1500 && m.el_mdeg == 250 &&
	      m.range_cm == 2000 && m.age_ms == 40);
	CHECK(proto_parse("N 4294967295", &m) == 0 && m.type == PROTO_NOTARGET &&
	      m.seq == 4294967295u);
	CHECK(proto_parse("H 1 pi", &m) == 0 && m.type == PROTO_HELLO && m.version == 1);

	/* Rejections */
	CHECK(proto_parse("", &m) < 0);
	CHECK(proto_parse("C", &m) < 0);
	CHECK(proto_parse("C 1 2 3 4", &m) < 0);           /* missing field */
	CHECK(proto_parse("C 1 2 3 4 5 6", &m) < 0);       /* extra field */
	CHECK(proto_parse("C 1 46000 0 0 0", &m) < 0);     /* angle out of range */
	CHECK(proto_parse("C 1 0 0 0 5000", &m) < 0);      /* stale */
	CHECK(proto_parse("C 1 0 0 -1 0", &m) < 0);        /* negative range */
	CHECK(proto_parse("C 1 0x10 0 0 0", &m) < 0);      /* not decimal */
	CHECK(proto_parse("C 1  0 0 0 0", &m) < 0);        /* double space */
	CHECK(proto_parse("N 99999999999", &m) < 0);       /* overflow */
	CHECK(proto_parse("N 4294967296", &m) < 0);        /* > uint32 */
	CHECK(proto_parse("X 1", &m) < 0);
	CHECK(proto_parse("H 1 waytoolongrole", &m) < 0);
	CHECK(proto_parse("C 1 - 0 0 0", &m) < 0);
}

static void test_line_asm(void)
{
	struct line_asm la;
	const char *in = "C 1 2 3 4 5\r\nN 7\n";
	int lines = 0;

	line_asm_reset(&la);
	for (const char *p = in; *p; p++) {
		if (line_asm_feed(&la, *p)) {
			lines++;
			CHECK(strcmp(la.buf, lines == 1 ? "C 1 2 3 4 5" : "N 7") == 0);
		}
	}
	CHECK(lines == 2);

	/* Over-long line is dropped, next line still works. */
	line_asm_reset(&la);
	for (int i = 0; i < 200; i++) {
		CHECK(!line_asm_feed(&la, 'a'));
	}
	CHECK(!line_asm_feed(&la, '\n'));
	CHECK(!line_asm_feed(&la, 'N'));
	CHECK(!line_asm_feed(&la, ' '));
	CHECK(!line_asm_feed(&la, '1'));
	CHECK(line_asm_feed(&la, '\n') && strcmp(la.buf, "N 1") == 0);

	/* Binary garbage poisons only its own line. */
	CHECK(!line_asm_feed(&la, 'N'));
	CHECK(!line_asm_feed(&la, (char)0x01));
	CHECK(!line_asm_feed(&la, '\n'));
}

static void test_proto_fmt(void)
{
	char buf[PROTO_MAX_LINE];

	CHECK(proto_fmt_tone(buf, sizeof(buf), 4400, 100, 35, 3) > 0);
	CHECK(strcmp(buf, "T 4400 100 35 3\n") == 0);
	CHECK(proto_fmt_tone(buf, 5, 4400, 100, 35, 3) < 0);
	CHECK(proto_fmt_hello(buf, sizeof(buf)) > 0 && strcmp(buf, "H 1 nrf\n") == 0);
}

static void test_tonemap(void)
{
	struct tonemap_cfg cfg;
	struct tonemap_in in = {0};
	struct tone t;

	tonemap_default_cfg(&cfg);
	tonemap_compute(&cfg, &in, &t);
	CHECK(fabsf(t.freq_hz - 440.0f) < 0.01f && t.gain_l == 1.0f && t.gain_r == 1.0f &&
	      t.flags == 0);

	in.el_err_mdeg = 1200; /* 12 semitones high -> octave up */
	tonemap_compute(&cfg, &in, &t);
	CHECK(fabsf(t.freq_hz - 880.0f) < 0.1f);

	in.el_err_mdeg = -140; /* quantized: -1.4 -> -1 semitone */
	tonemap_compute(&cfg, &in, &t);
	CHECK(fabsf(t.freq_hz - 415.30f) < 0.1f);

	in.el_err_mdeg = -100000; /* clamp at -24 */
	tonemap_compute(&cfg, &in, &t);
	CHECK(fabsf(t.freq_hz - 110.0f) < 0.1f);

	/* Aiming right -> target is left -> right ear quieter. */
	in.el_err_mdeg = 0;
	in.az_valid = true;
	in.az_err_mdeg = 5000;
	tonemap_compute(&cfg, &in, &t);
	CHECK(t.gain_l == 1.0f && fabsf(t.gain_r - cfg.min_side_gain) < 1e-4f);
	in.az_err_mdeg = -50; /* inside deadband */
	tonemap_compute(&cfg, &in, &t);
	CHECK(t.gain_l == 1.0f && t.gain_r == 1.0f);
	in.az_valid = false;
	in.az_err_mdeg = 5000; /* ignored without camera */
	tonemap_compute(&cfg, &in, &t);
	CHECK(t.gain_r == 1.0f);

	in.cant_mdeg = -2500;
	in.lost = true;
	tonemap_compute(&cfg, &in, &t);
	CHECK(t.flags == (TONE_FLAG_CANT | TONE_FLAG_LOST));
}

/* Gravity reading (specific force) for a gun pitched up by `pitch` and canted right by `cant`. */
static void acc_for(float pitch_deg, float cant_deg, float out[3])
{
	float p = pitch_deg * (float)M_PI / 180.0f, c = cant_deg * (float)M_PI / 180.0f;

	out[0] = 9.80665f * sinf(p);
	out[1] = 9.80665f * cosf(p) * sinf(c);
	out[2] = 9.80665f * cosf(p) * cosf(c);
}

static void test_fusion_tilt(void)
{
	struct fusion_cfg cfg;
	struct fusion f;
	struct tonemap_in out;
	float acc[3], gyro[3] = {0};
	uint32_t t = 0;

	fusion_default_cfg(&cfg);
	fusion_init(&f, &cfg);

	acc_for(2.0f, 0.0f, acc);
	for (int i = 0; i < 300; i++, t += 10) {
		fusion_imu_update(&f, acc, gyro, t, 0.01f);
	}
	fusion_output(&f, t, &out);
	CHECK(abs(out.el_err_mdeg - 2000) < 20);
	CHECK(!out.az_valid && !out.lost);

	CHECK(fusion_zero(&f, t) == FUSION_ZERO_TILT);
	fusion_output(&f, t, &out);
	CHECK(abs(out.el_err_mdeg) < 5);

	/* Raise the muzzle 0.5 degree. */
	acc_for(2.5f, 3.0f, acc);
	for (int i = 0; i < 400; i++, t += 10) {
		fusion_imu_update(&f, acc, gyro, t, 0.01f);
	}
	fusion_output(&f, t, &out);
	CHECK(abs(out.el_err_mdeg - 500) < 20);
	CHECK(abs(out.cant_mdeg - 3000) < 50);
}

static void test_fusion_camera(void)
{
	struct fusion_cfg cfg;
	struct fusion f;
	struct tonemap_in out;
	float acc[3], gyro[3] = {0};
	uint32_t t = 0;
	uint32_t seq = 0;

	fusion_default_cfg(&cfg);
	cfg.link_latency_ms = 0;
	fusion_init(&f, &cfg);
	acc_for(0.0f, 0.0f, acc);

	/* Target 1 degree above and 0.5 degree left of the camera axis. */
	for (int i = 0; i < 100; i++, t += 10) {
		fusion_imu_update(&f, acc, gyro, t, 0.01f);
		if (i % 3 == 0) {
			fusion_cam_update(&f, -500, 1000, 50, t);
			seq++;
		}
	}
	fusion_output(&f, t, &out);
	CHECK(out.az_valid);
	CHECK(abs(out.el_err_mdeg + 1000) < 30); /* aiming low */
	CHECK(abs(out.az_err_mdeg - 500) < 30);  /* aiming right */

	CHECK(fusion_zero(&f, t) == (FUSION_ZERO_TILT | FUSION_ZERO_CAM));
	fusion_output(&f, t, &out);
	CHECK(abs(out.el_err_mdeg) < 5 && abs(out.az_err_mdeg) < 5);

	/*
	 * Now rotate the muzzle up at 10 deg/s for 0.1 s (1 degree). The camera
	 * reports with 60 ms latency; the estimate should track the gyro right away
	 * and not be dragged back by stale frames.
	 */
	const float rate = 10.0f * (float)M_PI / 180.0f; /* rad/s */
	float true_el_err = 0.0f;                         /* mdeg, aiming high */
	float lat_hist[200];
	int n = 0;

	for (int i = 0; i < 60; i++, t += 10, n++) {
		bool moving = i < 10;

		gyro[1] = moving ? -rate : 0.0f; /* -wy = pitch up */
		if (moving) {
			true_el_err += 100.0f;
		}
		lat_hist[n] = true_el_err;
		fusion_imu_update(&f, acc, gyro, t, 0.01f);
		if (i % 3 == 0 && n >= 6) {
			/* Frame exposed 60 ms ago: target appears lower by the error then. */
			float err_then = lat_hist[n - 6];

			fusion_cam_update(&f, -500, 1000 - (int32_t)err_then, 60, t);
		}
		fusion_output(&f, t, &out);
		CHECK(fabsf((float)out.el_err_mdeg - true_el_err) < 120.0f);
	}
	fusion_output(&f, t, &out);
	CHECK(abs(out.el_err_mdeg - 1000) < 30);

	/* Camera stops: falls back to tilt, flagged as lost while Pi still talks. */
	gyro[1] = 0.0f;
	for (int i = 0; i < 50; i++, t += 10) {
		fusion_imu_update(&f, acc, gyro, t, 0.01f);
		fusion_pi_alive(&f, t);
	}
	fusion_output(&f, t, &out);
	CHECK(!out.az_valid && out.lost);

	for (int i = 0; i < 400; i++, t += 10) {
		fusion_imu_update(&f, acc, gyro, t, 0.01f);
	}
	fusion_output(&f, t, &out);
	CHECK(!out.lost); /* Pi gone entirely: plain tilt mode, no lost beeps */
}

static void test_fusion_bias(void)
{
	struct fusion_cfg cfg;
	struct fusion f;
	float acc[3], gyro[3] = {0.005f, -0.004f, 0.003f};
	uint32_t t = 0;

	fusion_default_cfg(&cfg);
	fusion_init(&f, &cfg);
	acc_for(0.0f, 0.0f, acc);
	for (int i = 0; i < 6000; i++, t += 10) {
		fusion_imu_update(&f, acc, gyro, t, 0.01f);
	}
	CHECK(fabsf(f.gyro_bias[0] - 0.005f) < 0.0005f);
	CHECK(fabsf(f.gyro_bias[1] + 0.004f) < 0.0005f);
	CHECK(fusion_is_still(&f, 1000));

	/* A big zero-rate offset (~6 deg/s) is still learned quickly at rest. */
	float big[3] = {0.1f, 0.0f, -0.08f};

	fusion_init(&f, &cfg);
	for (int i = 0; i < 400; i++, t += 10) {
		fusion_imu_update(&f, acc, big, t, 0.01f);
	}
	CHECK(f.bias_locked);
	CHECK(fabsf(f.gyro_bias[0] - 0.1f) < 0.002f && fabsf(f.gyro_bias[2] + 0.08f) < 0.002f);
}

static void test_mount(void)
{
	struct mount mt;
	float v[3], o[3];

	CHECK(mount_from_axes(&mt, 1, 3) == 0 && mount_valid(&mt));
	CHECK(mount_from_axes(&mt, 2, -2) < 0);
	CHECK(mount_from_axes(&mt, 0, 3) < 0);

	/* Sensor mounted with gun-forward = sensor -Y, gun-up = sensor +X. */
	CHECK(mount_from_axes(&mt, -2, 1) == 0 && mount_valid(&mt));
	v[0] = 1.0f; v[1] = 0.0f; v[2] = 0.0f; /* gravity reaction along sensor +X */
	mount_apply(&mt, v, o);
	CHECK(fabsf(o[2] - 1.0f) < 1e-5f && fabsf(o[0]) < 1e-5f);

	/* Pose calibration reproduces that mount from two readings. */
	struct mount cal;
	float level[3] = {9.8f, 0.0f, 0.0f};
	float p = 40.0f * (float)M_PI / 180.0f;
	/* Muzzle raised 40 deg: reaction = cos*up + sin*fwd; fwd is sensor -Y. */
	float raised[3] = {9.8f * cosf(p), -9.8f * sinf(p), 0.0f};

	CHECK(mount_from_poses(&cal, level, raised) == 0 && mount_valid(&cal));
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			CHECK(fabsf(cal.m[i][j] - mt.m[i][j]) < 1e-4f);
		}
	}
	/* Too little raise is refused. */
	float barely[3] = {9.8f, -0.5f, 0.0f};
	CHECK(mount_from_poses(&cal, level, barely) < 0);
	float zero[3] = {0};
	CHECK(mount_from_poses(&cal, zero, raised) < 0);
}

int main(void)
{
	test_mount();
	test_proto_parse();
	test_line_asm();
	test_proto_fmt();
	test_tonemap();
	test_fusion_tilt();
	test_fusion_camera();
	test_fusion_bias();
	if (failures) {
		printf("%d check(s) failed\n", failures);
		return 1;
	}
	printf("all host tests passed\n");
	return 0;
}
