/*
 * Stereo sine synthesis on two GPIOs using the nRF52 PWM peripheral with
 * EasyDMA double buffering. Filter each pin with an RC low-pass and a DC
 * blocking capacitor before the headphone jack (see docs/wiring.md).
 */
#ifndef AUDIOTARGET_AUDIO_H_
#define AUDIOTARGET_AUDIO_H_

#include <stdbool.h>
#include <stdint.h>

int audio_init(void);

/* Set the tone. Gains 0..1 already include volume. Safe from thread context. */
void audio_set(float freq_hz, float gain_l, float gain_r, uint8_t flags);

/* Call periodically from a thread: stops the peripheral after a period of
 * silence so the high-frequency clock can turn off. */
void audio_poll(void);

/* Stop immediately (before power-off). */
void audio_shutdown(void);

#endif
