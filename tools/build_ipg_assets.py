#!/usr/bin/env python3
"""Unified asset, seat-layout, localization, and standalone-sync builder for IPG.

Generates:
  1. gfx/interface/icons/ipg_gov_halo.dds  (32x32 transparent-center gold halo ring)
  2. Five modular GUI layout files under gui/:
       - gui/ipg_layout_hemicycle.gui      (100 / 200 / 300 tiers)
       - gui/ipg_layout_westminster.gui    (100 / 200 / 300 tiers)
       - gui/ipg_layout_horseshoe.gui      (100 / 200 / 300 tiers)
       - gui/ipg_layout_assembly.gui       (100 / 200 / 300 tiers)
       - gui/ipg_layout_bicameral.gui      (Upper 100 Power + Lower 200 Electoral/Alignment)
  3. 11-language UTF-8 BOM localization files under localization/*/ipg_l_*.yml
  4. Optional `--sync-standalone` sync into sibling `Improved ParliamentGraph[1.15]`.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MOD_DIR = Path(__file__).resolve().parent.parent
STANDALONE_DIR = MOD_DIR.parent / "Improved ParliamentGraph[1.15]"
WORKSHOP_IPG_DIR = Path(
    r"C:\Program Files (x86)\Steam\steamapps\workshop\content\529340\3721626337"
)

CANVAS_W = 600
CANVAS_H = 230

LAYOUT_DOT_SIZES: dict[str, dict[int, int]] = {
    "hemicycle":   {50: 13, 100: 11, 200: 9, 300: 7},
    "westminster": {50: 14, 100: 12, 200: 10, 300: 8},
    "horseshoe":   {50: 12, 100: 10, 200: 8, 300: 6},
    "assembly":    {50: 12, 100: 10, 200: 8, 300: 8},
}


# ---------------------------------------------------------------------------
# 1. Pure-Python uncompressed BGRA DDS generators (enamel dots, ruler seal,
#    chamber icons, swatch ring, and architectural floorplan underlays)
# ---------------------------------------------------------------------------


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 == edge0:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _write_rgba_dds(out_path: Path, w: int, h: int, pixels: bytes) -> None:
    """Write a standard 32-bit uncompressed A8R8G8B8 DDS texture."""
    assert len(pixels) == w * h * 4
    flags = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000
    pitch = w * 4
    pf_flags = 0x40 | 0x1  # DDPF_RGB | DDPF_ALPHAPIXELS
    header = struct.pack(
        "<4s7I11I8I5I",
        b"DDS ",
        124,
        flags,
        h,
        w,
        pitch,
        0,
        1,
        *([0] * 11),
        32,
        pf_flags,
        0,
        32,
        0x00FF0000,
        0x0000FF00,
        0x000000FF,
        0xFF000000,
        0x1000,
        0, 0, 0, 0,
    )
    assert len(header) == 128
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(header + pixels)


def build_white_circle_dds(out_path: Path) -> None:
    """Write a crisp 32x32 anti-aliased white circle disc matching overlay & halo."""
    w = h = 32
    cx = cy = (w - 1) / 2.0
    pixels = bytearray()
    for y in range(h):
        for x in range(w):
            r = math.hypot(x - cx, y - cy)
            alpha = 1.0 - _smoothstep(14.1, 15.2, r)
            a = int(round(255 * alpha))
            pixels.extend((255, 255, 255, a))
    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_gov_halo_dds(out_path: Path) -> None:
    """Write a 32x32 antique-gold INNER border ring with identical outer diameter."""
    w = h = 32
    cx = cy = (w - 1) / 2.0
    pixels = bytearray()

    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            r = math.hypot(dx, dy)
            if r <= 9.0 or r >= 15.4:
                pixels.extend((0, 0, 0, 0))
                continue

            # Inner dark bronze hairline separating IG/Party core from gold bezel
            inner_seam = _smoothstep(9.0, 9.8, r) * (1.0 - _smoothstep(10.3, 11.1, r))
            # Subdued antique brass-gold inner ring (strictly inside dot outer edge)
            gold_band = _smoothstep(10.2, 11.1, r) * (1.0 - _smoothstep(13.6, 14.3, r))
            # Outer dark sepia contour matching opposition dot edge pixel-for-pixel
            outer_rim = _smoothstep(13.6, 14.3, r) * (1.0 - _smoothstep(14.5, 15.35, r))

            # Subtle upper-left directional antique brass warmth (no neon glare)
            light = max(0.0, min(1.0, 0.52 - 0.30 * (dx / 15.0) - 0.34 * (dy / 15.0)))
            gr = 188 + 38 * light
            gg = 152 + 38 * light
            gb = 74 + 34 * light

            # Composite inner dark seam, antique gold band, and dark outer contour
            w_seam = inner_seam * 0.56
            w_gold = gold_band * 0.96
            w_rim = outer_rim * 0.86
            total = min(1.0, w_seam + w_gold + w_rim)
            if total <= 1e-4:
                pixels.extend((0, 0, 0, 0))
                continue

            denom = w_seam + w_gold + w_rim
            red = int(round((34 * w_seam + gr * w_gold + 24 * w_rim) / denom))
            green = int(round((25 * w_seam + gg * w_gold + 18 * w_rim) / denom))
            blue = int(round((15 * w_seam + gb * w_gold + 14 * w_rim) / denom))
            a = int(round(255 * total))
            pixels.extend((blue, green, red, a))

    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_dot_overlay_dds(out_path: Path) -> None:
    """Write a 32x32 matte Victorian enamel-button overlay with dark contour rim.

    Replaces the glossy plastic-bead highlight with a restrained diffuse top-left
    lift, subtle antique tone softening, and a crisp dark outer rim so opposition
    seats hold equal visual mass to governing seats.
    """
    w = h = 32
    cx = cy = (w - 1) / 2.0
    pixels = bytearray()

    for y in range(h):
        for x in range(w):
            dx = (x - cx) / 14.8
            dy = (y - cy) / 14.8
            r = math.hypot(dx, dy)
            r_px = math.hypot(x - cx, y - cy)
            if r_px >= 15.4:
                pixels.extend((0, 0, 0, 0))
                continue

            edge_mask = 1.0 - _smoothstep(14.3, 15.3, r_px)

            # Very gentle matte enamel diffuse lift (upper-left, no glossy bead)
            h_dist = math.hypot(dx + 0.28, dy + 0.30)
            lift = max(0.0, 1.0 - h_dist / 0.88)
            lift = (lift * lift) * 0.13

            # Subtle antique charcoal softening + lower-right matte shading + solid dark rim
            shade_dir = max(0.0, (dx * 0.55 + dy * 0.65 + 0.35) / 1.35)
            body_matte = 0.08 + 0.09 * shade_dir * _smoothstep(0.25, 0.90, r)
            outer_rim = _smoothstep(0.78, 0.93, r) * 0.68
            shadow = min(0.78, body_matte + outer_rim)

            if lift > shadow:
                a = int(round(255 * (lift - shadow) * edge_mask))
                pixels.extend((224, 240, 248, a))  # warm parchment diffuse lift
            else:
                a = int(round(255 * (shadow - lift) * edge_mask))
                pixels.extend((18, 20, 24, a))  # warm antique charcoal contour

    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_ruler_plinth_dds(out_path: Path) -> None:
    """Write a 48x48 double antique-gold ceremonial plinth medallion for the Ruler."""
    w = h = 48
    cx = cy = (w - 1) / 2.0
    pixels = bytearray()

    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            r = math.hypot(dx, dy)
            if r >= 23.8:
                pixels.extend((0, 0, 0, 0))
                continue

            # Dark mahogany-bronze recessed seal base
            base_a = (1.0 - _smoothstep(22.2, 23.4, r)) * 0.88
            # Outer fine antique-gold ring
            outer_ring = _smoothstep(20.0, 20.9, r) * (1.0 - _smoothstep(22.0, 22.9, r))
            # Inner refined gold filigree ring framing the Ruler's IG enamel core
            inner_ring = _smoothstep(14.8, 15.6, r) * (1.0 - _smoothstep(16.6, 17.4, r))
            # Four tiny cardinal brass studs at N/S/E/W between the two rings (r ~ 18.7)
            stud = 0.0
            for sx, sy in ((0.0, -18.7), (0.0, 18.7), (-18.7, 0.0), (18.7, 0.0)):
                d_stud = math.hypot(dx - sx, dy - sy)
                stud = max(stud, 1.0 - _smoothstep(0.9, 1.9, d_stud))

            gold_w = min(1.0, outer_ring * 0.96 + inner_ring * 0.98 + stud * 0.92)
            light = max(0.0, min(1.0, 0.54 - 0.30 * (dx / 23.0) - 0.34 * (dy / 23.0)))
            gr = 194 + 44 * light
            gg = 156 + 44 * light
            gb = 78 + 38 * light

            # Blend gold over dark bronze backing
            br, bg, bb = 28.0, 22.0, 18.0
            out_a = gold_w + base_a * (1.0 - gold_w)
            if out_a <= 1e-4:
                pixels.extend((0, 0, 0, 0))
                continue
            red = int(round((gr * gold_w + br * base_a * (1.0 - gold_w)) / out_a))
            green = int(round((gg * gold_w + bg * base_a * (1.0 - gold_w)) / out_a))
            blue = int(round((gb * gold_w + bb * base_a * (1.0 - gold_w)) / out_a))
            pixels.extend((blue, green, red, int(round(255 * out_a))))

    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_ruler_crown_dds(out_path: Path) -> None:
    """Write a 32x32 minimalist sovereign crown emblem with dark contrast outline."""
    w = h = 32

    def crown_sdf(px: float, py: float) -> float:
        """Signed distance (negative inside) to a balanced 3-peak heraldic crown."""
        # Normalize to [-1, 1] centered slightly lower for visual balance
        x = (px - 15.5) / 11.5
        y = (py - 16.5) / 11.5

        # Base circlet band (y in [0.24, 0.56], x in [-0.66, 0.66])
        bx = abs(x) - 0.66
        by = abs(y - 0.40) - 0.16
        d_band = math.hypot(max(bx, 0.0), max(by, 0.0)) + min(max(bx, by), 0.0)

        # Crown body polygon with 3 sharp classical peaks + 2 curved valleys
        # Top silhouette y_top(x) for |x| <= 0.72
        ax = abs(x)
        if ax <= 0.72:
            if ax <= 0.34:
                # Center peak (0, -0.58) down to valley (0.34, 0.06)
                t = ax / 0.34
                y_top = -0.56 + 0.62 * (t ** 0.85)
            else:
                # Valley (0.34, 0.06) up to side peak (0.68, -0.34)
                t = (ax - 0.34) / 0.34
                y_top = 0.06 - 0.40 * min(1.0, t)
            # Slight outward taper on outer flanks
            x_edge = 0.62 + 0.14 * max(0.0, (0.32 - y) / 0.75)
            in_body = (y >= y_top) and (y <= 0.32) and (ax <= x_edge)
            d_body = -0.06 if in_body else min(
                abs(y - y_top) if ax <= x_edge else 1.0,
                abs(ax - x_edge) if (y_top <= y <= 0.32) else 1.0,
                abs(y - 0.32) if ax <= x_edge else 1.0,
            )
        else:
            d_body = ax - 0.72

        # Three small heraldic orb finials atop the peaks
        d_orbs = min(
            math.hypot(x, y + 0.64) - 0.13,
            math.hypot(ax - 0.68, y + 0.40) - 0.11,
        )
        return min(d_band, d_body, d_orbs)

    # Precompute crisp supersampled fill & dark halo outline
    fill = [[0.0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            acc = 0.0
            for sy in (-0.3, 0.0, 0.3):
                for sx in (-0.3, 0.0, 0.3):
                    if crown_sdf(x + sx, y + sy) <= 0.0:
                        acc += 1.0
            fill[y][x] = acc / 9.0

    pixels = bytearray()
    for y in range(h):
        for x in range(w):
            f = fill[y][x]
            # Dilated dark shadow/outline (radius ~2px) for high readability on yellow/white IGs
            halo = 0.0
            for oy in range(-2, 3):
                ny = y + oy
                if 0 <= ny < h:
                    for ox in range(-2, 3):
                        nx = x + ox
                        if 0 <= nx < w:
                            dist = math.hypot(ox, oy)
                            if dist <= 2.2:
                                halo = max(halo, fill[ny][nx] * (1.0 - dist / 2.5))

            out_w = halo * 0.85
            t_y = max(0.0, min(1.0, (y - 7.0) / 18.0))
            cr = 254 - 26 * t_y
            cg = 236 - 44 * t_y
            cb = 166 - 62 * t_y

            out_a = f + out_w * (1.0 - f)
            if out_a <= 1e-4:
                pixels.extend((0, 0, 0, 0))
                continue
            red = int(round((cr * f + 20 * out_w * (1.0 - f)) / out_a))
            green = int(round((cg * f + 15 * out_w * (1.0 - f)) / out_a))
            blue = int(round((cb * f + 12 * out_w * (1.0 - f)) / out_a))
            pixels.extend((blue, green, red, int(round(255 * out_a))))

    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_gov_halo_small_dds(out_path: Path) -> None:
    """Write a 16x16 smooth antique-gold rim (NO dark inner seam) for <=8px dots.

    Eliminates downsampling aliasing / yellow-gear jaggedness on small-scale
    chambers (Bicameral, Horseshoe 200/300, Hemicycle 300, Assembly 200/300).
    """
    w = h = 16
    cx = cy = (w - 1) / 2.0
    pixels = bytearray()

    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            r = math.hypot(dx, dy)
            if r <= 4.3 or r >= 7.85:
                pixels.extend((0, 0, 0, 0))
                continue

            gold_band = _smoothstep(4.5, 5.5, r) * (1.0 - _smoothstep(6.7, 7.65, r))
            light = max(0.0, min(1.0, 0.54 - 0.26 * (dx / 7.5) - 0.30 * (dy / 7.5)))
            red = int(round(196 + 34 * light))
            green = int(round(160 + 34 * light))
            blue = int(round(80 + 30 * light))
            a = int(round(238 * gold_band))
            pixels.extend((blue, green, red, a))

    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_dot_overlay_small_dds(out_path: Path) -> None:
    """Write a 16x16 low-frequency matte enamel & soft dark rim for <=8px dots."""
    w = h = 16
    cx = cy = (w - 1) / 2.0
    pixels = bytearray()

    for y in range(h):
        for x in range(w):
            dx = (x - cx) / 7.4
            dy = (y - cy) / 7.4
            r = math.hypot(dx, dy)
            r_px = math.hypot(x - cx, y - cy)
            if r_px >= 7.85:
                pixels.extend((0, 0, 0, 0))
                continue

            edge_mask = 1.0 - _smoothstep(6.9, 7.75, r_px)
            h_dist = math.hypot(dx + 0.25, dy + 0.28)
            lift = max(0.0, 1.0 - h_dist / 0.90)
            lift = (lift * lift) * 0.11

            body_matte = 0.08
            outer_rim = _smoothstep(0.70, 0.94, r) * 0.54
            shadow = min(0.64, body_matte + outer_rim)

            if lift > shadow:
                a = int(round(255 * (lift - shadow) * edge_mask))
                pixels.extend((224, 240, 248, a))
            else:
                a = int(round(255 * (shadow - lift) * edge_mask))
                pixels.extend((18, 20, 24, a))

    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_tab_active_dds(out_path: Path) -> None:
    """Write a 64x32 warm antique-gold 9-slice active tab frame (no cool silver)."""
    w, h = 64, 32
    pixels = bytearray()
    for y in range(h):
        for x in range(w):
            d_left = x
            d_right = (w - 1) - x
            d_top = y
            d_bot = (h - 1) - y
            d_edge = min(d_left, d_right, d_top, d_bot)

            if d_edge == 0:
                r, g, b, a = 192, 152, 72, 225
            elif d_edge == 1:
                r, g, b, a = 232, 194, 108, 235
            elif d_bot == 2:
                r, g, b, a = 240, 204, 118, 215
            elif d_top == 2:
                r, g, b, a = 228, 192, 112, 95
            else:
                t_bot = y / (h - 1)
                r, g, b = 224, 180, 88
                a = int(round(18 + 34 * (t_bot ** 1.4)))

            if (x in (0, w - 1)) and (y in (0, h - 1)):
                a = 0
            pixels.extend((b, g, r, a))
    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_swatch_ring_dds(out_path: Path) -> None:
    """Write a 16x16 delicate pale parchment rim for dark IG/Party dots in tooltips."""
    w = h = 16
    cx = cy = (w - 1) / 2.0
    pixels = bytearray()
    for y in range(h):
        for x in range(w):
            r = math.hypot(x - cx, y - cy)
            ring = _smoothstep(5.4, 6.2, r) * (1.0 - _smoothstep(6.7, 7.5, r))
            a = int(round(165 * ring))
            pixels.extend((198, 222, 234, a))  # warm pale parchment (B, G, R, A)
    _write_rgba_dds(out_path, w, h, bytes(pixels))


# ---------------------------------------------------------------------------
# 1b. Architectural Floorplan Underlay DDS generators (600x230, 10%-14% alpha)
# ---------------------------------------------------------------------------


def _new_floor_canvas() -> list[list[float]]:
    return [[0.0] * CANVAS_W for _ in range(CANVAS_H)]


def _stamp_px(canvas: list[list[float]], x: float, y: float, val: float) -> None:
    ix = int(math.floor(x))
    iy = int(math.floor(y))
    fx = x - ix
    fy = y - iy
    for dy in (0, 1):
        py = iy + dy
        if 0 <= py < CANVAS_H:
            wy = fy if dy else (1.0 - fy)
            row = canvas[py]
            for dx in (0, 1):
                px = ix + dx
                if 0 <= px < CANVAS_W:
                    wx = fx if dx else (1.0 - fx)
                    v = val * wx * wy
                    if v > row[px]:
                        row[px] = v


def _draw_segment(
    canvas: list[list[float]],
    x0: float, y0: float, x1: float, y1: float,
    alpha: float,
    dashed: bool = False,
    dash_on: float = 5.0,
    dash_off: float = 4.0,
) -> None:
    dist = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(math.ceil(dist * 2.0)))
    period = dash_on + dash_off
    for i in range(steps + 1):
        s = dist * i / steps
        if dashed and (s % period) > dash_on:
            continue
        t = i / steps
        _stamp_px(canvas, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, alpha)


def _draw_arc(
    canvas: list[list[float]],
    cx: float, cy: float, r: float,
    deg_start: float, deg_end: float,
    alpha: float,
    dashed: bool = False,
) -> None:
    rad0 = math.radians(deg_start)
    rad1 = math.radians(deg_end)
    arc_len = abs(rad1 - rad0) * r
    steps = max(8, int(math.ceil(arc_len * 2.0)))
    for i in range(steps + 1):
        s = arc_len * i / steps
        if dashed and (s % 9.0) > 5.0:
            continue
        th = rad0 + (rad1 - rad0) * (i / steps)
        _stamp_px(canvas, cx + r * math.cos(th), cy - r * math.sin(th), alpha)


def _write_floor_canvas(out_path: Path, canvas: list[list[float]]) -> None:
    pixels = bytearray(CANVAS_W * CANVAS_H * 4)
    idx = 0
    # Warm antique parchment-brass architectural ink
    r_c, g_c, b_c = 218, 198, 152
    for y in range(CANVAS_H):
        row = canvas[y]
        for x in range(CANVAS_W):
            a = int(round(max(0.0, min(1.0, row[x])) * 255))
            pixels[idx] = b_c
            pixels[idx + 1] = g_c
            pixels[idx + 2] = r_c
            pixels[idx + 3] = a
            idx += 4
    _write_rgba_dds(out_path, CANVAS_W, CANVAS_H, bytes(pixels))


def build_floor_hemicycle_dds(out_path: Path) -> None:
    """Subtle concentric tiered hemicycle blueprint + 50% vertical axis + dais."""
    c = _new_floor_canvas()
    cx, cy = 300.0, 200.0
    for r, a in ((52.0, 0.14), (88.0, 0.11), (124.0, 0.11), (160.0, 0.11), (182.0, 0.14)):
        _draw_arc(c, cx, cy, r, 177.0, 3.0, a)
    # Subtle radial gangway dividers at 60° and 120°
    for deg in (60.0, 120.0):
        rad = math.radians(deg)
        _draw_segment(c, cx + 52.0 * math.cos(rad), cy - 52.0 * math.sin(rad),
                      cx + 182.0 * math.cos(rad), cy - 182.0 * math.sin(rad), 0.10)
    # 50% majority vertical dashed center line
    _draw_segment(c, cx, 14.0, cx, 162.0, 0.16, dashed=True, dash_on=4.0, dash_off=4.0)
    # Small semicircular presiding dais framing Ruler at (300, 194)
    _draw_arc(c, cx, 194.0, 22.0, 180.0, 0.0, 0.15)
    _draw_segment(c, cx - 26.0, 194.0, cx + 26.0, 194.0, 0.12)
    _write_floor_canvas(out_path, c)


def _draw_segment_faded(
    canvas: list[list[float]],
    x0: float, y0: float, x1: float, y1: float,
    alpha: float,
    fade_px: float = 20.0,
) -> None:
    """Draw a horizontal/sloped segment that smoothly fades out at both endpoints."""
    dist = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(math.ceil(dist * 2.0)))
    for i in range(steps + 1):
        s = dist * i / steps
        f_start = _smoothstep(0.0, fade_px, s)
        f_end = _smoothstep(0.0, fade_px, dist - s)
        t = i / steps
        _stamp_px(canvas, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, alpha * f_start * f_end)


def build_floor_westminster_tier_dds(out_path: Path, tier: int) -> None:
    """Tier-matched Westminster bench lines (end-faded) + exact-span Table of the House."""
    specs = {
        50:  (5, 5, 32, 16, 34),
        100: (5, 10, 26, 16, 34),
        200: (5, 20, 17, 15, 34),
        300: (6, 25, 14, 13, 32),
    }
    rows, cols, dx, dy, aisle = specs[tier]
    total_w = (cols - 1) * dx
    x0 = 326.0 - total_w / 2.0
    x1 = x0 + total_w
    y_mid = 108.0
    pad_x = 18.0
    x_l, x_r = x0 - pad_x, x1 + pad_x
    bench_h = (rows - 1) * dy + 6.0

    c = _new_floor_canvas()
    for frac in (0.0, 0.5, 1.0):
        off = aisle / 2.0 - 4.0 + frac * (bench_h + 4.0)
        _draw_segment_faded(c, x_l, y_mid - off, x_r, y_mid - off, 0.12, fade_px=22.0)
        _draw_segment_faded(c, x_l, y_mid + off, x_r, y_mid + off, 0.12, fade_px=22.0)

    tx0, tx1 = x0 - 6.0, x1 + 6.0
    ty0, ty1 = y_mid - 8.5, y_mid + 8.5
    _draw_segment(c, tx0, ty0, tx1, ty0, 0.15)
    _draw_segment(c, tx0, ty1, tx1, ty1, 0.15)
    _draw_segment(c, tx0, ty0, tx0, ty1, 0.15)
    _draw_segment(c, tx1, ty0, tx1, ty1, 0.15)
    _draw_segment(c, tx0 + 8.0, y_mid, tx1 - 8.0, y_mid, 0.11, dashed=True, dash_on=6.0, dash_off=4.0)

    _draw_arc(c, 104.0, y_mid, 22.0, 270.0, 90.0, 0.15)
    _draw_segment_faded(c, 126.0, y_mid, tx0, y_mid, 0.13, fade_px=10.0)
    _write_floor_canvas(out_path, c)


def build_floor_horseshoe_dds(out_path: Path) -> None:
    """Subtle U-shaped horseshoe concentric guidelines + 50% axis + top dais."""
    c = _new_floor_canvas()
    cx, y_bend, x_scale, leg = 300.0, 100.0, 1.16, 72.0
    for r, a in ((36.0, 0.14), (72.0, 0.11), (109.0, 0.14)):
        rx, ry = r * x_scale, r
        _draw_segment(c, cx - rx, y_bend - leg, cx - rx, y_bend, a)
        _draw_segment(c, cx + rx, y_bend - leg, cx + rx, y_bend, a)
        steps = 120
        for i in range(steps):
            p0 = math.pi * (1.0 - i / steps)
            p1 = math.pi * (1.0 - (i + 1) / steps)
            _draw_segment(
                c,
                cx + rx * math.cos(p0), y_bend + ry * math.sin(p0),
                cx + rx * math.cos(p1), y_bend + ry * math.sin(p1),
                a,
            )
    _draw_segment(c, cx, 62.0, cx, 206.0, 0.15, dashed=True, dash_on=4.0, dash_off=4.0)
    _draw_arc(c, cx, 38.0, 22.0, 360.0, 180.0, 0.15)
    _write_floor_canvas(out_path, c)


def build_floor_assembly_tier_dds(out_path: Path, tier: int) -> None:
    """Tier-matched Assembly Hall terraced curves + exact-length aisle + top presidium."""
    specs = {
        50:  (5, 5, 22, 22, 26, 86.0, 38.0),
        100: (5, 10, 16, 22, 24, 84.0, 38.0),
        200: (10, 10, 14, 14, 22, 68.0, 32.0),
        300: (10, 15, 12, 14, 20, 68.0, 32.0),
    }
    rows, half_cols, dx, dy, aisle, y0, ruler_cy = specs[tier]
    cx = 300.0
    wing_outer = aisle / 2.0 + (half_cols - 1) * dx + 14.0
    wing_inner = aisle / 2.0 - 2.0
    y_top = y0 - 8.0
    y_bot = y0 + (rows - 1) * dy + 8.0

    c = _new_floor_canvas()
    line_ys = [y_top, (y_top + y_bot) / 2.0, y_bot] if rows <= 5 else [
        y_top, y_top + (y_bot - y_top) / 3.0, y_top + 2.0 * (y_bot - y_top) / 3.0, y_bot
    ]
    for y_base in line_ys:
        for side in (-1, 1):
            x_in = cx + side * wing_inner
            x_out = cx + side * wing_outer
            steps = 36
            for i in range(steps):
                t0 = i / steps
                t1 = (i + 1) / steps
                px0 = x_in + (x_out - x_in) * t0
                px1 = x_in + (x_out - x_in) * t1
                py0 = y_base - 0.00032 * ((px0 - cx) ** 2)
                py1 = y_base - 0.00032 * ((px1 - cx) ** 2)
                fade = 1.0 - _smoothstep(0.75, 1.0, t0)
                _draw_segment(c, px0, py0, px1, py1, 0.12 * (0.25 + 0.75 * fade))

    _draw_segment(c, cx, y_top - 4.0, cx, y_bot + 2.0, 0.15, dashed=True, dash_on=4.0, dash_off=4.0)
    pres_y = ruler_cy + 16.0
    _draw_segment(c, cx - 54.0, pres_y, cx + 54.0, pres_y, 0.15)
    _draw_arc(c, cx, ruler_cy, 20.0, 360.0, 180.0, 0.13)
    _write_floor_canvas(out_path, c)


def build_floor_bicameral_dds(out_path: Path) -> None:
    """Balanced twin hemicycle blueprints on identical baseline + central Ruler dais."""
    c = _new_floor_canvas()
    cy = 190.0
    for r, a in ((36.0, 0.14), (74.0, 0.11), (114.0, 0.14)):
        _draw_arc(c, 148.0, cy, r, 178.0, 2.0, a)
    _draw_segment(c, 148.0, 72.0, 148.0, 162.0, 0.13, dashed=True, dash_on=4.0, dash_off=4.0)
    for r, a in ((40.0, 0.14), (82.0, 0.11), (122.0, 0.14)):
        _draw_arc(c, 452.0, cy, r, 178.0, 2.0, a)
    _draw_segment(c, 452.0, 64.0, 452.0, 162.0, 0.13, dashed=True, dash_on=4.0, dash_off=4.0)
    _draw_segment(c, 300.0, 42.0, 300.0, 148.0, 0.14, dashed=True, dash_on=4.0, dash_off=5.0)
    _draw_arc(c, 300.0, 176.0, 21.0, 0.0, 360.0, 0.15)
    _write_floor_canvas(out_path, c)


def write_textformatting_file(gui_dir: Path) -> Path:
    """Emit gui/ipg_textformatting.gui defining bright dark-bg green/red/gold/label formats."""
    content = (
        "# =============================================================================\n"
        "# Improved ParliamentGraph - High-Readability Dark-BG Text Formatting\n"
        "# Auto-generated by tools/build_ipg_assets.py — do not hand-edit.\n"
        "# =============================================================================\n\n"
        "textformatting = {\n"
        "\tformat = {\n"
        "\t\tname = ipg_green\n"
        '\t\tformat = "color:{ 0.46, 0.88, 0.56 }"\n'
        "\t}\n"
        "\tformat = {\n"
        "\t\tname = ipg_red\n"
        '\t\tformat = "color:{ 0.98, 0.52, 0.48 }"\n'
        "\t}\n"
        "\tformat = {\n"
        "\t\tname = ipg_gold\n"
        '\t\tformat = "color:{ 0.96, 0.84, 0.48 }"\n'
        "\t}\n"
        "\tformat = {\n"
        "\t\tname = ipg_label\n"
        '\t\tformat = "color:{ 0.84, 0.80, 0.72 }"\n'
        "\t}\n"
        "}\n"
    )
    out_path = gui_dir / "ipg_textformatting.gui"
    out_path.write_text(content, encoding="utf-8", newline="\n")
    return out_path


def build_chamber_upper_dds(out_path: Path) -> None:
    """Write a 24x24 antique-gold classical pediment & columns Upper House micro-icon."""
    w = h = 24
    pixels = bytearray()

    for y in range(h):
        for x in range(w):
            # Subtle warm antique gold gradient top->bottom
            t = y / (h - 1)
            r_col = int(round(244 - 38 * t))
            g_col = int(round(206 - 46 * t))
            b_col = int(round(118 - 44 * t))
            hit = False

            # Triangular pediment roof (y: 3..8)
            if 3 <= y <= 8:
                half_w = (y - 2.5) * 1.75
                if abs(x - 11.5) <= half_w:
                    hit = True
            # Entablature bar (y: 9..10)
            elif 9 <= y <= 10 and 3 <= x <= 20:
                hit = True
            # Three classical columns (y: 11..18)
            elif 11 <= y <= 18 and (x in (5, 6, 11, 12, 17, 18)):
                hit = True
            # Base plinth & steps (y: 19..21)
            elif y == 19 and 3 <= x <= 20:
                hit = True
            elif 20 <= y <= 21 and 2 <= x <= 21:
                hit = True

            if hit:
                pixels.extend((b_col, g_col, r_col, 245))
            else:
                pixels.extend((0, 0, 0, 0))

    _write_rgba_dds(out_path, w, h, bytes(pixels))


def build_chamber_lower_dds(out_path: Path) -> None:
    """Write a 24x24 warm sage-brass hemicycle benches Lower House micro-icon."""
    w = h = 24
    cx, cy = 11.5, 18.5
    pixels = bytearray()

    for y in range(h):
        for x in range(w):
            dx = x - cx
            dy = y - cy
            r = math.hypot(dx, dy)
            in_upper = dy <= 0.5
            hit = False
            bright = 1.0

            # Three concentric hemicycle seat arcs (r ~ 5.0, 7.8, 10.5)
            if in_upper and (abs(r - 5.0) <= 0.95 or abs(r - 7.8) <= 0.95 or abs(r - 10.4) <= 0.95):
                # Subtle center aisle notch
                if abs(dx) >= 0.8:
                    hit = True
                    bright = 1.05 if r < 6.5 else (0.95 if r < 9.0 else 0.85)
            # Central podium dot
            elif math.hypot(dx, dy + 0.5) <= 1.8:
                hit = True
                bright = 1.12

            if hit:
                red = min(255, int(round(170 * bright)))
                green = min(255, int(round(212 * bright)))
                blue = min(255, int(round(162 * bright)))
                pixels.extend((blue, green, red, 245))
            else:
                pixels.extend((0, 0, 0, 0))

    _write_rgba_dds(out_path, w, h, bytes(pixels))


def write_texticons_file(gui_dir: Path) -> Path:
    """Emit gui/ipg_texticons.gui registering @ipg_upper! and @ipg_lower!."""
    content = (
        "# =============================================================================\n"
        "# Improved ParliamentGraph - Custom Chamber Texticons (@ipg_upper!, @ipg_lower!)\n"
        "# Auto-generated by tools/build_ipg_assets.py — do not hand-edit.\n"
        "# =============================================================================\n\n"
        "texticon = {\n"
        "\ticon = ipg_upper\n"
        "\ticonsize = {\n"
        "\t\tsize = { 22 22 }\n"
        "\t\toffset = { 0 5 }\n"
        "\t\tfontsize = 18\n"
        '\t\ttexture = "gfx/interface/icons/ipg_chamber_upper.dds"\n'
        "\t}\n"
        "}\n\n"
        "texticon = {\n"
        "\ticon = ipg_lower\n"
        "\ticonsize = {\n"
        "\t\tsize = { 22 22 }\n"
        "\t\toffset = { 0 5 }\n"
        "\t\tfontsize = 18\n"
        '\t\ttexture = "gfx/interface/icons/ipg_chamber_lower.dds"\n'
        "\t}\n"
        "}\n"
    )
    out_path = gui_dir / "ipg_texticons.gui"
    out_path.write_text(content, encoding="utf-8", newline="\n")
    return out_path


# ---------------------------------------------------------------------------
# 2. Procedural 2D seat coordinate generators (all centered in 600x230)
# ---------------------------------------------------------------------------


def largest_remainder(weights: list[float], total: int) -> list[int]:
    s = sum(weights)
    exact = [w / s * total for w in weights]
    floors = [int(math.floor(x)) for x in exact]
    rem = total - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: exact[i] - floors[i], reverse=True)
    for i in order[:rem]:
        floors[i] += 1
    return floors


def gen_hemicycle(
    n: int,
    cx: float = 300.0,
    cy: float = 200.0,
    r_min: float = 66.0,
    r_max: float = 176.0,
    arcs: int = 8,
    dot_size: int = 8,
) -> list[tuple[int, int]]:
    """Classic semicircular hemicycle sweeping LEFT -> RIGHT in radial wedges."""
    radii = [
        r_min + (r_max - r_min) * i / max(1, arcs - 1)
        for i in range(arcs)
    ]
    counts = largest_remainder(radii, n)
    pts: list[tuple[float, float, int, int]] = []
    half = dot_size / 2.0
    a_start = math.radians(175.5)
    a_end = math.radians(4.5)
    for r, c in zip(radii, counts):
        for j in range(c):
            frac = 0.5 if c == 1 else j / (c - 1)
            theta = a_start + (a_end - a_start) * frac  # pi -> 0 (left -> right)
            x = int(round(cx + r * math.cos(theta) - half))
            y = int(round(cy - r * math.sin(theta) - half))
            pts.append((theta, r, x, y))
    pts.sort(key=lambda p: (-p[0], p[1]))
    return [(x, y) for _, _, x, y in pts]


def gen_westminster(n: int, dot_size: int) -> list[tuple[int, int]]:
    """House of Commons opposing benches: Top = Gov, Bottom = Opp, Speaker on left."""
    specs = {
        50:  (5, 5, 32, 16, 34),   # rows, cols, dx, dy, aisle_gap
        100: (5, 10, 26, 16, 34),
        200: (5, 20, 17, 15, 34),
        300: (6, 25, 14, 13, 32),
    }
    rows, cols, dx, dy, aisle = specs[n]
    assert rows * cols * 2 == n

    total_w = (cols - 1) * dx
    x0 = 326.0 - total_w / 2.0
    y_mid = 108.0
    half = dot_size / 2.0

    top_pts: list[tuple[int, int]] = []
    for col in range(cols):
        for row in range(rows):
            x = int(round(x0 + col * dx - half))
            y = int(round((y_mid - aisle / 2.0) - row * dy - half))
            top_pts.append((x, y))

    bot_pts: list[tuple[int, int]] = []
    for col in range(cols - 1, -1, -1):
        for row in range(rows):
            x = int(round(x0 + col * dx - half))
            y = int(round((y_mid + aisle / 2.0) + row * dy - half))
            bot_pts.append((x, y))

    return top_pts + bot_pts


def gen_horseshoe(n: int, dot_size: int) -> list[tuple[int, int]]:
    """Commonwealth U-shaped horseshoe with true arc-length spacing & >=18px margins."""
    specs = {
        50:  (3, 46.0, 94.0, 62.0, 102.0, 1.12),   # shells, r_min, r_max, leg, y_bend, x_scale
        100: (4, 46.0, 98.0, 66.0, 102.0, 1.14),
        200: (6, 44.0, 102.0, 70.0, 100.0, 1.16),
        300: (7, 44.0, 104.0, 72.0, 100.0, 1.18),
    }
    shells, r_min, r_max, leg, y_bend, x_scale = specs[n]
    radii = [r_min + (r_max - r_min) * i / max(1, shells - 1) for i in range(shells)]
    cx = 300.0
    half = dot_size / 2.0

    # Numerical arc-length LUT along the bottom half-ellipse (phi: pi -> 0)
    def build_arc_lut(a: float, b: float, samples: int = 512) -> tuple[list[float], list[float]]:
        phis = [math.pi * (1.0 - k / samples) for k in range(samples + 1)]
        cum = [0.0]
        px_prev = a * math.cos(phis[0])
        py_prev = b * math.sin(phis[0])
        for k in range(1, samples + 1):
            px = a * math.cos(phis[k])
            py = b * math.sin(phis[k])
            cum.append(cum[-1] + math.hypot(px - px_prev, py - py_prev))
            px_prev, py_prev = px, py
        return phis, cum

    def sample_phi(phis: list[float], cum: list[float], target_s: float) -> float:
        lo, hi = 0, len(cum) - 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if cum[mid] <= target_s:
                lo = mid
            else:
                hi = mid
        seg = cum[hi] - cum[lo]
        frac = 0.0 if seg <= 1e-9 else (target_s - cum[lo]) / seg
        return phis[lo] + (phis[hi] - phis[lo]) * frac

    luts = [build_arc_lut(r * x_scale, r) for r in radii]
    weights = [2.0 * leg + cum[-1] for _, cum in luts]
    counts = largest_remainder(weights, n)

    pts: list[tuple[float, float, int, int]] = []
    for r, c, (phis, cum) in zip(radii, counts, luts):
        a, b = r * x_scale, r
        arc_len = cum[-1]
        total_len = 2.0 * leg + arc_len

        for j in range(c):
            t = 0.5 if c == 1 else j / (c - 1)
            s = t * total_len
            if s <= leg:
                px = cx - a
                py = (y_bend - leg) + s
            elif s <= leg + arc_len:
                phi = sample_phi(phis, cum, s - leg)
                px = cx + a * math.cos(phi)
                py = y_bend + b * math.sin(phi)
            else:
                rem_s = s - (leg + arc_len)
                px = cx + a
                py = y_bend - rem_s

            pts.append((t, r, int(round(px - half)), int(round(py - half))))

    pts.sort(key=lambda p: (p[0], p[1]))
    return [(x, y) for _, _, x, y in pts]


def gen_assembly(n: int, dot_size: int) -> list[tuple[int, int]]:
    """Auditorium / People's Congress hall with exact 0px mirror symmetry & vertical centering."""
    specs = {
        50:  (5, 5, 22, 22, 26, 86.0),   # rows, half_cols, dx, dy, aisle_gap, y0
        100: (5, 10, 16, 22, 24, 84.0),
        200: (10, 10, 14, 14, 22, 68.0),
        300: (10, 15, 12, 14, 20, 68.0),
    }
    rows, half_cols, dx, dy, aisle, y0 = specs[n]
    assert rows * half_cols * 2 == n

    cx = 300.0
    half = dot_size / 2.0
    pts: list[tuple[int, int]] = []

    col_xs: list[float] = []
    for c in range(half_cols - 1, -1, -1):
        col_xs.append(cx - aisle / 2.0 - c * dx)
    for c in range(half_cols):
        col_xs.append(cx + aisle / 2.0 + c * dx)

    for px in col_xs:
        curve = -0.00032 * ((px - cx) ** 2)
        for r in range(rows):
            py = y0 + r * dy + curve
            pts.append((int(round(px - half)), int(round(py - half))))

    return pts


def validate_positions(
    name: str,
    pts: list[tuple[int, int]],
    expected: int,
    dot_size: int,
    min_y_margin: int = 8,
    min_bottom_margin: int = 8,
    min_gap: float = 1.9,
) -> float:
    assert len(pts) == expected, f"{name}: expected {expected} seats, got {len(pts)}"
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert min(xs) >= 8 and max(xs) + dot_size <= CANVAS_W - 8, (
        f"{name}: X out of bounds ({min(xs)}..{max(xs)+dot_size})"
    )
    assert min(ys) >= min_y_margin and max(ys) + dot_size <= CANVAS_H - min_bottom_margin, (
        f"{name}: Y out of bounds ({min(ys)}..{max(ys)+dot_size})"
    )
    min_d = 9999.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        for j in range(i + 1, len(pts)):
            d = math.hypot(pts[j][0] - x1, pts[j][1] - y1)
            if d < min_d:
                min_d = d
    gap = min_d - dot_size
    assert gap >= min_gap, (
        f"{name}: seats too cramped (min_center_dist={min_d:.2f}px, dot={dot_size}px, gap={gap:.2f}px < {min_gap}px)"
    )
    return gap


# ---------------------------------------------------------------------------
# 3. GUI Emitter (minimal tintcolor icons + child hollow gold halo on Gov)
# ---------------------------------------------------------------------------


def vis_range(scope_expr: str, var_min: str, var_max: str, idx: int) -> str:
    return (
        f"[And("
        f"GreaterThanOrEqualTo_CFixedPoint({scope_expr}.MakeScope.Var('{var_max}').GetValue, '(CFixedPoint){idx}'), "
        f"LessThanOrEqualTo_CFixedPoint({scope_expr}.MakeScope.Var('{var_min}').GetValue, '(CFixedPoint){idx}'))]"
    )


def emit_seat_widget(
    type_name: str,
    pts: list[tuple[int, int]],
    dot_size: int,
    halo_size: int,
    scope_visible: str,
    tint_expr: str,
    var_min: str,
    var_max: str,
    scope_expr: str,
    comment: str,
    datacontext_expr: str | None = None,
    gov_halo_expr: str | None = None,
    sample_indices: list[int] | None = None,
    tooltip_key: str | None = None,
) -> str:
    is_raw_color = tint_expr.lstrip().startswith("{")
    tint_line = (
        f"\t\t\ttintcolor = {tint_expr}"
        if is_raw_color
        else f'\t\t\ttintcolor = "{tint_expr}"'
    )
    lines = [
        f"\t# -- {comment} --",
        f"\ttype {type_name} = widget {{",
        f"\t\tsize = {{ {CANVAS_W} {CANVAS_H} }}",
    ]
    if datacontext_expr:
        lines.append(f'\t\tdatacontext = "{datacontext_expr}"')
    lines.append(f'\t\tvisible = "{scope_visible}"')

    overlay_tex = (
        "gfx/interface/icons/ipg_dot_overlay_small.dds"
        if dot_size <= 8
        else "gfx/interface/icons/ipg_dot_overlay.dds"
    )
    halo_tex = (
        "gfx/interface/icons/ipg_gov_halo_small.dds"
        if dot_size <= 8
        else "gfx/interface/icons/ipg_gov_halo.dds"
    )

    for i, (x, y) in enumerate(pts):
        idx = sample_indices[i] if sample_indices is not None else i
        vis = vis_range(scope_expr, var_min, var_max, idx)
        lines.append("\t\ticon = {")
        lines.append('\t\t\ttexture = "gfx/interface/icons/ipg_white_circle.dds"')
        lines.append(tint_line)
        lines.append(f"\t\t\tsize = {{ {dot_size} {dot_size} }}")
        lines.append(f"\t\t\tposition = {{ {x} {y} }}")
        lines.append(f'\t\t\tvisible = "{vis}"')
        if tooltip_key:
            lines.append("\t\t\talwaystransparent = no")
            lines.append("\t\t\tusing = tooltip_above")
            lines.append(f'\t\t\ttooltip = "{tooltip_key}"')
        lines.append("\t\t\ticon = {")
        lines.append(f'\t\t\t\ttexture = "{overlay_tex}"')
        lines.append("\t\t\t\tsize = { 100% 100% }")
        lines.append("\t\t\t\talwaystransparent = yes")
        lines.append("\t\t\t}")
        if gov_halo_expr:
            lines.append("\t\t\ticon = {")
            lines.append(f'\t\t\t\ttexture = "{halo_tex}"')
            lines.append("\t\t\t\tsize = { 100% 100% }")
            lines.append("\t\t\t\tparentanchor = center")
            lines.append("\t\t\t\talwaystransparent = yes")
            lines.append(f'\t\t\t\tvisible = "{gov_halo_expr}"')
            lines.append("\t\t\t}")
        lines.append("\t\t}")
    lines.append("\t}")
    lines.append("")
    return "\n".join(lines)


def write_standard_layout_file(
    slug: str,
    title: str,
    gen_fn,
    gui_dir: Path,
) -> tuple[Path, int]:
    header = (
        f"# =============================================================================\n"
        f"# Improved ParliamentGraph - {title} Layout (100 / 200 / 300 tiers)\n"
        f"# Auto-generated by tools/build_ipg_assets.py — do not hand-edit.\n"
        f"# =============================================================================\n\n"
        f"types politics_panel_types\n{{\n"
    )
    blocks: list[str] = []
    total_icons = 0

    for tier in (50, 100, 200, 300):
        dot = LAYOUT_DOT_SIZES[slug][tier]
        halo = dot
        pts = gen_fn(tier, dot)
        y_pad = 16 if slug == "horseshoe" else 8
        gap = validate_positions(f"{slug}_{tier}", pts, tier, dot, min_y_margin=y_pad, min_bottom_margin=y_pad)
        print(f"       {slug}_{tier}: dot={dot}px (equal outer dia), min_gap={gap:.2f}px")

        blocks.append(emit_seat_widget(
            f"ipg_{slug}_{tier}_power", pts, dot, halo,
            "[And(InterestGroup.MakeScope.Var('power_seat_max').IsSet, InterestGroup.MakeScope.Var('power_seat_min').IsSet)]",
            "[InterestGroup.GetColor]", "power_seat_min", "power_seat_max", "InterestGroup",
            f"{title} ({tier}) - Power Structure IG",
            datacontext_expr="[Scope.GetInterestGroup]",
            gov_halo_expr="[InterestGroup.IsInGovernment]",
            tooltip_key="ipg_seat_power_tt",
        ))
        blocks.append(emit_seat_widget(
            f"ipg_{slug}_{tier}_alignment", pts, dot, halo,
            "[And(InterestGroup.MakeScope.Var('alignment_seat_max').IsSet, InterestGroup.MakeScope.Var('alignment_seat_min').IsSet)]",
            "[InterestGroup.GetColor]", "alignment_seat_min", "alignment_seat_max", "InterestGroup",
            f"{title} ({tier}) - Political Alignment IG",
            datacontext_expr="[Scope.GetInterestGroup]",
            gov_halo_expr="[InterestGroup.IsInGovernment]",
            tooltip_key="ipg_seat_alignment_tt",
        ))
        blocks.append(emit_seat_widget(
            f"ipg_{slug}_{tier}_electoral", pts, dot, halo,
            "[And(Party.MakeScope.Var('electoral_seat_max').IsSet, Party.MakeScope.Var('electoral_seat_min').IsSet)]",
            "[Party.GetColor]", "electoral_seat_min", "electoral_seat_max", "Party",
            f"{title} ({tier}) - Electoral Party",
            datacontext_expr="[Scope.GetParty]",
            gov_halo_expr="[Party.IsInGovernment]",
            tooltip_key="ipg_seat_electoral_tt",
        ))
        blocks.append(emit_seat_widget(
            f"ipg_{slug}_{tier}_unaligned", pts, dot, halo,
            "[Country.MakeScope.Var('ipg_alignment_unaligned_max').IsSet]",
            "{ 0.55 0.55 0.55 1.00 }",
            "ipg_alignment_unaligned_min", "ipg_alignment_unaligned_max", "Country",
            f"{title} ({tier}) - Politically Unaligned",
            tooltip_key="ipg_seat_unaligned_tt",
        ))
        total_icons += tier * 4

    out_path = gui_dir / f"ipg_layout_{slug}.gui"
    out_path.write_text(header + "\n".join(blocks) + "}\n", encoding="utf-8", newline="\n")
    return out_path, total_icons


def write_bicameral_layout_file(gui_dir: Path) -> tuple[Path, int]:
    """Balanced Left 100-dot Upper House (Power) + Right 200-dot Lower House on aligned baseline."""
    dot_u, halo_u = 8, 8
    dot_l, halo_l = 7, 7
    upper_pts = gen_hemicycle(
        100, cx=148.0, cy=190.0, r_min=44.0, r_max=110.0, arcs=5, dot_size=dot_u
    )
    lower_pts = gen_hemicycle(
        200, cx=452.0, cy=190.0, r_min=48.0, r_max=118.0, arcs=8, dot_size=dot_l
    )
    gap_u = validate_positions("bicameral_upper_100", upper_pts, 100, dot_u)
    gap_l = validate_positions("bicameral_lower_200", lower_pts, 200, dot_l)
    print(f"       bicameral: upper dot={dot_u}px (gap={gap_u:.2f}px) | lower dot={dot_l}px (gap={gap_l:.2f}px)")

    header = (
        "# =============================================================================\n"
        "# Improved ParliamentGraph - Bicameral Split Layout (Upper 100 + Lower 200)\n"
        "# Subsamples the active visual tier (50 / 100 / 200 / 300) proportionally with zero\n"
        "# extra script variables.\n"
        "# Auto-generated by tools/build_ipg_assets.py — do not hand-edit.\n"
        "# =============================================================================\n\n"
        "types politics_panel_types\n{\n"
    )
    blocks: list[str] = []
    total_icons = 0

    for tier in (50, 100, 200, 300):
        idx_u = [int(round(i * (tier - 1) / 99.0)) for i in range(100)]
        idx_l = [int(round(i * (tier - 1) / 199.0)) for i in range(200)]

        blocks.append(emit_seat_widget(
            f"ipg_bicameral_upper_{tier}_power", upper_pts, dot_u, halo_u,
            "[And(InterestGroup.MakeScope.Var('power_seat_max').IsSet, InterestGroup.MakeScope.Var('power_seat_min').IsSet)]",
            "[InterestGroup.GetColor]", "power_seat_min", "power_seat_max", "InterestGroup",
            f"Bicameral Upper House (Power, mapped from tier {tier})",
            datacontext_expr="[Scope.GetInterestGroup]",
            gov_halo_expr="[InterestGroup.IsInGovernment]",
            sample_indices=idx_u,
            tooltip_key="ipg_seat_power_tt",
        ))
        blocks.append(emit_seat_widget(
            f"ipg_bicameral_lower_{tier}_electoral", lower_pts, dot_l, halo_l,
            "[And(Party.MakeScope.Var('electoral_seat_max').IsSet, Party.MakeScope.Var('electoral_seat_min').IsSet)]",
            "[Party.GetColor]", "electoral_seat_min", "electoral_seat_max", "Party",
            f"Bicameral Lower House (Electoral, mapped from tier {tier})",
            datacontext_expr="[Scope.GetParty]",
            gov_halo_expr="[Party.IsInGovernment]",
            sample_indices=idx_l,
            tooltip_key="ipg_seat_electoral_tt",
        ))
        blocks.append(emit_seat_widget(
            f"ipg_bicameral_lower_{tier}_alignment", lower_pts, dot_l, halo_l,
            "[And(InterestGroup.MakeScope.Var('alignment_seat_max').IsSet, InterestGroup.MakeScope.Var('alignment_seat_min').IsSet)]",
            "[InterestGroup.GetColor]", "alignment_seat_min", "alignment_seat_max", "InterestGroup",
            f"Bicameral Lower House (Alignment fallback, mapped from tier {tier})",
            datacontext_expr="[Scope.GetInterestGroup]",
            gov_halo_expr="[InterestGroup.IsInGovernment]",
            sample_indices=idx_l,
            tooltip_key="ipg_seat_alignment_tt",
        ))
        blocks.append(emit_seat_widget(
            f"ipg_bicameral_lower_{tier}_unaligned", lower_pts, dot_l, halo_l,
            "[Country.MakeScope.Var('ipg_alignment_unaligned_max').IsSet]",
            "{ 0.55 0.55 0.55 1.00 }",
            "ipg_alignment_unaligned_min", "ipg_alignment_unaligned_max", "Country",
            f"Bicameral Lower House (Unaligned fallback, mapped from tier {tier})",
            sample_indices=idx_l,
            tooltip_key="ipg_seat_unaligned_tt",
        ))
        total_icons += 100 + 200 * 3

    out_path = gui_dir / "ipg_layout_bicameral.gui"
    out_path.write_text(header + "\n".join(blocks) + "}\n", encoding="utf-8", newline="\n")
    return out_path, total_icons


# ---------------------------------------------------------------------------
# 4. 11-Language UTF-8 BOM Localization Generator
# ---------------------------------------------------------------------------

LOC_BASE: dict[str, dict[str, str]] = {
    "english": {
        "ipg_colon": ": ",
        "ipg_formula_prefix": "Method: ",
        "ipg_layout_prefix": "Hall: ",
        "ipg_panel_title": "Parliament",
        "ipg_expand": "Expand",
        "ipg_collapse": "Collapse",
        "ipg_view_power": "Power Structure",
        "ipg_view_alignment": "Political Alignment",
        "ipg_view_electoral": "Party Structure",
        "ipg_power_desc": "Share of $concept_clout$ by $concept_interest_group$.",
        "ipg_alignment_desc": "$concept_population$ alignment by $concept_interest_group$.",
        "ipg_electoral_desc": "$concept_votes$ share from the last $concept_election$.",
        "ipg_unaligned": "$concept_politically_unaligned$",
        "ipg_last_election": "Last Election",
        "ipg_next_election": "Next Election",
        "ipg_seats_unit": "Seats",
        "ipg_seats_col": "Seats",
        "ipg_share_col": "Share",
        "ipg_votes_col": "Votes",
        "ipg_members_col": "Members",
        "ipg_gov_label": "Gov",
        "ipg_opp_label": "Opp",
        "ipg_total_label": "Total",
        "ipg_majority_tag": "#ipg_green Majority#!",
        "ipg_minority_tag": "#ipg_red Minority#!",
        "ipg_layout_auto": "Auto",
        "ipg_layout_auto_tt": "Automatically matches chamber architecture to your country's laws and parliamentary tradition.",
        "ipg_layout_hemicycle": "Hemicycle",
        "ipg_layout_westminster": "Westminster",
        "ipg_layout_horseshoe": "Horseshoe",
        "ipg_layout_assembly": "Assembly",
        "ipg_layout_bicameral": "Bicameral",
        "ipg_layout_menu_title": "Chamber Layout",
        "ipg_mode_auto_badge": "#ipg_green Auto#!",
        "ipg_mode_manual_badge": "#title Custom#!",
        "ipg_layout_current_label": "Active Chamber",
        "ipg_layout_reason_label": "Constitutional Basis",
        "ipg_layout_cond_label": "Tradition & Laws",
        "ipg_layout_click_hint": "#instruction Click to choose a chamber layout#!",
        "ipg_layout_opt_badge_auto": "#ipg_green Traditional#!",
        "ipg_layout_opt_badge_preset": "Chamber Style",
        "ipg_layout_opt_badge_dual": "Bicameral",
        "ipg_layout_reason_manual": "Custom chamber arrangement currently in effect. Select another hall style or return to Auto to follow national traditions.",
        "ipg_layout_reason_1": "Follows the institutional tradition of #v $law_council_republic$#! or #v $law_single_party_state$#!.",
        "ipg_layout_reason_2": "Follows the #v $heritage_british$ / $anglo_canadian$#! parliamentary tradition (non-$law_autocracy$).",
        "ipg_layout_reason_3": "Follows the constitutional tradition of a #v $law_parliamentary_republic$#!.",
        "ipg_layout_reason_4": "Follows the #v $australian$#! parliamentary tradition (non-$law_autocracy$).",
        "ipg_layout_reason_5": "Follows the constitutional tradition of a #v $law_monarchy$#! with voting laws.",
        "ipg_layout_reason_6": "Follows the bicameral tradition of a #v $law_presidential_republic$#! with voting laws.",
        "ipg_layout_reason_7": "Classic continental hemicycle adopted under the current $lawgroup_governance_principles$.",
        "ipg_layout_auto_desc": "Adapts the chamber layout automatically to your $lawgroup_governance_principles$, $lawgroup_distribution_of_power$, and parliamentary heritage.",
        "ipg_layout_auto_cond": "• #v $law_council_republic$ / $law_single_party_state$#!: Assembly\n• #v $heritage_british$ / $anglo_canadian$#! (non-$law_autocracy$) or #v $law_parliamentary_republic$#!: Westminster\n• #v $law_presidential_republic$#! (with voting law): Bicameral\n• #v $australian$#! or other #v $law_monarchy$#! (with voting law): Horseshoe\n• #v $law_autocracy$ / $law_oligarchy$ / $law_technocracy$#! & others: Hemicycle",
        "ipg_layout_hemicycle_desc": "Classic continental European fan-shaped amphitheater inspired by the Palais Bourbon, radiating outward from the presiding dais.",
        "ipg_layout_hemicycle_cond": "Standard chamber for #v $law_autocracy$#!, #v $law_oligarchy$#!, #v $law_technocracy$#!, and regimes without a distinct parliamentary tradition.",
        "ipg_layout_westminster_desc": "Iconic opposing benches inspired by the Palace of Westminster, with Government and Opposition facing each other across the aisle.",
        "ipg_layout_westminster_cond": "• Primary culture with #v $heritage_british$#! heritage (excl. $australian$) or #v $anglo_canadian$#! (non-$law_autocracy$)\n• Or enacted #v $law_parliamentary_republic$#!",
        "ipg_layout_horseshoe_desc": "Curved U-shaped Commonwealth chamber blending Westminster debate traditions with cross-bench consensus seating.",
        "ipg_layout_horseshoe_cond": "• Primary culture is #v $australian$#! (non-$law_autocracy$)\n• Or non-$heritage_british$ #v $law_monarchy$#! with any voting law",
        "ipg_layout_assembly_desc": "Stepped rectilinear congress hall with ranked seating rows facing the central presidium.",
        "ipg_layout_assembly_cond": "Enacted #v $law_council_republic$#! or #v $law_single_party_state$#!.",
        "ipg_layout_bicameral_desc": "Dual-chamber parliament displaying the Upper House (Power Structure) on the left and the Lower House (Party Structure or Political Alignment) on the right.",
        "ipg_layout_bicameral_cond": "Enacted #v $law_presidential_republic$#! with any voting law.",
        "ipg_bicameral_panel_title": "Bicameral Parliament",
        "ipg_bicameral_upper": "@ipg_upper! [Country.GetCustom('ipg_upper_house_name')]",
        "ipg_bicameral_lower_electoral": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]",
        "ipg_bicameral_lower_alignment": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]",
        "ipg_toggle_info_btn": "Info",
        "ipg_toggle_info_tt": "Show or hide seat summaries and election dates within the chamber.",
        "ipg_no_election_yet": "No election results recorded yet. Hold an election or switch to Power Structure.",
        "ipg_ruler_title": "$concept_ruler$",
        # --- v3.1 Historical Chamber Names ---
        "ipg_ch_default_lower": "Lower House",
        "ipg_ch_default_upper": "Upper House",
        "ipg_ch_default_monarchy_upper": "House of Peers",
        "ipg_ch_senate": "Senate",
        "ipg_ch_usa_single": "Congress",
        "ipg_ch_usa_lower": "House of Representatives",
        "ipg_ch_gbr_single": "Parliament",
        "ipg_ch_gbr_lower": "House of Commons",
        "ipg_ch_gbr_upper": "House of Lords",
        "ipg_ch_fra_assembly": "National Assembly",
        "ipg_ch_fra_monarchy_single": "Parliament",
        "ipg_ch_fra_monarchy_lower": "Chamber of Deputies",
        "ipg_ch_fra_monarchy_upper": "Chamber of Peers",
        "ipg_ch_ger_single": "Imperial Parliament",
        "ipg_ch_ger_lower": "Reichstag",
        "ipg_ch_ger_upper": "Bundesrat",
        "ipg_ch_pru_single": "Landtag",
        "ipg_ch_pru_lower": "House of Deputies",
        "ipg_ch_pru_upper": "House of Lords",
        "ipg_ch_aus_monarchy_single": "Imperial Council",
        "ipg_ch_aus_rep_lower": "National Council",
        "ipg_ch_aus_rep_upper": "Federal Council",
        "ipg_ch_rus_single": "Imperial Assembly",
        "ipg_ch_rus_lower": "State Duma",
        "ipg_ch_rus_upper": "State Council",
        "ipg_ch_supreme_soviet": "Supreme Soviet",
        "ipg_ch_soviet_lower": "Soviet of the Union",
        "ipg_ch_soviet_upper": "Soviet of Nationalities",
        "ipg_ch_peoples_congress": "People's Congress",
        "ipg_ch_council_upper": "Supreme Council",
        "ipg_ch_jap_single": "Imperial Diet",
        "ipg_ch_jap_rep_single": "National Diet",
        "ipg_ch_jap_lower": "House of Representatives",
        "ipg_ch_jap_upper": "House of Peers",
        "ipg_ch_chi_monarchy_single": "Imperial Court",
        "ipg_ch_chi_monarchy_lower": "Advisory Council",
        "ipg_ch_chi_monarchy_upper": "Grand Council",
        "ipg_ch_tur_monarchy_single": "General Assembly",
        "ipg_ch_tur_rep_single": "Grand National Assembly",
        "ipg_ch_tur_lower": "Chamber of Deputies",
        "ipg_ch_tur_upper": "Senate",
        "ipg_ch_pol_lower": "Sejm",
        "ipg_ch_spa_single": "Cortes Generales",
        "ipg_ch_spa_lower": "Congress of Deputies",
        "ipg_ch_ita_lower": "Chamber of Deputies",
        "ipg_ch_latam_single": "National Congress",
        "ipg_ch_bel_lower": "Chamber of Representatives",
        "ipg_ch_net_single": "States General",
        "ipg_ch_net_lower": "Second Chamber",
        "ipg_ch_net_upper": "First Chamber",
        "ipg_ch_swe_single": "Riksdag",
        "ipg_ch_nor_single": "Storting",
        "ipg_ch_nor_lower": "Odelsting",
        "ipg_ch_nor_upper": "Lagting",
        # --- v3.1 Seat Apportionment / PR Formulas ---
        "ipg_formula_menu_title": "Seat Apportionment",
        "ipg_formula_auto": "Auto",
        "ipg_formula_1": "Hare / Hamilton",
        "ipg_formula_2": "D'Hondt",
        "ipg_formula_3": "Sainte-Laguë",
        "ipg_formula_4": "5% Threshold",
        "ipg_formula_5": "Plurality (FPTP)",
        "ipg_formula_current_label": "Active Method",
        "ipg_formula_reason_label": "Constitutional Basis",
        "ipg_formula_click_hint": "#instruction Click to choose an apportionment method#!",
        "ipg_formula_opt_badge_pr": "Proportional (PR)",
        "ipg_formula_opt_badge_maj": "Majoritarian",
        "ipg_formula_reason_manual": "Custom apportionment method currently in effect across Party Structure, Power Structure, and Political Alignment.",
        "ipg_formula_reason_1": "Adopts #v Hare / Hamilton#! proportionality in the absence of voting laws.",
        "ipg_formula_reason_2": "Adopts the continental #v D'Hondt#! method under #v $law_landed_voting$#! / #v $law_wealth_voting$#! / #v $law_census_voting$#!.",
        "ipg_formula_reason_3": "Adopts the balanced #v Sainte-Laguë#! method under #v $law_universal_suffrage$#! with #v $law_parliamentary_republic$#! or #v $law_council_republic$#!.",
        "ipg_formula_reason_4": "Adopts #v 5% Threshold PR#! under #v $law_universal_suffrage$#! to limit parliamentary fragmentation.",
        "ipg_formula_reason_5": "Adopts #v Plurality (FPTP)#! following #v $heritage_british$ / $language_anglophone$#! constituency traditions.",
        "ipg_formula_auto_desc": "Adapts the seat apportionment method automatically to your $lawgroup_distribution_of_power$ law and constitutional heritage.",
        "ipg_formula_auto_cond": "• #v No voting law#!: Hare / Hamilton\n• #v $heritage_british$ / $language_anglophone$#! (with voting law): Plurality (FPTP)\n• #v $law_universal_suffrage$#! (#v $law_parliamentary_republic$ / $law_council_republic$#!): Sainte-Laguë\n• #v $law_universal_suffrage$#! (other): 5% Threshold PR\n• #v $law_landed_voting$ / $law_wealth_voting$ / $law_census_voting$#! (other): D'Hondt",
        "ipg_formula_1_desc": "Largest-remainder method (Hare quota). Awards strictly proportional seats with leftover seats going to the highest fractional remainders.\nChamber size: #v standard (100%)#!.",
        "ipg_formula_1_cond": "Enacted under non-electoral systems (#v $law_autocracy$#!, #v $law_oligarchy$#!, #v $law_technocracy$#!, #v $law_single_party_state$#!).",
        "ipg_formula_2_desc": "Highest-average method using divisors 1, 2, 3, 4… Widely used across Europe; mildly favors larger parties and stable coalitions.\nChamber size: #v −5%#! (compact continental list).",
        "ipg_formula_2_cond": "Non-$language_anglophone$ nations under #v $law_landed_voting$#!, #v $law_wealth_voting$#!, or #v $law_census_voting$#!.",
        "ipg_formula_3_desc": "Highest-average method using odd divisors 1, 3, 5, 7… Standard in Scandinavia & Germany; unbiased between large and smaller parties.\nChamber size: #v +10%#! (leveling seats).",
        "ipg_formula_3_cond": "#v $law_universal_suffrage$#! combined with #v $law_parliamentary_republic$#! or #v $law_council_republic$#!.",
        "ipg_formula_4_desc": "Proportional representation with a #v 5%#! parliamentary hurdle. Factions below 5% win no seats, consolidating the chamber.\nChamber size: #v −15%#! (streamlined).",
        "ipg_formula_4_cond": "#v $law_universal_suffrage$#! under a #v $law_presidential_republic$#! or #v $law_monarchy$#!.",
        "ipg_formula_5_desc": "Single-member constituency winner's bonus rewarding leading parties with stronger governing majorities while preserving opposition representation.\nChamber size: #v +25%#! (local constituency MPs).",
        "ipg_formula_5_cond": "#v $heritage_british$#! or #v $language_anglophone$#! primary cultures with any voting law.",
        # --- v3.1 Rolling Election History & Foreign AI Viewer ---
        "ipg_hist_label": "Recent Elections",
        "ipg_inspect_foreign_btn": "Inspect Parliament",
        "ipg_inspect_foreign_tt": "Survey this country's current parliamentary composition across Party Structure, Power Structure, and Political Alignment.",
        "ipg_refresh_foreign_btn": "Refresh",
        "ipg_foreign_no_parties": "This country currently has no active political parties.",
        "ipg_tab_electoral_tt": "#title $ipg_view_electoral$#!\nDisplays lower-house seats apportioned from the last $concept_election$'s $concept_votes$ under the active apportionment method.\n#weak Displays Power Structure before an election is held.#!",
        "ipg_tab_foreign_electoral_tt": "#title $ipg_view_electoral$#!\nDisplays this country's lower-house seats across active $concept_party$ coalitions weighted by member $concept_clout$.\n#weak Displays Power Structure when no active parties exist.#!",
        "ipg_tab_power_tt": "#title $ipg_view_power$#!\nDisplays upper-house seats apportioned by each $concept_interest_group$'s $concept_clout$ under the active apportionment method.",
        "ipg_tab_alignment_tt": "#title $ipg_view_alignment$#!\nDisplays legislative seats apportioned by $concept_population$ support across each $concept_interest_group$, alongside $concept_politically_unaligned$ seats.",
        "ipg_collapse_tt": "Collapse the parliament chamber.",
        "ipg_expand_tt": "Expand the parliament chamber.",
    },
    "simp_chinese": {
        "ipg_colon": "：",
        "ipg_formula_prefix": "算法：",
        "ipg_layout_prefix": "格局：",
        "ipg_panel_title": "议会",
        "ipg_expand": "展开",
        "ipg_collapse": "折叠",
        "ipg_view_power": "权力结构",
        "ipg_view_alignment": "政治倾向",
        "ipg_view_electoral": "政党结构",
        "ipg_power_desc": "按$concept_interest_group$$concept_clout$划分。",
        "ipg_alignment_desc": "按$concept_interest_group$$concept_population$支持划分。",
        "ipg_electoral_desc": "按上届$concept_election$真实$concept_votes$划分。",
        "ipg_unaligned": "$concept_politically_unaligned$",
        "ipg_last_election": "上届选举",
        "ipg_next_election": "下届选举",
        "ipg_seats_unit": "席",
        "ipg_seats_col": "席位",
        "ipg_share_col": "占比",
        "ipg_votes_col": "得票率",
        "ipg_members_col": "成员",
        "ipg_gov_label": "执政",
        "ipg_opp_label": "在野",
        "ipg_total_label": "总计",
        "ipg_majority_tag": "#ipg_green 执政过半#!",
        "ipg_minority_tag": "#ipg_red 少数政府#!",
        "ipg_layout_auto": "自动",
        "ipg_layout_auto_tt": "按当前国家政体、法律与文化议会传统自动匹配席位结构。",
        "ipg_layout_hemicycle": "经典半圆",
        "ipg_layout_westminster": "威斯敏斯特",
        "ipg_layout_horseshoe": "马蹄形",
        "ipg_layout_assembly": "阶梯大会堂",
        "ipg_layout_bicameral": "两院分席",
        "ipg_layout_menu_title": "议会席位格局",
        "ipg_mode_auto_badge": "#ipg_green 依制匹配#!",
        "ipg_mode_manual_badge": "#title 自定义#!",
        "ipg_layout_current_label": "现行格局",
        "ipg_layout_reason_label": "宪政依据",
        "ipg_layout_cond_label": "适用条件",
        "ipg_layout_click_hint": "#instruction 点击更换议事厅格局#!",
        "ipg_layout_opt_badge_auto": "#ipg_green 依制匹配#!",
        "ipg_layout_opt_badge_preset": "议厅格局",
        "ipg_layout_opt_badge_dual": "两院并列",
        "ipg_layout_reason_manual": "当前采用自定义议事厅格局。点击可更换其他样式，或选回「自动」依本国宪政传统匹配。",
        "ipg_layout_reason_1": "现行 #v $law_council_republic$#! 或 #v $law_single_party_state$#! 政体采用阶梯大会堂格局。",
        "ipg_layout_reason_2": "承袭 #v $heritage_british$#! 或 #v $anglo_canadian$#! 议会传统（非 #v $law_autocracy$#!），采用威斯敏斯特对座式格局。",
        "ipg_layout_reason_3": "现行 #v $law_parliamentary_republic$#! 政体采用威斯敏斯特对座式格局。",
        "ipg_layout_reason_4": "承袭 #v $australian$#! 议会传统（非 #v $law_autocracy$#!），采用马蹄形议事厅格局。",
        "ipg_layout_reason_5": "现行 #v $law_monarchy$#! 立宪政体采用马蹄形议事厅格局。",
        "ipg_layout_reason_6": "现行 #v $law_presidential_republic$#! 政体实行两院分席议事格局。",
        "ipg_layout_reason_7": "当前$lawgroup_governance_principles$未形成特定议会传统，采用经典半圆议事厅格局。",
        "ipg_layout_auto_desc": "随$lawgroup_governance_principles$、$lawgroup_distribution_of_power$法律与历史传统确立最相称的议事厅格局。",
        "ipg_layout_auto_cond": "• #v $law_council_republic$ / $law_single_party_state$#!：阶梯大会堂\n• #v $heritage_british$ / $anglo_canadian$#!（非$law_autocracy$）或 #v $law_parliamentary_republic$#!：威斯敏斯特\n• #v $law_presidential_republic$#!（含投票法）：两院分席\n• #v $australian$#! 或其余 #v $law_monarchy$#!（含投票法）：马蹄形\n• #v $law_autocracy$ / $law_oligarchy$ / $law_technocracy$#! 等其余政体：经典半圆",
        "ipg_layout_hemicycle_desc": "源自法国波旁宫的欧陆经典扇形半圆议事厅，以中轴主席台为核心呈弧形排布席位。",
        "ipg_layout_hemicycle_cond": "适用于 #v $law_autocracy$#!、#v $law_oligarchy$#!、#v $law_technocracy$#! 及其他未形成特定议会传统的政体。",
        "ipg_layout_westminster_desc": "源自伦敦威斯敏斯特宫下议院的对座长椅格局，执政与在野阵营隔中道正面对峙辩论。",
        "ipg_layout_westminster_cond": "• 主流文化具备 #v $heritage_british$#! 传承（$british$、$scottish$、$welsh$、$irish$，不含$australian$）或 #v $anglo_canadian$#!（非 #v $law_autocracy$#!）\n• 或实行 #v $law_parliamentary_republic$#!",
        "ipg_layout_horseshoe_desc": "弧形 U 字马蹄议事厅，兼顾威斯敏斯特辩论传统与中立跨党派席位缓冲。",
        "ipg_layout_horseshoe_cond": "• 主流文化为 #v $australian$#!（非 #v $law_autocracy$#!）\n• 或其余实行 #v $law_monarchy$#! 且拥有投票法律的国家",
        "ipg_layout_assembly_desc": "阶梯矩形大会堂排布，多层横向坐席面向中央主席台，展现庄严的集体代表大会风貌。",
        "ipg_layout_assembly_cond": "实行 #v $law_council_republic$#! 或 #v $law_single_party_state$#!。",
        "ipg_layout_bicameral_desc": "两院并列议事厅：左侧上院呈现 #v 权力结构#!（$concept_clout$），右侧下院呈现 #v 政党结构#! 或 #v 政治倾向#!。",
        "ipg_layout_bicameral_cond": "实行 #v $law_presidential_republic$#! 且拥有任意投票法律。",
        "ipg_bicameral_panel_title": "两院制议会",
        "ipg_bicameral_upper": "@ipg_upper! [Country.GetCustom('ipg_upper_house_name')]",
        "ipg_bicameral_lower_electoral": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]",
        "ipg_bicameral_lower_alignment": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]",
        "ipg_toggle_info_btn": "信息",
        "ipg_toggle_info_tt": "显示或隐藏议事厅内的席位概览与选举日期。",
        "ipg_no_election_yet": "尚无选举记录。等待大选结束，或切换到「权力结构」查看。",
        "ipg_ruler_title": "$concept_ruler$",
        # --- v3.1 国别历史议院名称 ---
        "ipg_ch_default_lower": "下议院",
        "ipg_ch_default_upper": "上议院",
        "ipg_ch_default_monarchy_upper": "贵族院",
        "ipg_ch_senate": "参议院",
        "ipg_ch_usa_single": "国会",
        "ipg_ch_usa_lower": "众议院",
        "ipg_ch_gbr_single": "联合王国议会",
        "ipg_ch_gbr_lower": "下议院",
        "ipg_ch_gbr_upper": "上议院",
        "ipg_ch_fra_assembly": "国民议会",
        "ipg_ch_fra_monarchy_single": "法兰西议会",
        "ipg_ch_fra_monarchy_lower": "众议院",
        "ipg_ch_fra_monarchy_upper": "贵族院",
        "ipg_ch_ger_single": "德意志议会",
        "ipg_ch_ger_lower": "帝国议会",
        "ipg_ch_ger_upper": "联邦参议院",
        "ipg_ch_pru_single": "普鲁士议会",
        "ipg_ch_pru_lower": "众议院",
        "ipg_ch_pru_upper": "贵族院",
        "ipg_ch_aus_monarchy_single": "帝国议会",
        "ipg_ch_aus_rep_lower": "国民议会",
        "ipg_ch_aus_rep_upper": "联邦议院",
        "ipg_ch_rus_single": "俄国议会",
        "ipg_ch_rus_lower": "国家杜马",
        "ipg_ch_rus_upper": "国务会议",
        "ipg_ch_supreme_soviet": "最高苏维埃",
        "ipg_ch_soviet_lower": "联盟院",
        "ipg_ch_soviet_upper": "民族院",
        "ipg_ch_peoples_congress": "人民代表大会",
        "ipg_ch_council_upper": "最高苏维埃",
        "ipg_ch_jap_single": "帝国议会",
        "ipg_ch_jap_rep_single": "国会",
        "ipg_ch_jap_lower": "众议院",
        "ipg_ch_jap_upper": "贵族院",
        "ipg_ch_chi_monarchy_single": "朝堂议政",
        "ipg_ch_chi_monarchy_lower": "资政院",
        "ipg_ch_chi_monarchy_upper": "军机处",
        "ipg_ch_tur_monarchy_single": "奥斯曼议会",
        "ipg_ch_tur_rep_single": "大国民议会",
        "ipg_ch_tur_lower": "众议院",
        "ipg_ch_tur_upper": "贵族院",
        "ipg_ch_pol_lower": "瑟姆",
        "ipg_ch_spa_single": "西班牙议会",
        "ipg_ch_spa_lower": "众议院",
        "ipg_ch_ita_lower": "众议院",
        "ipg_ch_latam_single": "国会",
        "ipg_ch_bel_lower": "众议院",
        "ipg_ch_net_single": "荷兰国会",
        "ipg_ch_net_lower": "第二议院",
        "ipg_ch_net_upper": "第一议院",
        "ipg_ch_swe_single": "瑞典议会",
        "ipg_ch_nor_single": "挪威议会",
        "ipg_ch_nor_lower": "下议庭",
        "ipg_ch_nor_upper": "上议庭",
        # --- v3.1 比例代表制与席位算法 ---
        "ipg_formula_menu_title": "议席分配制度",
        "ipg_formula_auto": "依制自动",
        "ipg_formula_1": "哈密顿法",
        "ipg_formula_2": "洪特法",
        "ipg_formula_3": "圣拉格法",
        "ipg_formula_4": "5% 门槛制",
        "ipg_formula_5": "多数制加成",
        "ipg_formula_current_label": "现行制度",
        "ipg_formula_reason_label": "宪政依据",
        "ipg_formula_click_hint": "#instruction 点击调整议席分配制度#!",
        "ipg_formula_opt_badge_pr": "比例代表制",
        "ipg_formula_opt_badge_maj": "多数代表制",
        "ipg_formula_reason_manual": "当前采用自定义议席分配制度，统一适用于「政党结构」「权力结构」与「政治倾向」的席位与占比。",
        "ipg_formula_reason_1": "尚未实行投票法律，采用 #v 哈密顿法#! 按$concept_clout$比例分配席位。",
        "ipg_formula_reason_2": "实行 #v $law_landed_voting$#! / #v $law_wealth_voting$#! / #v $law_census_voting$#!，采用欧陆主流 #v 洪特法#!（温和偏向大党与稳固联盟）。",
        "ipg_formula_reason_3": "在 #v $law_parliamentary_republic$#! 或 #v $law_council_republic$#! 下实行 #v $law_universal_suffrage$#!，采用均衡的 #v 圣拉格法#!。",
        "ipg_formula_reason_4": "实行 #v $law_universal_suffrage$#!，采用 #v 5% 门槛制#! 以抑制议会过度碎片化。",
        "ipg_formula_reason_5": "承袭 #v $heritage_british$ / $language_anglophone$#! 单一选区传统且拥有投票法律，采用 #v 多数制加成#!。",
        "ipg_formula_auto_desc": "依本国$lawgroup_distribution_of_power$法律与宪政传统自动确立相称的议席分配制度。",
        "ipg_formula_auto_cond": "• #v 无投票法律#!：哈密顿法\n• #v $heritage_british$ / $language_anglophone$#!（含投票法）：多数制加成\n• #v $law_universal_suffrage$#!（#v $law_parliamentary_republic$ / $law_council_republic$#!）：圣拉格法\n• #v $law_universal_suffrage$#!（其余政体）：5% 门槛制\n• #v $law_landed_voting$ / $law_wealth_voting$ / $law_census_voting$#!（其余）：洪特法",
        "ipg_formula_1_desc": "经典最大余数法（黑尔基数）。严格按比例分配整数席，剩余席位依小数余数由大到小分配，大中小党最均衡。\n议会规模：#v 标准（100%）#!。",
        "ipg_formula_1_cond": "适用于未实行投票法律的政体（#v $law_autocracy$#!、#v $law_oligarchy$#!、#v $law_technocracy$#!、#v $law_single_party_state$#! 等）。",
        "ipg_formula_2_desc": "最高均数法（除数 1, 2, 3, 4…）。欧陆应用最广的比例代表制，温和有利于大党与稳固执政联盟。\n议会规模：#v −5%#!（欧陆紧凑名单制）。",
        "ipg_formula_2_cond": "非$language_anglophone$国家实行 #v $law_landed_voting$#!、#v $law_wealth_voting$#! 或 #v $law_census_voting$#!。",
        "ipg_formula_3_desc": "奇数除数最高均数法（除数 1, 3, 5, 7…）。北欧与德国议会通行标准，对中小$concept_party$几乎无偏置。\n议会规模：#v +10%#!（含平衡补偿议席）。",
        "ipg_formula_3_cond": "在 #v $law_parliamentary_republic$#! 或 #v $law_council_republic$#! 下实行 #v $law_universal_suffrage$#!。",
        "ipg_formula_4_desc": "附带 #v 5%#! 议会门槛的比例代表制。$concept_votes$或$concept_clout$低于 5% 的边缘$concept_party$/$concept_interest_group$不获席位，有效减少议会碎片化。\n议会规模：#v −15%#!（精简整合）。",
        "ipg_formula_4_cond": "#v $law_presidential_republic$#! 或 #v $law_monarchy$#! 下实行 #v $law_universal_suffrage$#!。",
        "ipg_formula_5_desc": "仿效英美单一选区制（FPTP），扩大领先$concept_party$的多数席位优势，同时保留在野党代表权。\n议会规模：#v +25%#!（地方选区直选扩席）。",
        "ipg_formula_5_cond": "主流文化属 #v $heritage_british$#! 或 #v $language_anglophone$#! 且拥有任意投票法律。",
        # --- v3.1 选举历史与外国议会 ---
        "ipg_hist_label": "近届席位趋势",
        "ipg_inspect_foreign_btn": "检视该国议会",
        "ipg_inspect_foreign_tt": "调阅该国当前的议会席位分布，包括政党结构、权力结构与政治倾向。",
        "ipg_refresh_foreign_btn": "刷新",
        "ipg_foreign_no_parties": "该国当前尚无活跃$concept_party$。",
        "ipg_tab_electoral_tt": "#title $ipg_view_electoral$#!\n按上届$concept_election$真实$concept_votes$与现行议席分配制度展示下院席位分布。\n#weak 尚未举行大选时自动按权力结构展示。#!",
        "ipg_tab_foreign_electoral_tt": "#title $ipg_view_electoral$#!\n按该国活跃$concept_party$成员的$concept_clout$占比展示下院席位分布。\n#weak 尚无活跃$concept_party$时自动按权力结构展示。#!",
        "ipg_tab_power_tt": "#title $ipg_view_power$#!\n按各$concept_interest_group$的$concept_clout$与现行议席分配制度展示上院席位分布。",
        "ipg_tab_alignment_tt": "#title $ipg_view_alignment$#!\n按全境$concept_population$对各$concept_interest_group$的支持比例分配席位，并保留$concept_politically_unaligned$席位。",
        "ipg_collapse_tt": "折叠议会席位图。",
        "ipg_expand_tt": "展开议会席位图。",
    },
}

from ipg_locales_extra import EXTRA_LOCALES  # noqa: E402
LOC_BASE.update(EXTRA_LOCALES)

# Dynamic composite templates shared across all 11 languages
DYNAMIC_TEMPLATES = {
    "ipg_gov_tag": "@in_government! #ipg_green $concept_in_government$#!",
    "ipg_opp_tag": "@in_opposition! #ipg_red $concept_in_opposition$#!",
    "ipg_total_seats_header": "#v [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]#! $ipg_seats_unit$",
    "ipg_power_coalition_badge": "#v [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#! / [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] $ipg_seats_unit$ ([Country.MakeScope.Var('ipg_power_gov_pct').GetValue|1]%)",
    "ipg_alignment_coalition_badge": "#v [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#! / [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] $ipg_seats_unit$ ([Country.MakeScope.Var('ipg_alignment_gov_pct').GetValue|1]%)",
    "ipg_electoral_coalition_badge": "#v [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#! / [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] $ipg_seats_unit$",
    "ipg_power_gov_kpi": "#ipg_green #bold [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#!#! ([Country.MakeScope.Var('ipg_power_gov_pct').GetValue|1]%)",
    "ipg_power_opp_kpi": "([Country.MakeScope.Var('ipg_power_opp_pct').GetValue|1]%) #ipg_red #bold [Country.MakeScope.Var('ipg_power_opp_seats').GetValue|0]#!#!",
    "ipg_alignment_gov_kpi": "#ipg_green #bold [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#!#! ([Country.MakeScope.Var('ipg_alignment_gov_pct').GetValue|1]%)",
    "ipg_alignment_unaligned_kpi": "#bold [Country.MakeScope.Var('ipg_alignment_unaligned_seats').GetValue|0]#! ([Country.MakeScope.Var('ipg_alignment_unaligned_share').GetValue|1]%)",
    "ipg_alignment_opp_kpi": "([Country.MakeScope.Var('ipg_alignment_opp_pct').GetValue|1]%) #ipg_red #bold [Country.MakeScope.Var('ipg_alignment_opp_seats').GetValue|0]#!#!",
    "ipg_electoral_gov_kpi": "#ipg_green #bold [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#!#! ([Country.MakeScope.Var('ipg_electoral_gov_pct').GetValue|1]%)",
    "ipg_electoral_opp_kpi": "([Country.MakeScope.Var('ipg_electoral_opp_pct').GetValue|1]%) #ipg_red #bold [Country.MakeScope.Var('ipg_electoral_opp_seats').GetValue|0]#!#!",
    "ipg_bicameral_power_compact": "@in_government! #ipg_green [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#!  @in_opposition! #ipg_red [Country.MakeScope.Var('ipg_power_opp_seats').GetValue|0]#!",
    "ipg_bicameral_electoral_compact": "@in_government! #ipg_green [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#!  @in_opposition! #ipg_red [Country.MakeScope.Var('ipg_electoral_opp_seats').GetValue|0]#!",
    "ipg_bicameral_alignment_compact": "@in_government! #ipg_green [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#!  @in_opposition! #ipg_red [Country.MakeScope.Var('ipg_alignment_opp_seats').GetValue|0]#!",
    "ipg_bicameral_upper_inline_maj": "@ipg_upper! [Country.GetCustom('ipg_upper_house_name')]  #ipg_green #bold [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#!#!/[Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]",
    "ipg_bicameral_upper_inline_min": "@ipg_upper! [Country.GetCustom('ipg_upper_house_name')]  #ipg_gold #bold [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#!#!/[Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]",
    "ipg_bicameral_lower_electoral_inline_maj": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]  #ipg_green #bold [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#!#!/[Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]",
    "ipg_bicameral_lower_electoral_inline_min": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]  #ipg_gold #bold [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#!#!/[Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]",
    "ipg_bicameral_lower_alignment_inline_maj": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]  #ipg_green #bold [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#!#!/[Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]",
    "ipg_bicameral_lower_alignment_inline_min": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]  #ipg_gold #bold [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#!#!/[Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]",
    "ipg_formula_btn_auto": "#weak $ipg_formula_prefix$#!$ipg_formula_auto$",
    "ipg_formula_btn_1": "#weak $ipg_formula_prefix$#!$ipg_formula_1$",
    "ipg_formula_btn_2": "#weak $ipg_formula_prefix$#!$ipg_formula_2$",
    "ipg_formula_btn_3": "#weak $ipg_formula_prefix$#!$ipg_formula_3$",
    "ipg_formula_btn_4": "#weak $ipg_formula_prefix$#!$ipg_formula_4$",
    "ipg_formula_btn_5": "#weak $ipg_formula_prefix$#!$ipg_formula_5$",
    "ipg_layout_btn_auto": "#weak $ipg_layout_prefix$#!$ipg_layout_auto$",
    "ipg_layout_btn_hemicycle": "#weak $ipg_layout_prefix$#!$ipg_layout_hemicycle$",
    "ipg_layout_btn_westminster": "#weak $ipg_layout_prefix$#!$ipg_layout_westminster$",
    "ipg_layout_btn_horseshoe": "#weak $ipg_layout_prefix$#!$ipg_layout_horseshoe$",
    "ipg_layout_btn_assembly": "#weak $ipg_layout_prefix$#!$ipg_layout_assembly$",
    "ipg_layout_btn_bicameral": "#weak $ipg_layout_prefix$#!$ipg_layout_bicameral$",
    "ipg_power_gov_sub": "#ipg_green #bold [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_power_opp_sub": "#ipg_red #bold [Country.MakeScope.Var('ipg_power_opp_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_alignment_gov_sub": "#ipg_green #bold [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_alignment_opp_sub": "#ipg_red #bold [Country.MakeScope.Var('ipg_alignment_opp_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_electoral_gov_sub": "#ipg_green #bold [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_electoral_opp_sub": "#ipg_red #bold [Country.MakeScope.Var('ipg_electoral_opp_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_power_seats_cell": "#v #bold [InterestGroup.MakeScope.Var('power_seats').GetValue|0]#!#!",
    "ipg_power_share_cell": "[InterestGroup.MakeScope.Var('power_share').GetValue|1]%",
    "ipg_ig_approval_cell": "[InterestGroup.GetApprovalRating] (#v [InterestGroup.GetApprovalValue|=+]#!)",
    "ipg_alignment_seats_cell": "#v #bold [InterestGroup.MakeScope.Var('alignment_seats').GetValue|0]#!#!",
    "ipg_alignment_share_cell": "[InterestGroup.MakeScope.Var('alignment_share').GetValue|1]%",
    "ipg_ig_pop_cell": "[InterestGroup.GetPopulation|D]",
    "ipg_unaligned_seats_cell": "#v #bold [Country.MakeScope.Var('ipg_alignment_unaligned_seats').GetValue|0]#!#!",
    "ipg_unaligned_share_cell": "[Country.MakeScope.Var('ipg_alignment_unaligned_share').GetValue|1]%",
    "ipg_electoral_seats_cell": "#v #bold [Party.MakeScope.Var('electoral_seats').GetValue|0]#!#!",
    "ipg_electoral_vote_cell": "[Party.MakeScope.Var('ipg_last_election_vote_share').GetValue|%1]",
    "ipg_election_dates_line": "$ipg_last_election$$ipg_colon$#v [Country.GetElection.GetLastElectionDateDesc]#!\n$ipg_next_election$$ipg_colon$#v [AccessPlayer.GetNextElectionDate]#!",
    "ipg_ruler_tooltip": "#title $ipg_ruler_title$#!\n[Country.GetRuler.GetFullName]\n[Country.GetRuler.GetInterestGroup.GetName]",
    "ipg_ruler_name": "[Country.GetRuler.GetFullName]",
    "ipg_ruler_ig_line": "[Country.GetRuler.GetInterestGroup.GetNameNoFormatting]",
    "ipg_single_chamber_title": "[Country.GetCustom('ipg_single_chamber_name')]",
    "ipg_lower_chamber_title": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')]",
    "ipg_upper_chamber_title": "@ipg_upper! [Country.GetCustom('ipg_upper_house_name')]",
    "ipg_tooltip_power_title": "[Country.GetCustom('ipg_upper_house_name')] · $ipg_view_power$",
    "ipg_tooltip_alignment_title": "[Country.GetCustom('ipg_single_chamber_name')] · $ipg_view_alignment$",
    "ipg_tooltip_electoral_title": "[Country.GetCustom('ipg_lower_house_name')] · $ipg_view_electoral$",
    "ipg_foreign_header_electoral": "@ipg_lower! [Country.GetCustom('ipg_lower_house_name')] — #v [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]#! $ipg_seats_unit$",
    "ipg_foreign_header_power": "@ipg_upper! [Country.GetCustom('ipg_upper_house_name')] — #v [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]#! $ipg_seats_unit$",
    "ipg_foreign_header_alignment": "[Country.GetCustom('ipg_single_chamber_name')] — #v [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]#! $ipg_seats_unit$",
    "ipg_seat_power_tt": "#title [InterestGroup.GetName]#!  [SelectLocalization(InterestGroup.IsInGovernment, 'ipg_gov_tag', 'ipg_opp_tag')]\n$ipg_seats_col$$ipg_colon$#v [InterestGroup.MakeScope.Var('power_seats').GetValue|0]#! / [InterestGroup.GetCountry.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] ([InterestGroup.MakeScope.Var('power_share').GetValue|1]%)\n[concept_clout]$ipg_colon$#v [InterestGroup.GetClout|%1]#! | [concept_approval]$ipg_colon$[InterestGroup.GetApprovalRating] (#v [InterestGroup.GetApprovalValue|=+]#!)[AddLocalizationIf(InterestGroup.MakeScope.Var('ipg_ph_2').IsSet, 'ipg_ph_block')]",
    "ipg_seat_alignment_tt": "#title [InterestGroup.GetName]#!  [SelectLocalization(InterestGroup.IsInGovernment, 'ipg_gov_tag', 'ipg_opp_tag')]\n$ipg_seats_col$$ipg_colon$#v [InterestGroup.MakeScope.Var('alignment_seats').GetValue|0]#! / [InterestGroup.GetCountry.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] ([InterestGroup.MakeScope.Var('alignment_share').GetValue|1]%)\n[concept_population]$ipg_colon$#v [InterestGroup.GetPopulation|D]#! ([InterestGroup.GetPopulationInCountryAsPercentage|%1])",
    "ipg_seat_unaligned_tt": "#title $ipg_unaligned$#!\n$ipg_seats_col$$ipg_colon$#v [Country.MakeScope.Var('ipg_alignment_unaligned_seats').GetValue|0]#! / [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] ([Country.MakeScope.Var('ipg_alignment_unaligned_share').GetValue|1]%)",
    "ipg_seat_electoral_tt": "#title [Party.GetName]#!  [SelectLocalization(Party.IsInGovernment, 'ipg_gov_tag', 'ipg_opp_tag')]\n$ipg_seats_col$$ipg_colon$#v [Party.MakeScope.Var('electoral_seats').GetValue|0]#! / [Party.MakeScope.Var('ipg_party_total_seats').GetValue|0]\n$ipg_votes_col$$ipg_colon$#v [Party.MakeScope.Var('ipg_last_election_vote_share').GetValue|%1]#!\n[Party.GetMembersSummary][AddLocalizationIf(Party.MakeScope.Var('ipg_eh_2').IsSet, 'ipg_eh_block')]",
    "ipg_eh_block": "\n$ipg_hist_label$$ipg_colon$[AddLocalizationIf(Party.MakeScope.Var('ipg_eh_5').IsSet, 'ipg_eh_5')][AddLocalizationIf(Party.MakeScope.Var('ipg_eh_4').IsSet, 'ipg_eh_4')][AddLocalizationIf(Party.MakeScope.Var('ipg_eh_3').IsSet, 'ipg_eh_3')][AddLocalizationIf(Party.MakeScope.Var('ipg_eh_2').IsSet, 'ipg_eh_2')]#v [Party.MakeScope.Var('ipg_eh_1').GetValue|0]#!",
    "ipg_eh_5": "[Party.MakeScope.Var('ipg_eh_5').GetValue|0] → ",
    "ipg_eh_4": "[Party.MakeScope.Var('ipg_eh_4').GetValue|0] → ",
    "ipg_eh_3": "[Party.MakeScope.Var('ipg_eh_3').GetValue|0] → ",
    "ipg_eh_2": "[Party.MakeScope.Var('ipg_eh_2').GetValue|0] → ",
    "ipg_ph_block": "\n$ipg_hist_label$$ipg_colon$[AddLocalizationIf(InterestGroup.MakeScope.Var('ipg_ph_5').IsSet, 'ipg_ph_5')][AddLocalizationIf(InterestGroup.MakeScope.Var('ipg_ph_4').IsSet, 'ipg_ph_4')][AddLocalizationIf(InterestGroup.MakeScope.Var('ipg_ph_3').IsSet, 'ipg_ph_3')][AddLocalizationIf(InterestGroup.MakeScope.Var('ipg_ph_2').IsSet, 'ipg_ph_2')]#v [InterestGroup.MakeScope.Var('ipg_ph_1').GetValue|0]#!",
    "ipg_ph_5": "[InterestGroup.MakeScope.Var('ipg_ph_5').GetValue|0] → ",
    "ipg_ph_4": "[InterestGroup.MakeScope.Var('ipg_ph_4').GetValue|0] → ",
    "ipg_ph_3": "[InterestGroup.MakeScope.Var('ipg_ph_3').GetValue|0] → ",
    "ipg_ph_2": "[InterestGroup.MakeScope.Var('ipg_ph_2').GetValue|0] → ",
}


def write_localizations(loc_root: Path) -> int:
    en = LOC_BASE["english"]
    count = 0
    for lang, overrides in LOC_BASE.items():
        merged = dict(en)
        merged.update(overrides)
        if "ipg_seats_col" not in overrides and "ipg_seats_unit" in overrides:
            merged["ipg_seats_col"] = overrides["ipg_seats_unit"]
        merged.update(DYNAMIC_TEMPLATES)

        lines = [f"l_{lang}:", ""]
        for k, v in merged.items():
            escaped = v.replace('"', '\\"').replace("\n", "\\n")
            lines.append(f'  {k}:0 "{escaped}"')
        out_path = loc_root / lang / f"ipg_l_{lang}.yml"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig", newline="\n")
        assert out_path.read_bytes().startswith(b"\xef\xbb\xbf"), f"Missing BOM: {out_path}"
        count += 1
    return count


# ---------------------------------------------------------------------------
# 5. Standalone Improved ParliamentGraph[1.15] sync
# ---------------------------------------------------------------------------


def sync_standalone() -> None:
    """Sync upgraded IPG files into sibling `Improved ParliamentGraph[1.15]`."""
    STANDALONE_DIR.mkdir(parents=True, exist_ok=True)

    # Restore thumbnail from Workshop copy if missing
    thumb_dst = STANDALONE_DIR / "thumbnail.png"
    thumb_src = WORKSHOP_IPG_DIR / "thumbnail.png"
    if not thumb_dst.exists() and thumb_src.exists():
        shutil.copy2(thumb_src, thumb_dst)

    # Write clean 1.15 metadata preserving Workshop ID 3721626337
    meta_dir = STANDALONE_DIR / ".metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "name": "Improved ParliamentGraph[1.15]",
        "id": "3721626337",
        "version": "3.1.0",
        "supported_game_version": "1.15.*",
        "short_description": (
            "v3.1 — Dynamic multi-chamber parliament visualizer (Hemicycle, "
            "Westminster, Horseshoe, Assembly Hall, Bicameral) with 5 switchable "
            "PR/electoral formulas (Hare, D'Hondt, Sainte-Laguë, 5% Threshold, FPTP), "
            "country-specific historical chamber names, 5-election seat trends, "
            "on-demand foreign AI parliament viewer, and Paradox-native tooltips."
        ),
        "tags": ["Graphics", "Interface"],
        "relationships": [],
        "game_custom_data": {"multiplayer_synchronized": True},
    }
    (meta_dir / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    # Sync all IPG core files from GORA UI+
    rel_files = [
        "common/customizable_localization/ipg_chamber_names.txt",
        "common/on_actions/ipg_on_actions.txt",
        "common/script_values/ipg_script_values.txt",
        "common/scripted_effects/ipg_seat_allocation.txt",
        "common/scripted_guis/ipg_election_capture.txt",
        "events/ipg_election_watch.txt",
        "gfx/interface/icons/ipg_white_circle.dds",
        "gfx/interface/icons/ipg_gov_halo.dds",
        "gfx/interface/icons/ipg_gov_halo_small.dds",
        "gfx/interface/icons/ipg_dot_overlay.dds",
        "gfx/interface/icons/ipg_dot_overlay_small.dds",
        "gfx/interface/icons/ipg_tab_active.dds",
        "gfx/interface/icons/ipg_ruler_plinth.dds",
        "gfx/interface/icons/ipg_ruler_crown.dds",
        "gfx/interface/icons/ipg_swatch_ring.dds",
        "gfx/interface/icons/ipg_chamber_upper.dds",
        "gfx/interface/icons/ipg_chamber_lower.dds",
        "gfx/interface/icons/ipg_floor_hemicycle.dds",
        "gfx/interface/icons/ipg_floor_westminster_50.dds",
        "gfx/interface/icons/ipg_floor_westminster_100.dds",
        "gfx/interface/icons/ipg_floor_westminster_200.dds",
        "gfx/interface/icons/ipg_floor_westminster_300.dds",
        "gfx/interface/icons/ipg_floor_horseshoe.dds",
        "gfx/interface/icons/ipg_floor_assembly_50.dds",
        "gfx/interface/icons/ipg_floor_assembly_100.dds",
        "gfx/interface/icons/ipg_floor_assembly_200.dds",
        "gfx/interface/icons/ipg_floor_assembly_300.dds",
        "gfx/interface/icons/ipg_floor_bicameral.dds",
        "gui/ipg_election_capture.gui",
        "gui/ipg_parliament_panel.gui",
        "gui/ipg_texticons.gui",
        "gui/ipg_textformatting.gui",
        "gui/ipg_layout_hemicycle.gui",
        "gui/ipg_layout_westminster.gui",
        "gui/ipg_layout_horseshoe.gui",
        "gui/ipg_layout_assembly.gui",
        "gui/ipg_layout_bicameral.gui",
        "gui/scripted_widgets/ipg_scripted_widgets.txt",
    ]
    for lang in LOC_BASE:
        rel_files.append(f"localization/{lang}/ipg_l_{lang}.yml")

    # Remove deprecated legacy files if present in standalone dir
    for obsolete in (
        "gui/ipg_seat_layout.gui",
        "gui/politics_panel_reform_government.gui",
        "gui/0_ipg_country_politics_panel.gui",
        "gfx/interface/icons/ipg_floor_westminster.dds",
        "gfx/interface/icons/ipg_floor_assembly.dds",
    ):
        p = STANDALONE_DIR / obsolete
        if p.exists():
            p.unlink()

    for rel in rel_files:
        src = MOD_DIR / rel
        dst = STANDALONE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Install clean partial-type override for government_details and lowest-priority
    # vanilla-path override `gui/country_politics_panel.gui` (yields automatically to
    # Improved Domestic Panel 3573737721 & any partial-type/later-loaded mod).
    src_gov = MOD_DIR / "gui" / "0_ipg_politics_panel_government_details.gui"
    dst_gov = STANDALONE_DIR / "gui" / "0_ipg_politics_panel_government_details.gui"
    shutil.copy2(src_gov, dst_gov)

    src_cpol = MOD_DIR / "gui" / "country_politics_panel.gui"
    dst_cpol = STANDALONE_DIR / "gui" / "country_politics_panel.gui"
    if src_cpol.exists():
        shutil.copy2(src_cpol, dst_cpol)

    print(f"[SYNC] Synced {len(rel_files) + 2} files to {STANDALONE_DIR}")


def sync_bpm25() -> None:
    """Sync full IPG v3.1 + BPM 2.5 (1.15.*) partial overrides into `BPM2.5-ParliamentGraph`."""
    bpm_dir = MOD_DIR.parent / "BPM2.5-ParliamentGraph"
    bpm_ws = Path(r"C:\Program Files (x86)\Steam\steamapps\workshop\content\529340\2932134122")
    if not bpm_ws.exists():
        raise FileNotFoundError(f"BPM Workshop 2932134122 not found: {bpm_ws}")
    bpm_dir.mkdir(parents=True, exist_ok=True)

    # Preserve existing thumbnail.png (or copy standalone thumbnail if missing)
    thumb_dst = bpm_dir / "thumbnail.png"
    if not thumb_dst.exists() and (STANDALONE_DIR / "thumbnail.png").exists():
        shutil.copy2(STANDALONE_DIR / "thumbnail.png", thumb_dst)

    # Write clean 1.15 metadata preserving Workshop ID 3697574736
    meta_dir = bpm_dir / ".metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "name": "BPM2.5-ParliamentGraph(1.15)",
        "id": "3697574736",
        "version": "3.1.0",
        "supported_game_version": "1.15.*",
        "short_description": (
            "Improved ParliamentGraph 3.1 tailored for Better Politics Mod 2.5 (1.15.*): "
            "5 chamber architectures, 5 live PR/electoral seat formulas, 20+ country "
            "historical chamber names, 5-election seat trends, and on-demand Foreign AI "
            "Parliament Viewer — full BPM 1.15 compatibility."
        ),
        "thumbnail": "thumbnail.png",
        "tags": ["Graphics", "Interface", "1.15"],
        "relationships": [
            {
                "rel_type": "dependency",
                "id": "2932134122",
                "display_name": "Better Politics Mod",
                "resource_type": "mod",
                "version": "*",
            }
        ],
        "game_custom_data": {"multiplayer_synchronized": True},
    }
    (meta_dir / "metadata.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    # Remove deprecated 1.13 legacy files
    for obsolete in (
        "gui/ipg_seat_layout.gui",
        "gui/ipg_electoral_seat_layout.gui",
        "gui/ipg_party_seat_layout.gui",
        "gui/ipg_power_seat_layout.gui",
        "gui/BPM_politics_panel_reform_government.gui",
        "gui/0_ipg_politics_panel_government_details.gui",
        "gui/0_ipg_country_politics_panel.gui",
        "gfx/interface/icons/ipg_floor_westminster.dds",
        "gfx/interface/icons/ipg_floor_assembly.dds",
    ):
        p = bpm_dir / obsolete
        if p.exists():
            p.unlink()

    # Sync all 31 core IPG files (excluding vanilla government/country_politics overrides)
    rel_files = [
        "common/customizable_localization/ipg_chamber_names.txt",
        "common/on_actions/ipg_on_actions.txt",
        "common/script_values/ipg_script_values.txt",
        "common/scripted_effects/ipg_seat_allocation.txt",
        "common/scripted_guis/ipg_election_capture.txt",
        "events/ipg_election_watch.txt",
        "gfx/interface/icons/ipg_white_circle.dds",
        "gfx/interface/icons/ipg_gov_halo.dds",
        "gfx/interface/icons/ipg_gov_halo_small.dds",
        "gfx/interface/icons/ipg_dot_overlay.dds",
        "gfx/interface/icons/ipg_dot_overlay_small.dds",
        "gfx/interface/icons/ipg_tab_active.dds",
        "gfx/interface/icons/ipg_ruler_plinth.dds",
        "gfx/interface/icons/ipg_ruler_crown.dds",
        "gfx/interface/icons/ipg_swatch_ring.dds",
        "gfx/interface/icons/ipg_chamber_upper.dds",
        "gfx/interface/icons/ipg_chamber_lower.dds",
        "gfx/interface/icons/ipg_floor_hemicycle.dds",
        "gfx/interface/icons/ipg_floor_westminster_50.dds",
        "gfx/interface/icons/ipg_floor_westminster_100.dds",
        "gfx/interface/icons/ipg_floor_westminster_200.dds",
        "gfx/interface/icons/ipg_floor_westminster_300.dds",
        "gfx/interface/icons/ipg_floor_horseshoe.dds",
        "gfx/interface/icons/ipg_floor_assembly_50.dds",
        "gfx/interface/icons/ipg_floor_assembly_100.dds",
        "gfx/interface/icons/ipg_floor_assembly_200.dds",
        "gfx/interface/icons/ipg_floor_assembly_300.dds",
        "gfx/interface/icons/ipg_floor_bicameral.dds",
        "gui/ipg_election_capture.gui",
        "gui/ipg_parliament_panel.gui",
        "gui/ipg_texticons.gui",
        "gui/ipg_textformatting.gui",
        "gui/ipg_layout_hemicycle.gui",
        "gui/ipg_layout_westminster.gui",
        "gui/ipg_layout_horseshoe.gui",
        "gui/ipg_layout_assembly.gui",
        "gui/ipg_layout_bicameral.gui",
        "gui/scripted_widgets/ipg_scripted_widgets.txt",
    ]
    for lang in LOC_BASE:
        rel_files.append(f"localization/{lang}/ipg_l_{lang}.yml")

    for rel in rel_files:
        src = MOD_DIR / rel
        dst = bpm_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Extract only the 2 BPM 1.15 types (`politics_panel_government_details` and
    # `country_panel_politics_content`) from live BPM Workshop and splice IPG hooks
    # into `gui/!ipg_bpm.gui` ('!' loads before BPM's 'B' regardless of load order).
    import sys as _sys
    if str(MOD_DIR / "tools") not in _sys.path:
        _sys.path.insert(0, str(MOD_DIR / "tools"))
    import compatch as _cp

    bpm_types = _cp.scan_gui_types(bpm_ws / "gui")
    assert "politics_panel_government_details" in bpm_types, "BPM missing politics_panel_government_details"
    assert "country_panel_politics_content" in bpm_types, "BPM missing country_panel_politics_content"

    gov_def = bpm_types["politics_panel_government_details"]
    cpol_def = bpm_types["country_panel_politics_content"]

    gov_body, gov_warns = _cp.apply_splice_ops(
        gov_def.raw_body,
        [{
            "action": "insert_after",
            "anchor": "in_opposition_icon.dds",
            "after_block_end": True,
            "enclosing_levels": 3,
            "gora_file": "0_ipg_politics_panel_government_details.gui",
            "fence": "IPG hemicycle",
            "idempotent_marker": "parliament_item = {}",
        }],
        MOD_DIR / "gui",
    )
    assert not gov_warns, f"BPM gov splice warnings: {gov_warns}"

    cpol_body, cpol_warns = _cp.apply_splice_ops(
        cpol_def.raw_body,
        [{
            "action": "insert_before",
            "anchor": "### MOVEMENTS",
            "inline": [
                "### IPG v3.1 — Foreign AI Parliament Viewer (ipg_foreign_parliament_section lives in gui/ipg_parliament_panel.gui)",
                "ipg_foreign_parliament_section = {}",
                "",
                "widget = { size = { 10 10 } }",
                "### /IPG v3.1",
            ],
            "idempotent_marker": "ipg_foreign_parliament_section",
        }],
        MOD_DIR / "gui",
    )
    assert not cpol_warns, f"BPM country_politics splice warnings: {cpol_warns}"

    # Preserve `@...` file constants referenced by both BPM types
    consts: dict[str, str] = {}
    for tdef in (gov_def, cpol_def):
        for k in sorted(tdef.referenced_constants):
            if k in tdef.file_constants and k not in consts:
                consts[k] = tdef.file_constants[k]
    const_lines = [f"{k} = {v}" for k, v in consts.items()]

    out_lines = [
        "# =============================================================================",
        "# BPM2.5-ParliamentGraph (1.15.*) — Partial-Type BPM Integration",
        "# Auto-generated by tools/build_ipg_assets.py --sync-bpm25",
        "# Overrides ONLY `politics_panel_government_details` and",
        "# `country_panel_politics_content` from Better Politics Mod 2.5 (1.15.*).",
        "# Prefix '!' guarantees higher GUI priority than BPM_'s 'B' regardless of load order.",
        "# =============================================================================",
        "",
        *const_lines,
        "",
        "types ipg_bpm_compat_types",
        "{",
        _cp.reindent_block(gov_body, "\t"),
        "",
        _cp.reindent_block(cpol_body, "\t"),
        "}",
        "",
    ]
    out_text = "\n".join(out_lines)
    syn = _cp.check_gui_syntax(out_text)
    assert syn.ok, f"BPM !ipg_bpm.gui syntax error: {syn}"
    out_gui = bpm_dir / "gui" / "!ipg_bpm.gui"
    out_gui.write_text(out_text, encoding="utf-8", newline="\n")
    print(f"[SYNC] Synced {len(rel_files) + 1} files (incl. gui/!ipg_bpm.gui) to {bpm_dir}")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Build IPG DDS, GUI layouts, and localizations.")
    ap.add_argument(
        "--sync-standalone",
        action="store_true",
        help="Also sync upgraded IPG into sibling Improved ParliamentGraph[1.15]",
    )
    ap.add_argument(
        "--sync-bpm25",
        action="store_true",
        help="Also sync upgraded IPG + BPM 2.5 (1.15.*) partial override into sibling BPM2.5-ParliamentGraph",
    )
    args = ap.parse_args()

    icons_dir = MOD_DIR / "gfx" / "interface" / "icons"
    for fname, fn in (
        ("ipg_white_circle.dds", build_white_circle_dds),
        ("ipg_gov_halo.dds", build_gov_halo_dds),
        ("ipg_gov_halo_small.dds", build_gov_halo_small_dds),
        ("ipg_dot_overlay.dds", build_dot_overlay_dds),
        ("ipg_dot_overlay_small.dds", build_dot_overlay_small_dds),
        ("ipg_tab_active.dds", build_tab_active_dds),
        ("ipg_ruler_plinth.dds", build_ruler_plinth_dds),
        ("ipg_ruler_crown.dds", build_ruler_crown_dds),
        ("ipg_swatch_ring.dds", build_swatch_ring_dds),
        ("ipg_chamber_upper.dds", build_chamber_upper_dds),
        ("ipg_chamber_lower.dds", build_chamber_lower_dds),
        ("ipg_floor_hemicycle.dds", build_floor_hemicycle_dds),
        ("ipg_floor_horseshoe.dds", build_floor_horseshoe_dds),
        ("ipg_floor_bicameral.dds", build_floor_bicameral_dds),
    ):
        p = icons_dir / fname
        fn(p)
        print(f"[DDS ] {p.relative_to(MOD_DIR)} ({p.stat().st_size} bytes)")

    for tier in (50, 100, 200, 300):
        pw = icons_dir / f"ipg_floor_westminster_{tier}.dds"
        build_floor_westminster_tier_dds(pw, tier)
        pa = icons_dir / f"ipg_floor_assembly_{tier}.dds"
        build_floor_assembly_tier_dds(pa, tier)
        print(f"[DDS ] {pw.relative_to(MOD_DIR)} & {pa.relative_to(MOD_DIR)}")

    # Remove obsolete single-tier floorplans if present
    for old_f in ("ipg_floor_westminster.dds", "ipg_floor_assembly.dds"):
        p_old = icons_dir / old_f
        if p_old.exists():
            p_old.unlink()

    gui_dir = MOD_DIR / "gui"
    ti_path = write_texticons_file(gui_dir)
    print(f"[GUI ] {ti_path.relative_to(MOD_DIR)} ({ti_path.stat().st_size} bytes)")
    tf_path = write_textformatting_file(gui_dir)
    print(f"[GUI ] {tf_path.relative_to(MOD_DIR)} ({tf_path.stat().st_size} bytes)")
    hemicycle_params = {
        50:  (74.0, 150.0, 4),
        100: (66.0, 154.0, 5),
        200: (62.0, 166.0, 7),
        300: (60.0, 174.0, 9),
    }
    layouts = [
        ("hemicycle", "Classic Hemicycle", lambda n, d: gen_hemicycle(
            n, cy=200.0,
            r_min=hemicycle_params[n][0],
            r_max=hemicycle_params[n][1],
            arcs=hemicycle_params[n][2],
            dot_size=d,
        )),
        ("westminster", "Westminster Opposing Benches", gen_westminster),
        ("horseshoe", "Commonwealth Horseshoe", gen_horseshoe),
        ("assembly", "Terraced Assembly Hall", gen_assembly),
    ]

    total_bytes = 0
    for slug, title, fn in layouts:
        p, icons = write_standard_layout_file(slug, title, fn, gui_dir)
        sz = p.stat().st_size
        total_bytes += sz
        print(f"[GUI ] {p.relative_to(MOD_DIR)} ({icons} icons, {sz / 1024:.1f} KB)")

    p_bi, icons_bi = write_bicameral_layout_file(gui_dir)
    total_bytes += p_bi.stat().st_size
    print(f"[GUI ] {p_bi.relative_to(MOD_DIR)} ({icons_bi} icons, {p_bi.stat().st_size / 1024:.1f} KB)")
    print(f"[INFO] Total modular layout GUI size: {total_bytes / (1024 * 1024):.2f} MB")

    # Remove superseded monolithic gui/ipg_seat_layout.gui
    legacy = gui_dir / "ipg_seat_layout.gui"
    if legacy.exists():
        legacy.unlink()
        print(f"[DEL ] Removed legacy {legacy.relative_to(MOD_DIR)}")

    n_locs = write_localizations(MOD_DIR / "localization")
    print(f"[LOC ] Generated {n_locs} UTF-8 BOM localization files")

    if args.sync_standalone:
        sync_standalone()
    if args.sync_bpm25:
        sync_bpm25()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
