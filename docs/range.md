# How far away can the camera see the card?

The table shows the furthest distance at which the camera found the card
centre to within 1.5 pixels, every time, in simulated frames with sensor
noise and the card turned 10 degrees. Real lighting and focus will cut these
somewhat, so treat them as upper limits.

"Markers" is the corner-marker detection (precise, gives distance).
"Rings" is the bullseye fallback the `card` detector uses when the markers are
too small or covered.

| Card | Camera and lens | Markers | Rings |
|---|---|---|---|
| 200 mm, 40 mm markers (fits Letter/A4) | Zero 2 W, 1280 x 720, 22° (HQ + 16 mm) | 10 m | 5 m |
| 200 mm, 40 mm markers | Zero 2 W, 1280 x 720, 14° (HQ + 25 mm) | 15 m | 10 m |
| 200 mm, 40 mm markers | Pi 5, 1920 x 1080, 14° (HQ + 25 mm) | 18 m | 15 m |
| 200 mm, 40 mm markers | USB camera, 1280 x 720, 30° | 8 m | 3 m |
| 280 mm, 60 mm markers (Tabloid/A3) | Zero 2 W, 1280 x 720, 22° | 15 m | 8 m |
| 280 mm, 60 mm markers | Zero 2 W, 1280 x 720, 14° | 25 m | 12 m |
| 280 mm, 60 mm markers | Pi 5, 1920 x 1080, 14° | 25 m | 20 m |
| 280 mm, 60 mm markers | USB camera, 1280 x 720, 30° | 12 m | 5 m |

Rules of thumb:

- A **narrower lens** (longer focal length) adds range fastest.
- **Bigger markers** come next: print with `--size 280 --marker 60 --page tabloid`.
  Put the same sizes in the config, or the distance readings will be wrong.
- A narrow lens also narrows what the camera sees. With a 14° lens at 10 m,
  the frame is about 2.5 m wide, so you have to be roughly on target before the
  camera can help. Tilt guidance still works outside that.

To make your own card: `python3 pi/tools/make_card.py -o card.svg`, then print
at 100% ("actual size") on matte paper, and have the 100 mm scale bar checked
with a ruler.
