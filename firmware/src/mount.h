/*
 * Sensor-to-gun rotation. Rows of m are the gun's forward, left and up axes
 * expressed in the sensor frame. Pure C for host testing.
 */
#ifndef AUDIOTARGET_MOUNT_H_
#define AUDIOTARGET_MOUNT_H_

#include <stdbool.h>

struct mount {
	float m[3][3];
};

/* axis: 1=+X 2=+Y 3=+Z, negative for the opposite direction. */
int mount_from_axes(struct mount *mt, int fwd_axis, int up_axis);

/*
 * Two-pose calibration from averaged accelerometer readings:
 * level = gun held level and upright; raised = muzzle pointed well up.
 * Returns 0, or -EINVAL if the poses are too similar or readings are bad.
 */
int mount_from_poses(struct mount *mt, const float level[3], const float raised[3]);

void mount_apply(const struct mount *mt, const float in[3], float out[3]);
bool mount_valid(const struct mount *mt);

#endif
