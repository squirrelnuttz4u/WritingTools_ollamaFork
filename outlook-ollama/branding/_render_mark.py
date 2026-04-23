"""Render the ACNR 'mark' - just the red US silhouette on a transparent square.

Used as the tray icon, window icon, and any small context where the full
wordmark of _render_logo.py would be illegible. Saved to branding/app_icon.png.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from _render_logo import _polygons_from_topology, _scale_polygons_to_box

HERE = Path(__file__).resolve().parent
TOPO = HERE / "vendor" / "us-nation-albers-10m.json"
OUT  = HERE / "app_icon.png"

SIZE   = 1024
MARGIN = 32
RED    = (178, 34, 34, 255)
RED_DK = (120, 20, 20, 255)


def main() -> None:
    polys = _polygons_from_topology(json.loads(TOPO.read_text()))

    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))  # transparent bg
    draw = ImageDraw.Draw(img)

    box = (MARGIN, MARGIN, SIZE - MARGIN, SIZE - MARGIN)
    for poly in _scale_polygons_to_box(polys, box):
        if len(poly) >= 3:
            draw.polygon(poly, fill=RED, outline=RED_DK)

    img.save(OUT, format="PNG")
    print(f"wrote {OUT} ({SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
