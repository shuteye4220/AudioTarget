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
| `android/` | Phone prototype of the camera + ML tracking, with the same guidance tones |
| `targets/` | Printable target card PDFs (Letter and A4) |
| `docs/` | Layouts and parts, wiring, buttons and sounds, protocol, range, Pi image, ML |

## Layouts and parts

The camera always rides on the gun. The Pi can go on your belt (layout 1, any
Pi from Zero 2 W to Pi 5) or on the gun next to the camera (layout 2, Pi Zero
2 W, just a power cable to the belt). Full specs, parts lists, cabling and
power for both are in **docs/layouts.md**.

In short:

- **Gun module (both layouts):** Seeed XIAO nRF52840 Sense, small LiPo, two
  tactile buttons, 3.5 mm jack, a few resistors and capacitors.
- **Layout 1:** a Pi HQ camera or USB camera on a rail mount, and any Pi in a
  belt case with three menu buttons and a power bank.
- **Layout 2:** a Pi Zero 2 W and an M12-lens camera in one rail box, and a
  power bank on the belt.
- **Either way:** Bluetooth headset or USB sound card for the Pi's speech, and
  printed target cards.

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
6. **Optional, other targets:** for plain bullseyes and steel plates without a
   printed card, add the ML fallback (`docs/ml.md`, best on a Pi 5).

## Building

**Firmware** (Zephyr 4.5, with the Zephyr SDK installed):

```
pip install west
mkdir at-workspace && cd at-workspace
git clone https://github.com/shuteye4220/AudioTarget
west init -l AudioTarget && west update      # fetches Zephyr next to the repo
pip install -r zephyr/scripts/requirements.txt
west build -b xiao_ble/nrf52840/sense AudioTarget/firmware                  # wire + Bluetooth
west build -b xiao_ble/nrf52840/sense AudioTarget/firmware -- -DAT_BLE=OFF  # wire only
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
