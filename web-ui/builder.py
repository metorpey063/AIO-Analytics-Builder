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

CRITICAL RULES:
- ALWAYS return valid JSON. Never ask clarifying questions. Never explain or discuss.
- If the user references a prior demo or existing work, infer reasonable defaults from the company name, industry, and use case — do NOT ask for more information.
- If details are vague, make your best judgment and generate a complete configuration.
- Your entire response must be a single JSON object. No text before or after it.

If ANY of the user fields are empty or vague (industry, use case, audience), infer the best fit from the company name and fill them in. Include a "suggestions" object with your inferred values so the UI can auto-populate empty fields.

Return ONLY valid JSON with this exact structure:
{
  "suggestions": {
    "industry": "inferred industry if user left it blank",
    "use_case": "inferred use case if user left it blank",
    "audience": "inferred audience if user left it blank"
  },
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


def _find_existing_demo(company):
    """Look for a previously built demo matching this company name."""
    demos_dir = PROJECT_ROOT / "demos"
    if not demos_dir.exists():
        return None

    company_lower = company.lower().replace(" ", "_").replace("'", "")
    for d in demos_dir.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        if company_lower in d.name.lower() or d.name.lower() in company_lower:
            csv_files = sorted(d.glob("*.csv"))
            if csv_files:
                try:
                    df = pd.read_csv(str(csv_files[-1]), nrows=3)
                    cp_file = d / f"{d.name}_checkpoint.json"
                    cp = {}
                    if cp_file.exists():
                        cp = json.loads(cp_file.read_text())
                    return {
                        "slug": d.name,
                        "columns": list(df.columns),
                        "sample_row": df.iloc[0].to_dict() if len(df) > 0 else {},
                        "build_type": cp.get("build_type", "unknown"),
                        "company": cp.get("company", d.name),
                    }
                except Exception:
                    pass
    return None


def generate_story(company, industry, use_case, audience, notes="", research_depth="quick"):
    """Call Claude API to generate story + metrics. Returns dict."""
    from app import _get_chat_config, CHAT_MODEL

    cfg = _get_chat_config()
    if not cfg:
        raise RuntimeError("No API key configured for AI generation")

    prior_context = ""
    existing = _find_existing_demo(company)
    if existing:
        cols = existing["columns"]
        metric_cols = [c for c in cols if c not in ("Record ID", "Date", "Day_Offset", "Entity ID", "Unit ID")]
        prior_context = f"""
IMPORTANT — A demo was previously built for this company. Here is the prior configuration:
- Demo slug: {existing['slug']}
- Previous build type: {existing['build_type']}
- Columns in the dataset: {', '.join(cols)}
- Metric/dimension columns: {', '.join(metric_cols)}
- Sample row: {json.dumps(existing['sample_row'], default=str)}

Reuse the same metrics, dimensions, and field names from the prior build. Match the column names exactly so the new build is consistent with the existing data. Adapt for the requested output platform if different."""

    depth_context = ""
    if research_depth == "detailed":
        depth_context = """
RESEARCH DEPTH: DETAILED
Go deep on this company's actual business model, industry dynamics, and real KPIs. Use real department names, real product lines, real geographic footprint where possible. The story should reference plausible industry benchmarks and use terminology the audience would recognize from their day-to-day work. Generate 5 metrics (not 3). Include dimension values that match the company's real operations (e.g. actual regions they operate in, actual product categories they sell)."""
    else:
        depth_context = """
RESEARCH DEPTH: QUICK
Generate a solid demo configuration using reasonable industry defaults. 3-4 metrics is fine. Use generic but realistic dimension values."""

    user_msg = f"""Company: {company}
Industry: {industry}
Use case / topic: {use_case}
Audience: {audience}
Additional context: {notes or 'None'}
{depth_context}
{prior_context}"""

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

    # Strip markdown code fences if present
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()

    # Try parsing the full text first, then fall back to extracting JSON block
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        raise RuntimeError(f"AI did not return valid JSON. Response: {text[:300]}")

    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"AI returned malformed JSON: {e}. Response: {text[:300]}")


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
    if shape == "step":
        return 1.0 if progress_val >= 0.3 else 0.0
    return progress_val


def generate_data(story_config, q=None, advanced=None):
    """Generate synthetic data from story config. Returns DataFrame."""
    metric_config = story_config["metric_config"]
    dimensions = story_config.get("dimensions", ["Region", "Category", "Segment"])
    advanced = advanced or {}

    history_months = advanced.get("history_months", 24)
    signal_magnitude = advanced.get("signal_magnitude", 0.40)
    supporting_magnitude = advanced.get("supporting_magnitude", 0.12)
    signal_onset = advanced.get("signal_onset", -3)
    signal_shape = advanced.get("signal_shape", "accelerating")

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

    grain = advanced.get("grain", "monthly")
    freq_map = {"daily": "D", "weekly": "W-MON", "monthly": "MS"}
    freq = freq_map.get(grain, "MS")

    start_date = TODAY - relativedelta(months=history_months)
    dates = pd.date_range(start_date, TODAY, freq=freq).date.tolist()

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
                ramp = signal_ramp(dt, onset=signal_onset, shape=signal_shape, duration=abs(signal_onset))
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
    """Generate a .docx walkthrough following the standard format. Returns file path."""
    from docx import Document
    doc = Document()
    dims = story_config.get("dimensions", [])

    # --- Section 1: Demo Scenario ---
    doc.add_heading("Demo Scenario", level=1)
    doc.add_heading(f"About {company}", level=2)
    doc.add_paragraph(story_config.get("story_summary", ""))
    doc.add_heading("Audience & Story", level=2)
    audience = story_config.get("audience", "")
    if audience:
        p = doc.add_paragraph()
        p.add_run("Audience: ").bold = True
        p.add_run(audience)
    doc.add_paragraph(story_config.get("signal_description", ""))

    # --- Section 2: Metrics Reference ---
    doc.add_heading("Metrics Reference", level=1)
    doc.add_paragraph(
        "Each metric below includes its definition and why it matters to the client. "
        "Primary metrics show the main signal; supporting metrics explain the cause or consequence."
    )
    for mc in metric_config:
        doc.add_heading(mc["label"], level=2)
        p = doc.add_paragraph()
        p.add_run("What it measures: ").bold = True
        p.add_run(mc.get("description", ""))
        p2 = doc.add_paragraph()
        p2.add_run("Why it matters: ").bold = True
        p2.add_run(mc.get("why_it_matters", ""))

    # --- Section 3: Click Path / Concierge Prompts ---
    if build_type == "pulse":
        doc.add_heading("Demo Click Path", level=1)
        doc.add_paragraph(
            "Each step below shows the action to take in Pulse followed by what the audience will see."
        )
        primary = [mc for mc in metric_config if mc.get("is_primary")]
        lead_metric = primary[0]["label"] if primary else metric_config[0]["label"]

        steps = [
            ("Opening — Surface Level", f"Open {company} metrics in Pulse", f"The {lead_metric} sparkline shows a recent decline, with a red comparison arrow vs. prior period."),
        ]
        if dims:
            steps.append((f"Drill 1 — {dims[0]}", f"Click into {lead_metric} and filter by {dims[0]}", f"One {dims[0].lower()} segment is declining significantly faster than others."))
        if len(dims) >= 2:
            steps.append((f"Drill 2 — {dims[1]}", f"Within the worst {dims[0].lower()}, break down by {dims[1]}", f"The decline is concentrated in a specific {dims[1].lower()} segment."))
        counter = [mc for mc in metric_config if not mc.get("is_primary") and mc.get("sentiment") != "up_is_good"]
        if counter:
            steps.append(("Counter-Trend", f"Switch to {counter[0]['label']}", f"This metric is actually improving — it masks the severity of the decline in the primary metric."))
        steps.append(("Action", "Summarize findings", "The audience now has a clear signal, knows where it's concentrated, and can identify at-risk entities."))

        for title, action, sees in steps:
            doc.add_heading(title, level=2)
            p = doc.add_paragraph()
            p.add_run("Action: ").bold = True
            p.add_run(action)
            p2 = doc.add_paragraph()
            p2.add_run("Audience sees: ").bold = True
            p2.add_run(sees)

    elif build_type == "next":
        doc.add_heading("Concierge Prompts", level=1)
        doc.add_paragraph(
            "Each step below shows the question to ask Concierge followed by the expected response."
        )
        primary = [mc for mc in metric_config if mc.get("is_primary")]
        lead_metric = primary[0]["label"] if primary else metric_config[0]["label"]

        prompts = [
            ("Opening", f"How is {lead_metric.lower()} trending?", f"Concierge shows the overall trend with a decline emerging in recent months."),
        ]
        if dims:
            prompts.append((f"Drill — {dims[0]}", f"Which {dims[0].lower()} has the worst {lead_metric.lower()}?", f"Concierge identifies the worst-performing {dims[0].lower()} segment with specific numbers."))
        if len(dims) >= 2:
            prompts.append((f"Drill — {dims[1]}", f"Within that {dims[0].lower()}, break it down by {dims[1].lower()}", f"Concierge drills deeper, revealing the compounding effect in a specific {dims[1].lower()} segment."))
        supporting = [mc for mc in metric_config if not mc.get("is_primary")]
        if supporting:
            prompts.append(("Root Cause", f"What about {supporting[0]['label'].lower()}?", f"Concierge shows the supporting metric lagging the primary, confirming the root cause."))
        prompts.append(("Action", "Which entities are most at risk?", "Concierge lists specific entities with the steepest declines, ready for outreach."))

        for title, ask, expected in prompts:
            doc.add_heading(title, level=2)
            p = doc.add_paragraph()
            p.add_run("Ask: ").bold = True
            p.add_run(f'"{ask}"')
            p2 = doc.add_paragraph()
            p2.add_run("Expected response: ").bold = True
            p2.add_run(expected)

    elif build_type == "crma":
        doc.add_heading("Demo Click Path", level=1)
        doc.add_paragraph("Navigate the CRM Analytics dashboard to explore the story.")

    # --- Section 4: Goal Lines (Pulse only, if any metric has goals) ---
    if build_type == "pulse":
        goals = [mc for mc in metric_config if mc.get("goal")]
        if goals:
            doc.add_heading("Setting Up Goal Lines", level=1)
            doc.add_paragraph(
                "The datasource includes target columns for easy goal setup in the Pulse UI:"
            )
            for mc in goals:
                g = mc["goal"]
                doc.add_paragraph(
                    f"{mc['label']}: select \"{g.get('field', '')}\" → target {g.get('value', '')} → direction: {g.get('direction', 'above')}",
                    style="List Bullet"
                )
            doc.add_paragraph(
                "To set up: Open metric → Edit → Goals → Select field from data → Choose the target column → Set direction."
            )

    # --- Section 5: Business Preferences (Next only) ---
    if build_type == "next":
        doc.add_heading("Business Preferences (SDM)", level=1)
        doc.add_paragraph(
            "Copy the text below and paste it into: Data 360 → Semantic Model → [SDM name] "
            "→ AI Optimization → Manage Business Preferences"
        )
        dims_str = ", ".join(dims) if dims else "Region, Category"
        metric_defs = "\n".join([f"- {mc['label']}: {mc.get('description', '')}" for mc in metric_config])
        bp_text = (
            f"# COMPANY CONTEXT\n"
            f"This data represents {company}'s operational analytics.\n\n"
            f"# METRIC DEFINITIONS\n{metric_defs}\n\n"
            f"# DIMENSION GUIDANCE\n"
            f"Available dimensions: {dims_str}. Use these to segment and filter data.\n\n"
            f"# THRESHOLDS AND TARGETS\n"
            f"A decline of more than 10 percentage points is significant. Track metrics against prior period.\n\n"
            f"# QUESTION INTENT\n"
            f"\"worst\" = steepest decline over the analysis period\n"
            f"\"most affected\" = steepest decline segmented by the most recently mentioned dimension\n"
            f"\"at risk\" = entities with the steepest recent decline\n\n"
            f"# ANSWER STYLE\n"
            f"Lead with the answer, then supporting data. Do not open with questions back to the user.\n\n"
            f"# TIME CONTEXT\n"
            f"Default comparison: current period vs. prior period (same duration)."
        )
        doc.add_paragraph(bp_text)
        checkpoint["business_preferences"] = bp_text

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

def pulse_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp, build_config=None):
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

    # --- Optional: Pulse Dashboard with embedded metric tiles ---
    outputs = build_config.get("outputs", {}) if build_config else {}
    if outputs.get("pulse_dashboard"):
        progress(q, "twb", "Creating Pulse Dashboard workbook...", 78)
        try:
            from twb_builder import build_pulse_workbook
            from connections import get_datasource_content_url
            ds_content_url = get_datasource_content_url(server, cp["pulse_datasource_id"])
            twb_path = build_pulse_workbook(
                df=df,
                metric_config=metric_config,
                ds_content_url=ds_content_url,
                company=company,
                slug=slug,
                demo_dir=demo_dir,
                server=server,
                project_id=cp["pulse_project_id"],
                datasource_id=cp["pulse_datasource_id"],
                def_ids=cp.get("pulse_def_ids", []),
                metric_ids=cp.get("pulse_metric_ids", []),
            )
            cp["pulse_twb_path"] = twb_path
            progress(q, "twb", "Pulse Dashboard published", -1)
        except Exception as e:
            progress(q, "warn", f"Pulse Dashboard skipped: {e}", -1)
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

def next_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp, build_config=None):
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
        connector_uuid = sf.get("connector_uuid_name", "")

        # Always auto-discover the connector on the CURRENT org (config may have stale IDs from a different org)
        r = req.get(f"{sf_instance}/services/data/v62.0/ssot/connections",
                    headers=h, params={"connectorType": "IngestApi", "limit": 100})
        conns = r.json().get("connections", []) if r.ok else []
        connector_id = ""
        connector_uuid = ""
        for c in conns:
            cname = c.get("name", "")
            if connector_name and connector_name in cname:
                connector_id = c.get("id", "")
                connector_uuid = cname
                break
        if not connector_id and conns:
            connector_id = conns[0].get("id", "")
            connector_uuid = conns[0].get("name", "")
            progress(q, "info", f"Using connector: {connector_uuid}", -1)
        if not connector_id:
            raise RuntimeError(
                f"No Ingest API connector found on this org ({sf_instance}). "
                "Create one in Salesforce Setup → Data Cloud → External Integrations → Ingestion API → New."
            )

        schema_name = slug.replace("-", "_")
        fields = [{"name": "Record ID", "dataType": "Text", "isPrimaryKey": True}]
        fields.append({"name": "Date", "dataType": "Date"})
        fields.append({"name": "Day_Offset", "dataType": "Number"})
        fields.append({"name": "Entity ID", "dataType": "Text"})
        for dim in story_config.get("dimensions", []):
            fields.append({"name": dim, "dataType": "Text"})
        for mc in metric_config:
            fields.append({"name": mc["label"], "dataType": "Number"})

        # Schema fields: no isPrimaryKey, no spaces, all lowercase names
        schema_fields = [{"name": f["name"].replace(" ", "_").lower(),
                          "label": f["name"].replace(" ", "_").lower(),
                          "dataType": f["dataType"]}
                         for f in fields]

        # Check if schema already exists — if so, skip PUT entirely
        r_schema = req.get(f"{sf_instance}/services/data/v62.0/ssot/connections/{connector_id}/schema", headers=h)
        existing = r_schema.json() if r_schema.ok else {"schemas": []}
        existing_schemas = existing.get("schemas", []) if isinstance(existing, dict) else []
        schema_exists = any(s.get("name") == schema_name for s in existing_schemas)

        if not schema_exists:
            # Strip platform-injected fields from existing schemas before re-submitting
            STRIP_KEYS = {"availabilityStatus"}
            clean_existing = []
            for s in existing_schemas:
                clean = {k: v for k, v in s.items() if k not in STRIP_KEYS}
                if "fields" in clean:
                    clean["fields"] = [{fk: fv for fk, fv in f.items() if fk not in STRIP_KEYS}
                                       for f in clean["fields"]]
                clean_existing.append(clean)

            new_schema = {"name": schema_name, "label": schema_name,
                          "schemaType": "IngestApi", "fields": schema_fields}
            r_put = req.put(f"{sf_instance}/services/data/v62.0/ssot/connections/{connector_id}/schema",
                            headers=h, json={"schemas": clean_existing + [new_schema]})
            if not r_put.ok:
                progress(q, "warn", f"Schema PUT failed: {r_put.text[:200]} — retrying with new schema only", -1)
                r_put2 = req.put(f"{sf_instance}/services/data/v62.0/ssot/connections/{connector_id}/schema",
                                 headers=h, json={"schemas": [new_schema]})
                if not r_put2.ok:
                    progress(q, "warn", f"Schema registration failed: {r_put2.text[:200]}", -1)
        else:
            progress(q, "info", f"Schema '{schema_name}' already exists — reusing", -1)

        progress(q, "stream", "Creating data stream...", 15)
        time.sleep(5)  # Schema propagation delay — stream creation fails without this
        # connector_uuid already resolved above

        # Stream creation: only include the PK field in DLO — other fields auto-discovered from schema
        pk_field = fields[0]  # Record ID is always first
        stream_payload = {
            "name": schema_name, "label": schema_name,
            "datasource": connector_uuid[:10],
            "datastreamType": "INGESTAPI",
            "connectorInfo": {"connectorType": "IngestApi",
                              "connectorDetails": {"name": connector_uuid,
                                                   "events": [schema_name]}},
            "dataLakeObjectInfo": {
                "label": schema_name,
                "category": "Other",
                "dataspaceInfo": [{"name": "default"}],
                "dataLakeFieldInputRepresentations": [
                    {"name": pk_field["name"].replace(" ", "_").lower(),
                     "label": pk_field["name"].replace(" ", "_").lower(),
                     "dataType": "Text", "isPrimaryKey": True},
                ],
                "eventDateTimeFieldName": "",
                "recordModifiedFieldName": "",
            },
            "mappings": [],
        }

        r_stream = req.post(f"{sf_instance}/services/data/v62.0/ssot/data-streams",
                            headers=h, json=stream_payload)
        if r_stream.status_code not in (200, 201):
            # Try to find an existing stream — creation failures often mean it already exists
            progress(q, "stream", f"Stream creation returned {r_stream.status_code} — checking for existing stream...", -1)
            r_list = req.get(f"{sf_instance}/services/data/v62.0/ssot/data-streams", headers=h)
            streams = r_list.json()
            stream_list = streams.get("dataStreams", []) if isinstance(streams, dict) else streams
            found = False
            for s in stream_list:
                if isinstance(s, dict) and schema_name in s.get("name", ""):
                    cp["stream_name"] = s["name"]
                    dlo_info = s.get("dataLakeObjectInfo", {})
                    if isinstance(dlo_info, dict):
                        cp["dlo_name"] = dlo_info.get("name", "")
                    progress(q, "stream", f"Found existing stream: {cp['stream_name']}", -1)
                    found = True
                    break
            if not found:
                raise RuntimeError(f"Stream creation failed and no existing stream found: {r_stream.status_code} {r_stream.text[:300]}")
        else:
            resp = r_stream.json()
            if isinstance(resp, list):
                resp = resp[0] if resp else {}
            cp["stream_name"] = resp.get("name", schema_name)
            dlo_info = resp.get("dataLakeObjectInfo", {})
            if isinstance(dlo_info, list):
                dlo_info = dlo_info[0] if dlo_info else {}
            cp["dlo_name"] = dlo_info.get("name", schema_name + "__dll")

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
        schema_name = slug  # same as what was registered in Phase 2

        job_payload = {
            "object": schema_name,
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

    # --- Phase 3b: CRM Actionability (upsert Account records) ---
    outputs = build_config.get("outputs", {}) if build_config else {}
    if outputs.get("crm_actionable") and not cp.get("crm_done"):
        progress(q, "crm", "Creating CRM Account records...", 36)
        try:
            from crm_upserter import ensure_external_id_field, upsert_crm_records
            sf_token, sf_instance = get_sf_token(config)

            ensure_external_id_field(sf_token, sf_instance, "Account", "Demo_External_ID__c")

            entities = df[["Entity ID"]].drop_duplicates()
            dims = story_config.get("dimensions", [])
            records = []
            for _, row_data in entities.iterrows():
                eid = row_data["Entity ID"]
                sample = df[df["Entity ID"] == eid].iloc[0]
                rec = {
                    "Name": f"{company} — {eid}",
                    "Demo_External_ID__c": eid,
                }
                for d in dims:
                    if d in sample:
                        if d.lower() in ("region", "location", "geography"):
                            rec["BillingState"] = str(sample[d])
                        elif d.lower() in ("vertical", "industry", "sector"):
                            rec["Industry"] = str(sample[d])
                records.append(rec)

            result = upsert_crm_records(sf_token, sf_instance, "Account", "Demo_External_ID__c", records)
            cp["crm_account_ids"] = result
            progress(q, "crm", f"Created {len(records)} Account records", -1)
        except Exception as e:
            progress(q, "warn", f"CRM upsert failed: {e}", -1)

        cp["crm_done"] = True
        _save_cp(cp, slug, demo_dir)

    # --- Phase 4: Workspace + SDM + DO ---
    if not cp.get("sdm_done"):
        progress(q, "sdm", "Creating workspace and semantic model...", 35)
        sf_token, sf_instance = get_sf_token(config)
        h = sf_headers(sf_token)

        build_config = build_config or {}
        demo_label = build_config.get("demo_name", "") or company
        ws_label = f"{demo_label} Analytics"
        r_ws = req.post(f"{sf_instance}/services/data/v65.0/tableau/workspaces",
                        headers=h, json={"label": ws_label})
        r_ws.raise_for_status()
        cp["ws_api"] = r_ws.json().get("name", "")
        cp["all_ws_apis"].append(cp["ws_api"])

        sdm_label = f"{demo_label} Analytics"
        r_sdm = req.post(f"{sf_instance}/services/data/v65.0/ssot/semantic/models",
                         headers=h, json={"label": sdm_label, "dataspace": "default"})
        r_sdm.raise_for_status()
        cp["sdm_api"] = r_sdm.json().get("apiName", "")
        cp["all_sdm_apis"].append(cp["sdm_api"])

        progress(q, "sdm", "Adding data object to semantic model...", 40)
        dlo_name = cp.get("dlo_name", slug + "__dll")
        demo_label = build_config.get("demo_name", "") or company
        r_do = req.post(f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}/data-objects",
                        headers=h, json={
                            "dataLakeObjectName": dlo_name, "dataObjectName": dlo_name,
                            "label": f"{demo_label} Fact",
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

        # Try MCP path first for higher quality dashboards
        mcp_available = False
        try:
            from mcp_client import MCPClient
            mcp = MCPClient(config)
            if mcp.available:
                mcp.authenticate()
                mcp.initialize()
                mcp_available = True
                progress(q, "viz", "MCP connected — using premium dashboard builder", -1)
        except Exception as e:
            progress(q, "info", f"MCP not available ({e}) — using REST fallback", -1)

        if mcp_available:
            # --- MCP path: slim viz specs + Z layout dashboard ---
            try:
                cp["viz_apis"] = []
                SYSTEM_DIMS = {"date", "record_id", "entity_id", "day_offset", "kq_record_id",
                               "datasourceobject", "datasource", "cdp_sys_sourceversion",
                               "data_source_object", "data_source"}
                user_dim_names = [k for k in cp.get("dim_field_map", {}).keys()
                                  if k.lower().replace(" ", "_") not in SYSTEM_DIMS]

                for i, mc in enumerate(metric_config[:4]):
                    progress(q, "viz", f"Creating viz {i+1} via MCP: {mc['label']}...", 70 + int(5 * i))
                    dim_name = user_dim_names[i % len(user_dim_names)] if user_dim_names else "region"
                    try:
                        result = mcp.create_visualization(
                            name=f"{slug}_{mc['field']}",
                            label=mc["label"],
                            semanticModelIdOrName=cp["sdm_api"],
                            workspaceIdOrApiName=cp["ws_api"],
                            description=mc.get("description", ""),
                        )
                        viz_api = result.get("name", "") if isinstance(result, dict) else ""
                        if viz_api:
                            cp["viz_apis"].append(viz_api)
                            cp["all_viz_apis"].append(viz_api)
                            progress(q, "viz", f"Created viz: {mc['label']}", -1)
                    except Exception as e:
                        progress(q, "warn", f"MCP viz {mc['label']} failed: {e}", -1)

                _save_cp(cp, slug, demo_dir)

                # Create dashboard with Z layout
                progress(q, "dash", "Creating Z layout dashboard via MCP...", 80)
                try:
                    demo_label = build_config.get("demo_name", "") or company
                    result = mcp.create_dashboard(
                        name=f"{slug}_dashboard",
                        label=f"{demo_label} Dashboard",
                        workspaceIdOrApiName=cp["ws_api"],
                    )
                    dash_api = result.get("name", "") if isinstance(result, dict) else ""
                    if dash_api:
                        cp["dash_api"] = dash_api
                        cp["all_dash_apis"].append(dash_api)

                        # Add viz widgets and metric widgets via edit_dashboard
                        from dashboard_builder import build_z_layout_ops
                        metric_labels = [mc["label"] for mc in metric_config[:3]]
                        viz_labels = [mc["label"] for mc in metric_config[:len(cp["viz_apis"])]]
                        ops = build_z_layout_ops(
                            page_name="Overview", title=f"{demo_label} Analytics",
                            subtitle=story_config.get("story_summary", "")[:100],
                            sdm_api=cp["sdm_api"], sdm_id="",
                            metric_apis=cp.get("metric_apis", [])[:3],
                            metric_labels=metric_labels,
                            viz_apis=cp["viz_apis"],
                            viz_labels=viz_labels,
                            viz_ids=[""] * len(cp["viz_apis"]),
                            filter_fields=user_dim_names[:3],
                        )
                        for op in ops:
                            try:
                                mcp.edit_dashboard(dashboardIdOrName=dash_api, **op)
                            except Exception:
                                pass

                        progress(q, "dash", f"Dashboard created: {dash_api}", -1)
                except Exception as e:
                    progress(q, "warn", f"MCP dashboard failed: {e}", -1)

                cp["viz_done"] = True
                cp["dash_done"] = True
                _save_cp(cp, slug, demo_dir)

            except Exception as e:
                progress(q, "warn", f"MCP viz/dash failed ({e}) — falling back to REST", -1)
                mcp_available = False

        if not mcp_available and not cp.get("viz_done"):
            # --- REST fallback for viz creation ---
            try:
                from viz_builder import build_viz_payload
                from viz_validator import is_valid

                cp["viz_apis"] = []

                SYSTEM_DIMS = {"date", "record_id", "entity_id", "day_offset", "kq_record_id",
                           "datasourceobject", "datasource", "cdp_sys_sourceversion",
                           "data_source_object", "data_source"}
                user_dim_names = [k for k in cp.get("dim_field_map", {}).keys()
                                  if k.lower().replace(" ", "_") not in SYSTEM_DIMS]

                brand = build_config.get("brand", {}) if build_config else {}
                style_overrides = {}
                if brand.get("primary"):
                    style_overrides["primary"] = brand["primary"]
                if brand.get("secondary"):
                    style_overrides["secondary"] = brand["secondary"]

                try:
                    from viz_templates import recommend_dashboard_vizzes
                    viz_plan = recommend_dashboard_vizzes(metric_config, user_dim_names)
                except ImportError:
                    viz_plan = [{"template": "trend_over_time", "metric_field": mc["field"],
                                 "label": f"{mc['label']} Over Time"} for mc in metric_config[:3]]

                for i, v in enumerate(viz_plan):
                    fm = {"measure": v["metric_field"], "date": "date"}
                    template = v.get("template", "trend_over_time")

                    if template == "bar_by_category" and user_dim_names:
                        fm = {"category": user_dim_names[i % len(user_dim_names)],
                              "amount": v["metric_field"]}
                    elif template == "stacked_bar" and len(user_dim_names) >= 2:
                        fm = {"category": user_dim_names[0],
                              "stack_dim": user_dim_names[1],
                              "amount": v["metric_field"]}
                    elif template == "donut" and user_dim_names:
                        fm = {"category": user_dim_names[i % len(user_dim_names)],
                              "amount": v["metric_field"]}

                    viz_name = f"{slug}_{v['metric_field']}"
                    payload = build_viz_payload(
                        template_name=template,
                        viz_name=viz_name,
                        viz_label=v.get("label", metric_config[0]["label"]),
                        sdm_api=cp["sdm_api"],
                        ws_api=cp["ws_api"],
                        do_api=cp["do_api"],
                        field_map=fm,
                        dim_field_map=cp.get("dim_field_map", {}),
                        measurements=cp.get("measurement_map", {}),
                        style_overrides=style_overrides if style_overrides else None,
                    )

                    ok, results = is_valid(payload)
                    if not ok:
                        progress(q, "warn", f"Viz validation failed for {v.get('label','')}: {results}", -1)

                    r_viz = req.post(
                        f"{sf_instance}/services/data/v66.0/tableau/visualizations?minorVersion=12",
                        headers=h, json=payload)
                    if r_viz.ok:
                        viz_api = r_viz.json().get("name", viz_name)
                        cp["viz_apis"].append(viz_api)
                        cp["all_viz_apis"].append(viz_api)
                        progress(q, "viz", f"Created viz {i+1}/{len(viz_plan)}: {v.get('label','')}", 70 + int(8 * ((i+1)/len(viz_plan))))
                    else:
                        progress(q, "warn", f"Viz {v.get('label','')} failed: {r_viz.text[:200]}", -1)

                _save_cp(cp, slug, demo_dir)
            except ImportError as e:
                progress(q, "warn", f"viz_builder not available ({e}) — skipping visualizations", -1)

            cp["viz_done"] = True
            _save_cp(cp, slug, demo_dir)

    if not cp.get("dash_done"):
        progress(q, "dash", "Assembling dashboard...", 80)
        try:
            from dashboard_builder import build_dashboard_payload
            sf_token, sf_instance = get_sf_token(config)
            h = sf_headers(sf_token)

            brand = build_config.get("brand", {}) if build_config else {}
            dash_style = {}
            if brand.get("primary"):
                c = brand["primary"].lstrip("#")
                r_c, g_c, b_c = int(c[:2], 16), int(c[2:4], 16), int(c[4:6], 16)
                tint = "#{:02x}{:02x}{:02x}".format(
                    round(r_c + (255 - r_c) * 0.90),
                    round(g_c + (255 - g_c) * 0.90),
                    round(b_c + (255 - b_c) * 0.90))
                dash_style["backgroundColor"] = tint
                dash_style["gutterColor"] = tint

            dash_payload = build_dashboard_payload(
                dash_name=f"{slug}_dashboard",
                dash_label=f"{company} Dashboard",
                ws_api=cp["ws_api"],
                sdm_api=cp["sdm_api"],
                viz_apis=cp.get("viz_apis", []),
                metric_apis=cp.get("metric_apis", []),
                style_overrides=dash_style if dash_style else None,
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
        demo_name = build_config.get("demo_name", "") or company
        slug = re.sub(r"[^a-z0-9]+", "_", demo_name.lower()).strip("_")
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

        from connections import load_config, load_full_config, set_active_profile
        profile_key = build_config.get("profile_key")
        if profile_key:
            full = load_full_config()
            if profile_key in full.get("profiles", {}):
                set_active_profile(full, profile_key)
        config = load_config(profile_key)

        advanced = build_config.get("advanced", {})

        progress(q, "init", "Generating data...", 0)
        df = generate_data(story_config, q, advanced=advanced)

        if outputs.get("csv"):
            csv_build(build_id, df, slug, demo_dir, q)

        if outputs.get("pulse"):
            progress(q, "pulse", "Starting Pulse build...", 15)
            pulse_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp, build_config)

        if outputs.get("next"):
            progress(q, "next", "Starting Tableau Next build...", 10)
            next_build(build_id, df, slug, company, config, metric_config, story_config, demo_dir, q, cp, build_config)

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
