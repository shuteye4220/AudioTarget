#include "store.h"
#include "proto.h"

#include <errno.h>
#include <math.h>
#include <string.h>

#include <zephyr/logging/log.h>
#include <zephyr/settings/settings.h>

LOG_MODULE_REGISTER(store, LOG_LEVEL_INF);

struct store g_store;

static int read_exact(void *dst, size_t want, size_t len, settings_read_cb read_cb, void *cb_arg)
{
	if (len != want) {
		return -EINVAL; /* stale layout from an older firmware: ignore it */
	}
	return read_cb(cb_arg, dst, want) == (ssize_t)want ? 0 : -EIO;
}

static bool zero_sane(const struct fusion_zero *z)
{
	const float lim = 90000.0f; /* millidegrees */

	return isfinite(z->pitch0_mdeg) && isfinite(z->cant0_mdeg) && fabsf(z->pitch0_mdeg) <= lim &&
	       fabsf(z->cant0_mdeg) <= 180000.0f && z->cam_az0_mdeg >= -PROTO_MAX_ANGLE_MDEG &&
	       z->cam_az0_mdeg <= PROTO_MAX_ANGLE_MDEG && z->cam_el0_mdeg >= -PROTO_MAX_ANGLE_MDEG &&
	       z->cam_el0_mdeg <= PROTO_MAX_ANGLE_MDEG;
}

static int h_set(const char *name, size_t len, settings_read_cb read_cb, void *cb_arg)
{
	const char *next;

	if (settings_name_steq(name, "zero", &next) && !next) {
		struct fusion_zero z;

		if (read_exact(&z, sizeof(z), len, read_cb, cb_arg) == 0 && zero_sane(&z)) {
			g_store.zero = z;
			g_store.have_zero = true;
		}
		return 0;
	}
	if (settings_name_steq(name, "mount", &next) && !next) {
		struct mount m;

		if (read_exact(&m, sizeof(m), len, read_cb, cb_arg) == 0 && mount_valid(&m)) {
			g_store.mount = m;
			g_store.have_mount = true;
		}
		return 0;
	}
	if (settings_name_steq(name, "route", &next) && !next) {
		uint8_t v;

		if (read_exact(&v, 1, len, read_cb, cb_arg) == 0 && v >= 1 && v <= 3) {
			g_store.route = v;
		}
		return 0;
	}
	if (settings_name_steq(name, "vol", &next) && !next) {
		uint8_t v;

		if (read_exact(&v, 1, len, read_cb, cb_arg) == 0 && v < 4) {
			g_store.volume = v;
		}
		return 0;
	}
	return -ENOENT;
}

SETTINGS_STATIC_HANDLER_DEFINE(at, "at", NULL, h_set, NULL, NULL);

int store_init(void)
{
	g_store.route = 1;  /* wired */
	g_store.volume = 1;
	return settings_subsys_init();
}

static void save(const char *key, const void *v, size_t len)
{
	int err = settings_save_one(key, v, len);

	if (err) {
		LOG_ERR("save %s failed: %d", key, err);
	}
}

void store_save_zero(const struct fusion_zero *z)
{
	g_store.zero = *z;
	g_store.have_zero = true;
	save("at/zero", z, sizeof(*z));
}

void store_save_mount(const struct mount *m)
{
	g_store.mount = *m;
	g_store.have_mount = true;
	save("at/mount", m, sizeof(*m));
}

void store_save_route(uint8_t route)
{
	g_store.route = route;
	save("at/route", &route, 1);
}

void store_save_volume(uint8_t vol)
{
	g_store.volume = vol;
	save("at/vol", &vol, 1);
}
