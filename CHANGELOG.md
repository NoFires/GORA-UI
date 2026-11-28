# Changelog

## [1.4.3] - 2026-11-29

- Fixed Pop Acceptance & Culture pie/treemap charts in the Society panel (`gui/0_gora_society_panel.gui`) leaving an inner gap around their decorative bronze frames by sizing the charts via `blockoverride "piechartsize"` (`150x150`) instead of stretching the outer container.
- Rebuilt `pop_list` collapsed & expanded rows (`gui/0_gora_pops_overview.gui`) with `hbox` + capped `fixedgridbox` (`5` goods tiles in Society/Overview, `4` tiles in Building Workforce) so Visible Pop Needs cards never clip off the right edge or overlap Radicals/Loyalists.
- Eliminated `pdx_gui_animation_runtime_state.cpp:618` warnings by adding `alpha = 1` to callback-only / no-op animation `state` blocks across Market, Smart Treaties, and IPG panels.
- Replaced hardcoded vanilla goods keys in Trade Partners' World Market demand-buffer valuation (`common/script_values/trade_partners_script_values.txt`) with a dynamic `goods.base_price` formula for zero warnings with goods-adding and total-conversion mods, and restored upstream's observer-mode refresh cadence.

## [1.4.2] - 2026-11-29

- Upgraded bundled Improved ParliamentGraph to v3.1.1: unified equal-outer-diameter matte-enamel seat dots (plus dedicated 16x16 small-dot textures eliminating aliasing on dense chambers), crowned Head of State medallion, true 50-seat visual tier (e.g. 50-seat Prussia renders 50 spaced dots), per-tier faded floorplan underlays for Westminster & Assembly Hall, vertically centered symmetric 8+8 Assembly Hall, roomier Horseshoe margins, and balanced Bicameral split with majority/minority seat colors and top-left title.
- Polished IPG chrome & tooltips: replaced cool-silver tab highlights with warm antique-gold active tab frames, gave the Foreign AI Parliament Viewer equal-thirds tabs with auto-refresh on open plus a compact round refresh button in the header, added tooltip bottom padding for middle-click lock clearance, brightened tooltip category tags, fixed D'Hondt icon & non-breaking minus line wraps across all 11 languages, and removed the duplicate Ruler IG icon.
- Improved foreign-panel mod compatibility: moved IPG's foreign parliament hook to lowest-priority `gui/country_politics_panel.gui` (yields cleanly to foreign-panel mods such as Improved Domestic Panel 3573737721 placed below GORA UI+) and aligned `gui/0_ipg_politics_panel_government_details.gui` with standalone IPG naming.
- Integrated Victorian Charts (1.0.0): softer, lower-contrast Victorian pie & treemap chart shaders (`gfx/FX/pdxgui_piechart.shader`, `gfx/FX/pdxgui_treemapchart.shader`).
- Updated bundled Trade Partners to v0.1.4: added a shared Pie/Treemap chart toggle on the Market Trade tab, refined export/import headers & tooltips, and updated 11-language localization.
- Fixed Building Workforce Radicals/Loyalists counts overlapping the Visible Pop Needs consumption tiles on both collapsed and expanded pop rows (`gui/0_gora_pops_overview.gui`).

## [1.4.1] - 2026-11-28

- Synced the military formation footer (`gui/0_gora_military_formation_panel.gui`) and military formations panel (`gui/0_gora_military_panel_formations.gui`) to Victoria 3 1.15.2 while keeping GORA UI+ performance optimizations intact.
- Restored the 1.15.2 "Automatically replace lost ships" checkbox (`AUTO_REPLACE_LOST_SHIPS_LABEL`) inside fleet Formation Settings.
- Removed the obsolete 1.15.0 "edit mission sea regions" button (whose engine bindings were removed in 1.15.2) from both fleet panels, and added vanilla 1.15.2 fleet status icons, the live naval mission sea-region edit summary banner, and button text margins.

## [1.4.0] - 2026-11-28

- Upgraded bundled Improved ParliamentGraph to v3.1: added an interactive bottom-left Seat Apportionment selector with 5 live formulas (Hare / Hamilton, D'Hondt, Sainte-Laguë, 5% Threshold PR, and Mild Plurality / FPTP) plus Smart Auto-Matching driven by Distribution of Power laws and cultural heritage.
- Linked active apportionment formulas to both real-time seat distribution across all 3 views (Party Structure, Power Structure, Political Alignment, including post-formula seat share percentages) and historically authentic chamber sizes (Plurality +25%, Sainte-Laguë +10%, Hare baseline, D'Hondt -5%, 5% Threshold -15%).
- Added 20+ country-specific historical chamber names with full Upper House / Lower House / Whole Parliament alignment across all views and tooltips (e.g., Great Britain House of Lords / House of Commons / Parliament, USA Senate / House of Representatives / Congress, Qing Grand Council / Advisory Council, Tsarist State Council / State Duma, German Bundesrat / Reichstag).
- Added on-demand Foreign AI Parliament Viewer on other countries' Diplomacy -> Politics tab (Party Structure, Power Structure, and Political Alignment with zero background AI overhead), 5-election rolling seat history on hover tooltips, 3D enameled dot sheen, custom Upper/Lower chamber badges, and full official vanilla terminology alignment.
- Added localized hover tooltips to all domestic and foreign parliament view tab buttons (Party Structure, Power Structure, Political Alignment) as well as Collapse/Expand controls across all 11 official languages.

## [1.3.0] - 2026-11-28

- Upgraded bundled Improved ParliamentGraph to v3.0: added 5 authentic chamber architectures (Westminster Opposing Benches, Bicameral Dual-Chamber Split, Commonwealth Horseshoe, Terraced Assembly Hall, and Classic Hemicycle) with automatic culture & law matching (British/Anglo-Canadian heritage -> Westminster, Presidential Republic -> Bicameral, Council/Single-Party -> Assembly Hall, Australian & Constitutional Monarchy -> Horseshoe) plus a sleek bottom-right dropdown selector with native explanation tooltips.
- Added dynamic parliamentary seat counts (50–650 seats) scaling with Distribution of Power law, incorporated states, and politically active population across 100/200/300 visual tiers using Hamilton (largest-remainder) apportionment.
- Redesigned all 4 parliament summary tooltips into Paradox-native FancyTooltips featuring ornate header emblems, multi-color proportional stacked bars (with a 50% majority line on Electoral view), and grouped In Government / In Opposition zebra-striped tables with native icons and party member IG icon strips.
- Added interactive per-seat hover tooltips on every seat dot, contiguous Government-first -> Opposition-second seating with gold coalition halos, Head of State focal seat, smart non-election fallback, and instant updates on government reform (`on_government_reformed`) across all 11 languages.

## [1.2.2] - 2026-11-26

- Fixed the Standard of Living label overlapping the workplace building button on expanded rows of the Population list (`gui/0_gora_pops_overview.gui`) by resizing the bottom info container to fit the 64px goods-consumption tiles alongside the SoL header, and added spacing between tiles.

## [1.2.1] - 2026-11-26

- Added clickable descending/ascending column sorting (Population, GDP, Standard of Living, Peasants) with sort-direction arrows to the Domestic Lens Decree state list; per-country scripted sorting is multiplayer-safe and preserves all existing filters and actions.
- Added built-in soft compatibility placeholders (`gui/z_gora_compat_placeholders.gui`) with native Economic and Financial Mod (E&F) currency panel hooks on the Country and State Overview panels (zero errors when E&F is disabled).
- Added the overhaul compatibility toolkit (`tools/compatch.py`, `tools/compatch_recipes.json`) and comprehensive `README.md` documentation for GUI override priorities, soft-compatibility hooks, and automated compatch building/auditing.

## [1.2.0] - 2026-11-26

- Integrated Reorder Research Queue: drag & drop techs (v0.10) into the tech tree panel alongside the Latest Research indicator, with drag-and-drop queue reordering, expandable overflow row, and 11-language localization.
- Integrated ship silhouette icons with tier numbers from Improved Ship Icons (pure DDS sprites only; vanilla ship types and groups remain untouched for overhaul compatibility).
- Updated bundled Smart Treaties from 0.12 to 0.14, adding losing goods-transfer alerts and collapsible best-partner recommendations on the Market Trade tab and Goods panel.
- Raised market and goods panel GUI filenames to the 00_ prefix so standalone 00_ partial-override mods (such as standalone Smart Treaties or Trade Partners) cannot hijack the outer 600px market window and clip goods icons.

## [1.1.1] - 2026-11-22

- Fixed the standard of living line on the Population overview's strata cards being misaligned with the new Victoria 3 1.15 header illustration.
