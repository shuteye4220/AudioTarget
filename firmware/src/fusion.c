#include "fusion.h"

#include <math.h>
#include <string.h>

#define RAD_TO_MDEG 57295.7795f
#define GRAVITY 9.80665f

void fusion_default_cfg(struct fusion_cfg *cfg)
{
	cfg->tilt_alpha = 0.98f;
	cfg->cam_gain = 0.5f;
	cfg->cam_timeout_ms = 300;
	cfg->pi_timeout_ms = 2500;
	cfg->link_latency_ms = 5;
	cfg->bias_rate = 0.002f;
	cfg->still_rad_s = 0.01f;
}

void fusion_init(struct fusion *f, const struct fusion_cfg *cfg)
{
	memset(f, 0, sizeof(*f));
	f->cfg = *cfg;
}

static void hist_push(struct fusion *f, uint32_t now_ms)
{
	struct fusion_hist *h = &f->hist[f->hist_head];

	h->t_ms = now_ms;
	h->i_el = f->i_el;
	h->i_az = f->i_az;
	f->hist_head = (f->hist_head + 1) % FUSION_HIST_LEN;
	if (f->hist_count < FUSION_HIST_LEN) {
		f->hist_count++;
	}
}

/* Newest history entry at or before t_ms (oldest available if none). */
static const struct fusion_hist *hist_at(const struct fusion *f, uint32_t now_ms, uint32_t t_ms)
{
	const struct fusion_hist *best = NULL;
	uint32_t want_age = now_ms - t_ms;

	for (unsigned int i = 1; i <= f->hist_count; i++) {
		unsigned int idx = (f->hist_head + FUSION_HIST_LEN - i) % FUSION_HIST_LEN;
		const struct fusion_hist *h = &f->hist[idx];

		best = h;
		if ((uint32_t)(now_ms - h->t_ms) >= want_age) {
			break;
		}
	}
	return best;
}

void fusion_imu_update(struct fusion *f, const float acc[3], const float gyro[3],
		       uint32_t now_ms, float dt_s)
{
	float g[3];
	float gnorm, anorm;

	if (dt_s <= 0.0f || dt_s > 0.1f) {
		dt_s = 0.01f; /* first sample or a hiccup; don't integrate garbage */
	}

	for (int i = 0; i < 3; i++) {
		g[i] = gyro[i] - f->gyro_bias[i];
	}
	anorm = sqrtf(acc[0] * acc[0] + acc[1] * acc[1] + acc[2] * acc[2]);

	/*
	 * Stillness is judged by how much the gyro wobbles around its own short-term
	 * average, so it works before the bias is known (zero-rate offsets on cheap
	 * IMUs can be several deg/s).
	 */
	float dev2 = 0.0f, lp_bias2 = 0.0f;

	for (int i = 0; i < 3; i++) {
		f->gyro_lp[i] += 0.05f * (gyro[i] - f->gyro_lp[i]);
		dev2 += (gyro[i] - f->gyro_lp[i]) * (gyro[i] - f->gyro_lp[i]);
		lp_bias2 += (f->gyro_lp[i] - f->gyro_bias[i]) * (f->gyro_lp[i] - f->gyro_bias[i]);
	}
	gnorm = sqrtf(dev2);

	if (gnorm < f->cfg.still_rad_s && fabsf(anorm - GRAVITY) < 0.5f &&
	    lp_bias2 < 0.25f * 0.25f) {
		f->still_ms += (uint32_t)(dt_s * 1000.0f);
	} else {
		f->still_ms = 0;
	}
	if (f->still_ms > 500) {
		/* Learn fast until the first good fix, then slowly track drift. */
		float rate = f->bias_locked ? f->cfg.bias_rate : 0.05f;

		for (int i = 0; i < 3; i++) {
			f->gyro_bias[i] += rate * (f->gyro_lp[i] - f->gyro_bias[i]);
		}
		if (f->still_ms > 2500) {
			f->bias_locked = true;
		}
	}

	/* Gun-frame rates in mdeg/s. +y is left, so +wy tips the muzzle down. */
	float pitch_up_rate = -g[1] * RAD_TO_MDEG;
	float yaw_right_rate = -g[2] * RAD_TO_MDEG;
	float cant_rate = g[0] * RAD_TO_MDEG;

	float acc_pitch = atan2f(acc[0], sqrtf(acc[1] * acc[1] + acc[2] * acc[2])) * RAD_TO_MDEG;
	float acc_cant = atan2f(acc[1], acc[2]) * RAD_TO_MDEG;

	if (!f->tilt_init) {
		f->pitch_mdeg = acc_pitch;
		f->cant_mdeg = acc_cant;
		f->tilt_init = true;
	} else {
		float a = f->cfg.tilt_alpha;

		f->pitch_mdeg = a * (f->pitch_mdeg + pitch_up_rate * dt_s) + (1.0f - a) * acc_pitch;
		f->cant_mdeg = a * (f->cant_mdeg + cant_rate * dt_s) + (1.0f - a) * acc_cant;
	}

	f->i_el += pitch_up_rate * dt_s;
	f->i_az += yaw_right_rate * dt_s;
	hist_push(f, now_ms);

	if (f->cam_tracking) {
		if ((uint32_t)(now_ms - f->last_cam_ms) > f->cfg.cam_timeout_ms) {
			f->cam_tracking = false;
		} else {
			f->est_el += pitch_up_rate * dt_s;
			f->est_az += yaw_right_rate * dt_s;
		}
	}
}

void fusion_pi_alive(struct fusion *f, uint32_t now_ms)
{
	f->pi_seen = true;
	f->last_pi_ms = now_ms;
}

void fusion_cam_update(struct fusion *f, int32_t az_mdeg, int32_t el_mdeg, uint32_t age_ms,
		       uint32_t now_ms)
{
	fusion_pi_alive(f, now_ms);
	f->last_cam_az = az_mdeg;
	f->last_cam_el = el_mdeg;

	/* Aim error as seen in the frame: target above the zero point = aiming low. */
	float meas_el = (float)(f->zero.cam_el0_mdeg - el_mdeg);
	float meas_az = (float)(f->zero.cam_az0_mdeg - az_mdeg);

	/* How far have we rotated since the frame was exposed? */
	float d_el = 0.0f, d_az = 0.0f;
	const struct fusion_hist *h =
		hist_at(f, now_ms, now_ms - age_ms - f->cfg.link_latency_ms);

	if (h != NULL) {
		d_el = f->i_el - h->i_el;
		d_az = f->i_az - h->i_az;
	}

	if (!f->cam_tracking) {
		f->est_el = meas_el + d_el;
		f->est_az = meas_az + d_az;
		f->cam_tracking = true;
	} else {
		f->est_el += f->cfg.cam_gain * (meas_el - (f->est_el - d_el));
		f->est_az += f->cfg.cam_gain * (meas_az - (f->est_az - d_az));
	}
	f->last_cam_ms = now_ms;
}

bool fusion_cam_active(const struct fusion *f, uint32_t now_ms)
{
	return f->cam_tracking && (uint32_t)(now_ms - f->last_cam_ms) <= f->cfg.cam_timeout_ms;
}

bool fusion_pi_present(const struct fusion *f, uint32_t now_ms)
{
	return f->pi_seen && (uint32_t)(now_ms - f->last_pi_ms) <= f->cfg.pi_timeout_ms;
}

bool fusion_is_still(const struct fusion *f, uint32_t min_ms)
{
	return f->still_ms >= min_ms;
}

unsigned int fusion_zero(struct fusion *f, uint32_t now_ms)
{
	unsigned int bits = 0;

	if (f->tilt_init) {
		f->zero.pitch0_mdeg = f->pitch_mdeg;
		f->zero.cant0_mdeg = f->cant_mdeg;
		f->zero.tilt_valid = true;
		bits |= FUSION_ZERO_TILT;
	}
	if (fusion_cam_active(f, now_ms)) {
		/* Shift the zero so the current estimated error becomes zero. */
		f->zero.cam_el0_mdeg -= (int32_t)lroundf(f->est_el);
		f->zero.cam_az0_mdeg -= (int32_t)lroundf(f->est_az);
		f->zero.cam_valid = true;
		f->est_el = 0.0f;
		f->est_az = 0.0f;
		bits |= FUSION_ZERO_CAM;
	}
	return bits;
}

void fusion_clear_zero(struct fusion *f)
{
	/* Re-base the running estimate so clearing doesn't cause a jump later. */
	f->est_el += (float)(0 - f->zero.cam_el0_mdeg);
	f->est_az += (float)(0 - f->zero.cam_az0_mdeg);
	memset(&f->zero, 0, sizeof(f->zero));
}

void fusion_output(const struct fusion *f, uint32_t now_ms, struct tonemap_in *out)
{
	bool cam = fusion_cam_active(f, now_ms);

	if (cam) {
		out->el_err_mdeg = (int32_t)lroundf(f->est_el);
		out->az_err_mdeg = (int32_t)lroundf(f->est_az);
	} else {
		float p0 = f->zero.tilt_valid ? f->zero.pitch0_mdeg : 0.0f;

		out->el_err_mdeg = (int32_t)lroundf(f->pitch_mdeg - p0);
		out->az_err_mdeg = 0;
	}
	out->az_valid = cam;
	out->cant_mdeg =
		(int32_t)lroundf(f->cant_mdeg - (f->zero.tilt_valid ? f->zero.cant0_mdeg : 0.0f));
	out->lost = fusion_pi_present(f, now_ms) && !cam;
}
