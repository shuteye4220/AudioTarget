# The two layouts

The camera always rides on the gun, because it has to point where the barrel
points. The question is where the Pi goes. Images never travel over Bluetooth:
the Pi turns each frame into a 30-byte "the target is here" line, and only
that goes to the gun module.

| | Layout 1: Pi on the belt | Layout 2: everything on the gun |
|---|---|---|
| On the rail | Gun module box + camera mount | Gun module box + Pi/camera box |
| On the belt | Pi in belt case + power bank | Power bank only |
| Gun to belt | Camera cable (USB or ribbon), plus a link cable if not using Bluetooth | One USB power cable |
| Which Pi | Any: Zero 2 W, 3, 4, 5, 500 | Zero 2 W |
| Best range | Pi 5 + HQ camera with a 25 mm lens | Zero 2 W + M12 camera with a 12 to 16 mm lens |
| Rail space | About 80 mm (40 mm + 36 mm clamps) | About 90 mm (50 mm + 40 mm clamps) |
| Menu buttons | On the belt case | On the Pi/camera box lid |
| Good for | Range, speed, trying the ML detector on a Pi 5 | Fewest cables, quick to pick up and go |

Both layouts use the same firmware, SD-card image and settings. The gun
module also works alone, with no Pi or camera, for tilt-only guidance.

---

## Shared: the gun module

| Qty | Part | Notes |
|---|---|---|
| 1 | Seeed Studio XIAO nRF52840 **Sense** or **Sense Plus** | Must be a Sense: it has the motion sensor. The Sense Plus adds 9 extra solder pads, ships without pin headers, and runs the same firmware file |
| 1 | LiPo cell, 3.7 V, about 300 mAh, 30 x 20 x 6 mm (602030 size) or smaller, with protection circuit | Solders to the XIAO's battery pads; charges over USB-C. The battery bay is 30 mm long, so 35 mm cells (502035) don't fit |
| 1 | Mini slide switch (SS12D00 style) | In the battery + lead |
| 2 | 12 x 12 mm tactile switches | One with a **round** cap (ZERO), one with a **square** cap (MODE) |
| 1 | 3.5 mm stereo panel jack, 6 mm thread (PJ-392 style) | Headphone output |
| 2 | 1 kΩ resistors | Audio filter (docs/wiring.md) |
| 2 | 22 nF capacitors, film or C0G | Audio filter |
| 2 | 220 µF electrolytic capacitors, 6.3 V or more | DC blocking |
| 1 | M4 x 35 bolt + nut | Rail clamp |
| 4 | M2.5 x 8 self-tapping screws | Lid |
| | Small perfboard, thin wire | |
| | Printed: `nrf_box_tray.stl`, `nrf_box_lid.stl` | |

Battery life: the gun module draws a few milliamps when tracking. Expect
roughly most of a day of use from 300 mAh, and much longer on standby. These are
estimates, not measurements yet.

---

## Layout 1: Pi on the belt

### Gun side

| Qty | Part | Notes |
|---|---|---|
| 1 | Camera, one of: | |
| | a) Raspberry Pi HQ Camera + 16 mm or 25 mm C-mount lens (with C-CS adapter ring) | Longest range |
| | b) USB (UVC) camera module with a narrow M12 lens (12 mm or longer) | Simplest cable to the belt |
| 4 | M2.5 x 12 screws, nuts, 6 mm spacers | Camera to mount |
| 1 | M4 x 35 bolt + nut | Rail clamp |
| | Printed: `camera_mount_hq.stl` | Change `board` and `holes` in `camera_mount.scad` for a USB module |

### Belt side

| Qty | Part | Notes |
|---|---|---|
| 1 | Raspberry Pi Zero 2 W, 3, 4, 5 or 500 | A Pi 5 tracks further and faster, and can run the ML detector |
| 1 | microSD card, 16 GB or more | |
| 1 | USB power bank | Pi 5: 5 V 3 A or better (a 27 W USB-C PD bank is ideal) |
| 1 | Audio: Bluetooth headset/speaker **or** USB sound card | Zero 2 W and Pi 5 have no headphone jack |
| 3 | 12 x 12 mm tactile switches + caps | Menu: Up, Select, Down |
| 4 | M3 x 12 bolts + nuts | Belt loop |
| 4 | M2.5 x 6 screws; 4 M2.5 x 8 self-tapping | Board; lid |
| | Printed: `pi_case_zero2w_*.stl` or `pi_case_pi5_*.stl` (tray, lid, loop) | |

### Cables from gun to belt

| Camera | Cable | Notes |
|---|---|---|
| USB camera | USB cable, 1 to 2 m; micro-USB OTG adapter on a Zero 2 W | Most robust. Run it along the sling |
| Pi HQ camera | Long camera ribbon, up to about 1 m; 22-pin for Zero 2 W / Pi 5, 15-pin for Pi 3 / 4 | Ribbons are fragile; protect with a sleeve or a cable-extension kit |

The gun module link can be Bluetooth (no cable) or a 3-core cable: TX, RX,
ground, plus optionally 5 V so the Pi's power bank keeps the gun module
charged.

### Power

- Pi Zero 2 W, tracking: roughly 2 to 3 W. A 10,000 mAh bank lasts most of a day.
- Pi 5, tracking: roughly 5 to 8 W, more with the ML detector. Use a 20,000 mAh
  bank for a full day.

---

## Layout 2: everything on the gun

### Gun side

| Qty | Part | Notes |
|---|---|---|
| 1 | Raspberry Pi Zero 2 W | Fits in the rail box; header soldered, or wires soldered straight on |
| 1 | Camera, one of: | |
| | a) Camera Module 2-size board with an M12 lens mount (for example Arducam IMX219 M12), with a **12 to 16 mm** M12 lens | Default. Narrow view (about 13 to 17 degrees), small box |
| | b) Raspberry Pi HQ Camera + 16 mm C-mount lens | Longer range, much taller box (set `cam = "hq"`) |
| 1 | Pi Zero camera ribbon, 15 cm (22-pin to 15-pin) | Folds inside the box |
| 1 | microSD card, 16 GB or more | |
| 3 | 12 x 12 mm tactile switches + caps | Menu buttons on the box lid |
| 4 | M2 x 10 screws + nuts (M12 board) or M2.5 x 10 (HQ) | Camera to front wall |
| 4 | M2.5 x 6 screws | Pi to standoffs |
| 4 | M2.5 x 8 self-tapping screws | Lid |
| 1 | M4 x 35 bolt + nut | Rail clamp |
| | 15 cm of 4-core wire | Pi to gun module box, through both glands |
| | Printed: `gun_pi_box_m12_tray.stl` + `_lid.stl` (or the `hq` pair) | |

### Belt side

| Qty | Part | Notes |
|---|---|---|
| 1 | USB power bank, 10,000 mAh or more | |
| 1 | Micro-USB cable, 1 to 1.5 m, ideally right-angle at the Pi end | Into the Zero's PWR port through the box's left side |
| 1 | Audio: Bluetooth headset or speaker | The Zero's only USB data port is free for a USB sound card or keypad if you prefer |

### Wiring between the two boxes

| Pi Zero header pin | Goes to |
|---|---|
| 8 (GPIO14, TXD) | XIAO D7 |
| 10 (GPIO15, RXD) | XIAO D6 |
| 6 (GND) | XIAO GND |
| 2 (5 V) | XIAO 5V pin (optional: charges the gun module's LiPo from the power bank) |

If you use the 5 V wire, unplug it before connecting the XIAO's USB-C to a
computer, so the Pi's supply can't push back into the computer's USB port.

The menu buttons go to GPIO5 (pin 29, Up), GPIO13 (pin 33, Select) and GPIO6
(pin 31, Down), each to a ground pin, as in docs/wiring.md.

### Mounting order on the rail

Pi/camera box in front, gun module box behind it, so the lens has a clear view
past the muzzle end of the rail. On a short rail, the gun module box can go on
a side rail or under-rail instead: its mount calibration works at any angle.

### Settings for layout 2

In the spoken menu:

- Camera, then Camera and lens: "Camera Module 2 size, 12 millimetre M12 lens"
  (or the 16 millimetre one).
- Gun module, then Connection type: "Wire only", since the boxes are wired
  together.

For any other lens, set `hfov_deg` (its horizontal field of view in degrees)
under `[camera]` in `/var/lib/audiotarget/audiotarget.toml`.
