# Changelog

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
