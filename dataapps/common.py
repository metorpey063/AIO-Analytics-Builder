"""Shared pieces of the data app engines: checkpoints, AIO demo lookup, the story brief, Claude calls.

A data app lives in demos/{slug}/ with a checkpoint {slug}_data_app_{platform}.json. When the source is
an AIO demo, slug is that demo's folder, so the app sits next to the demo it was built from.
"""

import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PLATFORMS = ("next", "cloud")


def step(name, detail=""):
    """Progress line the Web UI turns into step badges: `[step] detail`, then `[step] done`."""
    print(f"[{name}] {detail}".rstrip(), flush=True)


def slugify(text, max_len=48):
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s[:max_len].strip("_") or "data_app"


def app_dir(slug):
    d = os.path.join(ROOT, "demos", slug)
    os.makedirs(d, exist_ok=True)
    return d


def cp_path(slug, platform):
    return os.path.join(ROOT, "demos", slug, f"{slug}_data_app_{platform}.json")


def load_cp(slug, platform):
    p = cp_path(slug, platform)
    return json.load(open(p)) if os.path.exists(p) else {}


def save_cp(slug, platform, cp):
    app_dir(slug)
    json.dump(cp, open(cp_path(slug, platform), "w"), indent=2)


def demo_checkpoints():
    """(slug, checkpoint) for every AIO demo build (not transfers or data apps)."""
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "demos", "*", "*_checkpoint.json"))):
        slug = os.path.basename(os.path.dirname(p))
        if os.path.basename(p) != f"{slug}_checkpoint.json":
            continue
        try:
            out.append((slug, json.load(open(p))))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def aio_demos(platform, profile):
    """AIO demos built on this connection: Next ones carry an SDM, Cloud ones a Pulse datasource."""
    demos = []
    for slug, cp in demo_checkpoints():
        company = cp.get("company") or (cp.get("story_config") or {}).get("company") or slug
        if platform == "next":
            key = cp.get("_next_profile_key") or cp.get("_profile_key")
            if cp.get("sdm_api") and key == profile:
                demos.append({"slug": slug, "company": company, "source": cp["sdm_api"],
                              "workspace": cp.get("ws_api", ""), "built": cp.get("build_date", "")})
        else:
            key = cp.get("_pulse_profile_key") or cp.get("_profile_key")
            if cp.get("pulse_datasource_id") and key == profile:
                demos.append({"slug": slug, "company": company, "source": cp["pulse_datasource_id"],
                              "source_name": cp.get("pulse_datasource_name", ""),
                              "project": cp.get("pulse_project_id", ""), "built": cp.get("build_date", "")})
    return sorted(demos, key=lambda d: d["built"], reverse=True)


def existing_apps(platform, profile):
    """Data apps already built on this connection (from their checkpoints), newest first."""
    apps = []
    for p in glob.glob(os.path.join(ROOT, "demos", "*", f"*_data_app_{platform}.json")):
        slug = os.path.basename(os.path.dirname(p))
        if os.path.basename(p) != f"{slug}_data_app_{platform}.json":
            continue
        try:
            cp = json.load(open(p))
        except (OSError, json.JSONDecodeError):
            continue
        if cp.get("profile") != profile or not cp.get("url"):
            continue
        apps.append({"slug": slug, "title": cp.get("label") or cp.get("title") or slug,
                     "source": cp.get("sdm") if platform == "next" else cp.get("datasource_id"),
                     "source_name": cp.get("sdm") if platform == "next" else cp.get("datasource", ""),
                     "published": cp.get("published", "")})
    return sorted(apps, key=lambda a: a["published"], reverse=True)


def demo_for_source(platform, source):
    """The AIO demo whose SDM / Pulse datasource is this source, if any: (slug, checkpoint)."""
    field = "sdm_api" if platform == "next" else "pulse_datasource_id"
    for slug, cp in demo_checkpoints():
        if cp.get(field) == source:
            return slug, cp
    return None, None


def story_brief(cp):
    """The demo's story as plain text for Claude: what's wrong, where, why, the counter-trend, the metrics."""
    if not cp:
        return ""
    story = cp.get("story") or {}
    sc = cp.get("story_config") or {}
    lines = [f"Company: {cp.get('company') or sc.get('company', '')}"]
    for key, label in (("headline", "Story"), ("signal_description", "Signal")):
        if story.get(key):
            lines.append(f"{label}: {story[key]}")
    if sc.get("root_cause"):
        lines.append(f"Root cause: {sc['root_cause']}")
    plan = sc.get("signal_plan") or {}
    if plan.get("culprit"):
        lines.append(f"Culprit segment: {plan['culprit'].get('dimension')} = {plan['culprit'].get('value')}")
    if plan.get("culprit_detail"):
        d = plan["culprit_detail"]
        lines.append(f"Drill-down within the culprit: {d.get('dimension')} = {d.get('value')}")
    if plan.get("counter_trend_metric"):
        lines.append(f"Counter-trend metric (improves while the rest decline): {plan['counter_trend_metric']}")
    if plan.get("onset_months_ago"):
        lines.append(f"Signal started about {plan['onset_months_ago']} months ago")
    for m in sc.get("metric_config") or story.get("metric_config") or []:
        better = "lower is better" if m.get("sentiment") == "up_is_bad" else "higher is better"
        unit = m.get("unit") or ("percent" if m.get("number_format") == "Percentage" else "")
        lines.append(f"Metric: {m.get('label')} ({m.get('agg', '')}, {better}{', ' + unit if unit else ''})"
                     f"{': ' + m['description'] if m.get('description') else ''}")
    return "\n".join(lines)


def metric_hints(cp):
    """label -> {agg, unit, sentiment} from the demo's METRIC_CONFIG (used to pick aggregations)."""
    sc = (cp or {}).get("story_config") or {}
    out = {}
    for m in sc.get("metric_config") or (cp or {}).get("story", {}).get("metric_config") or []:
        out[m.get("label", "")] = {"agg": (m.get("agg") or "").lower(), "unit": m.get("unit", ""),
                                   "sentiment": m.get("sentiment", "")}
    return out


def ask_claude(system, user, raw_path):
    """Claude writes the app as JSON. Same credentials and model as Rev Intel drafting (the strongest
    model: the page has to build and run on the first publish)."""
    from revintel import llm
    return llm.ask_json(system, user, raw_path=raw_path, effort="high", max_tokens=48000)


def quick_claude(system, user, max_tokens=2000):
    """A short, fast Claude reply (the Web UI chat's model): classifying and answering chat messages."""
    from revintel import llm
    from claude_model import pick
    return llm.call(system, user, effort="low", max_tokens=max_tokens, model=pick("chat")).strip()


def push_history(cp, keep=10):
    """Keep the app being replaced, so a revise can be undone."""
    if cp.get("app"):
        cp.setdefault("history", []).append({"app": cp["app"], "at": cp.get("published", ""),
                                             "revision": cp.get("revision"), "title": cp.get("title") or cp.get("label")})
        cp["history"] = cp["history"][-keep:]


def read_asset(name):
    return open(os.path.join(ASSETS, name), encoding="utf-8").read()


def rows_preview(rows, limit=24):
    """A probe result as compact text for the prompt."""
    if not rows:
        return "(no rows)"
    shown = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in rows[:limit]]
    out = json.dumps(shown, default=str)
    if len(rows) > limit:
        out += f" … ({len(rows)} rows)"
    return out
