"""Shared polygon helpers used by both logo renderers.

Separated from _render_logo.py so _render_mark.py can depend on these
primitives without pulling in the wide-banner rendering code.
"""
from __future__ import annotations

from typing import Dict, List, Tuple


def _decode_arc(arc: List[List[int]], scale, translate) -> List[Tuple[float, float]]:
    """Undo TopoJSON delta-encoding + quantization for a single arc."""
    x = y = 0
    pts: List[Tuple[float, float]] = []
    for dx, dy in arc:
        x += dx
        y += dy
        pts.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
    return pts


def polygons_from_topology(topo: Dict) -> List[List[Tuple[float, float]]]:
    """Flatten the us-atlas `nation` object to a list of absolute-coordinate rings."""
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
                seg = seg[1:]  # drop the shared endpoint
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


def polygon_area(poly: List[Tuple[float, float]]) -> float:
    """Absolute polygon area via the shoelace formula."""
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def scale_polygons_to_box(
    polys: List[List[Tuple[float, float]]],
    box: Tuple[int, int, int, int],
) -> List[List[Tuple[float, float]]]:
    """Fit all polygons into the given pixel box (x0, y0, x1, y1), preserving aspect."""
    all_pts = [p for poly in polys for p in poly]
    if not all_pts:
        return []
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    src_w = max(xs) - min(xs)
    src_h = max(ys) - min(ys)
    if src_w == 0 or src_h == 0:
        return polys
    dst_w = box[2] - box[0]
    dst_h = box[3] - box[1]
    scale = min(dst_w / src_w, dst_h / src_h)
    new_w = src_w * scale
    new_h = src_h * scale
    off_x = box[0] + (dst_w - new_w) / 2 - min(xs) * scale
    off_y = box[1] + (dst_h - new_h) / 2 - min(ys) * scale
    return [[(x * scale + off_x, y * scale + off_y) for x, y in poly] for poly in polys]
