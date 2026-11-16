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
