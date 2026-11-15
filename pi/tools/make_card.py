#!/usr/bin/env python3
"""Generate a printable target card (SVG, true millimetre scale).

Four ArUco markers in the corners for the camera, a bullseye in the middle.
The defaults fit on Letter or A4; print at 100% / "actual size" and check the
100 mm scale bar with a ruler.

    python3 tools/make_card.py -o card.svg
    python3 tools/make_card.py --size 300 --marker 60 --page tabloid -o big.svg
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audiotarget.card import CardLayout, marker_bits  # noqa: E402

PAGES = {"letter": (215.9, 279.4), "a4": (210.0, 297.0), "tabloid": (279.4, 431.8),
         "a3": (297.0, 420.0)}


def svg_marker(marker_id: int, x: float, y: float, size: float) -> str:
    bits = marker_bits(marker_id, 6)  # 4x4 data + 1-cell border each side
    cells = bits.shape[0]
    cell = size / cells
    out = [f'<rect x="{x:.3f}" y="{y:.3f}" width="{size:.3f}" height="{size:.3f}" fill="#fff"/>']
    for r in range(cells):
        for c in range(cells):
            if bits[r, c] < 128:
                out.append(f'<rect x="{x + c * cell:.3f}" y="{y + r * cell:.3f}" '
                           f'width="{cell + 0.01:.3f}" height="{cell + 0.01:.3f}" fill="#000"/>')
    return "\n".join(out)


def build(layout: CardLayout, page: tuple[float, float], bullseye_mm: float) -> str:
    pw, ph = page
    ox, oy = (pw - layout.size_mm) / 2.0, 15.0
    if layout.size_mm > pw - 10 or layout.size_mm + 40 > ph:
        raise SystemExit("card doesn't fit on that page; pick a bigger page or smaller --size")
    cx, cy = layout.centre
    max_r = math.sqrt(2) * (layout.size_mm / 2 - layout.margin_mm - layout.marker_mm) - 2
    r_outer = min(bullseye_mm / 2.0, max_r)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{pw}mm" height="{ph}mm" '
        f'viewBox="0 0 {pw} {ph}">',
        f'<rect width="{pw}" height="{ph}" fill="#fff"/>',
        f'<g transform="translate({ox:.3f},{oy:.3f})">',
        f'<rect x="0" y="0" width="{layout.size_mm}" height="{layout.size_mm}" fill="#fff" '
        f'stroke="#888" stroke-width="0.2" stroke-dasharray="2,2"/>',
    ]
    for i, mid in enumerate(layout.ids()):
        x, y = layout.marker_origin(i)
        parts.append(svg_marker(mid, x, y, layout.marker_mm))
    # Bullseye: alternating rings, black outermost.
    rings = 5
    for k in range(rings * 2):
        r = r_outer * (1 - k / (rings * 2))
        colour = "#000" if k % 2 == 0 else "#fff"
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.3f}" fill="{colour}"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="1.2" fill="#fff"/>')
    parts.append("</g>")

    # Scale check and label below the card.
    by = oy + layout.size_mm + 10
    parts.append(f'<rect x="{ox}" y="{by}" width="100" height="2" fill="#000"/>')
    parts.append(f'<text x="{ox}" y="{by + 7}" font-family="sans-serif" font-size="4">'
                 f'Scale check: this bar must measure 100 mm</text>')
    parts.append(f'<text x="{ox}" y="{by + 13}" font-family="sans-serif" font-size="4">'
                 f'AudioTarget card: {layout.size_mm:g} mm, markers {layout.marker_mm:g} mm, '
                 f'IDs {layout.id_base}-{layout.id_base + 3}, bullseye {2 * r_outer:.0f} mm</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--size", type=float, default=200.0, help="card size, mm (default 200)")
    ap.add_argument("--marker", type=float, default=40.0, help="marker size, mm (default 40)")
    ap.add_argument("--margin", type=float, default=8.0, help="white margin, mm (default 8)")
    ap.add_argument("--id-base", type=int, default=0, help="first marker ID (default 0)")
    ap.add_argument("--bullseye", type=float, default=120.0, help="bullseye diameter, mm")
    ap.add_argument("--page", choices=sorted(PAGES), default="letter")
    a = ap.parse_args()
    if not (0 <= a.id_base <= 46):
        ap.error("--id-base must be 0..46 (4x4_50 dictionary)")
    if 2 * (a.marker + a.margin) >= a.size:
        ap.error("markers don't fit on the card")
    layout = CardLayout(a.size, a.marker, a.margin, a.id_base)
    Path(a.output).write_text(build(layout, PAGES[a.page], a.bullseye), encoding="utf-8")
    print(f"wrote {a.output}: match these in config: card_size_mm={a.size:g}, "
          f"marker_size_mm={a.marker:g}, marker_margin_mm={a.margin:g}, marker_id_base={a.id_base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
