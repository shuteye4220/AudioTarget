/* Persistent settings (zero, mount calibration, audio route, volume). */
#ifndef AUDIOTARGET_STORE_H_
#define AUDIOTARGET_STORE_H_

#include <stdbool.h>
#include <stdint.h>

#include "fusion.h"
#include "mount.h"

struct store {
	bool have_zero;
	struct fusion_zero zero;
	bool have_mount;
	struct mount mount;
	uint8_t route;
	uint8_t volume;
};

extern struct store g_store;

/* settings_subsys_init(); the caller runs settings_load() afterwards. */
int store_init(void);
void store_save_zero(const struct fusion_zero *z);
void store_save_mount(const struct mount *m);
void store_save_route(uint8_t route);
void store_save_volume(uint8_t vol);

#endif
