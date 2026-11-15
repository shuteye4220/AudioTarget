/*
 * Two buttons, polled every 20 ms while either is held (interrupt starts the
 * polling, so nothing runs while idle).
 *
 *   short  (< 0.7 s)
 *   long   (0.7 - 2.5 s)
 *   vlong  (>= 2.5 s)
 *   both held >= 2.5 s: separate gesture, individual events suppressed
 *
 * A tick event fires as each threshold is crossed so the user can hear
 * which gesture they're about to release.
 */
#include "buttons.h"
#include "events.h"

#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(buttons, LOG_LEVEL_INF);

#define USER_NODE DT_PATH(zephyr_user)
BUILD_ASSERT(DT_PROP_LEN(USER_NODE, button_gpios) == 2,
	     "zephyr,user button-gpios needs two entries: zero, mode");

#define POLL_MS 20
#define LONG_MS 700
#define VLONG_MS 2500

enum { B_ZERO, B_MODE, B_COUNT };

static const struct gpio_dt_spec btns[B_COUNT] = {
	GPIO_DT_SPEC_GET_BY_IDX(USER_NODE, button_gpios, 0),
	GPIO_DT_SPEC_GET_BY_IDX(USER_NODE, button_gpios, 1),
};

static struct gpio_callback cbs[B_COUNT];
static struct k_work_delayable poll_work;

struct bstate {
	bool down;
	int64_t since;
	uint8_t ticks; /* thresholds already signalled */
};

static struct bstate st[B_COUNT];
static bool both_gesture;
static int64_t both_since;
static uint8_t both_ticks;

static void post_btn(enum btn_evt e)
{
	struct app_evt evt = {.type = EVT_BTN, .btn = e};

	app_post(&evt);
}

static void tick_check(int64_t held, uint8_t *ticks, bool allow_long)
{
	if (allow_long && held >= LONG_MS && *ticks == 0) {
		*ticks = 1;
		post_btn(BTN_TICK);
	}
	if (held >= VLONG_MS && *ticks < 2) {
		*ticks = 2;
		post_btn(BTN_TICK);
	}
}

static void classify(int which, int64_t held)
{
	static const enum btn_evt map[B_COUNT][3] = {
		{BTN_ZERO_SHORT, BTN_ZERO_LONG, BTN_ZERO_VLONG},
		{BTN_MODE_SHORT, BTN_MODE_LONG, BTN_MODE_VLONG},
	};
	int idx = held >= VLONG_MS ? 2 : (held >= LONG_MS ? 1 : 0);

	post_btn(map[which][idx]);
}

static void poll_fn(struct k_work *work)
{
	int64_t now = k_uptime_get();
	bool any = false;

	ARG_UNUSED(work);

	for (int i = 0; i < B_COUNT; i++) {
		bool down = gpio_pin_get_dt(&btns[i]) > 0;

		if (down && !st[i].down) {
			st[i].down = true;
			st[i].since = now;
			st[i].ticks = 0;
		} else if (!down && st[i].down) {
			st[i].down = false;
			if (!both_gesture) {
				classify(i, now - st[i].since);
			}
		}
		any |= st[i].down;
	}

	if (st[B_ZERO].down && st[B_MODE].down && !both_gesture) {
		both_gesture = true;
		both_since = now;
		both_ticks = 0;
	}

	if (both_gesture) {
		if (st[B_ZERO].down && st[B_MODE].down) {
			tick_check(now - both_since, &both_ticks, false);
		} else if (!any) {
			if (both_ticks >= 2) {
				post_btn(BTN_BOTH_VLONG);
			}
			both_gesture = false;
		}
	} else {
		for (int i = 0; i < B_COUNT; i++) {
			if (st[i].down) {
				tick_check(now - st[i].since, &st[i].ticks, true);
			}
		}
	}

	if (any) {
		k_work_reschedule(&poll_work, K_MSEC(POLL_MS));
	}
}

static void edge_cb(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
	ARG_UNUSED(dev);
	ARG_UNUSED(cb);
	ARG_UNUSED(pins);
	/* Debounce: first poll happens one interval after the edge. */
	k_work_schedule(&poll_work, K_MSEC(POLL_MS));
}

int buttons_init(void)
{
	k_work_init_delayable(&poll_work, poll_fn);

	for (int i = 0; i < B_COUNT; i++) {
		int err;

		if (!gpio_is_ready_dt(&btns[i])) {
			return -ENODEV;
		}
		err = gpio_pin_configure_dt(&btns[i], GPIO_INPUT);
		if (err == 0) {
			err = gpio_pin_interrupt_configure_dt(&btns[i], GPIO_INT_EDGE_TO_ACTIVE);
		}
		if (err) {
			LOG_ERR("button %d config failed: %d", i, err);
			return err;
		}
		gpio_init_callback(&cbs[i], edge_cb, BIT(btns[i].pin));
		gpio_add_callback_dt(&btns[i], &cbs[i]);
	}
	return 0;
}

bool buttons_any_pressed(void)
{
	for (int i = 0; i < B_COUNT; i++) {
		if (gpio_pin_get_dt(&btns[i]) > 0) {
			return true;
		}
	}
	return false;
}

int buttons_arm_wakeup(void)
{
	return gpio_pin_interrupt_configure_dt(&btns[B_MODE], GPIO_INT_LEVEL_ACTIVE);
}
