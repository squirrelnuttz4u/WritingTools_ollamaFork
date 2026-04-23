"""Render the ACNR Intelligence logo from a vendored US silhouette.

Source: us-atlas nation-albers-10m.json (ISC-licensed, Michael Bostock).

The output replaces outlook-ollama/branding/logo.png, then the caller should
run generate_logo_assets.py to rebuild the .ico and the Office ribbon PNGs.

Style: dark crimson US silhouette centered on a white square, with the
"AMERICAN CONSOLIDATED NATURAL RESOURCES, INC." wordmark wrapped above and
below. Designed to read cleanly at 16x16 through 512x512.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
TOPO = HERE / "vendor" / "us-nation-albers-10m.json"
OUT  = HERE / "logo.png"

SIZE       = 1024
MARGIN     = 40
RED        = (178, 34, 34, 255)    # firebrick / ACNR red
RED_DARK   = (120, 20, 20, 255)
WHITE      = (255, 255, 255, 255)

WORDMARK_TOP    = "AMERICAN CONSOLIDATED NATURAL RESOURCES, INC."
WORDMARK_BOTTOM = "ACNR INTELLIGENCE"


# ---------------------------------------------------------------------------
# TopoJSON -> polygon decoding
# ---------------------------------------------------------------------------
def _decode_arc(arc: List[List[int]], scale, translate) -> List[Tuple[float, float]]:
    """TopoJSON stores arcs as delta-encoded quantized coordinates. Undo that."""
    x = y = 0
    pts: List[Tuple[float, float]] = []
    for dx, dy in arc:
        x += dx
        y += dy
        pts.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
    return pts


def _polygons_from_topology(topo: dict) -> List[List[Tuple[float, float]]]:
    arcs_raw = topo["arcs"]
    scale = topo["transform"]["scale"]
    translate = topo["transform"]["translate"]
    decoded_arcs = [_decode_arc(a, scale, translate) for a in arcs_raw]

    def ring(arc_indices: List[int]) -> List[Tuple[float, float]]:
        pts: List[Tuple[float, float]] = []
        for idx in arc_indices:
            if idx < 0:
                seg = list(reversed(decoded_arcs[~idx]))
            else:
                seg = decoded_arcs[idx]
            if pts and seg:
                # Arcs share endpoints; skip the duplicate.
                seg = seg[1:]
            pts.extend(seg)
        return pts

    polys: List[List[Tuple[float, float]]] = []
    for geom in topo["objects"]["nation"]["geometries"]:
        gtype = geom["type"]
        arcs = geom["arcs"]
        if gtype == "Polygon":
            for r in arcs:
                polys.append(ring(r))
        elif gtype == "MultiPolygon":
            for poly in arcs:
                for r in poly:
                    polys.append(ring(r))
    return polys


def _load_us_polygons() -> List[List[Tuple[float, float]]]:
    topo = json.loads(TOPO.read_text())
    return _polygons_from_topology(topo)


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------
def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Logo composition
# ---------------------------------------------------------------------------
def _scale_polygons_to_box(
    polys: List[List[Tuple[float, float]]],
    box: Tuple[int, int, int, int],
) -> List[List[Tuple[float, float]]]:
    """Fit all polygons into the given pixel box (x0, y0, x1, y1), preserving aspect."""
    all_pts = [p for poly in polys for p in poly]
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    src_w = max(xs) - min(xs)
    src_h = max(ys) - min(ys)
    dst_w = box[2] - box[0]
    dst_h = box[3] - box[1]
    scale = min(dst_w / src_w, dst_h / src_h)
    new_w = src_w * scale
    new_h = src_h * scale
    off_x = box[0] + (dst_w - new_w) / 2 - min(xs) * scale
    off_y = box[1] + (dst_h - new_h) / 2 - min(ys) * scale
    return [[(x * scale + off_x, y * scale + off_y) for x, y in poly] for poly in polys]


def _draw_curved_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    center: Tuple[float, float],
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
    font: ImageFont.FreeTypeFont,
    fill,
    img: Image.Image,
) -> None:
    """Render `text` along an arc from start to end angle (degrees, 0 = east, CCW)."""
    # Measure per-character widths to distribute evenly along the arc.
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths)
    if total == 0:
        return

    arc_len = math.radians(end_angle_deg - start_angle_deg) * radius
    # Use the smaller of "natural" and "arc" so we never overflow.
    if arc_len > total:
        # Center the text by shrinking the span.
        arc_extent = total / radius
        start = math.radians((start_angle_deg + end_angle_deg) / 2) - arc_extent / 2
        end = start + arc_extent
        arc_len = total
    else:
        start = math.radians(start_angle_deg)
        end = math.radians(end_angle_deg)

    pos = 0.0
    for ch, w in zip(text, widths):
        frac = (pos + w / 2) / total
        theta = start + frac * (end - start)
        # For the bottom arc we want text facing outward (readable from outside).
        # For the top arc text faces inward (readable from outside naturally).
        is_bottom = math.sin(theta) > 0
        tangent = theta + math.pi / 2 if not is_bottom else theta - math.pi / 2
        cx = center[0] + radius * math.cos(theta)
        cy = center[1] - radius * math.sin(theta)   # PIL y is flipped
        # Render the character onto a small transparent canvas, rotate, paste.
        ch_img = Image.new("RGBA", (int(w) + 8, font.size + 8), (0, 0, 0, 0))
        ch_draw = ImageDraw.Draw(ch_img)
        ch_draw.text((4, 4), ch, font=font, fill=fill)
        rot_deg = math.degrees(tangent)
        rotated = ch_img.rotate(rot_deg, resample=Image.Resampling.BICUBIC, expand=True)
        img.alpha_composite(
            rotated,
            (int(cx - rotated.width / 2), int(cy - rotated.height / 2)),
        )
        pos += w


def main() -> None:
    polys = _load_us_polygons()

    img = Image.new("RGBA", (SIZE, SIZE), WHITE)
    draw = ImageDraw.Draw(img)

    # The US silhouette lives in the middle band. Leave top/bottom margins for text.
    map_box = (MARGIN, int(SIZE * 0.22), SIZE - MARGIN, int(SIZE * 0.82))
    placed = _scale_polygons_to_box(polys, map_box)

    # Fill the silhouette in dark red. Outline slightly darker for definition.
    for poly in placed:
        if len(poly) >= 3:
            draw.polygon(poly, fill=RED, outline=RED_DARK)

    # Top arc: "AMERICAN CONSOLIDATED NATURAL RESOURCES, INC."
    center = (SIZE / 2, SIZE / 2)
    radius_top = SIZE / 2 - 70
    top_font = _font(36, bold=True)
    _draw_curved_text(
        draw, WORDMARK_TOP, center, radius_top,
        start_angle_deg=150, end_angle_deg=30,
        font=top_font, fill=RED_DARK, img=img,
    )

    # Bottom flat: "ACNR INTELLIGENCE"
    bottom_font = _font(62, bold=True)
    bw = draw.textlength(WORDMARK_BOTTOM, font=bottom_font)
    draw.text(
        ((SIZE - bw) / 2, int(SIZE * 0.86)),
        WORDMARK_BOTTOM, font=bottom_font, fill=RED_DARK,
    )

    img.save(OUT, format="PNG")
    print(f"wrote {OUT} ({SIZE}x{SIZE})")


if __name__ == "__main__":
    main()
