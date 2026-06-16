# Changelog

All notable changes to AIO Analytics Builder are documented here.

---

## 2026-06-16 — CRM Analytics (CRMA) Output Mode

### Added

**CRM Analytics as 4th output mode** (`crma_uploader.py`, `crma_dashboard_builder.py`)
- Full dataset upload via InsightsExternalData API (metadata → base64 CSV chunks → process → poll)
- Automatic field schema generation from METRIC_CONFIG and dimension lists
- CRMA dashboard builder: SAQL steps (time series, grouped bars, KPIs), chart widgets, filter dropdowns, text headers
- Brand color integration: background container, text colors, chart themes
- App/folder management: find_or_create_app for organizing assets
- Security predicate helper for row-level security on datasets
- CRMA guidance document integrated into build flow (SAQL pitfalls, PATCH rules, field naming)

---

## 2026-06-10 — Viz Template Library + Validation Engine + Dashboard Builder

### Added

**Visualization template library** (`viz_templates.py`, `viz_builder.py`)
- 9 chart templates: trend_over_time, multi_series_line, bar_by_category, stacked_bar, horizontal_bar, donut, scatter, heatmap, funnel
- Auto-recommends chart types from METRIC_CONFIG based on field names and aggregation patterns
- Builds complete API payloads with correct fields, encodings, style, marks, legends
- Infers number formats (%, $, decimals) from field name patterns
- Supports brand color palettes and style overrides
- Adapted from alaviron/tableau-skills template library (internal Salesforce)

**Pre-POST validation engine** (`viz_validator.py`)
- 17 rules checking all known API failure modes before hitting the endpoint
- Validates: root fields, view structure, visualSpecification keys, marks structure, style (fonts/lines/axis/encodings/headers), encoding field references, donut requirements, size encoding support
- Catches errors locally instead of learning from 400 responses
- Returns actionable fix suggestions for each failure

**Dashboard layout builder** (`dashboard_builder.py`)
- 4 layout patterns: standard (3 metrics + 2x2 vizzes), metrics_heavy (6 metrics + 3 vizzes), story_flow (3 metrics + wide hero + 2-up), wide_viz (3 metrics + 2 full-width)
- Auto-selects pattern based on widget counts
- Produces complete dashboard payload with widgets dict, layouts, containers
- ASCII preview generation for user confirmation before building
- 72-column grid with rowspan 15 metric cards (matches our existing preference)

**Style defaults module** (`style_defaults.py`)
- Font builder (7 required keys), line builder (4 keys), shading, field labels
- Brand color override system
- Number format helpers for axis, encoding, and header fields
- Marks header/panes style builders with all v66.12 required fields

---

## 2026-06-05 — Pulse Refresh Pattern + Dynamic Offset + /refresh-demo Rewrite

### Changed

**Pulse date freshness: refresh-based instead of self-healing**
- `.tdsx` packages NEVER index on Tableau Cloud (confirmed: 14+ hours with no indexing, across multiple tests with both hand-crafted and Cloud-format `.tdsx` files)
- True self-healing via calculated fields is not possible for Pulse on Tableau Cloud
- New pattern: publish `.hyper` → set `use_dynamic_offset: True` via PATCH → run `/refresh-demo` before meetings to regenerate data anchored to today
- Metrics survive `.hyper` datasource overwrites — no deletion/recreation needed on refresh

**`/refresh-demo` rewritten from scratch**
- Old purpose: upgrade legacy demos to `.tdsx` self-healing (no longer applicable)
- New purpose: regenerate data + re-publish `.hyper` to keep Pulse dates fresh
- Supports refreshing a single demo by slug or all demos at once
- ~30 seconds to refresh (data gen + publish)
- Optional Tableau Next re-ingest for demos that also use Data Cloud

### Added

**Pulse 26.2 API findings documented**
- `extension_options` must be set via PATCH (not accepted in POST create payload)
- `temporality: 'TEMPORALITY_UNSPECIFIED'` causes 400 on create — field is read-only
- PATCH Content-Type: `application/vnd.tableau.metricqueryservice.v1.UpdateDefinitionRequest+json`

---

## 2026-06-04 — Pulse .hyper Direct Publish Fix

### Fixed

**Pulse datasource indexing: publish .hyper directly, never .tdsx**
- Publishing `.tdsx` packages causes Pulse to take 2+ hours (or indefinitely) to index the datasource — metric creation fails with 404 "Not Found" during that window
- Publishing `.hyper` directly allows Pulse to index in seconds and metric creation succeeds immediately
- Root cause: Pulse's internal discovery system processes raw `.hyper` files on a fast path but queues `.tdsx` packages for deferred processing
- Updated all Pulse publish calls to use `server.datasources.publish(ds_item, hyper_path, "Overwrite")` instead of `.tdsx`
- Pulse metric `time_dimension` now references raw `Date` column (not calculated `Display Date`)

---

## 2026-06-03 — Viz Field Role Exclusivity + Summary Clarity

### Fixed

**Visualizations: field role exclusivity rule**
- Added a guard to prevent placing the same semantic field in both a grouping slot (dimension/columns) and an aggregation slot (measure/rows) in the same visualization
- This caused charts to silently fail to render — reported by a user whose build needed manual correction
- Rule added to both `build-demo.md` Phase 5 instructions and `CLAUDE.md` Known Pitfalls

### Improved

**Final summary: business preferences callout**
- The post-build summary now explicitly tells the user that Business Preferences are at the end of the walkthrough `.docx` file, includes the full file path, and reminds them where to paste it in the SDM UI

---
## 2026-05-29 — Pulse Goals/Thresholds + HCHSP Demo

### Added

**Pulse goals/thresholds support (data-side + documented manual setup)**
- `METRIC_CONFIG` now supports an optional `goal` dict with `value`, `field`, `name`, `direction`
- Data generation adds constant target columns to the datasource (e.g. `Attendance Target = 0.85`)
- Walkthrough `.docx` includes a "Setting Up Goal Lines" section with field-to-metric mapping table
- Company research step now explicitly calls out finding regulatory thresholds and compliance targets

**Known Pitfall: Pulse `datasource_goals` API is non-functional**
- Tested all payload variations: `basic_specification`, `threshold_basic_specification`, minimal — all return 400 "Invalid request"
- PATCH/PUT on existing definitions also fails
- Workaround: include target columns in datasource + document 2-minute UI setup

**HCHSP (Hidalgo County Head Start Program) demo built**
- 27 campuses across 8 ISDs in Hidalgo County, TX
- Metrics: Attendance Rate (85% federal threshold), Dental Completion, Screening Compliance, Family Referral Rate
- Signal: rural ISDs (Monte Alto, Mercedes, La Joya) declining below federal floor; urban campuses masking the problem
- Full walkthrough `.docx` with federal compliance context (45 CFR citations)

---

## 2026-05-28 — Self-Healing Dates (Tableau Next + Pulse)

### Changed

**Both platforms now use self-healing Display Date formulas — no `/refresh-demo` needed**

The same logic applies to both Tableau Next and Pulse:
```
DATEADD("day", DATEDIFF("day", #<build_date>#, [date_field]), TODAY())
```
Each row's date is shifted forward by the number of days elapsed since the build. `TODAY()` evaluates at query time on both platforms, so the most recent data always appears as "today" automatically.

**Tableau Next**: Self-healing calculated dimension on the SDM. Metrics reference it via `{"calculatedFieldApiName": "Display_Date"}`.

**Pulse**: Self-healing calculated field embedded in a `.tdsx` package (ZIP of `.tds` XML + `.hyper`). Pulse evaluates `TODAY()` fresh on every query because "unstable functions" are excluded from extract materialization.

### Key findings
- SDM calculated dimensions use `#YYYY-MM-DD#` hash-delimited date literals (not `DATE(y,m,d)`)
- Metric `timeDimensionReference` for calc dims must use `calculatedFieldApiName` (not `tableFieldReference`)
- Pulse `.tdsx` calc fields use single quotes: `DATEADD('day', ...)`; SDM uses double quotes
- Tableau Cloud evaluates `TODAY()` at query time for both published extracts and SDM expressions

### Updated files
- `CLAUDE.md` — unified date-shifting rule, new Known Pitfall for `calculatedFieldApiName`
- `.claude/commands/build-demo.md` — Phase 2 documents `.tdsx` packaging; Phase 4 documents self-healing calc dim
- `.claude/commands/refresh-demo.md` — reframed as legacy upgrade tool only
- `OVERVIEW.md` — both platforms documented as self-healing
- `README.md` — Step 5 now says "no action needed"

---

## [Unreleased]

---

## 2026-05-21 — Field Descriptions for AI Optimization

### Added

**Automatic field descriptions on every SDM measurement and dimension**
- `METRIC_CONFIG` entries now carry a `description` field; it is included in the measurement PUT payload (same call as `aggregationType` — no extra round-trip)
- A `DIM_DESCRIPTIONS` dict at the top of each demo script maps dimension field names to plain-language descriptions written for Concierge to read ("Use this field to..." style)
- After DO creation, a loop PUTs descriptions on every filterable dimension via `PUT /services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}/dimensions/{api}`
- Descriptions are generated during the company research phase so they reflect the actual use case and terminology

These descriptions appear in the Tableau Next UI and are the primary signal the Analytics AI Agent uses to understand what each field means. Without them, Concierge cannot accurately answer questions about the data.

---

## 2026-05-21 — Conversational Analytics Principle + TriNet Dimension Expansion

### Added

**Conversational analytics design principle**
- Added a core design principle to both `build-demo.md` and `CLAUDE.md`: every demo must let the audience answer four questions — What is wrong? Where is it worst? Why is it happening? Who is most at risk?
- Dimensions must be designed to support each layer of that conversation, not just produce a chart
- Signal amplification by segment (high-cost plans hit harder, micro clients harder than mid-market, specific regions lead) so filtering feels like discovery, not decoration

**TriNet demo — drillable dimensions**
- Added `plan_cost_tier` (Low/Mid/High) and `workforce_type` (Technical/Administrative/Sales/Mixed) to client generation — with realistic distributions by vertical (Tech/Life Sciences skew High cost; Nonprofits skew Low)
- Added three benefit category metrics: `medical_enrollment_rate`, `dental_enrollment_rate`, `voluntary_plan_enrollment_rate` — with differentiated signal decay (voluntary drops at 1.8× the primary signal, medical at 0.2×) to show cost-sensitive benefits drop first
- All new dimensions denormalized into the fact table so the SDM can filter by them (IngestAPI DLO join workaround)
- Signal now amplified by segment: High-cost tier × 1.5, Micro size × 1.3, Northeast/West regions × 1.2–1.3 — creating a real investigative story
- Dashboard expanded to 3 rows of vizzes (6 total): overall trend, voluntary opt-in, voluntary plan breakdown, medical trend, utilization, satisfaction
- Metric tiles updated to show Benefits Enrollment Rate, Voluntary Opt-in Rate, Voluntary Plan Rate as the three opening KPIs
- `additionalDimensions` on metrics now includes vertical, size_band, region, state, plan_cost_tier, workforce_type

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
