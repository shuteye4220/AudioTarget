#include "mount.h"

#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

static void cross(const float a[3], const float b[3], float out[3])
{
	out[0] = a[1] * b[2] - a[2] * b[1];
	out[1] = a[2] * b[0] - a[0] * b[2];
	out[2] = a[0] * b[1] - a[1] * b[0];
}

static float dot(const float a[3], const float b[3])
{
	return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static int normalize(float v[3])
{
	float n = sqrtf(dot(v, v));

	if (!(n > 1e-6f) || !isfinite(n)) {
		return -EINVAL;
	}
	for (int i = 0; i < 3; i++) {
		v[i] /= n;
	}
	return 0;
}

int mount_from_axes(struct mount *mt, int fwd_axis, int up_axis)
{
	float fwd[3] = {0}, up[3] = {0};

	if (fwd_axis == 0 || up_axis == 0 || abs(fwd_axis) > 3 || abs(up_axis) > 3 ||
	    abs(fwd_axis) == abs(up_axis)) {
		return -EINVAL;
	}
	fwd[abs(fwd_axis) - 1] = fwd_axis > 0 ? 1.0f : -1.0f;
	up[abs(up_axis) - 1] = up_axis > 0 ? 1.0f : -1.0f;
	memcpy(mt->m[0], fwd, sizeof(fwd));
	cross(up, fwd, mt->m[1]); /* left = up x forward */
	memcpy(mt->m[2], up, sizeof(up));
	return 0;
}

int mount_from_poses(struct mount *mt, const float level[3], const float raised[3])
{
	float up[3], r[3], fwd[3], left[3];

	memcpy(up, level, sizeof(up));
	memcpy(r, raised, sizeof(r));
	if (normalize(up) || normalize(r)) {
		return -EINVAL;
	}
	/*
	 * When the muzzle is raised, gravity's reaction tips toward the muzzle.
	 * The part of the raised reading orthogonal to "up" points forward.
	 * Require at least ~25 degrees of raise for a usable direction.
	 */
	float d = dot(r, up);

	for (int i = 0; i < 3; i++) {
		fwd[i] = r[i] - d * up[i];
	}
	if (sqrtf(dot(fwd, fwd)) < 0.42f || normalize(fwd)) {
		return -EINVAL;
	}
	cross(up, fwd, left);
	memcpy(mt->m[0], fwd, sizeof(fwd));
	memcpy(mt->m[1], left, sizeof(left));
	memcpy(mt->m[2], up, sizeof(up));
	return 0;
}

void mount_apply(const struct mount *mt, const float in[3], float out[3])
{
	for (int i = 0; i < 3; i++) {
		out[i] = dot(mt->m[i], in);
	}
}

bool mount_valid(const struct mount *mt)
{
	/* Orthonormal within tolerance. */
	for (int i = 0; i < 3; i++) {
		for (int j = 0; j < 3; j++) {
			float d = dot(mt->m[i], mt->m[j]);

			if (!isfinite(d) || fabsf(d - (i == j ? 1.0f : 0.0f)) > 0.01f) {
				return false;
			}
		}
	}
	return true;
}
