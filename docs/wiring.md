# Wiring

## Gun module (Seeed XIAO nRF52840 Sense)

Pins are the labels printed on the XIAO (D0, D1 and so on).

| XIAO pin | Goes to |
|---|---|
| D0 | Left audio filter input (see below) |
| D1 | Right audio filter input |
| D2 | ZERO button, other leg to GND |
| D3 | MODE button, other leg to GND. Also wakes the module from power-off |
| D6 (TX) | Wired link only: Pi GPIO15 / RXD, header pin 10 |
| D7 (RX) | Wired link only: Pi GPIO14 / TXD, header pin 8 |
| GND | Button commons, jack sleeve, Pi ground (header pin 6) for the wired link |
| BAT+ / BAT- pads (underside) | LiPo (602030 size), through the slide switch on the + lead |

The buttons need no resistors: the firmware turns on internal pull-ups.

The motion sensor is on the XIAO itself, so mount the XIAO flat in the box.
Its exact angle doesn't matter after the mount calibration.

### Audio output, one per channel

The XIAO makes the tone as a fast pulse train. This filter smooths it into a
clean sine wave and blocks the DC so earphones don't get a steady current:

1. D0 goes to one end of a 1 kΩ resistor.
2. The resistor's other end is the filter junction.
3. A 22 nF capacitor goes from the junction to GND.
4. The 220 µF capacitor's + leg goes to the junction, and its − leg goes to the
   jack TIP (left channel).
5. The jack SLEEVE goes to GND.

Build an identical second copy from D1 to the jack RING (right channel).

- The 1 kΩ resistor also sets the loudness. 470 Ω is louder; 2.2 kΩ is quieter.
  The module's volume button gives 4 levels on top of that.
- This drives earphones and bone-conduction headsets with a 3.5 mm plug. For a
  speaker, feed the filter output into a small amplifier board (a PAM8302,
  for example) instead.

### Power

If the LiPo comes with a plug, cut it off and solder the wires directly.
Small cells often have their wire colours swapped, so check which lead is +
with a meter (or ask the seller) before soldering it to BAT+.

The XIAO charges the LiPo whenever USB-C is plugged in. With the wired link,
you can also run a fourth wire from the Pi's 5 V (header pin 2) to the XIAO's
5V pin, so the Pi's power bank keeps the gun module charged.

## Pi

### Wired link (optional)

| Pi header pin | Signal | Goes to |
|---|---|---|
| 8 | GPIO14, TXD | XIAO D7 |
| 10 | GPIO15, RXD | XIAO D6 |
| 6 | GND | XIAO GND |

Both sides use 3.3 V logic, so connect them directly. The SD-card image turns
on the UART and removes the serial login console from it.

### Belt-case buttons

Each button connects a GPIO pin to ground; the image turns on the pull-ups.

| Button | Pi header pin | GPIO |
|---|---|---|
| Up (one dimple beside it) | 29 | GPIO5 |
| Down (two dimples) | 31 | GPIO6 |
| Select (big, in the middle) | 33 | GPIO13 |
| Common | 30, 34 or 39 | GND |

They appear to the Pi as the Up, Down and Enter keys, so a USB keypad works
the same way alongside them.

### Camera

- **Pi camera (HQ or Camera Module 3):** ribbon cable to the Pi's camera
  connector. The Zero 2 W and Pi 5 use the narrow 22-pin connector; the Pi 3 and
  4 use the 15-pin one. Adapter cables exist for each combination.
- **USB camera:** any USB port. On a Zero 2 W, use a micro-USB OTG adapter.
  Set `camera.backend = "v4l2"`, or choose a USB camera in the spoken menu
  under Camera, Camera and lens.
