# Changelog

All notable changes to Analytics Builder are documented here.

---

## [Unreleased]

---

## 2026-05-14 — Business Preferences, Brand Colors, Retry Cleanup, Advanced Mode

### Added

**Business Preferences for Tableau Next SDMs**
- The build now generates SDM-level Business Preferences text tailored to the company and use case — structured as `#`-prefixed instruction lines covering entity context, leading vs. lagging indicators, diagnostic dimensions, terminology, and time comparison defaults
- Text is saved to the checkpoint, included as a dedicated "Business Preferences (SDM)" section in the concierge walkthrough `.docx`, and printed in the final summary with a clear callout to paste it into the SDM manually
- Note: there is no public REST API for this field — it must be set in the UI (Data 360 → Semantic Model → [SDM] → AI Optimization → Manage Business Preferences)

**Brand Colors for Tableau Next dashboards**
- `/build-demo` now asks whether to use brand colors when building a Tableau Next demo for a real company
- If yes, Claude researches the company's brand guidelines and applies a `BRAND` dict (primary, secondary, chart_bg, text, dash_bg) to dashboard background/gutter and visualization shading/fonts
- Dark primary colors are automatically tinted: each channel blended 90% toward 255 (e.g. `#033C5A` → `#E6F1F6`)
- If no, or for fictitious companies, defaults to `#F3F3F3` background and `#2E2E2E` text

**Advanced Mode for `/build-demo`**
- Optional mode unlocked at the start of each session — never saved to config
- Configures four parameters per build:
  - **History length** — 6 / 12 / 24 (default) / 36 months
  - **Time grain** — daily / weekly / monthly (default); warns on daily + 36 months combination
  - **Signal design** (per primary metric) — severity (15% / 25% / 40% / custom), onset (−3 / −6 / −9 months), and shape (ramp / accelerating / step)
  - **Supporting metric strength** — subtle (8%) / moderate (12% default) / strong (18%)

**Cross-org OAuth error handling in `/setup`**
- Added two new troubleshooting blocks to the Salesforce OAuth browser flow step:
  - `invalid_client_id`: app not yet activated — wait 2–10 minutes and retry
  - `Cross-org OAuth flows are not supported`: browser is logged into the wrong org — sign out of all Salesforce sessions, log back into the target org, then retry

### Fixed

**Retry cleanup for Tableau Next phase 6**
- Vizzes and dashboards created during failed phase 6 runs are now tracked in `cp["all_viz_apis"]` and `cp["all_dash_apis"]` in the checkpoint
- At the start of each phase 6 run, all previously created assets in those lists are deleted before new ones are created
- These lists are never cleared on phase reset — they survive across retries so stale assets from any prior run are always cleaned up
- Safety rule: Claude will only delete assets that appear in those checkpoint lists; any other deletion requires explicit user confirmation

**VizQL visualization format**
- Rewrote `make_viz` to use the correct VizQL format: `layout: "Vizql"`, columns/rows as field-key arrays, all required top-level and style keys present
- Fixed series of 400 errors from missing required fields: `encodings`, `headers` (style + marks), `legends`, `lines`, `marks.panes`
- `style.marks.headers` now uses the `_marks_headers_style()` pattern
- `marks.panes` is a direct object specifying the chart type, not nested under `default`
- `style.lines` uses explicit keys — `{"referenceLines": {}}` is invalid
- `legends` is required at the top level of `visualSpecification`; use `{}` when no color dimension

**DLO status polling**
- Fixed status field path: `body.get("dataLakeObjectInfo", {}).get("status") or body.get("status", "UNKNOWN")` — the top-level `status` field is not always present
- Added 30-second post-ACTIVE wait before submitting bulk ingest jobs to allow schema propagation

---

## 2026-05-12 — Initial Release

### Added

- **`/setup`** — guided one-time configuration wizard for Tableau Cloud (PAT) and Salesforce (OAuth + Data Cloud); discovers or creates an Ingest API connector; supports multiple named profiles in `config.json`
- **`/build-demo`** — story-driven demo builder with three output modes:
  - **Tableau Pulse** — publishes `.hyper` datasource, creates Pulse metric definitions with correct granularities, creates a group, and subscribes it to all metrics
  - **Tableau Next** — pushes data to Data Cloud via Bulk Ingest API, builds a Semantic Data Model with relationships, calculated measurements, and metrics, then creates visualizations and a dashboard
  - **CSV export** — exports the generated dataset for use in any viz tool
- **Synthetic data generation** — 24 months of history, one row per entity per month, with an engineered signal ramp over the last 6 months
- **Concierge walkthrough `.docx`** — generated automatically with ordered Concierge prompts and talking points for each demo
- **Checkpoint/resume** — each build writes a `{slug}_checkpoint.json` after each phase so interrupted runs can resume without re-ingesting data or re-creating assets
- **`connections.py`** — centralized auth module; all demo scripts import from here, never inline credentials
- **`config.json.template`** — safe-to-commit template showing required credential fields
