"""Draft a customer config with Claude: `python3 -m revintel <demo> draft [--feedback "…"]`.

Inputs: the web UI's Q&A answers (rev_intel_request.json), the org facts from `inspect`
(out/inspect.json), the config template, and the KnowBe4 config as a worked example.
Outputs: config.json, pool_seed.json, loss_reasons.json and out/draft_notes.json (assumptions
and open questions). The draft is validated by running `plan`; on failure Claude gets the
errors and one repair attempt. With --feedback, the current config is revised instead.

Claude calls and credentials are in revintel/llm.py.
"""

import json
import os
import subprocess
import sys
from datetime import date

from revintel import llm
from revintel.config import DEMO_DIR, OUT
from revintel.llm import ROOT

SYSTEM = """You design demo data for Salesforce Revenue Intelligence (Revenue Insights + Einstein Account \
Management) so a Solutions Engineer can show one customer a story about their own business.

You write the customer config that a deterministic generator turns into ~2 years of accounts, opportunities, \
renewals, line items, contacts, activities, team, territories and quotas. You do not generate records yourself.

Design rules (from the AIO demo principles):
- Align everything to the customer and use case: their real products and pricing model, their segments and \
regions, their renewal motion, the problem in their requirements. Every product, segment, stage, field and story \
beat should trace back to the answers or the requirements text.
- The story must be drillable: one or two culprit segments (mult 1.5–2.5), moderate segments (~1), one flat \
(~0.3), one counter-trend (-0.05 to -0.15, never lower). Product drops lead full churn (leading indicator). \
Stretch factors make the culprit's reps fall behind quota and the counter-trend's reps beat it.
- Revenue Insights shows the forecast managers of the sales leader's child roles: give the leader the number \
of leads the answers ask for (7–9 reads best), one LEAD_ROLES entry each, using SUB_ROLES for one drill level.
- Use only User Ids that appear in the org facts. People who don't exist become NEW_USERS with fictional \
names — never real employees of the customer.
- Use only record type Ids, stage values, territory Ids, price book Ids and account Ids from the org facts. A \
product that matches an existing price book entry by name reuses its `pbe`; otherwise omit `pbe` and set \
`name`, `family`, `code`, `list` so the products step creates it.
- Pool accounts come from org_facts.pool_unused (never from pool_tagged unless the answers say to reuse a \
pool); re-skin each with a realistic name, country, state and city for its region. Use a customer-specific \
POOL_PREFIX ("AIO-POOL-<SHORT>") and EXT_PREFIX ("AIO-<SHORT>").
- Set FIELDS entries to null for story fields the org doesn't have (see story_fields)."""

CONTRACT = """Return exactly one JSON object inside a ```json fence, with these keys:
- "config": every key from the template, as JSON (tuples become lists; TERRITORIES values are \
[territory Id or null to create, parent developer name or null, forecast manager USERS key]; LEAD_ROLES \
entries are [role name, developer name, existing developer name to reuse or null, lead key]; SUB_ROLES \
entries are [role name, developer name, parent lead key, [member keys]]; NEW_USERS entries are \
[key, first, last, title, time zone]).
- "pool_seed": [{"id", "segment", "type", "name", "country", "state", "city", "industry", "orig_name"}] — \
type is Enterprise, Mid-Market or Small Business; segment is a SEGMENTS key.
- "notes": short strings — assumptions you made and why.
- "questions": short strings — anything the SE should confirm (empty list if none).
No text outside the fence."""


TEAM_REUSE = """## Keep the team already built in this org
The config below is the demo already loaded in this org; its team is what the SE demos. By default this \
demo only swaps the data, so:
- USERS: the old demo's USERS plus every entry of its new_users.json (key → Id): those people already exist, \
so NEW_USERS is empty.
- Copy unchanged: SALES_LEADER, SALES_LEADER_ROLE, CEO, CEO_ROLE, CEO_QUOTA, MANAGERS, LEADS, \
SUB_ROLES, EXTRA_TEAM, OWNER_SPLITS, TERRITORIES (same Ids, parents and forecast managers), TERRITORY_USERS, \
TERRITORY_MODEL, TERRITORY_TYPE, TERRITORY_FORECAST_TYPE, ROLE_FORECAST_TYPES, ROLES_UNDER_CEO, \
OTHER_QUOTA_OWNERS, OTHER_DEMO_OWNER, REFRESH_APPS. TERRITORY_USERS_REMOVE is empty.
- LEAD_ROLES: same leads in the same roles, each reusing its existing developer name. You may rename a role \
to fit the new customer (e.g. "EMEA Enterprise Renewals" → "Canada Enterprise Renewals"); the record is kept.
- SEGMENTS: keep every key, owner and territory, so each person keeps their seat and the click path stays the \
same. Change what each segment means for the new customer (its label, region wording, accounts and products) \
and its story multiplier and stretch, so the culprit and counter-trend fit the new story.
- Reuse the same pool accounts (org_facts.pool_tagged, the old demo's pool seed) and POOL_PREFIX, re-skinned \
for the new customer. Use a new customer-specific EXT_PREFIX.
- Only add, remove or restructure people, roles or territories when the SE's answers or requested changes \
explicitly ask for it. This overrides the pool_unused and NEW_USERS rules above."""


def _base_team(org_alias):
    """The most recently loaded other demo in the same org: (folder name, config text, pool seed text)."""
    import glob
    best = None
    for d in glob.glob(os.path.join(ROOT, "demos", "*")):
        if os.path.abspath(d) == os.path.abspath(DEMO_DIR):
            continue
        cp = os.path.join(d, "out", "checkpoint.json")
        if not os.path.exists(cp) or "opportunities" not in json.load(open(cp)).get("done", []):
            continue
        cfgs = [p for p in (os.path.join(d, "config.json"), os.path.join(d, "config.py")) if os.path.exists(p)] \
            or sorted(glob.glob(os.path.join(d, "*_config.py")))
        if not cfgs:
            continue
        text = open(cfgs[0]).read()
        if org_alias not in text:
            continue
        if not best or os.path.getmtime(cp) > best[0]:
            extra = "".join(f"\n\nIts {os.path.basename(f)}:\n{open(f).read()}"
                            for f in sorted(glob.glob(os.path.join(d, "*pool*seed*.json")))
                            + [os.path.join(d, "new_users.json")] if os.path.exists(f))
            best = (os.path.getmtime(cp), os.path.basename(d), text, extra)
    return best[1:] if best else None


def _ask_json(system, user):
    return llm.ask_json(system, user, raw_path=os.path.join(OUT, "draft_raw.txt"))


def _validate():
    r = subprocess.run([sys.executable, "-m", "revintel", DEMO_DIR, "plan"], cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def _facts():
    report = json.load(open(os.path.join(OUT, "inspect.json")))
    keep = ("org", "apps", "refresh_chain", "opportunity_stages", "story_fields", "forecast_types", "team",
            "scheduled_apex", "warnings", "org_facts", "pricebooks")
    return {k: report.get(k) for k in keep}


def _write(result):
    cfg = result["config"]
    cfg["_status"] = f"drafted by Claude {date.today().isoformat()} — review in the UI before loading"
    json.dump(cfg, open(os.path.join(DEMO_DIR, "config.json"), "w"), indent=1)
    json.dump(result.get("pool_seed", []), open(os.path.join(DEMO_DIR, "pool_seed.json"), "w"), indent=1)
    lr = ((_facts().get("org_facts") or {}).get("loss_reasons") or {}).get("map")
    if lr:
        json.dump(lr, open(os.path.join(DEMO_DIR, "loss_reasons.json"), "w"), indent=1)
    os.makedirs(OUT, exist_ok=True)
    json.dump({"notes": result.get("notes", []), "questions": result.get("questions", []),
               "drafted": date.today().isoformat()}, open(os.path.join(OUT, "draft_notes.json"), "w"), indent=1)


def run(feedback=None):
    import glob
    if os.path.exists(os.path.join(DEMO_DIR, "config.py")) or glob.glob(os.path.join(DEMO_DIR, "*_config.py")):
        raise SystemExit("This demo uses a hand-written Python config — edit it directly (draft only writes config.json).")
    req_path = os.path.join(DEMO_DIR, "rev_intel_request.json")
    if not os.path.exists(req_path):
        raise SystemExit("No answers yet — fill in the Update Rev Intel page and save first.")
    if not os.path.exists(os.path.join(OUT, "inspect.json")):
        raise SystemExit("Run Inspect first — the draft needs the org facts.")
    answers = json.load(open(req_path))
    template = open(os.path.join(ROOT, "revintel", "config_template.py")).read()
    example = open(os.path.join(ROOT, "demos", "knowbe4_renewals", "kb4_config.py")).read() \
        if os.path.exists(os.path.join(ROOT, "demos", "knowbe4_renewals", "kb4_config.py")) else "(not available)"
    today = date.today()
    qy, qm = (today.year - 1, today.month - 1) if today.month > 1 else (today.year - 2, 12)
    parts = [f"Today is {today.isoformat()}. Use QUOTA_START [{qy}, {qm}] and QUOTA_COUNT 18 unless the answers say otherwise.",
             "## The SE's answers\n" + json.dumps(answers, indent=1),
             "## Org facts (from inspect)\n" + json.dumps(_facts(), indent=1, default=str),
             "## Config template (keys and meaning)\n" + template,
             "## Worked example: the KnowBe4 config (Python; your output is the JSON equivalent)\n" + example]
    base = _base_team(answers.get("org_alias", "")) if answers.get("team_mode", "reuse") == "reuse" else None
    if base:
        name, text, seed = base
        parts.append(f"{TEAM_REUSE}\n\nDemo already in this org: demos/{name}\n{text}{seed}")
        print(f"  keeping the team from demos/{name} (already loaded in this org)", flush=True)
    current = os.path.join(DEMO_DIR, "config.json")
    if feedback and os.path.exists(current):
        parts.append("## Current config (revise this — keep everything the feedback doesn't touch)\n" + open(current).read())
        seed = os.path.join(DEMO_DIR, "pool_seed.json")
        if os.path.exists(seed):
            parts.append("## Current pool_seed\n" + open(seed).read())
        parts.append("## The SE's requested changes\n" + feedback)
    parts.append(CONTRACT)
    print("→ asking Claude to draft the config (this can take a few minutes)…", flush=True)
    result = _ask_json(SYSTEM, "\n\n".join(parts))
    _write(result)
    ok, out = _validate()
    if not ok:
        print("  draft didn't validate — asking Claude to fix it…", flush=True)
        fix = "\n\n".join(parts[:-1] + ["## Your previous draft\n" + json.dumps(result)[:200000],
                                        "## Validation errors from `plan`\n" + out,
                                        "Fix the draft so it validates. " + CONTRACT])
        result = _ask_json(SYSTEM, fix)
        _write(result)
        ok, out = _validate()
    if not ok:
        raise SystemExit("The draft still doesn't validate:\n" + out)
    print("✓ config.json, pool_seed.json drafted and validated (plan ran)", flush=True)
    for n in result.get("notes", []):
        print("  note:", n)
    for q in result.get("questions", []):
        print("  question:", q)
