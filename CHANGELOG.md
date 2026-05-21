# Changelog

All notable changes to Analytics Builder are documented here.

---

## [Unreleased]

---

## 2026-05-21 — Update Check on Skill Launch

### Added

**Automatic update check in `/build-demo` and `/setup`**
- Both skills now run `git fetch origin main` at startup and compare the remote commit count to the local HEAD
- If the remote is ahead, the user is prompted to pull before continuing, with a summary of what changed (`git log --oneline`)
- If the user declines, the build or setup proceeds with their current version
- Failures (no network, not a git repo) are silently ignored

---

## 2026-05-21 — Autonomous Mode Persisted + TriNet Build Fixes

### Changed

**Autonomous mode is now always on**
- The `allow` block in `.claude/settings.local.json` is no longer removed after each build — autonomous mode persists across sessions
- `/build-demo` no longer asks "would you like to run autonomously?" at the start of each session
- Instead, it notifies the user at build start that autonomous mode is active and explains how to switch to manual mode by typing "manual mode"

### Fixed

**Bulk ingest: daily-grain fact tables were losing all but the last day**
- Root cause: fact stream was created with `client_id` as the sole primary key; `upsert` with a non-unique PK overwrites previous rows, leaving only the final day's data
- Fix: added a `record_id` surrogate key (`date_clientid`, e.g. `2025-05-21_TN-10051`) as the stream PK so each client×day row is unique
- Note: the Bulk Ingest API only supports `upsert` and `delete` — `insert` returns 400

**Rate metrics displayed as decimals instead of percentages**
- CLCs for rate metrics (stored as decimals 0–1) now multiply by 100: `AVG([DO].[field]) * 100`
- Viz format suffix and axis format updated to `%` with 1 decimal place for rate fields
- Non-rate metrics (e.g. satisfaction scores) use a separate format with no suffix
- `METRIC_CONFIG` entries now carry an `is_rate` flag to control CLC expression and viz formatting

**Dashboard container widgets missing from widgets dict**
- Container widgets referenced in the layout's `page_widgets` were not included in the top-level `widgets` dict, causing 500 "Cannot invoke EntityObject.getId()"
- Fix: every widget name in the layout must have a corresponding entry in `widgets` with `type`, `name`, `actions: []`, and `parameters`

**Schema registration always updates existing schemas**
- Phase 1 previously skipped schema registration if the schema name already existed on the connector
- Fix: always PUT the current `FACT_FIELDS`/`DIM_FIELDS` definitions, replacing stale schemas — ensures new fields (e.g. `record_id`) are picked up without manual cleanup

### Added (CLAUDE.md pitfalls)

- Bulk Ingest: only `upsert` and `delete` are valid operations; `insert` returns 400
- Bulk Ingest: daily-grain fact tables need a surrogate `record_id` PK (`date_clientid`)
- Schema registration: PUT always replaces — don't skip if schema already exists when fields have changed
- Dashboard: all widget names in the layout must have entries in the `widgets` dict, including containers
- Dashboard widget entries need `actions: []`, `name`, `type`, `source`, and `parameters`

---

## 2026-05-14 — Retry Cleanup Extended to Workspace + SDM

### Fixed

**Stale SDMs and workspaces from failed runs**
- Extended the retry cleanup pattern (previously applied only to vizzes/dashboards in phase 6) to the workspace and SDM creation phase (phase 4)
- `all_ws_apis` and `all_sdm_apis` are now tracked in the checkpoint alongside `all_viz_apis` and `all_dash_apis`
- At the start of each phase 4 run, all previously created workspaces and SDMs in those lists are deleted before new ones are created, preventing accumulation of stale assets across retries
- Derived checkpoint keys (`ws_api`, `sdm_api`, `do_api`) are cleared before recreation so the phase always starts clean

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
