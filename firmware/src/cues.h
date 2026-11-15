/* Short audible status cues (there is no screen). See docs/sounds.md. */
#ifndef AUDIOTARGET_CUES_H_
#define AUDIOTARGET_CUES_H_

#include <stdbool.h>
#include <stdint.h>

struct note {
	uint16_t hz; /* 0 = rest */
	uint16_t ms;
};

enum cue_id {
	CUE_BOOT,
	CUE_ZERO_CAM,
	CUE_ZERO_TILT,
	CUE_ZERO_CLEARED,
	CUE_MUTE_ON,
	CUE_MUTE_OFF,
	CUE_ROUTE_1,
	CUE_ROUTE_2,
	CUE_ROUTE_3,
	CUE_VOLUME,
	CUE_TICK,
	CUE_PAIRING,
	CUE_BLE_UP,
	CUE_BLE_DOWN,
	CUE_CAL_STEP1,
	CUE_CAL_STEP2,
	CUE_CAL_OK,
	CUE_ERROR,
	CUE_POWEROFF,
	CUE_COUNT,
};

void cue_play(enum cue_id id, uint32_t now_ms);
/* Returns true while a cue is playing, with the current note in *hz (0 = rest). */
bool cue_current(uint32_t now_ms, uint16_t *hz);

#endif
