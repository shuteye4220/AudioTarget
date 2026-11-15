#include "tonemap.h"
#include "proto.h"

#include <math.h>
#include <stdlib.h>

void tonemap_default_cfg(struct tonemap_cfg *cfg)
{
	cfg->base_hz = 440.0f;
	cfg->mdeg_per_semitone = 100;
	cfg->quantize = true;
	cfg->max_semitones = 24;
	cfg->az_full_mdeg = 2000;
	cfg->az_deadband_mdeg = 100;
	cfg->min_side_gain = 0.1f;
	cfg->cant_warn_mdeg = 2000;
}

static float clampf(float v, float lo, float hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

void tonemap_compute(const struct tonemap_cfg *cfg, const struct tonemap_in *in,
		     struct tone *out)
{
	float semis = (float)in->el_err_mdeg / (float)cfg->mdeg_per_semitone;

	if (cfg->quantize) {
		semis = roundf(semis);
	}
	semis = clampf(semis, -(float)cfg->max_semitones, (float)cfg->max_semitones);
	out->freq_hz = cfg->base_hz * exp2f(semis / 12.0f);

	out->gain_l = 1.0f;
	out->gain_r = 1.0f;
	if (in->az_valid && abs(in->az_err_mdeg) > cfg->az_deadband_mdeg) {
		/*
		 * The target is on the side of the louder ear: turn toward the sound.
		 * Aiming right (az_err > 0) means the target is to the left.
		 */
		float span = (float)(cfg->az_full_mdeg - cfg->az_deadband_mdeg);
		float mag = (float)(abs(in->az_err_mdeg) - cfg->az_deadband_mdeg);
		float far = 1.0f - clampf(mag / span, 0.0f, 1.0f) * (1.0f - cfg->min_side_gain);

		if (in->az_err_mdeg > 0) {
			out->gain_r = far;
		} else {
			out->gain_l = far;
		}
	}

	out->flags = 0;
	if (abs(in->cant_mdeg) > cfg->cant_warn_mdeg) {
		out->flags |= TONE_FLAG_CANT;
	}
	if (in->lost) {
		out->flags |= TONE_FLAG_LOST;
	}
}
