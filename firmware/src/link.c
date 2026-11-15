#include "link.h"
#include "events.h"
#include "proto.h"

#include <string.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/ring_buffer.h>

LOG_MODULE_REGISTER(link, LOG_LEVEL_INF);

/* ------------------------------------------------------------------ UART */
#if defined(CONFIG_AT_LINK_UART)
#include <zephyr/drivers/uart.h>

#define USER_NODE DT_PATH(zephyr_user)
static const struct device *const uart = DEVICE_DT_GET(DT_PHANDLE(USER_NODE, link_uart));

RING_BUF_DECLARE(uart_tx_rb, 256);
static struct k_spinlock uart_tx_lock;
static struct line_asm uart_rx_asm;

static void uart_isr(const struct device *dev, void *user_data)
{
	ARG_UNUSED(user_data);

	uart_irq_update(dev);
	while (uart_irq_is_pending(dev) > 0) {
		if (uart_irq_rx_ready(dev) > 0) {
			uint8_t buf[32];
			int n = uart_fifo_read(dev, buf, sizeof(buf));

			for (int i = 0; i < n; i++) {
				if (line_asm_feed(&uart_rx_asm, (char)buf[i])) {
					struct app_evt evt = {.type = EVT_LINE, .src = SRC_UART};

					memcpy(evt.line, uart_rx_asm.buf, sizeof(evt.line));
					app_post(&evt);
				}
			}
		}
		if (uart_irq_tx_ready(dev) > 0) {
			k_spinlock_key_t key = k_spin_lock(&uart_tx_lock);
			uint8_t *data;
			uint32_t n = ring_buf_get_ptr(&uart_tx_rb, &data, 0);

			if (n == 0) {
				uart_irq_tx_disable(dev);
			} else {
				int w = uart_fifo_fill(dev, data, MIN(n, 32U));

				ring_buf_consume(&uart_tx_rb, w > 0 ? (size_t)w : 0);
			}
			k_spin_unlock(&uart_tx_lock, key);
		}
		uart_irq_update(dev);
	}
}

static int uart_link_init(void)
{
	if (!device_is_ready(uart)) {
		LOG_ERR("link UART not ready");
		return -ENODEV;
	}
	line_asm_reset(&uart_rx_asm);
	uart_irq_callback_user_data_set(uart, uart_isr, NULL);
	uart_irq_rx_enable(uart);
	return 0;
}

static void uart_link_send(const char *data, size_t len)
{
	k_spinlock_key_t key = k_spin_lock(&uart_tx_lock);

	/* All-or-nothing so a full buffer never produces half a line. */
	if (ring_buf_space_get(&uart_tx_rb) >= len) {
		ring_buf_put(&uart_tx_rb, (const uint8_t *)data, len);
	}
	k_spin_unlock(&uart_tx_lock, key);
	uart_irq_tx_enable(uart);
}
#endif /* CONFIG_AT_LINK_UART */

/* ------------------------------------------------------------------- BLE */
#if defined(CONFIG_AT_LINK_BLE)
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/services/nus.h>

/* cur_conn is written from the BT thread and read from the control thread. */
static struct bt_conn *cur_conn;
static struct k_spinlock conn_lock;
static atomic_t ble_secure;
static atomic_t ble_notify;
static struct line_asm ble_rx_asm;
static atomic_t pairing_until; /* k_uptime_get_32() deadline, 0 = closed */
static struct k_work adv_work;

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_NUS_SRV_VAL),
};

static const struct bt_data sd[] = {
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

bool link_pairing_is_open(void)
{
	uint32_t until = (uint32_t)atomic_get(&pairing_until);

	return until != 0 && (int32_t)(until - k_uptime_get_32()) > 0;
}

void link_pairing_open(uint32_t seconds)
{
	uint32_t until = k_uptime_get_32() + seconds * 1000U;

	atomic_set(&pairing_until, (atomic_val_t)(until ? until : 1));
	LOG_INF("pairing window open for %u s", seconds);
}

static void count_bond(const struct bt_bond_info *info, void *user_data)
{
	ARG_UNUSED(info);
	(*(int *)user_data)++;
}

int link_bond_count(void)
{
	int n = 0;

	bt_foreach_bond(BT_ID_DEFAULT, count_bond, &n);
	return n;
}

static void post_simple(enum app_evt_type t)
{
	struct app_evt evt = {.type = t, .src = SRC_BLE};

	app_post(&evt);
}

static void adv_fn(struct k_work *work)
{
	/* ~1 s interval: cheap on battery, reconnects within a couple of seconds. */
	static const struct bt_le_adv_param param = BT_LE_ADV_PARAM_INIT(
		BT_LE_ADV_OPT_CONN, BT_GAP_ADV_SLOW_INT_MIN, BT_GAP_ADV_SLOW_INT_MAX, NULL);
	int err;

	ARG_UNUSED(work);
	err = bt_le_adv_start(&param, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));
	if (err && err != -EALREADY) {
		LOG_ERR("advertising failed: %d", err);
	}
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		k_work_submit(&adv_work);
		return;
	}
	if (cur_conn != NULL) {
		bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
		return; /* one peer at a time */
	}
	/* Only bonded devices may connect, except during the pairing window. */
	if (!link_pairing_is_open() && !bt_le_bond_exists(BT_ID_DEFAULT, bt_conn_get_dst(conn))) {
		LOG_WRN("rejecting unbonded device");
		bt_conn_disconnect(conn, BT_HCI_ERR_AUTH_FAIL);
		post_simple(EVT_BLE_REJECTED);
		return;
	}
	k_spinlock_key_t key = k_spin_lock(&conn_lock);

	cur_conn = bt_conn_ref(conn);
	k_spin_unlock(&conn_lock, key);
	atomic_set(&ble_secure, 0);
	atomic_set(&ble_notify, 0);
	line_asm_reset(&ble_rx_asm);
	if (bt_conn_set_security(conn, BT_SECURITY_L2)) {
		bt_conn_disconnect(conn, BT_HCI_ERR_AUTH_FAIL);
	}
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(reason);
	if (conn != cur_conn) {
		return;
	}
	k_spinlock_key_t key = k_spin_lock(&conn_lock);
	struct bt_conn *old = cur_conn;

	cur_conn = NULL;
	k_spin_unlock(&conn_lock, key);
	bt_conn_unref(old);
	atomic_set(&ble_secure, 0);
	atomic_set(&ble_notify, 0);
	post_simple(EVT_BLE_DISCONNECTED);
}

static void recycled(void)
{
	k_work_submit(&adv_work);
}

static void security_changed(struct bt_conn *conn, bt_security_t level, enum bt_security_err err)
{
	if (conn != cur_conn) {
		return;
	}
	if (err || level < BT_SECURITY_L2) {
		LOG_WRN("security failed: level %d err %d", level, err);
		bt_conn_disconnect(conn, BT_HCI_ERR_AUTH_FAIL);
		return;
	}
	atomic_set(&ble_secure, 1);
	/* Short connection interval keeps camera latency low. */
	(void)bt_conn_le_param_update(conn, BT_LE_CONN_PARAM(6, 12, 0, 400));
	post_simple(EVT_BLE_SECURED);
}

BT_CONN_CB_DEFINE(conn_cbs) = {
	.connected = connected,
	.disconnected = disconnected,
	.recycled = recycled,
	.security_changed = security_changed,
};

static enum bt_security_err pairing_accept(struct bt_conn *conn,
					   const struct bt_conn_pairing_feat *const feat)
{
	ARG_UNUSED(conn);
	ARG_UNUSED(feat);
	return link_pairing_is_open() ? BT_SECURITY_ERR_SUCCESS
				      : BT_SECURITY_ERR_PAIR_NOT_ALLOWED;
}

static void auth_cancel(struct bt_conn *conn)
{
	ARG_UNUSED(conn);
}

static struct bt_conn_auth_cb auth_cb = {
	.pairing_accept = pairing_accept,
	.cancel = auth_cancel,
};

static void pairing_complete(struct bt_conn *conn, bool bonded)
{
	ARG_UNUSED(conn);
	if (bonded) {
		atomic_set(&pairing_until, 0); /* one device per window */
		post_simple(EVT_BLE_PAIRED);
	}
}

static void pairing_failed(struct bt_conn *conn, enum bt_security_err reason)
{
	LOG_WRN("pairing failed: %d", reason);
	bt_conn_disconnect(conn, BT_HCI_ERR_AUTH_FAIL);
}

static struct bt_conn_auth_info_cb auth_info_cb = {
	.pairing_complete = pairing_complete,
	.pairing_failed = pairing_failed,
};

static void nus_notif_enabled(bool enabled, void *ctx)
{
	ARG_UNUSED(ctx);
	atomic_set(&ble_notify, enabled ? 1 : 0);
}

static void nus_received(struct bt_conn *conn, const void *data, uint16_t len, void *ctx)
{
	const char *p = data;

	ARG_UNUSED(ctx);
	if (conn != cur_conn || !atomic_get(&ble_secure)) {
		return; /* never act on unencrypted input */
	}
	for (uint16_t i = 0; i < len; i++) {
		if (line_asm_feed(&ble_rx_asm, p[i])) {
			struct app_evt evt = {.type = EVT_LINE, .src = SRC_BLE};

			memcpy(evt.line, ble_rx_asm.buf, sizeof(evt.line));
			app_post(&evt);
		}
	}
}

static struct bt_nus_cb nus_cb = {
	.notif_enabled = nus_notif_enabled,
	.received = nus_received,
};

static int ble_link_init(void)
{
	int err;

	k_work_init(&adv_work, adv_fn);
	err = bt_conn_auth_cb_register(&auth_cb);
	if (err == 0) {
		err = bt_conn_auth_info_cb_register(&auth_info_cb);
	}
	if (err == 0) {
		err = bt_nus_cb_register(&nus_cb, NULL);
	}
	if (err == 0) {
		err = bt_enable(NULL);
	}
	if (err) {
		LOG_ERR("BLE init failed: %d", err);
		return err;
	}
	/* Bonds are loaded by settings_load() in main; advertising starts then. */
	return 0;
}

bool link_ble_ready(void)
{
	return atomic_get(&ble_secure) && atomic_get(&ble_notify);
}

static struct bt_conn *conn_get(void)
{
	k_spinlock_key_t key = k_spin_lock(&conn_lock);
	struct bt_conn *conn = cur_conn ? bt_conn_ref(cur_conn) : NULL;

	k_spin_unlock(&conn_lock, key);
	return conn;
}

static void ble_link_send(const char *data, size_t len)
{
	struct bt_conn *conn;

	if (!link_ble_ready()) {
		return;
	}
	conn = conn_get();
	if (conn != NULL) {
		(void)bt_nus_send(conn, data, len);
		bt_conn_unref(conn);
	}
}

static void ble_link_suspend(void)
{
	struct bt_conn *conn = conn_get();

	(void)bt_le_adv_stop();
	if (conn) {
		bt_conn_disconnect(conn, BT_HCI_ERR_REMOTE_POWER_OFF);
		bt_conn_unref(conn);
	}
}
#else
bool link_ble_ready(void)
{
	return false;
}
void link_pairing_open(uint32_t seconds)
{
	ARG_UNUSED(seconds);
}
bool link_pairing_is_open(void)
{
	return false;
}
int link_bond_count(void)
{
	return 0;
}
#endif /* CONFIG_AT_LINK_BLE */

/* ---------------------------------------------------------------- common */
int link_init(void)
{
	int err = 0;

#if defined(CONFIG_AT_LINK_UART)
	err = uart_link_init();
	if (err) {
		return err;
	}
#endif
#if defined(CONFIG_AT_LINK_BLE)
	err = ble_link_init();
#endif
	return err;
}

void link_send(const char *data, size_t len)
{
#if defined(CONFIG_AT_LINK_UART)
	uart_link_send(data, len);
#endif
#if defined(CONFIG_AT_LINK_BLE)
	ble_link_send(data, len);
#endif
}

void link_start(void)
{
#if defined(CONFIG_AT_LINK_BLE)
	k_work_submit(&adv_work);
#endif
}

void link_suspend(void)
{
#if defined(CONFIG_AT_LINK_BLE)
	ble_link_suspend();
#endif
}
