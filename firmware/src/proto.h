/*
 * AudioTarget line protocol (shared by the wired UART and the BLE NUS link).
 * See docs/protocol.md. Pure C, no Zephyr dependencies, so it can be unit
 * tested on the host.
 */
#ifndef AUDIOTARGET_PROTO_H_
#define AUDIOTARGET_PROTO_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PROTO_VERSION 1
#define PROTO_MAX_LINE 64 /* including the terminating NUL */

/* Bounds applied to every incoming value. Anything outside is rejected. */
#define PROTO_MAX_ANGLE_MDEG 45000  /* +/- 45 degrees */
#define PROTO_MAX_RANGE_CM 100000   /* 1 km */
#define PROTO_MAX_AGE_MS 2000

enum proto_type {
	PROTO_NONE = 0,
	PROTO_HELLO,    /* H <version> <role> */
	PROTO_CAM,      /* C <seq> <az_mdeg> <el_mdeg> <range_cm> <age_ms> */
	PROTO_NOTARGET, /* N <seq> */
};

struct proto_msg {
	enum proto_type type;
	uint32_t seq;
	int32_t az_mdeg;  /* target angle right of the camera axis */
	int32_t el_mdeg;  /* target angle above the camera axis */
	uint32_t range_cm;
	uint32_t age_ms;  /* time from exposure to send */
	uint32_t version;
};

/* Tone flags carried in T messages and used by the audio engine. */
#define TONE_FLAG_CANT 0x01 /* fast flutter: gun tipped sideways */
#define TONE_FLAG_LOST 0x02 /* slow beeping: camera can't see the card */

/* Incremental line assembly from an untrusted byte stream. */
struct line_asm {
	char buf[PROTO_MAX_LINE];
	size_t len;
	bool overflow;
};

void line_asm_reset(struct line_asm *la);
/* Feed one byte. Returns true when buf holds a complete NUL-terminated line. */
bool line_asm_feed(struct line_asm *la, char c);

/* Parse one line (without trailing newline). Returns 0 or a negative errno. */
int proto_parse(const char *line, struct proto_msg *out);

/* Formatters return the number of bytes written (excluding NUL) or <0. */
int proto_fmt_hello(char *buf, size_t len);
int proto_fmt_route(char *buf, size_t len, unsigned int route);
int proto_fmt_tone(char *buf, size_t len, uint32_t freq_dhz, unsigned int gain_l_pct,
		   unsigned int gain_r_pct, unsigned int flags);
int proto_fmt_zero(char *buf, size_t len, bool cam);

#endif
