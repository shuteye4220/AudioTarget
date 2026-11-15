/*
 * Aim estimation.
 *
 * Tilt mode: accelerometer + gyro complementary filter gives barrel pitch
 * (high/low) and cant (sideways tilt) relative to the stored zero.
 *
 * Camera mode: the Pi reports where the target card sits relative to the
 * camera axis. Gyro rates carry the estimate between frames, and each frame
 * pulls it back toward the camera's answer, compensating for camera latency
 * by comparing against where the gyro thought we were when the frame was
 * exposed.
 *
 * All vectors are in the gun frame: x = forward (muzzle), y = left, z = up.
 * Pure C for host testing.
 */
#ifndef AUDIOTARGET_FUSION_H_
#define AUDIOTARGET_FUSION_H_

#include <stdbool.h>
#include <stdint.h>

#include "tonemap.h"

#define FUSION_HIST_LEN 64 /* ~640 ms at 100 Hz */

struct fusion_cfg {
	float tilt_alpha;         /* complementary filter gyro weight per step */
	float cam_gain;           /* 0..1 pull toward each camera sample */
	uint32_t cam_timeout_ms;  /* camera sample considered stale after this */
	uint32_t pi_timeout_ms;   /* no Pi messages for this long = Pi absent */
	uint32_t link_latency_ms; /* added to the Pi-reported frame age */
	float bias_rate;          /* online gyro-bias learning rate when still */
	float still_rad_s;        /* below this the gun counts as still */
};

struct fusion_zero {
	bool tilt_valid;
	bool cam_valid;
	float pitch0_mdeg;
	float cant0_mdeg;
	int32_t cam_az0_mdeg;
	int32_t cam_el0_mdeg;
};

struct fusion_hist {
	uint32_t t_ms;
	float i_el; /* integrated pitch-up rotation, mdeg */
	float i_az; /* integrated yaw-right rotation, mdeg */
};

struct fusion {
	struct fusion_cfg cfg;
	struct fusion_zero zero;

	bool tilt_init;
	float pitch_mdeg;
	float cant_mdeg;

	float gyro_bias[3];
	float gyro_lp[3];  /* short-term gyro average */
	bool bias_locked;  /* first bias fix done */
	uint32_t still_ms; /* how long the gun has been still */

	float i_el, i_az;
	struct fusion_hist hist[FUSION_HIST_LEN];
	unsigned int hist_head;
	unsigned int hist_count;

	bool cam_tracking;
	uint32_t last_cam_ms;
	uint32_t last_pi_ms;
	bool pi_seen;
	int32_t last_cam_az, last_cam_el; /* raw target position, for zeroing */
	float est_el, est_az;             /* aim error estimate, mdeg */
};

#define FUSION_ZERO_TILT 0x1
#define FUSION_ZERO_CAM 0x2

void fusion_default_cfg(struct fusion_cfg *cfg);
void fusion_init(struct fusion *f, const struct fusion_cfg *cfg);

/* acc in m/s^2, gyro in rad/s, both in the gun frame. */
void fusion_imu_update(struct fusion *f, const float acc[3], const float gyro[3],
		       uint32_t now_ms, float dt_s);

/* Raw target position from the Pi (relative to the camera axis). */
void fusion_cam_update(struct fusion *f, int32_t az_mdeg, int32_t el_mdeg, uint32_t age_ms,
		       uint32_t now_ms);
/* Any message from the Pi (proves the camera link is alive). */
void fusion_pi_alive(struct fusion *f, uint32_t now_ms);

/* Store the current pose as "on target". Returns FUSION_ZERO_* bits. */
unsigned int fusion_zero(struct fusion *f, uint32_t now_ms);
void fusion_clear_zero(struct fusion *f);

bool fusion_cam_active(const struct fusion *f, uint32_t now_ms);
bool fusion_pi_present(const struct fusion *f, uint32_t now_ms);
bool fusion_is_still(const struct fusion *f, uint32_t min_ms);
void fusion_output(const struct fusion *f, uint32_t now_ms, struct tonemap_in *out);

#endif
