"""GORA UI+ Overhaul Compatibility Toolkit.

Zero-dependency Python 3 CLI for scanning, building, and auditing Victoria 3
GUI compatibility patches between GORA UI+ and major overhaul mods.

Subcommands:
  scan <target>         Compare any overhaul mod (recipe key, Workshop ID, or
                        directory path) against Vanilla + GORA UI+.
  build <target>        Generate a minimal partial-type-override compatch mod
                        (`!gora_<slug>.gui` + `.metadata/metadata.json`) using
                        declarative fence splicing and/or indent-normalized
                        3-way merge.
  audit                 Inspect local and Steam Workshop GORA compat patches
                        for syntax errors, outdated game versions, sort-order
                        traps, missing conflicts, and (with --check-steam)
                        upstream Steam update drift.
  list-fences           List all extractable `### GORA UI+` / `### Smart Treaties`
                        fenced delta blocks across GORA UI+'s `gui/*.gui`.

Examples:
  python tools/compatch.py scan bpm
  python tools/compatch.py scan 3843134572
  python tools/compatch.py build bpm --out "../GORA UI+ x BPM Compat"
  python tools/compatch.py audit --check-steam
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

MOD_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_RECIPES_PATH = TOOLS_DIR / "compatch_recipes.json"
DEFAULT_VANILLA_DIR = Path(
    os.environ.get(
        "VIC3_GAME_DIR",
        r"C:\Program Files (x86)\Steam\steamapps\common\Victoria 3\game",
    )
)
DEFAULT_WORKSHOP_DIR = Path(
    os.environ.get(
        "VIC3_WORKSHOP_DIR",
        r"C:\Program Files (x86)\Steam\steamapps\workshop\content\529340",
    )
)
LOCAL_MODS_DIR = MOD_DIR.parent

TYPE_HEADER_RE = re.compile(
    r"^[ \t]*type\s+(\w+)\s*=\s*(\w+)\s*\{", re.MULTILINE
)
CONST_DEF_RE = re.compile(r"^[ \t]*(@\w+)\s*=\s*([^\r\n#]+)", re.MULTILINE)
CONST_REF_RE = re.compile(r"(?<![A-Za-z0-9_])(@[A-Za-z_]\w*)(?!!)")
CONFLICT_MARKER_RE = re.compile(r"^[ \t]*(?:<{7}|={7}|>{7}|\|{7})(?:\s|$)", re.MULTILINE)

FENCE_START_RE = re.compile(
    r"^[ \t]*###\s*(?:GORA UI\+|Smart Treaties)(?:\s|$|[—\-:])(.*)$"
)
FENCE_END_RE = re.compile(
    r"^[ \t]*###\s*(?:/GORA UI\+|GORA UI\+\s*(?:[—\-]+\s*end\b|end\b)|Smart Treaties\s*[—\-]+\s*end\b|/Smart Treaties)",
    re.IGNORECASE,
)


@dataclass
class GuiTypeDef:
    name: str
    base_type: str
    rel_path: str
    line_no: int
    raw_body: str
    normalized_body: str
    file_constants: dict[str, str] = field(default_factory=dict)
    referenced_constants: set[str] = field(default_factory=set)

    @property
    def filename(self) -> str:
        return Path(self.rel_path).name


@dataclass
class SyntaxReport:
    ok: bool
    final_depth: int
    min_depth: int
    conflict_markers: int
    stray_lines: list[tuple[int, str]]


@dataclass
class FenceBlock:
    file: str
    label: str
    start_line: int
    end_line: int
    text: str


# ---------------------------------------------------------------------------
# Jomini GUI parsing, normalization, and syntax checks
# ---------------------------------------------------------------------------


def read_text_clean(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace").replace(
        "\r\n", "\n"
    )


def strip_comments_and_ws(text: str) -> str:
    """Normalize GUI text for semantic comparison (ignores comments & spacing)."""
    out: list[str] = []
    in_q = False
    in_c = False
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if in_c:
            if ch == "\n":
                in_c = False
                out.append(" ")
        elif in_q:
            out.append(ch)
            if ch == '"' and (i == 0 or text[i - 1] != "\\"):
                in_q = False
        else:
            if ch == "#":
                in_c = True
            elif ch == '"':
                in_q = True
                out.append(ch)
            else:
                out.append(ch)
        i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()


def find_matching_brace(text: str, open_idx: int) -> int:
    """Return index of matching '}' for '{' at open_idx, respecting quotes & '#'."""
    depth = 0
    in_q = False
    in_c = False
    n = len(text)
    i = open_idx
    while i < n:
        ch = text[i]
        if in_c:
            if ch == "\n":
                in_c = False
        elif in_q:
            if ch == '"' and text[i - 1] != "\\":
                in_q = False
        else:
            if ch == "#":
                in_c = True
            elif ch == '"':
                in_q = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def parse_file_constants(text: str) -> dict[str, str]:
    consts: dict[str, str] = {}
    for m in CONST_DEF_RE.finditer(text):
        consts[m.group(1)] = m.group(2).strip()
    return consts


def scan_gui_types(gui_root: Path) -> dict[str, GuiTypeDef]:
    """Scan all .gui files in Victoria 3 first-load-wins VFS filename order.

    In Victoria 3, files across gui/ and subfolders load alphabetically by
    filename; the first definition of a given `type` name wins.
    """
    result: dict[str, GuiTypeDef] = {}
    if not gui_root.is_dir():
        return result

    all_files = sorted(
        gui_root.rglob("*.gui"),
        key=lambda p: (p.name.lower(), str(p.relative_to(gui_root)).lower()),
    )
    for path in all_files:
        text = read_text_clean(path)
        consts = parse_file_constants(text)
        rel = str(path.relative_to(gui_root)).replace("\\", "/")
        for m in TYPE_HEADER_RE.finditer(text):
            tname, base = m.group(1), m.group(2)
            if tname in result:
                continue  # First-load-wins
            open_idx = m.end() - 1
            close_idx = find_matching_brace(text, open_idx)
            if close_idx < 0:
                continue
            raw = text[m.start() : close_idx + 1]
            line_no = text[: m.start()].count("\n") + 1
            refs = set(CONST_REF_RE.findall(raw))
            result[tname] = GuiTypeDef(
                name=tname,
                base_type=base,
                rel_path=rel,
                line_no=line_no,
                raw_body=raw,
                normalized_body=strip_comments_and_ws(raw),
                file_constants=consts,
                referenced_constants=refs,
            )
    return result


def check_gui_syntax(text: str) -> SyntaxReport:
    """Quote-aware brace balance, conflict-marker, and top-level token check."""
    depth = 0
    min_depth = 0
    in_q = False
    stray_lines: list[tuple[int, str]] = []
    conflicts = len(CONFLICT_MARKER_RE.findall(text))

    top_ok_re = re.compile(
        r"^(?:@\w+\s*=|types\s+\w+\s*(?:\{|$)|type\s+\w+\s*=|template\s*(?:=\s*)?\w+\s*(?:\{|$)|"
        r"texticon\s*\{|textformatting\s*\{|local_template\s*(?:=\s*)?\w+|"
        r"\w+\s*=\s*\{|\}|\{)"
    )

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if (
            depth == 0
            and not in_q
            and stripped
            and not stripped.startswith("#")
            and not CONFLICT_MARKER_RE.match(line)
            and not top_ok_re.match(stripped)
        ):
            stray_lines.append((lineno, stripped[:100]))

        i = 0
        n = len(line)
        while i < n:
            ch = line[i]
            if in_q:
                if ch == '"' and (i == 0 or line[i - 1] != "\\"):
                    in_q = False
            else:
                if ch == "#":
                    break
                if ch == '"':
                    in_q = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth < min_depth:
                        min_depth = depth
            i += 1

    ok = (
        depth == 0
        and min_depth == 0
        and conflicts == 0
        and len(stray_lines) == 0
    )
    return SyntaxReport(
        ok=ok,
        final_depth=depth,
        min_depth=min_depth,
        conflict_markers=conflicts,
        stray_lines=stray_lines,
    )


def extract_fences(path: Path) -> list[FenceBlock]:
    """Extract all paired `### GORA UI+` / `### Smart Treaties` fenced blocks."""
    lines = read_text_clean(path).splitlines()
    blocks: list[FenceBlock] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if FENCE_START_RE.match(line) and not FENCE_END_RE.match(line):
            start = i
            label = line.strip()
            j = i + 1
            while j < n:
                if FENCE_END_RE.match(lines[j]):
                    blocks.append(
                        FenceBlock(
                            file=path.name,
                            label=label,
                            start_line=start + 1,
                            end_line=j + 1,
                            text="\n".join(lines[start : j + 1]),
                        )
                    )
                    i = j
                    break
                # Stop if another unrelated fence starts without closing previous
                if FENCE_START_RE.match(lines[j]) and not FENCE_END_RE.match(lines[j]):
                    break
                j += 1
        i += 1
    return blocks


def load_placeholder_types(gora_gui: Path) -> set[str]:
    """Return custom types provided by GORA UI+'s `z_*compat_placeholders.gui`."""
    placeholders: set[str] = set()
    for p in sorted(gora_gui.glob("z_*placeholder*.gui")):
        for m in TYPE_HEADER_RE.finditer(read_text_clean(p)):
            placeholders.add(m.group(1))
    return placeholders


# ---------------------------------------------------------------------------
# Metadata & target resolution
# ---------------------------------------------------------------------------


def load_metadata(mod_path: Path) -> dict[str, Any]:
    mp = mod_path / ".metadata" / "metadata.json"
    if not mp.is_file():
        return {}
    try:
        return json.loads(mp.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def load_recipes(path: Path = DEFAULT_RECIPES_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {"recipes": {}}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_target(
    target: str,
    recipes: dict[str, Any],
    workshop_dir: Path,
    source_override: str | None = None,
) -> tuple[str, Path | None, dict[str, Any] | None]:
    """Resolve a recipe key, Workshop ID, or path into (slug, mod_path, recipe)."""
    recipe = recipes.get("recipes", {}).get(target.lower())

    if source_override:
        p = Path(source_override)
        if not p.is_dir() and source_override.isdigit():
            p = workshop_dir / source_override
        slug = target.lower() if recipe else re.sub(r"[^a-z0-9_]+", "_", p.name.lower()).strip("_")
        return slug, (p if p.is_dir() else None), recipe

    if recipe:
        for wid in recipe.get("workshop_ids", []):
            cand = workshop_dir / str(wid)
            if cand.is_dir() and (cand / "gui").is_dir():
                return target.lower(), cand, recipe
        return target.lower(), None, recipe

    cand_path = Path(target)
    if cand_path.is_dir():
        meta = load_metadata(cand_path)
        raw_slug = meta.get("name") or cand_path.name
        slug = re.sub(r"[^a-z0-9]+", "_", raw_slug.lower()).strip("_")[:24] or "mod"
        return slug, cand_path, None

    if target.isdigit():
        cand = workshop_dir / target
        if cand.is_dir():
            meta = load_metadata(cand)
            raw_slug = meta.get("name") or f"ws_{target}"
            slug = re.sub(r"[^a-z0-9]+", "_", raw_slug.lower()).strip("_")[:24] or f"ws_{target}"
            return slug, cand, None

    return target.lower(), None, None


# ---------------------------------------------------------------------------
# Indent normalization, 3-way merge, and declarative splicing
# ---------------------------------------------------------------------------


def normalize_indent(text: str) -> str:
    """Convert leading 4-space runs to tabs so whitespace style doesn't conflict."""
    out: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^([ \t]+)(.*)$", line)
        if m:
            lead = m.group(1).replace("    ", "\t")
            out.append(lead + m.group(2))
        else:
            out.append(line)
    return "\n".join(out)


def reindent_block(block: str, target_indent: str) -> str:
    """Re-indent a multi-line snippet so its minimum non-empty indent == target_indent."""
    lines = block.splitlines()
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return block

    def lead_tabs(s: str) -> int:
        expanded = re.match(r"^[ \t]*", s).group(0).replace("    ", "\t")
        return len(expanded)

    min_tabs = min(lead_tabs(l) for l in non_empty)
    res: list[str] = []
    for l in lines:
        if not l.strip():
            res.append("")
            continue
        norm = re.match(r"^[ \t]*", l).group(0).replace("    ", "\t")
        extra = "\t" * max(0, len(norm) - min_tabs)
        res.append(target_indent + extra + l.lstrip(" \t"))
    return "\n".join(res)


def three_way_merge(
    base_body: str, ours_body: str, theirs_body: str, type_name: str
) -> tuple[str, int]:
    """Run indent-normalized `git merge-file --diff3`. Returns (merged, conflicts)."""
    nb = normalize_indent(base_body) + "\n"
    no = normalize_indent(ours_body) + "\n"
    nt = normalize_indent(theirs_body) + "\n"
    with tempfile.TemporaryDirectory() as td:
        pb = Path(td) / "vanilla"
        po = Path(td) / "gora"
        pt = Path(td) / "overhaul"
        pb.write_text(nb, encoding="utf-8")
        po.write_text(no, encoding="utf-8")
        pt.write_text(nt, encoding="utf-8")
        proc = subprocess.run(
            [
                "git",
                "merge-file",
                "-p",
                "--diff3",
                "-L",
                f"GORA UI+ ({type_name})",
                "-L",
                f"Vanilla ({type_name})",
                "-L",
                f"Overhaul ({type_name})",
                str(po),
                str(pb),
                str(pt),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.stdout.rstrip("\n"), max(0, proc.returncode)


def resolve_snippet(op: dict[str, Any], gora_gui: Path) -> str:
    if "inline" in op:
        val = op["inline"]
        return "\n".join(val) if isinstance(val, list) else str(val)
    if "gora_file" in op and "fence" in op:
        src = gora_gui / op["gora_file"]
        blocks = extract_fences(src)
        needle = op["fence"].lower()
        matches = [b for b in blocks if needle in b.label.lower()]
        if not matches:
            raise ValueError(
                f"Fence '{op['fence']}' not found in {op['gora_file']} "
                f"(available: {[b.label for b in blocks]})"
            )
        return matches[0].text
    raise ValueError(f"Splice op missing 'inline' or ('gora_file'+'fence'): {op}")


def find_enclosing_block_end(lines: list[str], line_idx: int, levels: int = 1) -> int:
    """Starting at line_idx (0-based), scan forward to close `levels` open '{'."""
    depth = 0
    in_q = False
    for idx in range(line_idx, len(lines)):
        line = lines[idx]
        i = 0
        while i < len(line):
            ch = line[i]
            if in_q:
                if ch == '"' and (i == 0 or line[i - 1] != "\\"):
                    in_q = False
            else:
                if ch == "#":
                    break
                if ch == '"':
                    in_q = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == -levels:
                        return idx
            i += 1
    return -1


def apply_splice_ops(
    body: str, ops: list[dict[str, Any]], gora_gui: Path
) -> tuple[str, list[str]]:
    """Apply declarative splice operations to a type body. Returns (new_body, warnings)."""
    lines = normalize_indent(body).splitlines()
    warnings: list[str] = []

    for idx_op, op in enumerate(ops, 1):
        action = op.get("action", "insert_after")
        anchor = op["anchor"]
        use_regex = bool(op.get("regex", False))
        occurrence = int(op.get("occurrence", 1))
        snippet = resolve_snippet(op, gora_gui)

        # Idempotency guard
        marker = op.get("idempotent_marker")
        if not marker:
            for sl in snippet.splitlines():
                if sl.strip() and not sl.strip().startswith("#"):
                    marker = sl.strip()
                    break
        if marker and any(marker in l for l in lines):
            continue

        # Locate anchor line
        hit_idx = -1
        seen = 0
        for i, l in enumerate(lines):
            matched = bool(re.search(anchor, l)) if use_regex else (anchor in l)
            if matched:
                seen += 1
                if seen == occurrence:
                    hit_idx = i
                    break

        if hit_idx < 0:
            warnings.append(
                f"Op #{idx_op} ({action}): anchor '{anchor}' (occ={occurrence}) NOT FOUND"
            )
            continue

        if op.get("after_block_end"):
            levels = int(op.get("enclosing_levels", 1))
            end_idx = find_enclosing_block_end(lines, hit_idx, levels=levels)
            if end_idx < 0:
                warnings.append(
                    f"Op #{idx_op}: could not find closing brace (levels={levels}) after anchor '{anchor}'"
                )
                continue
            target_indent = re.match(r"^[ \t]*", lines[end_idx]).group(0)
            ins = reindent_block(snippet, target_indent).splitlines()
            lines[end_idx + 1 : end_idx + 1] = [""] + ins
        elif action == "insert_before":
            target_indent = re.match(r"^[ \t]*", lines[hit_idx]).group(0)
            ins = reindent_block(snippet, target_indent).splitlines()
            lines[hit_idx:hit_idx] = ins + [""]
        elif action == "insert_after":
            target_indent = re.match(r"^[ \t]*", lines[hit_idx]).group(0)
            ins = reindent_block(snippet, target_indent).splitlines()
            lines[hit_idx + 1 : hit_idx + 1] = [""] + ins
        else:
            warnings.append(f"Op #{idx_op}: unsupported action '{action}'")

    return "\n".join(lines), warnings


# ---------------------------------------------------------------------------
# Conflict analysis (shared by scan, build, and audit)
# ---------------------------------------------------------------------------


@dataclass
class ScanResult:
    target_name: str
    target_path: Path
    true_conflicts: list[tuple[str, GuiTypeDef, GuiTypeDef]]
    soft_compatible: list[tuple[str, GuiTypeDef, GuiTypeDef, str]]
    harmless_overlaps: list[tuple[str, GuiTypeDef, GuiTypeDef]]
    sort_hazards: list[tuple[str, str, str]]
    common_overlaps: list[str]


def analyze_mod(
    target_path: Path,
    van_types: dict[str, GuiTypeDef],
    gora_types: dict[str, GuiTypeDef],
    placeholder_types: set[str],
    recipe: dict[str, Any] | None = None,
) -> ScanResult:
    meta = load_metadata(target_path)
    target_name = meta.get("name") or target_path.name
    ov_types = scan_gui_types(target_path / "gui")

    recipe_types = (recipe or {}).get("types", {})
    true_conflicts: list[tuple[str, GuiTypeDef, GuiTypeDef]] = []
    soft_compatible: list[tuple[str, GuiTypeDef, GuiTypeDef, str]] = []
    harmless: list[tuple[str, GuiTypeDef, GuiTypeDef]] = []
    sort_hazards: list[tuple[str, str, str]] = []

    for tname in sorted(set(gora_types) & set(ov_types)):
        if tname in placeholder_types:
            # Built-in `z_*_compat_placeholders.gui` types are intentionally
            # designed to yield to the overhaul's real definition.
            continue

        gt = gora_types[tname]
        ot = ov_types[tname]
        vt = van_types.get(tname)

        # Check filename sort-order hazard (overhaul loads before GORA)
        if ot.filename.lower() < gt.filename.lower():
            sort_hazards.append((tname, ot.rel_path, gt.rel_path))

        # Check explicit soft_compat in recipe
        cfg = recipe_types.get(tname, {})
        if cfg.get("strategy") == "soft_compat":
            soft_compatible.append((tname, gt, ot, cfg.get("reason", "built-in hook")))
            continue

        # Check automatic placeholder detection: if overhaul added a widget from
        # z_*_compat_placeholders.gui and GORA already invokes that same widget
        if vt and ot.normalized_body == vt.normalized_body:
            harmless.append((tname, gt, ot))
            continue

        matched_ph = [
            ph for ph in placeholder_types if ph in ot.raw_body and ph in gt.raw_body
        ]
        if matched_ph and cfg.get("strategy") is None and vt:
            # Verify whether the placeholder hook is the overhaul's intentional hook
            soft_compatible.append(
                (tname, gt, ot, f"built-in placeholder ({', '.join(sorted(matched_ph))})")
            )
            continue

        true_conflicts.append((tname, gt, ot))

    # Check common/ & data_binding/ exact file collisions
    common_overlaps: list[str] = []
    for sub in ("common", "data_binding", "events"):
        g_sub = MOD_DIR / sub
        o_sub = target_path / sub
        if not (g_sub.is_dir() and o_sub.is_dir()):
            continue
        g_files = {str(p.relative_to(MOD_DIR)).replace("\\", "/") for p in g_sub.rglob("*.txt")}
        o_files = {str(p.relative_to(target_path)).replace("\\", "/") for p in o_sub.rglob("*.txt")}
        common_overlaps.extend(sorted(g_files & o_files))

    return ScanResult(
        target_name=target_name,
        target_path=target_path,
        true_conflicts=true_conflicts,
        soft_compatible=soft_compatible,
        harmless_overlaps=harmless,
        sort_hazards=sort_hazards,
        common_overlaps=common_overlaps,
    )


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> int:
    recipes = load_recipes(Path(args.recipes))
    slug, target_path, recipe = resolve_target(
        args.target, recipes, Path(args.workshop), args.source
    )
    if not target_path:
        print(f"[ERROR] Target '{args.target}' not found locally in {args.workshop}.")
        if recipe:
            print(f"        Configured workshop_ids: {recipe.get('workshop_ids')}")
            print("        Subscribe on Steam or pass --source <local_mod_dir>.")
        return 1

    van_types = scan_gui_types(Path(args.vanilla) / "gui")
    gora_types = scan_gui_types(MOD_DIR / "gui")
    placeholders = load_placeholder_types(MOD_DIR / "gui")

    res = analyze_mod(target_path, van_types, gora_types, placeholders, recipe)

    if args.markdown:
        print(f"## Compatibility Scan: {res.target_name}")
        print(f"- Path: `{res.target_path}`")
        print(
            f"- True GUI conflicts: **{len(res.true_conflicts)}** | "
            f"Built-in soft compat: **{len(res.soft_compatible)}** | "
            f"Harmless vanilla copies: **{len(res.harmless_overlaps)}**\n"
        )
        if res.true_conflicts:
            print("| Type | GORA UI+ File | Overhaul File |")
            print("| --- | --- | --- |")
            for t, gt, ot in res.true_conflicts:
                print(f"| `{t}` | `{gt.rel_path}` | `{ot.rel_path}` |")
        return 0

    print(f"=== Compatibility Scan: {res.target_name} ({slug}) ===")
    print(f"Target path : {res.target_path}")
    print(f"Vanilla gui : {Path(args.vanilla) / 'gui'} ({len(van_types)} types)")
    print(f"GORA UI+    : {MOD_DIR / 'gui'} ({len(gora_types)} types)")
    print(f"\nTRUE GUI CONFLICTS ({len(res.true_conflicts)}):")
    if not res.true_conflicts:
        print("  (none! Fully compatible without a GUI compatch)")
    for t, gt, ot in res.true_conflicts:
        print(f"  - {t:42s} | GORA: {gt.rel_path:40s} | OV: {ot.rel_path}")

    if res.soft_compatible:
        print(f"\nBUILT-IN SOFT COMPATIBLE ({len(res.soft_compatible)}) — no compatch needed:")
        for t, gt, ot, reason in res.soft_compatible:
            print(f"  - {t:42s} | {reason}")

    print(f"\nHARMLESS OVERLAPS ({len(res.harmless_overlaps)}) — overhaul copied vanilla unchanged:")
    if res.harmless_overlaps:
        names = [x[0] for x in res.harmless_overlaps]
        print("  " + ", ".join(names[:15]) + (f" ... (+{len(names)-15} more)" if len(names) > 15 else ""))
    else:
        print("  (none)")

    if res.sort_hazards:
        print(f"\n[WARN] FILENAME SORT-ORDER HAZARDS ({len(res.sort_hazards)} — overhaul loads BEFORE GORA):")
        for t, of, gf in res.sort_hazards:
            print(f"  - {t}: overhaul '{of}' < GORA '{gf}'")

    if res.common_overlaps:
        print(f"\n[WARN] NON-GUI FILE OVERLAPS ({len(res.common_overlaps)}):")
        for f in res.common_overlaps:
            print(f"  - {f}")

    return 0


def cmd_build(args: argparse.Namespace) -> int:
    recipes = load_recipes(Path(args.recipes))
    slug, target_path, recipe = resolve_target(
        args.target, recipes, Path(args.workshop), args.source
    )
    if not target_path:
        print(f"[ERROR] Target '{args.target}' not found locally.")
        return 1

    van_types = scan_gui_types(Path(args.vanilla) / "gui")
    gora_types = scan_gui_types(MOD_DIR / "gui")
    placeholders = load_placeholder_types(MOD_DIR / "gui")
    res = analyze_mod(target_path, van_types, gora_types, placeholders, recipe)

    gora_meta = load_metadata(MOD_DIR)
    ov_meta = load_metadata(target_path)
    game_ver = gora_meta.get("supported_game_version", "1.15.*")
    recipe_types = (recipe or {}).get("types", {})

    if not res.true_conflicts:
        print(f"[OK] {res.target_name}: 0 true GUI conflicts! No compatch file needed.")
        return 0

    out_dir = (
        Path(args.out)
        if args.out
        else (MOD_DIR / "build" / f"compat_{slug}")
    )
    gui_out = out_dir / "gui"
    meta_out = out_dir / ".metadata"
    gui_out.mkdir(parents=True, exist_ok=True)
    meta_out.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for old_gui in gui_out.glob("*.gui"):
            old_gui.unlink()

    prefix = args.prefix
    out_gui_name = f"{prefix}gora_{slug}.gui"

    merged_blocks: list[tuple[str, str, str, int, list[str]]] = []
    needed_consts: dict[str, str] = {}

    # Also build fallback constant map from vanilla & GORA
    all_const_pool: dict[str, str] = {}
    for td in list(van_types.values()) + list(gora_types.values()):
        all_const_pool.update(td.file_constants)

    for tname, gt, ot in res.true_conflicts:
        cfg = recipe_types.get(tname, {})
        strat = cfg.get("strategy", "auto")
        notes: list[str] = []
        conflicts = 0

        if strat == "splice":
            body, warns = apply_splice_ops(
                ot.raw_body, cfg.get("ops", []), MOD_DIR / "gui"
            )
            notes.extend(warns)
            if warns:
                conflicts = len(warns)
            status = "SPLICE-CLEAN" if not warns else f"SPLICE-WARN({len(warns)})"
        elif strat == "prefer_overhaul":
            body = normalize_indent(ot.raw_body)
            status = "OVERHAUL"
        elif strat == "prefer_gora":
            body = normalize_indent(gt.raw_body)
            status = "GORA"
        else:
            vt = van_types.get(tname)
            if vt:
                body, conflicts = three_way_merge(
                    vt.raw_body, gt.raw_body, ot.raw_body, tname
                )
                status = "3WAY-CLEAN" if conflicts == 0 else f"CONFLICT({conflicts})"
            else:
                body = normalize_indent(ot.raw_body)
                status = "NO-VANILLA-BASE"

        merged_blocks.append((tname, status, body, conflicts, notes))

        # Collect @constants referenced by the merged body
        refs = set(CONST_REF_RE.findall(body))
        for c in sorted(refs):
            if c in ot.file_constants:
                needed_consts[c] = ot.file_constants[c]
            elif c in gt.file_constants:
                needed_consts[c] = gt.file_constants[c]
            elif c in all_const_pool:
                needed_consts[c] = all_const_pool[c]

    # Assemble minimal partial-type-override GUI file
    header_lines = [
        f"# GORA UI+ x {res.target_name} — Compatibility Patch (auto-generated)",
        "# ------------------------------------------------------------------------------",
        f"# Generated by: tools/compatch.py ({datetime.date.today().isoformat()})",
        f"# GORA UI+    : v{gora_meta.get('version', '?')} (game {game_ver})",
        f"# Overhaul    : {res.target_name} (v{ov_meta.get('version', '?')}, id={ov_meta.get('id', target_path.name)})",
        "#",
        "# Partial type override: declares ONLY the genuinely conflicting GUI types.",
        f"# Filename prefix `{prefix}` sorts before both mods in Victoria 3's first-load-wins",
        "# type registry; all non-conflicting types load cleanly from their source mods.",
        "#",
        "# Merged types:",
    ]
    for tname, status, _, _, notes in merged_blocks:
        header_lines.append(f"#   - {tname:42s} [{status}]")
        for w in notes:
            header_lines.append(f"#       ! {w}")
    if res.soft_compatible:
        header_lines.append("# Built-in soft-compatible types (handled natively by GORA UI+):")
        for tname, _, _, reason in res.soft_compatible:
            header_lines.append(f"#   - {tname:42s} ({reason})")
    header_lines.append(
        "# ------------------------------------------------------------------------------"
    )

    body_parts = ["\n".join(header_lines), ""]
    if needed_consts:
        body_parts.append("# File-scoped @constants referenced by merged types")
        for k, v in sorted(needed_consts.items()):
            body_parts.append(f"{k} = {v}")
        body_parts.append("")

    body_parts.append(f"types gora_compat_{slug} {{")
    for tname, _, body, _, _ in merged_blocks:
        indented = reindent_block(body, "\t")
        body_parts.append("")
        body_parts.append(indented)
    body_parts.append("}")
    body_parts.append("")

    final_gui = "\n".join(body_parts)
    out_gui_path = gui_out / out_gui_name
    out_gui_path.write_text(final_gui, encoding="utf-8", newline="\n")

    # Write .metadata/metadata.json (preserving existing id if updating an existing mod dir)
    existing_meta = load_metadata(out_dir)
    compatch_id = (
        existing_meta.get("id")
        or (recipe or {}).get("compatch_workshop_id")
        or f"gora_compat_{slug}"
    )
    compatch_name = (recipe or {}).get("compatch_name") or existing_meta.get("name") or f"GORA UI+ × {res.target_name} Compat"
    ov_dep_id = ov_meta.get("id") or (
        str(recipe["workshop_ids"][0]) if recipe and recipe.get("workshop_ids") else target_path.name
    )
    meta_obj = {
        "name": compatch_name,
        "id": str(compatch_id),
        "version": args.version or existing_meta.get("version") or "1.1.0",
        "supported_game_version": game_ver,
        "short_description": f"Compatibility patch for GORA UI+ and {res.target_name}.",
        "tags": ["UI", "Compatibility", game_ver.rstrip(".*")],
        "relationships": [
            {
                "rel_type": "dependency",
                "id": str(gora_meta.get("id", "3724865565")),
                "display_name": "GORA UI+",
                "resource_type": "mod",
                "version": "*",
            },
            {
                "rel_type": "dependency",
                "id": str(ov_dep_id),
                "display_name": res.target_name,
                "resource_type": "mod",
                "version": "*",
            },
        ],
        "game_custom_data": {"multiplayer_synchronized": True},
    }
    (meta_out / "metadata.json").write_text(
        json.dumps(meta_obj, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    syn = check_gui_syntax(final_gui)
    clean_cnt = sum(1 for _, _, _, c, _ in merged_blocks if c == 0)
    conflict_cnt = sum(1 for _, _, _, c, _ in merged_blocks if c > 0)

    print(f"=== Built Compatch: {compatch_name} ===")
    print(f"Output GUI : {out_gui_path} ({len(final_gui.splitlines())} lines)")
    print(f"Metadata   : {meta_out / 'metadata.json'} (game {game_ver})")
    print(
        f"Types      : {len(merged_blocks)} merged "
        f"({clean_cnt} clean, {conflict_cnt} need review) | "
        f"{len(res.soft_compatible)} soft-compat | "
        f"{len(res.harmless_overlaps)} harmless skipped"
    )
    for tname, status, _, _, notes in merged_blocks:
        print(f"  - {tname:42s} [{status}]")
        for w in notes:
            print(f"      WARN: {w}")
    print(
        f"Syntax     : {'PASS' if syn.ok else 'NEEDS REVIEW'} "
        f"(depth={syn.final_depth}, min={syn.min_depth}, "
        f"conflicts={syn.conflict_markers}, stray={len(syn.stray_lines)})"
    )
    return 0 if syn.ok else 2


def fetch_steam_details(ids: list[str]) -> dict[str, dict[str, Any]]:
    unique_ids = sorted({str(i) for i in ids if str(i).isdigit()})
    if not unique_ids:
        return {}
    params: dict[str, Any] = {"itemcount": len(unique_ids)}
    for idx, fid in enumerate(unique_ids):
        params[f"publishedfileids[{idx}]"] = fid
    req = urllib.request.Request(
        "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/",
        data=urllib.parse.urlencode(params).encode("utf-8"),
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return {
        str(it["publishedfileid"]): it
        for it in data.get("response", {}).get("publishedfiledetails", [])
    }


def cmd_audit(args: argparse.Namespace) -> int:
    recipes = load_recipes(Path(args.recipes))
    van_types = scan_gui_types(Path(args.vanilla) / "gui")
    gora_types = scan_gui_types(MOD_DIR / "gui")
    placeholders = load_placeholder_types(MOD_DIR / "gui")
    gora_meta = load_metadata(MOD_DIR)
    target_game_ver = gora_meta.get("supported_game_version", "1.15.*")

    workshop_dir = Path(args.workshop)
    candidates: list[tuple[str, Path]] = []

    # 1. Local sibling compat folders
    if LOCAL_MODS_DIR.is_dir():
        for d in sorted(LOCAL_MODS_DIR.iterdir()):
            if d.is_dir() and d != MOD_DIR and "gora" in d.name.lower():
                candidates.append(("LOCAL", d))

    # 2. Subscribed Workshop GORA compatches
    if workshop_dir.is_dir():
        for d in sorted(workshop_dir.iterdir()):
            if not d.is_dir() or d.name == str(gora_meta.get("id", "3724865565")):
                continue
            m = load_metadata(d)
            name = m.get("name", "")
            rels = [str(r.get("id", "")) for r in m.get("relationships", [])]
            if (
                "gora" in name.lower()
                and ("compat" in name.lower() or "x " in name.lower() or "×" in name)
            ) or any("gora" in r.lower() or r == "3724865565" for r in rels):
                candidates.append((f"WS:{d.name}", d))

    print(f"=== GORA UI+ Compatibility Audit (target game: {target_game_ver}) ===")
    print(f"Built-in soft-compat placeholder types: {sorted(placeholders)}\n")

    # Audit GORA UI+'s own gui/*.gui first
    gora_bad = 0
    for gf in sorted((MOD_DIR / "gui").rglob("*.gui")):
        syn = check_gui_syntax(read_text_clean(gf))
        if not syn.ok:
            gora_bad += 1
            print(
                f"[FAIL] GORA UI+ {gf.name}: depth={syn.final_depth} min={syn.min_depth} "
                f"conflicts={syn.conflict_markers} stray={syn.stray_lines}"
            )
    if gora_bad == 0:
        print(f"[PASS] GORA UI+ gui/ syntax: all {len(list((MOD_DIR / 'gui').rglob('*.gui')))} files clean.\n")

    # Audit each discovered compat patch
    for tag, path in candidates:
        meta = load_metadata(path)
        name = meta.get("name") or path.name
        gver = meta.get("supported_game_version", "?")
        issues: list[str] = []

        if gver != target_game_ver:
            issues.append(f"stale game_version={gver} (expected {target_game_ver})")

        gui_files = sorted((path / "gui").rglob("*.gui")) if (path / "gui").is_dir() else []
        declared_types: dict[str, str] = {}
        for gf in gui_files:
            txt = read_text_clean(gf)
            syn = check_gui_syntax(txt)
            if not syn.ok:
                issues.append(
                    f"SYNTAX ERROR in {gf.name}: depth={syn.final_depth}, "
                    f"stray={syn.stray_lines[:2]}, conflicts={syn.conflict_markers}"
                )
            for m in TYPE_HEADER_RE.finditer(txt):
                declared_types.setdefault(m.group(1), gf.name)

        # Check for clobbered non-target GORA types (e.g. full-file copy traps)
        clobbered_gora = [
            f"{t} ({declared_types[t]} < {gora_types[t].filename})"
            for t in sorted(set(declared_types) & set(gora_types))
            if declared_types[t].lower() < gora_types[t].filename.lower()
        ]
        if len(declared_types) > 12:
            issues.append(
                f"bloated full-file copy ({len(declared_types)} types declared; consider partial override)"
            )
        if any("state_panel_overview_content" in c and "00_mog_bso" in c for c in clobbered_gora):
            issues.append(
                "CLOBBERS Better State Overview (00_mog_bso_ui_state_overview_panel.gui)"
            )

        status = "OK" if not issues else f"{len(issues)} ISSUE(S)"
        print(f"[{tag:11s}] {name} ({len(gui_files)} gui, {len(declared_types)} types) -> {status}")
        for iss in issues:
            print(f"    ! {iss}")

    # Optional Steam freshness check across recipes
    if args.check_steam:
        print("\n=== Steam Workshop Freshness Check (recipes) ===")
        all_ids: list[str] = []
        for r in recipes.get("recipes", {}).values():
            all_ids.extend(r.get("workshop_ids", []))
            if r.get("compatch_workshop_id"):
                all_ids.append(str(r["compatch_workshop_id"]))
            all_ids.extend(str(x) for x in r.get("legacy_compatch_ids", []))
        try:
            details = fetch_steam_details(all_ids)
        except Exception as e:
            print(f"[WARN] Steam Web API query failed: {e}")
            return 0

        def fmt_date(ts: int) -> str:
            return (
                datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                if ts
                else "N/A"
            )

        for key, r in recipes.get("recipes", {}).items():
            ov_ids = [str(x) for x in r.get("workshop_ids", [])]
            cp_id = str(r.get("compatch_workshop_id", ""))
            primary_ov = details.get(ov_ids[0], {}) if ov_ids else {}
            cp = details.get(cp_id, {}) if cp_id else {}
            ov_ts = primary_ov.get("time_updated", 0)
            cp_ts = cp.get("time_updated", 0)
            local_ok = any((workshop_dir / i).is_dir() for i in ov_ids)
            stale = "STALE (overhaul newer!)" if (ov_ts and cp_ts and ov_ts > cp_ts) else "OK"
            print(
                f"  [{key:8s}] local={str(local_ok):5s} | "
                f"overhaul({ov_ids[0] if ov_ids else '-'})={fmt_date(ov_ts)} | "
                f"compatch({cp_id or '-'})={fmt_date(cp_ts)} -> {stale}"
            )
            if primary_ov.get("title"):
                print(f"             Overhaul: {primary_ov['title']}")
    return 0


def cmd_list_fences(args: argparse.Namespace) -> int:
    gora_gui = MOD_DIR / "gui"
    total = 0
    for gf in sorted(gora_gui.glob("*.gui")):
        blocks = extract_fences(gf)
        if not blocks:
            continue
        print(f"=== {gf.name} ({len(blocks)} fences) ===")
        for b in blocks:
            total += 1
            print(f"  L{b.start_line:4d}-L{b.end_line:<4d} | {b.label}")
    print(f"\nTotal paired extractable fences: {total}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GORA UI+ Overhaul Compatibility Toolkit"
    )
    parser.add_argument(
        "--vanilla", default=str(DEFAULT_VANILLA_DIR), help="Victoria 3 game/ directory"
    )
    parser.add_argument(
        "--workshop", default=str(DEFAULT_WORKSHOP_DIR), help="Steam Workshop 529340 directory"
    )
    parser.add_argument(
        "--recipes", default=str(DEFAULT_RECIPES_PATH), help="Path to compatch_recipes.json"
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Scan an overhaul mod for GUI/script conflicts")
    p_scan.add_argument("target", help="Recipe key (bpm/tgr/psc/ef), Workshop ID, or mod dir")
    p_scan.add_argument("--source", help="Override source Workshop ID or local mod dir")
    p_scan.add_argument("--markdown", action="store_true", help="Output Markdown table")
    p_scan.set_defaults(func=cmd_scan)

    p_build = sub.add_parser("build", help="Build a minimal partial-override compatch mod")
    p_build.add_argument("target", help="Recipe key (bpm/tgr/psc/ef), Workshop ID, or mod dir")
    p_build.add_argument("--source", help="Override source Workshop ID or local mod dir")
    p_build.add_argument("--out", help="Output mod directory (default: build/compat_<slug>)")
    p_build.add_argument("--prefix", default="!", help="Filename priority prefix (default: '!')")
    p_build.add_argument("--clean", action="store_true", help="Remove stale .gui files in output gui/ before writing")
    p_build.add_argument("--version", help="Override compatch metadata version (e.g. 1.1.0)")
    p_build.set_defaults(func=cmd_build)

    p_audit = sub.add_parser("audit", help="Audit GORA UI+ and existing compat patches")
    p_audit.add_argument(
        "--check-steam",
        action="store_true",
        help="Query Steam Web API to detect compatches older than their target overhauls",
    )
    p_audit.set_defaults(func=cmd_audit)

    p_fences = sub.add_parser("list-fences", help="List paired GORA UI+ fence markers")
    p_fences.set_defaults(func=cmd_list_fences)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
