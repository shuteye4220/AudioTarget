/*
 * Turns aim error into a tone: pitch for high/low, left/right ear balance
 * for left/right. Pure C for host testing.
 */
#ifndef AUDIOTARGET_TONEMAP_H_
#define AUDIOTARGET_TONEMAP_H_

#include <stdbool.h>
#include <stdint.h>

struct tonemap_cfg {
	float base_hz;              /* note played when dead on (default A4) */
	int32_t mdeg_per_semitone;  /* vertical error per semitone step */
	bool quantize;              /* snap to whole semitones */
	int32_t max_semitones;      /* clamp */
	int32_t az_full_mdeg;       /* error at which the far ear is quietest */
	int32_t az_deadband_mdeg;   /* centred balance within this window */
	float min_side_gain;        /* far-ear gain at full error */
	int32_t cant_warn_mdeg;     /* flutter above this sideways tilt */
};

struct tonemap_in {
	int32_t el_err_mdeg; /* + = aiming high */
	int32_t az_err_mdeg; /* + = aiming right */
	bool az_valid;       /* only true when the camera is tracking */
	bool lost;           /* camera running but can't see the card */
	int32_t cant_mdeg;   /* + = right side down */
};

struct tone {
	float freq_hz;
	float gain_l; /* 0..1 */
	float gain_r; /* 0..1 */
	uint8_t flags;
};

void tonemap_default_cfg(struct tonemap_cfg *cfg);
void tonemap_compute(const struct tonemap_cfg *cfg, const struct tonemap_in *in,
		     struct tone *out);

#endif
