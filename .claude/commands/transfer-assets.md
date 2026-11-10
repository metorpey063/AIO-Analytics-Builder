# /transfer-assets — Transfer Tableau Next Assets Between Orgs

Package a Tableau Next dashboard from one Salesforce org and deploy it to another using the Package & Deploy API.

---

## What this does

Uses the Tableau Next Package & Deploy service (`https://next-package-deploy.demo.tableau.com`) to:

1. **Package** a dashboard from a source org — extracts the full dependency tree (dashboard, visualizations, SDM structure, metrics, calculated fields) into a portable JSON
2. **Deploy** it to a target org — creates a new workspace + SDM with proper field mappings, or maps to an existing one

This solves the cross-org field name mismatch problem (e.g. `region6` in one org vs `region1` in another) that makes manual dashboard copying unreliable.

---

## Prerequisites

Both orgs must be set up as profiles via `/setup`. If they aren't:
> "One or both orgs aren't configured yet. Run `/setup` to create profiles for the source and target orgs first."

The target org must have:
- Data Cloud enabled and configured
- An ingest connector configured (via `/setup`)

The target org does NOT need to have a matching DLO or data stream already. If the data infrastructure doesn't exist, `transfer_assets.py run` creates it (schema registration, stream creation, row copy).

---

## How to run

**Use `transfer_assets.py` for every step — never re-write the package/ingest/deploy calls inline.** The Web UI's Transfer Assets page runs the same engine. Tested end to end on 2026-11-10 (AIO Test Org → AIO Dev: 5 dashboards, 18,000 rows, all metrics matching the source).

Guide the user one step at a time (buttons, not "type next"):

### Step 1 — Source and target

Ask which profile is the **source** (where the dashboards are today) and which is the **target**. Show each profile's label *and* org URL (`config.json` profiles; labels can be stale). Source and target must differ.

If a profile's token refresh fails with `invalid_client_id`, its saved client ID no longer matches the org's AIO app. Re-authorize it (browser login):
```bash
python3 org_bootstrap.py authorize --alias <sf-cli-alias> --profile <profile_key>
```

### Step 2 — Pick dashboards (read-only)

```bash
python3 transfer_assets.py list --profile <source>
```
Dashboards transferred together go into **one** workspace and share **one** SDM, so pick dashboards from one source workspace. Skip managed-app dashboards (`template` set, e.g. Sales Insights): use `/deploy-sales-insights` for those.

### Step 3 — Check (read-only)

Pick a slug for the transfer folder (e.g. `transfer_{target}_{workspace}`), then:
```bash
python3 transfer_assets.py plan --source <src> --target <tgt> --dashboards a,b,c --slug <slug> --fresh
```
This packages each dashboard into `demos/{slug}/{name}_package.json` and prints `PLAN_JSON {...}`: vizzes/metrics per dashboard, whether they share one SDM, and per data object whether the target will **reuse** an existing stream (same schema name) or **create + copy rows**. Show the plan and confirm before Step 4.

### Step 4 — Transfer (writes to the target only)

```bash
python3 -u transfer_assets.py run --source <src> --target <tgt> --dashboards a,b,c --slug <slug> \
    --workspace-label "Acme Demo" [--sdm-name Acme_Demo]
```
Run it in the background (5–15 min). The engine:
1. Finds each Ingest API DLO the packages use, and its schema on the source connector
2. In the target: reuses a stream built from the same schema, or registers the schema + creates the stream, then copies every row from the source (Query API → Bulk Ingest upsert) and waits until the rows are queryable
3. Patches source DLO names → target DLO names in the packages
4. Deploys the first dashboard with a new workspace + SDM, then the rest into that workspace + SDM ("Found existing model")
5. Verifies: every target metric returns the same yearly values as the source (`cp["verify"]`)

Checkpointed in `demos/{slug}/{slug}_transfer_checkpoint.json`: re-running the same command resumes and skips finished dashboards. `cp["created"]` lists every workspace/SDM the transfer created.

### Step 5 — Summary

Report the workspace, SDM, dashboard count, row count and the verify result. Remind the user to share the workspace in the UI (Share → All Internal Users → View) — the API can't.

### Undo

```bash
python3 transfer_assets.py remove --target <tgt> --slug <slug> [--workspaces ws1,ws2]
```
Deletes dashboards, vizzes, workspaces and SDMs listed in `cp["created"]` only. Data streams stay. Confirm with the user first.

### Verify again later (read-only)

```bash
python3 transfer_assets.py verify --source <src> --target <tgt> --slug <slug>
```

---

## API Reference

**Base URL:** `https://next-package-deploy.demo.tableau.com`

**Authentication:** Pass-through headers on every request:
- `Authorization: Bearer <SALESFORCE_ACCESS_TOKEN>`
- `X-Instance-Url: <org_instance_url>` (e.g. `https://trailsignup-xyz.my.salesforce.com`)
- `Content-Type: application/json`

**Important:** Use the SOURCE org's token for packaging (Steps 2-3). Switch to the TARGET org's token for deployment (Steps 4-6). Never write to the source org.

**Endpoints:**

| Action | Method | Path |
|--------|--------|------|
| List dashboards | GET | `/api/v1/dashboards/list` |
| Package dashboard | POST | `/api/v1/dashboards/package` |
| Package status | GET | `/api/v1/dashboards/package/status/{job_id}` |
| List workspaces (target) | GET | `/api/v1/deployment/workspaces` |
| List SDMs (target) | GET | `/api/v1/deployment/semantic-models` |
| Validate requirements | POST | `/api/v1/deployment/validate-requirements` |
| Validate package | POST | `/api/v1/deployment/validate-package` |
| Deploy | POST | `/api/v1/deployment/deploy` |
| Deploy status | GET | `/api/v1/deployment/deploy/status/{job_id}` |

---

## Known issues

- **DLO validation:** The tool validates that the DLO referenced in the package exists in the target org. Since DLO names include org-specific suffixes, the package must be patched before deploying — `run` does this.
- **Match target data by schema name, not DLO prefix.** Stream names are `{connector_short}_{schema}_{HASH}` and DLO names truncate that, so a source DLO `analytics_builder_demo_salesfor_C27D2110__dll` (connector `analytics_builder_demo`) becomes `analytics_builder_salesforce_te_0500ED45__dll` in an org whose connector is `analytics_builder`. A DLO-prefix match finds nothing across orgs with different connector names.
- **The stream GET has no schema fields.** `GET /ssot/data-streams/{name}` returns `dataLakeFieldInfoRepresentation` (incl. system fields) and no event/schema name. Read the field list from the connector's `GET /ssot/connections/{id}/schema`.
- **Query API v2 column metadata is a dict**, `{"col__c": {"type", "placeInOrder"}}`, not a `columns` list. Sort by `placeInOrder`. Select only schema columns (`{field}__c`) to leave out `DataSource`, `KQ_*` and `cdp_sys_*`.
- **The deploy status doesn't name the SDM** (only `workspace_api_name`); it's in the step `"Semantic Model 'X' created"`. Without it every later dashboard silently creates its own workspace + SDM (`X1`, `X_2`, …).
- **`/ssot/data-streams` rejects `limit` above 200** (400). Page with `offset`. Listing takes 25–45s on a busy org, so the engine caches it.
- **Data infrastructure creation:** When auto-creating data infrastructure (Step 4c), the target org's ingest connector must already be configured via `/setup`. The schema, stream, and data are created automatically, but the connector is a one-time setup step.
- **Data sourced from source org:** When creating data infrastructure, the command always downloads data directly from the source org via the Data Cloud Query API (`POST /api/v2/query`). This works regardless of whether the demo was originally built by this tool. Requires `cdp_query_api` scope on the source org's connected app. Falls back to asking for a CSV if the query fails.
- **Schema propagation delay:** After registering a schema and creating a stream, there's a 20-30 second propagation delay before the bulk ingest API recognizes the new object. The command handles this with automatic retries.
- **"Use existing" SDM:** When deploying to an existing SDM, the tool validates field names exactly. If the target org has different auto-generated suffixes (e.g. `region1` vs `region6`), you need a complete `dependency_map`. The "Create new" option avoids this entirely and is recommended.
- **Token expiration:** Some orgs have aggressive token rotation. If deploy fails with auth errors, re-run `/setup` Step 4b to refresh the token for that profile.
- **Internal tool:** This is an internal Salesforce tool (not a public product). Availability is not guaranteed. If the service is down, fall back to manual dashboard recreation.
- **One dashboard per package:** the service packages one dashboard at a time; `run` loops over them and deploys the rest into the first one's workspace + SDM.
- **Single SDM:** The dashboard must use a single semantic model. Multi-SDM dashboards are not supported.
- **No SDM extensions:** The source SDM must be self-contained (not extended from another model).
- **Layout alignment:** On 2026-11-10 (5 AIO dashboards, API 67.14) every widget landed at the source's row/column/size, so no alignment step is needed. Older reports (Sales Insights clone, 91-col grid) saw shifted widgets; if that happens, compare source and target `layouts[].pages[].widgets` and PATCH the dashboard on v67.0.
- **Grid column scaling:** if you do realign, scale `column`/`colspan` by `target_grid / src_grid` (REST = 72, MCP = 48; the Sales Insights source used 91).

---

## Complete payload examples

### List dashboards response
```json
{"dashboards": [
  {"name": "DDI_Perf", "label": "DDI Perf", "workspaceIdOrApiName": "DDI_Analytics", "id": "0Tr...", "...": "..."},
  {"name": "Sales_Performance", "label": "Sales Performance", "workspaceIdOrApiName": "Sales_Insights",
   "templateSource": {"name": "sfdc_internal__SalesInsightsTN", "assetName": "Sales_Performance"}}
]}
```

### Package request
```json
{"dashboard_api_name": "DDI_Perf"}
```

### Package status response (completed)
```json
{
  "status": "completed",
  "job_id": "ea15708d-5537-4c9a-8f38-3f8e7ecf3f21",
  "package_data": {
    "templateId": "DDI_Perf",
    "apiVersion": "67.10",
    "requirements": {
      "metrics": ["active_lead_count_mtc", "franchise_revenue_mtc", "..."],
      "fields": [
        {"fieldName": "Display_Date", "objectName": null},
        {"fieldName": "region6", "objectName": "DDI_Franchise_Performance_Fact"},
        {"fieldName": "franchise_revenue_clc", "objectName": null}
      ],
      "listParameters": []
    },
    "components": {
      "visualizations": {"Viz_Name": {"...viz definition..."}},
      "dashboard": {"label": "DDI Perf", "layouts": [], "widgets": {}, "style": {}},
      "semanticModel": {"apiName": "placeholder", "agentEnabled": true, "...": "..."},
      "dimensions": [{"apiName": "Display_Date", "label": "Display Date", "expression": "..."}],
      "measurements": [{"apiName": "franchise_revenue_clc", "label": "Franchise Revenue", "expression": "..."}],
      "metrics": [{"apiName": "franchise_revenue_mtc", "label": "Franchise Revenue", "...": "..."}]
    }
  }
}
```

### Validate requirements response
```json
{
  "valid": false,
  "missing": {
    "Metric": ["Projects_Completed_mtc", "Royalty_Amount_mtc"],
    "DMO Field": ["region6", "franchise_tier", "close_rate"]
  },
  "available": {
    "Metric": {"franchise_revenue_mtc": "Franchise Revenue", "...": "..."},
    "Dimension": {"Display_Date": "Display Date"},
    "Measurement": {"franchise_revenue_clc": "Franchise Revenue"},
    "DMO Field": {"region1": "region", "franchise_tier1": "franchise_tier", "close_rate1": "close_rate"}
  }
}
```

### Deploy request (create new)
```json
{
  "package_data": {"...package from step 3..."},
  "workspace_choice": "create",
  "workspace_label": "DDI Franchise Performance",
  "sdm_choice": "create",
  "sdm_api_name": "DDI_Franchise_Performance",
  "dependency_map": {},
  "dry_run": false,
  "skip_validation": false
}
```

### Deploy request (use existing with mapping)
```json
{
  "package_data": {"...package from step 3..."},
  "workspace_choice": "existing",
  "workspace_api_name": "DDI_Franchise_Performance1",
  "sdm_choice": "existing",
  "sdm_api_name": "DDI_Franchise_Performance_5e61",
  "dependency_map": {
    "Projects_Completed_mtc": "projects_completed_mtc",
    "Royalty_Amount_mtc": "royalty_amount_mtc",
    "region6": "region1",
    "franchise_tier": "franchise_tier1",
    "close_rate": "close_rate1"
  },
  "dry_run": false,
  "skip_validation": true
}
```

### Deploy status response (success)
```json
{
  "status": "completed",
  "created_at": "2026-08-06T18:30:00.000000",
  "steps": [
    "Validating package...",
    "Creating workspace: DDI_Franchise_Performance2",
    "Creating semantic model...",
    "Deploying calculated dimensions...",
    "Deploying calculated measurements...",
    "Deploying metrics...",
    "Deploying visualizations...",
    "Dashboard deployed"
  ],
  "workspace_api_name": "DDI_Franchise_Performance2",
  "workspace_url": "https://trailsignup-xyz.lightning.force.com/tableau/workspace/DDI_Franchise_Performance2",
  "error": null,
  "completed_at": "2026-08-06T18:30:45.000000"
}
```

### Deploy status response (failure)
```json
{
  "status": "failed",
  "steps": ["Validating package..."],
  "workspace_api_name": null,
  "workspace_url": null,
  "error": "{\"message\": \"Package validation failed with 1 blocking error(s): DLO 'xyz__dll' not found\", \"code\": \"DLO_NOT_FOUND\", \"validation_skipped\": false}",
  "completed_at": "2026-08-06T18:31:00.000000"
}
```

---

## DLO name pattern

Stream: `{connector_short}_{schema}_{8_HEX}`. DLO: the same string truncated (`{connector_short}_{schema[:n]}_{8_HEX}__dll`).

Example (verified 2026-11-10):
- Source (connector `analytics_builder_demo`): stream `analytics_builder_demo_salesforce_test_demo_C27D2110`, DLO `analytics_builder_demo_salesfor_C27D2110__dll`
- Target (connector `analytics_builder`): stream `analytics_builder_salesforce_test_demo_0500ED45`, DLO `analytics_builder_salesforce_te_0500ED45__dll`

The prefix differs whenever the connectors differ, so match on the **schema name** (`salesforce_test_demo`): stream name ends in `_{schema}_{8_HEX}`. `transfer_assets.find_target_stream()` does this.

---

## Relationship to Data Kits

Salesforce also offers **Data Kits** as the official mechanism for migrating Tableau Next assets (SDMs, workspaces, vizzes, dashboards) between orgs via Change Sets or the SF CLI. Data Kits are more appropriate for:
- Production deployments (sandbox → prod)
- Managed packages (ISV distribution)
- CI/CD pipelines

The Package & Deploy API is faster for:
- Demo-to-demo transfers
- Quick replication across SE orgs
- Iterative dashboard development across test environments

For Data Kit documentation, see:
- https://help.salesforce.com/s/articleView?id=analytics.tua_deploy_assets_datakit.htm
- https://developer.salesforce.com/docs/data/data-cloud-dev/guide/packages-data-kits.html
- https://github.com/tcufrogger/tableau-next-industry-data-kits (community industry kits)

---

## Safety rules

- **NEVER write to the source org.** All source org interactions are READ-ONLY (list dashboards, package).
- **Always confirm with the user** before deploying to the target org.
- **Save the package JSON locally** before attempting deployment — if deploy fails, the package can be re-used without re-packaging.
- **Do not delete assets in the source org** as part of this flow — this is a copy, not a move.
