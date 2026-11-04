"""Draft a customer config with Claude: `python3 -m revintel <demo> draft [--feedback "…"]`.

Inputs: the web UI's Q&A answers (rev_intel_request.json), the org facts from `inspect`
(out/inspect.json), the config template, and the KnowBe4 config as a worked example.
Outputs: config.json, pool_seed.json, loss_reasons.json and out/draft_notes.json (assumptions
and open questions). The draft is validated by running `plan`; on failure Claude gets the
errors and one repair attempt. With --feedback, the current config is revised instead.

Credentials, in the web UI's order: Bedrock gateway (ANTHROPIC_BEDROCK_BASE_URL +
ANTHROPIC_AUTH_TOKEN, or config.json "bedrock"), then an Anthropic API key or OAuth token
(ANTHROPIC_API_KEY or config.json "anthropic.api_key").
"""

import json
import os
import re
import subprocess
import sys
from datetime import date

from revintel.config import C, DEMO_DIR, OUT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = "claude-opus-5-5"
GATEWAY_MODEL = "us.anthropic.claude-opus-5-5"   # Bedrock gateway model ID for the same model

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


def _credentials():
    try:
        aio = json.load(open(os.path.join(ROOT, "config.json")))
    except (OSError, json.JSONDecodeError):
        aio = {}
    url = os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") or (aio.get("bedrock") or {}).get("base_url")
    tok = os.environ.get("ANTHROPIC_AUTH_TOKEN") if os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") \
        else (aio.get("bedrock") or {}).get("auth_token")
    if url and tok:
        return {"mode": "gateway", "base_url": url.rstrip("/"), "token": tok,
                "ca_bundle": os.environ.get("NODE_EXTRA_CA_CERTS") or (aio.get("bedrock") or {}).get("ca_bundle") or True}
    key = os.environ.get("ANTHROPIC_API_KEY") or (aio.get("anthropic") or {}).get("api_key")
    if key:
        return {"mode": "sdk", "key": key}
    raise SystemExit("No Claude credentials: set ANTHROPIC_API_KEY, add an Anthropic key in Setup, "
                     "or run inside a Claude Code session with the Bedrock gateway.")


def _call(system, user):
    """One Claude call; returns the response text."""
    cred = _credentials()
    if cred["mode"] == "gateway":
        # The internal Bedrock gateway speaks Bedrock's /invoke format with an x-api-key header, which the
        # SDK's Bedrock client (SigV4) can't send — same raw call the web UI's chat uses for this gateway.
        import requests
        r = requests.post(f"{cred['base_url']}/model/{GATEWAY_MODEL}/invoke",
                          headers={"x-api-key": cred["token"], "Content-Type": "application/json"},
                          json={"anthropic_version": "bedrock-2023-05-31", "max_tokens": 64000,
                                "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"},
                                "system": system, "messages": [{"role": "user", "content": user}]},
                          verify=cred["ca_bundle"], timeout=900)
        if r.status_code != 200:
            raise SystemExit(f"Claude call failed ({r.status_code}): {r.text[:500]}")
        body = r.json()
        if body.get("stop_reason") == "refusal":
            raise SystemExit("Claude declined this request — rephrase the answers and try again.")
        if body.get("stop_reason") == "max_tokens":
            raise SystemExit("Claude's draft was cut off (max tokens) — simplify the request and try again.")
        return "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")

    import anthropic
    key = cred["key"]
    client = anthropic.Anthropic(auth_token=key) if key.startswith("sk-ant-oat") else anthropic.Anthropic(api_key=key)
    try:
        # server-side refusal fallback: a declined request is retried on a fallback model inside the same call
        with client.beta.messages.stream(model=MODEL, max_tokens=64000, thinking={"type": "adaptive"},
                                         output_config={"effort": "high"}, system=system,
                                         messages=[{"role": "user", "content": user}],
                                         betas=["server-side-fallback-2026-07-01"], fallbacks="default") as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise SystemExit("Claude rejected the credentials — check the Anthropic key in Setup.")
    except anthropic.RateLimitError:
        raise SystemExit("Claude rate limit — wait a minute and draft again.")
    except anthropic.APIStatusError as e:
        raise SystemExit(f"Claude API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise SystemExit("Couldn't reach the Claude API — check the network.")
    if msg.stop_reason == "refusal":
        raise SystemExit("Claude declined this request — rephrase the answers and try again.")
    if msg.stop_reason == "max_tokens":
        raise SystemExit("Claude's draft was cut off (max tokens) — simplify the request and try again.")
    return "".join(b.text for b in msg.content if b.type == "text")


def _extract(text):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "draft_raw.txt"), "w").write(text)
    m = re.search(r"```json\s*(\{.*\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    return m.group(1)


def _ask_json(system, user):
    """Call Claude and parse its JSON; on a syntax error, send back the error and the broken JSON once."""
    raw = _extract(_call(system, user))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  reply wasn't valid JSON ({e.msg} at line {e.lineno}) — asking Claude to correct it…", flush=True)
        snippet = raw[max(0, e.pos - 300): e.pos + 300]
        fix = (f"This JSON failed to parse: {e.msg} at line {e.lineno} column {e.colno}.\n"
               f"Context around the error:\n{snippet}\n\nReturn the complete corrected JSON object, same content, "
               f"inside a ```json fence and nothing else.\n\n```json\n{raw}\n```")
        raw = _extract(_call("You fix JSON syntax without changing content.", fix))
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e2:
            raise SystemExit(f"Claude's draft still isn't valid JSON ({e2.msg} at line {e2.lineno}); raw reply in "
                             f"out/draft_raw.txt — try drafting again.")


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
