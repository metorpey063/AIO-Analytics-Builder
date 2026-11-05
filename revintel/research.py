"""Customer research for the Update Rev Intel page: prefill the Q&A answers from a name.

Runs web searches (the web UI's DuckDuckGo search, no key needed), then asks Claude to turn the
results plus what it knows into suggested answers: industry, audience, products and pricing,
regions and segments, and a story hypothesis aligned to the use case. Every suggestion carries a
reason and a confidence so the SE can check it. Read-only: no org, no demo folder, no config.
"""

import json
import os
import sys

from revintel import llm

PROBLEMS = ["Product churn on won renewals", "Full churn", "Contraction (seat cuts)", "Renewals slipping (timing)",
            "Low expansion / whitespace", "Forecast accuracy"]
REGIONS = ["NAMR", "EMEA", "APJ", "LTAM"]
SEGMENTS = ["Enterprise", "Mid-Market", "SMB", "Transactional"]

SYSTEM = f"""You research a B2B company so a Solutions Engineer can build a Salesforce Revenue Intelligence demo \
(Revenue Insights + Einstein Account Management) about that company's own sales and renewals business.

From the search results and your own knowledge, suggest answers for the SE's setup form. Rules:
- Ground everything in the company: its real product names and families, its pricing model and unit (users, \
seats, endpoints, devices), where it sells, which customer segments it serves.
- List prices: annual list price for one typical mid-size customer subscription, in USD. Public pricing is often \
missing; estimate from comparable products and mark confidence low.
- Products: 4–8 sellable products. Exactly one is core (what most customers buy first). If the use case involves \
renewals or churn, mark one add-on as dropped at renewal (the one most exposed to competition or consolidation). \
Mark a recently launched product as new if there is one.
- Story: a plausible hypothesis that fits the use case and the company's real market pressures — not a claim \
about real results. The worst segment and the counter-trend must be region + segment combinations from the \
regions and segments you pick. The leading indicator must move before the main problem.
- problems must come from: {json.dumps(PROBLEMS)}. regions from: {json.dumps(REGIONS)}. segments from: \
{json.dumps(SEGMENTS)}.
- audience is a role (e.g. "CRO, VP of Renewals, RevOps"), never a named person. Do not name the company's \
employees anywhere.
- Only fill use_case if the SE left it empty; otherwise return their text unchanged.
- Keep the form answers short; they go into single-line fields. worst and counter_trend are under 60 characters \
(e.g. "EMEA Mid-Market"), root_cause and leading_indicator are one sentence under 160 characters, and \
structure_notes is under 250 characters. Put the longer reasoning in "why"."""

CONTRACT = """Return exactly one JSON object inside a ```json fence, nothing else:
{"summary": "2–3 sentences on the company and its go-to-market",
 "industry": "...", "use_case": "...", "audience": "...",
 "products": [{"name": "...", "family": "...", "list_price": 40000, "unit": "users", "core": true, "dropped": false, "new": false}],
 "story": {"problems": [...], "worst": "...", "counter_trend": "...", "root_cause": "...", "leading_indicator": "..."},
 "team": {"regions": [...], "segments": [...], "structure_notes": "..."},
 "why": {"industry": "...", "products": "...", "pricing": "...", "regions": "...", "segments": "...", "story": "..."},
 "confidence": {"industry": "high|medium|low", "products": "...", "pricing": "...", "regions": "...", "segments": "...", "story": "..."},
 "sources": ["urls from the search results you relied on"]}"""


def _queries(customer, use_case):
    q = [f"{customer} products platform pricing plans",
         f"{customer} company overview customers employees headquarters regions",
         f"{customer} go-to-market enterprise mid-market SMB partners channel",
         f"{customer} annual report earnings net revenue retention churn competition"]
    if use_case:
        q.append(f"{customer} {use_case[:80]}")
    return q


def _search(queries, progress):
    sys.path.insert(0, os.path.join(llm.ROOT, "web-ui"))
    try:
        from researcher import _ddg_search
    except Exception:
        progress("Web search isn't available — using Claude's own knowledge of the company")
        return []
    hits, seen = [], set()
    for q in queries:
        progress(f"Searching: {q}")
        for h in _ddg_search(q, max_results=5):
            if h["url"] not in seen:
                seen.add(h["url"])
                hits.append(h)
    return hits


def run(answers, progress=print):
    """answers: the page's current answers (customer required). Returns suggested answers + why/confidence."""
    customer = (answers.get("customer") or "").strip()
    if not customer:
        raise SystemExit("Enter the customer name first.")
    hits = _search(_queries(customer, answers.get("use_case", "")), progress)
    progress(f"{len(hits)} search results — asking Claude to suggest the answers (about a minute)…")
    given = {k: answers.get(k) for k in ("customer", "industry", "use_case", "audience") if answers.get(k)}
    req = (answers.get("requirements") or "").strip()
    parts = ["## What the SE entered\n" + json.dumps(given, indent=1)]
    if req:
        parts.append("## The customer's requirements (BRD / discovery notes) — align the story to these\n" + req[:30000])
    parts.append("## Search results\n" + ("\n".join(f"- {h['title']} ({h['url']}): {h['snippet']}" for h in hits)
                                          or "(none — web search returned nothing; rely on what you know and lower confidence)"))
    parts.append(CONTRACT)
    out = llm.ask_json(SYSTEM, "\n\n".join(parts), effort="medium", max_tokens=16000)
    st, tm = out.get("story") or {}, out.get("team") or {}
    st["problems"] = [p for p in st.get("problems", []) if p in PROBLEMS]
    tm["regions"] = [r for r in tm.get("regions", []) if r in REGIONS]
    tm["segments"] = [s for s in tm.get("segments", []) if s in SEGMENTS]
    out["story"], out["team"] = st, tm
    out["searched"] = len(hits)
    return out
