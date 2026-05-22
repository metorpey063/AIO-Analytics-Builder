# Analytics Builder

A Claude Code skill for Tableau and Salesforce Solutions Engineers to rapidly build compelling demo assets across three platforms: Tableau Pulse, Tableau Next, and Salesforce Data Cloud.

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
- **Cross segment combinations for compound stories** — the most compelling drill paths combine two dimensions. Example: "down 20% overall → down 30% in East region → down 45% in East + Mid-Market". Implement with a 2D multiplier table: `SIGNAL_MULTIPLIERS = {("East", "Mid-Market"): 2.2, ("East", "Enterprise"): 1.1, ("West", "Mid-Market"): 0.4, ...}`. Apply as `signal * SIGNAL_MULTIPLIERS.get((region, size_band), 1.0)`.
- **At least one counter-trend segment** — include one segment that bucks the trend (flat or improving). This makes the overall decline feel like a concentration problem, not a systemic one — which is a more actionable story. "It's not everyone, it's specifically President's Club in the East."
- **Vary noise by segment** — lower-volume segments should have more noise (`np.random.uniform(-0.04, 0.04)`) to look realistic; high-volume segments should be smoother (`-0.01, 0.01`).
- Supporting metrics should lag the primary signal slightly — they answer "why" after the audience has already seen "what"

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

- **Grain**: one row per entity (person/account/product) per month
- **History**: 24 months back from today
- **Signal ramp**: engineered trend decline over last 6 months to create a demo story
  ```python
  def signal_ramp(d, onset=-6, duration=6):
      months_from_today = (d.year - TODAY.year) * 12 + (d.month - TODAY.month)
      if months_from_today <= onset: return 0.0
      return min(1.0, (months_from_today - onset) / duration)
  ```
- **Percentages**: always store as decimals (0.35 not 35)
- **Column names**: business-friendly with spaces and proper caps ("Approval Rate" not "approval_rate")
- **Date shifting**: always add a `display_date` calc field so demos stay current after build

## Metric classification (always classify before writing code)

| Type | Aggregation | Time default | Example |
|------|-------------|--------------|---------|
| Flow | AGGREGATION_SUM | Year to Date | Volume, Revenue, Originations |
| Rate/Average | AGGREGATION_AVERAGE | Last Month | Approval Rate, Retention % |
| Snapped | AGGREGATION_SUM (on snapshot rows) | Last Month | AUM, Pipeline, Headcount |

## Known pitfalls

- Pulse: Use metric ID (from `GET /definitions/{id}/metrics`) for subscriptions — NOT definition ID
- Pulse: Granularities must include MONTH + QUARTER + YEAR minimum or slicers won't load
- Pulse: `name` must be top-level in the definition payload, not inside `metadata`
- Data Cloud: DLO status is nested under `dataLakeObjectInfo.status`, not at the top level of the data-stream response — always read `body.get("dataLakeObjectInfo", {}).get("status") or body.get("status", "UNKNOWN")` to handle both shapes. After reaching ACTIVE, wait an additional 30s before submitting bulk ingest jobs — schema propagation lag can cause 404s even after ACTIVE is reported.
- Data Cloud: Dashboard `widgets` must be a dict, not a list
- Data Cloud: Dashboard page `name` must be a UUID string (`str(uuid.uuid4())`)
- Data Cloud: `"headers": {}` in visualization style causes 400 — omit entirely
- Salesforce External Client App requires scopes: api, sfap_api, cdp_query_api, cdp_ingest_api, refresh_token; must check "Enable Authorization Code and Credentials Flow"; must UNCHECK "Require PKCE" (it defaults to on)
- Semantics: SDM `name` field is ignored — `apiName` is auto-generated from `label`; capture `apiName` from POST response
- Semantics: `dataObjectType` in data-objects POST must be lowercase `"dlo"` (not `"DLO"`)
- Semantics: Relationship payload uses `leftSemanticDefinitionApiName`/`rightSemanticDefinitionApiName` (DO apiName) + `leftFieldApiName`/`rightFieldApiName` (field name with `__c` suffix)
- Semantics: Measurement PUT requires `aggregationType: "Average"` or `"Sum"` (title case, not `AGGREGATION_AVERAGE`); also requires `apiName` + `dataObjectFieldName` in body
- Semantics: `/calculated-measurements` POST at SDM level requires DO-qualified field references in expressions: `AVG([DO_apiName].[measurement_apiName])` e.g. `AVG([Member_CSAT_Activity7].[csat_score8])` — bare field names, `__c`-suffixed names, and label names all fail with "Missing reference"
- Semantics: Metrics (`_mtc`) require a `_clc` calculated measurement as the `measurementReference.calculatedFieldApiName` — they cannot reference auto-detected measurement apiNames directly; create the `_clc` at SDM level first, then create the metric
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
- Pulse group creation: parse group ID with explicit `if grp is None` checks — never use `element or fallback` on an XML Element (evaluates element truthiness, returns None silently). Pattern: `grp = root.find(".//{http://tableau.com/api}group"); if grp is None: grp = root.find(".//group")`. Fail loudly if group ID is still None after creation.
- Pulse subscriptions: check and log each `batchCreate` response individually — a 201 with `group_id: null` silently succeeds but does nothing. Always verify group_id is non-null before posting subscriptions.
- Pulse subscriptions: `POST /api/-/pulse/subscriptions:batchCreate` requires standard `Content-Type: application/json` — do NOT reuse `h_pulse` (which has the metric-creation Content-Type). Use a separate header dict `{"x-tableau-auth": token, "Accept": "application/json", "Content-Type": "application/json"}` for all subscription calls. Using the metric-creation Content-Type causes 404.
- Pulse definitions pagination: use `next_page_token` not `page=N` — the Pulse definitions API returns a `next_page_token` field; the `page=N` parameter returns empty results after the first page. Pattern: loop with `params={'page_size': 100, 'page_token': npt}` until `next_page_token` is empty.
- Pulse group cleanup: before creating a new group, delete all existing groups whose name starts with `{Company} |` — same as project/definition cleanup. Use `GET /api/{version}/sites/{site_id}/groups?pageSize=100` (XML), parse with namespace-aware `find`, then `DELETE /groups/{id}` for each match.
- Business preferences (Concierge nouns): after creating all metrics, PUT each one back with `insightsSettings.singularNoun` and `insightsSettings.pluralNoun` filled in. Pattern: GET the metric, update the fields, strip read-only fields (`id`, `createdBy`, `createdDate`, `lastModifiedBy`, `lastModifiedDate`), PUT back to `PUT /services/data/v66.0/ssot/semantic/models/{sdm}/metrics/{api}?minorVersion=12`. Define noun pairs in `METRIC_CONFIG` alongside the other metric fields.
- Field descriptions (AI optimization): every DO measurement and dimension should have a `description` set so Concierge understands what each field means. Include `description` in the measurement PUT payload (same call as `aggregationType`). For dimensions, loop and PUT each one to `PUT /services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}/dimensions/{dim_api}` with `apiName`, `label`, `dataObjectFieldName`, `description`. Required body for dimension PUT: `apiName`, `label`, `dataObjectFieldName`, `description` — missing any causes a 400. Write descriptions from the Concierge's perspective: "Use this field to..." or "This metric represents..." so they read as instructions to the AI.
- Business preferences (SDM-level, Concierge context): the SDM has a free-text "Business Preferences" field in the UI (Data 360 → Semantic Model → [SDM] → AI Optimization → Manage Business Preferences) that shapes how Concierge interprets questions. There is no public REST API for this field — it is UI-only. Generate the text during the build as `#`-prefixed instruction lines, save it to the checkpoint as `"business_preferences"`, include it in a dedicated section of the `.docx` walkthrough, and print it in the final summary with a clear callout for the user to paste it in manually.
- Checkpoint/resume: write a `{slug}_checkpoint.json` file in the demo folder after each major phase (CSV, Pulse, Next) completes. On script start, load the checkpoint and skip phases already marked done. This prevents re-ingesting data or re-creating assets when a run is interrupted mid-way.
- Visualizations (VizQL format): `visualSpecification` must use `"layout": "Vizql"` with `columns`/`rows` as field-key arrays (e.g. `["F1"]`, `["F2"]`), NOT an `"encodings"` dict. Required top-level keys: `columns`, `rows`, `forecasts`, `legends`, `measureValues`, `referenceLines`, `marks`, `style`.
- Visualizations `style` required keys: `axis`, `encodings`, `fieldLabels`, `fit`, `fonts`, `headers`, `lines`, `marks`, `referenceLines`, `shading`, `showDataPlaceholder`, `title`. Missing any one causes a 400 "Value required for [key]".
- Visualizations `style.headers`: requires `columns`, `rows` (both `{"mergeRepeatedCells": True, "showIndex": False}`), and `fields` (map of field key → `{"hiddenValues": [], "isVisible": True, "showMissingValues": False}`).
- Visualizations `style.marks.headers`: use `_marks_headers_style()` pattern: `{"color": {"color": ""}, "isAutomaticSize": True, "label": {"canOverlapLabels": False, "marksToLabel": {"type": "All"}, "showMarkLabels": False}, "range": {"reverse": False}, "size": {"isAutomatic": True, "type": "Pixel", "value": 13}}`.
- Visualizations `marks.panes` (top-level, not in style): `{"encodings": [], "isAutomatic": True, "stack": {"isAutomatic": True, "isStacked": False}, "type": "Line"|"Bar"}`. The `style.marks.panes` is a separate object with color/label/range/size — not the chart type.
- Visualizations `marks.headers` (in `visualSpecification.marks`, NOT `style.marks`): the `type` field must always be `"Text"` — never `"Line"` or `"Bar"`. The chart type belongs only in `marks.panes.type`. Using `"Line"` or `"Bar"` in `marks.headers.type` causes 400 `Invalid value for mark type of the visualization header`.
- Dashboard `page_widgets` layout array: use lowercase `colspan`/`rowspan` and `name` (not `columnSpan`/`rowSpan`/`widgetName`). The correct shape is `{"name": "widget_key", "row": 0, "column": 0, "rowspan": 15, "colspan": 36}`. Using camelCase keys causes 400 `Unrecognized field "widgetName"`.
- Visualizations `style.lines`: must use explicit keys (e.g. `axisLine`, `fieldLabelDividerLine`, etc.) — `{"referenceLines": {}}` is not valid here; use `{}` or the `LINES` dict pattern.
- Visualizations `legends`: required at top level of `visualSpecification`; use `{}` when no color dimension, or `{"F3": {"isVisible": True, "position": "Right", "title": {"isVisible": True}}}` when a color field is present.
- Retry cleanup: apply the same pattern to ALL phases that create assets (workspace/SDM in phase4, vizzes/dashboard in phase6). Track every created asset in `cp["all_ws_apis"]`, `cp["all_sdm_apis"]`, `cp["all_viz_apis"]`, `cp["all_dash_apis"]`. At the start of each phase (when not skipped), DELETE everything in those lists, reset to `[]`, clear related `cp` keys (ws_api, sdm_api, do_api, etc.), save checkpoint, then create fresh. Append each new asset immediately after creation and save checkpoint. Never clear these lists when resetting a phase — they must survive across retries.
- Asset ownership: only DELETE assets whose names appear in the checkpoint tracking lists. If asked to delete something not in those lists, always confirm with the user first.
- Dashboard filters: every Tableau Next dashboard must include filter widgets in the first row — (1) a Date filter and (2) a segmentation filter (Region, State, Vertical, Segment, or whichever categorical dimension fits the use case). Place them at the top of the layout before metric tiles and vizzes, spanning roughly half the grid width each at `rowspan: 5`.
