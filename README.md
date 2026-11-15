# AudioTarget

An audio aiming aid for target shooting (built for airsoft) that you use by
ear. A small module on the gun's rail plays a tone: the pitch tells you whether
you're aiming high or low, and which ear is louder tells you left or right.
Hold the zero button once while you're on target, and from then on the tone
brings you back to that spot.

It works at two levels:

- **Tilt only (gun module on its own):** a motion sensor tracks barrel angle,
  so you get high/low and a warning when the gun is tipped sideways. No camera
  or Pi needed.
- **Camera (gun module + Pi):** a camera on the rail sees a printed target card.
  The Pi works out where the card is, and the gun module blends that with its
  motion sensor. You get high/low and left/right relative to the actual target.

The Pi runs from a ready-made SD-card image with a spoken menu, so the whole
thing can be set up and used eyes-free.

The gun module and the camera clip onto the rail. The Pi can ride on your belt,
connected to the gun module by a thin cable or by Bluetooth, with the camera
cabled down to it. Tones play from the gun module's headphone jack, from the
Pi's Bluetooth audio, or both.

## What's in the repo

| Folder | What |
|---|---|
| `firmware/` | Zephyr firmware for the gun module (Seeed XIAO nRF52840 Sense) |
| `pi/` | Python service for the Pi: camera tracking, links, tones, spoken menu |
| `image/` | Builds the flashable Pi SD-card image (also installs onto an existing Pi) |
| `hardware/` | OpenSCAD sources and ready STL files for 3D printing |
| `docs/` | Wiring, buttons and sounds, protocol, range, Pi image guide |

## Parts list

### Gun module

| Qty | Part | Notes |
|---|---|---|
| 1 | Seeed Studio XIAO nRF52840 **Sense** | Must be the Sense version: it has the motion sensor |
| 1 | LiPo cell, 3.7 V, 300 to 500 mAh, about 35 x 20 x 5 mm (502035 size) | Solders to the XIAO's battery pads, which charge it over USB-C |
| 1 | Mini slide switch (SS12D00 style) | In the battery's + lead, for storage |
| 2 | 12 x 12 mm tactile switches | One with a **round** cap (ZERO), one with a **square** cap (MODE) |
| 1 | 3.5 mm stereo panel jack, 6 mm thread (PJ-392 style) | Headphone output |
| 2 | 1 kΩ resistors | Audio filter, see docs/wiring.md |
| 2 | 22 nF capacitors (film or C0G) | Audio filter |
| 2 | 220 µF electrolytic capacitors, 6.3 V or more | DC blocking for earphones |
| 1 | M4 x 35 bolt and M4 nut | Rail clamp cross bolt |
| 4 | M2.5 x 8 self-tapping screws | Lid |
| | Small perfboard, thin wire | |
| | Wired link only: 3-core cable (TX, RX, ground), 1 to 1.5 m | Not needed for Bluetooth |

### Camera (optional, needed for left/right)

| Qty | Part | Notes |
|---|---|---|
| 1 | Camera, one of: | Narrow lenses see further (docs/range.md) |
| | a) Raspberry Pi HQ Camera + 16 mm or 25 mm C-mount lens | Best range. Needs a ribbon cable to the Pi |
| | b) USB (UVC) camera module with a narrow M12 lens | Easiest with the Pi on your belt: just a USB cable |
| 4 | M2.5 x 12 screws, nuts, 6 mm spacers | Camera to mount |
| 1 | M4 x 35 bolt and M4 nut | Rail clamp |
| | Long camera ribbon (Pi camera) or USB cable + adapter (USB camera) | Gun to belt |

### Pi (optional, needed for the camera)

| Qty | Part | Notes |
|---|---|---|
| 1 | Raspberry Pi Zero 2 W, 3, 4, 5 or 500 | Same SD-card image for all. A Pi 5 tracks further and faster |
| 1 | microSD card, 16 GB or more | |
| 1 | USB power bank | Pi 5 wants a 5 V 3 A (or better) supply |
| 1 | Audio out: Bluetooth headset or speaker, **or** a USB sound card | The Zero 2 W and Pi 5 have no headphone jack |
| 3 | 12 x 12 mm tactile switches + caps | Belt-case menu buttons: Up, Select, Down |
| | Optional: any USB numeric keypad or keyboard | Works with the menu as well as, or instead of, the buttons |
| 4 | M3 x 12 bolts + nuts | Belt loop to case |
| 4 | M2.5 x 6 screws | Pi to case standoffs |
| 4 | M2.5 x 8 self-tapping screws | Case lid |
| | Printed target cards (`pi/tools/make_card.py`) | |

## Getting started

1. **Print the parts:** see `hardware/README.md`.
2. **Wire the gun module:** see `docs/wiring.md`.
3. **Flash the firmware:** download `audiotarget-xiao-sense.uf2` from the
   Releases page (or build it, below). Double-press the XIAO's reset button. A
   USB drive called XIAO-SENSE appears; copy the `.uf2` file onto it. The
   board reboots and plays a rising three-note chime.
4. **Learn the buttons:** see `docs/buttons-and-sounds.md`. Do the two-pose
   mount calibration once, with the box on the gun.
5. **Optional, Pi and camera:** flash the SD-card image (`docs/pi-image.md`),
   print a target card, and pair the gun module from the spoken menu.

## Building

**Firmware** (Zephyr 4.5, with the Zephyr SDK installed):

```
pip install west
west init -l firmware && west update
pip install -r zephyr/scripts/requirements.txt
west build -b xiao_ble/nrf52840/sense firmware                 # wire + Bluetooth
west build -b xiao_ble/nrf52840/sense firmware -- -DAT_BLE=OFF # wire only, smaller
```

The result is `build/zephyr/zephyr.uf2`. Unit tests for the maths and protocol
code run on any PC: `make -C firmware/tests/host run`.

**Pi service:** `cd pi && pip install -e .[dev] && pytest`. Try it with a
camera and no gun module: `python -m audiotarget -c config.toml --dry-run`
prints where the target is twice a second.

**SD-card image:** push a tag such as `v0.1.0`. The Release workflow builds the
image and both firmware variants and attaches them to a GitHub release. To set
up a Pi you already have, run `sudo ./image/install.sh` from a checkout.

## License

MIT, see `LICENSE`.
