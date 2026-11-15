# Printed parts

Ready-to-print STL files are in `stl/`. The `.scad` files are the OpenSCAD
sources: change the settings at the top of each and export again.

| File | What | Print orientation |
|---|---|---|
| `nrf_box_tray.stl` | Gun module box with Picatinny clamp | As exported: clamp down, open top up |
| `nrf_box_lid.stl` | Gun module lid with round (ZERO) and square (MODE) button holes | As exported: top face down |
| `camera_mount_hq.stl` | Camera plate on a Picatinny clamp, for the Pi HQ camera | As exported: clamp down |
| `pi_case_zero2w_*.stl` | Belt case for a Pi Zero 2 W: tray, lid (3 buttons), belt loop | As exported |
| `pi_case_pi5_*.stl` | The same for a Pi 5 (also fits a Pi 3 or 4) | As exported |

## Settings

- **Material:** PETG or ASA. PLA softens in a hot car or in summer sun.
- **Layers and walls:** 0.2 mm layers, 4 walls, 30% infill. The rail clamps want
  solid-ish jaws, so use 5 walls on the trays and camera mount if your slicer
  lets you set it per object.
- **Supports:** none needed. The rail channel is a short bridge across the top
  of the rail, and the jaw undercuts are 45 degrees.

## Fit

- `clear` in `lib.scad` (default 0.25 mm) sets every fit gap. If the clamp won't
  slide onto the rail, raise it to 0.3 or 0.4 and export again.
- The clamps slide on from the end of the rail. The M4 cross bolt passes through
  one of the rail's cross slots and squeezes the jaws, so the module can't slide
  or rock. The nut sits in a hexagonal pocket on one side.
- The engraved arrow on the gun module lid points at the muzzle.

## Buttons by touch

- Gun module: **round** cap = ZERO (toward the muzzle), **square** cap = MODE
  (toward you), with an engraved groove between them.
- Pi case: three round buttons in a line. The big middle one is Select. The
  one with **one** dimple beside it is Up, the one with **two** is Down.
