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

TIER_SPECS = {
    100: {"dot": 13, "halo": 17},
    200: {"dot": 11, "halo": 15},
    300: {"dot": 10, "halo": 14},
}


# ---------------------------------------------------------------------------
# 1. Pure-Python 32x32 uncompressed BGRA DDS generator for gold coalition halo
# ---------------------------------------------------------------------------


def build_gov_halo_dds(out_path: Path) -> None:
    """Write a 32x32 RGBA DDS hollow gold ring (transparent center, crisp edge)."""
    w = h = 32
    cx = cy = (w - 1) / 2.0
    pixels = bytearray()

    for y in range(h):
        for x in range(w):
            r = math.hypot(x - cx, y - cy)
            # Transparent center (r <= 10.6) so tinted inner dot shows cleanly.
            # Smooth bright gold ring peaking at r ~ 12.8..14.0, fading out by 15.6.
            if r <= 10.2 or r >= 15.8:
                alpha = 0.0
            elif r < 11.6:
                alpha = (r - 10.2) / (11.6 - 10.2)
            elif r <= 14.0:
                alpha = 1.0
            else:
                alpha = (15.8 - r) / (15.8 - 14.0)

            # Soft smoothstep easing
            alpha = max(0.0, min(1.0, alpha))
            alpha = alpha * alpha * (3.0 - 2.0 * alpha)

            # Warm imperial gold (#F6D46C core, slightly deeper amber outer rim)
            t_outer = max(0.0, min(1.0, (r - 11.5) / 3.5))
            red = int(round(252 - 22 * t_outer))
            green = int(round(220 - 44 * t_outer))
            blue = int(round(115 - 50 * t_outer))
            a = int(round(240 * alpha))
            # DDS uncompressed A8R8G8B8 stores B, G, R, A in little-endian bytes
            pixels.extend((blue, green, red, a))

    # Standard 128-byte DDS header (DDSD_CAPS | HEIGHT | WIDTH | PIXELFORMAT | PITCH)
    flags = 0x1 | 0x2 | 0x4 | 0x8 | 0x1000
    pitch = w * 4
    pf_flags = 0x40 | 0x1  # DDPF_RGB | DDPF_ALPHAPIXELS
    header = struct.pack(
        "<4s7I11I8I5I",
        b"DDS ",
        124,      # dwSize
        flags,    # dwFlags
        h,        # dwHeight
        w,        # dwWidth
        pitch,    # dwPitchOrLinearSize
        0,        # dwDepth
        1,        # dwMipMapCount
        *([0] * 11),
        32,       # ddspf.dwSize
        pf_flags, # ddspf.dwFlags
        0,        # ddspf.dwFourCC
        32,       # ddspf.dwRGBBitCount
        0x00FF0000,  # R mask
        0x0000FF00,  # G mask
        0x000000FF,  # B mask
        0xFF000000,  # A mask
        0x1000,   # dwCaps (DDSCAPS_TEXTURE)
        0, 0, 0, 0,
    )
    assert len(header) == 128
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(header + bytes(pixels))


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
    cy: float = 212.0,
    r_min: float = 68.0,
    r_max: float = 184.0,
    arcs: int = 8,
    dot_size: int = 10,
) -> list[tuple[int, int]]:
    """Classic semicircular hemicycle sweeping LEFT -> RIGHT in radial wedges."""
    radii = [
        r_min + (r_max - r_min) * i / max(1, arcs - 1)
        for i in range(arcs)
    ]
    counts = largest_remainder(radii, n)
    pts: list[tuple[float, float, int, int]] = []
    half = dot_size / 2.0
    # Slight angle inset so bottom row stays clean above canvas edge
    a_start = math.radians(177.0)
    a_end = math.radians(3.0)
    for r, c in zip(radii, counts):
        for j in range(c):
            frac = 0.5 if c == 1 else j / (c - 1)
            theta = a_start + (a_end - a_start) * frac  # pi -> 0 (left -> right)
            x = int(round(cx + r * math.cos(theta) - half))
            y = int(round(cy - r * math.sin(theta) - half))
            pts.append((theta, r, x, y))
    # Sort descending by theta (left to right), inner to outer within same angle
    pts.sort(key=lambda p: (-p[0], p[1]))
    return [(x, y) for _, _, x, y in pts]


def gen_westminster(n: int, dot_size: int) -> list[tuple[int, int]]:
    """House of Commons opposing benches: Top = Gov, Bottom = Opp, Speaker on left."""
    specs = {
        100: (5, 10, 26, 17, 36),  # rows, cols, dx, dy, aisle_gap
        200: (5, 20, 17, 16, 36),
        300: (6, 25, 14, 14, 34),
    }
    rows, cols, dx, dy, aisle = specs[n]
    assert rows * cols * 2 == n

    total_w = (cols - 1) * dx
    # Shift slightly right of canvas center so Speaker/Ruler chair sits on left
    x0 = 326.0 - total_w / 2.0
    y_mid = 116.0
    half = dot_size / 2.0

    # Top bench (Government): left-to-right columns, frontbench (near aisle) -> backbench
    top_pts: list[tuple[int, int]] = []
    for col in range(cols):
        for row in range(rows):
            x = int(round(x0 + col * dx - half))
            y = int(round((y_mid - aisle / 2.0) - row * dy - half))
            top_pts.append((x, y))

    # Bottom bench (Opposition): right-to-left columns so Gov overflow > 50%
    # wraps seamlessly across the far right gangway while Opp leader faces Gov on left.
    bot_pts: list[tuple[int, int]] = []
    for col in range(cols - 1, -1, -1):
        for row in range(rows):
            x = int(round(x0 + col * dx - half))
            y = int(round((y_mid + aisle / 2.0) + row * dy - half))
            bot_pts.append((x, y))

    return top_pts + bot_pts


def gen_horseshoe(n: int, dot_size: int) -> list[tuple[int, int]]:
    """Commonwealth U-shaped horseshoe: Left bench -> Bottom Crossbench -> Right bench."""
    specs = {
        100: (4, 52.0, 106.0, 60.0),  # shells, r_min, r_max, leg_len
        200: (5, 48.0, 110.0, 66.0),
        300: (6, 44.0, 114.0, 70.0),
    }
    shells, r_min, r_max, leg = specs[n]
    radii = [r_min + (r_max - r_min) * i / max(1, shells - 1) for i in range(shells)]
    x_scale = 1.42  # Gentle horizontal stretch to use 600px width harmoniously
    cx = 300.0
    y_bend = 102.0  # Bottom apex reaches y_bend + r_max ~ 216 (inside 230)
    half = dot_size / 2.0

    # Approximate elliptical bottom arc length for each shell
    def shell_len(r: float) -> float:
        a, b = r * x_scale, r
        # Ramanujan half-ellipse circumference approximation
        h_val = ((a - b) ** 2) / ((a + b) ** 2)
        half_ell = 0.5 * math.pi * (a + b) * (1 + (3 * h_val) / (10 + math.sqrt(4 - 3 * h_val)))
        return 2.0 * leg + half_ell

    weights = [shell_len(r) for r in radii]
    counts = largest_remainder(weights, n)

    pts: list[tuple[float, float, int, int]] = []
    for r, c in zip(radii, counts):
        a, b = r * x_scale, r
        h_val = ((a - b) ** 2) / ((a + b) ** 2)
        arc_len = 0.5 * math.pi * (a + b) * (1 + (3 * h_val) / (10 + math.sqrt(4 - 3 * h_val)))
        total_len = 2.0 * leg + arc_len

        for j in range(c):
            t = 0.5 if c == 1 else j / (c - 1)
            s = t * total_len
            if s <= leg:
                # Left vertical wing going top -> bend
                px = cx - a
                py = (y_bend - leg) + s
            elif s <= leg + arc_len:
                # Bottom U-arc: phi goes pi -> 0 (left -> bottom -> right)
                u = (s - leg) / arc_len
                phi = math.pi * (1.0 - u)
                px = cx + a * math.cos(phi)
                py = y_bend + b * math.sin(phi)
            else:
                # Right vertical wing going bend -> top
                rem_s = s - (leg + arc_len)
                px = cx + a
                py = y_bend - rem_s

            pts.append((t, r, int(round(px - half)), int(round(py - half))))

    pts.sort(key=lambda p: (p[0], p[1]))
    return [(x, y) for _, _, x, y in pts]


def gen_assembly(n: int, dot_size: int) -> list[tuple[int, int]]:
    """Auditorium / People's Congress terraced hall facing top presidium with central aisle."""
    specs = {
        100: (5, 10, 18, 24, 26),  # rows, half_cols, dx, dy, aisle_gap
        200: (10, 10, 17, 15, 24),
        300: (10, 15, 13, 15, 22),
    }
    rows, half_cols, dx, dy, aisle = specs[n]
    assert rows * half_cols * 2 == n

    cx = 300.0
    y0 = 66.0 if n == 100 else 58.0
    half = dot_size / 2.0
    pts: list[tuple[int, int]] = []

    # Build left wing columns (outer -> aisle) then right wing columns (aisle -> outer)
    # so Government fills the left wing cleanly and Opposition fills the right wing.
    col_xs: list[float] = []
    for c in range(half_cols - 1, -1, -1):
        col_xs.append(cx - aisle / 2.0 - c * dx)
    for c in range(half_cols):
        col_xs.append(cx + aisle / 2.0 + c * dx)

    for px in col_xs:
        # Subtle amphitheater arch hugging the top presidium
        curve = -0.00035 * ((px - cx) ** 2)
        for r in range(rows):
            py = y0 + r * dy + curve
            pts.append((int(round(px - half)), int(round(py - half))))

    return pts


def validate_positions(name: str, pts: list[tuple[int, int]], expected: int, dot_size: int) -> None:
    assert len(pts) == expected, f"{name}: expected {expected} seats, got {len(pts)}"
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert min(xs) >= 8 and max(xs) + dot_size <= CANVAS_W - 8, (
        f"{name}: X out of bounds ({min(xs)}..{max(xs)+dot_size})"
    )
    assert min(ys) >= 8 and max(ys) + dot_size <= CANVAS_H - 6, (
        f"{name}: Y out of bounds ({min(ys)}..{max(ys)+dot_size})"
    )


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
        if gov_halo_expr:
            lines.append("\t\t\ticon = {")
            lines.append('\t\t\t\ttexture = "gfx/interface/icons/ipg_gov_halo.dds"')
            lines.append(f"\t\t\t\tsize = {{ {halo_size} {halo_size} }}")
            lines.append("\t\t\t\tparentanchor = center")
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

    for tier in (100, 200, 300):
        spec = TIER_SPECS[tier]
        dot, halo = spec["dot"], spec["halo"]
        pts = gen_fn(tier, dot)
        validate_positions(f"{slug}_{tier}", pts, tier, dot)

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
    """Left 100-dot Upper House (Power) + Right 200-dot Lower House (Electoral / Alignment)."""
    dot_u, halo_u = 8, 12
    dot_l, halo_l = 8, 12
    upper_pts = gen_hemicycle(
        100, cx=150.0, cy=206.0, r_min=40.0, r_max=104.0, arcs=5, dot_size=dot_u
    )
    lower_pts = gen_hemicycle(
        200, cx=444.0, cy=206.0, r_min=42.0, r_max=128.0, arcs=7, dot_size=dot_l
    )
    validate_positions("bicameral_upper_100", upper_pts, 100, dot_u)
    validate_positions("bicameral_lower_200", lower_pts, 200, dot_l)

    header = (
        "# =============================================================================\n"
        "# Improved ParliamentGraph - Bicameral Split Layout (Upper 100 + Lower 200)\n"
        "# Subsamples the active visual tier (100 / 200 / 300) proportionally with zero\n"
        "# extra script variables.\n"
        "# Auto-generated by tools/build_ipg_assets.py — do not hand-edit.\n"
        "# =============================================================================\n\n"
        "types politics_panel_types\n{\n"
    )
    blocks: list[str] = []
    total_icons = 0

    for tier in (100, 200, 300):
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
        "ipg_panel_title": "Parliament",
        "ipg_expand": "Expand",
        "ipg_collapse": "Collapse",
        "ipg_view_power": "Power Structure",
        "ipg_view_alignment": "Political Alignment",
        "ipg_view_electoral": "Party Structure",
        "ipg_power_desc": "Political strength of Interest Groups.",
        "ipg_alignment_desc": "Population alignment by Interest Group.",
        "ipg_electoral_desc": "Last election vote results.",
        "ipg_unaligned": "Politically Unaligned",
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
        "ipg_majority_tag": "#P Majority#!",
        "ipg_minority_tag": "#N Minority#!",
        "ipg_layout_auto": "Auto",
        "ipg_layout_auto_tt": "Automatically matches chamber architecture to your country's laws and parliamentary tradition.",
        "ipg_layout_hemicycle": "Hemicycle",
        "ipg_layout_westminster": "Westminster",
        "ipg_layout_horseshoe": "Horseshoe",
        "ipg_layout_assembly": "Assembly",
        "ipg_layout_bicameral": "Bicameral",
        "ipg_layout_menu_title": "Chamber Layout",
        "ipg_mode_auto_badge": "#P Auto#!",
        "ipg_mode_manual_badge": "#title Manual#!",
        "ipg_layout_current_label": "Active Layout",
        "ipg_layout_reason_label": "Why This Layout",
        "ipg_layout_cond_label": "Auto-Match Condition",
        "ipg_layout_click_hint": "#instruction Click to choose a chamber layout#!",
        "ipg_layout_opt_badge_auto": "#P Recommended#!",
        "ipg_layout_opt_badge_preset": "Chamber Preset",
        "ipg_layout_opt_badge_dual": "Dual Chamber",
        "ipg_layout_reason_manual": "Manually selected by the player. Click to pick another chamber or return to Auto.",
        "ipg_layout_reason_1": "Matched automatically because this country is a #v Council Republic#! or #v Single-Party State#!.",
        "ipg_layout_reason_2": "Matched automatically via #v British / Anglo-Canadian#! parliamentary tradition (non-autocratic).",
        "ipg_layout_reason_3": "Matched automatically because this country is a #v Parliamentary Republic#!.",
        "ipg_layout_reason_4": "Matched automatically via #v Australian#! parliamentary tradition (non-autocratic).",
        "ipg_layout_reason_5": "Matched automatically because this country is a #v Constitutional Monarchy#! with voting laws.",
        "ipg_layout_reason_6": "Matched automatically because this country is a #v Presidential Republic#! with voting laws (Upper & Lower Houses).",
        "ipg_layout_reason_7": "Default classic hemicycle matched for the current government structure.",
        "ipg_layout_auto_desc": "Dynamically adapts the chamber layout whenever your government laws or regime change.",
        "ipg_layout_auto_cond": "• #v Council / Single-Party#!: Assembly Hall\n• #v British Heritage / Parliamentary Republic#!: Westminster\n• #v Presidential Republic (Voting)#!: Bicameral\n• #v Australian / Constitutional Monarchy#!: Horseshoe\n• #v All other regimes#!: Hemicycle",
        "ipg_layout_hemicycle_desc": "Classic continental European fan-shaped amphitheater inspired by the Palais Bourbon, radiating outward from the presiding dais.",
        "ipg_layout_hemicycle_cond": "Default fallback for Autocracy, Oligarchy, Technocracy, and other regimes without a specialized chamber match.",
        "ipg_layout_westminster_desc": "Iconic opposing benches inspired by the Palace of Westminster, with Government and Opposition facing each other across the aisle.",
        "ipg_layout_westminster_cond": "• Primary culture with #v British heritage#! (excl. Australian) or #v Anglo-Canadian#! (non-autocratic)\n• Or enacted #v Parliamentary Republic#!",
        "ipg_layout_horseshoe_desc": "Curved U-shaped Commonwealth chamber blending Westminster debate traditions with cross-bench consensus seating.",
        "ipg_layout_horseshoe_cond": "• Primary culture is #v Australian#! (non-autocratic)\n• Or non-British #v Monarchy#! with any voting law",
        "ipg_layout_assembly_desc": "Stepped rectilinear congress hall with ranked seating rows facing the central presidium.",
        "ipg_layout_assembly_cond": "Enacted #v Council Republic#! or #v Single-Party State#!.",
        "ipg_layout_bicameral_desc": "Split dual-chamber display showing the Upper House (Power Structure) on the left and the Lower House (Election / Alignment) on the right.",
        "ipg_layout_bicameral_cond": "Enacted #v Presidential Republic#! with any voting law.",
        "ipg_bicameral_upper": "Upper House · Power",
        "ipg_bicameral_lower_electoral": "Lower House · Election",
        "ipg_bicameral_lower_alignment": "Lower House · Alignment",
        "ipg_toggle_info_btn": "Info",
        "ipg_toggle_info_tt": "Show or hide corner seat totals and election dates.",
        "ipg_no_election_yet": "No election results recorded yet. Hold an election or switch to Power Structure.",
        "ipg_ruler_title": "Head of State",
    },
    "simp_chinese": {
        "ipg_panel_title": "议会",
        "ipg_expand": "展开",
        "ipg_collapse": "折叠",
        "ipg_view_power": "权力结构",
        "ipg_view_alignment": "政治倾向",
        "ipg_view_electoral": "政党结构",
        "ipg_power_desc": "按利益集团政治影响力划分。",
        "ipg_alignment_desc": "按利益集团人口支持度划分。",
        "ipg_electoral_desc": "按上届选举真实得票划分。",
        "ipg_unaligned": "政治中立",
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
        "ipg_majority_tag": "#P 执政过半#!",
        "ipg_minority_tag": "#N 少数政府#!",
        "ipg_layout_auto": "自动",
        "ipg_layout_auto_tt": "按当前国家政体、法律与文化议会传统自动匹配席位结构。",
        "ipg_layout_hemicycle": "经典半圆",
        "ipg_layout_westminster": "威斯敏斯特",
        "ipg_layout_horseshoe": "马蹄形",
        "ipg_layout_assembly": "阶梯大会堂",
        "ipg_layout_bicameral": "两院分席",
        "ipg_layout_menu_title": "议会席位结构",
        "ipg_mode_auto_badge": "#P 自动匹配#!",
        "ipg_mode_manual_badge": "#title 手动指定#!",
        "ipg_layout_current_label": "当前结构",
        "ipg_layout_reason_label": "匹配原因",
        "ipg_layout_cond_label": "自动匹配条件",
        "ipg_layout_click_hint": "#instruction 点击切换其他席位结构#!",
        "ipg_layout_opt_badge_auto": "#P 默认推荐#!",
        "ipg_layout_opt_badge_preset": "席位样式",
        "ipg_layout_opt_badge_dual": "双院联动",
        "ipg_layout_reason_manual": "当前由玩家手动指定。点击按钮可切换其他议会形式，或选回「自动」按国情匹配。",
        "ipg_layout_reason_1": "当前实行 #v 委员会共和国#! 或 #v 一党制#!，自动匹配阶梯大会堂布局。",
        "ipg_layout_reason_2": "具备 #v 英国 / 英裔加拿大#! 议会文化传统（非君主专制），自动匹配威斯敏斯特对座式议会。",
        "ipg_layout_reason_3": "当前实行 #v 议会共和制#!，自动匹配威斯敏斯特对座式议会。",
        "ipg_layout_reason_4": "具备 #v 澳大利亚#! 议会文化传统（非君主专制），自动匹配马蹄形议事厅。",
        "ipg_layout_reason_5": "当前实行 #v 君主立宪制#!（君主制且含选举法），自动匹配马蹄形议事厅。",
        "ipg_layout_reason_6": "当前实行 #v 总统共和制#! 且拥有选举法，自动匹配参众两院分席布局。",
        "ipg_layout_reason_7": "当前政体未触发特殊议会传统，采用经典半圆议事厅作为默认布局。",
        "ipg_layout_auto_desc": "随政体、选举法律与国家文化传统动态切换最贴合历史的议会形态。",
        "ipg_layout_auto_cond": "• #v 委员会 / 一党制#!：阶梯大会堂\n• #v 英国系文化（非专制）或议会共和#!：威斯敏斯特\n• #v 总统共和制（含选举法）#!：两院分席\n• #v 澳大利亚或其余君主立宪制#!：马蹄形\n• #v 专制 / 寡头 / 技术官僚等其余政体#!：经典半圆",
        "ipg_layout_hemicycle_desc": "源自法国波旁宫的欧陆经典扇形半圆议事厅，以中轴主席台为核心呈弧形排布席位。",
        "ipg_layout_hemicycle_cond": "君主专制、寡头制、技术官僚及其他未触发特色样式的政体（默认兜底）。",
        "ipg_layout_westminster_desc": "源自伦敦威斯敏斯特宫下议院的对座长椅格局，执政与在野阵营隔中道正面对峙辩论。",
        "ipg_layout_westminster_cond": "• 主流文化属于 #v 不列颠系#!（英格兰、苏格兰、威尔士、爱尔兰）或 #v 英裔加拿大#!（非专制）\n• 或实行 #v 议会共和制#!",
        "ipg_layout_horseshoe_desc": "弧形 U 字马蹄议事厅，兼顾威斯敏斯特辩论传统与中立跨党派席位缓冲。",
        "ipg_layout_horseshoe_cond": "• 主流文化为 #v 澳大利亚#!（非专制）\n• 或其余实行 #v 君主立宪制#!（君主制 + 选举法）的国家",
        "ipg_layout_assembly_desc": "阶梯矩形大会堂排布，多层横向坐席面向中央主席台，展现庄严的集体代表大会风貌。",
        "ipg_layout_assembly_cond": "实行 #v 委员会共和国#! 或 #v 一党制#!。",
        "ipg_layout_bicameral_desc": "左右双院同屏展示：左侧上院呈现 #v 权力结构#!（势力），右侧下院呈现 #v 选举政党#! 或 #v 政治倾向#!。",
        "ipg_layout_bicameral_cond": "实行 #v 总统共和制#! 且拥有任意选举法。",
        "ipg_bicameral_upper": "上院 · 权力结构",
        "ipg_bicameral_lower_electoral": "下院 · 政党选举",
        "ipg_bicameral_lower_alignment": "下院 · 政治倾向",
        "ipg_toggle_info_btn": "信息",
        "ipg_toggle_info_tt": "显示或隐藏画布角落的席位统计与选举日期。",
        "ipg_no_election_yet": "尚无选举记录。等待大选结束，或切换到「权力结构」查看。",
        "ipg_ruler_title": "国家元首",
    },
    "braz_por": {
        "ipg_panel_title": "Parlamento",
        "ipg_expand": "Expandir",
        "ipg_collapse": "Recolher",
        "ipg_view_power": "Estrutura de Poder",
        "ipg_view_alignment": "Alinhamento Político",
        "ipg_view_electoral": "Estrutura Partidária",
        "ipg_power_desc": "Força política dos Grupos de Interesse.",
        "ipg_alignment_desc": "Alinhamento da população por Grupo de Interesse.",
        "ipg_electoral_desc": "Resultados da última eleição.",
        "ipg_unaligned": "Politicamente Não Alinhados",
        "ipg_last_election": "Última Eleição",
        "ipg_next_election": "Próxima Eleição",
        "ipg_seats_unit": "Assentos",
        "ipg_layout_auto": "Auto",
        "ipg_layout_hemicycle": "Hemiciclo",
        "ipg_layout_westminster": "Westminster",
        "ipg_layout_horseshoe": "Ferradura",
        "ipg_layout_assembly": "Assembleia",
        "ipg_layout_bicameral": "Bicameral",
        "ipg_ruler_title": "Chefe de Estado",
    },
    "french": {
        "ipg_panel_title": "Parlement",
        "ipg_expand": "Développer",
        "ipg_collapse": "Réduire",
        "ipg_view_power": "Structure du pouvoir",
        "ipg_view_alignment": "Alignement politique",
        "ipg_view_electoral": "Structure des partis",
        "ipg_power_desc": "Force politique des groupes d'intérêt.",
        "ipg_alignment_desc": "Alignement de la population par groupe d'intérêt.",
        "ipg_electoral_desc": "Résultats des dernières élections.",
        "ipg_unaligned": "Non-alignés politiquement",
        "ipg_last_election": "Dernières élections",
        "ipg_next_election": "Prochaines élections",
        "ipg_seats_unit": "Sièges",
        "ipg_gov_tag": "#P (Gouv.)#!",
        "ipg_opp_tag": "#N (Opp.)#!",
        "ipg_gov_label": "Gouv.",
        "ipg_opp_label": "Opp.",
        "ipg_total_label": "Total",
        "ipg_layout_auto": "Auto",
        "ipg_layout_hemicycle": "Hémicycle",
        "ipg_layout_westminster": "Westminster",
        "ipg_layout_horseshoe": "Fer à cheval",
        "ipg_layout_assembly": "Assemblée",
        "ipg_layout_bicameral": "Bicaméral",
        "ipg_ruler_title": "Chef d'État",
    },
    "german": {
        "ipg_panel_title": "Parlament",
        "ipg_expand": "Ausbauen",
        "ipg_collapse": "Einklappen",
        "ipg_view_power": "Machtstruktur",
        "ipg_view_alignment": "Politische Ausrichtung",
        "ipg_view_electoral": "Parteienstruktur",
        "ipg_power_desc": "Politische Stärke der Interessengruppen.",
        "ipg_alignment_desc": "Ausrichtung der Bevölkerung nach Interessengruppen.",
        "ipg_electoral_desc": "Ergebnisse der letzten Wahl.",
        "ipg_unaligned": "Politisch nicht gebunden",
        "ipg_last_election": "Letzte Wahl",
        "ipg_next_election": "Nächste Wahl",
        "ipg_seats_unit": "Sitze",
        "ipg_gov_tag": "#P (Reg.)#!",
        "ipg_opp_tag": "#N (Opp.)#!",
        "ipg_gov_label": "Reg.",
        "ipg_opp_label": "Opp.",
        "ipg_total_label": "Gesamt",
        "ipg_layout_auto": "Auto",
        "ipg_layout_hemicycle": "Halbkreis",
        "ipg_layout_westminster": "Westminster",
        "ipg_layout_horseshoe": "Hufeisen",
        "ipg_layout_assembly": "Saal",
        "ipg_layout_bicameral": "Zweikammer",
        "ipg_ruler_title": "Staatsoberhaupt",
    },
    "japanese": {
        "ipg_panel_title": "議会",
        "ipg_expand": "展開",
        "ipg_collapse": "折りたたむ",
        "ipg_view_power": "権力構造",
        "ipg_view_alignment": "政治的傾向",
        "ipg_view_electoral": "政党構造",
        "ipg_power_desc": "利益集団の政治的影響力。",
        "ipg_alignment_desc": "利益集団ごとの人口支持度。",
        "ipg_electoral_desc": "前回選挙の得票結果。",
        "ipg_unaligned": "政治的に無関心",
        "ipg_last_election": "前回の選挙",
        "ipg_next_election": "次回の選挙",
        "ipg_seats_unit": "議席",
        "ipg_gov_tag": "#P 【与党】#!",
        "ipg_opp_tag": "#N 【野党】#!",
        "ipg_gov_label": "与党",
        "ipg_opp_label": "野党",
        "ipg_total_label": "合計",
        "ipg_layout_auto": "自動",
        "ipg_layout_hemicycle": "半円",
        "ipg_layout_westminster": "対座",
        "ipg_layout_horseshoe": "馬蹄",
        "ipg_layout_assembly": "大会堂",
        "ipg_layout_bicameral": "二院制",
        "ipg_ruler_title": "国家元首",
    },
    "korean": {
        "ipg_panel_title": "의회",
        "ipg_expand": "펼치기",
        "ipg_collapse": "접기",
        "ipg_view_power": "권력 구조",
        "ipg_view_alignment": "정치 성향",
        "ipg_view_electoral": "정당 구조",
        "ipg_power_desc": "이해집단의 정치적 영향력.",
        "ipg_alignment_desc": "이해집단별 인구 지지율.",
        "ipg_electoral_desc": "지난 선거 득표 결과.",
        "ipg_unaligned": "정치적 무관심",
        "ipg_last_election": "지난 선거",
        "ipg_next_election": "다음 선거",
        "ipg_seats_unit": "의석",
        "ipg_gov_tag": "#P (여당)#!",
        "ipg_opp_tag": "#N (야당)#!",
        "ipg_gov_label": "여당",
        "ipg_opp_label": "야당",
        "ipg_total_label": "합계",
        "ipg_layout_auto": "자동",
        "ipg_layout_hemicycle": "반원형",
        "ipg_layout_westminster": "대좌형",
        "ipg_layout_horseshoe": "말굽형",
        "ipg_layout_assembly": "대회당",
        "ipg_layout_bicameral": "양원제",
        "ipg_ruler_title": "국가원수",
    },
    "polish": {
        "ipg_panel_title": "Parlament",
        "ipg_expand": "Rozwiń",
        "ipg_collapse": "Zwiń",
        "ipg_view_power": "Struktura władzy",
        "ipg_view_alignment": "Poglądy polityczne",
        "ipg_view_electoral": "Struktura partyjna",
        "ipg_power_desc": "Siła polityczna grup interesu.",
        "ipg_alignment_desc": "Poparcie populacji dla grup interesu.",
        "ipg_electoral_desc": "Wyniki ostatnich wyborów.",
        "ipg_unaligned": "Niezrzeszeni politycznie",
        "ipg_last_election": "Ostatnie wybory",
        "ipg_next_election": "Następne wybory",
        "ipg_seats_unit": "Mandaty",
        "ipg_layout_auto": "Auto",
        "ipg_layout_hemicycle": "Półkole",
        "ipg_layout_westminster": "Westminster",
        "ipg_layout_horseshoe": "Podkowa",
        "ipg_layout_assembly": "Zgromadzenie",
        "ipg_layout_bicameral": "Dwuizbowy",
        "ipg_ruler_title": "Głowa państwa",
    },
    "russian": {
        "ipg_panel_title": "Парламент",
        "ipg_expand": "Развернуть",
        "ipg_collapse": "Свернуть",
        "ipg_view_power": "Структура власти",
        "ipg_view_alignment": "Политические взгляды",
        "ipg_view_electoral": "Партийная структура",
        "ipg_power_desc": "Политическое влияние групп интересов.",
        "ipg_alignment_desc": "Поддержка групп интересов населением.",
        "ipg_electoral_desc": "Результаты последних выборов.",
        "ipg_unaligned": "Аполитичные",
        "ipg_last_election": "Прошлые выборы",
        "ipg_next_election": "След. выборы",
        "ipg_seats_unit": "мест",
        "ipg_gov_tag": "#P (Прав.)#!",
        "ipg_opp_tag": "#N (Опп.)#!",
        "ipg_gov_label": "Прав.",
        "ipg_opp_label": "Опп.",
        "ipg_total_label": "Всего",
        "ipg_layout_auto": "Авто",
        "ipg_layout_hemicycle": "Полукруг",
        "ipg_layout_westminster": "Вестминстер",
        "ipg_layout_horseshoe": "Подкова",
        "ipg_layout_assembly": "Ассамблея",
        "ipg_layout_bicameral": "Двухпалатный",
        "ipg_ruler_title": "Глава государства",
    },
    "spanish": {
        "ipg_panel_title": "Parlamento",
        "ipg_expand": "Expandir",
        "ipg_collapse": "Contraer",
        "ipg_view_power": "Estructura de poder",
        "ipg_view_alignment": "Alineación política",
        "ipg_view_electoral": "Estructura de partidos",
        "ipg_power_desc": "Fuerza política de los grupos de interés.",
        "ipg_alignment_desc": "Alineación de la población por grupo de interés.",
        "ipg_electoral_desc": "Resultados de las últimas elecciones.",
        "ipg_unaligned": "No alineados políticamente",
        "ipg_last_election": "Últimas elecciones",
        "ipg_next_election": "Próximas elecciones",
        "ipg_seats_unit": "Escaños",
        "ipg_layout_auto": "Auto",
        "ipg_layout_hemicycle": "Hemiciclo",
        "ipg_layout_westminster": "Westminster",
        "ipg_layout_horseshoe": "Herradura",
        "ipg_layout_assembly": "Asamblea",
        "ipg_layout_bicameral": "Bicameral",
        "ipg_ruler_title": "Jefe de Estado",
    },
    "turkish": {
        "ipg_panel_title": "Parlamento",
        "ipg_expand": "Genişlet",
        "ipg_collapse": "Daralt",
        "ipg_view_power": "Güç Yapısı",
        "ipg_view_alignment": "Siyasi Eğilim",
        "ipg_view_electoral": "Parti Yapısı",
        "ipg_power_desc": "Çıkar Gruplarının siyasi gücü.",
        "ipg_alignment_desc": "Çıkar Gruplarına göre nüfus eğilimi.",
        "ipg_electoral_desc": "Son seçim oy sonuçları.",
        "ipg_unaligned": "Siyasi Olarak Tarafsız",
        "ipg_last_election": "Son Seçim",
        "ipg_next_election": "Sonraki Seçim",
        "ipg_seats_unit": "Koltuk",
        "ipg_gov_tag": "#P (Hük.)#!",
        "ipg_opp_tag": "#N (Muh.)#!",
        "ipg_gov_label": "Hük.",
        "ipg_opp_label": "Muh.",
        "ipg_total_label": "Toplam",
        "ipg_layout_auto": "Oto",
        "ipg_layout_hemicycle": "Yarım Daire",
        "ipg_layout_westminster": "Westminster",
        "ipg_layout_horseshoe": "At Nalı",
        "ipg_layout_assembly": "Meclis",
        "ipg_layout_bicameral": "Çift Meclis",
        "ipg_ruler_title": "Devlet Başkanı",
    },
}

# Dynamic composite templates shared across all 11 languages
DYNAMIC_TEMPLATES = {
    "ipg_gov_tag": "@in_government! #P $concept_in_government$#!",
    "ipg_opp_tag": "@in_opposition! #N $concept_in_opposition$#!",
    "ipg_total_seats_header": "#v [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]#! $ipg_seats_unit$",
    "ipg_power_coalition_badge": "#v [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#! / [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] $ipg_seats_unit$ ([Country.MakeScope.Var('ipg_power_gov_pct').GetValue|1]%)",
    "ipg_alignment_coalition_badge": "#v [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#! / [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] $ipg_seats_unit$ ([Country.MakeScope.Var('ipg_alignment_gov_pct').GetValue|1]%)",
    "ipg_electoral_coalition_badge": "#v [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#! / [Country.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] $ipg_seats_unit$",
    "ipg_power_gov_kpi": "#P #bold [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#!#! ([Country.MakeScope.Var('ipg_power_gov_pct').GetValue|1]%)",
    "ipg_power_opp_kpi": "([Country.MakeScope.Var('ipg_power_opp_pct').GetValue|1]%) #N #bold [Country.MakeScope.Var('ipg_power_opp_seats').GetValue|0]#!#!",
    "ipg_alignment_gov_kpi": "#P #bold [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#!#! ([Country.MakeScope.Var('ipg_alignment_gov_pct').GetValue|1]%)",
    "ipg_alignment_unaligned_kpi": "#bold [Country.MakeScope.Var('ipg_alignment_unaligned_seats').GetValue|0]#! ([Country.MakeScope.Var('ipg_alignment_unaligned_share').GetValue|1]%)",
    "ipg_alignment_opp_kpi": "([Country.MakeScope.Var('ipg_alignment_opp_pct').GetValue|1]%) #N #bold [Country.MakeScope.Var('ipg_alignment_opp_seats').GetValue|0]#!#!",
    "ipg_electoral_gov_kpi": "#P #bold [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#!#! ([Country.MakeScope.Var('ipg_electoral_gov_pct').GetValue|1]%)",
    "ipg_electoral_opp_kpi": "([Country.MakeScope.Var('ipg_electoral_opp_pct').GetValue|1]%) #N #bold [Country.MakeScope.Var('ipg_electoral_opp_seats').GetValue|0]#!#!",
    "ipg_bicameral_power_compact": "@in_government! #P [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#!  @in_opposition! #N [Country.MakeScope.Var('ipg_power_opp_seats').GetValue|0]#!",
    "ipg_bicameral_electoral_compact": "@in_government! #P [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#!  @in_opposition! #N [Country.MakeScope.Var('ipg_electoral_opp_seats').GetValue|0]#!",
    "ipg_bicameral_alignment_compact": "@in_government! #P [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#!  @in_opposition! #N [Country.MakeScope.Var('ipg_alignment_opp_seats').GetValue|0]#!",
    "ipg_power_gov_sub": "#P #bold [Country.MakeScope.Var('ipg_power_gov_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_power_opp_sub": "#N #bold [Country.MakeScope.Var('ipg_power_opp_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_alignment_gov_sub": "#P #bold [Country.MakeScope.Var('ipg_alignment_gov_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_alignment_opp_sub": "#N #bold [Country.MakeScope.Var('ipg_alignment_opp_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_electoral_gov_sub": "#P #bold [Country.MakeScope.Var('ipg_electoral_gov_seats').GetValue|0]#!#! $ipg_seats_unit$",
    "ipg_electoral_opp_sub": "#N #bold [Country.MakeScope.Var('ipg_electoral_opp_seats').GetValue|0]#!#! $ipg_seats_unit$",
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
    "ipg_election_dates_line": "$ipg_last_election$: #v [Country.GetElection.GetLastElectionDateDesc]#!\n$ipg_next_election$: #v [AccessPlayer.GetNextElectionDate]#!",
    "ipg_ruler_tooltip": "#title $ipg_ruler_title$#!\n[Country.GetRuler.GetFullName]\n[Country.GetRuler.GetInterestGroup.GetName]",
    "ipg_seat_power_tt": "#title [InterestGroup.GetName]#!  [SelectLocalization(InterestGroup.IsInGovernment, 'ipg_gov_tag', 'ipg_opp_tag')]\n$ipg_seats_col$: #v [InterestGroup.MakeScope.Var('power_seats').GetValue|0]#! / [GetPlayer.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] ([InterestGroup.MakeScope.Var('power_share').GetValue|1]%)\n[concept_clout]: #v [InterestGroup.GetClout|%1]#! | [concept_approval]: [InterestGroup.GetApprovalRating] (#v [InterestGroup.GetApprovalValue|=+]#!)",
    "ipg_seat_alignment_tt": "#title [InterestGroup.GetName]#!  [SelectLocalization(InterestGroup.IsInGovernment, 'ipg_gov_tag', 'ipg_opp_tag')]\n$ipg_seats_col$: #v [InterestGroup.MakeScope.Var('alignment_seats').GetValue|0]#! / [GetPlayer.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] ([InterestGroup.MakeScope.Var('alignment_share').GetValue|1]%)\n[concept_population]: #v [InterestGroup.GetPopulation|D]#! ([InterestGroup.GetPopulationInCountryAsPercentage|%1])",
    "ipg_seat_unaligned_tt": "#title $ipg_unaligned$#!\n$ipg_seats_col$: #v [GetPlayer.MakeScope.Var('ipg_alignment_unaligned_seats').GetValue|0]#! / [GetPlayer.MakeScope.Var('ipg_real_total_seats_val').GetValue|0] ([GetPlayer.MakeScope.Var('ipg_alignment_unaligned_share').GetValue|1]%)",
    "ipg_seat_electoral_tt": "#title [Party.GetName]#!  [SelectLocalization(Party.IsInGovernment, 'ipg_gov_tag', 'ipg_opp_tag')]\n$ipg_seats_col$: #v [Party.MakeScope.Var('electoral_seats').GetValue|0]#! / [GetPlayer.MakeScope.Var('ipg_real_total_seats_val').GetValue|0]\n$ipg_votes_col$: #v [Party.MakeScope.Var('ipg_last_election_vote_share').GetValue|%1]#!\n[Party.GetMembersSummary]",
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
        "version": "3.0.0",
        "supported_game_version": "1.15.*",
        "short_description": (
            "v3.0 Major Overhaul — Dynamic multi-chamber parliament visualizer "
            "(Hemicycle, Westminster, Horseshoe, Assembly Hall, Bicameral) with "
            "culture/law auto-matching, dynamic 50–650 seat counts, Hamilton "
            "apportionment, coalition halos, per-seat hover tooltips, and "
            "Paradox-native stacked-bar tooltips."
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
        "common/on_actions/ipg_on_actions.txt",
        "common/script_values/ipg_script_values.txt",
        "common/scripted_effects/ipg_seat_allocation.txt",
        "common/scripted_guis/ipg_election_capture.txt",
        "events/ipg_election_watch.txt",
        "gfx/interface/icons/ipg_white_circle.dds",
        "gfx/interface/icons/ipg_gov_halo.dds",
        "gui/ipg_election_capture.gui",
        "gui/ipg_parliament_panel.gui",
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
    ):
        p = STANDALONE_DIR / obsolete
        if p.exists():
            p.unlink()

    for rel in rel_files:
        src = MOD_DIR / rel
        dst = STANDALONE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # Install clean partial-type override for politics_panel_government_details
    src_gov = MOD_DIR / "gui" / "0_gora_politics_panel_government_details.gui"
    dst_gov = STANDALONE_DIR / "gui" / "0_ipg_politics_panel_government_details.gui"
    shutil.copy2(src_gov, dst_gov)

    print(f"[SYNC] Synced {len(rel_files) + 1} files to {STANDALONE_DIR}")


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
    args = ap.parse_args()

    halo_path = MOD_DIR / "gfx" / "interface" / "icons" / "ipg_gov_halo.dds"
    build_gov_halo_dds(halo_path)
    print(f"[DDS ] {halo_path.relative_to(MOD_DIR)} ({halo_path.stat().st_size} bytes)")

    gui_dir = MOD_DIR / "gui"
    layouts = [
        ("hemicycle", "Classic Hemicycle", lambda n, d: gen_hemicycle(
            n, r_min=(78.0 if n == 100 else (70.0 if n == 200 else 66.0)),
            r_max=(164.0 if n == 100 else (178.0 if n == 200 else 184.0)),
            arcs=(5 if n == 100 else (7 if n == 200 else 8)),
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
