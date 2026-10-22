# AIO Analytics Builder

A Claude Code skill for Tableau and Salesforce Solutions Engineers to rapidly build compelling demo assets across three platforms: Tableau Pulse, Tableau Next, and Salesforce Data Cloud.

## CRITICAL: Troubleshooting rules

**When you encounter an error during a `/build-demo` run, follow this order EVERY time:**

1. **Check the Known Pitfalls section below FIRST** — most errors are already documented with exact fixes
2. **Check the `/build-demo` skill instructions** — the correct payload format, field names, and API patterns are already specified there
3. **Check existing working demo scripts** in `demos/` — if another demo built successfully on the same org, copy its exact pattern
4. **Only if the error is genuinely new** (not in Known Pitfalls, not in the skill, not in any working script) — then troubleshoot independently

**NEVER:**
- Research or web-search for solutions to API errors that are already documented in this file
- Guess at payload formats when the `/build-demo` skill specifies the exact format
- Rewrite working patterns from scratch when you can copy from a working demo script
- Spend multiple retries on an approach that contradicts what's documented here

**When you fix a genuinely new issue**, add it to the Known Pitfalls section so it's solved permanently for all future builds.

## Demo design principle — conversational analytics

Every demo should let the audience *solve a problem*, not just see a chart. Design data and dimensions so the demo can answer a sequence of questions:

1. **What is wrong?** — The primary metric signal makes the problem unmissable within 10 seconds
2. **Where is it worst?** — Dimensions like Vertical, Region, Size Band let the presenter filter to the segment driving the decline
3. **Why is it happening?** — Supporting metrics and category breakdowns explain the cause (e.g. voluntary plan enrollment drops before overall enrollment — cost sensitivity)
4. **Who is most at risk?** — Fine-grained dimensions (Plan Cost Tier, Workforce Type, State) let the audience identify specific clients or groups to act on
5. **What do we do now?** *(optional — only when the demo includes close-the-loop)* — `/close-loop` turns the at-risk finding into a live follow-up in the org (Tasks / Case / Campaign via Flows) with a Slack or Chatter notification the audience triggers during the meeting

**Dimension design rules:**
- Always denormalize categorical dimensions into the fact table (IngestAPI DLO joins silently drop criteria — see Known Pitfalls). Every field the audience might filter by must be a column on the fact row.
- Add at least one dimension that explains *cost or effort* (e.g. Plan Cost Tier, Deal Size Band) — this is almost always the root cause the audience cares most about
- Add at least one dimension that explains *who/where* (Region, Vertical, Size Band) — segmentation is the first move in any analytical conversation
- Category breakdowns (e.g. Medical vs Dental vs Voluntary enrollment) are more valuable than aggregate totals — they reveal *which* component is driving the change

**Signal design rules for drillable stories:**

- **Differentiate signal magnitude by segment** — never apply the same signal multiplier to all rows. Assign per-segment multipliers so that filtering reveals a story rather than confirming the overall average. One or two segments should be the clear culprit (multiplier 1.5–2.5×), one or two should be moderate (0.8–1.2×), and at least one should be flat or slightly improving (0.0–0.3×). Example for a participation decline: President's Club drops 30%, Mid-Market drops 15%, SMB is flat, Enterprise actually ticks up slightly — the average hides this until you filter.

- **2D compound multiplier tables for the deepest drill path** — the most compelling demos have a "compound story": overall down 20% → filtered to Program Type X down 35% → filtered to Program Type X + Region Y down 45%. Implement by assigning 2D multipliers keyed on `(dim1_value, dim2_value)` tuples for the primary culprit segment only; all other program types get flat scalar multipliers. Pattern:
  ```python
  # President's Club uses 2D: region × size band
  PC_COMPOUND = {
      ("Northeast", "Mid-Market"):       2.2,   # steepest — the reveal
      ("Northeast", "Small Enterprise"): 1.9,
      ("West",      "Mid-Market"):       1.8,
      ("West",      "Small Enterprise"): 1.6,
      ("Midwest",   "Mid-Market"):       1.0,   # moderate
      ("South",     "Mid-Market"):       0.6,   # barely moves
      ("South",     "Global"):           0.3,
  }
  # Other program types: flat scalar (not 2D)
  if prog == "Sales Contest":      combined_mult = 0.55
  elif prog == "Quota Attainment": combined_mult = 0.35
  elif prog == "Channel Partner":  combined_mult = -0.10  # counter-trend
  else:  # President's Club
      combined_mult = PC_COMPOUND.get((client["region"], client["size_band"]), 1.0)
  ```
  The resulting demo narrative: "Overall down 25% → President's Club down 38% → Northeast President's Club down 45% → Northeast Mid-Market President's Club down 50%."

- **Counter-trend segment** — assign a small negative multiplier (e.g. `-0.10`) to one segment so it trends slightly upward while everything else declines. This makes the overall average misleading on purpose — the counter-trend segment props up the average and masks the severity in the culprit segment. The "aha" moment is when the audience sees Channel Partner is actually *improving* while President's Club is cratering. Never set counter-trend multiplier below -0.15 or the upward trend becomes implausibly obvious.

- **Signal ramp shape** — use `"accelerating"` (quadratic) as the default signal shape, not linear. Accelerating = slow at first, steeper toward the present, which mirrors how real problems manifest. The ramp function:
  ```python
  def signal_ramp(d, onset=SIGNAL_ONSET, shape="accelerating", duration=3):
      months_from_today = (d.year - TODAY.year) * 12 + (d.month - TODAY.month)
      months_from_onset = months_from_today - onset
      if months_from_onset <= 0:
          return 0.0
      progress = min(1.0, months_from_onset / duration)
      if shape == "accelerating": return progress ** 2
      if shape == "ramp":         return progress
      if shape == "step":         return 1.0 if progress >= 0.3 else 0.0
      return progress
  ```
  `onset` is a negative integer (months before today when the signal starts). `duration` is how many months until the signal reaches full magnitude. Set `SIGNAL_MAGNITUDE` higher than you think you need (0.45–0.55) — the accelerating shape keeps early months nearly flat, so the effective visible decline is smaller than the magnitude parameter.

- **Noise scale by size band** — smaller/lower-volume segments need more noise to look realistic; larger segments should be smoother:
  ```python
  NOISE_SCALE = {
      "Small Enterprise": 0.022,
      "Mid-Market":       0.016,
      "Large Enterprise": 0.011,
      "Global":           0.007,
  }
  ns = NOISE_SCALE[client["size_band"]]
  participation = max(0.05, base * (1 - SIGNAL_MAGNITUDE * p_ramp) + np.random.normal(0, ns))
  ```

- **Supporting metrics lag the primary** — multiply supporting metrics by `0.7×` the primary ramp and use `SUPPORTING_MAGNITUDE` (typically 0.65–0.75× of `SIGNAL_MAGNITUDE`). This creates the story sequence: Redemption Rate drops first → Points Per Rep follows → Participation Rate declines → Goal Achievement Rate confirms. Never have all metrics move simultaneously at full magnitude.
  ```python
  p_ramp = ramp * combined_mult          # primary metrics (Participation, Goal Achievement)
  s_ramp = ramp * combined_mult * 0.7   # supporting metrics (Redemption, Points Per Rep)
  active_reps uses s_ramp * 0.5         # headcount lags even more
  ```

- **Base value variation per client** — assign each client a randomized base value (e.g. `base_participation = random.uniform(0.62, 0.82)`) so the starting levels vary realistically. Without this, all clients start at the same value and the data looks synthetic at a row level.

- **Client roster construction** — build a full cross-product of all dimension combinations (vertical × region × size × N clients per cell) with N=2. This ensures every filter combination has data. Use `random.choice(PROGRAM_TYPES)` to assign program type so distribution is approximately even but not perfectly balanced.

## What this does

- **/setup** — Guided one-time setup: connects to Tableau Cloud (PAT) and Salesforce (OAuth), discovers or creates Data Cloud ingest connector
- **/build-demo** — Story-driven demo builder: generates synthetic data with engineered signals, then offers three outputs:
  1. **Tableau Pulse** — publishes a .hyper datasource and creates Pulse metric definitions + group subscriptions
  2. **Tableau Next** — pushes data to Data Cloud, builds a Semantic Data Model, metrics, visualizations, and dashboard
  3. **CSV export** — exports the generated dataset for manual use in any viz tool
- **/close-loop** — Optional final step (offered at the end of `/build-demo`, or run standalone on any `demos/{slug}/`): deploys Flows that create the story's follow-up records and notify the team in Slack (or Chatter). Slack is configured here only, never in `/setup`
- **/studio** — Tableau Studio Agent skills pre-loaded with the demo's story (aio-story, aio-autobuilder, aio-audience, plus custom skills Claude writes on request). Offered after close-loop at the end of `/build-demo`, or run standalone on any `demos/{slug}/`, an outside CSV/.hyper/.tdsx, or a published Tableau datasource. Needs no org

## Project structure

- `connections.py` — all auth logic; import this everywhere, never inline credentials
- `oauth_flow.py` — Salesforce OAuth browser flow (port 8080 callback)
- `setup.py` — setup wizard logic called by /setup
- `config.json` — per-SE credentials (gitignored, never commit)
- `config.json.template` — safe to commit, shows required fields
- `demos/` — generated demo scripts and exports land here
- `viz_templates.py` — chart template definitions and auto-recommendation logic
- `viz_builder.py` — builds complete viz API payloads from templates + SDM field map
- `viz_validator.py` — 17-rule pre-POST validation engine; run before every viz POST
- `dashboard_builder.py` — layout patterns and dashboard payload assembly
- `style_defaults.py` — font/line/shading/encoding builders with brand color support
- `crma_uploader.py` — CRM Analytics dataset upload (metadata + base64 CSV + poll)
- `crma_dashboard_builder.py` — CRMA dashboard state builder (SAQL steps + chart widgets + layout)
- `twb_builder.py` — Tableau Desktop workbook (.twb) generator: creates worksheets (bar, line, multi-line, dual-axis) + dashboard with Pulse metric tiles, publishes via TSC
- `prep_flow_builder.py` — Tableau Prep flow generator for auto-refreshing Pulse dates (builds .tflx with embedded CSV + DATEADD(Day_Offset, TODAY()) calc + PublishExtract output)
- `crm_upserter.py` — Salesforce CRM record upsert (External ID field creation via Tooling API, batch upsert via Composite Collections API, SOQL query helper)
- `close_loop.py` — /close-loop engine: story analysis → action/trigger plan → Flow generation → Metadata API deploy → activate → walkthrough Section 7. CLI: `preflight | slack-check | plan | build | test | reset | remove`
- `close_loop_flows.py` — Flow metadata XML generators (follow-up, notify, alert, screen, signal) + `package.xml`
- `setup_slack.py` — saves Slack IDs to `profiles.{key}.slack` and runs the read-only Slack check; called by /close-loop only when the user picks Slack
- `studio_skills.py` — /studio engine: story derivation (reuses `close_loop.analyze_story`) → `demo-story.md` → skill folders + `install.sh` + README → walkthrough Section 8. Also imports outside sources and validates custom skills. CLI: `story | generate | custom | install | status`
- `sidekicks/studio/skills/` — the three Tableau Studio skill templates (generic; each falls back to asking for the story if `references/demo-story.md` is missing). Design: `sidekicks/studio/docs/studio-skills-design.md`

## CRM actionability (Tableau Next)

When `crm_actionable` is enabled for a Tableau Next build, AIO creates real Salesforce CRM records (Accounts) linked to the analytics fact data via a shared External ID. This closes the insight-to-action loop: the audience drills from a metric → identifies at-risk entities → clicks through to the actual Account record → triggers a Flow or Global Action.

**How it works:**
1. Data gen creates an `ACCOUNT_ROSTER` — one Account per entity in the demo, with standard SF fields (`Name`, `Industry`, `BillingState`, etc.) plus `Demo_External_ID__c` matching the fact table entity key
2. Phase 1b upserts these records via `crm_upserter.py` (Composite Collections API, 200 records/batch, idempotent)
3. Phase 4a adds the Account DMO to the SDM and creates a `ManyToOne` relationship from the fact DLO to Account on the External ID
4. Concierge can now answer "which accounts are at risk?" and return results linked to real Account records

**Key patterns:**
- `ensure_external_id_field(sf_token, sf_instance, "Account", "Demo_External_ID__c")` — creates the custom field via Tooling API if it doesn't exist (one-time per org)
- `upsert_crm_records(sf_token, sf_instance, "Account", "Demo_External_ID__c", records)` — returns `{external_id: sf_record_id}` mapping
- Account DMO discovery: list DMOs in default dataspace, find `category: "Standard"` + name starts with `"Account"`
- Relationship: `joinType: "Auto"`, `cardinality: "ManyToOne"`, join on `entity_key__c` → `Demo_External_ID__c`

## Walkthrough document format (.docx)

Every demo build generates a `{slug}_demo_walkthrough.docx` file. **All walkthroughs must follow this consistent structure.** The sections included depend on the build type (Pulse vs Next), but the format within each section is identical across all demos. Reference implementation: `demos/mcgough_labor_productivity/mcgough_labor_productivity_demo_walkthrough.docx` (Pulse), `demos/bi_worldwide_sales_incentive/bi_worldwide_sales_incentive_concierge_walkthrough.docx` (Next).

### Section 1 — Demo Scenario (ALL builds)
- **H1:** "Demo Scenario"
- **H2:** "About {Company}" — one paragraph describing the company, their industry, scale, operating model, and why this use case matters to them
- **H2:** "Audience & Story" — audience line (persona + title), then a paragraph describing the story the demo tells (what's wrong, where it's concentrated, the root cause, and the counter-trend)

### Section 2 — Metrics Reference (ALL builds)
- **H1:** "Metrics Reference"
- Intro paragraph: "Each metric below includes its definition and why it matters to the client..."
- **H2** per metric with two bold-labeled paragraphs:
  - **"What it measures:"** — technical definition, aggregation type, signal direction, benchmarks/thresholds
  - **"Why it matters:"** — business context for this specific audience; what decision it informs, what it signals when it moves

### Section 3 — Demo Click Path (Pulse) / Concierge Prompts (Next)

**For Pulse builds — Demo Click Path:**
- **H1:** "Demo Click Path"
- Intro paragraph: "Each step below shows the action to take in Pulse followed by what the audience will see."
- **H2** per step with a drill-down title (Opening, Drill 1 — Sector, Root Cause — Trade, Counter-trend, Action, etc.)
- Each step has:
  - **"Action:"** (bold) — what to click/filter in Pulse
  - **"Audience sees:"** (bold) — what the sparkline/data reveals at this step

**For Tableau Next builds — Concierge Prompts:**
- **H1:** "Concierge Prompts"
- Intro paragraph: "Each step below shows the question to ask followed by the expected Concierge response..."
- Same H2-per-step structure, but with:
  - **"Ask:"** (bold) — the quoted question to ask Concierge
  - **"Expected response:"** (bold) — the AI's answer text (captured live from the Insights API when available, or written from known data when API is unavailable)

**Prompt/step sequence pattern** (adapt to use case):
1. Opening (surface-level metric view)
2. Drill 1 — primary dimension (where is it worst?)
3. Drill 2 — secondary dimension within the culprit
4. Root cause (what's driving it?)
5. Leading indicator (what moved first?)
6. Consequence (what broke downstream?)
7. Counter-trend (the benchmark that proves it's not systemic)
8. Financial impact (what's the cost?)
9. At-risk identification (who specifically needs action?)
10. Action/Summary (what to do next)

### Section 4 — Pulse Discover Questions (Pulse builds only)
- **H1:** "Pulse Discover Questions"
- Intro paragraph: "Each question below was asked to Pulse Discover at build time. The responses are live AI-generated answers based on the actual demo data."
- **H2** per question (Q1, Q2, Q3, etc.) with:
  - **"Ask:"** (bold) — the quoted question sent to the Pulse Discover API
  - **"Expected response:"** (bold) — the live AI-generated answer captured from the `POST /api/-/pulse/insights/brief` endpoint
- Questions should mirror the demo click path story arc (overall trend → worst segment → drill deeper → root cause → supporting metrics → counter-trend → action)
- These are **real API responses**, not hand-written — they are captured during the build by sending each question to the Brief API with the metric context

### Section 5 — Setting Up Goal Lines (Pulse builds with goals defined)
- **H1:** "Setting Up Goal Lines"
- Intro paragraph: "The datasource includes target columns for easy goal setup in the Pulse UI:"
- **Bulleted list** — one per metric with a goal: `{Metric}: select "{Goal Field}" → target {value}% → direction: {above/below}`
- Instructions: "To set up: Open metric → Edit → Goals → Select field from data → Choose the target column → Set direction."
- **Include only if** any `METRIC_CONFIG` entries have a `goal` key

### Section 6 — Business Preferences (SDM) — Tableau Next only
- **H1:** "Business Preferences (SDM)"
- Copy-paste instructions pointing to: Data 360 → Semantic Model → [SDM name] → AI Optimization → Manage Business Preferences
- Full `#`-prefixed text block with sections:
  - `# COMPANY CONTEXT` — what the data represents
  - `# METRIC DEFINITIONS` — how to interpret each metric name
  - `# DIMENSION GUIDANCE` — which dimensions to use for which question types
  - `# THRESHOLDS AND TARGETS` — numeric boundaries for "good" vs "bad"
  - `# QUESTION INTENT` — how to resolve ambiguous terms without asking the user
  - `# ANSWER STYLE` — "Lead with the answer, then supporting data. Do not open with questions back to the user."
  - `# TIME CONTEXT` — default comparison period

### Section 7 — Close the Loop (only if /close-loop was built)
- **H1:** "Close the Loop"
- Written by `close_loop.py build` (replaces any earlier version) — never hand-write it
- Intro paragraph: the action, why it fits the story, and the trigger
- **H2** per demo step (e.g. The alert lands / Close the loop / Owners act), each with:
  - **"Say:"** (bold) — the talk track: the line the presenter speaks, built from the story (worst segment, leading signal, counter-trend, owner)
  - **"Trigger:"** (bold) — what the presenter does to fire the action
  - **"Result:"** (bold) — what Salesforce / Slack does in response
- Preview it before deploying with `python close_loop.py plan --slug {slug}` (no org or .docx changes)

### Section 8 — Tableau Studio Skills (only if /studio was generated)
- **H1:** "Tableau Studio Skills"
- Written by `studio_skills.py generate` / `custom` (replaces any earlier version). Never hand-write it.
- Intro paragraph: what the skills are, the install command, `/reload-skills`, and the datasource to connect
- **H2** per skill (aio-autobuilder, aio-story, aio-audience, then any custom skills), each with:
  - **"Ask:"** (bold): the quoted example prompts
  - **"Expected response:"** (bold): what the skill does, in terms of this demo's story

### Summary of sections by build type

| Section | Pulse | Tableau Next | CRMA |
|---------|-------|-------------|------|
| 1. Demo Scenario | ✓ | ✓ | ✓ |
| 2. Metrics Reference | ✓ | ✓ | ✓ |
| 3. Demo Click Path / Concierge Prompts | ✓ (Click Path) | ✓ (Concierge) | ✓ (Click Path) |
| 4. Pulse Discover Questions | ✓ | — | — |
| 5. Setting Up Goal Lines | ✓ (if goals) | — | — |
| 6. Business Preferences (SDM) | — | ✓ | — |
| 7. Close the Loop | ✓ (if built) | ✓ (if built) | ✓ (if built) |
| 8. Tableau Studio Skills | ✓ (if generated) | ✓ (if generated) | ✓ (if generated) |

**Label rules — do NOT mix these:**
- **"Action:" / "Audience sees:"** → for UI navigation sections (Demo Click Path). Describes what to click and what the data shows visually.
- **"Ask:" / "Expected response:"** → for AI Q&A sections (Concierge Prompts, Pulse Discover Questions, Tableau Studio Skills). Describes questions asked to an AI and the AI's responses.
- **"Say:" / "Trigger:" / "Result:"** → for the Close the Loop section only. What the presenter says, what fires the follow-up, and what the org does.

## Visualization building (Tableau Next)

**ALWAYS build visualizations and a dashboard for Tableau Next demos.** Never ask the user whether to create them — they are required so that assets appear in the workspace. Without vizzes, the workspace appears empty in the Tableau Next UI and the SDM is only accessible through Data 360 (which the demo audience won't navigate to).

When building Tableau Next visualizations in `/build-demo`, ALWAYS use the template library:

```python
from viz_builder import build_viz_payload
from viz_validator import is_valid, print_results
from dashboard_builder import build_dashboard_payload, format_layout_preview

# Build a viz from template
payload = build_viz_payload(
    template_name="trend_over_time",  # or bar_by_category, stacked_bar, donut, etc.
    viz_name="enrollment_trend",
    viz_label="Enrollment Rate Over Time",
    sdm_api=sdm_api,
    ws_api=ws_api,
    do_api=do_api,
    field_map={"measure": "benefits_enrollment_rate", "date": "date"},
    dim_field_map=dim_field_map,
    measurements=measurements,
    style_overrides=BRAND,  # optional brand colors
)
```

**Available templates:** trend_over_time, multi_series_line, bar_by_category, stacked_bar, horizontal_bar, donut, scatter, heatmap, funnel

**Dashboard UX flow during /build-demo:**
1. Auto-select viz types from METRIC_CONFIG using `recommend_dashboard_vizzes()`
2. Show the plan using `format_layout_preview()` — user sees ASCII grid of metrics + vizzes
3. User approves, edits, or skips
4. Build each viz with `build_viz_payload()` (validation runs automatically)
5. Assemble dashboard with `build_dashboard_payload()`

## Two-pass viz creation (Tableau Next — high fidelity)

For demos requiring pixel-perfect vizzes, use the **two-pass pattern**: MCP creates the structure, REST PATCH applies the styling.

**Pass 1 — MCP `create_visualization`** (slim IR-v2 spec):
- Chart type, fields, shelves (rows/columns), encodings (Color/Size/Detail/Label)
- Sorts (`sortIntent`), filters, reference lines, number formats, mark color
- This gets ~80% of the visual right

**Pass 2 — REST PATCH** for styling the MCP can't set:
```python
import requests
from connections import sf_headers

# GET the viz, modify specific style properties, PATCH back
viz = requests.get(f'{instance}/services/data/v66.0/tableau/visualizations/{viz_id}?minorVersion=12',
    headers=sf_headers(token)).json()

# Example: set dual-axis (F1=Bar, F2=Line)
viz['visualSpecification']['marks']['fields'] = {
    'F1': {'type': 'Bar', 'isAutomatic': False, 'encodings': [], 'stack': {'isAutomatic': True, 'isStacked': True}},
    'F2': {'type': 'Line', 'isAutomatic': False, 'encodings': [], 'stack': {'isAutomatic': True, 'isStacked': False}},
}

# Strip read-only keys before PATCH
STRIP = {'id','createdBy','createdDate','lastModifiedBy','lastModifiedDate','permissions',
    'sourceVersion','templateSource','creationSource','url','isOriginal','semanticModel','useInlineModel'}
def clean(obj):
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if k not in STRIP}
    elif isinstance(obj, list):
        return [clean(i) for i in obj]
    return obj

requests.patch(f'{instance}/services/data/v66.0/tableau/visualizations/{viz_id}?minorVersion=12',
    headers=sf_headers(token), json=clean(viz))
```

**What PATCH can set that MCP cannot:**

| Property | Path in viz spec |
|----------|-----------------|
| Dual-axis mark types | `marks.fields.{fk}.type` (Line/Bar per measure) |
| Per-field mark colors | `style.marks.fields.{fk}.color.color` (hex) |
| Continuous color palettes | `style.encodings.fields.{fk}.colors = {type: "Continuous", palette: {start, end}}` |
| Hidden axes | `style.axis.fields.{fk}.isVisible = false` |
| Axis titles | `style.axis.fields.{fk}.titleText` |
| Mark size/line width | `style.marks.panes.size = {type: "Pixel", value: 3}` |
| Mark labels | `style.marks.panes.label.showMarkLabels = true` |
| Fit mode | `style.fit = "Entire"` |
| Reference lines | `visualSpecification.referenceLines.{key}` |

**PATCH gotchas:**
- `negativeValuesFormat: "NegativeSign"` is rejected — omit this field from number formats
- `isOriginal` on `view` is read-only — must strip
- `semanticModel` inside `dataSource` is huge and read-only — must strip
- Always GET → modify → PATCH (never build from scratch — the viz has server-generated fields you must preserve)

## Dashboard assembly (Tableau Next)

**Layout defaults for clean spacing:**
```python
layout = {
    "columnCount": 48, "rowHeight": 20, "maxWidth": 1200,
    "style": {"backgroundColor": "#FFFFFF", "gutterColor": "#F3F3F3", "cellSpacingX": 4, "cellSpacingY": 4}
}
```

**Widget gaps:** leave 2-row gaps between visual sections. Use column gaps (e.g. col 0-23 + col 25-47) instead of col 0-24 + col 24-48 to prevent widgets from touching.

**Metric widgets** can't be added via `create_dashboard` — use `add_widget_to_dashboard` with `semanticModelIdOrName` after creation. Same for text widgets (`textContent` only works on `add_widget_to_dashboard`).

**`edit_visualization` is nearly useless** — only `changeMarkType` works (and it's global, not per-field). Use REST PATCH instead for all viz styling.

## SDM replication (for /transfer-assets)

When cloning an SDM to another workspace or org:

1. **Create SDM with all DOs inline** (`semanticDataObjects` in create payload with `shouldIncludeAllFields: true`)
2. **Read BOTH SDMs** to build complete field apiName mapping — match by `dataObjectFieldName` (the `__c` suffixed DLO field name is stable; auto-generated apiNames are not)
3. **HTML-decode expressions** — `html.unescape()` all expressions from GET before POSTing (API returns `&gt;`, `&#39;`, `&quot;`)
4. **Create in dependency order**: parameters → calc dimensions → calc measurements → metrics → relationships
5. **Translate viz field references** using the DO + field mapping before creating vizzes
6. **Auto-generated apiName suffixes change on SDM recreation** — if an SDM is deleted and recreated, ALL field apiNames get new suffixes (e.g. `FullName1` → `FullName2`). Always read current state, never cache.

## Tableau Dashboard building (Pulse demos — .twb workbooks)

For Pulse demos, optionally publish a Tableau workbook (.twb) alongside the metrics. This uses `twb_builder.py` which generates valid Tableau XML and publishes via `server.workbooks.publish()`.

**How it works:**
- The `.twb` references the already-published datasource via a `class='sqlproxy'` connection (live reference by `content_url`, not an embed)
- Tableau Cloud resolves the connection server-side at render time
- Embedded Pulse metric tiles render live BAN numbers using the `com.tableau.pulse-metric` dashboard extension
- Requires "Allow Tableau-built extensions" enabled in site Settings → Extensions

**Supported chart types:**
- `horizontal_bar` — dimension sorted by measure (who is worst?)
- `bar` — vertical bar chart
- `line` — measure over time (monthly trend)
- `line` + `color_field` — multi-line, one line per dimension value (segment divergence)
- `dual_axis` — two measures on independent Y-axes, bar + line combo (leading indicator relationship)

**Dashboard layout auto-adapts:** 1=full width, 2=side-by-side, 3=2+1, 4=2×2 grid, 5+=3+N rows.

**Critical implementation details:**
- The datasource `content_url` includes a Tableau-appended timestamp — always use `get_datasource_content_url()` to look it up at runtime
- Pulse tile extension URL must be `tableau:/pulse/extension-assets/dashboard-metric/index.html` (not `main.trex`)
- Pulse tile zones must use `type-v2='dashboard-object'`
- The workbook must include a `<referenced-extensions>` manifest section after `</windows>` for Pulse tiles to load
- Instance IDs for tiles must be uppercase hex without hyphens
- Zone-before-zone-style rule (TD-017): child `<zone>` elements must precede `<zone-style>` in every container
- Window/zone/viewpoint lockstep: every worksheet name in a dashboard zone must also appear in `<windows>` and in the dashboard window's `<viewpoints>`
- **Column names MUST use labels (not snake_case field names):** The published `.hyper` datasource uses the original DataFrame column names (e.g. `"30-Day Unplanned Readmission Rate"` not `"30_day_unplanned_readmission_rate"`). All TWB `columns`, `rows_field`, `cols_field`, `color_field`, and sort references must use `mc["label"]` (the display name), not `mc["field"]` (the snake_case API name). Using `mc["field"]` causes "The sort on X is invalid" publish errors.
- **Golden config template:** See `demos/twb_config_template.json` for the reference pattern. Key rule: every field reference in the TWB config must match the `.hyper` column name exactly.

## Credentials & config

All credentials live in `config.json`. Never hardcode credentials in demo scripts. Always call `connections.load_config()` to read them.

The config has two top-level sections:
- `tableau` — server_url, site_name, pat_name, pat_secret
- `salesforce` — sf_login_url, client_id, client_secret, refresh_token, data_cloud_domain, ingestion_connector_name, connector_sf_id, connector_uuid_name

## Auth patterns

**Tableau Cloud (Pulse):**
```python
from connections import get_tableau_token, tableau_headers, tableau_pulse_headers
server, auth_token, site_id = get_tableau_token()
# Always sign out when done: server.auth.sign_out()
```

**Salesforce + Data Cloud (Tableau Next):**
```python
from connections import get_all_tokens, sf_headers, dc_headers
sf_token, sf_instance, dc_token, dc_domain = get_all_tokens()
# SF token for all Semantics/Workspace/Visualization API calls
# DC token only for Bulk Ingest API calls
```

## Key API endpoints

**Tableau Pulse:**
- `POST /api/-/pulse/definitions` — create metric (use `tableau_pulse_headers`)
- `GET /api/-/pulse/definitions/{id}/metrics` — get metric ID (use this for subscriptions, NOT definition ID)
- `POST /api/-/pulse/subscriptions:batchCreate` — subscribe group to metric
- `POST /api/{version}/sites/{site_id}/groups` (XML content-type) — create group

**Data Cloud (v62.0, SF token):**
- `GET/PUT /services/data/v62.0/ssot/connections/{id}/schema`
- `POST /services/data/v62.0/ssot/data-streams`
- `GET /services/data/v62.0/ssot/data-streams/{name}` — poll for `status == "ACTIVE"`

**Semantics (v65.0, SF token):**
- `POST /services/data/v65.0/tableau/workspaces`
- `POST /services/data/v65.0/ssot/semantic/models` — use `"dataspace": "default"` (not `dataspaceName`); SDM ignores `name` field, `apiName` is auto-generated from `label` (e.g. `Engine_Member_CSAT_4213`)
- `POST /services/data/v65.0/ssot/semantic/models/{sdm}/data-objects` — add DLOs with `dataObjectType: "dlo"` (lowercase); DO gets its own `apiName` (e.g. `Member_CSAT_Activity2`)
- `GET /services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}` — returns `semanticMeasurements` (auto-detected) and `semanticDimensions`; DC field names get `__c` suffix
- `PUT /services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}/measurements/{api}` — update aggregation; requires `apiName` + `dataObjectFieldName` in body; use `aggregationType: "Average"/"Sum"` (not `AGGREGATION_AVERAGE`)
- `POST /services/data/v65.0/ssot/semantic/models/{sdm}/relationships` — use `leftSemanticDefinitionApiName`/`leftFieldApiName` (DO apiName, field with `__c` suffix)
- `POST /services/data/v65.0/tableau/workspaces/{name}/assets`

**Visualizations + Dashboards (v66.0 + ?minorVersion=12, SF token):**
- `POST /services/data/v66.0/tableau/visualizations?minorVersion=12` — create viz; name/label/dataSource/workspace/fields/visualSpecification/view required
- `GET /services/data/v66.0/tableau/visualizations/{name}?minorVersion=12`
- `DELETE /services/data/v66.0/tableau/visualizations/{name}?minorVersion=12`
- `POST /services/data/v66.0/tableau/dashboards?minorVersion=12` — create dashboard
- `DELETE /services/data/v66.0/tableau/dashboards/{name}`
- Viz `objectName` = DO apiName (e.g. `Member_CSAT_Activity5`), `fieldName` = field without `__c` suffix? No — use `fieldName` as the bare field name; `objectName` from DO apiName
- Dashboard `widgets` must be a dict; `source` must have only `"name"` key (no label/type)

**Bulk Ingest (DC token, dc_domain):**
- `POST https://{dc_domain}/api/v1/ingest/jobs`
- Response key is `"data"` not `"jobs"`. States: Open → UploadComplete → InProgress → JobComplete / Failed
- New schemas take 15-30s to become available to Bulk API after DLO ACTIVE — retry with backoff on 404

## Brand colors (Tableau Next demos)

For real companies, look up brand guidelines and apply brand colors to dashboards and visualizations:

```python
BRAND = {
    "primary":   "#XXXXXX",   # dominant brand color
    "secondary": "#XXXXXX",   # accent
    "chart_bg":  "#FFFFFF",
    "text":      "#2E2E2E",
}
```

- **Dashboard `style.backgroundColor` / `gutterColor`**: use a light tint of the primary. For dark primaries, blend each channel 90% toward 255: `tint_channel = round(channel + (255 - channel) * 0.90)`.
- **Viz `style.shading.backgroundColor`**: `BRAND["chart_bg"]` (usually white)
- **Viz `FONTS` color fields**: `BRAND["text"]`
- If brand colors can't be found, fall back to `#F3F3F3` background and `#2E2E2E` text.

## Data generation rules

- **Grain**: one row per entity (person/account/product) per time period (weekly default, monthly for slower-moving metrics)
- **History**: 24 months back from today
- **Signal ramp**: use the full ramp function with configurable shape — `"accelerating"` is the default (see Signal design rules above for full implementation). The stub below is the minimal version; use the full version in all demos:
  ```python
  def signal_ramp(d, onset=-3, shape="accelerating", duration=3):
      months_from_today = (d.year - TODAY.year) * 12 + (d.month - TODAY.month)
      progress = min(1.0, max(0.0, (months_from_today - onset) / duration))
      return progress ** 2 if shape == "accelerating" else progress
  ```
- **Percentages**: always store as decimals (0.35 not 35)
- **Column names**: business-friendly with spaces and proper caps ("Approval Rate" not "approval_rate")
- **Date shifting (self-healing — both Tableau Next and Pulse)**: all demos use the same self-healing formula that shifts dates relative to the build date and `TODAY()`. The formula logic is identical across platforms — only the syntax differs:
  - **Tableau Next (SDM calculated dimension)**: `DATEADD("day", DATEDIFF("day", #<build_date>#, [DO_apiName].[date_field_apiName]), TODAY())` — uses double quotes, DO-qualified field references. Create via `POST /services/data/v65.0/ssot/semantic/models/{sdm}/calculated-dimensions` with `{apiName, label, expression, dataType: "Date"}`. Point metrics at it using `{"calculatedFieldApiName": "Display_Date"}` (not `tableFieldReference` — calc dims are SDM-level).
  - **Pulse (refresh-based)**: publish the `.hyper` directly (NOT a `.tdsx`). The Pulse metric's `time_dimension` references the raw `{"field": "Date"}` column. Set `use_dynamic_offset: True` via PATCH after creation so Pulse anchors to the most recent data point. To keep dates fresh, run `/refresh-dates` which regenerates data anchored to today and re-publishes the `.hyper` — existing metrics survive the overwrite and pick up fresh data automatically. Calculated fields via `.tdsx` do NOT work on Tableau Cloud (Pulse never indexes `.tdsx` packages — see Known Pitfalls).
  - **Date literal syntax**: `#YYYY-MM-DD#` (hash-delimited) in both platforms. `DATE(year, month, day)` with 3 args does NOT work in SDM expressions (causes "Arguments mismatch").
  - **Result — Tableau Next**: true self-healing — `TODAY()` evaluates at query time, dates always appear current automatically.
  - **Result — Pulse**: dates are correct at build time. Run `/refresh-dates` before a meeting if the demo is more than a week old (~30 seconds). `use_dynamic_offset` ensures Pulse never shows empty/broken data even without a refresh.
  - Save `display_date_api`, `date_field_api`, and `build_date` to the checkpoint.
- **Pulse datasource publish**: use the two-step self-healing pattern from `tdsx_builder.py`: (1) publish `.hyper` with stored `Date` column (indexes in seconds), (2) create metrics, (3) overwrite with `.tdsx` containing calc `Date = DATEADD('day', [Day_Offset], TODAY())`. This eliminates the need for Prep flows or scheduled refreshes. The Pulse metric `time_dimension` references `"Date"` which resolves to the calc field via its `name='[Date]'` attribute in the `.tds`. Publishing a `.tdsx` cold (without the `.hyper`-first step) does NOT work — Pulse cannot index `.tdsx` packages from scratch.
- **`METRIC_CONFIG`**: define all metrics in a single list of dicts with at minimum: `label`, `field`, `agg`, `description`, `why_it_matters`, `singular`, `plural`, `sentiment`, `pulse_agg`. The `description` is the technical definition (what it counts); `why_it_matters` is the customer-facing business reason (what decision it informs, what it signals when it moves). Both fields are used in the docx walkthrough. Optionally include `goal` dict: `{'value': 0.85, 'field': 'Attendance Target', 'name': 'Federal 85% Threshold', 'direction': 'above'}` — if present, add a constant target column to the datasource and document the goal setup in the walkthrough.
- **Pulse goals/thresholds**: the REST API `datasource_goals` field does NOT work programmatically (always returns 400 "Invalid request"). Goals must be set in the Pulse UI. To make this trivial: include constant target columns in the `.hyper` (e.g. `Attendance Target = 0.85`), then document the field-to-metric mapping in the walkthrough with a "Setting Up Goal Lines" section. This takes under 2 minutes in the UI.
- **Surrogate `Record ID`**: for upsert-based bulk ingest, always add a `Record ID` column formatted as `{entity_id}_{date_YYYYMMDD}`. This is the primary key for the ingest stream — without it, daily/weekly rows for the same entity overwrite each other on upsert.

## Metric classification (always classify before writing code)

| Type | Aggregation | Time default | Example |
|------|-------------|--------------|---------|
| Flow | AGGREGATION_SUM | Year to Date | Volume, Revenue, Originations |
| Rate/Average | AGGREGATION_AVERAGE | Last Month | Approval Rate, Retention % |
| Snapped | AGGREGATION_SUM (on snapshot rows) | Last Month | AUM, Pipeline, Headcount |

## Known pitfalls

- Visualizations: **REST PATCH is the only way to set advanced viz styling** — the MCP `edit_visualization` tool only supports `changeMarkType` (and it's global, not per-field). For dual-axis, per-field colors, continuous palettes, hidden axes, mark sizes, etc., use `PATCH /services/data/v66.0/tableau/visualizations/{id}?minorVersion=12` with GET → modify → PATCH pattern. Strip read-only keys: `id`, `createdBy`, `createdDate`, `lastModifiedBy`, `lastModifiedDate`, `permissions`, `sourceVersion`, `templateSource`, `creationSource`, `url`, `isOriginal`, `semanticModel`, `useInlineModel`.
- Visualizations: **`negativeValuesFormat: "NegativeSign"` rejected** — the PATCH endpoint rejects this value in `numberFormatInfo`. Omit the field entirely; the engine uses the correct default.
- Visualizations: **MCP BasicViz endpoint not directly accessible** — the `/services/data/v67.0/tableau/visualizations/basic` POST endpoint used internally by MCP returns `METHOD_NOT_ALLOWED` when called directly via REST. Must use the MCP `create_visualization` tool for slim-spec viz creation.
- Visualizations: **Calc field `level` required for MCP viz creation** — model-level calc measures MUST include `level` when a `function` is supplied. `AggregateFunction` for `UserAgg` calcs, `Row` for `Sum`/`Avg`/`CountD`/`Max`/`Min` calcs, `Lod` for LOD calcs, `TableCalc` for table calcs. Calc dimensions used as measures (e.g. with `CountD` function) also need `level: "Row"`. Omitting causes "must include its semantic level" error.
- Visualizations: **`Mdy` date function** in original viz packages maps to `DateTruncMonth` in MCP slim spec.
- Dashboards: **Metric widgets require `add_widget_to_dashboard`** — the `create_dashboard` endpoint does not accept `semanticModelIdOrName` on metric widgets. Create the dashboard with viz widgets inline, then add metric widgets via `add_widget_to_dashboard` which supports `semanticModelIdOrName`.
- Dashboards: **Text widget `textContent` requires `add_widget_to_dashboard`** — the `create_dashboard` endpoint rejects `textContent` on text widgets. Add text widgets after creation.
- Dashboards: **`cellSpacingX/Y: 0` makes widgets touch** — always use `cellSpacingX: 4, cellSpacingY: 4` with `gutterColor: "#F3F3F3"` for readable layouts. Leave 2-row gaps between visual sections and 1-2 column gaps between side-by-side widgets.
- SDM replication: **Auto-generated field apiNames change on SDM recreation** — if an SDM is deleted and recreated with the same DOs, the field apiNames get different numeric suffixes (e.g. `FullName1` → `FullName2`). Never cache field maps across SDM deletions. Always read the CURRENT SDM state via `GET /ssot/semantic/models/{sdm}?includeModelContent=true`.
- SDM replication: **HTML entity encoding in expressions** — expressions returned by the SDM GET API are HTML-encoded (`&gt;` for `>`, `&#39;` for `'`, `&quot;` for `"`). Must call `html.unescape()` before POSTing to create calc fields. Without this, ~90% of calc fields fail with "token recognition error at: '&'".
- SDM replication: **Parameters must be created before calc fields** — calc dimensions/measurements that reference `[Parameters].[param_name]` fail if the parameter doesn't exist yet. Create all parameters first, then calc dims, then calc meas, then metrics, then relationships.
- Pulse: **2026.2 payload validation changes** — `POST /api/-/pulse/definitions` now requires fields that were previously optional and enforces aggregation/format consistency. Missing any of these causes a generic 400 "Invalid request" with no detail. Required fields as of 2026.2: (1) `insights_options` key must be present (can be `{"show_insights": true, "settings": []}`); (2) `comparisons` key must be present (can be `{"comparisons": [{"compare_config": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD", "comparison_period_override": []}, "index": "0"}]}`); (3) `AGGREGATION_AVERAGE` requires `is_running_total: false` — combining AVERAGE with `is_running_total: true` returns 400; (4) `NUMBER_FORMAT_TYPE_PERCENTAGE` cannot be used programmatically at all — both POST and PATCH reject it with 400 "Invalid request" regardless of aggregation type (tested with AVERAGE, SUM, and COUNT on us-east-1 and 10ax pods as of 2026.2). Workaround: create metrics with `NUMBER_FORMAT_TYPE_NUMBER`, store values as decimals (0.62 = 62%), then manually change Number Format to "Percentage" in the Pulse UI (Edit → Core Definition → Number format → Percentage). The UI handles the ×100 display automatically. Always set `is_running_total: false` for rate/average metrics and `true` only for flow/sum metrics that accumulate over time.
- Pulse: **Self-healing date pattern (`.hyper` → metrics → `.tdsx` overwrite)** — Pulse does NOT index `.tdsx` packages published cold (from scratch). However, if you first publish a `.hyper` with a stored `Date` column (indexes in seconds), create metrics against it, and THEN overwrite with a `.tdsx` containing a calculated `Date = DATEADD('day', [Day_Offset], TODAY())`, the metrics survive and the calc Date resolves — self-healing forever with no Prep flow or scheduling. The key: metrics must be created BETWEEN the `.hyper` publish and the `.tdsx` overwrite. Use `tdsx_builder.py`: `publish_hyper_for_indexing()` → create metrics → `convert_to_self_healing()`. The `.tds` inside the `.tdsx` must set `name='[Date]'` on the calc column so Pulse resolves `time_dimension.field = "Date"` correctly.
- Pulse: **Default time filter (Month to Date) cannot be changed via API** — the `measurement_period.granularity` field on the metric spec appears settable (putting `GRANULARITY_BY_YEAR` first in `allowed_granularities` causes the API to return `GRANULARITY_BY_YEAR` in the metric's `measurement_period`), but the Pulse UI always defaults to "Month to Date" regardless. This is a UI-level user preference — each user must manually select "Year to Date" in the Filter dropdown on first view. Document this in the walkthrough as a first-time setup step. There is no known API workaround as of 2026.2.
- Pulse: **Comparison period is tied to the filter period** — the `TIME_COMPARISON_PREVIOUS_PERIOD` comparison dynamically changes based on the active filter. With "Month to Date" filter, comparison shows "vs. prior month." With "Year to Date" filter, comparison shows "vs. prior year (same period)." You cannot independently set the comparison period separately from the filter period — they are linked. If you want month-over-month comparison, the filter must be set to Month to Date. If you want year-over-year, filter must be Year to Date.
- Pulse: **Platform indexing outages** — If metric creation returns 400 "Not Found" or the Pulse catalog returns HTTP 400706 after a datasource is successfully published, the issue is the Tableau Cloud indexing service being degraded on that pod (not a code or data problem). This is a platform-side issue that resolves on its own (typically within hours). Symptoms: datasource shows as Published in the REST API, but Pulse UI shows "Waiting on Tableau Cloud indexing" and the metric creation endpoint cannot find the datasource fields. Guidance to the user: (1) check trust.salesforce.com for platform status; (2) wait and retry — the checkpoint will skip completed phases; (3) confirm indexing recovery by going to Pulse → New Metric → search for the datasource name → if fields appear, indexing is back. Do NOT re-publish the datasource (it's already there) — just retry the metric creation phase once indexing recovers.
- Pulse: `extension_options` are now **required** in the POST create payload on 2026.2+. Include `allowed_dimensions`, `allowed_granularities`, `offset_from_today`, `correlation_candidate_definition_ids`, and `use_dynamic_offset` in the POST. Then PATCH separately to set `use_dynamic_offset: true` (it's accepted in POST but not always persisted). PATCH uses `Content-Type: application/vnd.tableau.metricqueryservice.v1.UpdateDefinitionRequest+json`.
- Pulse: `allowed_dimensions` must be a **flat list of field name strings** — e.g. `["Region", "Program Type", "Vertical"]`. Using objects like `[{"field": "Region"}]` causes 400 "Invalid request" with no detail. The API returns them as strings in GET responses and expects the same format on POST.
- Pulse: Definition creation response wraps everything under a `"definition"` key. The ID is at `resp["definition"]["metadata"]["id"]`. The metric ID is at `resp["definition"]["metrics"][0]["id"]` (no separate GET needed). Parse with: `resp = r.json(); def_id = resp["definition"]["metadata"]["id"]; metric_id = resp["definition"]["metrics"][0]["id"]`. Do NOT use `resp.get("metadata", {}).get("id")` (returns None — there's no top-level `metadata`).
- Pulse: Subscriptions payload changed in 2026.2 — use `{"metric_id": "...", "followers": [{"group_id": "..."}]}` (flat structure). The old `{"subscriptions": [{"follower": {"group_id": "..."}, "metric_id": "..."}]}` wrapper format now returns 400.
- Pulse: Do NOT include `temporality: 'TEMPORALITY_UNSPECIFIED'` in the create payload — it causes 400 "Bad Request" on Tableau Cloud 26.2+. This field is read-only (returned by GET but rejected on POST).
- Pulse: Use metric ID (from `GET /definitions/{id}/metrics`) for subscriptions — NOT definition ID
- Pulse: Granularities must include MONTH + QUARTER + YEAR minimum or slicers won't load
- Pulse: `name` must be top-level in the definition payload, not inside `metadata`
- Data Cloud: DLO status polling must use the **stream name** (e.g. `bi_worldwide_incentive_fact_bi_worldwide_incentive_fact_B79A6FF2`), NOT the DLO name (e.g. `bi_worldwide_incentive_fact_bi_B79A6FF2__dll`). The endpoint `GET /services/data/v62.0/ssot/data-streams/{name}` returns 400 "DataStream found null" when given a DLO name. Save the stream name from creation/discovery and use it for polling. Status is nested under `dataLakeObjectInfo.status`. After reaching ACTIVE, wait an additional 30s before submitting bulk ingest jobs — schema propagation lag can cause 404s even after ACTIVE is reported.
- Data Cloud: Dashboard `widgets` must be a dict, not a list
- Data Cloud: Dashboard page `name` must be a UUID string (`str(uuid.uuid4())`)
- Data Cloud: `"headers": {}` in visualization style causes 400 — omit entirely
- Salesforce External Client App requires scopes: api, sfap_api, cdp_query_api, cdp_ingest_api, refresh_token; must check "Enable Authorization Code and Credentials Flow"; PKCE can be left checked (our OAuth flow supports PKCE via code_challenge/code_verifier). If dashboard creation returns 500 "For input string: null" and the layout format is correct, check whether the token has `wave_api` scope (introspect endpoint) — adding extra scopes to the Connected App can trigger stricter enforcement; re-run the OAuth flow to get a token with the broader scope set
- Semantics: SDM `name` field is ignored — `apiName` is auto-generated from `label`; capture `apiName` from POST response
- Semantics: `dataObjectType` in data-objects POST must be lowercase `"dlo"` (not `"DLO"`)
- Semantics: Relationship payload uses `leftSemanticDefinitionApiName`/`rightSemanticDefinitionApiName` (DO apiName) + `leftFieldApiName`/`rightFieldApiName` (field name with `__c` suffix)
- Semantics: Measurement PUT requires `aggregationType: "Average"` or `"Sum"` (title case, not `AGGREGATION_AVERAGE`); also requires `apiName` + `dataObjectFieldName` in body
- Semantics: `/calculated-measurements` POST at SDM level requires DO-qualified field references in expressions: `AVG([DO_apiName].[measurement_apiName])` e.g. `AVG([Member_CSAT_Activity7].[csat_score8])` — bare field names, `__c`-suffixed names, and label names all fail with "Missing reference"
- Semantics: Metrics (`_mtc`) require a `_clc` calculated measurement as the `measurementReference.calculatedFieldApiName` — they cannot reference auto-detected measurement apiNames directly; create the `_clc` at SDM level first, then create the metric
- Semantics: Metric `timeDimensionReference` for SDM-level calculated dimensions (like Display Date) must use `{"calculatedFieldApiName": "Display_Date"}` — NOT `{"tableFieldReference": {...}}`. Using tableFieldReference with a calculated dim name causes 400 "Table field with table name (X) and field name (Display_Date) was not found in the model" because calc dims are SDM-level, not DO-level
- Semantics: SDM-level list endpoints use `items` key (not `semanticModels` or `calculatedMeasurements`) — always read `r.json().get('items', [])`
- Semantics: Relationship join criteria (`leftFieldApiName`/`rightFieldApiName`) are silently dropped for IngestAPI DLO relationships — `criteria` always comes back `[]`; SDM will throw "No join criteria found" at query time. Workaround: denormalize dimension fields into the fact table and only add the fact DLO to the SDM (no relationship needed)
- Semantics: Relationship `joinType` must be `"Auto"` — explicit types like `"LeftOuter"`, `"LEFT_OUTER"`, or `"Left"` cause 400 "Relationship must have the 'AUTO' join type." Explicit join types are only permitted for relationships within logical views.
- Semantics: CRM standard objects (Account, Contact, etc.) must be added to SDMs with `dataObjectType: "dlo"` and the full DLO name including `__dll` suffix (e.g. `Account_Home__dll`). Using `"dmo"` causes "DMO/CI/DLO does not exist" even when the object is active in the data lake.
- Bulk Ingest: `sourceName` must be the short connector name (e.g. `analytics_builder_demo`), not the UUID name (`analytics_builder_demo_d964ca78_...`)
- Bulk Ingest: API is CSV-based — submit jobs with `Content-Type: application/json`, then PUT batches with `Content-Type: text/csv`, then PATCH to `UploadComplete`. Response from job creation has `"id"` at top level (not nested under `"data"`).
- Bulk Ingest: Only `upsert` and `delete` operations are supported — `insert` causes 400. For daily-grain fact tables where the natural key is non-unique (e.g. `client_id` alone), add a surrogate `record_id` column (`date_clientid`) and use it as the stream PK. Set it as the `isPrimaryKey` field in the stream's `dataLakeFieldInputRepresentations` and insert it as the first column of the fact DataFrame.
- Bulk Ingest: **X-prefix for digit-leading field names** — Data Cloud auto-prepends `X` to schema field names that start with a digit (e.g. `30day_readmission_rate` becomes `X30day_readmission_rate`). CSV upload headers must match the stored schema name exactly. If the CSV header is `30day_readmission_rate` but the schema field is `X30day_readmission_rate`, the column data silently ingests as NULL. Fix: prepend `X` in both `_clean_field_name()` (schema registration) and the CSV column rename before upload: `if clean[0].isdigit(): clean = "X" + clean`.
- Schema registration: PUT payload uses key `"schemas"` (not `"objects"`). Each schema needs `name`, `label`, `schemaType: "IngestApi"`, and fields with `dataType` (not `type`). Field dataType values: `"Text"`, `"Number"`, `"Date"`.
- Schema registration: If the target schema already exists on the connector, skip the PUT entirely. Other schemas on the same connector may contain platform-injected reserved fields (`DataSourceId`, `DataSourceObjectId`) that the API returns in GET but rejects on PUT — stripping them causes "Removing ExternalDataTranField not allowed", keeping them causes "reserved field" validation error.
- Stream creation: requires full nested payload — `connectorInfo.connectorDetails.name` must be the UUID connector name (not short name). Capture `dataLakeObjectInfo.name` from the POST response — it's the auto-generated DLO name (e.g. `trinet_benefits_fact_trinet_ben_D5EE9465__dll`), not the schema name.
- DO creation: POST to `/ssot/semantic/models/{sdm}/data-objects` requires both `dataLakeObjectName` AND `dataObjectName` (set both to the DLO name). Missing `dataObjectName` causes 400.
- Measurement PUT: requires `label` field in the body alongside `apiName`, `dataObjectFieldName`, `aggregationType`. Missing `label` causes 500.
- CLC creation: minimal payload causes 500. Required fields: `apiName`, `label`, `aggregationType: "UserAgg"`, `dataType: "Number"`, `decimalPlace: 4`, `directionality: "Up"`, `displayCategory: "Continuous"`, `expression`, `filters: []`, `isOverrideBase: False`, `isVisible: True`, `level: "AggregateFunction"`, `overriddenProperties: []`, `semanticDataType: "None"`.
- Metric creation: requires `timeDimensionReference.tableFieldReference` with `fieldApiName` (date dimension's auto-generated apiName, e.g. `date1`) and `tableApiName` (DO apiName). Also requires `timeGrains`, `aggregationType: "UserAgg"`. Build `dim_field_map` by iterating `semanticDimensions` — strip `__c` from `dataObjectFieldName` to get the base name key; value is the dimension `apiName`.
- Metric dimensions (drilldown/why): to enable dimension drilldowns on a metric (so Concierge and Tableau Next can answer "why"), set BOTH `additionalDimensions` AND `insightsSettings.insightsDimensionsReferences` to the same list of `{"tableFieldReference": {"fieldApiName": dim_api, "tableApiName": do_api}}` entries. Setting only `insightsDimensionsReferences` causes 400 "Insight dimension is missing from the metric additional dimensions". Both fields are required together.
- Visualizations: `dataSource` must be the SDM apiName (e.g. `TriNet_Benefits_Analytics_8c9`), not the DO apiName. Using DO apiName causes 400 "Semantic object not found".
- Visualizations: `fieldName` in viz fields must use the DO dimension/measurement apiNames from `semanticDimensions`/`semanticMeasurements` (e.g. `date1`, `benefits_enrollment_rate__c`), not raw DC field names. Build a field map from the DO GET response.
- Visualizations: `style.encodings.fields` must have an entry for every measure field (F2, etc.) — an empty `{}` causes 400 "encodings style is required for [field]". Each entry needs `defaults.format.numberFormatInfo` with `decimalPlaces`, `displayUnits`, `includeThousandSeparator`, `negativeValuesFormat`, `prefix`, `suffix`, `type`.
- Visualizations: `fieldName` in fields uses the bare field name (no `__c`); `objectName` is the DO apiName (auto-generated, e.g. `Member_CSAT_Activity5`) — get it from Phase 7 response and pass it through
- Visualizations: `visualSpecification.style` must omit `"headers": {}` — an empty headers object causes 400; only include `headers` if it has actual content
- Dashboard: every widget name referenced in `page_widgets` (layout positions) must have a corresponding entry in `widgets_dict`. Container widgets must be in `widgets_dict` with `type: "container"` and `parameters.widgetStyle`. Missing container entries cause 500 "Cannot invoke EntityObject.getId()".
- Dashboard: each widget dict entry needs `"actions": []` and `"name"` fields alongside `type`, `source`, `parameters`.
- Calculated measurements/metrics at v66.0: `POST /services/data/v66.0/ssot/semantic/models/{sdm}/calculated-measurements` still returns 500 for IngestAPI DLOs; stick with PUT on auto-detected measurements (v65.0 pattern)
- Dashboard pattern: use `widgets` dict + `layouts` array (not `pages` at top level); metric widgets need `source: {name: mtc_api}` (no `type`) + `parameters.metricOption.sdmApiName`; viz widgets need `source: {name: viz_api}` (no `type`); `workspaceIdOrApiName` is the correct field (not `workspace`); adding `type` or `label` inside `source` causes `JSON_PARSER_ERROR`
- Dashboard layouts (REQUIRED fields): the `layouts` array entry MUST include `columnCount: 72`, `maxWidth: 1200`, `rowHeight: 10`, and a `style` object with `backgroundColor`, `gutterColor`, `cellSpacingX: 8`, `cellSpacingY: 8`. Omitting any of these causes 500 "For input string: null". The grid is 72 columns wide (not 36). Minimal working layout: `{"name": "default", "columnCount": 72, "maxWidth": 1200, "rowHeight": 10, "style": {"backgroundColor": "#F3F3F3", "gutterColor": "#F3F3F3", "cellSpacingX": 8, "cellSpacingY": 8}, "pages": [...]}`
- Pulse group creation: parse group ID with explicit `if grp is None` checks — never use `element or fallback` on an XML Element (evaluates element truthiness, returns None silently). Pattern: `grp = root.find(".//{http://tableau.com/api}group"); if grp is None: grp = root.find(".//group")`. Fail loudly if group ID is still None after creation.
- Pulse subscriptions: check and log each `batchCreate` response individually — a 201 with `group_id: null` silently succeeds but does nothing. Always verify group_id is non-null before posting subscriptions.
- Pulse subscriptions: `POST /api/-/pulse/subscriptions:batchCreate` requires standard `Content-Type: application/json` — do NOT reuse `h_pulse` (which has the metric-creation Content-Type). Use a separate header dict `{"x-tableau-auth": token, "Accept": "application/json", "Content-Type": "application/json"}` for all subscription calls. Using the metric-creation Content-Type causes 404.
- Pulse definitions pagination: use `next_page_token` not `page=N` — the Pulse definitions API returns a `next_page_token` field; the `page=N` parameter returns empty results after the first page. Pattern: loop with `params={'page_size': 100, 'page_token': npt}` until `next_page_token` is empty.
- Pulse group cleanup: before creating a new group, delete all existing groups whose name starts with `{Company} |` — same as project/definition cleanup. Use `GET /api/{version}/sites/{site_id}/groups?pageSize=100` (XML), parse with namespace-aware `find`, then `DELETE /groups/{id}` for each match.
- Business preferences (Concierge nouns): after creating all metrics, PUT each one back with `insightsSettings.singularNoun` and `insightsSettings.pluralNoun` filled in. Pattern: GET the metric, update the fields, strip read-only fields (`id`, `createdBy`, `createdDate`, `lastModifiedBy`, `lastModifiedDate`), PUT back to `PUT /services/data/v66.0/ssot/semantic/models/{sdm}/metrics/{api}?minorVersion=12`. Define noun pairs in `METRIC_CONFIG` alongside the other metric fields.
- Field descriptions (AI optimization): every DO measurement and dimension should have a `description` set so Concierge understands what each field means. Include `description` in the measurement PUT payload (same call as `aggregationType`). For dimensions, loop and PUT each one to `PUT /services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}/dimensions/{dim_api}` with `apiName`, `label`, `dataObjectFieldName`, `description`. Required body for dimension PUT: `apiName`, `label`, `dataObjectFieldName`, `description` — missing any causes a 400. Write descriptions from the Concierge's perspective: "Use this field to..." or "This metric represents..." so they read as instructions to the AI.
- Business preferences (SDM-level, Concierge context): the SDM has a free-text "Business Preferences" field (Data 360 → Semantic Model → [SDM] → AI Optimization → Manage Business Preferences) that shapes how Concierge interprets questions. **Now auto-deployed via MCP** in Phase 5b using `update_semantic_model_business_preferences`. Format: one atomic instruction per line, each prefixed with `# `. Up to 30,000 characters. Generate with `generate_business_preferences()` in `builder.py`. Preferences are **intent-driven instructions** — they tell Concierge what to do when it hears business jargon, not what the data contains (field descriptions already cover that). Categories:
  - **Jargon resolution:** `# 'Worst performing' means the highest value for '30-Day Readmission Rate' — higher is worse for this metric.`
  - **Default behaviors:** `# When asked about performance, always include Service Line in the breakdown.`
  - **Metric relationships:** `# When asked 'why' readmission rate is changing, look at Preventable Readmission Rate first — it is the leading indicator.`
  - **Sorting/display:** `# When ranking service lines, sort by 30-Day Readmission Rate descending — worst first.`
  - **Counter-trends:** `# Hospital-Free Days trends opposite to other metrics — use it as the benchmark when asked 'is everything declining'.`
  - **Answer style:** `# Always lead with the answer, then supporting data. Never open with a question back to the user.`
  Do NOT duplicate field descriptions (what a metric measures) — those belong on the measurement/dimension `description` field, not in business preferences. If MCP is not configured, the preferences are still generated and included in the walkthrough HTML with manual paste instructions as a fallback.
- SDM Enhancement phase (Phase 5b): runs after metrics creation, uses MCP to: (1) update all measurement descriptions, labels, aggregations, and sentiment; (2) update all dimension labels and descriptions with story-specific values; (3) hide system fields (cdp_sys_SourceVersion, DataSource, DataSourceObject, record_id, entity_id, KQ_record_id, day_offset); (4) deploy business preferences. Guarded by `cp["sdm_enhanced"]` checkpoint key. Falls back gracefully if MCP is not configured — the REST-based descriptions from Phase 4 still apply.
- Checkpoint/resume: write a `{slug}_checkpoint.json` file in the demo folder after each major phase (CSV, Pulse, Next) completes. On script start, load the checkpoint and skip phases already marked done. This prevents re-ingesting data or re-creating assets when a run is interrupted mid-way.
- Visualizations (VizQL format): `visualSpecification` must use `"layout": "Vizql"` with `columns`/`rows` as field-key arrays (e.g. `["F1"]`, `["F2"]`), NOT an `"encodings"` dict. Required top-level keys: `columns`, `rows`, `forecasts`, `legends`, `measureValues`, `referenceLines`, `marks`, `style`.
- Visualizations `style` required keys: `axis`, `encodings`, `fieldLabels`, `fit`, `fonts`, `headers`, `lines`, `marks`, `referenceLines`, `shading`, `showDataPlaceholder`, `title`. Missing any one causes a 400 "Value required for [key]".
- Visualizations `style.headers`: requires `columns`, `rows` (both `{"mergeRepeatedCells": True, "showIndex": False}`), and `fields` (map of field key → `{"hiddenValues": [], "isVisible": True, "showMissingValues": False}`). Every dimension field that appears in `columns` or as a color grouping dimension (even if it's just in `columns` for grouping) MUST have an entry in `style.headers.fields` — omitting it causes 400 `"headers.fields" style is required for the "[FieldName]" ("[Fkey]") field`.
- Visualizations `style.marks.headers`: use `_marks_headers_style()` pattern: `{"color": {"color": ""}, "isAutomaticSize": True, "label": {"canOverlapLabels": False, "marksToLabel": {"type": "All"}, "showMarkLabels": False}, "range": {"reverse": False}, "size": {"isAutomatic": True, "type": "Pixel", "value": 13}}`.
- Visualizations `marks.panes` (top-level, not in style): `{"encodings": [], "isAutomatic": False, "stack": {"isAutomatic": True, "isStacked": False}, "type": "Line"|"Bar"|"Square"|"Circle"}`. The `style.marks.panes` is a separate object with color/label/range/size — not the chart type. `"isAutomatic": False` is correct here; `True` is only valid on top-level `marks.fields` entries (and those entries also require an `"encodings"` key — but for most charts `marks.fields: {}` empty dict is correct and accepted).
- Visualizations Square (highlight table) and Circle (scatter): both work with `marks.fields: {}` (empty). Use `type: "Square"` for highlight tables and `type: "Circle"` for scatter plots. The `marks.fields` entries with `{"isAutomatic": True/False}` cause 400 `Value required for [stack]` or `Value required for [type]` errors — use the empty dict instead.
- Visualizations color grouping (scatter, multi-line): place the color dimension `F3` in `columns` BEFORE any continuous measure fields — `columns: ["F3", "F1"]`. A dimension cannot come after continuous fields in `columns` or `rows`; doing so causes 400 `"[FieldName]" field can't appear after continuous fields in "columns"`. For multi-line charts where F3 is the line color, use `columns: ["F1", "F3"]` (date first, then the categorical dim) — this is accepted because date is discrete, not continuous.
- Visualizations `style.fonts` format: use `{"actionableHeaders": {"color": "#2E2E2E", "size": 13}, "axisTickLabels": ..., "fieldLabels": ..., "headers": ..., "legendLabels": ..., "markLabels": ..., "marks": ...}`. Do NOT use the docx-style font format (`{"fontName": ..., "fontSize": ..., "isBold": ...}`) — that is only for Google Docs and `.docx` outputs. Using the wrong format causes 400 `Unrecognized field "body"` (or similar).
- Visualizations `marks.headers` (in `visualSpecification.marks`, NOT `style.marks`): the `type` field must always be `"Text"` — never `"Line"` or `"Bar"`. The chart type belongs only in `marks.panes.type`. Using `"Line"` or `"Bar"` in `marks.headers.type` causes 400 `Invalid value for mark type of the visualization header`.
- Dashboard `page_widgets` layout array: use lowercase `colspan`/`rowspan` and `name` (not `columnSpan`/`rowSpan`/`widgetName`). The correct shape is `{"name": "widget_key", "row": 0, "column": 0, "rowspan": 15, "colspan": 36}`. Using camelCase keys causes 400 `Unrecognized field "widgetName"`.
- Visualizations `style.lines`: must use explicit keys (e.g. `axisLine`, `fieldLabelDividerLine`, etc.) — `{"referenceLines": {}}` is not valid here; use `{}` or the `LINES` dict pattern.
- Visualizations `legends`: required at top level of `visualSpecification`; use `{}` when no color dimension, or `{"F3": {"isVisible": True, "position": "Right", "title": {"isVisible": True}}}` when a color field is present.
- Retry cleanup: apply the same pattern to ALL phases that create assets (workspace/SDM in phase4, vizzes/dashboard in phase6). Track every created asset in `cp["all_ws_apis"]`, `cp["all_sdm_apis"]`, `cp["all_viz_apis"]`, `cp["all_dash_apis"]`. At the start of each phase (when not skipped), DELETE everything in those lists, reset to `[]`, clear related `cp` keys (ws_api, sdm_api, do_api, etc.), save checkpoint, then create fresh. Append each new asset immediately after creation and save checkpoint. Never clear these lists when resetting a phase — they must survive across retries.
- Asset ownership: only DELETE assets whose names appear in the checkpoint tracking lists. If asked to delete something not in those lists, always confirm with the user first.
- Dashboard filters: the `type: "filter"` widget with `parameters: {"filterType": ..., "sdmApiName": ...}` causes 400 `Unrecognized field "filterType"` — filter widget parameters are not documented and this API shape is not supported. Omit filter widgets from programmatic dashboard creation; they must be added manually in the Tableau Next UI if needed.
- Template deployer (Z Layout): the template has 5 viz widget slots but only 4 viz definitions. `visualization_4` has no source — `prepare_viz_payloads()` auto-generates `Detail_Bar_2` by cloning `Horizontal_Bar` with `team1` (dim[0]). The field_map remaps it to the target dim. If the 3rd detail slot is still empty after deploy, check that `Detail_Bar_2` was created and wired.
- Template deployer (text widgets): `label_map` is applied to viz payloads only by default. Dashboard text widgets (`text_1` through `text_8`) need explicit handling in `prepare_dashboard_payload()` — use the `label_map` and `detail_headers` parameters. Without this, "Section Subheader" and "Metric by system_source" appear as raw template text.
- Template deployer (Display_Date): the Trend_Line viz references `Display_Date` (SDM calc dim) with no `objectName`. If the target SDM's calc dim has a different apiName, add `field_map["Display_Date"] = cp["display_date_api"]`. Without this mapping, the trend line renders empty (axes visible but no data).
- Template deployer (viz titles): template viz labels are generic ("Trend Line", "Donut Chart"). Add entries like `label_map["Trend Line"] = f"{primary_metric} Over Time"` to set meaningful titles. The label_map substitution in `prepare_viz_payloads()` catches these.
- Data generation: **always use `dimension_values` from the story config** — `generate_data()` reads `story_config.get("dimension_values", {})` first, then falls back to pattern-matching dim names. Without this, dimensions like "Service Line" or "Facility Type" produce generic placeholders ("Service Line 1", "Service Line 2") instead of realistic values from the research phase.
- Pulse goals/thresholds: the `datasource_goals` field in `POST /api/-/pulse/definitions` does NOT accept any non-empty payload — tested with `basic_specification`, `threshold_basic_specification`, and minimal `name`+`benchmark_sentiment_type` — all return 400 "Invalid request". PATCH/PUT on existing definitions also fails. Goals must be set in the Tableau Cloud Pulse UI (metric → Edit → Goals → select field from data). Workaround: include constant target columns in the datasource (e.g. `Attendance Target = 0.85`) and document the setup in the walkthrough.
- Pulse Insights API (BAN + Brief): every Pulse demo should include a post-build phase that calls the Pulse Insights API to capture live AI summaries and append them to the `.docx` walkthrough as a "Live Insights" section. Key patterns:
  - **Endpoint**: `POST /api/-/pulse/insights/ban` (Big Ass Number) and `POST /api/-/pulse/insights/brief` (AI conversational)
  - **Content-Type**: MUST use the vendor MIME type — `application/vnd.tableau.pulse.insightsservice.v1.GenerateInsightBundleBANRequest+json` for BAN, `application/vnd.tableau.pulse.embeddingsservice.v1.GenerateInsightBriefRequest+json` for brief. Using `application/json` returns `validation_code: 400952 / Bad Request`.
  - **`now` field**: MUST be date-only `YYYY-MM-DD` (e.g. `date.today().isoformat()`). A full ISO timestamp with time component (e.g. `2026-05-23T10:00:00Z`) causes `validation_code: 400952 / Bad Request`.
  - **brief action_type**: Use `"ACTION_TYPE_SUMMARIZE"` with `"role": "ROLE_USER"`. `ACTION_TYPE_QUESTION` returns "Invalid request".
  - **Payload structure**: BAN uses `{"bundle_request": {"version": 1, "options": {...}, "input": {"metadata": ..., "metric": {...}}}}`. Brief uses `{"language": "LANGUAGE_EN_US", "locale": "LOCALE_EN_US", "now": ..., "messages": [{"content": ..., "action_type": "ACTION_TYPE_SUMMARIZE", "role": "ROLE_USER", "metric_group_context": [ctx], "metric_group_context_resolved": false}]}`.
  - **`language` and `locale` fields**: MUST use enum format — `"LANGUAGE_EN_US"` and `"LOCALE_EN_US"` (not `"en"` or `"en_US"`). Plain string values cause 400 "Invalid request" with no detail.
  - **metric context structure (CRITICAL)**: The `metric_group_context` array entries MUST use a nested `metadata` + `metric` wrapper — NOT flat keys. Build from live definition GET (`/api/-/pulse/definitions/{def_id}`) and metric GET (`/api/-/pulse/definitions/{def_id}/metrics`). Pattern:
    ```python
    metric_context = {
        "metadata": {
            "definition_id": def_id,
            "metric_id": metric_id,
            "name": f"{COMPANY} — {metric_label}",
            "tags": []
        },
        "metric": {
            "definition":           d.get("specification", {}),
            "extension_options":    d.get("extension_options", {}),
            "metric_specification": m.get("specification", {}),
            "representation_options": d.get("representation_options", {}),
        }
    }
    ```
    Using flat keys (e.g. `{"definition": ..., "extension_options": ..., "metric_specification": ...}` without the `metadata`/`metric` wrapper) causes 400 "Invalid request" with no detail. The GET headers for fetching definition/metric data should use standard `{"x-tableau-auth": token, "Accept": "application/json"}` — NOT the Pulse vendor Content-Type.
  - **Brief response**: Success returns 201 with `{"markup": "..."}`. The `markup` field contains HTML spans (`<span data-type="metric">...</span>`), bold markers (`**...**`), markdown headers, and reference links (`[[1]](uuid|metric_id)`). Strip these for clean text: `re.sub(r'<span[^>]*>(.*?)</span>', r'\1', markup)` then `re.sub(r'\[\[\d+\]\]\([^)]+\)', '', text)` then `re.sub(r'\*\*', '', text)`.
  - **Save def_ids**: During Pulse metric creation, save both `pulse_metric_ids` AND `pulse_def_ids` to the checkpoint so the insights phase can look them up.
  - **generativeAiPulse**: The REST API GET on the site may incorrectly return `False` for this flag even when it's enabled via the Tableau Cloud UI. If all insight endpoints return 400 "Bad Request" with `validation_code: 400952`, ask the user to enable Pulse AI in Tableau Cloud Settings → AI Features. The `pulsePremiumInsightsEnabled: true` and `pulsePremiumGAIEnabled: true` flags in `siteSettings` are the authoritative indicator.
- Close the loop: **Flow API names can't contain `__` or end in `_`** — Salesforce reserves double underscores for namespaces and custom-object suffixes, and a deploy fails on them. Slugs like `barrett_distribution_demand_forecasting`, truncated to 28 characters, end in `_` and then gain `__Followup`. `close_loop.flow_names()` strips any trailing `_` after truncating. Never build Flow names by hand.
- Close the loop: **`slackPostMessage` can be usable in Flows while missing from `/actions/standard`.** In some orgs (e.g. Slack demo-bundle orgs), `GET /actions/standard/slackPostMessage` returns 404 "Invalid Action Type", yet an Active Flow using it deploys fine. `preflight()` falls back to a check-only deploy of a probe Flow (`_slack_action_deployable`) and then uses `SLACK_FLOW_INPUTS`. All four inputs are required: `slackAppIdForToken` (an `A…` app ID, not the Slack `E…` Enterprise ID in `Slack__mdt`), `slackWorkspaceIdForToken` (a `T…` team ID), `slackConversationId` (`C…`), `slackMessage`. The fastest way to find the right app and workspace IDs is an existing Flow built in Flow Builder: `SELECT Id FROM Flow WHERE Status='Active'` via Tooling, then read `Metadata.actionCalls[].inputParameters` where `actionType` contains `slack`. Draft Flows skip input validation, so always probe with `<status>Active</status>`.
- Close the loop: **Callouts can't share a transaction with the record DML.** The Slack post (`slackPostMessage`) is a callout, so it can't run in the same synchronous transaction that created the Tasks/Case/Campaign. That's why the Notify Flow is record-triggered on an `AsyncAfterCommit` scheduled path and isn't a step inside the follow-up Flow. Keep the follow-up Flow DML-only.
- CRM upsert: **A new External ID field gets no field-level security for the running user.** The Tooling API creates `Account.Demo_External_ID__c`, but describe hides it and `PATCH /composite/sobjects/Account/Demo_External_ID__c` returns 404 forever (no amount of propagation wait helps). `ensure_external_id_field()` now calls `grant_field_access()`, which creates and assigns the `AIO_Demo_Field_Access` permission set with read/edit on the field. It also detects a field that exists in Tooling but is hidden from describe, and grants access instead of re-creating it.
- Semantics: **`OutlierDetection` and `RecordLevelTable` insight types need an identifying dimension.** Enabling either on a metric's `insightsSettings.insightTypes` causes 400 "You must define an identifying dimension when the RecordLevelTable or OutlierDetection insight types are enabled." Leave both out of the insight types list.
- Semantics: **Dimension `description` has a length limit (~200 chars after HTML encoding).** The API double-encodes `&` as `&amp;amp;` before checking, so a description with ampersands overflows sooner than its raw length suggests. The PUT returns 400 "data value too large". Keep dimension descriptions short and avoid `&`.
- Workspace share: **`{"shareWith": "ALL_USERS", "accessLevel": "View"}` is rejected** with 400 `Unrecognized field "shareWith"` on `/tableau/records/{ws}/shares`. GET on that endpoint needs the workspace record ID (`1Dy…`, from `GET /tableau/workspaces/{api}`), not its apiName. The working POST schema isn't known yet; share in the UI (Share → All Internal Users → View) until it's found.
- Close the loop: **Pin the story with `cp["story"]` when the analysis picks the wrong drill path.** `analyze_story()` takes the single worst segment across all text columns, so a dimension that tracks the intended one (e.g. Account Size vs Location Count Band) can take over the talk track, and `metrics[1:4]` can name a lagging metric as the "leading signal". Set `story.dimensions` (leave out the duplicate dimension) and `story.supporting_metrics` (labels, leading indicator first) in the demo's docs phase.
- Studio: **Run `/studio` after `/close-loop`, or re-run it.** `demo-story.md` gets its Close the Loop section only if `{slug}_close_loop_payload.json` exists at generate time. Installed copies in Tableau Studio don't update either, so re-run `install` (then `/reload-skills`) after regenerating.
- Studio: **Self-healing `.tdsx` has no stored Date.** Its Date is a calc on `Day_Offset`, so the extract only has `Day_Offset`. `studio_skills.py` rebuilds `Date` from `Day_Offset` when importing a `.hyper`/`.tdsx`/published datasource. Outside sources without a date column need `--set date_field=...`.
- Studio: **Outside data has no `METRIC_CONFIG`.** `analyze_story` falls back to the first numeric column, which is often a count. Always confirm `primary_metric` and `entity_field` with `--set` for CSV/.hyper/datasource sources.
