# AIO Analytics Builder — Feature Overview

A Claude Code tool for Salesforce/Tableau Solutions Engineers to rapidly build compelling, story-driven demo assets across four platforms — without writing a line of code.

---

## Core workflow

1. Run `/setup` once to connect your Tableau Cloud PAT and Salesforce OAuth credentials
2. Run `/build-demo` to describe your customer scenario
3. Walk away — Claude generates the data, builds all the assets, and hands you a ready-to-run walkthrough document
4. Demo your Tableau Next — the Display Date is self-healing and always shows current data (run `/refresh-dates` only for Pulse demos)

---

## What gets built

### Tableau Pulse
- Publishes a `.hyper` datasource to Tableau Cloud
- Creates Pulse metric definitions with correct granularities (Month / Quarter / Year)
- Creates a group and subscribes it to all metrics automatically

### Tableau Next (Salesforce Data Cloud)
- Pushes synthetic data via Bulk Ingest API
- Builds a full Semantic Data Model — DLO, measurements, calculated measurements, metrics
- Generates visualizations and an assembled dashboard with brand colors applied
- Configures AI optimization: field descriptions, Concierge noun pairs, and Business Preferences text

### CRM Analytics (CRMA / Wave)
- Uploads dataset via InsightsExternalData API (metadata → base64 CSV → process → poll)
- Creates a SAQL-driven dashboard from smart templates: time-series charts, grouped bars, KPI numbers, scatter plots
- Dimension filter dropdowns for interactive segmentation
- Brand color integration for backgrounds, text, and chart themes
- Organizes assets in a dedicated CRMA app/folder

### CSV export
- Exports the generated dataset for use in any viz tool

---

## Standout features

**Conversational analytics design**
Every demo is built to let the audience *solve a problem*, not just see a chart. Data and dimensions are engineered so the presenter can answer four questions in sequence: What is wrong? Where is it worst? Why is it happening? Who is most at risk? Signal is amplified differently by segment so filtering feels like discovery.

**Engineered story signal**
24 months of synthetic history with a deliberate metric decline over the last 6 months. Supporting metrics lag the primary signal to answer "why" after the audience has already seen "what." Signal severity, onset, and shape are all configurable.

**Advanced Mode**
Optional per-session configuration for power users:
- History length: 6 / 12 / 24 / 36 months
- Time grain: daily / weekly / monthly
- Signal design per metric: severity (15–40% or custom), onset (−3 / −6 / −9 months), shape (ramp / accelerating / step)
- Supporting metric strength: subtle / moderate / strong

**Autonomous mode**
Runs the entire build end-to-end without confirmation prompts. Always on — no need to opt in each session. Type "manual mode" during a build to switch back.

**Automatic update check**
Both `/setup` and `/build-demo` check for updates at launch via `git fetch`. If the remote is ahead, Claude shows a summary of what changed and offers to pull before continuing.

**Self-healing dates (both Tableau Next and Pulse)**
Both platforms use the same `DATEDIFF`/`TODAY()` formula that evaluates at query time — data always appears current automatically, no manual refresh needed. Tableau Next uses an SDM calculated dimension; Pulse uses a calculated field in the `.tdsx` datasource package.

**Date refresh (/refresh-dates)**
Only needed for Tableau Pulse demos — Pulse can't use calculated date formulas, so dates go stale over time. Run `/refresh-dates` before a meeting to regenerate data anchored to today and re-publish the `.hyper` (~30 seconds). Tableau Next demos are self-healing and never need this.

**Checkpoint / resume**
Every build writes a checkpoint file after each phase. If a run is interrupted, re-running `/build-demo` skips completed phases and picks up where it left off — no re-ingesting data, no duplicate assets.

**Retry cleanup**
Stale assets from failed runs (workspaces, SDMs, vizzes, dashboards) are tracked in the checkpoint and deleted automatically before each retry — so you always end up with exactly one clean set of assets.

**Brand colors**
For real-company demos, Claude researches brand guidelines and applies a `BRAND` dict to dashboard backgrounds, gutters, and visualization shading. Dark primaries are automatically tinted for readability.

**AI optimization (Tableau Next)**
- Field descriptions on every SDM measurement and dimension, written from the Concierge's perspective
- Concierge noun pairs (singular/plural) per metric
- SDM-level Business Preferences text generated and printed for manual paste-in (no public API — UI only)

**Demo walkthrough documents**
Every build produces:
- A `.docx` demo walkthrough with a focused click path and talking points
- A Concierge walkthrough (Tableau Next builds) with ordered AI prompts and expected responses

**Multi-org support**
`config.json` supports multiple named profiles. Switch between customer orgs or sandbox environments without re-running setup.

---

## Built-in guardrails

- All credentials live in `config.json` — gitignored, never committed
- OAuth refresh tokens are stored locally and exchanged for short-lived access tokens at runtime
- Claude only deletes assets that appear in its own checkpoint tracking lists — anything else requires explicit confirmation
