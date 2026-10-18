"""
AIO Analytics Builder — Web UI Build Orchestrator
Runs the full build pipeline in a background thread with SSE progress updates.
"""

import csv
import io
import json
import os
import random
import re
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TODAY = date.today()


# ---------------------------------------------------------------------------
# Progress helper
# ---------------------------------------------------------------------------

def progress(q, stage, message, pct=-1):
    if q:
        q.put({"stage": stage, "message": message, "pct": pct})


# ---------------------------------------------------------------------------
# Story + metric generation via Claude API
# ---------------------------------------------------------------------------

STORY_SYSTEM_PROMPT = """You are a data analytics demo designer for Tableau and Salesforce.
Given a company name, industry, use case, audience, and optional notes, generate a complete demo configuration.

Return ONLY valid JSON with this exact structure:
{
  "story_summary": "2-3 sentence narrative describing the company context and the analytical story",
  "signal_description": "1 sentence describing the engineered signal (e.g., 'accelerating decline in X over 3 months, concentrated in Y segment')",
  "dimensions": ["Region", "Department", "Category"],
  "metric_config": [
    {
      "label": "Revenue Growth Rate",
      "field": "revenue_growth_rate",
      "agg": "Average",
      "description": "Measures period-over-period revenue change",
      "why_it_matters": "Indicates business health trajectory",
      "singular": "revenue growth rate",
      "plural": "revenue growth rates",
      "sentiment": "up_is_good",
      "pulse_agg": "AGGREGATION_AVERAGE",
      "is_primary": true
    }
  ]
}

Rules:
- Generate 3-5 metrics. 1-2 should be primary (is_primary: true) with strong signal, rest are supporting.
- Primary metrics show the "uh oh" moment. Supporting metrics explain why or show consequences.
- Include at least one counter-trend metric (one that improves while others decline).
- Dimensions should enable drill-down: at least one "where" dimension (Region, Location), one "what" dimension (Category, Type), one "who" dimension (Team, Rep).
- Field names use snake_case with no spaces.
- Sentiment: "up_is_good" or "down_is_good".
- All metrics should be rates/averages stored as decimals (0.0-1.0 range) OR flow metrics stored as raw numbers.
- pulse_agg: "AGGREGATION_AVERAGE" for rates, "AGGREGATION_SUM" for flows/counts.
"""


def generate_story(company, industry, use_case, audience, notes=""):
    """Call Claude API to generate story + metrics. Returns dict."""
    from app import _get_chat_config, CHAT_MODEL

    cfg = _get_chat_config()
    if not cfg:
        raise RuntimeError("No API key configured for AI generation")

    user_msg = f"""Company: {company}
Industry: {industry}
Use case / topic: {use_case}
Audience: {audience}
Additional context: {notes or 'None'}"""

    if cfg["mode"] == "bedrock_gateway":
        import requests as req
        url = f"{cfg['base_url']}/model/{CHAT_MODEL}/invoke"
        headers = {"x-api-key": cfg["token"], "Content-Type": "application/json"}
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "system": STORY_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        }
        r = req.post(url, headers=headers, json=body,
                     verify=cfg.get("ca_bundle", True), timeout=60)
        r.raise_for_status()
        text = ""
        for block in r.json().get("content", []):
            if block.get("type") == "text":
                text += block["text"]
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=cfg["api_key"])
        resp = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=2048,
            system=STORY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text

    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        raise RuntimeError("AI did not return valid JSON")
    return json.loads(match.group())


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

def signal_ramp(d, onset=-3, shape="accelerating", duration=3):
    if isinstance(d, pd.Timestamp):
        d = d.date()
    months_from_today = (d.year - TODAY.year) * 12 + (d.month - TODAY.month)
    months_from_onset = months_from_today - onset
    if months_from_onset <= 0:
        return 0.0
    progress_val = min(1.0, months_from_onset / duration)
    if shape == "accelerating":
        return progress_val ** 2
    return progress_val


def generate_data(story_config, q=None):
    """Generate synthetic data from story config. Returns DataFrame."""
    metric_config = story_config["metric_config"]
    dimensions = story_config.get("dimensions", ["Region", "Category", "Segment"])

    history_months = 24
    signal_magnitude = 0.45
    supporting_magnitude = 0.30

    dim_values = {}
    for dim in dimensions:
        if dim.lower() in ("region", "location", "geography"):
            dim_values[dim] = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
        elif dim.lower() in ("category", "type", "product", "product category"):
            dim_values[dim] = ["Category A", "Category B", "Category C", "Category D"]
        elif dim.lower() in ("department", "team", "group"):
            dim_values[dim] = ["Sales", "Marketing", "Operations", "Support"]
        elif dim.lower() in ("segment", "tier", "level"):
            dim_values[dim] = ["Enterprise", "Mid-Market", "SMB", "Startup"]
        else:
            dim_values[dim] = [f"{dim} 1", f"{dim} 2", f"{dim} 3", f"{dim} 4"]

    segment_mults = {}
    for dim in dimensions:
        vals = dim_values[dim]
        mults = [random.uniform(1.5, 2.5)]
        mults.append(random.uniform(0.8, 1.2))
        mults.append(random.uniform(0.0, 0.4))
        while len(mults) < len(vals):
            mults.append(random.uniform(-0.15, 0.5))
        random.shuffle(mults)
        segment_mults[dim] = dict(zip(vals, mults))

    start_date = TODAY - relativedelta(months=history_months)
    dates = pd.date_range(start_date, TODAY, freq="MS").date.tolist()

    n_entities = 2
    from itertools import product as cartprod
    dim_combos = list(cartprod(*[dim_values[d] for d in dimensions]))

    rows = []
    entity_id = 0
    for combo in dim_combos:
        for ent in range(n_entities):
            entity_id += 1
            eid = f"E-{entity_id:04d}"
            base_values = {m["field"]: random.uniform(0.55, 0.85) for m in metric_config}

            for dt in dates:
                ramp = signal_ramp(dt, onset=-3, shape="accelerating", duration=3)
                primary_mult = max(segment_mults[dimensions[0]].get(combo[0], 1.0), 0.0)

                row = {"Record ID": f"{eid}_{dt.strftime('%Y%m%d')}", "Date": dt, "Entity ID": eid}
                for i, dim in enumerate(dimensions):
                    row[dim] = combo[i]

                for mc in metric_config:
                    base = base_values[mc["field"]]
                    is_primary = mc.get("is_primary", False)
                    sent = mc.get("sentiment", "up_is_good")

                    if is_primary:
                        mag = signal_magnitude
                        mult = primary_mult
                    else:
                        mag = supporting_magnitude
                        mult = primary_mult * 0.7

                    noise = np.random.normal(0, 0.015)
                    if sent == "up_is_good":
                        val = base * (1 - mag * ramp * mult) + noise
                    else:
                        val = base * (1 + mag * ramp * mult * 0.3) + noise

                    if mc["agg"] == "Average":
                        val = max(0.01, min(1.0, val))
                    else:
                        val = max(0, val * 1000)

                    row[mc["label"]] = round(val, 4)

                day_offset = (dt - TODAY).days
                row["Day_Offset"] = day_offset
                rows.append(row)

    df = pd.DataFrame(rows)
    if q:
        progress(q, "data", f"Generated {len(df)} rows, {len(df.columns)} columns", -1)
    return df


# ---------------------------------------------------------------------------
# Walkthrough document generation
# ---------------------------------------------------------------------------

def generate_walkthrough(slug, company, story_config, metric_config, build_type, checkpoint, demo_dir):
    """Generate a .docx walkthrough. Returns file path."""
    from docx import Document
    doc = Document()

    doc.add_heading("Demo Scenario", level=1)
    doc.add_heading(f"About {company}", level=2)
    doc.add_paragraph(story_config.get("story_summary", ""))
    doc.add_heading("Story & Signal", level=2)
    doc.add_paragraph(story_config.get("signal_description", ""))

    doc.add_heading("Metrics Reference", level=1)
    for mc in metric_config:
        doc.add_heading(mc["label"], level=2)
        p = doc.add_paragraph()
        p.add_run("What it measures: ").bold = True
        p.add_run(mc.get("description", ""))
        p2 = doc.add_paragraph()
        p2.add_run("Why it matters: ").bold = True
        p2.add_run(mc.get("why_it_matters", ""))

    if build_type == "pulse":
        doc.add_heading("Demo Click Path", level=1)
        doc.add_paragraph("Open Pulse and follow the metric story arc through filters and drill-downs.")
    elif build_type == "next":
        doc.add_heading("Concierge Prompts", level=1)
        doc.add_paragraph("Ask Concierge the following questions to walk through the demo story.")

    path = os.path.join(demo_dir, f"{slug}_demo_walkthrough.docx")
    doc.save(path)
    return path


# ---------------------------------------------------------------------------
# CSV build
# ---------------------------------------------------------------------------

def csv_build(build_id, df, slug, demo_dir, q):
    progress(q, "csv", "Exporting CSV...", 10)
    csv_path = os.path.join(demo_dir, f"{slug}_{TODAY.strftime('%Y%m%d')}.csv")
    df.to_csv(csv_path, index=False)
    progress(q, "csv", f"CSV exported: {len(df)} rows", 15)
    return csv_path


# ---------------------------------------------------------------------------
# Pulse build
# ---------------------------------------------------------------------------

def pulse_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp):
    import requests as req
    from connections import get_tableau_token, tableau_headers, tableau_pulse_headers

    csv_path = csv_build(build_id, df, slug, demo_dir, q)
    cp["csv_done"] = True
    cp["csv_path"] = csv_path
    _save_cp(cp, slug, demo_dir)

    progress(q, "publish", "Publishing datasource to Tableau Cloud...", 20)
    server, auth_token, site_id = get_tableau_token(config)
    import tableauserverclient as TSC

    project_name = f"{company} | {TODAY.strftime('%Y-%m-%d %H:%M')}"
    new_project = TSC.ProjectItem(name=project_name)
    project = server.projects.create(new_project)
    cp["pulse_project_id"] = project.id
    cp["pulse_project_name"] = project_name

    from tdsx_builder import publish_hyper_for_indexing
    ds_name = slug.replace("_", " ").title()
    ds_luid = publish_hyper_for_indexing(df, "Date", ds_name, project.id, server, demo_dir)
    cp["pulse_datasource_id"] = ds_luid
    cp["pulse_datasource_name"] = ds_name
    _save_cp(cp, slug, demo_dir)

    progress(q, "index", "Waiting for Tableau Cloud indexing (30s)...", 30)
    time.sleep(30)

    h_pulse = tableau_pulse_headers(auth_token)
    h = tableau_headers(auth_token)
    base = config["tableau"]["server_url"].rstrip("/")
    dimensions = story_config.get("dimensions", [])

    cp["pulse_metric_ids"] = []
    cp["pulse_def_ids"] = []

    for i, mc in enumerate(metric_config):
        pct = 40 + int(20 * (i / len(metric_config)))
        progress(q, "metrics", f"Creating metric {i+1}/{len(metric_config)}: {mc['label']}...", pct)

        payload = {
            "name": f"{company} — {mc['label']}",
            "description": mc.get("description", ""),
            "measurement": {"field": mc["label"], "aggregation": mc.get("pulse_agg", "AGGREGATION_AVERAGE")},
            "time_dimension": {"field": "Date"},
            "datasource": {"id": ds_luid},
            "is_running_total": mc.get("pulse_agg") == "AGGREGATION_SUM",
            "representation_options": {
                "type": "NUMBER_FORMAT_TYPE_NUMBER",
                "number_format": {
                    "number_of_decimal_places": 2,
                },
            },
            "extension_options": {
                "allowed_dimensions": dimensions,
                "allowed_granularities": [
                    "GRANULARITY_BY_MONTH",
                    "GRANULARITY_BY_QUARTER",
                    "GRANULARITY_BY_YEAR",
                ],
                "offset_from_today": 0,
            },
            "insights_options": {"show_insights": True, "settings": []},
            "comparisons": {"comparisons": [
                {"compare_config": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD", "comparison_period_override": []}, "index": "0"}
            ]},
        }

        r = req.post(f"{base}/api/-/pulse/definitions", headers=h_pulse, json=payload)
        if r.status_code not in (200, 201):
            progress(q, "warn", f"Metric {mc['label']} failed: {r.status_code} {r.text[:200]}", -1)
            continue

        resp = r.json()
        def_id = resp["definition"]["metadata"]["id"]
        metric_id = resp["definition"]["metrics"][0]["id"]
        cp["pulse_def_ids"].append(def_id)
        cp["pulse_metric_ids"].append(metric_id)

        patch_h = {
            "x-tableau-auth": auth_token,
            "Content-Type": "application/vnd.tableau.metricqueryservice.v1.UpdateDefinitionRequest+json",
            "Accept": "application/json",
        }
        req.patch(f"{base}/api/-/pulse/definitions/{def_id}", headers=patch_h,
                  json={"extension_options": {"use_dynamic_offset": True}})

    _save_cp(cp, slug, demo_dir)

    progress(q, "selfheal", "Converting to self-healing dates...", 60)
    try:
        from tdsx_builder import convert_to_self_healing
        convert_to_self_healing(df, "Date", ds_name, project.id, server, demo_dir)
    except Exception as e:
        progress(q, "warn", f"Self-healing conversion skipped: {e}", -1)

    progress(q, "group", "Creating group and subscriptions...", 70)
    try:
        group_name = f"{company} | {TODAY.strftime('%Y-%m-%d %H:%M')}"
        api_ver = "3.24"
        xml_body = f'<tsRequest><group name="{group_name}" /></tsRequest>'
        gh = {"x-tableau-auth": auth_token, "Content-Type": "application/xml", "Accept": "application/xml"}
        gr = req.post(f"{base}/api/{api_ver}/sites/{site_id}/groups", headers=gh, data=xml_body)

        import xml.etree.ElementTree as ET
        root = ET.fromstring(gr.text)
        grp = root.find(".//{http://tableau.com/api}group")
        if grp is None:
            grp = root.find(".//group")
        group_id = grp.get("id") if grp is not None else None
        cp["pulse_group_id"] = group_id

        if group_id:
            sub_h = {"x-tableau-auth": auth_token, "Accept": "application/json", "Content-Type": "application/json"}
            for mid in cp["pulse_metric_ids"]:
                req.post(f"{base}/api/-/pulse/subscriptions:batchCreate", headers=sub_h,
                         json={"metric_id": mid, "followers": [{"group_id": group_id}]})
    except Exception as e:
        progress(q, "warn", f"Group/subscription creation failed: {e}", -1)

    _save_cp(cp, slug, demo_dir)

    progress(q, "walkthrough", "Generating walkthrough document...", 85)
    wt_path = generate_walkthrough(slug, company, story_config, metric_config, "pulse", cp, demo_dir)

    server.auth.sign_out()
    cp["pulse_done"] = True
    cp["build_type"] = "pulse"
    cp["company"] = company
    cp["build_date"] = TODAY.isoformat()
    _save_cp(cp, slug, demo_dir)
    return cp


# ---------------------------------------------------------------------------
# Tableau Next build
# ---------------------------------------------------------------------------

def next_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp):
    import requests as req
    from connections import get_sf_token, get_dc_token, sf_headers, dc_headers

    csv_path = csv_build(build_id, df, slug, demo_dir, q)
    cp["csv_done"] = True
    cp["csv_path"] = csv_path
    _save_cp(cp, slug, demo_dir)

    sf = config["salesforce"]
    sf_token, sf_instance = get_sf_token(config)
    h = sf_headers(sf_token)

    # --- Phase 2: Schema + Stream ---
    if not cp.get("streams_done"):
        progress(q, "schema", "Registering schema with Data Cloud...", 10)
        connector_name = sf.get("ingestion_connector_name", "analytics_builder_demo")
        connector_id = sf.get("connector_sf_id", "")

        if not connector_id:
            r = req.get(f"{sf_instance}/services/data/v62.0/ssot/connections",
                        headers=h, params={"connectorType": "IngestApi", "limit": 100})
            for c in r.json().get("connections", []):
                if connector_name in c.get("name", ""):
                    connector_id = c["id"]
                    break
            if not connector_id:
                raise RuntimeError(f"Ingest connector '{connector_name}' not found")

        schema_name = slug.replace("-", "_")
        fields = [{"name": "Record ID", "dataType": "Text", "isPrimaryKey": True}]
        fields.append({"name": "Date", "dataType": "Date"})
        fields.append({"name": "Day_Offset", "dataType": "Number"})
        fields.append({"name": "Entity ID", "dataType": "Text"})
        for dim in story_config.get("dimensions", []):
            fields.append({"name": dim, "dataType": "Text"})
        for mc in metric_config:
            fields.append({"name": mc["label"], "dataType": "Number"})

        schema_fields = [{"name": f["name"], "label": f["name"],
                          "dataType": f["dataType"], "isPrimaryKey": f.get("isPrimaryKey", False)}
                         for f in fields]

        r_schema = req.get(f"{sf_instance}/services/data/v62.0/ssot/connections/{connector_id}/schema", headers=h)
        existing = r_schema.json() if r_schema.ok else {"schemas": []}
        schemas = [s for s in existing.get("schemas", []) if s.get("name") != schema_name]
        schemas.append({"name": schema_name, "label": schema_name.replace("_", " ").title(),
                        "schemaType": "IngestApi", "fields": schema_fields})
        req.put(f"{sf_instance}/services/data/v62.0/ssot/connections/{connector_id}/schema",
                headers=h, json={"schemas": schemas})

        progress(q, "stream", "Creating data stream...", 15)
        connector_uuid = sf.get("connector_uuid_name", "")
        if not connector_uuid:
            r_conns = req.get(f"{sf_instance}/services/data/v62.0/ssot/connections",
                              headers=h, params={"connectorType": "IngestApi", "limit": 100})
            for c in r_conns.json().get("connections", []):
                if connector_name in c.get("name", ""):
                    connector_uuid = c.get("name", "")
                    break

        stream_fields = [{"name": f["name"], "label": f["name"], "dataType": f["dataType"],
                          "isPrimaryKey": f.get("isPrimaryKey", False)} for f in fields]
        dlo_fields = [{"name": f["name"].replace(" ", "_").lower() + "__c", "label": f["name"],
                       "dataType": f["dataType"], "isPrimaryKey": f.get("isPrimaryKey", False)}
                      for f in fields]

        mappings = [{"sourceFieldName": f["name"], "targetFieldName": f["name"].replace(" ", "_").lower() + "__c"}
                    for f in fields]

        stream_payload = {
            "name": schema_name, "label": schema_name.replace("_", " ").title(),
            "datastreamType": "INGESTAPI",
            "connectorInfo": {"connectorType": "IngestApiConnector",
                              "connectorDetails": {"name": connector_uuid}},
            "schemaInfo": {"schemaName": schema_name},
            "dataLakeObjectInfo": {
                "name": schema_name + "__dll", "label": schema_name.replace("_", " ").title(),
                "category": "Other",
                "dataspaceInfo": [{"name": "default"}],
                "fields": dlo_fields,
            },
            "sourceFieldInputRepresentations": stream_fields,
            "dataLakeFieldInputRepresentations": dlo_fields,
            "mappings": mappings,
        }

        r_stream = req.post(f"{sf_instance}/services/data/v62.0/ssot/data-streams",
                            headers=h, json=stream_payload)
        if r_stream.status_code not in (200, 201):
            sr = r_stream.json() if r_stream.headers.get("content-type", "").startswith("application/json") else {}
            existing_stream = sr.get("errorCode") == "DUPLICATE_VALUE" or "already exists" in r_stream.text.lower()
            if existing_stream:
                r_list = req.get(f"{sf_instance}/services/data/v62.0/ssot/data-streams", headers=h)
                for s in r_list.json().get("data", []):
                    if schema_name in s.get("name", ""):
                        cp["stream_name"] = s["name"]
                        cp["dlo_name"] = s.get("dataLakeObjectInfo", {}).get("name", "")
                        break
            else:
                raise RuntimeError(f"Stream creation failed: {r_stream.status_code} {r_stream.text[:300]}")
        else:
            resp = r_stream.json()
            cp["stream_name"] = resp.get("name", schema_name)
            cp["dlo_name"] = resp.get("dataLakeObjectInfo", {}).get("name", schema_name + "__dll")

        progress(q, "stream", "Waiting for DLO to become active...", 20)
        for attempt in range(30):
            time.sleep(10)
            r_poll = req.get(f"{sf_instance}/services/data/v62.0/ssot/data-streams/{cp['stream_name']}", headers=h)
            if r_poll.ok:
                status = r_poll.json().get("dataLakeObjectInfo", {}).get("status", "")
                if status == "ACTIVE":
                    break
            progress(q, "stream", f"Waiting for DLO... ({(attempt+1)*10}s)", 20)
        else:
            progress(q, "warn", "DLO did not reach ACTIVE in 5 min — continuing anyway", -1)

        time.sleep(30)
        cp["streams_done"] = True
        _save_cp(cp, slug, demo_dir)

    # --- Phase 3: Bulk Ingest ---
    if not cp.get("ingest_done"):
        progress(q, "ingest", "Ingesting data via Bulk API...", 25)
        sf_token, sf_instance = get_sf_token(config)
        dc_token, dc_domain = get_dc_token(sf_token, sf_instance)
        dch = dc_headers(dc_token)
        connector_name = sf.get("ingestion_connector_name", "analytics_builder_demo")

        job_payload = {
            "object": cp.get("dlo_name", slug + "__dll").replace("__dll", ""),
            "sourceName": connector_name,
            "operation": "upsert",
        }
        r_job = req.post(f"https://{dc_domain}/api/v1/ingest/jobs", headers=dch, json=job_payload)
        r_job.raise_for_status()
        job_id = r_job.json()["id"]

        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        csv_bytes = csv_buf.getvalue().encode("utf-8")
        req.put(f"https://{dc_domain}/api/v1/ingest/jobs/{job_id}/batches",
                headers={"Authorization": f"Bearer {dc_token}", "Content-Type": "text/csv"},
                data=csv_bytes)
        req.patch(f"https://{dc_domain}/api/v1/ingest/jobs/{job_id}",
                  headers=dch, json={"state": "UploadComplete"})

        progress(q, "ingest", "Waiting for ingest to complete...", 30)
        for attempt in range(30):
            time.sleep(10)
            r_poll = req.get(f"https://{dc_domain}/api/v1/ingest/jobs/{job_id}", headers=dch)
            state = r_poll.json().get("state", "")
            if state == "JobComplete":
                break
            elif state == "Failed":
                raise RuntimeError(f"Ingest failed: {r_poll.json()}")
            progress(q, "ingest", f"Ingesting... {state} ({(attempt+1)*10}s)", 30)

        cp["ingest_done"] = True
        cp["ingest_job_id"] = job_id
        _save_cp(cp, slug, demo_dir)

    # --- Phase 4: Workspace + SDM + DO ---
    if not cp.get("sdm_done"):
        progress(q, "sdm", "Creating workspace and semantic model...", 35)
        sf_token, sf_instance = get_sf_token(config)
        h = sf_headers(sf_token)

        ws_label = f"{company} Analytics"
        r_ws = req.post(f"{sf_instance}/services/data/v65.0/tableau/workspaces",
                        headers=h, json={"label": ws_label})
        r_ws.raise_for_status()
        cp["ws_api"] = r_ws.json().get("name", "")
        cp["all_ws_apis"].append(cp["ws_api"])

        sdm_label = f"{company} Analytics"
        r_sdm = req.post(f"{sf_instance}/services/data/v65.0/ssot/semantic/models",
                         headers=h, json={"label": sdm_label, "dataspace": "default"})
        r_sdm.raise_for_status()
        cp["sdm_api"] = r_sdm.json().get("apiName", "")
        cp["all_sdm_apis"].append(cp["sdm_api"])

        progress(q, "sdm", "Adding data object to semantic model...", 40)
        dlo_name = cp.get("dlo_name", slug + "__dll")
        r_do = req.post(f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}/data-objects",
                        headers=h, json={
                            "dataLakeObjectName": dlo_name, "dataObjectName": dlo_name,
                            "dataObjectType": "dlo", "shouldIncludeAllFields": True,
                        })
        r_do.raise_for_status()
        cp["do_api"] = r_do.json().get("apiName", "")

        progress(q, "sdm", "Configuring measurements and dimensions...", 45)
        r_do_detail = req.get(
            f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}/data-objects/{cp['do_api']}",
            headers=h)
        do_data = r_do_detail.json()

        dim_field_map = {}
        for dim in do_data.get("semanticDimensions", []):
            base_name = dim.get("dataObjectFieldName", "").replace("__c", "")
            dim_field_map[base_name] = dim["apiName"]

        measurement_map = {}
        for meas in do_data.get("semanticMeasurements", []):
            base_name = meas.get("dataObjectFieldName", "").replace("__c", "")
            measurement_map[base_name] = meas["apiName"]

        cp["dim_field_map"] = dim_field_map
        cp["measurement_map"] = measurement_map

        for mc in metric_config:
            field_key = mc["field"]
            meas_api = measurement_map.get(field_key) or measurement_map.get(mc["label"].lower().replace(" ", "_"))
            if meas_api:
                agg = mc.get("agg", "Average")
                req.put(
                    f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}/data-objects/{cp['do_api']}/measurements/{meas_api}",
                    headers=h, json={
                        "apiName": meas_api,
                        "label": mc["label"],
                        "dataObjectFieldName": meas_api.rstrip("0123456789") + "__c" if "__c" not in meas_api else meas_api,
                        "aggregationType": agg,
                        "description": mc.get("description", ""),
                    })

        progress(q, "sdm", "Creating self-healing Display Date...", 50)
        build_date_str = TODAY.strftime("%Y-%m-%d")
        date_field_api = dim_field_map.get("date") or dim_field_map.get("Date", "")
        expression = f'DATEADD("day", DATEDIFF("day", #{build_date_str}#, [{cp["do_api"]}].[{date_field_api}]), TODAY())'
        r_dd = req.post(
            f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}/calculated-dimensions",
            headers=h, json={
                "apiName": "Display_Date", "label": "Display Date",
                "expression": expression, "dataType": "Date",
            })
        if r_dd.ok:
            cp["display_date_api"] = r_dd.json().get("apiName", "Display_Date")
        else:
            cp["display_date_api"] = ""
            progress(q, "warn", f"Display Date creation failed: {r_dd.text[:200]}", -1)

        cp["build_date"] = build_date_str
        cp["sdm_done"] = True
        _save_cp(cp, slug, demo_dir)

    # --- Phase 5: Metrics ---
    if not cp.get("metrics_done"):
        progress(q, "metrics", "Creating semantic metrics...", 55)
        sf_token, sf_instance = get_sf_token(config)
        h = sf_headers(sf_token)

        cp["metric_apis"] = []
        for i, mc in enumerate(metric_config):
            pct = 55 + int(10 * (i / len(metric_config)))
            progress(q, "metrics", f"Creating metric {i+1}/{len(metric_config)}: {mc['label']}...", pct)

            field_key = mc["field"]
            meas_api = cp.get("measurement_map", {}).get(field_key, "")
            if not meas_api:
                continue

            clc_api = f"{field_key}_clc"
            clc_expression = f'AVG([{cp["do_api"]}].[{meas_api}])'
            if mc.get("agg") == "Sum":
                clc_expression = f'SUM([{cp["do_api"]}].[{meas_api}])'

            r_clc = req.post(
                f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}/calculated-measurements",
                headers=h, json={
                    "apiName": clc_api, "label": mc["label"],
                    "aggregationType": "UserAgg", "dataType": "Number",
                    "decimalPlace": 4, "directionality": "Up" if mc.get("sentiment") == "up_is_good" else "Down",
                    "displayCategory": "Continuous", "expression": clc_expression,
                    "filters": [], "isOverrideBase": False, "isVisible": True,
                    "level": "AggregateFunction", "overriddenProperties": [],
                    "semanticDataType": "None",
                })
            if not r_clc.ok:
                progress(q, "warn", f"CLC {mc['label']} failed: {r_clc.text[:200]}", -1)
                continue

            mtc_api = f"{field_key}_mtc"
            time_ref = {"calculatedFieldApiName": cp.get("display_date_api", "Display_Date")} \
                if cp.get("display_date_api") else \
                {"tableFieldReference": {"fieldApiName": cp.get("dim_field_map", {}).get("date", ""), "tableApiName": cp["do_api"]}}

            dim_refs = [{"tableFieldReference": {"fieldApiName": dapi, "tableApiName": cp["do_api"]}}
                        for dname, dapi in cp.get("dim_field_map", {}).items()
                        if dname.lower() not in ("date", "record_id", "entity_id", "day_offset", "record id", "entity id")]

            r_mtc = req.post(
                f"{sf_instance}/services/data/v66.0/ssot/semantic/models/{cp['sdm_api']}/metrics?minorVersion=12",
                headers=h, json={
                    "apiName": mtc_api, "label": mc["label"],
                    "measurementReference": {"calculatedFieldApiName": clc_api},
                    "timeDimensionReference": time_ref,
                    "timeGrains": ["Month", "Quarter", "Year"],
                    "aggregationType": "UserAgg",
                    "additionalDimensions": dim_refs,
                    "insightsSettings": {
                        "insightsDimensionsReferences": dim_refs,
                        "singularNoun": mc.get("singular", mc["label"].lower()),
                        "pluralNoun": mc.get("plural", mc["label"].lower() + "s"),
                    },
                })
            if r_mtc.ok:
                cp["metric_apis"].append(r_mtc.json().get("apiName", mtc_api))
            else:
                progress(q, "warn", f"Metric {mc['label']} failed: {r_mtc.text[:200]}", -1)

        cp["metrics_done"] = True
        _save_cp(cp, slug, demo_dir)

    # --- Phase 6: Visualizations + Dashboard ---
    if not cp.get("viz_done"):
        progress(q, "viz", "Creating visualizations...", 70)
        sf_token, sf_instance = get_sf_token(config)
        h = sf_headers(sf_token)

        try:
            from viz_builder import build_viz_payload
            from viz_validator import is_valid

            cp["viz_apis"] = []
            templates = ["trend_over_time", "bar_by_category", "stacked_bar"]
            for i, mc in enumerate(metric_config[:3]):
                template = templates[i % len(templates)]
                meas_api = cp.get("measurement_map", {}).get(mc["field"], "")
                date_api = cp.get("dim_field_map", {}).get("date", "")
                first_dim = next((v for k, v in cp.get("dim_field_map", {}).items()
                                  if k.lower() not in ("date", "record_id", "entity_id", "day_offset", "record id", "entity id")), "")

                field_map = {"measure": meas_api, "date": date_api}
                if template != "trend_over_time":
                    field_map["dimension"] = first_dim

                viz_name = f"{slug}_{mc['field']}"
                payload = build_viz_payload(
                    template_name=template,
                    viz_name=viz_name,
                    viz_label=mc["label"],
                    sdm_api=cp["sdm_api"],
                    ws_api=cp["ws_api"],
                    do_api=cp["do_api"],
                    field_map=field_map,
                    dim_field_map=cp.get("dim_field_map", {}),
                    measurements=cp.get("measurement_map", {}),
                )

                r_viz = req.post(
                    f"{sf_instance}/services/data/v66.0/tableau/visualizations?minorVersion=12",
                    headers=h, json=payload)
                if r_viz.ok:
                    viz_api = r_viz.json().get("name", viz_name)
                    cp["viz_apis"].append(viz_api)
                    cp["all_viz_apis"].append(viz_api)
                    progress(q, "viz", f"Created viz {i+1}: {mc['label']}", 70 + int(5 * (i+1)))
                else:
                    progress(q, "warn", f"Viz {mc['label']} failed: {r_viz.text[:200]}", -1)

            _save_cp(cp, slug, demo_dir)
        except ImportError:
            progress(q, "warn", "viz_builder not available — skipping visualizations", -1)

        cp["viz_done"] = True
        _save_cp(cp, slug, demo_dir)

    if not cp.get("dash_done"):
        progress(q, "dash", "Assembling dashboard...", 80)
        try:
            from dashboard_builder import build_dashboard_payload
            sf_token, sf_instance = get_sf_token(config)
            h = sf_headers(sf_token)

            dash_payload = build_dashboard_payload(
                dash_name=f"{slug}_dashboard",
                dash_label=f"{company} Dashboard",
                ws_api=cp["ws_api"],
                sdm_api=cp["sdm_api"],
                viz_apis=cp.get("viz_apis", []),
                metric_apis=cp.get("metric_apis", []),
            )
            r_dash = req.post(
                f"{sf_instance}/services/data/v66.0/tableau/dashboards?minorVersion=12",
                headers=h, json=dash_payload)
            if r_dash.ok:
                cp["dash_api"] = r_dash.json().get("name", "")
                cp["all_dash_apis"].append(cp["dash_api"])
            else:
                progress(q, "warn", f"Dashboard failed: {r_dash.text[:200]}", -1)
        except (ImportError, Exception) as e:
            progress(q, "warn", f"Dashboard creation skipped: {e}", -1)

        cp["dash_done"] = True
        _save_cp(cp, slug, demo_dir)

    # --- Phase 7: Link assets to workspace ---
    progress(q, "assets", "Adding assets to workspace...", 90)
    try:
        sf_token, sf_instance = get_sf_token(config)
        h = sf_headers(sf_token)
        for viz_api in cp.get("viz_apis", []):
            req.post(f"{sf_instance}/services/data/v65.0/tableau/workspaces/{cp['ws_api']}/assets",
                     headers=h, json={"assetApiName": viz_api, "assetType": "visualization"})
        if cp.get("dash_api"):
            req.post(f"{sf_instance}/services/data/v65.0/tableau/workspaces/{cp['ws_api']}/assets",
                     headers=h, json={"assetApiName": cp["dash_api"], "assetType": "dashboard"})
    except Exception as e:
        progress(q, "warn", f"Asset linking failed: {e}", -1)

    progress(q, "walkthrough", "Generating walkthrough document...", 92)
    generate_walkthrough(slug, company, story_config, metric_config, "next", cp, demo_dir)

    cp["build_type"] = "next"
    cp["company"] = company
    cp["build_date"] = TODAY.isoformat()
    _save_cp(cp, slug, demo_dir)
    return cp


# ---------------------------------------------------------------------------
# CRMA build
# ---------------------------------------------------------------------------

def crma_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp):
    csv_path = csv_build(build_id, df, slug, demo_dir, q)
    cp["csv_done"] = True
    cp["csv_path"] = csv_path
    _save_cp(cp, slug, demo_dir)

    progress(q, "crma", "Uploading dataset to CRM Analytics...", 30)
    try:
        from connections import get_sf_token, sf_headers
        from crma_uploader import upload_dataset, build_metadata, fields_from_metric_config

        sf_token, sf_instance = get_sf_token(config)
        dims = story_config.get("dimensions", [])
        fields_spec = fields_from_metric_config(metric_config, dims)
        metadata = build_metadata(slug, slug.replace("_", " ").title(), fields_spec)

        csv_buf = io.BytesIO()
        df.to_csv(csv_buf, index=False)
        csv_bytes = csv_buf.getvalue()

        result = upload_dataset(sf_instance, sf_token, slug, slug.replace("_", " ").title(),
                                metadata, csv_bytes, f"{company} Analytics")
        cp["crma_dataset_id"] = result.get("id", "")
        progress(q, "crma", "Dataset uploaded", 60)
    except Exception as e:
        progress(q, "warn", f"CRMA upload failed: {e}", -1)

    progress(q, "walkthrough", "Generating walkthrough document...", 85)
    generate_walkthrough(slug, company, story_config, metric_config, "crma", cp, demo_dir)

    cp["build_type"] = "crma"
    cp["company"] = company
    cp["build_date"] = TODAY.isoformat()
    _save_cp(cp, slug, demo_dir)
    return cp


# ---------------------------------------------------------------------------
# Main build entry point
# ---------------------------------------------------------------------------

def run_build(build_id, build_config, progress_queue):
    """Main entry point — called from background thread."""
    q = progress_queue
    try:
        company = build_config["company"]
        slug = re.sub(r"[^a-z0-9]+", "_", company.lower()).strip("_")
        story_config = build_config["story_config"]
        metric_config = story_config["metric_config"]
        outputs = build_config.get("outputs", {})

        demo_dir = str(PROJECT_ROOT / "demos" / slug)
        os.makedirs(demo_dir, exist_ok=True)

        cp_path = os.path.join(demo_dir, f"{slug}_checkpoint.json")
        if os.path.exists(cp_path):
            with open(cp_path) as f:
                cp = json.load(f)
        else:
            cp = {"all_ws_apis": [], "all_sdm_apis": [], "all_viz_apis": [], "all_dash_apis": []}

        from connections import load_config
        config = load_config()

        progress(q, "init", "Generating data...", 0)
        df = generate_data(story_config, q)

        if outputs.get("csv"):
            csv_build(build_id, df, slug, demo_dir, q)

        if outputs.get("pulse"):
            progress(q, "pulse", "Starting Pulse build...", 15)
            pulse_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp)

        if outputs.get("next"):
            progress(q, "next", "Starting Tableau Next build...", 10)
            next_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp)

        if outputs.get("crma"):
            progress(q, "crma", "Starting CRM Analytics build...", 10)
            crma_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp)

        progress(q, "done", f"Build complete! Demo saved to demos/{slug}/", 100)

    except Exception as e:
        progress(q, "error", f"Build failed: {str(e)[:500]}", -1)


# ---------------------------------------------------------------------------
# Checkpoint helper
# ---------------------------------------------------------------------------

def _save_cp(cp, slug, demo_dir):
    path = os.path.join(demo_dir, f"{slug}_checkpoint.json")
    with open(path, "w") as f:
        json.dump(cp, f, indent=2, default=str)
