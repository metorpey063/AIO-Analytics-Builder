# /deploy-sales-insights — Deploy Sales Insights to Any Org

Deploy the standalone Sales Insights solution to ANY Salesforce org with Data Cloud. No managed app required. Uses CSV-backed DLOs, not standard DMOs. Contains the full SDM with ~300 calculated fields, 11 data objects, 11 relationships, 15 parameters, ~80 visualizations across 12 dashboards, and 6 metrics.

---

## What this does (updated)

This skill deploys a fully standalone version of Tableau's Sales Insights solution. Unlike the original managed-app approach (which required the SalesInsights app and Package & Deploy API), this creates everything from scratch via REST API:

1. **Ingests data** into CSV-backed DLOs via Bulk Ingest API (from a source org or custom data)
2. **Creates a standalone SDM** with all 11 data objects, 11 relationships, 15 parameters, ~90 calc dimensions, ~170 calc measurements, and 6 metrics
3. **Creates ~80 visualizations** from full viz spec payloads stored in the package file
4. **Creates 12 dashboards** with complete widget layouts, filters, parameters, metric tiles, dynamic tokens, and page navigation
5. **Result:** pixel-perfect Sales Insights with no managed app dependency — works on any org with Data Cloud

---

## Two deployment modes

### Mode 1: Source-org clone (production-quality)
- Export real data from a source org that has the managed Sales Insights app installed
- Uses Data Cloud Query API to pull from the source org's DMOs
- Ingest into target org's DLOs via Bulk Ingest API
- Create SDM, vizzes, dashboards from the standalone package
- Result: pixel-perfect clone of the source org's Sales Insights, populated with real data

### Mode 2: Custom data (new use cases)
- Generate or provide custom CRM data matching the data contract
- Ingest via Bulk Ingest API into the same DLO schema
- Deploy same dashboards with different data story
- See `demos/sales_insights_packages/data_contract.json` for the required schema
- See `demos/sales_insights_packages/CUSTOMIZATION_GUIDE.md` for which fields to customize

---

## Prerequisites

The **target org** must have:
- **Data Cloud enabled** with an ingest connector configured (create one via `/setup` if needed)
- A profile configured via `/setup` (Salesforce OAuth credentials with `cdp_ingest_api` scope)

The target org does **NOT** need:
- The Sales Insights managed app (that is the whole point)
- Existing CRM data
- Any manual dashboard or SDM configuration

For **Mode 1** (source-org clone), you also need:
- A **source org** with the Sales Insights managed app installed and populated with data
- A second profile configured in `config.json` for the source org (with `cdp_query_api` scope)

---

## Package file format

The package is stored as `demos/sales_insights_packages/Sales_Insights_Standalone_package.json`. Key structure:

```json
{
  "templateId": "Forecast_Insights",
  "apiVersion": "67.14",
  "requirements": {
    "metrics": [...],
    "fields": [...],
    "listParameters": [...]
  },
  "components": {
    "visualizations": { ... },
    "dashboard": { ... },
    "semanticModel": { ... },
    "dimensions": [ ... ],
    "measurements": [ ... ],
    "metrics": [ ... ]
  }
}
```

### Component breakdown

| Component | Count | Description |
|-----------|-------|-------------|
| `components.visualizations` | ~80 | Full viz specs keyed by name, with template placeholders |
| `components.dashboard` | 12 | Dashboard definitions with widgets, layouts, pages |
| `components.semanticModel` | 1 | SDM: DOs, relationships, parameters, business preferences |
| `components.dimensions` | ~90 | Calculated dimensions with DO-qualified expressions |
| `components.measurements` | ~170 | Calculated measurements with DO-qualified expressions |
| `components.metrics` | 6 | Metric definitions with time dimensions and insight settings |

### Template placeholders

Every viz and dashboard widget uses these placeholders that get replaced at deploy time:

| Placeholder | Replaced with | Example |
|-------------|---------------|---------|
| `{{SDM_API_NAME}}` | Target SDM's apiName | `Sales_Insights_Standalone_a1b2` |
| `{{SDM_ID}}` | Target SDM's record ID | `0IdXX0000000001` |
| `{{SDM_LABEL}}` | Target SDM's label | `Sales Insights Standalone` |
| `{{WORKSPACE_API_NAME}}` | Target workspace apiName | `Sales_Insights_Demo_c3d4` |
| `{{WORKSPACE_LABEL}}` | Target workspace label | `Sales Insights Demo` |
| `{{VIZ_NAME_*}}` | Actual viz apiName after creation | `SP_Sparkline_Win_Rate_abc123` |

The `{{VIZ_NAME_*}}` placeholders follow the pattern `{{VIZ_NAME_<original_viz_name>}}` (e.g. `{{VIZ_NAME_SP_Sparkline_Win_Rate}}`). These can only be resolved after the corresponding viz has been created, so vizzes must be created before dashboards.

---

## Data objects in the standalone SDM (11)

The package references these `SI_`-prefixed DOs. Each maps to a DLO created by the Bulk Ingest API:

| DO name | Underlying DLO | Dims | Meas | Description |
|---------|----------------|------|------|-------------|
| SI_Opportunity | si_opportunity_* | 17 | 4 | Main fact table: deals with stage, amount, dates |
| SI_Account | si_account_* | 9 | 2 | Company records with industry, size, region |
| SI_User | si_user_* | 6 | 0 | Opportunity owners (sales reps) |
| SI_Forecast_Owner | si_user_* | 5 | 0 | Second User copy for forecast hierarchy joins |
| SI_Lead_Owner | si_user_* | 3 | 0 | Third User copy for lead owner joins |
| SI_Forecast_Item | si_forecast_item_* | 10 | 1 | Forecast per rep/month/category |
| SI_Quota | si_quota_* | 4 | 1 | Quota per rep/month |
| SI_Opportunity_History | si_opportunity_history_* | 7 | 4 | Stage change events with timestamps |
| SI_Opportunity_Trend | si_opportunity_trend_* | 11 | 2 | Weekly opportunity snapshots for pipeline trending |
| SI_Forecast_Trend | si_forecast_trend_* | 5 | 1 | Weekly forecast snapshots |
| SI_Lead | si_lead_* | 13 | 0 | Leads with source, status, conversion data |
| SI_Activity | si_activity_* | 6 | 0 | Tasks/events linked to opportunities |

**Critical:** SI_Forecast_Owner, SI_Lead_Owner, and SI_User all point to the **same underlying DLO** (the User table). The DLO is added three times to the SDM with different DO apiNames so each join path is distinct. When creating the SDM, use `shouldIncludeAllFields: false` and specify fields explicitly for each DO instance.

---

## Relationships (11)

All use `joinType: "Auto"`, `cardinality: "ManyToOne"`:

| From DO | To DO | Join field(s) |
|---------|-------|---------------|
| SI_Opportunity | SI_Account | Account_Id |
| SI_Opportunity | SI_User | Owner_User_Id -> User_Id |
| SI_Opportunity | SI_Forecast_Item | Forecasting_Item_Id |
| SI_Forecast_Item | SI_Quota | Owner_Id + Business_Period_Id (compound key) |
| SI_Forecast_Item | SI_Forecast_Owner | Owner_Id -> User_Id |
| SI_Forecast_Trend | SI_Forecast_Item | Forecasting_Item_Id |
| SI_Opportunity_History | SI_Opportunity | Opportunity_Id |
| SI_Opportunity_Trend | SI_Opportunity | Opportunity_Id |
| SI_Activity | SI_Opportunity | Related_To_Item_Id -> Opportunity_Id |
| SI_Lead | SI_Account | Converted_To_Account_Id -> Account_Id |
| SI_Lead | SI_Lead_Owner | Owner_Id -> User_Id |

**Note on compound keys:** The SI_Forecast_Item -> SI_Quota relationship uses two join fields (Owner_Id AND Business_Period_Id). The relationship payload needs both pairs in `criteria`:
```json
{
  "criteria": [
    {"leftFieldApiName": "Owner_Id__c", "rightFieldApiName": "Owner_Id__c"},
    {"leftFieldApiName": "Business_Period_Id__c", "rightFieldApiName": "Business_Period_Id__c"}
  ]
}
```

---

## Dashboards (12)

All dashboards from the package:

| Dashboard | Vizzes | Pages | Description |
|-----------|--------|-------|-------------|
| Team_Performance | ~16 | 1 | Revenue by rep, top accounts, 4 dynamic KPI charts |
| Team_Performance_Forecasting2 | ~16 | 2 | Same metrics for forecasting hierarchy view |
| Sales_Performance_Forecasting | ~9 | 5 | Win rate, pipeline, deal size sparklines + drill pages |
| Sales_Stage_Progression | ~12 | 4 | Stage progression, stalled/pushed/neglected deals |
| Sales_Stage_Conversion | ~8 | 2 | Funnel, conversion trends, current/historical |
| Leaderboard | ~20 | 8 | 8 tabs: No Activity, Next Step, Stuck, Amount, Close Date, Forecast Cat, New, Lost, Open Opps |
| Forecasting_Leaderboard | ~20 | 8 | Same leaderboard with forecasting hierarchy |
| Forecast_Insights | ~8 | 5 | Waterfall, commit analysis, pipeline trends, velocity |
| Forecasting_Historical_Trend | ~6 | 2 | Closed won + commit over time, deals at risk, velocity |
| Lead_Analysis | ~9 | 1 | Conversion rate, age buckets, source breakdown |
| Homepage | 0 | 1 | Metric tiles (Closed Won, Pipeline, Win Rate) |

**Note:** Homepage has no visualizations — it uses only metric widgets (BAN tiles) that reference the 6 `_mtc` metrics from the SDM.

---

## Widget types in dashboards

| Type | Description | Creation method |
|------|-------------|----------------|
| `visualization` | References created vizzes by `{{VIZ_NAME_*}}` | Inline in `create_dashboard` |
| `text` | Static labels AND dynamic tokens (live BAN values) | `add_widget_to_dashboard` (textContent required) |
| `metric` | BAN tiles referencing `_mtc` metrics | `add_widget_to_dashboard` (semanticModelIdOrName required) |
| `filter` | List-type filters on SDM fields | Inline in `create_dashboard` |
| `parameter` | Toggle/list/input widgets bound to SDM parameters | Inline in `create_dashboard` |
| `container` | Background styling containers with rounded corners | Inline in `create_dashboard` |
| `button` | Navigation between dashboard pages | Inline in `create_dashboard` |
| `summary` | InsightSummary widget with AI-generated summaries | Inline in `create_dashboard` (requires AI features enabled) |

### Dynamic tokens in text widgets

Text widgets can embed live KPI values via dynamic tokens. These query the SDM at render time:

```json
{
  "dynamicTokens": {
    "token_0": {
      "name": "token_0",
      "source": {"id": "{{SDM_ID}}"},
      "tokenSpec": {
        "aggregationType": "UserAgg",
        "fieldName": "Closed_Won_Sales_RI_clc",
        "fieldType": "Measure"
      },
      "type": "query"
    }
  }
}
```

The `source.id` must be the SDM **record ID** (the `0Id...` format), not the apiName. This is why `{{SDM_ID}}` is a separate placeholder from `{{SDM_API_NAME}}`.

---

## Deployment steps

### Phase 1 — Connect and validate

1. Ask which target org profile to deploy to (show profiles from `config.json`)
2. Get SF token + DC token for the target org:
   ```python
   from connections import load_config, get_all_tokens, sf_headers, dc_headers
   config = load_config(profile_key)
   sf_token, sf_instance, dc_token, dc_domain = get_all_tokens(config, profile_key)
   ```
3. Verify Data Cloud is enabled (attempt a DC query)
4. Verify ingest connector exists — if not, tell the user to run `/setup` first
5. Load the package file:
   ```python
   import json, os
   PKG_DIR = os.path.join(os.path.dirname(__file__), "demos", "sales_insights_packages")
   with open(os.path.join(PKG_DIR, "Sales_Insights_Standalone_package.json")) as f:
       package = json.load(f)
   ```
6. Load or create `deploy_checkpoint.json` for resume capability

### Phase 2 — Data ingestion

#### Mode 2a — Source org clone

```bash
python demos/sales_insights_packages/ingest_source_data.py --source tableau_next --target default
```

The script:
1. Connects to the source org via its profile key
2. Exports data from source DMOs using Data Cloud Query API with **explicit SELECT columns** (NEVER `SELECT *` — some DMOs return rows without column metadata)
3. Transforms field names from DMO format (`ssot__X__c`) to DLO format (`X__c`)
4. Registers schemas on the target connector if needed
5. Creates data streams on the target org
6. Ingests via Bulk Ingest API (CSV upload)
7. Polls for DLO ACTIVE status

**Objects exported (15 total, ~5000 rows):**
- Opportunity, Account, User, Forecast_Item, Quota, Opportunity_History, Opportunity_Trend, Forecast_Trend, Lead, Activity
- Plus dimension tables if present

**Critical:** Data Cloud Query API returns rows WITHOUT column metadata for some DMOs. ALWAYS use explicit `SELECT col1, col2, ...` with known column names from `data_contract.json`.

#### Mode 2b — Custom data

Provide CSV files matching the schema in `demos/sales_insights_packages/data_contract.json`. Each object needs:
- All required fields (marked `required: true` in the contract)
- Field names matching the DLO naming convention (no `ssot__` prefix)
- A `Record_Id` surrogate key for fact tables (format: `{entity_id}_{date_YYYYMMDD}`)

See `demos/sales_insights_packages/CUSTOMIZATION_GUIDE.md` for which fields to customize for different use cases.

### Phase 3 — Create workspace + SDM

This phase creates the full semantic layer. Follow dependency order strictly:

**Step 3.1 — Create workspace:**
```python
ws_payload = {"label": "Sales Insights", "description": "Sales Insights Standalone"}
r = requests.post(f"{sf_instance}/services/data/v65.0/tableau/workspaces",
                  headers=sf_headers(sf_token), json=ws_payload)
ws_api = r.json()["apiName"]  # Auto-generated, e.g. Sales_Insights_a1b2
```

**Step 3.2 — Create SDM with all DOs inline:**
```python
sdm_payload = {
    "label": "Sales Insights Standalone",
    "dataspace": "default",
    "semanticDataObjects": [
        {
            "dataLakeObjectName": dlo_name,
            "dataObjectName": dlo_name,
            "dataObjectType": "dlo",
            "shouldIncludeAllFields": False,
            "dataLakeFieldInputRepresentations": [...]  # Explicit field list
        }
        for dlo_name in all_dlo_names
    ]
}
r = requests.post(f"{sf_instance}/services/data/v65.0/ssot/semantic/models",
                  headers=sf_headers(sf_token), json=sdm_payload)
sdm_api = r.json()["apiName"]  # Auto-generated from label
sdm_id = r.json()["id"]        # Record ID (0Id...) — needed for dynamic tokens
```

**Important:** The SDM `name` field is ignored. `apiName` is auto-generated from `label`. Always capture both `apiName` (for API calls) and `id` (for dynamic tokens in dashboards).

**Step 3.3 — Read SDM back to get auto-generated field apiNames:**
```python
r = requests.get(f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{sdm_api}?includeModelContent=true",
                 headers=sf_headers(sf_token))
sdm_content = r.json()
# Build field maps from each DO's semanticDimensions and semanticMeasurements
```

Auto-generated apiNames change on every SDM recreation (e.g. `FullName1` -> `FullName2`). NEVER cache — always read current state.

**Step 3.4 — Create parameters** (from `semanticModel.semanticParameters`):
Parameters must be created BEFORE calc fields that reference them. Calc expressions use `[Parameters].[param_name]`.

**Step 3.5 — Create calculated dimensions** (from `components.dimensions`):
```python
import html
for dim in package["components"]["dimensions"]:
    dim["expression"] = html.unescape(dim["expression"])  # &gt; -> >, &#39; -> ', etc.
    r = requests.post(
        f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{sdm_api}/calculated-dimensions",
        headers=sf_headers(sf_token), json=dim)
```

All expressions use DO-qualified field references: `[DO_apiName].[field_apiName]`. Must html.unescape() — the API returns HTML-encoded expressions (`&gt;`, `&#39;`, `&quot;`).

**Step 3.6 — Create calculated measurements** (from `components.measurements`):
Same pattern. Key fields: `apiName`, `label`, `aggregationType: "UserAgg"`, `dataType: "Number"`, `decimalPlace`, `directionality`, `displayCategory`, `expression`, `filters: []`, `isOverrideBase: False`, `isVisible: True`, `level`, `overriddenProperties: []`, `semanticDataType: "None"`.

Levels:
- `"AggregateFunction"` — most common, for complex aggregate measures (UserAgg)
- `"Row"` — for per-record computed columns (Sum/Avg/CountD/Max/Min)
- `"Lod"` — for FIXED expressions (`{ FIXED [DO].[field] : MAX(...) }`)
- `"TableCalc"` — for table calculations

**Step 3.7 — Create metrics** (from `components.metrics`):
Metrics require a `_clc` calculated measurement as `measurementReference.calculatedFieldApiName`. For `timeDimensionReference` on SDM-level calculated dimensions, use `{"calculatedFieldApiName": "Display_Date"}` (NOT `tableFieldReference`).

Set BOTH `additionalDimensions` AND `insightsSettings.insightsDimensionsReferences` to the same list — setting only one causes 400.

**Step 3.8 — Create relationships** (from `semanticModel.semanticRelationships`):
```python
rel_payload = {
    "leftSemanticDefinitionApiName": left_do_api,
    "rightSemanticDefinitionApiName": right_do_api,
    "joinType": "Auto",
    "cardinality": "ManyToOne",
    "criteria": [
        {"leftFieldApiName": "field__c", "rightFieldApiName": "field__c"}
    ]
}
```
`joinType` MUST be `"Auto"` — explicit types like `"LeftOuter"` cause 400.

**Step 3.9 — Set business preferences:**
The SDM has a free-text Business Preferences field (UI-only, no REST API). Generate the text from the package's `semanticModel.businessPreferences` field, save to checkpoint, and instruct the user to paste it in: Data 360 -> Semantic Model -> [SDM] -> AI Optimization -> Manage Business Preferences.

### Phase 4 — Create visualizations

For each viz in `components.visualizations`:

1. **Replace template placeholders** — substitute `{{SDM_API_NAME}}`, `{{WORKSPACE_API_NAME}}`, etc. in the viz spec
2. **POST to create:**
   ```python
   r = requests.post(
       f"{sf_instance}/services/data/v67.0/tableau/visualizations?minorVersion=14",
       headers=sf_headers(sf_token), json=viz_payload)
   viz_api = r.json()["apiName"]
   ```
3. **Track created viz apiNames** — build a map of `original_name -> created_apiName` for dashboard placeholder replacement
4. **Add to workspace:**
   ```python
   requests.post(
       f"{sf_instance}/services/data/v65.0/tableau/workspaces/{ws_api}/assets",
       headers=sf_headers(sf_token),
       json={"apiName": viz_api, "type": "Visualization"})
   ```

**Order matters:** Some vizzes are referenced by dashboards via `{{VIZ_NAME_*}}` placeholders. All vizzes must be created before any dashboard.

**Error handling:** If a viz fails, log the error and continue. Track failures in the checkpoint so they can be retried. Common failures:
- Missing field reference — a calc field wasn't created successfully in Phase 3
- Style validation — missing required style keys (see Viz spec patterns below)

### Phase 5 — Create dashboards

For each dashboard in `components.dashboard`:

1. **Replace ALL placeholders:**
   - `{{SDM_API_NAME}}` -> target SDM apiName
   - `{{SDM_ID}}` -> target SDM record ID
   - `{{SDM_LABEL}}` -> target SDM label
   - `{{WORKSPACE_API_NAME}}` -> target workspace apiName
   - `{{WORKSPACE_LABEL}}` -> target workspace label
   - `{{VIZ_NAME_*}}` -> actual viz apiNames from Phase 4 map

2. **Separate widgets by creation method:**
   - **Inline widgets** (viz, filter, parameter, container, button, summary) -> include in `create_dashboard` POST
   - **Post-creation widgets** (metric, text with textContent/dynamicTokens) -> use `add_widget_to_dashboard` after creation

3. **POST to create dashboard:**
   ```python
   r = requests.post(
       f"{sf_instance}/services/data/v67.0/tableau/dashboards?minorVersion=14",
       headers=sf_headers(sf_token), json=dash_payload)
   dash_api = r.json()["apiName"]
   ```

4. **Add metric widgets** (must be separate — they require `semanticModelIdOrName`):
   ```python
   metric_widget = {
       "type": "metric",
       "source": {"name": metric_api},
       "parameters": {"metricOption": {"sdmApiName": sdm_api}},
       "actions": [],
       "name": widget_key
   }
   # Use add_widget_to_dashboard MCP or REST endpoint
   ```

5. **Add text widgets with dynamicTokens** (textContent rejected in create_dashboard):
   Separate any text widgets that have `textContent` or `dynamicTokens` and add them after creation.

6. **Add to workspace:**
   ```python
   requests.post(
       f"{sf_instance}/services/data/v65.0/tableau/workspaces/{ws_api}/assets",
       headers=sf_headers(sf_token),
       json={"apiName": dash_api, "type": "Dashboard"})
   ```

### Phase 6 — Share workspace

Share the workspace with All Internal Users. **This must be done in the UI** — the API rejects `shareWith: "ALL_USERS"` with 400 `Unrecognized field "shareWith"`.

Instruct the user:
> Open the workspace in Tableau Next -> Share -> All Internal Users -> View

---

## Checkpoint / resume

Write `demos/sales_insights_packages/deploy_checkpoint.json` after each major phase:

```json
{
  "target_profile": "default",
  "phase2_ingest": "done",
  "phase3_sdm": "done",
  "ws_api": "Sales_Insights_a1b2",
  "sdm_api": "Sales_Insights_Standalone_c3d4",
  "sdm_id": "0IdXX0000000001",
  "do_apis": {"SI_Opportunity": "SI_Opportunity5", ...},
  "dim_field_map": {...},
  "meas_field_map": {...},
  "phase4_vizzes": "done",
  "viz_name_map": {"SP_Sparkline_Win_Rate": "SP_Sparkline_Win_Rate_abc123", ...},
  "all_viz_apis": [...],
  "phase5_dashboards": "done",
  "all_dash_apis": [...],
  "failed_vizzes": [...],
  "failed_dashboards": [...]
}
```

On script start, load the checkpoint and skip phases already marked done. Track every created asset in `all_viz_apis` and `all_dash_apis` so retries can clean up before recreating.

---

## Key differences from the original approach

| Aspect | Old (abandoned) | New (working) |
|--------|----------------|---------------|
| SDM dependency | Requires SalesInsights managed app | Standalone — no managed app needed |
| Data source | CRM connector (standard DMOs) | CSV-backed DLOs via Bulk Ingest |
| Data | Synthetic generator (`sales_insights_data_gen.py`) | Real source org data OR custom CSV |
| Deploy method | Package & Deploy API (`next-package-deploy.demo.tableau.com`) | REST API (viz + dashboard creation) |
| Field names | `ssot__X__c` (DMO fields) | `X__c` (DLO fields) |
| Dashboard deploy | One call to Package & Deploy per dashboard | REST POST per dashboard + post-creation widget adds |
| Calc field creation | Automatic from managed package | Manual in order: params -> calc dims -> calc meas -> metrics -> relationships |
| Workspace/SDM | Created by Package & Deploy service | Created explicitly via REST |
| Expression format | Pre-resolved by Package & Deploy | Template placeholders resolved at deploy time |

---

## Viz spec patterns learned

### Chart type mapping

| Chart type | marks.panes.type | Key patterns |
|-----------|-----------------|--------------|
| Line (sparkline) | `"Line"` | columns=[date], rows=[measure] |
| Bar (vertical) | `"Bar"` | Color encoding on panes |
| Stacked bar | `"Bar"` + `stack.isStacked: true` | Color = dimension for stacking |
| Dual axis | marks.fields per measure | F1=Bar, F2=Line with different types per field |
| Donut | `"Donut"` | Angle, Color, Label encodings; columns=[], rows=[] |
| Circle (scatter) | `"Circle"` | marks.fields: {} (empty); dimension on cols/rows |
| Table | `layout: "Table"` | All fields in rows |
| Highlight table | `"Square"` | marks.fields: {} (empty) |
| Waterfall | `"Bar"` + Range encoding | `{fieldKey: "F_range", type: "Range"}` |
| Funnel | `"Bar"` + `connector: {type: "Origami"}` | `isStackingAxisCentered: true` |

### Required viz style keys

Every viz spec must include ALL of these style keys — missing any one causes 400:

```
axis, encodings, fieldLabels, fit, fonts, headers, lines, marks,
referenceLines, shading, showDataPlaceholder, title
```

### Fonts format (viz API)

```json
{
  "actionableHeaders": {"color": "#0250D9", "size": 12},
  "axisTickLabels": {"color": "#5C5C5C", "size": 12},
  "fieldLabels": {"color": "#2E2E2E", "size": 12},
  "headers": {"color": "#5C5C5C", "size": 12},
  "legendLabels": {"color": "#2E2E2E", "size": 12},
  "markLabels": {"color": "#000000", "size": 12},
  "marks": {"color": "#5C5C5C", "size": 12}
}
```

Do NOT use the docx-style font format (`fontName`/`fontSize`/`isBold`) — that causes 400.

### Headers style

Every dimension field in `columns` or used as a color grouping MUST have an entry in `style.headers.fields`:
```json
{
  "columns": {"mergeRepeatedCells": true, "showIndex": false},
  "rows": {"mergeRepeatedCells": true, "showIndex": false},
  "fields": {
    "F1": {"hiddenValues": [], "isVisible": true, "showMissingValues": false}
  }
}
```
Omitting a field entry causes 400 `"headers.fields" style is required for the "[FieldName]" ("[Fkey]") field`.

### Marks structure

- `marks.headers.type` must ALWAYS be `"Text"` — never `"Line"` or `"Bar"` (those go in `marks.panes.type` only)
- `marks.panes`: `{"encodings": [], "isAutomatic": false, "stack": {...}, "type": "Line"|"Bar"|"Square"|etc.}`
- `marks.fields`: use `{}` (empty dict) for Square/Circle charts; for dual-axis, use per-field entries with `type` and `stack`
- `style.marks.panes` is separate — contains color/label/range/size styling, NOT chart type

### Color dimension placement

- For scatter/multi-line with a color dimension F3: place it in `columns` BEFORE any continuous measure fields
- Multi-line: `columns: ["F1", "F3"]` (date first, then categorical dim — accepted because date is discrete)
- A dimension CANNOT come after continuous fields — causes 400

---

## Dashboard layout patterns

### Grid system

Sales Insights dashboards use a different grid than standard AIO demos:

| Property | Sales Insights | Standard AIO |
|----------|---------------|--------------|
| `columnCount` | **91** | 72 |
| `rowHeight` | **16** | 10 |
| `cellSpacingX` | **0** | 8 |
| `cellSpacingY` | **0** | 8 |
| `backgroundColor` | `#FFFFFF` | `#F3F3F3` |
| `gutterColor` | `#FFFFFF` | `#F3F3F3` |

Keep the original 91-column grid — do NOT convert to 72.

### Container widgets

Rounded-corner section backgrounds:
```json
{
  "type": "container",
  "parameters": {
    "widgetStyle": {
      "borderRadius": 16,
      "borderEdges": ["all"],
      "backgroundColor": "#F8F8F8"
    }
  }
}
```

### Vertical separators

Text widgets with border edges:
```json
{
  "type": "text",
  "parameters": {
    "widgetStyle": {"borderEdges": ["left"], "borderColor": "#E0E0E0"}
  }
}
```

### Page navigation (button widgets)

```json
{
  "type": "button",
  "parameters": {
    "actionType": "navigate",
    "targetPageId": "uuid-of-target-page",
    "label": "Pipeline"
  }
}
```

### Filter widget patterns

Filters reference SDM fields by object and field name:
```json
{
  "type": "filter",
  "parameters": {
    "filterOption": {
      "dataType": "DateTime",
      "fieldName": "Close_Date",
      "objectName": "SI_Opportunity",
      "selectionType": "multiple"
    }
  }
}
```

**Known issue:** `filterType` parameter is NOT supported — causes 400 `Unrecognized field "filterType"`. Omit it.

### Parameter widget patterns

Parameters reference SDM parameter apiNames:
```json
{
  "type": "parameter",
  "parameters": {
    "parameterName": "Team_Performance_List_1_RI_prm",
    "viewType": "list"
  }
}
```

Toggle parameters use `"viewType": "toggle"` with `selectedStyle` and `defaultStyle`.

---

## Calc field expression syntax

Expressions in the package use Tableau's semantic expression language:

- **DO-qualified field references**: `[DO_apiName].[field_apiName]` — e.g. `[SI_Opportunity5].[Amount3]`
- **Parameter references**: `[Parameters].[param_name]` — e.g. `[Parameters].[Time_Period_prm]`
- **LOD expressions**: `{ FIXED [DO].[field] : MAX([DO].[measure]) }` — curly braces, DO-qualified
- **Aggregation functions**: `SUM(...)`, `AVG(...)`, `COUNTD(...)`, `MAX(...)`, `MIN(...)`
- **Conditional logic**: `IF ... THEN ... ELSEIF ... ELSE ... END`
- **Date functions**: `DATEDIFF('day', [DO].[date], TODAY())`, `DATEADD('month', -3, TODAY())`
- **String functions**: `CONTAINS(...)`, `LEFT(...)`, `TRIM(...)`

**Level assignment:**
- `"AggregateFunction"` — for UserAgg calcs (most common; complex aggregate expressions)
- `"Row"` — for Sum/Avg/CountD/Max/Min calcs (row-level functions)
- `"Lod"` — for FIXED expressions
- `"TableCalc"` — for table calculations

---

## Files in demos/sales_insights_packages/

| File | Purpose |
|------|---------|
| `Sales_Insights_Standalone_package.json` | THE master package — all viz specs, dashboard layouts, SDM definition, calc fields, metrics |
| `ingest_source_data.py` | Source org data export + target org ingest script |
| `data_contract.json` | Complete field schema for all 11+ objects (required fields, types, descriptions) |
| `CUSTOMIZATION_GUIDE.md` | Which fields to customize for different use cases |
| `expression_translation.json` | Field name mapping between source DMO and target DLO formats |
| `field_maps.json` | Auto-detected field apiNames per DO (from last deployment) |
| `dlo_name_map.json` | Maps logical object names to target DLO names (with auto-generated suffixes) |
| `dlo_schema_map.json` | Full DLO schema definitions for schema registration |
| `deploy_checkpoint.json` | Tracks deployment state for resume |
| `source_layouts.json` | Dashboard layout specs extracted from source org |
| `src_*_full.json` | Full dashboard exports from source org (reference copies) |
| `replicate_sdm.py` | SDM replication script (reads source, creates on target) |
| `translate_vizzes.py` | Viz field reference translator (source apiNames -> target apiNames) |
| `translated_vizzes.json` | Pre-translated viz specs (intermediate artifact) |
| `calc_levels.json` | Level assignments for all calculated fields |
| `alignment_ops.json` | Field alignment operations between source and target |
| `filter_ops.json` | Filter translation operations |
| `mcp_ops_SI_*.json` | MCP slim-spec operations per dashboard (alternative creation path) |
| `MANUAL_TASKS.md` | Post-deployment manual steps (workspace sharing, etc.) |

---

## Known issues

### API limitations
- **Workspace sharing**: `shareWith: "ALL_USERS"` rejected via REST API — must share in the Tableau Next UI (Share -> All Internal Users -> View)
- **Filter widgets**: `filterType` parameter not supported in dashboard creation endpoint — causes 400 `Unrecognized field "filterType"`. Filters may need to be added in the UI after deployment
- **Metric widgets**: must use `add_widget_to_dashboard` with `semanticModelIdOrName` — cannot be included inline in `create_dashboard`
- **Text widgets with textContent/dynamicTokens**: must use `add_widget_to_dashboard` — `create_dashboard` rejects `textContent`
- **Summary widgets**: InsightSummary requires AI features enabled on the org
- **Dynamic tokens**: `tokenSpec.source.id` must be the SDM **record ID** (`0Id...`), not the apiName

### SDM/field issues
- **Expression HTML encoding**: API returns `&gt;`, `&#39;`, `&quot;` in expressions — must `html.unescape()` before POSTing. Without this, ~90% of calc fields fail with "token recognition error at: '&'"
- **Auto-generated apiNames change on SDM recreation** — field apiNames get new numeric suffixes every time. NEVER cache field maps across SDM deletions; always `GET` current state
- **Multiple User DOs**: The package adds the same User DLO three times (SI_User, SI_Forecast_Owner, SI_Lead_Owner) — each needs its own DO entry in the SDM with a unique apiName but the same underlying DLO
- **Calc field dependency order**: parameters -> calc dimensions -> calc measurements -> metrics -> relationships. Out-of-order creation causes "Missing reference" errors
- **`dataObjectType` must be lowercase `"dlo"`** — using `"DLO"` causes 400

### Viz-specific issues
- **`negativeValuesFormat: "NegativeSign"` rejected** — omit this field entirely from `numberFormatInfo`
- **`marks.headers.type` must be `"Text"`** — using `"Line"` or `"Bar"` causes 400 `Invalid value for mark type of the visualization header`
- **Empty `"headers": {}` in style causes 400** — either omit entirely or include all required sub-keys
- **`style.encodings.fields` must have entries for every measure field** — an empty `{}` causes 400 for that field
- **Grid is 91 columns, not 72** — keep the original `columnCount` from the package; do not normalize to 72

### Data ingestion issues
- **Source DMO Query API**: some DMOs return rows without column metadata — ALWAYS use explicit `SELECT col1, col2, ...` (never `SELECT *`)
- **Schema registration**: if target schema already exists on the connector, skip the PUT — existing schemas may have platform-injected reserved fields that cause validation loops
- **Bulk Ingest**: only `upsert` and `delete` operations are supported — `insert` causes 400
- **DLO ACTIVE lag**: after DLO reaches ACTIVE status, wait an additional 30s before submitting bulk ingest jobs — schema propagation lag can cause 404s

---

## Safety rules

- **Always confirm** before deploying to the target org
- **Check for existing Sales Insights assets** before deploying — warn if a workspace named "Sales Insights" already exists
- **Save checkpoint after every phase** — interrupted runs can resume without recreating assets
- **Track all created assets** in checkpoint lists (`all_viz_apis`, `all_dash_apis`) for clean retry
- **Never delete assets not in checkpoint tracking lists** without user confirmation
- **Use existing connector** — never create a new ingest connector; require one from `/setup`
- **Batch operations** — use Composite API and Bulk Ingest for efficiency within API limits
