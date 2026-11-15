#include "imu.h"

#include <errno.h>

#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(imu, LOG_LEVEL_INF);

#if !DT_NODE_EXISTS(DT_ALIAS(imu0))
#error "Board overlay must define an imu0 alias pointing at a 6-axis accel+gyro sensor"
#endif

static const struct device *const imu = DEVICE_DT_GET(DT_ALIAS(imu0));

static int set_odr(int hz)
{
	struct sensor_value odr = {.val1 = hz};
	int err = sensor_attr_set(imu, SENSOR_CHAN_ACCEL_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY, &odr);

	if (err == 0) {
		err = sensor_attr_set(imu, SENSOR_CHAN_GYRO_XYZ, SENSOR_ATTR_SAMPLING_FREQUENCY,
				      &odr);
	}
	return err;
}

int imu_init(void)
{
	int err;

	if (!device_is_ready(imu)) {
		LOG_ERR("IMU not ready");
		return -ENODEV;
	}
	err = set_odr(104);
	if (err) {
		/* Some drivers fix ODR at build time; that's fine. */
		LOG_WRN("IMU ODR not set (%d), using driver default", err);
	}
	return 0;
}

int imu_read(float acc[3], float gyro[3])
{
	struct sensor_value a[3], g[3];
	int err = sensor_sample_fetch(imu);

	if (err == 0) {
		err = sensor_channel_get(imu, SENSOR_CHAN_ACCEL_XYZ, a);
	}
	if (err == 0) {
		err = sensor_channel_get(imu, SENSOR_CHAN_GYRO_XYZ, g);
	}
	if (err) {
		return err;
	}
	for (int i = 0; i < 3; i++) {
		acc[i] = sensor_value_to_float(&a[i]);
		gyro[i] = sensor_value_to_float(&g[i]);
	}
	return 0;
}

void imu_suspend(void)
{
	(void)set_odr(0);
}
