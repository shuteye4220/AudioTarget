#include "cues.h"

#include <stddef.h>

#define END {0, 0}

/* Note frequencies (equal temperament, A4 = 440). */
#define C5 523
#define E5 659
#define G5 784
#define A4 440
#define E4 330
#define A5 880
#define D6 1175
#define E6 1319
#define A6 1760

static const struct note boot[] = {{C5, 90}, {E5, 90}, {G5, 140}, END};
static const struct note zero_cam[] = {{A5, 90}, {0, 40}, {D6, 160}, END};
static const struct note zero_tilt[] = {{A5, 160}, END};
static const struct note zero_cleared[] = {{A5, 90}, {0, 40}, {A4, 200}, END};
static const struct note mute_on[] = {{E5, 80}, {A4, 160}, END};
static const struct note mute_off[] = {{A4, 80}, {E5, 160}, END};
static const struct note route1[] = {{1000, 80}, END};
static const struct note route2[] = {{1000, 80}, {0, 90}, {1000, 80}, END};
static const struct note route3[] = {{1000, 80}, {0, 90}, {1000, 80}, {0, 90}, {1000, 80}, END};
static const struct note volume[] = {{E5, 250}, END};
static const struct note tick[] = {{1500, 25}, END};
static const struct note pairing[] = {{1200, 60}, {0, 60}, {1200, 60}, {0, 60}, {1200, 60}, END};
static const struct note ble_up[] = {{E6, 60}, {A6, 80}, END};
static const struct note ble_down[] = {{A6, 60}, {E6, 80}, END};
static const struct note cal1[] = {{600, 400}, END};
static const struct note cal2[] = {{600, 150}, {0, 100}, {600, 150}, END};
static const struct note cal_ok[] = {{C5, 90}, {E5, 90}, {G5, 90}, {1047, 200}, END};
static const struct note error[] = {{220, 350}, END};
static const struct note poweroff[] = {{G5, 90}, {E5, 90}, {C5, 90}, {E4, 200}, END};

static const struct note *const cues[CUE_COUNT] = {
	[CUE_BOOT] = boot,
	[CUE_ZERO_CAM] = zero_cam,
	[CUE_ZERO_TILT] = zero_tilt,
	[CUE_ZERO_CLEARED] = zero_cleared,
	[CUE_MUTE_ON] = mute_on,
	[CUE_MUTE_OFF] = mute_off,
	[CUE_ROUTE_1] = route1,
	[CUE_ROUTE_2] = route2,
	[CUE_ROUTE_3] = route3,
	[CUE_VOLUME] = volume,
	[CUE_TICK] = tick,
	[CUE_PAIRING] = pairing,
	[CUE_BLE_UP] = ble_up,
	[CUE_BLE_DOWN] = ble_down,
	[CUE_CAL_STEP1] = cal1,
	[CUE_CAL_STEP2] = cal2,
	[CUE_CAL_OK] = cal_ok,
	[CUE_ERROR] = error,
	[CUE_POWEROFF] = poweroff,
};

static const struct note *active;
static uint32_t started;

void cue_play(enum cue_id id, uint32_t now_ms)
{
	if (id < CUE_COUNT) {
		active = cues[id];
		started = now_ms;
	}
}

bool cue_current(uint32_t now_ms, uint16_t *hz)
{
	uint32_t t;

	if (active == NULL) {
		return false;
	}
	t = now_ms - started;
	for (const struct note *n = active; n->ms != 0; n++) {
		if (t < n->ms) {
			*hz = n->hz;
			return true;
		}
		t -= n->ms;
	}
	active = NULL;
	return false;
}
