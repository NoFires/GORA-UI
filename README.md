# GORA UI+

A curated quality-of-life UI overhaul bundle for **Victoria 3** (`1.15.*`), designed for minimal conflict surface, Ironman & multiplayer safety, and optional [Community Mod Framework (CMF)](https://steamcommunity.com/sharedfiles/filedetails/?id=3385002128) coexistence.

- **Steam Workshop**: [GORA UI+ (`3724865565`)](https://steamcommunity.com/sharedfiles/filedetails/?id=3724865565)
- **Discord**: https://discord.gg/SUygUwq3Tx
- **Integrated Mods & Versions**: [reference.md](reference.md)
- **Changelogs**: [CHANGELOG.md](CHANGELOG.md) | [CHANGELOG_CN.md](CHANGELOG_CN.md)

---

## GUI Architecture & Load-Order Rules

Victoria 3's Jomini GUI engine uses a **first-load-wins** type registry ordered **alphabetically by filename** across all enabled mods (independent of launcher load order):

| Prefix | Precedence | Purpose |
| --- | --- | --- |
| `!` | Highest | Dedicated overhaul compatibility patches (`!gora_<mod>.gui`) |
| `000_` | Very High | High-priority GORA / CMF building & map-list overrides |
| `00_` | High | Core panels that must beat standalone `00_` sub-mods (`00_gora_market_panel.gui`, `00_gora_goods_panel.gui`, `00_gora_tech_tree_panel.gui`) |
| `0_` | Standard | GORA partial type overrides (beat vanilla bare filenames, yield to `00_`/`000_`/`!` compatches) |
| *(bare)* | Vanilla | Base game files (`budget_panel.gui`, `states_panel.gui`, etc.) |
| `z_` | Lowest | Soft-compatibility fallback placeholders (`gui/z_gora_compat_placeholders.gui`, `gui/z_gate_compat_placeholders.gui`) |

### Core Design Rules

1. **Partial Type Overrides Only**: Never copy an entire 4,000-line vanilla `.gui` file when editing a single panel. Redeclare *only* the modified `type` blocks so all sibling vanilla/overhaul types load cleanly without conflict.
2. **Fenced GORA Deltas**: Wrap every GORA-specific UI addition inside paired comment fences so patches and automated compatch builds can extract them live:
   ```text
   ### GORA UI+ — <short feature description>
   ...
   ### /GORA UI+
   ```
3. **File Encoding**:
   - `gui/*.gui`, `common/**/*.txt`, `events/*.txt`: **UTF-8 without BOM**.
   - `localization/**/*.yml`: **UTF-8 with BOM** (required by Victoria 3).

---

## Overhaul Compatibility Strategy (Low-Effort 3-Tier Workflow)

Victoria 3 has no native widget-injection mechanism—duplicate GUI `type` definitions are whole-block first-load-wins. To minimize maintenance across major overhauls, GORA UI+ uses a **3-tier strategy**:

### Tier 1 — Zero-Compatch by Design (CMF Hooks & Granular Overrides)

Whenever possible, features override narrow inner sub-types or attach to CMF extension hooks rather than whole outer `*_panel` types. Overhauls that follow the same pattern (e.g., *Morgenröte*, *Tech & Res*, *Hail, Columbia!*) coexist automatically without any compatch.

### Tier 2 — Built-in Soft Compatibility (`gui/z_gora_compat_placeholders.gui`)

When an overhaul's modification to a shared panel is purely invoking its own custom widget `type`, GORA UI+ embeds that hook natively and declares an empty `visible = no` fallback in `gui/z_gora_compat_placeholders.gui` (which sorts last with `z_`):

- **Overhaul enabled**: the overhaul's real `type` loads first and renders natively inside GORA UI+ — **no separate compatch needed**.
- **Overhaul disabled**: the `z_` placeholder loads with `visible = no` — **zero `error.log` warnings and zero layout impact**.

Currently built in:
- **Economic and Financial Mod (E&F)**: `country_panel_currency_panel_content` (Country panel) & `state_panel_currency_panel_content` (State Overview panel) in `gui/z_gora_compat_placeholders.gui`.
- **Manaflow / Gate**: `gate_mana_density_colored` in `gui/z_gate_compat_placeholders.gui`.

**Adding a new soft-compat hook (3 steps):**
1. Add the overhaul's widget call inside the relevant GORA panel under `### GORA UI+ Soft Compat: <Mod Name>` ... `### /GORA UI+ Soft Compat`.
2. Add a matching empty `visible = no` fallback `type` to `gui/z_gora_compat_placeholders.gui`.
3. Run `python tools/compatch.py audit` to verify syntax.

### Tier 3 — Automated Compatch Toolkit (`tools/compatch.py`)

For heavy overhauls that rewrite shared panels (e.g., *Better Politics Mod*, *The Great Revision*, *Private Sector Construction Continued*, *Economic and Financial Mod*, *Project Utopia*), use the zero-dependency CLI in `tools/compatch.py` and declarative recipes in `tools/compatch_recipes.json`.

#### Prerequisites
- Python 3.9+ and `git` (for `git merge-file --diff3`).
- Optional environment overrides if Steam is not in the default Windows location:
  - `VIC3_GAME_DIR` (default: `C:\Program Files (x86)\Steam\steamapps\common\Victoria 3\game`)
  - `VIC3_WORKSHOP_DIR` (default: `C:\Program Files (x86)\Steam\steamapps\workshop\content\529340`)

#### Common Commands

```bash
# 1. Audit GORA UI+ and all local/Workshop compat patches (+ check Steam update drift)
python tools/compatch.py audit --check-steam

# 2. Scan ANY overhaul (by recipe key, Workshop ID, or local folder) for real vs. harmless conflicts
python tools/compatch.py scan bpm
python tools/compatch.py scan 3843134572
python tools/compatch.py scan "C:/path/to/overhaul_mod" --markdown

# 3. Build a minimal partial-type-override compatch (`!gora_<slug>.gui` + `.metadata/metadata.json`)
python tools/compatch.py build bpm --out "../GORA UI+ × Better Politics Mod Compat"
python tools/compatch.py build tgr --out "../GORA UI+ × The Great Revision Compat"

#    Override source if an overhaul changed maintainers / Workshop ID:
python tools/compatch.py build psc --source 3843134572 --out "../GORA UI+ x PSC Compat"

# 4. List all paired `### GORA UI+` / `### Smart Treaties` fences available for splice recipes
python tools/compatch.py list-fences
```

#### Per-Type Merge Strategies (`tools/compatch_recipes.json`)

| Strategy | Behavior | Best For |
| --- | --- | --- |
| `splice` | Pulls the overhaul's latest `type` body and injects GORA UI+'s live `### GORA UI+` fenced snippets by block-aware anchor (`after_block_end`) | Additive GORA features on heavily reworked panels (BPM, TGR, E&F Budget) — usually **0 conflicts** across updates |
| `auto` *(default)* | Indent-normalized 3-way merge (`git merge-file --diff3`: Vanilla base, GORA ours, Overhaul theirs) | General conflicts; eliminates tab-vs-space noise and marks only genuinely overlapping lines with `<<<<<<<` |
| `soft_compat` | Skipped — already handled natively via `gui/z_gora_compat_placeholders.gui` | Pure widget-hook overhauls |
| `prefer_overhaul` / `prefer_gora` | Keeps one side verbatim when both mods redesign the exact same UI slot | Intentional design overrides |

Each recipe also supports an array of `workshop_ids` (active fork first, legacy IDs as fallback) and `--source` CLI overrides, so when an overhaul is adopted by a new maintainer (e.g., *Private Sector Construction Continued* `3843134572` replacing `3420714166`), no code changes are needed.

---

## Publishing to Steam Workshop

`tools/publish_steam.py` stages the mod and publishes localized English + Simplified Chinese descriptions and change notes directly via the local Steam client:

```bash
# Dry run (stage and preview EN + ZH-CN notes/descriptions without uploading)
python tools/publish_steam.py

# Publish new version (requires .metadata/metadata.json, CHANGELOG.md, and CHANGELOG_CN.md versions to match)
python tools/publish_steam.py --publish

# Update EN + ZH-CN Workshop titles & descriptions only (no content re-upload)
python tools/publish_steam.py --metadata-only --publish
```

> **Note**: Keep `tools/steam_description.bbcode` and `tools/steam_description_cn.bbcode` under Steam's 8,000 UTF-8 byte limit.
