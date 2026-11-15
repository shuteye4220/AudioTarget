/*
 * Pi <-> nRF transport. Two links carry the same line protocol:
 *   - wired UART (CONFIG_AT_LINK_UART)
 *   - Bluetooth LE, Nordic UART Service (CONFIG_AT_LINK_BLE)
 * Incoming lines are posted as EVT_LINE; outgoing lines go to every link
 * that is up.
 */
#ifndef AUDIOTARGET_LINK_H_
#define AUDIOTARGET_LINK_H_

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

int link_init(void);
/* Start advertising; call after settings_load() so bonds are known. */
void link_start(void);
void link_send(const char *data, size_t len);
bool link_ble_ready(void);
/* Allow a new device to pair for the given time. */
void link_pairing_open(uint32_t seconds);
bool link_pairing_is_open(void);
/* Number of bonded peers (0 if BLE disabled). */
int link_bond_count(void);
void link_suspend(void);

#endif
