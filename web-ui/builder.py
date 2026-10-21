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

_build_log_file = None

def progress(q, stage, message, pct=-1):
    if q:
        q.put({"stage": stage, "message": message, "pct": pct})
    if _build_log_file:
        try:
            with open(_build_log_file, "a") as f:
                f.write(f"[{stage}] {message}\n")
        except Exception:
            pass


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
- Field names use snake_case with no spaces. Keep field names SHORT — max 35 characters.
- Metric LABELS should be short and business-focused (max 5 words). Example: "Client Retention Rate" not "Salesforce CRM Client Retention Tracking Rate".
- Sentiment: "up_is_good" or "down_is_good".
- CRITICAL: Metrics must be about the CUSTOMER'S BUSINESS, not about Salesforce/Tableau platform features. If uploaded documents mention Salesforce reports, dashboards, or platform features, IGNORE those — focus on the customer's industry KPIs (revenue, retention, efficiency, satisfaction, etc.).
- All metrics should be rates/averages stored as decimals (0.0-1.0 range) OR flow metrics stored as raw numbers.
- pulse_agg: "AGGREGATION_AVERAGE" for rates, "AGGREGATION_SUM" for flows/counts.
"""

# Minimum data requirements per dashboard template
TEMPLATE_REQUIREMENTS = {
    "z_layout":         {"min_metrics": 4, "min_dimensions": 3, "description": "Z Layout needs 4-6 metrics and 3+ dimensions for filters, grouping, and breakdowns"},
    "f_layout":         {"min_metrics": 3, "min_dimensions": 3, "description": "F Layout needs 3 metrics and 3+ dimensions"},
    "exec_summary":     {"min_metrics": 4, "min_dimensions": 2, "description": "Executive Summary needs 4-5 metrics and 2+ dimensions for entity rankings"},
    "pharma_analytics": {"min_metrics": 4, "min_dimensions": 3, "description": "Pharma Analytics needs 4 metrics and 3 dimensions (specialty, geography, brand)"},
    "multi_page_kpi":   {"min_metrics": 6, "min_dimensions": 4, "description": "Multi-Page KPI needs 6+ metrics and 4+ dimensions across 4 dashboard pages"},
    "standard":         {"min_metrics": 3, "min_dimensions": 2, "description": "Standard layout needs 3+ metrics and 2+ dimensions"},
}


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


def generate_story(company, industry, use_case, audience, notes="", research_depth="quick", dashboard_template=None):
    """Call Claude API to generate story + metrics with web research. Returns dict."""
    from app import _get_chat_config, CHAT_MODEL

    cfg = _get_chat_config()
    if not cfg:
        raise RuntimeError("No API key configured for AI generation")

    # --- Web research (same 5 areas as CLI /build-demo) ---
    research_context = ""
    brand_colors = {}
    try:
        from researcher import research_company, format_research_for_prompt
        research = research_company(
            company=company,
            industry=industry,
            use_case=use_case,
            depth=research_depth,
        )
        research_context = format_research_for_prompt(research)
        brand_colors = research.get("brand_colors", {})
    except Exception:
        pass

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

    # Generate enough metrics/dimensions to support any template
    template_context = ""
    if dashboard_template and dashboard_template in TEMPLATE_REQUIREMENTS:
        tpl_reqs = TEMPLATE_REQUIREMENTS[dashboard_template]
        template_context = f"""
DASHBOARD REQUIREMENTS: Generate at least {tpl_reqs['min_metrics']} metrics and at least {tpl_reqs['min_dimensions']} dimensions."""
    else:
        template_context = """
DASHBOARD REQUIREMENTS: Generate at least 4 metrics and at least 3 dimensions to support the widest range of dashboard templates."""

    user_msg = f"""Company: {company}
Industry: {industry}
Use case / topic: {use_case}
Audience: {audience}
Additional context: {notes or 'None'}
{template_context}
{depth_context}
{research_context}
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
    elif cfg.get("api_key", "").startswith("sk-ant-oat"):
        import requests as req
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Authorization": f"Bearer {cfg['api_key']}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": CHAT_MODEL,
            "max_tokens": 2048,
            "system": STORY_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_msg}],
        }
        r = req.post(url, headers=headers, json=body, timeout=60)
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
    result = None
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', text)
        if not match:
            raise RuntimeError(f"AI did not return valid JSON. Response: {text[:300]}")
        try:
            result = json.loads(match.group())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"AI returned malformed JSON: {e}. Response: {text[:300]}")

    # Attach brand colors from research (if found and not already in result)
    if brand_colors and not result.get("brand_colors"):
        result["brand_colors"] = brand_colors

    return result


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

    # Per-dimension signal multipliers: culprit (1.5-2.5x), moderate (0.8-1.2x),
    # flat (0.0-0.3x), and one counter-trend (-0.10 to -0.15)
    segment_mults = {}
    for dim in dimensions:
        vals = dim_values[dim]
        mults = [random.uniform(1.8, 2.5)]   # culprit segment
        mults.append(random.uniform(0.8, 1.2))  # moderate
        mults.append(random.uniform(0.0, 0.3))  # flat
        mults.append(random.uniform(-0.15, -0.08))  # counter-trend
        while len(mults) < len(vals):
            mults.append(random.uniform(0.3, 1.0))
        random.shuffle(mults)
        segment_mults[dim] = dict(zip(vals, mults[:len(vals)]))

    # 2D compound multiplier table for the primary culprit dimension pair
    # Creates the "drill deeper" story: overall down → dim1 filtered → dim1+dim2 filtered → steeper
    compound_2d = {}
    if len(dimensions) >= 2:
        dim1_vals = dim_values[dimensions[0]]
        dim2_vals = dim_values[dimensions[1]]
        culprit_dim1 = max(segment_mults[dimensions[0]], key=segment_mults[dimensions[0]].get)
        for v1 in dim1_vals:
            for v2 in dim2_vals:
                if v1 == culprit_dim1:
                    compound_2d[(v1, v2)] = random.uniform(1.2, 2.8)
                else:
                    compound_2d[(v1, v2)] = segment_mults[dimensions[0]].get(v1, 0.5)

    # Noise scale by segment size (larger segments = smoother)
    noise_scales = {}
    for dim in dimensions:
        vals = dim_values[dim]
        sorted_vals = sorted(vals, key=lambda v: abs(segment_mults[dim].get(v, 0)), reverse=True)
        for i, v in enumerate(sorted_vals):
            noise_scales[(dim, v)] = 0.022 - (i * 0.004)

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

                # 2D compound multiplier if available, else fall back to dim1 scalar
                if compound_2d and len(dimensions) >= 2:
                    combined_mult = compound_2d.get((combo[0], combo[1]),
                                                     segment_mults[dimensions[0]].get(combo[0], 0.5))
                else:
                    combined_mult = segment_mults[dimensions[0]].get(combo[0], 0.5)

                # Noise based on first dimension's segment size
                ns = noise_scales.get((dimensions[0], combo[0]), 0.015)

                row = {"Record ID": f"{eid}_{dt.strftime('%Y%m%d')}", "Date": dt, "Entity ID": eid}
                for i, dim in enumerate(dimensions):
                    row[dim] = combo[i]

                for mc in metric_config:
                    base = base_values[mc["field"]]
                    is_primary = mc.get("is_primary", False)
                    sent = mc.get("sentiment", "up_is_good")

                    if is_primary:
                        mag = signal_magnitude
                        mult = combined_mult
                    else:
                        mag = supporting_magnitude
                        mult = combined_mult * 0.7

                    noise = np.random.normal(0, ns)
                    if sent == "up_is_good":
                        val = base * (1 - mag * ramp * mult) + noise
                    else:
                        val = base * (1 + mag * ramp * mult * 0.3) + noise

                    if mc["agg"] == "Average":
                        val = max(0.01, min(1.0, val))
                    else:
                        val = max(0, val * 1000)

                    row[mc["label"]] = round(val, 4)

                    # Goal target column (constant)
                    goal = mc.get("goal")
                    if goal:
                        row[goal.get("field", f"{mc['label']} Target")] = goal["value"]

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

    # --- Section 4b: Pulse Discover Questions (Pulse only, if insights captured) ---
    if build_type == "pulse":
        discover = checkpoint.get("pulse_discover_results", [])
        if discover:
            doc.add_heading("Pulse Discover Questions", level=1)
            doc.add_paragraph(
                "Each question below was asked to Pulse Discover at build time. "
                "The responses are live AI-generated answers based on the actual demo data."
            )
            for i, dr in enumerate(discover):
                doc.add_heading(f"Q{i+1} — {dr.get('metric', '')}", level=2)
                p_ask = doc.add_paragraph("")
                p_ask.add_run("Ask: ").bold = True
                p_ask.add_run(f'"{dr["question"]}"')
                p_resp = doc.add_paragraph("")
                p_resp.add_run("Expected response: ").bold = True
                p_resp.add_run(dr.get("answer", "(no response captured)"))

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

    # Cleanup: delete only assets this script previously created (tracked in checkpoint)
    base = config["tableau"]["server_url"].rstrip("/")
    api_ver = server.version or "3.24"
    h_pulse_std = {"x-tableau-auth": auth_token, "Accept": "application/json"}
    try:
        # Delete prior project (by ID from checkpoint)
        if cp.get("pulse_project_id"):
            try:
                server.projects.delete(cp["pulse_project_id"])
                progress(q, "cleanup", f"Deleted prior project: {cp.get('pulse_project_name', cp['pulse_project_id'])}", -1)
            except Exception:
                pass

        # Delete prior group (by ID from checkpoint)
        if cp.get("pulse_group_id"):
            try:
                req.delete(f"{base}/api/{api_ver}/sites/{site_id}/groups/{cp['pulse_group_id']}",
                           headers={"x-tableau-auth": auth_token})
                progress(q, "cleanup", f"Deleted prior group", -1)
            except Exception:
                pass

        # Delete prior Pulse definitions (by ID from checkpoint)
        for did in cp.get("pulse_def_ids", []):
            try:
                req.delete(f"{base}/api/-/pulse/definitions/{did}", headers=h_pulse_std)
                progress(q, "cleanup", f"Deleted prior definition: {did}", -1)
            except Exception:
                pass

        # Clear checkpoint tracking for Pulse assets
        for k in ("pulse_project_id", "pulse_project_name", "pulse_group_id",
                   "pulse_def_ids", "pulse_metric_ids", "pulse_datasource_id",
                   "pulse_datasource_name", "pulse_insights_done", "pulse_discover_results"):
            cp.pop(k, None)
        _save_cp(cp, slug, demo_dir)
    except Exception as e:
        progress(q, "info", f"Cleanup partial: {e}", -1)

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

        # Payload matches the working CLI pattern: specification wrapper with basic_specification
        is_sum = mc.get("pulse_agg") == "AGGREGATION_SUM"
        payload = {
            "name": f"{company} — {mc['label']}",
            "description": mc.get("why_it_matters", mc.get("description", "")),
            "specification": {
                "datasource": {"id": ds_luid},
                "basic_specification": {
                    "measure": {"field": mc["label"], "aggregation": mc.get("pulse_agg", "AGGREGATION_AVERAGE")},
                    "time_dimension": {"field": "Date"},
                    "filters": [],
                },
                "is_running_total": is_sum,
            },
            "representation_options": {
                "type": "NUMBER_FORMAT_TYPE_NUMBER",
                "number_units": {
                    "singular_noun": mc.get("singular", mc["label"].lower()),
                    "plural_noun": mc.get("plural", mc["label"].lower() + "s"),
                },
                "sentiment_type": "SENTIMENT_TYPE_UP_IS_GOOD" if mc.get("sentiment") == "up_is_good" else "SENTIMENT_TYPE_DOWN_IS_GOOD" if mc.get("sentiment") == "down_is_good" else "SENTIMENT_TYPE_UP_IS_GOOD",
            },
            "extension_options": {
                "allowed_dimensions": dimensions,
                "allowed_granularities": [
                    "GRANULARITY_BY_YEAR",
                    "GRANULARITY_BY_QUARTER",
                    "GRANULARITY_BY_MONTH",
                ],
                "offset_from_today": 0,
                "correlation_candidate_definition_ids": [],
                "use_dynamic_offset": False,
            },
            "insights_options": {"show_insights": True, "settings": []},
            "comparisons": {"comparisons": [
                {"compare_config": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD", "comparison_period_override": []}, "index": "0"},
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
                  json={"extension_options": {
                      "allowed_dimensions": dimensions,
                      "allowed_granularities": [
                          "GRANULARITY_BY_YEAR", "GRANULARITY_BY_QUARTER", "GRANULARITY_BY_MONTH",
                      ],
                      "offset_from_today": 0,
                      "correlation_candidate_definition_ids": [],
                      "use_dynamic_offset": True,
                  }})

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

    # --- Pulse Discover Questions (Brief API) ---
    if cp.get("pulse_def_ids") and not cp.get("pulse_insights_done"):
        progress(q, "insights", "Capturing Pulse AI insights...", 87)
        try:
            import tableauserverclient as TSC
            auth_token = server.auth_token
            server_url = server.server_address
            site_id = server.site_id

            h_std = {"x-tableau-auth": auth_token, "Accept": "application/json"}
            h_brief = {
                "x-tableau-auth": auth_token,
                "Content-Type": "application/vnd.tableau.pulse.embeddingsservice.v1.GenerateInsightBriefRequest+json",
            }

            discover_results = []
            questions = [
                f"Summarize the overall trend for {mc['label']}" for mc in metric_config[:4]
            ]
            primary = [mc for mc in metric_config if mc.get("is_primary")]
            if primary:
                questions.append(f"What is driving the change in {primary[0]['label']}?")
                questions.append(f"Which segments are most affected by the {primary[0]['label']} decline?")

            for i, (def_id, metric_id) in enumerate(zip(
                cp.get("pulse_def_ids", []), cp.get("pulse_metric_ids", [])
            )):
                if i >= len(questions):
                    break
                question = questions[i]
                mc = metric_config[i] if i < len(metric_config) else metric_config[0]

                try:
                    # GET definition + metric data for context
                    r_def = req.get(f"{server_url}/api/-/pulse/definitions/{def_id}", headers=h_std)
                    r_met = req.get(f"{server_url}/api/-/pulse/definitions/{def_id}/metrics", headers=h_std)
                    if not (r_def.ok and r_met.ok):
                        continue

                    d = r_def.json()
                    m_list = r_met.json().get("metrics", [])
                    m = m_list[0] if m_list else {}

                    metric_context = {
                        "metadata": {
                            "definition_id": def_id,
                            "metric_id": metric_id,
                            "name": f"{company} — {mc['label']}",
                            "tags": [],
                        },
                        "metric": {
                            "definition": d.get("specification", {}),
                            "extension_options": d.get("extension_options", {}),
                            "metric_specification": m.get("specification", {}),
                            "representation_options": d.get("representation_options", {}),
                        },
                    }

                    brief_payload = {
                        "language": "LANGUAGE_EN_US",
                        "locale": "LOCALE_EN_US",
                        "now": TODAY.isoformat(),
                        "messages": [{
                            "content": question,
                            "action_type": "ACTION_TYPE_SUMMARIZE",
                            "role": "ROLE_USER",
                            "metric_group_context": [metric_context],
                            "metric_group_context_resolved": False,
                        }],
                    }

                    r_brief = req.post(f"{server_url}/api/-/pulse/insights/brief",
                                       headers=h_brief, json=brief_payload, timeout=30)
                    if r_brief.status_code == 201:
                        markup = r_brief.json().get("markup", "")
                        clean = re.sub(r'<span[^>]*>(.*?)</span>', r'\1', markup)
                        clean = re.sub(r'\[\[\d+\]\]\([^)]+\)', '', clean)
                        clean = re.sub(r'\*\*', '', clean).strip()
                        discover_results.append({"question": question, "answer": clean, "metric": mc["label"]})
                        progress(q, "insights", f"Q{i+1}: {mc['label']} — got response", -1)
                    else:
                        progress(q, "info", f"Brief API {r_brief.status_code} for {mc['label']}", -1)
                except Exception as e:
                    progress(q, "info", f"Insight {i+1} failed: {str(e)[:100]}", -1)

            if discover_results:
                cp["pulse_discover_results"] = discover_results
                progress(q, "insights", f"Captured {len(discover_results)} Pulse AI insights", -1)
            cp["pulse_insights_done"] = True
            _save_cp(cp, slug, demo_dir)
        except Exception as e:
            progress(q, "warn", f"Pulse insights phase failed (non-blocking): {e}", -1)
            cp["pulse_insights_done"] = True
            _save_cp(cp, slug, demo_dir)

    progress(q, "walkthrough", "Generating walkthrough document...", 90)
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

def _validate_next_build(config, cp, metric_config, q):
    """Post-build validation: query SDM, check metrics and vizzes have data."""
    import requests as req
    from connections import get_sf_token, sf_headers

    checks_passed = 0
    checks_failed = 0
    checks_total = 0

    try:
        sf_token, sf_instance = get_sf_token(config)
        h = sf_headers(sf_token)
    except Exception as e:
        progress(q, "validate", f"SKIP — could not authenticate: {e}", -1)
        return

    sdm_api = cp.get("sdm_api", "")
    do_api = cp.get("do_api", "")

    # 1. Query the SDM to verify data is accessible
    progress(q, "validate", "Checking SDM data query...", -1)
    checks_total += 1
    try:
        first_meas = ""
        first_dim = ""
        for k, v in cp.get("measurement_map", {}).items():
            first_meas = v
            break
        for k, v in cp.get("dim_field_map", {}).items():
            if k.lower() not in ("date", "record_id", "entity_id", "day_offset", "record id", "entity id"):
                first_dim = v
                break

        dlo_name = cp.get("dlo_name", "")
        if first_meas and dlo_name:
            query_body = {
                "sql": f'SELECT COUNT(*) as cnt FROM {dlo_name}',
            }
            r = req.post(f"{sf_instance}/services/data/v62.0/ssot/queryv2",
                         headers=h, json=query_body, timeout=30)
            if r.ok:
                resp = r.json()
                data = resp.get("data", resp) if isinstance(resp, dict) else resp
                row_count = data[0].get("cnt", 0) if data and isinstance(data[0], dict) else 0
                if row_count and int(row_count) > 0:
                    progress(q, "validate", f"✓ SDM query returned {row_count} rows", -1)
                    checks_passed += 1
                else:
                    progress(q, "validate", f"✗ SDM query returned 0 rows — data may not have ingested", -1)
                    checks_failed += 1
            else:
                progress(q, "validate", f"✗ SDM query failed: {r.text[:200]}", -1)
                checks_failed += 1
        else:
            progress(q, "validate", "SKIP — no measurement or DO found for query check", -1)
    except Exception as e:
        progress(q, "validate", f"✗ SDM query error: {str(e)[:200]}", -1)
        checks_failed += 1

    # 2. Check each metric renders (GET metric, check for non-null value)
    for mtc_api in cp.get("metric_apis", []):
        checks_total += 1
        try:
            r = req.get(
                f"{sf_instance}/services/data/v66.0/ssot/semantic/models/{sdm_api}/metrics/{mtc_api}?minorVersion=12",
                headers=h, timeout=15)
            if r.ok:
                mtc_data = r.json()
                label = mtc_data.get("label", mtc_api)
                progress(q, "validate", f"✓ Metric '{label}' exists in SDM", -1)
                checks_passed += 1
            else:
                progress(q, "validate", f"✗ Metric '{mtc_api}' not found: {r.status_code}", -1)
                checks_failed += 1
        except Exception as e:
            progress(q, "validate", f"✗ Metric '{mtc_api}' check error: {str(e)[:100]}", -1)
            checks_failed += 1

    # 3. Check Display Date calc dim exists
    checks_total += 1
    dd_api = cp.get("display_date_api", "")
    if dd_api:
        try:
            r = req.get(
                f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{sdm_api}/calculated-dimensions/{dd_api}",
                headers=h, timeout=15)
            if r.ok:
                progress(q, "validate", f"✓ Display Date calc dim exists: {dd_api}", -1)
                checks_passed += 1
            else:
                progress(q, "validate", f"✗ Display Date not found (API returned {r.status_code}) — dates will show raw values", -1)
                checks_failed += 1
        except Exception as e:
            progress(q, "validate", f"✗ Display Date check error: {str(e)[:100]}", -1)
            checks_failed += 1
    else:
        progress(q, "validate", "✗ Display Date was not created — metrics will show raw dates from data generation", -1)
        checks_failed += 1

    # 4. Check each viz exists and has a valid data source
    for viz_api in cp.get("viz_apis", []):
        checks_total += 1
        try:
            r = req.get(
                f"{sf_instance}/services/data/v66.0/tableau/visualizations/{viz_api}?minorVersion=12",
                headers=h, timeout=15)
            if r.ok:
                viz_data = r.json()
                label = viz_data.get("label", viz_api)
                ds = viz_data.get("dataSource", "")
                if ds:
                    progress(q, "validate", f"✓ Viz '{label}' exists, dataSource: {ds}", -1)
                    checks_passed += 1
                else:
                    progress(q, "validate", f"✗ Viz '{label}' has no dataSource — will show no data", -1)
                    checks_failed += 1
            else:
                progress(q, "validate", f"✗ Viz '{viz_api}' not found: {r.status_code}", -1)
                checks_failed += 1
        except Exception as e:
            progress(q, "validate", f"✗ Viz '{viz_api}' check error: {str(e)[:100]}", -1)
            checks_failed += 1

    # 5. Check dashboard exists
    if cp.get("dash_api"):
        checks_total += 1
        try:
            r = req.get(
                f"{sf_instance}/services/data/v66.0/tableau/dashboards/{cp['dash_api']}?minorVersion=12",
                headers=h, timeout=15)
            if r.ok:
                progress(q, "validate", f"✓ Dashboard exists: {cp['dash_api']}", -1)
                checks_passed += 1
            else:
                progress(q, "validate", f"✗ Dashboard not found: {r.status_code}", -1)
                checks_failed += 1
        except Exception as e:
            progress(q, "validate", f"✗ Dashboard check error: {str(e)[:100]}", -1)
            checks_failed += 1

    # 6. Verify SDM has data objects with measurements
    checks_total += 1
    try:
        if sdm_api and do_api:
            r = req.get(
                f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{sdm_api}/data-objects/{do_api}",
                headers=h, timeout=15)
            if r.ok:
                do_data = r.json()
                meas_count = len(do_data.get("semanticMeasurements", []))
                dim_count = len(do_data.get("semanticDimensions", []))
                progress(q, "validate", f"✓ SDM data object verified: {meas_count} measurements, {dim_count} dimensions", -1)
                checks_passed += 1
            else:
                progress(q, "validate", f"✗ SDM data object not found: {r.status_code}", -1)
                checks_failed += 1
    except Exception as e:
        progress(q, "validate", f"✗ SDM data object check error: {str(e)[:200]}", -1)
        checks_failed += 1

    # Summary
    summary = f"Validation complete: {checks_passed}/{checks_total} passed"
    if checks_failed:
        summary += f", {checks_failed} failed"
        progress(q, "validate", f"⚠ {summary}", -1)
    else:
        progress(q, "validate", f"✓ {summary} — all assets verified", -1)


def _cleanup_assets(asset_list, api_base, headers, asset_type, q):
    """Delete previously created assets before recreating. Skips 404s silently."""
    import requests as req
    for name in list(asset_list):
        try:
            r = req.delete(f"{api_base}/{name}", headers=headers)
            if r.status_code in (204, 200):
                progress(q, "cleanup", f"Deleted prior {asset_type}: {name}", -1)
            elif r.status_code == 404:
                pass
        except Exception:
            pass
    asset_list.clear()


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

        schema_name = re.sub(r"[^a-z0-9_]", "", slug.replace("-", "_")).strip("_")
        fields = [{"name": "Record ID", "dataType": "Text", "isPrimaryKey": True}]
        fields.append({"name": "Date", "dataType": "Date"})
        fields.append({"name": "Day_Offset", "dataType": "Number"})
        fields.append({"name": "Entity ID", "dataType": "Text"})
        for dim in story_config.get("dimensions", []):
            fields.append({"name": dim, "dataType": "Text"})
        for mc in metric_config:
            fields.append({"name": mc["label"], "dataType": "Number"})

        def _clean_field_name(name):
            """Sanitize field name for Data Cloud schema: lowercase, underscores, alphanumeric only, max 40 chars.
            Also strips reserved prefixes (salesforce, tableau, data_cloud)."""
            clean = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_"))
            clean = re.sub(r"_+", "_", clean).strip("_")
            for prefix in ("salesforce_", "tableau_", "data_cloud_", "sfdc_"):
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
            return (clean[:40] if clean else "field")

        schema_fields = [{"name": _clean_field_name(f["name"]),
                          "label": _clean_field_name(f["name"]),
                          "dataType": f["dataType"]}
                         for f in fields]

        # Check if schema already exists — if so, skip PUT entirely
        r_schema = req.get(f"{sf_instance}/services/data/v62.0/ssot/connections/{connector_id}/schema", headers=h)
        existing = r_schema.json() if r_schema.ok else {"schemas": []}
        existing_schemas = existing.get("schemas", []) if isinstance(existing, dict) else []
        schema_exists = any(s.get("name") == schema_name for s in existing_schemas)

        if not schema_exists:
            new_schema = {"name": schema_name, "label": schema_name,
                          "schemaType": "IngestApi", "fields": schema_fields}
            r_put = req.put(f"{sf_instance}/services/data/v62.0/ssot/connections/{connector_id}/schema",
                            headers=h, json={"schemas": [new_schema]})
            if not r_put.ok:
                raise RuntimeError(f"Schema registration failed: {r_put.text[:300]}")
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
            # Try to find an existing stream — "already in use" means the schema/DLO exists
            progress(q, "stream", f"Stream creation returned {r_stream.status_code} — checking for existing stream...", -1)
            r_list = req.get(f"{sf_instance}/services/data/v62.0/ssot/data-streams", headers=h)
            streams_resp = r_list.json()
            stream_list = streams_resp.get("dataStreams", []) if isinstance(streams_resp, dict) else streams_resp
            found = False
            # Search by schema name OR DLO name (stream names have connector prefix + hash suffix)
            schema_lower = schema_name.lower().replace("_", "")
            for s in stream_list:
                if not isinstance(s, dict):
                    continue
                sname = s.get("name", "").lower()
                dlo_name = s.get("dataLakeObjectInfo", {}).get("name", "") if isinstance(s.get("dataLakeObjectInfo"), dict) else ""
                if schema_name in sname or schema_lower in sname.replace("_", "") or schema_name in dlo_name:
                    cp["stream_name"] = s["name"]
                    dlo_info = s.get("dataLakeObjectInfo", {})
                    if isinstance(dlo_info, dict):
                        cp["dlo_name"] = dlo_info.get("name", "")
                    progress(q, "stream", f"Found existing stream: {cp['stream_name']} (DLO: {cp.get('dlo_name','')})", -1)
                    found = True
                    break
            if not found:
                # Schema is "in use" but no stream found — the old stream was deleted
                # but the schema registration persists. Try with a unique suffix.
                import hashlib as _hl
                suffix = _hl.md5(f"{schema_name}{time.time()}".encode()).hexdigest()[:8].upper()
                unique_schema = f"{schema_name}_{suffix}"
                progress(q, "stream", f"Retrying with unique schema name: {unique_schema}", -1)
                new_schema = {"name": unique_schema, "label": unique_schema,
                              "schemaType": "IngestApi", "fields": schema_fields}
                req.put(f"{sf_instance}/services/data/v62.0/ssot/connections/{connector_id}/schema",
                        headers=h, json={"schemas": [new_schema]})
                time.sleep(5)
                stream_payload["name"] = unique_schema
                stream_payload["label"] = unique_schema
                stream_payload["connectorInfo"]["connectorDetails"]["events"] = [unique_schema]
                stream_payload["dataLakeObjectInfo"]["label"] = unique_schema
                r_stream2 = req.post(f"{sf_instance}/services/data/v62.0/ssot/data-streams", headers=h, json=stream_payload)
                if r_stream2.status_code in (200, 201):
                    resp2 = r_stream2.json()
                    if isinstance(resp2, list): resp2 = resp2[0] if resp2 else {}
                    cp["stream_name"] = resp2.get("name", unique_schema)
                    cp["dlo_name"] = resp2.get("dataLakeObjectInfo", {}).get("name", "")
                    cp["schema_name"] = unique_schema
                    progress(q, "stream", f"Created stream with new schema: {cp['stream_name']}", -1)
                else:
                    raise RuntimeError(f"Stream creation failed: {r_stream2.status_code} {r_stream2.text[:300]}")
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

        # Rename columns to match sanitized schema field names
        col_rename = {}
        for col in df.columns:
            clean = re.sub(r"[^a-z0-9_]", "", col.lower().replace(" ", "_"))
            clean = re.sub(r"_+", "_", clean).strip("_") or "field"
            col_rename[col] = clean
        df_ingest = df.rename(columns=col_rename)

        job_payload = {
            "object": schema_name,
            "sourceName": connector_name,
            "operation": "upsert",
        }
        r_job = req.post(f"https://{dc_domain}/api/v1/ingest/jobs", headers=dch, json=job_payload)
        r_job.raise_for_status()
        job_id = r_job.json()["id"]

        csv_buf = io.StringIO()
        df_ingest.to_csv(csv_buf, index=False)
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

        # Retry cleanup: delete prior workspace/SDM assets from failed runs
        if cp.get("all_dash_apis"):
            _cleanup_assets(cp["all_dash_apis"],
                f"{sf_instance}/services/data/v66.0/tableau/dashboards", h, "dashboard", q)
        if cp.get("all_viz_apis"):
            _cleanup_assets(cp["all_viz_apis"],
                f"{sf_instance}/services/data/v66.0/tableau/visualizations", h, "viz", q)
        if cp.get("all_sdm_apis"):
            _cleanup_assets(cp["all_sdm_apis"],
                f"{sf_instance}/services/data/v65.0/ssot/semantic/models", h, "SDM", q)
        if cp.get("all_ws_apis"):
            _cleanup_assets(cp["all_ws_apis"],
                f"{sf_instance}/services/data/v65.0/tableau/workspaces", h, "workspace", q)
        for k in ("ws_api", "sdm_api", "do_api", "dim_field_map", "measurement_map",
                   "display_date_api", "metric_apis", "viz_apis", "dash_api",
                   "viz_done", "dash_done", "metrics_done"):
            cp.pop(k, None)
        _save_cp(cp, slug, demo_dir)

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
                         headers=h, json={"label": sdm_label, "dataspace": "default", "agentEnabled": True})
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

        # PUT descriptions on dimensions so Concierge understands what each field means
        dim_descriptions = story_config.get("dim_descriptions", {})
        for dim in do_data.get("semanticDimensions", []):
            dim_api = dim["apiName"]
            base = dim.get("dataObjectFieldName", "").replace("__c", "")
            label = dim.get("label", base)
            desc = dim_descriptions.get(base, dim_descriptions.get(label, ""))
            if not desc:
                desc = f"Use this field to filter or group by {label}."
            try:
                req.put(
                    f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}/data-objects/{cp['do_api']}/dimensions/{dim_api}",
                    headers=h, json={
                        "apiName": dim_api,
                        "label": label,
                        "dataObjectFieldName": dim.get("dataObjectFieldName", ""),
                        "description": desc,
                    })
            except Exception:
                pass

        progress(q, "sdm", "Creating self-healing Display Date...", 50)
        build_date_str = TODAY.strftime("%Y-%m-%d")
        date_field_api = dim_field_map.get("date") or dim_field_map.get("Date", "")
        if not date_field_api:
            all_dim_keys = list(dim_field_map.keys())
            progress(q, "warn", f"No 'date' dimension found in field map. Keys: {all_dim_keys[:10]}", -1)
            for k, v in dim_field_map.items():
                if "date" in k.lower():
                    date_field_api = v
                    progress(q, "info", f"Using '{k}' → '{v}' as date dimension", -1)
                    break

        expression = f'DATEADD("day", DATEDIFF("day", #{build_date_str}#, [{cp["do_api"]}].[{date_field_api}]), TODAY())'
        progress(q, "info", f"Display Date expression: {expression}", -1)
        r_dd = req.post(
            f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}/calculated-dimensions",
            headers=h, json={
                "apiName": "Display_Date", "label": "Display Date",
                "expression": expression, "dataType": "Date",
            })
        if r_dd.ok:
            cp["display_date_api"] = r_dd.json().get("apiName", "Display_Date")
            progress(q, "info", f"Display Date created: {cp['display_date_api']}", -1)
        else:
            cp["display_date_api"] = ""
            progress(q, "warn", f"Display Date creation failed: {r_dd.text[:300]}", -1)

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
            dd_api = cp.get("display_date_api", "")
            if dd_api:
                time_ref = {"calculatedFieldApiName": dd_api}
            else:
                raw_date_api = cp.get("dim_field_map", {}).get("date", "")
                time_ref = {"tableFieldReference": {"fieldApiName": raw_date_api, "tableApiName": cp["do_api"]}}
                progress(q, "warn", f"No Display Date — metric '{mc['label']}' using raw date field '{raw_date_api}'", -1)

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

        # Retry cleanup: delete prior viz/dashboard assets from failed runs
        if cp.get("all_dash_apis"):
            _cleanup_assets(cp["all_dash_apis"],
                f"{sf_instance}/services/data/v66.0/tableau/dashboards", h, "dashboard", q)
        if cp.get("all_viz_apis"):
            _cleanup_assets(cp["all_viz_apis"],
                f"{sf_instance}/services/data/v66.0/tableau/visualizations", h, "viz", q)
        for k in ("viz_apis", "dash_api", "dash_done"):
            cp.pop(k, None)
        _save_cp(cp, slug, demo_dir)

        # --- Primary path: Package & Deploy templates (pixel-perfect, 72-col grid) ---
        template_deployed = False
        try:
            from template_deployer import deploy_template, AVAILABLE_TEMPLATES
            template_name = build_config.get("dashboard_template", "z_layout") if build_config else "z_layout"
            if template_name in AVAILABLE_TEMPLATES:
                progress(q, "viz", f"Deploying {template_name.replace('_', ' ').title()} template...", 72)

                # Get workspace ID and SDM info
                r_ws = req.get(f"{sf_instance}/services/data/v65.0/tableau/workspaces/{cp['ws_api']}", headers=h)
                ws_info = r_ws.json() if r_ws.ok else {}
                ws_id = ws_info.get("id", "")
                ws_label = ws_info.get("label", cp["ws_api"])

                r_sdm = req.get(f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}", headers=h)
                sdm_info = r_sdm.json() if r_sdm.ok else {}
                sdm_label = sdm_info.get("label", cp["sdm_api"])
                sdm_id = sdm_info.get("id", "")

                # Build field_map: template uses D16 field names, remap to target SDM
                # The template vizzes reference _clc calc measures and DO dimensions
                # Only use CLCs that were actually created (metric creation may have partially failed)
                created_metric_bases = [m.replace("_mtc", "") for m in cp.get("metric_apis", [])]
                clc_apis = [f"{base}_clc" for base in created_metric_bases]
                dim_map = cp.get("dim_field_map", {})
                SYSTEM_DIMS = {"date", "record_id", "entity_id", "day_offset", "kq_record_id",
                               "datasourceobject", "datasource", "cdp_sys_sourceversion",
                               "data_source_object", "data_source"}
                user_dims = [(k, v) for k, v in dim_map.items()
                             if k.lower().replace(" ", "_") not in SYSTEM_DIMS]

                # Map template fields to this demo's fields
                field_map = {}
                # Primary measure for hero trend line
                if clc_apis:
                    field_map["platform_utilization_rate_clc"] = clc_apis[0]
                # Breakdown measure for detail vizzes
                if len(clc_apis) > 1:
                    field_map["reports_migrated_to_tableau_clc"] = clc_apis[1]
                # Dimensions for grouping/breakdown/detail
                dim_template_names = ["team1", "report_type1", "system_source1", "request_status1"]
                for i, tmpl_dim in enumerate(dim_template_names):
                    if i < len(user_dims):
                        field_map[tmpl_dim] = user_dims[i][1]  # map to target dim apiName

                # Filter fields
                filter_fields = [
                    {"fieldName": api, "objectName": cp["do_api"], "label": name.replace("_", " ").title()}
                    for name, api in user_dims[:6]
                ]

                demo_label = build_config.get("demo_name", "") or company if build_config else company
                results = deploy_template(
                    template_name=template_name,
                    sf_token=sf_token,
                    sf_instance=sf_instance,
                    sdm_api=cp["sdm_api"],
                    sdm_label=sdm_label,
                    sdm_id=sdm_id,
                    ws_api=cp["ws_api"],
                    ws_label=ws_label,
                    ws_id=ws_id,
                    do_api=cp.get("do_api", ""),
                    slug=slug,
                    dash_label=f"{demo_label} Dashboard",
                    metric_apis=[m for m in cp.get("metric_apis", [])],
                    filter_fields=filter_fields,
                    title_text=demo_label,
                    detail_header="Details",
                    field_map=field_map if field_map else None,
                )

                if results.get("dashboard") and not results.get("errors"):
                    cp["viz_apis"] = [v["name"] for v in results["vizzes_created"].values()]
                    cp["all_viz_apis"].extend(cp["viz_apis"])
                    cp["dash_api"] = results["dashboard"]["name"]
                    cp["all_dash_apis"].append(cp["dash_api"])
                    cp["viz_done"] = True
                    cp["dash_done"] = True
                    template_deployed = True
                    progress(q, "dash", f"Template dashboard deployed: {cp['dash_api']} ({len(cp['viz_apis'])} vizzes)", 85)
                    _save_cp(cp, slug, demo_dir)
                elif results.get("vizzes_created"):
                    # Vizzes created but dashboard failed
                    cp["viz_apis"] = [v["name"] for v in results["vizzes_created"].values()]
                    cp["all_viz_apis"].extend(cp["viz_apis"])
                    cp["viz_done"] = True
                    _save_cp(cp, slug, demo_dir)
                    progress(q, "warn", f"Template vizzes created but dashboard failed: {results['errors']}", -1)
                else:
                    progress(q, "warn", f"Template deploy failed: {results.get('errors', ['unknown'])}", -1)
        except Exception as e:
            progress(q, "info", f"Template deployer not available ({e}) — falling back", -1)

        # --- Fallback: MCP path (only if template deploy didn't succeed) ---
        mcp_available = False
        if not template_deployed and not cp.get("viz_done"):
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

        def _parse_mcp_result(result):
            """Extract the actual data from an MCP tool response.
            MCP wraps in {"content": [{"text": "<json>"}]}.
            Viz creation returns {"defaultExc": "<nested-json>", "responseCode": 201}."""
            if not isinstance(result, dict):
                return {}
            if result.get("isError"):
                err_text = result.get("content", [{}])[0].get("text", "Unknown error") if result.get("content") else "Unknown error"
                raise RuntimeError(f"MCP error: {err_text[:200]}")
            content = result.get("content", [])
            if content and content[0].get("type") == "text":
                try:
                    outer = json.loads(content[0]["text"])
                except (json.JSONDecodeError, KeyError):
                    return result
                if isinstance(outer, list):
                    return outer[0] if outer else {}
                # Handle double-nested: {"defaultExc": "<json>", "responseCode": 201}
                if isinstance(outer, dict) and "defaultExc" in outer:
                    try:
                        return json.loads(outer["defaultExc"])
                    except (json.JSONDecodeError, KeyError):
                        pass
                return outer
            return result

        if mcp_available:
            # --- MCP path: slim viz specs (fields + chart type) + dashboard ---
            try:
                cp["viz_apis"] = []
                SYSTEM_DIMS = {"date", "record_id", "entity_id", "day_offset", "kq_record_id",
                               "datasourceobject", "datasource", "cdp_sys_sourceversion",
                               "data_source_object", "data_source"}
                user_dim_names = [k for k in cp.get("dim_field_map", {}).keys()
                                  if k.lower().replace(" ", "_") not in SYSTEM_DIMS]
                do_api = cp["do_api"]
                # MCP vizzes use the raw date field (not Display_Date calc dim)
                # because calc dims are model-level and can't have objectName
                date_field_api = cp.get("dim_field_map", {}).get("date", "")
                meas_map = cp.get("measurement_map", {})

                # Get workspace ID and SDM label (MCP needs these exact params)
                r_ws_info = req.get(f"{sf_instance}/services/data/v65.0/tableau/workspaces/{cp['ws_api']}", headers=h)
                ws_id = r_ws_info.json().get("id", "") if r_ws_info.ok else ""
                r_sdm_info = req.get(f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{cp['sdm_api']}", headers=h)
                sdm_label = r_sdm_info.json().get("label", "") if r_sdm_info.ok else ""

                # Build viz plan: alternate between trend line and bar chart
                viz_plan = []
                for i, mc in enumerate(metric_config[:4]):
                    meas_api = meas_map.get(mc["field"], "")
                    if not meas_api:
                        continue
                    dim = user_dim_names[i % len(user_dim_names)] if user_dim_names else None
                    dim_api = cp.get("dim_field_map", {}).get(dim, "") if dim else ""
                    is_rate = mc.get("agg", "Average") == "Average"
                    func = "Avg" if is_rate else "Sum"
                    fmt = "Percent" if is_rate else "Number"

                    if i == 0:
                        # First viz: trend line over time
                        viz_plan.append({
                            "label": f"{mc['label']} Over Time",
                            "name": f"{slug}_{mc['field']}_trend",
                            "fields": {
                                "F1": {"objectName": do_api, "fieldName": date_field_api,
                                        "displayCategory": "Discrete", "function": "DateTruncMonth"},
                                "F2": {"objectName": do_api, "fieldName": meas_api,
                                        "displayCategory": "Continuous", "function": func,
                                        "numberFormat": fmt},
                            },
                            "spec": {"layout": "Vizql", "columns": ["F1"], "rows": ["F2"],
                                     "marks": {"panes": {"type": "Line"}}},
                        })
                    elif i == 1 and dim_api:
                        # Second viz: bar by dimension
                        viz_plan.append({
                            "label": f"{mc['label']} by {dim}",
                            "name": f"{slug}_{mc['field']}_bar",
                            "fields": {
                                "F1": {"objectName": do_api, "fieldName": dim_api,
                                        "displayCategory": "Discrete"},
                                "F2": {"objectName": do_api, "fieldName": meas_api,
                                        "displayCategory": "Continuous", "function": func,
                                        "numberFormat": fmt},
                            },
                            "spec": {"layout": "Vizql", "columns": ["F1"], "rows": ["F2"],
                                     "marks": {"panes": {"type": "Bar"}}},
                            "sortIntent": "MeasureDescending",
                        })
                    elif dim_api:
                        # Multi-line by dimension
                        viz_plan.append({
                            "label": f"{mc['label']} by {dim}",
                            "name": f"{slug}_{mc['field']}_multi",
                            "fields": {
                                "F1": {"objectName": do_api, "fieldName": date_field_api,
                                        "displayCategory": "Discrete", "function": "DateTruncMonth"},
                                "F2": {"objectName": do_api, "fieldName": meas_api,
                                        "displayCategory": "Continuous", "function": func,
                                        "numberFormat": fmt},
                                "F3": {"objectName": do_api, "fieldName": dim_api,
                                        "displayCategory": "Discrete"},
                            },
                            "spec": {"layout": "Vizql", "columns": ["F1", "F3"], "rows": ["F2"],
                                     "marks": {"panes": {"type": "Line",
                                               "encodings": [{"fieldKey": "F3", "type": "Color"}]}}},
                        })
                    else:
                        # Fallback: simple trend
                        viz_plan.append({
                            "label": f"{mc['label']} Trend",
                            "name": f"{slug}_{mc['field']}_trend",
                            "fields": {
                                "F1": {"objectName": do_api, "fieldName": date_field_api,
                                        "displayCategory": "Discrete", "function": "DateTruncMonth"},
                                "F2": {"objectName": do_api, "fieldName": meas_api,
                                        "displayCategory": "Continuous", "function": func,
                                        "numberFormat": fmt},
                            },
                            "spec": {"layout": "Vizql", "columns": ["F1"], "rows": ["F2"],
                                     "marks": {"panes": {"type": "Line"}}},
                        })

                for i, vp in enumerate(viz_plan):
                    progress(q, "viz", f"Creating viz {i+1}/{len(viz_plan)} via MCP: {vp['label']}...", 70 + int(5 * i))
                    try:
                        raw = mcp.create_visualization(
                            label=vp["label"],
                            workspaceId=ws_id,
                            workspaceName=cp["ws_api"],
                            semanticModelName=cp["sdm_api"],
                            semanticModelLabel=sdm_label,
                            fields=vp["fields"],
                            visualSpecification=vp["spec"],
                            sortIntent=vp.get("sortIntent", "None"),
                        )
                        parsed = _parse_mcp_result(raw)
                        viz_api = parsed.get("name", "")
                        if viz_api:
                            cp["viz_apis"].append(viz_api)
                            cp["all_viz_apis"].append(viz_api)
                            progress(q, "viz", f"Created viz: {vp['label']} → {viz_api}", -1)
                        else:
                            progress(q, "warn", f"MCP viz {vp['label']}: no name in response: {str(parsed)[:150]}", -1)
                    except Exception as e:
                        progress(q, "warn", f"MCP viz {vp['label']} failed: {e}", -1)

                _save_cp(cp, slug, demo_dir)

                # MCP vizzes done — now create dashboard via MCP with upsert + place pattern
                if cp["viz_apis"]:
                    cp["viz_done"] = True
                    progress(q, "viz", f"Created {len(cp['viz_apis'])} vizzes via MCP", -1)
                    _save_cp(cp, slug, demo_dir)

                    progress(q, "dash", "Creating dashboard via MCP...", 80)
                    try:
                        demo_label = build_config.get("demo_name", "") or company
                        raw = mcp.create_dashboard(
                            name=f"{slug}_dashboard",
                            label=f"{demo_label} Dashboard",
                            workspaceIdOrApiName=cp["ws_api"],
                            minorVersion=-1,
                        )
                        parsed = _parse_mcp_result(raw)
                        dash_api = parsed.get("name", "")
                        if dash_api:
                            cp["dash_api"] = dash_api
                            cp["all_dash_apis"].append(dash_api)

                            # Build operations: upsert widgets + place on page
                            ops = []

                            # Metric widgets across top
                            for mi, mtc in enumerate(cp.get("metric_apis", [])[:3]):
                                wn = f"kpi_{mi}"
                                ops.append({"operation": "upsert_metric_widget",
                                    "widget": {"type": "metric", "name": wn,
                                        "source": {"name": mtc},
                                        "parameters": {"metricOption": {"sdmApiName": cp["sdm_api"]}}}})
                                ops.append({"operation": "place_widget_on_page",
                                    "pageName": "page_1",
                                    "placement": {"name": wn, "row": 0, "column": mi * 16, "rowspan": 6, "colspan": 16}})

                            # Filter widgets
                            for fi, (dname, dapi) in enumerate(
                                [(k, v) for k, v in cp.get("dim_field_map", {}).items()
                                 if k.lower() not in ("date", "record_id", "entity_id", "day_offset",
                                     "cdp_sys_sourceversion", "datasource", "datasourceobject",
                                     "data_source", "data_source_object", "kq_record_id")][:3]):
                                fn = f"filter_{fi}"
                                flabel = dname.replace("_", " ").title()
                                ops.append({"operation": "upsert_filter_widget",
                                    "widget": {"type": "filter", "name": fn, "label": flabel,
                                        "source": {"name": cp["sdm_api"]},
                                        "parameters": {"isLabelHidden": False,
                                            "filterOption": {"objectName": cp["do_api"], "fieldName": dapi}}}})
                                ops.append({"operation": "place_widget_on_page",
                                    "pageName": "page_1",
                                    "placement": {"name": fn, "row": 6, "column": fi * 16, "rowspan": 1, "colspan": 16}})

                            # Viz widgets in Z layout
                            z_layouts = [
                                {"row": 8, "col": 0, "rs": 12, "cs": 48},
                                {"row": 21, "col": 0, "rs": 12, "cs": 23},
                                {"row": 21, "col": 25, "rs": 12, "cs": 23},
                                {"row": 34, "col": 0, "rs": 12, "cs": 48},
                            ]
                            for vi, vapi in enumerate(cp["viz_apis"][:4]):
                                wn = f"viz_{vi}"
                                ops.append({"operation": "upsert_visualization_widget",
                                    "widget": {"type": "visualization", "name": wn,
                                        "source": {"name": vapi}}})
                                if vi < len(z_layouts):
                                    zl = z_layouts[vi]
                                    ops.append({"operation": "place_widget_on_page",
                                        "pageName": "page_1",
                                        "placement": {"name": wn, "row": zl["row"], "column": zl["col"],
                                                     "rowspan": zl["rs"], "colspan": zl["cs"]}})

                            ops.append({"operation": "save_dashboard"})

                            raw2 = mcp.edit_dashboard(
                                dashboardIdOrApiName=dash_api, minorVersion=-1,
                                autosave=False, operations=ops)
                            if not raw2.get("isError"):
                                cp["dash_done"] = True
                                progress(q, "dash", f"Dashboard created with {len(ops)} ops: {dash_api}", -1)
                            else:
                                progress(q, "warn", f"Dashboard ops failed: {raw2.get('content', [{}])[0].get('text', '')[:200]}", -1)
                        else:
                            progress(q, "warn", f"Dashboard creation returned no name", -1)
                    except Exception as e:
                        progress(q, "warn", f"MCP dashboard failed: {e}", -1)

                    _save_cp(cp, slug, demo_dir)
                else:
                    progress(q, "warn", "All MCP vizzes failed — falling back to REST", -1)
                    mcp_available = False

            except Exception as e:
                progress(q, "warn", f"MCP viz/dash failed ({e}) — falling back to REST", -1)
                mcp_available = False

        if not template_deployed and not mcp_available and not cp.get("viz_done"):
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

    # --- Phase 8: Post-build validation ---
    progress(q, "validate", "Running post-build validation...", 95)
    _validate_next_build(config, cp, metric_config, q)

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
        from crma_dashboard_builder import find_or_create_app

        sf_token, sf_instance = get_sf_token(config)
        dims = story_config.get("dimensions", [])
        fields_spec = fields_from_metric_config(metric_config, dims)
        metadata = build_metadata(slug, slug.replace("_", " ").title(), fields_spec)

        # Sanitize column names for CRMA (no spaces, snake_case)
        # Drop internal columns that aren't in the metadata
        import re as _re
        drop_cols = [c for c in df.columns if c.lower().replace(" ", "_") in
                     ("entity_id", "day_offset", "kq_record_id")]
        crma_df = df.drop(columns=drop_cols, errors="ignore")
        crma_df = crma_df.rename(columns={c: _re.sub(r'[^a-zA-Z0-9_]', '_', c).strip('_').lower() for c in crma_df.columns})
        csv_buf = io.BytesIO()
        crma_df.to_csv(csv_buf, index=False)
        csv_bytes = csv_buf.getvalue()

        # Find or create the CRMA app FIRST (upload needs the app ID, not the name)
        app_id = find_or_create_app(sf_instance, sf_token, f"{company} Analytics")

        result = upload_dataset(sf_instance, sf_token, slug, slug.replace("_", " ").title(),
                                metadata, csv_bytes, operation="Overwrite",
                                app_name=app_id)
        job_id, dataset_id = result
        cp["crma_dataset_id"] = dataset_id
        cp["crma_dataset_name"] = slug
        progress(q, "crma", "Dataset uploaded", 60)

        # Create CRMA dashboard from golden template
        progress(q, "crma", "Building CRM Analytics dashboard from template...", 65)
        try:
            from crma_dashboard_builder import create_dashboard

            golden_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "crma_golden_template.json")
            with open(golden_path) as _gf:
                state = json.load(_gf)

            dims = story_config.get("dimensions", [])
            safe_dims = [_re.sub(r'[^a-zA-Z0-9_]', '_', d).strip('_').lower() for d in dims]
            metric_fields = [mc["field"] for mc in metric_config]

            # Substitute dataset references (safe — IDs and names are unique)
            state_str = json.dumps(state)
            state_str = state_str.replace("biw_incentive", slug)
            state_str = state_str.replace("0Fbfj0000010m0rCAA", dataset_id)
            state_str = state_str.replace("BI Worldwide Sales Incentive", f"{company} Analytics")
            state = json.loads(state_str)

            # Map golden template fields to this demo's fields
            field_map = {}
            if len(metric_fields) >= 1: field_map["participation_rate"] = metric_fields[0]
            if len(metric_fields) >= 2: field_map["goal_achievement_rate"] = metric_fields[1]
            if len(safe_dims) >= 1: field_map["vertical"] = safe_dims[0]
            if len(safe_dims) >= 2: field_map["program_type"] = safe_dims[1]
            if len(safe_dims) >= 3: field_map["client_name"] = safe_dims[2]
            elif len(safe_dims) >= 1: field_map["client_name"] = safe_dims[0]

            # Substitute field names in SAQL queries (both quoted and unquoted forms)
            for step in state.get("steps", {}).values():
                q_obj = step.get("query", {})
                if isinstance(q_obj, dict) and "query" in q_obj:
                    q_str = q_obj["query"]
                    for old_f, new_f in field_map.items():
                        q_str = q_str.replace(f'"{old_f}"', f'"{new_f}"')
                        q_str = q_str.replace(old_f, new_f)
                    q_obj["query"] = q_str
                # Also substitute in selectMode/groups for compact JSON queries
                for ds in step.get("datasets", []):
                    ds_name = ds.get("name", "")
                    if ds_name:
                        ds["name"] = slug

            # Substitute KPI widget title labels
            old_labels = ["Participation", "Goal Achievement", "Redemption", "Active Reps", "Points per Rep"]
            for wname, w in state.get("widgets", {}).items():
                params = w.get("parameters", {})
                title = params.get("title", {})
                if isinstance(title, dict) and "label" in title:
                    for i, mc in enumerate(metric_config[:5]):
                        if i < len(old_labels) and old_labels[i] in str(title.get("label", "")):
                            title["label"] = title["label"].replace(old_labels[i], mc["label"])
                # Substitute number widget step references
                if w.get("type") == "number" and "step" in params:
                    step_ref = params["step"]
                    if isinstance(step_ref, str):
                        for old_f, new_f in field_map.items():
                            step_ref = step_ref.replace(old_f, new_f)
                        params["step"] = step_ref

            # Decode HTML entities in SAQL queries
            import html as _html_mod
            for step in state.get("steps", {}).values():
                q_obj = step.get("query", {})
                if isinstance(q_obj, dict) and "query" in q_obj:
                    q_obj["query"] = _html_mod.unescape(q_obj["query"])

            # Strip read-only fields the Wave API rejects on POST
            for step in state.get("steps", {}).values():
                step.pop("label", None)
                step.pop("isGlobal", None)
                step.pop("broadcastFacet", None)
                for ds in step.get("datasets", []):
                    ds.pop("url", None)
                    ds.pop("label", None)
            # Strip page labels in gridLayouts
            for gl in state.get("gridLayouts", []):
                for page in gl.get("pages", []):
                    page.pop("label", None)

            dash_id = create_dashboard(
                sf_instance=sf_instance,
                sf_token=sf_token,
                dashboard_label=f"{company} — Analytics Dashboard",
                state=state,
                app_id=app_id,
                description=f"CRM Analytics dashboard for {company} demo",
            )
            if dash_id:
                cp["crma_dashboard_id"] = dash_id
                progress(q, "crma", f"CRMA dashboard created: {dash_id}", 80)
            else:
                progress(q, "warn", "CRMA dashboard creation returned no ID", -1)
        except Exception as e:
            progress(q, "warn", f"CRMA dashboard failed (non-blocking): {e}", -1)

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
    global _build_log_file
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

        _build_log_file = os.path.join(demo_dir, f"{slug}_build.log")
        with open(_build_log_file, "w") as f:
            f.write(f"=== AIO Build Log — {company} — {TODAY.isoformat()} ===\n")

        cp_path = os.path.join(demo_dir, f"{slug}_checkpoint.json")
        if os.path.exists(cp_path):
            with open(cp_path) as f:
                cp = json.load(f)
        else:
            cp = {"all_ws_apis": [], "all_sdm_apis": [], "all_viz_apis": [], "all_dash_apis": []}

        from connections import load_config, load_full_config, set_active_profile

        # Per-output profile keys — each output can use a different connection
        pulse_profile = build_config.get("pulse_profile_key") or build_config.get("profile_key")
        next_profile = build_config.get("next_profile_key") or build_config.get("profile_key")
        crma_profile = build_config.get("crma_profile_key") or build_config.get("profile_key")

        # Default config for non-output-specific operations (data gen, etc.)
        default_profile = next_profile or pulse_profile or crma_profile
        if default_profile:
            full = load_full_config()
            if default_profile in full.get("profiles", {}):
                set_active_profile(full, default_profile)
        config = load_config(default_profile)

        # Pre-load per-output configs (only if they differ from default)
        pulse_config = load_config(pulse_profile) if pulse_profile and pulse_profile != default_profile else config
        next_config = load_config(next_profile) if next_profile and next_profile != default_profile else config
        crma_config = load_config(crma_profile) if crma_profile and crma_profile != default_profile else config

        advanced = build_config.get("advanced", {})

        # Save story context to checkpoint for /close-loop and /studio interop
        if not cp.get("story"):
            primary = [mc for mc in metric_config if mc.get("is_primary")]
            dims = story_config.get("dimensions", [])
            cp["story"] = {
                "headline": story_config.get("story_summary", ""),
                "signal_description": story_config.get("signal_description", ""),
                "primary_metric": primary[0]["label"] if primary else (metric_config[0]["label"] if metric_config else ""),
                "dimensions": dims,
                "audience": story_config.get("audience", build_config.get("audience", "")),
                "root_cause": story_config.get("root_cause", ""),
                "entity_field": "entity_id",
            }
            cp["company"] = company
            cp["build_type"] = "next" if outputs.get("next") else "pulse" if outputs.get("pulse") else "csv"
            _save_cp(cp, slug, demo_dir)

        progress(q, "init", "Generating data...", 0)
        df = generate_data(story_config, q, advanced=advanced)

        if outputs.get("csv"):
            csv_build(build_id, df, slug, demo_dir, q)

        if outputs.get("pulse"):
            progress(q, "pulse", "Starting Pulse build...", 15)
            pulse_build(build_id, df, slug, company, pulse_config, metric_config, story_config, demo_dir, q, cp, build_config)

        if outputs.get("next"):
            progress(q, "next", "Starting Tableau Next build...", 10)
            next_build(build_id, df, slug, company, next_config, metric_config, story_config, demo_dir, q, cp, build_config)

        if outputs.get("crma"):
            progress(q, "crma", "Starting CRM Analytics build...", 10)
            crma_build(build_id, df, slug, company, crma_config, metric_config, story_config, demo_dir, q, cp)

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
