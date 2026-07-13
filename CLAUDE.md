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
- `prep_flow_builder.py` — Tableau Prep flow generator for auto-refreshing Pulse dates (builds .tflx with embedded CSV + DATEADD(Day_Offset, TODAY()) calc + PublishExtract output)

## Walkthrough document format (.docx)

Every demo build generates a `{slug}_demo_walkthrough.docx` file. **All walkthroughs must follow this consistent 4-section structure** (reference implementation: `demos/bi_worldwide_sales_incentive/bi_worldwide_sales_incentive_concierge_walkthrough.docx`):

### Section 1 — Demo Scenario
- **H1:** "Demo Scenario"
- **H2:** "About {Company}" — one paragraph describing the company, their industry, scale, operating model, and why this use case matters to them
- **H2:** "Audience & Story" — audience line (persona + title), then a paragraph describing the story the demo tells (what's wrong, where it's concentrated, the root cause, and the counter-trend)

### Section 2 — Metrics Reference
- **H1:** "Metrics Reference"
- Intro paragraph: "Each metric below includes its definition and why it matters to the client..."
- **H2** per metric with two bold-labeled paragraphs:
  - **"What it measures:"** — technical definition, aggregation type, signal direction, benchmarks/thresholds
  - **"Why it matters:"** — business context for this specific audience; what decision it informs, what it signals when it moves

### Section 3 — Concierge Prompts (Tableau Next) / Demo Click Path (Pulse)

**For Tableau Next builds (Concierge):**
- **H1:** "Concierge Prompts"
- Intro paragraph: "Each step below shows the question to ask followed by the expected Concierge response..."
- **H2** per step with a drill-down title (Opening, Drill 1 — Region, Reveal — Concentration, Root Cause, Counter-trend, Action, etc.)
- Each step has:
  - **"Ask:"** (bold) — the quoted question to ask Concierge
  - **"Expected response:"** (bold) — the AI's answer text (captured live from the Insights API when available, or written from known data when API is unavailable)

**For Pulse-only builds (no Concierge):**
- **H1:** "Demo Click Path"
- Same H2-per-step structure, but with:
  - **"Action:"** (bold) — what to click/filter in Pulse
  - **"Audience sees:"** (bold) — what the sparkline/data reveals at this step

**Prompt sequence pattern** (adapt to use case):
1. Opening (surface-level metric view)
2. Drill 1 — primary dimension (where is it worst?)
3. Reveal — concentration check (is it everywhere or concentrated?)
4. Root cause (what's driving it?)
5. Drill 2 — secondary dimension (which sub-segment?)
6. Drill 3 — tertiary dimension (tenure band, cost tier, etc.)
7. Counter-trend (the benchmark that proves it's not systemic)
8. Cross-metric correlation (safety, belonging, alerts confirming the story)
9. At-risk identification (who specifically needs action?)
10. Action/Summary (what to do next)

### Section 4 — Business Preferences (SDM) — Tableau Next only
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

**Omit Section 4 for Pulse-only builds** (Pulse has no Concierge/Business Preferences).

## Visualization building (Tableau Next)

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
- **Pulse datasource publish**: always publish the `.hyper` file directly — `server.datasources.publish(ds_item, hyper_path, "Overwrite")`. Do NOT publish a `.tdsx` for Pulse. Pulse indexes `.hyper` datasources in seconds but takes 2+ hours (or fails entirely) to index `.tdsx` packages. The Pulse metric `time_dimension` should reference the raw `Date` column, not a calculated `Display Date` field.
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

- Pulse: **2026.2 payload validation changes** — `POST /api/-/pulse/definitions` now requires fields that were previously optional and enforces aggregation/format consistency. Missing any of these causes a generic 400 "Invalid request" with no detail. Required fields as of 2026.2: (1) `insights_options` key must be present (can be `{"show_insights": true, "settings": []}`); (2) `comparisons` key must be present (can be `{"comparisons": [{"compare_config": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD", "comparison_period_override": []}, "index": "0"}]}`); (3) `AGGREGATION_AVERAGE` requires `is_running_total: false` — combining AVERAGE with `is_running_total: true` returns 400; (4) `NUMBER_FORMAT_TYPE_PERCENTAGE` cannot be used with `AGGREGATION_SUM` — use `NUMBER_FORMAT_TYPE_NUMBER` for rate metrics or use `AGGREGATION_AVERAGE` with percentage format. Always set `is_running_total: false` for rate/average metrics and `true` only for flow/sum metrics that accumulate over time.
- Pulse: ALWAYS publish `.hyper` directly for Pulse datasources — NEVER publish `.tdsx`. Pulse indexes `.hyper` files in seconds but NEVER indexes `.tdsx` packages on Tableau Cloud (tested: 14+ hours with no indexing). Publishing `.tdsx` causes metric creation to fail with 404 "Not Found". The `time_dimension` must reference the raw `Date` column. Calculated fields (like `Display Date`) are not available to Pulse — use `/refresh-dates` to keep dates current instead.
- Pulse: **Default time filter (Month to Date) cannot be changed via API** — the `measurement_period.granularity` field on the metric spec appears settable (putting `GRANULARITY_BY_YEAR` first in `allowed_granularities` causes the API to return `GRANULARITY_BY_YEAR` in the metric's `measurement_period`), but the Pulse UI always defaults to "Month to Date" regardless. This is a UI-level user preference — each user must manually select "Year to Date" in the Filter dropdown on first view. Document this in the walkthrough as a first-time setup step. There is no known API workaround as of 2026.2.
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
- Bulk Ingest: `sourceName` must be the short connector name (e.g. `analytics_builder_demo`), not the UUID name (`analytics_builder_demo_d964ca78_...`)
- Bulk Ingest: API is CSV-based — submit jobs with `Content-Type: application/json`, then PUT batches with `Content-Type: text/csv`, then PATCH to `UploadComplete`. Response from job creation has `"id"` at top level (not nested under `"data"`).
- Bulk Ingest: Only `upsert` and `delete` operations are supported — `insert` causes 400. For daily-grain fact tables where the natural key is non-unique (e.g. `client_id` alone), add a surrogate `record_id` column (`date_clientid`) and use it as the stream PK. Set it as the `isPrimaryKey` field in the stream's `dataLakeFieldInputRepresentations` and insert it as the first column of the fact DataFrame.
- Schema registration: PUT payload uses key `"schemas"` (not `"objects"`). Each schema needs `name`, `label`, `schemaType: "IngestApi"`, and fields with `dataType` (not `type`). Field dataType values: `"Text"`, `"Number"`, `"Date"`.
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
- Business preferences (SDM-level, Concierge context): the SDM has a free-text "Business Preferences" field in the UI (Data 360 → Semantic Model → [SDM] → AI Optimization → Manage Business Preferences) that shapes how Concierge interprets questions. There is no public REST API for this field — it is UI-only. Generate the text during the build as `#`-prefixed instruction lines, save it to the checkpoint as `"business_preferences"`, include it in a dedicated section of the `.docx` walkthrough, and print it in the final summary with a clear callout for the user to paste it in manually. **Always include a `# QUESTION INTENT` section** that defines how to resolve ambiguous words without asking the user to clarify — e.g. `"worst" = steepest percentage-point decline over 12 weeks`, `"most affected" = steepest decline segmented by the most recently mentioned dimension`, `"flag for outreach" = filter to the known culprit segment`. Without this, Concierge asks clarifying questions back to the user (e.g. "what do you mean by worst?") when queried on a single metric outside of a full dashboard context. The QUESTION INTENT section prevents this by giving Concierge a default interpretation for every term it might encounter. Also always include a `# ANSWER STYLE` line: `Lead with the answer, then supporting data. Do not open with questions back to the user.`
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
- Pulse goals/thresholds: the `datasource_goals` field in `POST /api/-/pulse/definitions` does NOT accept any non-empty payload — tested with `basic_specification`, `threshold_basic_specification`, and minimal `name`+`benchmark_sentiment_type` — all return 400 "Invalid request". PATCH/PUT on existing definitions also fails. Goals must be set in the Tableau Cloud Pulse UI (metric → Edit → Goals → select field from data). Workaround: include constant target columns in the datasource (e.g. `Attendance Target = 0.85`) and document the setup in the walkthrough.
- Pulse Insights API (BAN + Brief): every Pulse demo should include a post-build phase that calls the Pulse Insights API to capture live AI summaries and append them to the `.docx` walkthrough as a "Live Insights" section. Key patterns:
  - **Endpoint**: `POST /api/-/pulse/insights/ban` (Big Ass Number) and `POST /api/-/pulse/insights/brief` (AI conversational)
  - **Content-Type**: MUST use the vendor MIME type — `application/vnd.tableau.pulse.insightsservice.v1.GenerateInsightBundleBANRequest+json` for BAN, `application/vnd.tableau.pulse.embeddingsservice.v1.GenerateInsightBriefRequest+json` for brief. Using `application/json` returns `validation_code: 400952 / Bad Request`.
  - **`now` field**: MUST be date-only `YYYY-MM-DD` (e.g. `date.today().isoformat()`). A full ISO timestamp with time component (e.g. `2026-05-23T10:00:00Z`) causes `validation_code: 400952 / Bad Request`.
  - **brief action_type**: Use `"ACTION_TYPE_SUMMARIZE"` with `"role": "ROLE_USER"`. `ACTION_TYPE_QUESTION` returns "Invalid request".
  - **Payload structure**: BAN uses `{"bundle_request": {"version": 1, "options": {...}, "input": {"metadata": ..., "metric": {...}}}}`. Brief uses `{"language": "LANGUAGE_EN_US", "locale": "LOCALE_EN_US", "now": ..., "messages": [{"content": ..., "action_type": "ACTION_TYPE_SUMMARIZE", "role": "ROLE_USER", "metric_group_context": [ctx], "metric_group_context_resolved": false}]}`.
  - **`language` and `locale` fields**: MUST use enum format — `"LANGUAGE_EN_US"` and `"LOCALE_EN_US"` (not `"en"` or `"en_US"`). Plain string values cause 400 "Invalid request" with no detail.
  - **metric context**: Build from the live definition GET (`/api/-/pulse/definitions/{def_id}`) and metric GET (`/api/-/pulse/definitions/{def_id}/metrics`) — use `d.get("specification")` for `definition`, `d.get("extension_options")` for `extension_options`, `m.get("specification")` for `metric_specification`, `d.get("representation_options")` for `representation_options`.
  - **Save def_ids**: During Pulse metric creation, save both `pulse_metric_ids` AND `pulse_def_ids` to the checkpoint so the insights phase can look them up.
  - **generativeAiPulse**: The REST API GET on the site may incorrectly return `False` for this flag even when it's enabled via the Tableau Cloud UI. If all insight endpoints return 400 "Bad Request" with `validation_code: 400952`, ask the user to enable Pulse AI in Tableau Cloud Settings → AI Features. The `pulsePremiumInsightsEnabled: true` and `pulsePremiumGAIEnabled: true` flags in `siteSettings` are the authoritative indicator.
