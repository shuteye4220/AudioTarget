/* Events posted to the main control thread from ISRs, workqueues and BT. */
#ifndef AUDIOTARGET_EVENTS_H_
#define AUDIOTARGET_EVENTS_H_

#include <stdint.h>

#include "proto.h"

enum app_evt_type {
	EVT_LINE,          /* a complete protocol line from a link */
	EVT_BTN,           /* data.btn = enum btn_evt */
	EVT_BLE_SECURED,   /* encrypted connection up */
	EVT_BLE_DISCONNECTED,
	EVT_BLE_PAIRED,
	EVT_BLE_REJECTED,  /* unknown device tried to connect outside pairing window */
};

enum link_src {
	SRC_UART = 1,
	SRC_BLE = 2,
};

enum btn_evt {
	BTN_ZERO_SHORT,
	BTN_ZERO_LONG,
	BTN_ZERO_VLONG,
	BTN_MODE_SHORT,
	BTN_MODE_LONG,
	BTN_MODE_VLONG,
	BTN_BOTH_VLONG,
	BTN_TICK, /* a hold threshold was crossed (audible feedback) */
};

struct app_evt {
	uint8_t type;
	uint8_t src;
	uint8_t btn;
	char line[PROTO_MAX_LINE];
};

/* Non-blocking, ISR-safe. Drops the event if the queue is full. */
void app_post(const struct app_evt *evt);

#endif
