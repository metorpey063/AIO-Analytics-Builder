# Tableau Next MCP Build Guide

When the Tableau Next pilot MCP server (`tableau-next-pilot`) is connected, use this guide instead of the direct REST API approach for Tableau Next demos. The MCP handles payload complexity, version differences, and style scaffolding automatically.

**Scope:** This guide covers the Tableau Next build path only. Pulse, CRMA, `.twb`, and `.docx` generation are unaffected — those continue using the existing patterns in `CLAUDE.md`.

## Prerequisites

- MCP server `tableau-next-pilot` added and authenticated (see install guide)
- `/mcp` shows the server as connected
- Org has `TableauPilotMCPServerEnabled` permission enabled

## Build phases: MCP vs direct REST

| Phase | Direct REST (current) | MCP approach | Status |
|-------|----------------------|--------------|--------|
| 1. Data generation | Python/numpy | Python/numpy (unchanged) | Same |
| 2. CSV export | pandas `.to_csv()` | pandas `.to_csv()` (unchanged) | Same |
| 3. Data ingestion | Schema PUT → stream POST → Bulk Ingest API (CSV batches) | `generate_presigned_credential` → HTTP PUT → `create_data_stream` → `run_data_stream` | **Changed** |
| 4. DMO creation | N/A (we use DLOs directly) | `create_data_model_object` → `create_dlo_to_dmo_mapping` | **New option** |
| 5. Workspace + SDM | `POST /tableau/workspaces` + `POST /ssot/semantic/models` | `create_workspace` + `create_semantic_model` (can inline DOs) | **Simplified** |
| 6. DO + fields | `POST .../data-objects` + multiple PUTs for measures/dims | `add_semantic_model_data_object(shouldIncludeAllFields=true)` + update calls | **Simplified** |
| 7. Calc dimensions | `POST .../calculated-dimensions` | `add_semantic_model_calculated_dimension` | Same pattern |
| 8. Calc measures | `POST .../calculated-measurements` (500 on v66 for IngestAPI) | `add_semantic_model_calculated_measure` | May route internally to working version |
| 9. Metrics | CLC POST → metric POST → noun PUT (3 calls) | `add_semantic_model_metric` (1 call, nouns + insights inline) | **Major win** |
| 10. Business preferences | Manual UI paste | `update_semantic_model(businessPreferences=...)` | **Major win** |
| 11. Field descriptions | Individual PUT per dim/measure | `generate_description` (AI) + `update_semantic_model_dimension/measure` | **AI-assisted** |
| 12. Visualizations | `build_viz_payload()` → 17-rule validation → POST | `create_visualization` (slim spec, server hydrates VizQL) | **Major win** |
| 13. Dashboard | `build_dashboard_payload()` → POST | `create_dashboard` + `add_widget_to_dashboard` per widget | **Simplified** |
| 14. Dashboard filters | 400 errors, must add in UI | `add_global_filter_to_dashboard` | **Now works** |
| 15. Workspace assets | `POST .../workspaces/{name}/assets` | `add_workspace_asset` | Same pattern |
| 16. AI optimization | Hand-written, manual paste | `generate_business_preference` + `generate_questions` | **AI-assisted** |

## Phase-by-phase MCP approach

### Phase 1–2: Data generation + CSV export (unchanged)

Generate synthetic data with Python/numpy exactly as today. Export to CSV. The MCP ingestion path uploads the CSV file rather than pushing it through Bulk Ingest API.

### Phase 3: Data ingestion via MCP

The MCP uses a file-upload + stream pipeline instead of the Bulk Ingest API.

```
Step 1: generate_presigned_credential(fileName="demo_data.csv")
        → returns presignedUrl, parentDirectory, importDirectory

Step 2: HTTP PUT the CSV file to the presigned URL (outside MCP — use requests.put())
        Include any encryption headers from step 1

Step 3: get_upload_connection(connectorType="UploadedFiles")
        → returns connectionId

Step 4: infer_object_schema(
            connectionId=...,
            resourceName="files",
            advancedAttributes={
                driveLibraryId: "fileUploads$tua",
                parentDirectory: <from step 1>,
                importDirectory: <from step 1>,
                fileName: "demo_data.csv",
                fileType: "CSV"
            })
        → returns sourceFields (column names + types)

Step 5: create_data_stream(
            name="demo_fact",
            label="Demo Fact",
            connectorInfo={connectorType: "DataConnector",
                           connectorDetails: {name: "UploadedFiles"}},
            sourceFields=<from step 4>,
            dataLakeObjectInfo={
                name: "demo_fact__dll",
                label: "Demo Fact",
                category: "Other",
                dataspaceInfo: [{name: "default"}],
                fields: [...],  # name, label, dataType, isPrimaryKey
            },
            mappings=[...],  # 1:1 source→target
            refreshConfig={refreshMode: "TOTAL_REPLACE",
                           frequency: {frequencyType: "None"}})
        → creates stream + DLO in one call

Step 6: run_data_stream(recordIdOrDeveloperName="demo_fact", interactive=true)
        → triggers sync ingestion

Step 7: Poll get_data_stream() until lastRunStatus="Success"
        (30-60s intervals, small CSVs ~30s)
```

**Key differences from direct REST:**
- No schema registration PUT — `infer_object_schema` detects types from the CSV
- No Bulk Ingest jobs/batches — `run_data_stream` handles ingestion
- `parentDirectory` and `importDirectory` are opaque server values — pass verbatim, never construct
- `interactive=true` for file uploads (sync fast-ingest), `false` for database sources
- Stream status (`status`) vs ingestion status (`lastRunStatus`) are different fields

### Phase 4: DMO creation (optional, recommended by MCP)

The MCP recommends DMOs over raw DLOs for semantic models. If using DMOs:

```
Step 1: create_data_model_object(
            name="Demo_Fact",
            label="Demo Fact",
            category="Other",  # NOT "Engagement" for file uploads
            fields=[...])      # isPrimaryKey must be set on EVERY field (null = NPE)

Step 2: create_dlo_to_dmo_mapping(
            sourceEntityDeveloperName="demo_fact__dll",
            targetEntityDeveloperName="Demo_Fact__dlm",
            fieldMapping=[{sourceFieldDeveloperName, targetFieldDeveloperName}, ...])
        → NOT idempotent — duplicate = 500

Step 3: Poll get_dlo_to_dmo_mapping_status() until status="ACTIVE"
```

**Caveat:** `category: "Engagement"` DMOs cannot be mapped from file-upload DLOs (fails with "Unable to find Event Field for Engagement DLO"). Default to `"Other"`.

### Phase 5: Workspace + SDM creation

```python
# Create workspace
create_workspace(name="demo_workspace", label="Demo Workspace")
# Response is double-wrapped: parse JSON.parse(response.defaultExc)

# Create SDM (can inline DOs at creation time)
create_semantic_model(
    apiName="Demo_Analytics",
    label="Demo Analytics",
    dataspace="default",
    sourceCreation="Other",
    semanticDataObjects=[{
        apiName="Demo_Fact_DO",
        label="Demo Fact",
        dataObjectName="demo_fact__dll",  # or Demo_Fact__dlm if using DMO
        dataObjectType="Dlo",             # or "Dmo"
        shouldIncludeAllFields=True
    }])

# Register SDM in workspace
add_workspace_asset(
    workspaceIdOrApiName="demo_workspace",
    assetId=<sdm_id>,
    assetType="SemanticModel",
    assetUsageType="Created")
```

**Key simplification:** `shouldIncludeAllFields=True` on the inline DO auto-attaches all columns as dimensions/measures — eliminates the separate DO POST + field configuration loop.

**Caveat:** `shouldIncludeAllFields=True` triggers numeric-suffix mutation on apiNames (e.g. `date` → `date1`). Always read back actual names via `list_semantic_model_dimensions` / `list_semantic_model_measures`.

### Phase 6: Field configuration

After SDM creation with `shouldIncludeAllFields=True`, read back actual field names then update:

```python
# Read actual apiNames (they get numeric suffixes)
dims = list_semantic_model_dimensions(modelApiNameOrId=sdm_api, dataObjectNameOrId=do_api)
measures = list_semantic_model_measures(modelApiNameOrId=sdm_api, dataObjectNameOrId=do_api)

# Update measure aggregations
update_semantic_model_measure(
    modelApiNameOrId=sdm_api,
    dataObjectNameOrId=do_api,
    measurementNameOrId=measure_api,
    apiName=measure_api,              # required — must match
    dataObjectFieldName=field_name,   # required even on update
    aggregationType="Average",        # or "Sum"
    description="Use this field to...",
    label="Enrollment Rate",
    isVisible=True)                   # ALWAYS echo back — silent reset bug

# Update dimension descriptions
update_semantic_model_dimension(
    modelApiNameOrId=sdm_api,
    dataObjectNameOrId=do_api,
    dimensionNameOrId=dim_api,
    apiName=dim_api,
    dataObjectFieldName=field_name,
    description="Use this field to filter by...",
    isVisible=True)                   # ALWAYS echo back
```

**AI-assisted alternative:** Use `generate_description(semanticModelApiName=sdm_api, apiNames=[...])` to auto-generate descriptions, then apply via update calls.

**Critical bug:** `isVisible` is NOT preserved by sparse updates. If you update only `description`, `isVisible` silently resets to `true`. Always include `isVisible` in every update call.

### Phase 7: Calculated dimension (date shift)

Same TuA expression syntax as direct REST:

```python
add_semantic_model_calculated_dimension(
    modelApiNameOrId=sdm_api,
    apiName="Display_Date",
    label="Display Date",
    dataType="Date",
    expression='DATEADD("day", DATEDIFF("day", #2026-09-21#, [DO_api].[date_field_api]), TODAY())')
```

Expression rules:
- Bracketed DO-qualified references: `[DataObjectApiName].[FieldApiName]`
- Date literals: `#YYYY-MM-DD#`
- Bare field names, `__c`-suffixed names, and label names all fail with "Missing reference"

### Phase 8: Calculated measures

```python
add_semantic_model_calculated_measure(
    modelApiNameOrId=sdm_api,
    apiName="avg_enrollment_rate",
    label="Average Enrollment Rate",
    dataType="Number",
    aggregationType="UserAgg",  # for level-aware aggregations
    expression="AVG([DO_api].[enrollment_rate_api])",
    description="Average benefits enrollment rate across all clients",
    directionality="Up",
    sentiment="SentimentTypeUpIsGood",
    decimalPlace=4)
```

**Expression rules:**
- Only simple-CASE supported (`CASE <expr> WHEN <val> THEN <res> END`)
- Searched-CASE and `IF()` are NOT supported
- Division by zero accepted at create time, fails at query time

### Phase 9: Metrics (major simplification)

One call replaces three (CLC POST → metric POST → noun PUT):

```python
add_semantic_model_metric(
    modelApiNameOrId=sdm_api,
    apiName="enrollment_rate_mtc",
    label="Enrollment Rate",
    measurementReference={"calculatedFieldApiName": "avg_enrollment_rate"},
    timeDimensionReference={"calculatedFieldApiName": "Display_Date"},
    aggregationType="UserAgg",
    timeGrains=["Month", "Quarter", "Year"],
    primaryTimeComparison="PreviousYear",
    additionalDimensions=[
        {"tableFieldReference": {"fieldApiName": dim_api, "tableApiName": do_api}}
        for dim_api in drilldown_dims
    ],
    insightsSettings={
        "identifyingDimension": {
            "identifierDimensionReference": {
                "tableFieldReference": {"fieldApiName": id_dim, "tableApiName": do_api}
            }
        },
        "insightTypes": [
            "TopContributors", "BottomContributors", "TopDrivers",
            "TopDetractors", "TrendChangeAlert", "CurrentTrend"
        ],
        "insightsDimensionsReferences": [
            {"tableFieldReference": {"fieldApiName": dim_api, "tableApiName": do_api}}
            for dim_api in drilldown_dims
        ],
        "singularNoun": "enrollment rate",
        "pluralNoun": "enrollment rates",
        "sentiment": "SentimentTypeUpIsGood"
    })
```

**Key:** `additionalDimensions` and `insightsDimensionsReferences` must contain the same dimension list — same constraint as direct REST.

### Phase 10: Business preferences (major win — no more manual paste)

```python
# Generate AI-drafted preferences
prefs = generate_business_preference(
    semanticModelApiName=sdm_api,
    userInput="This SDM tracks benefits enrollment for a large employer services company. Key metrics are enrollment rate, plan mix, and voluntary participation. The audience is a VP of Benefits Operations who cares about cost sensitivity and regional variation.")

# Save to the SDM
update_semantic_model(
    modelApiNameOrId=sdm_api,
    businessPreferences=prefs_text)  # or hand-written text
```

This eliminates the manual "copy this text and paste it in Data 360 → AI Optimization" step from every walkthrough.

**Still include in the walkthrough:** document what the business preferences say, but note they're already applied (no manual action needed).

### Phase 11: Visualizations (major win — slim spec)

The MCP `create_visualization` handles all VizQL complexity. You provide fields, layout, and chart type — the server hydrates marks, style, encodings, headers, fonts, axis, lines, shading, etc.

```python
# Line chart — trend over time
create_visualization(
    label="Enrollment Rate Over Time",
    workspaceId=ws_id,
    workspaceName=ws_name,
    semanticModelName=sdm_api,
    semanticModelLabel=sdm_label,
    fields={
        "F1": {"objectName": do_api, "fieldName": "Display_Date",
                "displayCategory": "Discrete", "function": "DateTruncMonth"},
        "F2": {"objectName": do_api, "fieldName": "enrollment_rate_api",
                "displayCategory": "Continuous", "function": "Avg",
                "numberFormat": "Percent"}
    },
    visualSpecification={
        "layout": "Vizql",
        "columns": ["F1"],
        "rows": ["F2"],
        "marks": {"panes": {"type": "Line"}},
        "legends": {}
    },
    sortIntent="None")

# Multi-line chart — trend by segment
create_visualization(
    label="Enrollment by Region",
    workspaceId=ws_id,
    workspaceName=ws_name,
    semanticModelName=sdm_api,
    semanticModelLabel=sdm_label,
    fields={
        "F1": {"objectName": do_api, "fieldName": "Display_Date",
                "displayCategory": "Discrete", "function": "DateTruncMonth"},
        "F2": {"objectName": do_api, "fieldName": "enrollment_rate_api",
                "displayCategory": "Continuous", "function": "Avg",
                "numberFormat": "Percent"},
        "F3": {"objectName": do_api, "fieldName": "region_api",
                "displayCategory": "Discrete"}
    },
    visualSpecification={
        "layout": "Vizql",
        "columns": ["F1", "F3"],
        "rows": ["F2"],
        "marks": {"panes": {"type": "Line",
                             "encodings": [{"fieldKey": "F3", "type": "Color"}]}},
        "legends": {"F3": {"isVisible": True, "position": "Right",
                           "title": {"isVisible": True}}}
    })

# Bar chart — sorted by measure
create_visualization(
    label="Enrollment by Vertical",
    ...,
    fields={
        "F1": {"objectName": do_api, "fieldName": "vertical_api",
                "displayCategory": "Discrete"},
        "F2": {"objectName": do_api, "fieldName": "enrollment_rate_api",
                "displayCategory": "Continuous", "function": "Avg",
                "numberFormat": "Percent"}
    },
    visualSpecification={
        "layout": "Vizql",
        "columns": ["F1"],
        "rows": ["F2"],
        "marks": {"panes": {"type": "Bar"}}
    },
    sortIntent="MeasureDescending")

# Donut chart
create_visualization(
    ...,
    visualSpecification={
        "layout": "Radial",
        "columns": ["F1"],
        "rows": ["F2"],
        "marks": {"panes": {"type": "Donut",
                             "encodings": [{"fieldKey": "F1", "type": "Color"}]}}
    })

# Heatmap (Square marks)
create_visualization(
    ...,
    visualSpecification={
        "layout": "Vizql",
        "columns": ["F1"],
        "rows": ["F3"],
        "marks": {"panes": {"type": "Square",
                             "encodings": [{"fieldKey": "F2", "type": "Color"}]}}
    })

# Reference line
create_visualization(
    ...,
    fields={
        "F1": {...},
        "F2": {..., "referenceLine": "Average"},  # adds avg reference line
    },
    ...)
```

**Supported chart types:** Bar (incl. stacked, grouped, multi-measure), Line, Donut, Scatter/Bubble (Circle + Size), Heatmap (Square), Text table.

**Brand colors:** Use `markColor` for single-color charts (no Color encoding): `markColor: "#E8762D"`. For multi-series, colors are auto-assigned by the Color encoding.

**What's eliminated:**
- `viz_builder.py` — `build_viz_payload()` and all template logic
- `viz_validator.py` — 17-rule validation engine (server handles this)
- `style_defaults.py` — font/line/shading/encoding builders
- `viz_templates.py` — template definitions (replaced by slim specs above)
- All Known Pitfalls related to VizQL style keys, marks.headers, encodings, fonts, lines, etc.

### Phase 12: Dashboard creation

The MCP recommends: create empty → add widgets one at a time.

```python
# Create empty dashboard
create_dashboard(
    name="demo_dashboard",
    label="Demo Dashboard",
    workspaceIdOrApiName=ws_name,
    widgets={},
    layouts=[],
    minorVersion=-1)

# Add viz widgets
add_widget_to_dashboard(
    dashboardIdOrApiName="demo_dashboard",
    widget={
        "type": "visualization",
        "name": "enrollment_trend_widget",
        "source": {"id": viz_id, "name": viz_api_name}
    },
    placement={"row": 0, "column": 0, "rowspan": 20, "colspan": 24, "pageIndex": 0})

# Add metric widgets
add_widget_to_dashboard(
    dashboardIdOrApiName="demo_dashboard",
    widget={
        "type": "metric",
        "name": "enrollment_metric_widget",
        "source": {"id": metric_sf_id, "name": metric_api},
        "semanticModelIdOrName": sdm_api
    },
    placement={"row": 0, "column": 24, "rowspan": 10, "colspan": 24, "pageIndex": 0})

# Add global filter (this actually works via MCP!)
add_global_filter_to_dashboard(
    dashboardIdOrApiName="demo_dashboard",
    semanticModelIdOrName=sdm_api,
    objectName=do_api,
    fieldName="region_api",
    placement={"row": 0, "column": 0, "rowspan": 3, "colspan": 48, "pageIndex": 0},
    dataType="Text",
    selectionType="multiple")
```

**Grid:** 48 columns wide (not 72 as in direct REST). Row height default 20px.

**Key differences from direct REST:**
- `add_widget_to_dashboard` is atomic (handles read-modify-write internally)
- Filter widgets actually work (400 via raw API, works via MCP)
- Widget `type` must be lowercase: `"visualization"`, `"metric"`, `"filter"`, `"text"`
- Widget `source` must have only `id` and `name` (no `label` or `type`)
- `minorVersion` must be `-1` (not `12` as in direct REST)

### Phase 13: AI optimization

```python
# Auto-generate field descriptions
descriptions = generate_description(
    semanticModelApiName=sdm_api,
    apiNames=[dim_apis + measure_apis])
# Then apply via update_semantic_model_dimension / update_semantic_model_measure

# Generate suggested questions for walkthrough
questions = generate_questions(
    semanticModelApiName=sdm_api,
    questionsToGenerate=10,
    seedQuestions=[
        "What is the overall enrollment trend?",
        "Which region has the steepest decline?"
    ])

# Natural-language analysis for walkthrough content
answer = analyze_data(
    utterance="What is driving the enrollment decline?",
    targetEntityType="sdm",
    targetEntityIdOrApiName=sdm_api)
```

### Phase 14: Preview and validate

```python
# Render a viz to preview it
render_visualization(visualizationId=viz_id)

# Render a metric card
render_metric(
    metricApiName="enrollment_rate_mtc",
    modelApiName=sdm_api,
    bundleType="BAN",
    layout="BILLBOARD")

# Show the full dashboard
show_dashboard(
    dashboardIdOrApiName="demo_dashboard",
    addVisualization=True,
    addSdm=True,
    minorVersion=-1)

# Query to validate data signals
run_semantic_query(
    semanticModelApiName=sdm_api,
    structuredMetricQuery={
        "model_api_name": sdm_api,
        "submetric_definition": {"metric_api_name": "enrollment_rate_mtc"},
        "time_grain": "Month"
    })
```

## What stays the same (not MCP)

- **Data generation** — Python/numpy synthetic data with signal ramps, noise, compound multipliers
- **CSV export** — pandas `.to_csv()`
- **HTTP PUT for file upload** — MCP gives presigned URL but the PUT is manual
- **Pulse metrics** — entirely separate API (`/api/-/pulse/*`), not covered by MCP
- **Pulse Insights (BAN/Brief)** — separate Pulse API
- **`.twb` workbook generation** — `twb_builder.py`, Tableau Desktop format
- **`.tflx` Prep flows** — `prep_flow_builder.py`
- **`.docx` walkthrough generation** — python-docx
- **CRMA dashboards** — `crma_uploader.py`, `crma_dashboard_builder.py`
- **Checkpoint/resume** — still need checkpoint JSON for crash recovery

## MCP detection in `/build-demo`

When `/build-demo` runs, detect whether the MCP is available:

1. Check if `tableau-next-pilot` MCP tools are loaded (tool names start with `mcp__tableau-next-pilot__`)
2. If available and the user selects "Tableau Next" build type, use the MCP approach documented here
3. If not available, fall back to the existing direct REST approach

This keeps the builder working in both MCP-connected and non-MCP environments.

## Known MCP constraints

- **Presigned URL upload** — the MCP gives you the URL but cannot do the HTTP PUT; you must use `requests.put()` or equivalent outside the MCP
- **Response double-wrapping** — many MCP responses wrap as `{"defaultExc": "<stringified JSON>", "responseCode": N}`; parse accordingly
- **`isVisible` silent reset** — updating any measure/dimension property without including `isVisible` silently resets it to `true`
- **DMO category** — `"Engagement"` DMOs cannot be mapped from file-upload DLOs; default to `"Other"`
- **DLO-to-DMO mapping not idempotent** — duplicate mapping = 500 error
- **Relationship criteria for IngestAPI DLOs** — still silently dropped (same as direct REST); continue denormalizing
- **`generate_insight_bundle`** — internal/app-only, not for direct client use
- **Only simple-CASE in expressions** — searched-CASE and `IF()` not supported in calc measures
- **Grid is 48 columns** — not 72 as in direct REST dashboard layouts
