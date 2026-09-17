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

The target org does NOT need to have a matching DLO or data stream already. If the data infrastructure doesn't exist, `/transfer-assets` will create it automatically (schema registration, stream creation, data ingest) as part of Step 4.

---

## How to run

When you invoke `/transfer-assets`, guide the user through these steps one at a time:

### Step 1 — Source and Target

Ask:
> "Which profile is the **source** (where the dashboard exists today)?"

Show the list of available profiles (same as `/setup` Step 1b).

Then ask:
> "Which profile is the **target** (where you want to deploy the dashboard)?"

Validate both connections before proceeding.

### Step 2 — Select Dashboard

Using the source org's token, list available dashboards:

```python
DEPLOY_BASE = "https://next-package-deploy.demo.tableau.com"
headers = {
    "Authorization": f"Bearer {sf_token}",
    "X-Instance-Url": sf_instance,
    "Content-Type": "application/json",
}
r = requests.get(f"{DEPLOY_BASE}/api/v1/dashboards/list", headers=headers)
```

Show the list and ask:
> "Which dashboard do you want to transfer?"

### Step 3 — Package

Start the async packaging job:

```python
r = requests.post(f"{DEPLOY_BASE}/api/v1/dashboards/package", headers=headers,
                  json={"dashboard_api_name": dashboard_name})
job_id = r.json().get("job_id")
```

Poll until complete:
```python
r = requests.get(f"{DEPLOY_BASE}/api/v1/dashboards/package/status/{job_id}", headers=headers)
# status: "running" → "completed"
# When completed, response includes "package_data"
```

Save the package locally at `demos/{slug}/{slug}_package.json`.

### Step 4 — DLO Mapping (auto-creates data infrastructure if needed)

The package references the source org's DLO name. The target org needs a matching DLO — either one that already exists, or one that `/transfer-assets` creates automatically.

**4a — Find the source DLO name** from the package:
```python
import re
pkg_str = json.dumps(package_data)
dlo_matches = re.findall(r'[a-z_]+__dll', pkg_str)
source_dlo = dlo_matches[0] if dlo_matches else None
# Extract schema prefix (everything before the last _XXXXXXXX__dll)
source_prefix = re.sub(r'_[A-Fa-f0-9]{8}__dll$', '', source_dlo)
```

**4b — Search for a matching DLO in the target org:**
```python
# Using target org token
r = requests.get(f"{tgt_instance}/services/data/v62.0/ssot/data-streams",
                 headers=tgt_h, params={"connectorId": tgt_connector_id, "limit": 200})
target_dlo = None
target_stream_name = None
for stream in r.json().get("dataStreams", []):
    if source_prefix in stream.get("name", "").lower():
        stream_detail = requests.get(
            f"{tgt_instance}/services/data/v62.0/ssot/data-streams/{stream['name']}",
            headers=tgt_h)
        target_dlo = stream_detail.json().get("dataLakeObjectInfo", {}).get("name", "")
        target_stream_name = stream["name"]
        break
```

**4c — If no matching DLO exists, auto-create the data infrastructure:**

Tell the user:
> "The target org doesn't have a matching data stream. I'll create the data infrastructure now — this takes 2-5 minutes."

**4c.1 — Get the schema from the source org:**
```python
# Find the source stream to extract its schema fields
src_r = requests.get(f"{src_instance}/services/data/v62.0/ssot/data-streams",
                     headers=src_h, params={"connectorId": src_connector_id, "limit": 200})
for stream in src_r.json().get("dataStreams", []):
    if source_prefix in stream.get("name", "").lower():
        src_stream = requests.get(
            f"{src_instance}/services/data/v62.0/ssot/data-streams/{stream['name']}",
            headers=src_h).json()
        break

# Extract field definitions from the source stream
src_fields = src_stream.get("dataLakeObjectInfo", {}).get("dataLakeFieldInputRepresentations", [])
# These give us: name, label, dataType, isPrimaryKey for each field
```

**4c.2 — Download data from the source org:**

Always pull data directly from the source org via the Data Cloud Query API. This ensures the transfer works regardless of whether we built the original demo or not.

```python
from connections import get_dc_token

# Get Data Cloud token for the SOURCE org
src_dc_token, src_dc_domain = get_dc_token(src_sf_token, src_instance)

# Query the source DLO for all rows
query_url = f"https://{src_dc_domain}/api/v2/query"
query_payload = {"sql": f"SELECT * FROM {source_dlo}"}
r = requests.post(query_url, headers={
    "Authorization": f"Bearer {src_dc_token}",
    "Content-Type": "application/json",
}, json=query_payload)

if r.status_code not in (200, 201):
    raise RuntimeError(f"Failed to query source data: {r.status_code} {r.text[:300]}")

result = r.json()
columns = [col["name"] for col in result.get("metadata", {}).get("columns", [])]
rows = result.get("data", [])

import pandas as pd
df = pd.DataFrame(rows, columns=columns)
print(f"  Downloaded {len(df):,} rows from source org")

# Convert to CSV bytes for ingest
# Column names from Data Cloud have __c suffix — strip for ingest schema matching
ingest_df = df.copy()
ingest_df.columns = [c.replace("__c", "") for c in ingest_df.columns]
csv_bytes = ingest_df.to_csv(index=False).encode("utf-8")

# Save a local copy for reference
csv_path = os.path.join(DEMO_DIR, f"{schema_name}_transferred.csv")
ingest_df.to_csv(csv_path, index=False)
print(f"  Saved local copy: {csv_path}")
```

**Pagination:** If the source DLO has more than 10,000 rows, the Query API paginates. Handle with `nextBatchId`:
```python
all_rows = []
next_batch = None
while True:
    payload = {"sql": f"SELECT * FROM {source_dlo}"}
    if next_batch:
        payload["nextBatchId"] = next_batch
    r = requests.post(query_url, headers=query_headers, json=payload)
    result = r.json()
    all_rows.extend(result.get("data", []))
    next_batch = result.get("nextBatchId")
    if not next_batch:
        break
```

**If the Query API fails** (missing `cdp_query_api` scope, or source org doesn't support it), fall back to asking the user:
> "I couldn't query data from the source org directly. Please provide a CSV file path containing the data to ingest into the target org."

**4c.3 — Register schema in target org:**
```python
# GET existing schemas, merge, PUT
tgt_connector_id = tgt_config["salesforce"]["connector_sf_id"]
r = requests.get(f"{tgt_instance}/services/data/v62.0/ssot/connections/{tgt_connector_id}/schema",
                 headers=tgt_h)
existing = r.json().get("schemas", [])

STRIP_FIELDS = {"availabilityStatus", "createdDate", "lastModifiedDate"}
cleaned = [{k: v for k, v in s.items() if k not in STRIP_FIELDS} for s in existing]

# Build schema from source fields
schema_fields = [{"name": f["name"], "label": f.get("label", f["name"]),
                  "dataType": f["dataType"]} for f in src_fields]
new_schema = {"name": schema_name, "label": schema_name,
              "schemaType": "IngestApi", "fields": schema_fields}

# Merge or append
if schema_name in [s["name"] for s in cleaned]:
    merged = [new_schema if s["name"] == schema_name else s for s in cleaned]
else:
    merged = cleaned + [new_schema]

requests.put(f"{tgt_instance}/services/data/v62.0/ssot/connections/{tgt_connector_id}/schema",
             headers=tgt_h, json={"schemas": merged})
time.sleep(20)  # Schema propagation
```

**4c.4 — Create data stream in target org:**

Use the exact stream creation payload format from CLAUDE.md (with `datastreamType`, `dataLakeObjectInfo`, `dataspaceInfo`, `mappings`). Find the `isPrimaryKey` field from the source fields and include it in `dataLakeFieldInputRepresentations`.

```python
tgt_connector_uuid = tgt_config["salesforce"]["connector_uuid_name"]
tgt_connector_short = tgt_config["salesforce"]["ingestion_connector_name"]
pk_field = next((f["name"] for f in src_fields if f.get("isPrimaryKey")), "record_id")

stream_payload = {
    "name": schema_name, "label": schema_name,
    "datasource": tgt_connector_short[:10],
    "datastreamType": "INGESTAPI",
    "connectorInfo": {
        "connectorType": "IngestApi",
        "connectorDetails": {"name": tgt_connector_uuid, "events": [schema_name]},
    },
    "dataLakeObjectInfo": {
        "label": schema_name, "category": "Other",
        "dataspaceInfo": [{"name": "default"}],
        "dataLakeFieldInputRepresentations": [
            {"name": pk_field, "label": pk_field, "dataType": "Text", "isPrimaryKey": True}
        ],
        "eventDateTimeFieldName": "", "recordModifiedFieldName": "",
    },
    "mappings": [],
}
r = requests.post(f"{tgt_instance}/services/data/v62.0/ssot/data-streams",
                  headers=tgt_h, json=stream_payload)
```

If the stream already exists ("already in use"), discover the existing stream name and DLO.

Poll for ACTIVE status, then wait 30s for schema propagation.

**4c.5 — Bulk ingest data:**

```python
tgt_dc_token, tgt_dc_domain = get_dc_token(tgt_sf_token, tgt_instance)

# Create ingest job
job_r = requests.post(f"https://{tgt_dc_domain}/api/v1/ingest/jobs",
    headers={"Authorization": f"Bearer {tgt_dc_token}", "Content-Type": "application/json"},
    json={"object": schema_name, "operation": "upsert", "sourceName": tgt_connector_short})

job_id = job_r.json().get("id")

# Upload CSV
requests.put(f"https://{tgt_dc_domain}/api/v1/ingest/jobs/{job_id}/batches",
    headers={"Authorization": f"Bearer {tgt_dc_token}", "Content-Type": "text/csv"},
    data=csv_bytes)

# Close job
requests.patch(f"https://{tgt_dc_domain}/api/v1/ingest/jobs/{job_id}",
    headers={"Authorization": f"Bearer {tgt_dc_token}", "Content-Type": "application/json"},
    json={"state": "UploadComplete"})

# Poll until JobComplete (up to 10 minutes)
```

After ingest completes, the target DLO and stream name are known — proceed to 4d.

**4d — Patch the package:**

Replace the source DLO name with the target DLO name:
```python
pkg_str = json.dumps(package_data)
pkg_str = pkg_str.replace(source_dlo, target_dlo)
package_data = json.loads(pkg_str)
```

### Step 5 — Deployment Options

Ask:
> "How would you like to deploy?
> 1. **Create new** (recommended) — creates a new workspace and SDM in the target org
> 2. **Use existing** — deploy into an existing workspace/SDM (requires field mapping)"

**If "Create new" (recommended):**
```python
deploy_payload = {
    "package_data": package_data,
    "workspace_choice": "create",
    "workspace_label": "Dashboard Label Here",
    "sdm_choice": "create",
    "sdm_api_name": "Suggested_Api_Name",
    "dependency_map": {},
    "dry_run": False,
    "skip_validation": False,
}
```

**If "Use existing":**

First validate requirements:
```python
r = requests.post(f"{DEPLOY_BASE}/api/v1/deployment/validate-requirements", headers=headers,
                  json={"package_data": package_data, "sdm_api_name": target_sdm})
```

If validation shows missing fields, build a `dependency_map` by matching source field names to available target field names (match by base name, ignoring numeric suffixes).

```python
deploy_payload = {
    "package_data": package_data,
    "workspace_choice": "existing",
    "workspace_api_name": target_ws,
    "sdm_choice": "existing",
    "sdm_api_name": target_sdm,
    "dependency_map": dependency_map,
    "dry_run": False,
    "skip_validation": True,  # may need to skip if DLO validation blocks
}
```

### Step 6 — Deploy

```python
r = requests.post(f"{DEPLOY_BASE}/api/v1/deployment/deploy", headers=target_headers, json=deploy_payload)
job_id = r.json().get("job_id")

# Poll every 5 seconds
for attempt in range(60):
    time.sleep(5)
    r = requests.get(f"{DEPLOY_BASE}/api/v1/deployment/deploy/status/{job_id}", headers=target_headers)
    status_data = r.json()
    status = status_data.get("status", "unknown")
    steps = status_data.get("steps", [])
    last_step = steps[-1] if steps else ""
    # Print progress
    if status in ("completed", "done", "success"):
        break
    elif status in ("failed", "error"):
        break
```

Print progress as each step completes (the status response includes a `steps` array).

### Step 7 — Summary

On success, print:
> ## Transfer Complete
>
> **Dashboard:** {dashboard_label}
> **Source:** {source_profile_label} ({source_instance})
> **Target:** {target_profile_label} ({target_instance})
>
> **Deployed assets:**
> - Workspace: {workspace_api_name}
> - SDM: {sdm_api_name}
> - Dashboard URL: {workspace_url}
>
> The dashboard is ready to use in the target org.

On failure, print the error and suggest next steps based on the error code:
- `DLO_NOT_FOUND` → DLO name wasn't patched correctly, or data hasn't been ingested to target
- `DEPLOY_EXECUTION_FAILED` → field mapping issue, suggest using "Create new" instead
- Auth errors → re-run `/setup` to refresh the target org token

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

- **DLO validation:** The tool validates that the DLO referenced in the package exists in the target org. Since DLO names include org-specific UUID suffixes, you MUST patch the DLO name in the package before deploying. Step 4 handles this automatically (including creating the DLO if needed).
- **Data infrastructure creation:** When auto-creating data infrastructure (Step 4c), the target org's ingest connector must already be configured via `/setup`. The schema, stream, and data are created automatically, but the connector is a one-time setup step.
- **Data sourced from source org:** When creating data infrastructure, the command always downloads data directly from the source org via the Data Cloud Query API (`POST /api/v2/query`). This works regardless of whether the demo was originally built by this tool. Requires `cdp_query_api` scope on the source org's connected app. Falls back to asking for a CSV if the query fails.
- **Schema propagation delay:** After registering a schema and creating a stream, there's a 20-30 second propagation delay before the bulk ingest API recognizes the new object. The command handles this with automatic retries.
- **"Use existing" SDM:** When deploying to an existing SDM, the tool validates field names exactly. If the target org has different auto-generated suffixes (e.g. `region1` vs `region6`), you need a complete `dependency_map`. The "Create new" option avoids this entirely and is recommended.
- **Token expiration:** Some orgs have aggressive token rotation. If deploy fails with auth errors, re-run `/setup` Step 4b to refresh the token for that profile.
- **Internal tool:** This is an internal Salesforce tool (not a public product). Availability is not guaranteed. If the service is down, fall back to manual dashboard recreation.
- **Single dashboard:** The tool packages one dashboard at a time. For multiple dashboards, run the transfer multiple times.
- **Single SDM:** The dashboard must use a single semantic model. Multi-SDM dashboards are not supported.
- **No SDM extensions:** The source SDM must be self-contained (not extended from another model).

---

## Complete payload examples

### List dashboards response
```json
[
  {"name": "DDI_Perf", "label": "DDI Perf"},
  {"name": "Sales_Performance", "label": "Sales Performance"}
]
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

DLO names follow this pattern: `{schema_short}_{schema_short_truncated}_{8_CHAR_HEX}__dll`

Example:
- Source org: `ddi_franchise_perf_ddi_franchis_8C46EE58__dll`
- Target org: `ddi_franchise_perf_ddi_franchis_7A1C1199__dll`

The schema prefix is the same — only the hex suffix differs. To find the target DLO:
1. Get the schema prefix from the source DLO (everything before the last `_XXXXXXXX__dll`)
2. Search the target org's data streams for one with the same prefix
3. Extract the full DLO name from the matching stream's `dataLakeObjectInfo.name`

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
