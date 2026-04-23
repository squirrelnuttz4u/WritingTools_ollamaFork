"""Render the ACNR Intelligence wide logo banner.

Matches the artwork the customer supplied: four lines of stacked text on the
left ("AMERICAN / CONSOLIDATED / NATURAL / RESOURCES, INC.") and a red
lower-48 silhouette on the right. White background so it reads cleanly on
light and dark popup themes alike.

Source geometry: us-atlas nation-albers-10m.json (ISC, Michael Bostock).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from _render_logo_common import polygons_from_topology, scale_polygons_to_box, polygon_area

HERE = Path(__file__).resolve().parent
TOPO = HERE / "vendor" / "us-nation-albers-10m.json"
OUT  = HERE / "logo.png"

# Wide banner dimensions. The popup header and Outlook task pane both render
# this scaled; 1200x500 gives us a 2.4:1 aspect that fits both nicely.
WIDTH       = 1200
HEIGHT      = 500
MARGIN      = 30

# Left/right split: 45% text, 55% map.
TEXT_FRAC   = 0.45

RED         = (178, 34, 34, 255)     # ACNR firebrick red
RED_DARK    = (120, 20, 20, 255)
TEXT_COLOR  = (70, 70, 70, 255)      # near-black, matches the reference art
HIGHLIGHT   = (178, 34, 34, 255)     # red used for "NATURAL" accent line
BG          = (255, 255, 255, 255)   # white

LINES = ["AMERICAN", "CONSOLIDATED", "NATURAL", "RESOURCES, INC."]
# Line 3 ("NATURAL") is drawn in red to match the source artwork's accent.
RED_LINE_INDEX = 2


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    candidates_reg = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in (candidates_bold if bold else candidates_reg):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _largest_polygon(polys: List[List[Tuple[float, float]]]) -> List[Tuple[float, float]]:
    """Return just the continental US polygon (drops AK, HI, outlying islands)."""
    return max(polys, key=polygon_area)


def _fit_text_to_width(lines: List[str], max_width: int, max_height: int,
                       bold: bool = True) -> Tuple[ImageFont.FreeTypeFont, int]:
    """Find the largest font size such that every line fits in max_width and
    the stacked block fits in max_height. Returns (font, line_height)."""
    # Upper bound: 1/len(lines) of max_height so all lines fit vertically.
    best = 12
    line_spacing = 1.15
    for size in range(200, 20, -2):
        font = _font(size, bold=bold)
        dummy = Image.new("RGBA", (10, 10))
        d = ImageDraw.Draw(dummy)
        widths = [d.textlength(t, font=font) for t in lines]
        line_h = int(size * line_spacing)
        block_h = line_h * len(lines)
        if max(widths) <= max_width and block_h <= max_height:
            best = size
            break
    font = _font(best, bold=bold)
    return font, int(best * line_spacing)


def main() -> None:
    topo = json.loads(TOPO.read_text())
    polys = polygons_from_topology(topo)
    conus = _largest_polygon(polys)

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # --- Left text block -----------------------------------------------
    text_area_x0 = MARGIN
    text_area_x1 = int(WIDTH * TEXT_FRAC) - MARGIN // 2
    text_area_w  = text_area_x1 - text_area_x0
    text_area_h  = HEIGHT - 2 * MARGIN

    font, line_h = _fit_text_to_width(LINES, text_area_w, text_area_h, bold=True)

    block_h = line_h * len(LINES)
    y = (HEIGHT - block_h) // 2
    for i, text in enumerate(LINES):
        color = HIGHLIGHT if i == RED_LINE_INDEX else TEXT_COLOR
        w = draw.textlength(text, font=font)
        # Right-align the text block so it sits flush against the map side.
        x = text_area_x1 - w
        draw.text((x, y + i * line_h), text, font=font, fill=color)

    # --- Right silhouette (lower 48) -----------------------------------
    map_x0 = int(WIDTH * TEXT_FRAC) + MARGIN // 2
    map_box = (map_x0, MARGIN, WIDTH - MARGIN, HEIGHT - MARGIN)
    placed = scale_polygons_to_box([conus], map_box)
    for poly in placed:
        if len(poly) >= 3:
            draw.polygon(poly, fill=RED, outline=RED_DARK)

    img.save(OUT, format="PNG")
    print(f"wrote {OUT} ({WIDTH}x{HEIGHT}, lower-48 only)")


if __name__ == "__main__":
    main()
