#ifndef AUDIOTARGET_BUTTONS_H_
#define AUDIOTARGET_BUTTONS_H_

#include <stdbool.h>

int buttons_init(void);
bool buttons_any_pressed(void);
/* Configure the mode button as the System OFF wake source. */
int buttons_arm_wakeup(void);

#endif
