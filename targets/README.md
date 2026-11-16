# Printable targets

| File | Paper |
|---|---|
| [audiotarget-card-letter.pdf](audiotarget-card-letter.pdf) | US Letter, 8.5 x 11 in |
| [audiotarget-card-a4.pdf](audiotarget-card-a4.pdf) | A4 |

Both hold the standard AudioTarget card: 200 mm square, four 40 mm corner
markers (IDs 0 to 3), and a 120 mm bullseye whose centre is the aim point. The
Pi's default settings and the phone app both expect exactly this card.

1. Print at **100%** or **Actual size**, not "Fit to page".
2. Have the 100 mm bar under the card checked with a ruler. If it's off, the
   printer scaled the page, and distance readings will be off by the same
   amount (aiming still works).
3. Cut along the dashed line, keeping the white border around each corner
   square. Glue it to cardboard so it stays flat. Matte paper reflects less glare.

To make other sizes: `python3 pi/tools/make_card.py --help`.

## Rings

The bullseye is 120 mm across: five black and five white bands, each 6 mm.
The phone app (and later the Pi) count them in pairs from the centre:

- bull's eye: within 12 mm of the centre
- first ring: 12 to 24 mm out
- second ring: 24 to 36 mm out
- third ring: 36 to 48 mm out
- fourth ring: 48 to 60 mm out
