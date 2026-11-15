#ifndef AUDIOTARGET_IMU_H_
#define AUDIOTARGET_IMU_H_

int imu_init(void);
/* Raw sensor-frame readings: m/s^2 and rad/s. */
int imu_read(float acc[3], float gyro[3]);
/* Put the sensor in power-down (before system off). */
void imu_suspend(void);

#endif
