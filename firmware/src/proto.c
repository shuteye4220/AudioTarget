#include "proto.h"

#include <errno.h>
#include <stdio.h>
#include <string.h>

void line_asm_reset(struct line_asm *la)
{
	la->len = 0;
	la->overflow = false;
	la->buf[0] = '\0';
}

bool line_asm_feed(struct line_asm *la, char c)
{
	if (c == '\r') {
		return false;
	}
	if (c == '\n') {
		bool ok = !la->overflow && la->len > 0;

		la->buf[la->len] = '\0';
		la->len = 0;
		la->overflow = false;
		return ok;
	}
	if (la->overflow) {
		return false;
	}
	/* Only printable ASCII is valid on the wire. */
	if (c < 0x20 || c > 0x7e || la->len >= PROTO_MAX_LINE - 1) {
		la->overflow = true;
		la->len = 0;
		return false;
	}
	la->buf[la->len++] = c;
	return false;
}

/* Parse a signed decimal integer token [*p, ...) up to a space or NUL. */
static int parse_i64(const char **p, int64_t min, int64_t max, int64_t *out)
{
	const char *s = *p;
	bool neg = false;
	int64_t v = 0;
	int digits = 0;

	if (*s == '-') {
		neg = true;
		s++;
	}
	while (*s >= '0' && *s <= '9') {
		if (++digits > 10) {
			return -ERANGE;
		}
		v = v * 10 + (*s - '0');
		s++;
	}
	if (digits == 0 || (*s != ' ' && *s != '\0')) {
		return -EINVAL;
	}
	if (neg) {
		v = -v;
	}
	if (v < min || v > max) {
		return -ERANGE;
	}
	*out = v;
	*p = (*s == ' ') ? s + 1 : s;
	return 0;
}

#define PARSE(field, min, max)                                                                 \
	do {                                                                                   \
		int64_t _v;                                                                    \
		int _e = parse_i64(&p, (min), (max), &_v);                                     \
		if (_e) {                                                                      \
			return _e;                                                             \
		}                                                                              \
		(field) = _v;                                                                  \
	} while (0)

int proto_parse(const char *line, struct proto_msg *out)
{
	const char *p;

	if (line == NULL || out == NULL || line[0] == '\0' || line[1] != ' ') {
		return -EINVAL;
	}
	memset(out, 0, sizeof(*out));
	p = line + 2;

	switch (line[0]) {
	case 'H':
		PARSE(out->version, 0, 1000);
		/* The role word is informational; require it to be short and sane. */
		if (strlen(p) == 0 || strlen(p) > 8) {
			return -EINVAL;
		}
		out->type = PROTO_HELLO;
		return 0;
	case 'C':
		PARSE(out->seq, 0, UINT32_MAX);
		PARSE(out->az_mdeg, -PROTO_MAX_ANGLE_MDEG, PROTO_MAX_ANGLE_MDEG);
		PARSE(out->el_mdeg, -PROTO_MAX_ANGLE_MDEG, PROTO_MAX_ANGLE_MDEG);
		PARSE(out->range_cm, 0, PROTO_MAX_RANGE_CM);
		PARSE(out->age_ms, 0, PROTO_MAX_AGE_MS);
		break;
	case 'N':
		PARSE(out->seq, 0, UINT32_MAX);
		break;
	default:
		return -ENOTSUP;
	}
	if (*p != '\0') {
		return -EINVAL; /* trailing garbage */
	}
	out->type = (line[0] == 'C') ? PROTO_CAM : PROTO_NOTARGET;
	return 0;
}

static int fmt_result(int n, size_t len)
{
	return (n < 0 || (size_t)n >= len) ? -ENOSPC : n;
}

int proto_fmt_hello(char *buf, size_t len)
{
	return fmt_result(snprintf(buf, len, "H %d nrf\n", PROTO_VERSION), len);
}

int proto_fmt_route(char *buf, size_t len, unsigned int route)
{
	return fmt_result(snprintf(buf, len, "A %u\n", route), len);
}

int proto_fmt_tone(char *buf, size_t len, uint32_t freq_dhz, unsigned int gain_l_pct,
		   unsigned int gain_r_pct, unsigned int flags)
{
	return fmt_result(snprintf(buf, len, "T %lu %u %u %u\n", (unsigned long)freq_dhz,
				   gain_l_pct, gain_r_pct, flags),
			  len);
}

int proto_fmt_zero(char *buf, size_t len, bool cam)
{
	return fmt_result(snprintf(buf, len, "Z %d\n", cam ? 1 : 0), len);
}
