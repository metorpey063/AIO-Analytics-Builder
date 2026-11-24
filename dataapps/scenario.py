"""Data apps from a description: Claude designs a data model for what the customer wants to see, AIO
generates event-level mock data with the problem engineered in, checks the signal, loads it (Data Cloud +
semantic model for Next, a published datasource for Cloud) and saves it as an AIO demo, so the data app
build runs on it like on any other demo.

The data is one fact table, one row per event (a haul cycle, a ticket, a shipment), in AIO's fact schema
(Record ID, Date, Day_Offset, Entity ID, text dimensions, numeric measures). Things with a place on a
site get X/Y positions (0-100 grid) as extra measures, so the app can draw a site map without joins.
"""

import json
import math
import os
import random
import sys
import time
from datetime import date, timedelta

from dataapps import common as C

MAX_ROWS = 60000
MAX_DESIGN_TRIES = 2
MAX_DRAWS = 3

DESIGN_SYSTEM = """You design the data model behind a data app for a Salesforce solution engineer's demo.
The SE describes what a customer wants to track. You return ONE JSON object (in a ```json fence) describing
a single event-level fact table and the operational problem the data should reveal. AIO generates the rows.

Shape:
{
 "title": "short app name (3-5 words)",
 "summary": "2-3 sentences: what the customer tracks and why",
 "headline": "the story the data tells: what is wrong, where it is worst, why, and what is improving",
 "root_cause": "one sentence",
 "entity": {"name": "Haul Truck", "prefix": "HT", "count": 24},
 "events": {"name": "Haul Cycle", "per_day": 140, "days": 365},
 "dimensions": [
   {"name": "Truck Class", "values": ["CAT 777G", "CAT 785D"], "weights": [0.6, 0.4], "per_entity": true},
   {"name": "Loader", "values": ["Loader L1", "Loader L2", "Loader L3"]},
   {"name": "Mineral", "derived_from": "Loader", "map": {"Loader L1": "Silver", "Loader L2": "Silver", "Loader L3": "Gold"}},
   {"name": "Parking Spot", "values": ["P-01", "P-02", "..."]},
   {"name": "Parking Zone", "derived_from": "Parking Spot", "map": {"P-01": "Zone A", "...": "..."}},
   {"name": "Shift", "values": ["Day", "Night"], "weights": [0.55, 0.45]}
 ],
 "layout": {"Parking Spot": {"P-01": [12, 80], "...": [0, 0]}, "Loader": {"Loader L1": [70, 20], "...": [0, 0]}},
 "measures": [
   {"label": "Queue Wait (Min)", "unit": "min", "agg": "Average", "sentiment": "up_is_bad", "base_range": [3.5, 6.0],
    "distance": {"from": "Parking Spot", "to": "Loader", "per_unit": 0.08},
    "description": "Minutes a truck waits at the loader before loading", "why_it_matters": "...",
    "singular": "queue wait", "plural": "queue waits", "is_primary": true}
 ],
 "signal": {"measure": "Queue Wait (Min)", "culprit": {"dimension": "Parking Zone", "value": "Zone C"},
            "culprit_detail": {"dimension": "Mineral", "value": "Silver"}, "magnitude": 0.5,
            "onset_months_ago": 3, "counter_trend_metric": "Payload Per Cycle (Tonnes)"}
}

Rules:
- Real, specific values for the customer's operation (equipment models, site areas, products), never
  "Zone 1"/"Spot 1" style placeholders unless that is how the site names them (P-01 style IDs are fine for spots).
- 4-7 dimensions with 2-20 values each. `per_entity: true` = fixed per entity (a truck's class).
  `derived_from` + `map` = determined by another dimension (a loader serves one mineral; a spot sits in one zone);
  the map must cover every value of the source dimension.
- `layout` only when things have a physical place (spots, loaders, docks, bays). Coordinates on a 0-100 grid,
  laid out like the real site (spots grouped by zone, loaders near their pit). Omit `layout` otherwise.
- 4-7 measures. agg "Average" for times, rates, sizes; "Sum" for counts and volumes. sentiment "up_is_bad" or
  "up_is_good". base_range = realistic per-event values before the problem. Rates are decimals (0.82 not 82).
  `distance` (optional) adds per_unit x grid distance between the row's two layout positions: this is how
  parking far from the loader costs time. Exactly one measure has is_primary: true (the problem metric).
  With a layout, include a travel/transit time measure driven by distance (e.g. "Haul Transit (Min)", base
  [2.5, 4.5], distance per_unit 0.09 from the place to the equipment): the site map's route tooltips show it.
- signal: the culprit is a dimension value where the problem concentrates; culprit_detail narrows it further
  (a value of another dimension, the steepest cell); counter_trend_metric is a different measure that improves
  (it makes the overall picture look fine). magnitude 0.4-0.6. onset_months_ago 2-4. The culprit should also
  make physical sense with the layout (e.g. the zone farthest from its loader).
- events.days = 365 (a year: the signal check needs a baseline). events.per_day x events.days <= 60000.
"""


def _norm(s):
    return str(s).strip().lower()


def design_problems(sc):
    """Everything wrong with a designed scenario, or []."""
    from data_validator import validate_dimension_values
    p = []
    dims = sc.get("dimensions") or []
    names = [d.get("name") for d in dims]
    if not 3 <= len(dims) <= 8:
        p.append("need 3 to 8 dimensions")
    values = {}
    for d in dims:
        if d.get("derived_from"):
            src = d["derived_from"]
            if src not in names:
                p.append(f'{d["name"]}: derived_from "{src}" is not a dimension')
                continue
            src_vals = next((x.get("values") or [] for x in dims if x.get("name") == src), [])
            missing = [v for v in src_vals if v not in (d.get("map") or {})]
            if missing:
                p.append(f'{d["name"]}: map is missing {missing[:5]}')
            values[d["name"]] = sorted(set((d.get("map") or {}).values()))
        else:
            vals = d.get("values") or []
            if not 2 <= len(vals) <= 40:
                p.append(f'{d["name"]}: needs 2 to 40 values')
            w = d.get("weights")
            if w and (len(w) != len(vals) or min(w) < 0):
                p.append(f'{d["name"]}: weights must match the values')
            values[d["name"]] = list(vals)
    try:
        validate_dimension_values(values, names)
    except ValueError as e:
        p.append(str(e))
    for dim, coords in (sc.get("layout") or {}).items():
        if dim not in values:
            p.append(f'layout: "{dim}" is not a dimension')
            continue
        missing = [v for v in values[dim] if v not in coords]
        if missing:
            p.append(f'layout {dim}: no position for {missing[:5]}')
        if any(not (isinstance(xy, list) and len(xy) == 2 and all(0 <= float(c) <= 100 for c in xy)) for xy in coords.values()):
            p.append(f"layout {dim}: positions must be [x, y] between 0 and 100")
    ms = sc.get("measures") or []
    labels = [m.get("label") for m in ms]
    if not 3 <= len(ms) <= 8:
        p.append("need 3 to 8 measures")
    if len(set(labels)) != len(labels):
        p.append("measure labels must be unique")
    if sum(1 for m in ms if m.get("is_primary")) != 1:
        p.append("exactly one measure must have is_primary: true")
    for m in ms:
        br = m.get("base_range") or []
        if m.get("agg") not in ("Average", "Sum"):
            p.append(f'{m.get("label")}: agg must be "Average" or "Sum"')
        if m.get("sentiment") not in ("up_is_bad", "up_is_good"):
            p.append(f'{m.get("label")}: sentiment must be up_is_bad or up_is_good')
        if len(br) != 2 or not br[0] < br[1]:
            p.append(f'{m.get("label")}: base_range must be [low, high] with low < high')
        dist = m.get("distance")
        if dist and not (dist.get("from") in (sc.get("layout") or {}) and dist.get("to") in (sc.get("layout") or {})):
            p.append(f'{m.get("label")}: distance from/to must both be layout dimensions')
    sig = sc.get("signal") or {}
    if sig.get("measure") not in labels:
        p.append("signal.measure must be one of the measures")
    for key in ("culprit", "culprit_detail"):
        c = sig.get(key) or {}
        if c and c.get("value") not in values.get(c.get("dimension"), []):
            p.append(f'signal.{key}: "{c.get("value")}" is not a value of {c.get("dimension")}')
    if not sig.get("culprit"):
        p.append("signal.culprit is required")
    ct = sig.get("counter_trend_metric")
    if ct and (ct not in labels or ct == sig.get("measure")):
        p.append("signal.counter_trend_metric must be a different measure")
    ent, ev = sc.get("entity") or {}, sc.get("events") or {}
    if not 3 <= int(ent.get("count") or 0) <= 300:
        p.append("entity.count must be 3 to 300")
    rows = int(ev.get("per_day") or 0) * int(ev.get("days") or 0)
    if not 2000 <= rows <= MAX_ROWS:
        p.append(f"events.per_day x events.days must be 2,000 to {MAX_ROWS:,} (is {rows:,})")
    if int(ev.get("days") or 0) < 300:
        p.append("events.days must be at least 300 (the signal check needs a year of baseline)")
    return p


def design(company, description, slug):
    """Claude designs the scenario; AIO checks it and asks once for a fix."""
    user = f"Customer: {company}\n\nWhat the SE wants the data app to show:\n{description}"
    raw = os.path.join(C.app_dir(slug), "data_app_scenario_claude.txt")
    sc = C.ask_claude(DESIGN_SYSTEM, user, raw)
    for attempt in range(MAX_DESIGN_TRIES):
        problems = design_problems(sc)
        if not problems:
            sc["company"] = company
            sc["description"] = description
            return sc
        print(f"  the data model has {len(problems)} problem(s), asking Claude to fix them:", flush=True)
        for x in problems:
            print(f"   - {x}", flush=True)
        if attempt == MAX_DESIGN_TRIES - 1:
            break
        sc = C.ask_claude(DESIGN_SYSTEM, user + "\n\nYour design:\n```json\n" + json.dumps(sc) +
                          "\n```\nFix every one of these problems and return the whole corrected JSON:\n- " +
                          "\n- ".join(problems), raw)
    raise SystemExit("Claude's data model still has problems (listed above). Rephrase the description and try again.")


# ── Generate ─────────────────────────────────────────────────────────────────

def signal_ramp(d, today, onset, duration=3):
    """0 before the onset, then an accelerating rise to 1 over `duration` months (the AIO default shape)."""
    months = (d.year - today.year) * 12 + (d.month - today.month) + (d.day - today.day) / 30.0
    progress = (months + onset) / duration
    return max(0.0, min(1.0, progress)) ** 2


def configs(sc):
    """(metric_config, story_config, story) in the shapes the AIO builders and the data app engine read."""
    primary = next(m for m in sc["measures"] if m.get("is_primary"))
    order = [primary] + [m for m in sc["measures"] if m is not primary]
    metric_config = []
    for m in order:
        metric_config.append({
            "label": m["label"], "field": _field(m["label"]), "agg": m["agg"], "sentiment": m["sentiment"],
            "unit": m.get("unit", ""), "description": m.get("description", ""), "why_it_matters": m.get("why_it_matters", ""),
            "singular": m.get("singular", m["label"].lower()), "plural": m.get("plural", m["label"].lower()),
            "base_range": m["base_range"], "is_primary": m is primary,
            "pulse_agg": "AGGREGATION_AVERAGE" if m["agg"] == "Average" else "AGGREGATION_SUM"})
    for dim in (sc.get("layout") or {}):
        for axis in ("X", "Y"):
            metric_config.append({"label": f"{dim} {axis}", "field": _field(f"{dim} {axis}"), "agg": "Average",
                                  "sentiment": "up_is_good", "unit": "grid", "no_metric": True,
                                  "description": f"{axis} position of the {dim} on the site map (0-100 grid)",
                                  "why_it_matters": "Places the row on the site map", "base_range": [0, 100]})
    dims = [d["name"] for d in sc["dimensions"]]
    dim_values = {}
    for d in sc["dimensions"]:
        dim_values[d["name"]] = sorted(set(d["map"].values())) if d.get("derived_from") else list(d["values"])
    sig = sc["signal"]
    plan = {"culprit": sig["culprit"], "onset_months_ago": int(sig.get("onset_months_ago", 3))}
    if sig.get("culprit_detail"):
        plan["culprit_detail"] = sig["culprit_detail"]
    if sig.get("counter_trend_metric"):
        plan["counter_trend_metric"] = sig["counter_trend_metric"]
    story_config = {"company": sc["company"], "dimensions": dims, "dimension_values": dim_values,
                    "metric_config": metric_config, "signal_plan": plan, "root_cause": sc.get("root_cause", ""),
                    "story_summary": sc.get("summary", ""), "signal_description": sc.get("headline", ""),
                    "data_app_scenario": True}
    story = {"headline": sc.get("headline", ""), "signal_description": sc.get("summary", ""),
             "primary_metric": primary["label"], "dimensions": dims, "dimension_values": dim_values,
             "metric_config": metric_config}
    return metric_config, story_config, story


def _field(label):
    import re
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", label.lower())).strip("_")


def _pick(rng, values, weights=None):
    return rng.choices(values, weights=weights or None, k=1)[0]


def generate(sc, seed=7, today=None):
    """One draw of the event table as a DataFrame (AIO fact schema)."""
    import pandas as pd
    rng = random.Random(seed)
    today = today or date.today()
    ent, ev, sig = sc["entity"], sc["events"], sc["signal"]
    layout = sc.get("layout") or {}
    dims = sc["dimensions"]
    by_name = {d["name"]: d for d in dims}
    entities = [f"{ent.get('prefix', 'E')}-{i + 1:03d}" for i in range(int(ent["count"]))]
    fixed = {e: {d["name"]: _pick(rng, d["values"], d.get("weights")) for d in dims
                 if d.get("per_entity") and not d.get("derived_from")} for e in entities}
    ent_level = {e: rng.uniform(0.94, 1.06) for e in entities}
    primary, onset = sig["measure"], int(sig.get("onset_months_ago", 3))
    magnitude = float(sig.get("magnitude", 0.5))
    culprit, detail = sig["culprit"], sig.get("culprit_detail") or {}
    counter = sig.get("counter_trend_metric")
    rows = []
    for day in range(int(ev["days"]) - 1, -1, -1):
        d = today - timedelta(days=day)
        ramp = signal_ramp(d, today, onset)
        season = 1 + 0.03 * math.sin(2 * math.pi * d.timetuple().tm_yday / 365.0)
        n = max(1, int(rng.gauss(ev["per_day"], ev["per_day"] * 0.08)))
        for k in range(n):
            e = rng.choice(entities)
            row = {"Record ID": f"{e}_{d:%Y%m%d}_{k:04d}", "Date": d, "Day_Offset": (d - today).days, "Entity ID": e}
            for dd in dims:
                if dd.get("derived_from"):
                    continue
                row[dd["name"]] = fixed[e].get(dd["name"]) or _pick(rng, dd["values"], dd.get("weights"))
            for dd in dims:
                if dd.get("derived_from"):
                    row[dd["name"]] = dd["map"][row[dd["derived_from"]]]
            in_culprit = row.get(culprit["dimension"]) == culprit["value"]
            in_detail = in_culprit and detail and row.get(detail["dimension"]) == detail["value"]
            # The culprit carries the signal, its drill-down cell the most; everyone else barely moves
            mult = (1.6 if in_detail else 1.0) if in_culprit else 0.12
            for m in sc["measures"]:
                lo, hi = m["base_range"]
                v = (lo + (hi - lo) * rng.betavariate(2.2, 2.2)) * ent_level[e] * season
                dist = m.get("distance")
                if dist:
                    (x1, y1), (x2, y2) = layout[dist["from"]][row[dist["from"]]], layout[dist["to"]][row[dist["to"]]]
                    v += float(dist.get("per_unit", 0)) * math.hypot(x1 - x2, y1 - y2)
                worse = 1 if m["sentiment"] == "up_is_bad" else -1
                if m["label"] == primary:
                    v *= 1 + worse * magnitude * ramp * mult
                elif m["label"] == counter:
                    v *= 1 - worse * 0.25 * ramp       # improves while the problem grows
                else:
                    v *= 1 + worse * magnitude * 0.6 * signal_ramp(d, today, onset - 1) * mult * 0.7
                v += rng.gauss(0, abs(v) * 0.05)
                row[m["label"]] = round(max(v, 0.0), 4 if hi <= 1.5 else 2)
            for dim, coords in layout.items():
                row[f"{dim} X"], row[f"{dim} Y"] = coords[row[dim]]
            rows.append(row)
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def build_data(sc, slug):
    """Generate, verify the signal (redrawing a miss), and save the CSV. Returns (df, report text)."""
    from signal_verifier import verify_signal, format_report
    metric_config, story_config, _ = configs(sc)
    business = [m for m in metric_config if not m.get("no_metric")]
    best = None
    for draw in range(MAX_DRAWS):
        df = generate(sc, seed=7 + draw)
        rep = verify_signal(df, business, story_config["dimensions"], story_config["signal_plan"],
                            onset_months=story_config["signal_plan"]["onset_months_ago"])
        score = len(rep.get("failures", []))
        if best is None or score < best[0]:
            best = (score, df, rep)
        if rep.get("ok") or not rep.get("fixable_by_redraw", True):
            break
    _, df, rep = best
    df.to_csv(os.path.join(C.app_dir(slug), f"{slug}_data_app_data.csv"), index=False)
    return df, format_report(rep), rep.get("ok", False)


def summary_text(sc, df):
    """What the plan shows the SE before anything is loaded."""
    lines = [f"{sc.get('title')} — {sc.get('summary', '')}", f"Story: {sc.get('headline', '')}",
             f"{len(df):,} {sc['events']['name'].lower()} rows over {sc['events']['days']} days, "
             f"{sc['entity']['count']} {sc['entity']['name'].lower()}s"]
    for d in sc["dimensions"]:
        vals = sorted(set(d["map"].values())) if d.get("derived_from") else d["values"]
        lines.append(f"  Dimension {d['name']}: {', '.join(map(str, vals[:8]))}{' …' if len(vals) > 8 else ''}")
    for m in sc["measures"]:
        lines.append(f"  Measure {m['label']} ({m['agg']}, {'lower' if m['sentiment'] == 'up_is_bad' else 'higher'} is better)"
                     f"{' — the problem metric' if m.get('is_primary') else ''}")
    if sc.get("layout"):
        lines.append(f"  Site map: {', '.join(sc['layout'])} placed on the site")
    s = sc["signal"]
    lines.append(f"  Problem: {s['measure']} worst at {s['culprit']['dimension']} = {s['culprit']['value']}"
                 + (f", steepest for {s['culprit_detail']['dimension']} = {s['culprit_detail']['value']}" if s.get("culprit_detail") else "")
                 + (f"; {s['counter_trend_metric']} improves" if s.get("counter_trend_metric") else ""))
    return "\n".join(lines)


# ── Load (writes to the org / site) ──────────────────────────────────────────

class _Printer:
    """The progress channel the Web UI builders expect, printing to stdout instead."""
    log_file = None

    def put(self, item):
        if item.get("message"):
            print(f"  {item['message']}", flush=True)


def demo_checkpoint(slug):
    p = os.path.join(C.ROOT, "demos", slug, f"{slug}_checkpoint.json")
    return (json.load(open(p)) if os.path.exists(p) else {}), p


def load_next(sc, df, slug, profile):
    """Data Cloud stream + ingest + semantic model + metrics through the Tableau Next builder (no vizzes)."""
    sys.path.insert(0, os.path.join(C.ROOT, "web-ui"))
    import builder
    from connections import load_config
    metric_config, story_config, story = configs(sc)
    cp, _ = demo_checkpoint(slug)
    # New measures or dimensions mean a new schema: reload the data and rebuild the semantic model. The builder
    # deletes the old workspace and model it created, so the data app on them goes first (it is republished after)
    if cp.get("sdm_done") and cp.get("schema_fields_sig") != builder.schema_signature(story_config, metric_config):
        print("  the data model changed: reloading the data and rebuilding the semantic model", flush=True)
        app_cp = C.load_cp(slug, "next")
        if app_cp.get("app_name"):
            from dataapps import next as N
            org = N.org_for(profile)
            r = N.rest(org, "DELETE", f"v66.0/tableau/dashboards/{app_cp['app_name']}")
            print(f"  removed the data app {app_cp['app_name']} ({r.status_code}); it is rebuilt on the new model", flush=True)
            for k in ("app_id", "revision", "workspace", "workspace_id", "sdm", "url", "asset_id", "job_id"):
                app_cp.pop(k, None)
            C.save_cp(slug, "next", app_cp)
        for k in ("streams_done", "ingest_done", "sdm_done", "metrics_done", "sdm_enhanced", "schema_name",
                  "stream_name", "dlo_name", "ingest_job_id", "ingest_job_pending", "ingest_state", "csv_done"):
            cp.pop(k, None)
    cp.update({"_profile_key": profile, "_next_profile_key": profile, "company": sc["company"], "story": story,
               "story_config": story_config, "data_app_scenario": sc})
    for k in ("all_ws_apis", "all_sdm_apis", "all_viz_apis", "all_dash_apis"):
        cp.setdefault(k, [])
    demo_dir = C.app_dir(slug)
    builder._save_cp(cp, slug, demo_dir)
    config = load_config(profile, connection_type="salesforce")
    cp = builder.next_build(f"dataapp_{slug}", df, slug, sc["company"], config, metric_config, story_config, demo_dir,
                            _Printer(), cp, build_config={"data_only": True, "demo_name": sc.get("title") or sc["company"],
                                                          "dashboard_templates": ["none"]})
    cp["build_type"] = "data_app"
    builder._save_cp(cp, slug, demo_dir)
    if not cp.get("sdm_api"):
        raise SystemExit("The semantic model wasn't created (see the lines above).")
    return cp["sdm_api"], cp["ws_api"]


def load_cloud(sc, df, slug, profile):
    """A project + a self-healing published datasource (dates follow TODAY())."""
    import tableauserverclient as TSC
    from tdsx_builder import publish_hyper_for_indexing, convert_to_self_healing
    from dataapps.cloud import Site
    _, story_config, story = configs(sc)
    cp, path = demo_checkpoint(slug)
    site = Site(profile)
    try:
        name = f"{sc['company']} | {sc.get('title') or 'Data App'}"
        proj = next((p for p in TSC.Pager(site.server.projects) if p.name == name), None)
        if proj is None:
            proj = site.server.projects.create(TSC.ProjectItem(name=name, description="Created by AIO for a data app"))
            cp.setdefault("created_projects", []).append(proj.id)
        ds_name = f"{sc['company']} - {sc.get('title') or 'Data App'}"
        demo_dir = C.app_dir(slug)
        print("  publishing the datasource…", flush=True)
        ds_id = publish_hyper_for_indexing(df, "Date", ds_name, proj.id, site.server, demo_dir)
        convert_to_self_healing(df, "Date", ds_name, proj.id, site.server, demo_dir)
    finally:
        site.close()
    cp.update({"_profile_key": profile, "_pulse_profile_key": profile, "company": sc["company"], "story": story,
               "story_config": story_config, "data_app_scenario": sc, "build_type": "data_app",
               "pulse_datasource_id": ds_id, "pulse_datasource_name": ds_name, "pulse_project_id": proj.id,
               "pulse_project_name": name, "build_date": time.strftime("%Y-%m-%d %H:%M")})
    json.dump(cp, open(path, "w"), indent=2, default=str)
    return ds_id, proj.id


def plan_path(slug):
    return os.path.join(C.ROOT, "demos", slug, f"{slug}_data_app_scenario.json")


def describe(platform, profile, company, description, slug=None, plan_only=False, ask=""):
    """The whole flow. plan_only: design + generate + verify, no writes to the org or site."""
    slug = slug or C.slugify(f"{company} {description[:40]}")
    saved = json.load(open(plan_path(slug))) if os.path.exists(plan_path(slug)) else None
    if saved and saved.get("description") == description and saved.get("company") == company:
        sc = saved
        C.step("design", "using the saved data model")
    else:
        C.step("design", "Claude is designing the data model")
        sc = design(company, description, slug)
        json.dump(sc, open(plan_path(slug), "w"), indent=2)
    C.step("design", "done")
    C.step("data", "generating the data and checking the story landed")
    df, report, ok = build_data(sc, slug)
    print(summary_text(sc, df), flush=True)
    print("Signal check:\n" + report, flush=True)
    C.step("data", "done" if ok else "done (the signal check has warnings, see above)")
    print(f"\nPLAN {json.dumps({'slug': slug, 'title': sc.get('title'), 'rows': len(df), 'signal_ok': ok})}", flush=True)
    if plan_only:
        return slug
    C.step("load", "loading the data" + (" into Data Cloud" if platform == "next" else " to Tableau Cloud"))
    if platform == "next":
        source, dest = load_next(sc, df, slug, profile)
    else:
        source, dest = load_cloud(sc, df, slug, profile)
    C.step("load", "done")
    # The app takes the scenario's title, not the generic "{company} Data App"
    app_cp = C.load_cp(slug, platform)
    field = "title" if platform == "cloud" else "label"
    if not app_cp.get(field) or app_cp[field] == f"{company} Data App":   # a generic name gives way to the scenario's
        app_cp[field] = sc.get("title") or f"{company} Data App"
    C.save_cp(slug, platform, app_cp)
    engine = __import__(f"dataapps.{platform}", fromlist=["build"])
    brief = description + (f"\n\n{ask}" if ask else "")
    if sc.get("layout"):
        brief += ("\n\nThe data has site positions (" + ", ".join(f"{d} X / {d} Y" for d in sc["layout"]) +
                  "): include a site map section.")
    engine.build(profile, source, dest, slug=slug, ask=brief)
    return slug
