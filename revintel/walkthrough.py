"""Demo walkthrough for a Rev Intel build: `python3 -m revintel <demo> walkthrough`.

Writes {slug}_demo_walkthrough.html in the demo folder: a dashboard click path for Revenue Insights and
Einstein Account Management (which team to open, which deal and account to show, what the audience sees),
with the accounts and numbers picked from this build's plan. Same shape as the KnowBe4 click path
(demos/knowbe4_renewals/KB4_DEMO_CLICK_PATH.md). Deterministic: no Claude call. `plan` regenerates it.
"""

import collections
import html
import json
import os
import re
from datetime import date

from revintel.config import C, DEMO_DIR, OUT, opt

e = html.escape
STAGE_CATEGORY = {"Closed Won": "Closed", "Closed Lost": "Omitted", "Confirmed Renewal": "Commit",
                  "Negotiations": "Commit", "Proposal": "Commit", "Initial Renewal Discovery": "BestCase",
                  "Needs Analysis": "BestCase", "At Risk (Timing)": "Pipeline", "At Risk (Contraction)": "Pipeline",
                  "At Risk (Full Churn)": "Pipeline", "Created": "Pipeline", "Targeting": "Pipeline"}

CSS = """:root{--bg:#fff;--text:#1a1a2e;--muted:#555;--accent:#1565c0;--border:#e0e0e0;--card-bg:#fafafa;--warn:#b26b00}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;--border:#30363d;--card-bg:#161b22;--warn:#e3b341}}
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:860px;margin:0 auto;padding:24px 20px;background:var(--bg);color:var(--text);line-height:1.65}
h1{font-size:1.6em;margin:2em 0 0.5em;padding-bottom:8px;border-bottom:2px solid var(--accent);color:var(--accent)}
h1:first-of-type{margin-top:0.5em}h2{font-size:1.15em;margin:1.5em 0 0.4em}p{margin:0.5em 0}
.subtitle{color:var(--muted);font-size:0.92em}.step{background:var(--card-bg);border:1px solid var(--border);border-radius:8px;padding:14px 18px;margin:12px 0}
.step h2{margin:0 0 8px;font-size:1.05em}.warn{color:var(--warn)}ul{padding-left:1.4em}li{margin:4px 0}
table{border-collapse:collapse;width:100%;font-size:0.9em;margin:8px 0}th,td{border-bottom:1px solid var(--border);padding:6px 8px;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600}.tag{font-weight:600}.culprit{color:#c23934}.counter{color:#2e844a}.flat{color:var(--muted)}
@media print{body{max-width:100%}h1{break-before:page}h1:first-of-type{break-before:avoid}.step{break-inside:avoid}}"""


def money(v):
    v = float(v or 0)
    return f"${v / 1e6:.2f}M" if abs(v) >= 1e6 else f"${v / 1e3:.0f}K" if abs(v) >= 1e3 else f"${v:,.0f}"


def plural(n, word="deal"):
    return f"{n} {word}" + ("" if n == 1 else "s")


def _load(name, default):
    p = name if os.path.isabs(name) else os.path.join(DEMO_DIR, name)
    return json.load(open(p)) if os.path.exists(p) else default


def _stage_categories():
    """The org's stage → forecast category mapping (read-only); the usual defaults if the org can't be read."""
    try:
        from revintel import apply as A
        rows = A.query("SELECT ApiName, ForecastCategoryName FROM OpportunityStage WHERE IsActive = true")
        found = {r["ApiName"]: (r["ForecastCategoryName"] or "").replace(" ", "") for r in rows}
        return {**STAGE_CATEGORY, **found} if found else STAGE_CATEGORY
    except BaseException:   # no CLI session / offline: fall back to the defaults
        return STAGE_CATEGORY


def _forecast_label():
    """The label of the role-based forecast type the quotas are written to (read-only)."""
    dev = (opt("ROLE_FORECAST_TYPES", ["OpportunityAmount"]) or ["OpportunityAmount"])[0]
    try:
        from revintel import apply as A
        rows = A.query(f"SELECT MasterLabel FROM ForecastingType WHERE DeveloperName = '{dev}'")
        return rows[0]["MasterLabel"] if rows else dev
    except BaseException:
        return dev


def _story_part(m):
    return ("culprit", "Culprit: churn and slips concentrate here") if m >= 1.5 else \
        ("counter", "Counter-trend: healthy, beats quota") if m < 0 else \
        ("flat", "Steady") if m < 0.5 else ("", "Moderate")


def build(plan=None, categories=None):
    plan = plan or _load(os.path.join(OUT, "plan.json"), None)
    if not plan:
        raise SystemExit("No plan yet. Run plan (or Draft with Claude) first.")
    req = _load("rev_intel_request.json", {})
    facts = (_load(os.path.join(OUT, "inspect.json"), {}) or {}).get("org_facts") or {}
    by_id = {u["id"]: u["name"] for u in facts.get("users", [])}
    new_users = _load("new_users.json", {})
    names = {k: by_id.get(v, k.title()) for k, v in C.USERS.items()}
    names.update({u[0]: f"{u[1]} {u[2]}" for u in opt("NEW_USERS", [])})
    names.update({k: names.get(k, k.title()) for k in new_users})
    cat = categories or _stage_categories()

    today = date.fromisoformat(str(plan["today"]))
    month = today.isoformat()[:7]
    q0 = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    q1 = date(q0.year + (q0.month + 3 > 12), (q0.month + 2) % 12 + 1, 1)
    forecast_label = _forecast_label()
    qs, qe = q0.isoformat(), q1.isoformat()
    customer = opt("CUSTOMER_LABEL", req.get("customer", "the customer"))
    leader = opt("SALES_LEADER", "elliot")
    segs = C.SEGMENTS
    role_of = {r[3]: r[0] for r in opt("LEAD_ROLES", [])}
    leads = opt("LEADS", {})
    lead_for = lambda u: u if u in leads else next((l for l, reps in leads.items() if u in reps), u)   # noqa: E731
    stretch = opt("STRETCH", {})

    accts = {a["Id"]: a for a in plan["accounts"]}
    seg_of = {a["Id"]: a["_seg"] for a in plan["accounts"]}
    amount = collections.defaultdict(float)
    lines_of = collections.defaultdict(list)
    for li in plan["line_items"]:
        amount[li["_opp_ext"]] += (li["UnitPrice"] or 0) * (li.get("Quantity") or 1)
        lines_of[li["_opp_ext"]].append(li)
    opps = plan["opportunities"]
    for o in opps:
        o["_amount"] = amount[o["Demo_External_ID__c"]]
        o["_cat"] = cat.get(o["StageName"], "Pipeline")
        o["_seg"] = seg_of.get(o["AccountId"])
    renewal_rt = C.RT["renewal"]
    is_open = lambda o: not o["StageName"].startswith("Closed")   # noqa: E731

    from revintel.build import story_check
    _, _, churn12 = story_check(plan)
    ranked = sorted(segs, key=lambda s: -segs[s].get("mult", 1))
    culprit = ranked[0]
    counter = next((s for s in segs if segs[s].get("mult", 1) < 0), ranked[-1])
    lead_c, lead_k = lead_for(segs[culprit]["owner"]), lead_for(segs[counter]["owner"])
    total_churn = sum(churn12.values()) or 1

    # Hero account: the culprit-segment account that dropped the most at renewal, with an open renewal at risk
    def dropped_value(a_id):
        val, when, prods = 0, None, []
        for o in opps:
            if o["AccountId"] == a_id and o["RecordTypeId"] == renewal_rt and o["StageName"] == "Closed Won":
                for li in lines_of[o["Demo_External_ID__c"]]:
                    if "Dropped at renewal" in (li.get("Description") or ""):
                        m = re.search(r"\$([\d,]+)", li["Description"])
                        val += int(m.group(1).replace(",", "")) if m else 0
                        when, prods = o["CloseDate"], prods + [li["_product"]]
        return val, when, prods

    def open_renewal(a_id):
        rs = sorted((o for o in opps if o["AccountId"] == a_id and o["RecordTypeId"] == renewal_rt and is_open(o)),
                    key=lambda o: o["CloseDate"])
        return rs[0] if rs else None

    candidates = []
    for a_id, a in accts.items():
        if a["_seg"] != culprit:
            continue
        val, when, prods = dropped_value(a_id)
        r = open_renewal(a_id)
        at_risk = bool(r and r["StageName"].startswith("At Risk"))
        candidates.append((val > 0, at_risk, val, a_id, when, prods, r))
    candidates.sort(reverse=True)
    hero = candidates[0] if candidates else None

    # Commit deal on the culprit team this month (else the nearest open Commit deal on that team)
    team_open = [o for o in opps if o["_seg"] == culprit and is_open(o) and o["_amount"] > 0]
    commits = sorted((o for o in team_open if o["_cat"] == "Commit"),
                     key=lambda o: (o["CloseDate"][:7] != month, o["CloseDate"]))
    commit = commits[0] if commits else None

    # Commit Calculator numbers for the counter-trend lead, this quarter
    in_q = [o for o in opps if o["_seg"] == counter and qs <= o["CloseDate"] < qe]
    calc = {k: [o for o in in_q if o["_cat"] == k] for k in ("Closed", "Commit", "BestCase", "Pipeline")}

    h = [f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(customer)} — Revenue Intelligence demo walkthrough</title><style>{CSS}</style></head><body>"]
    h.append(f"<p class='subtitle'>Revenue Intelligence demo · {e(C.ORG_ALIAS)} · data as of {today:%b %d, %Y} "
             f"· regenerated by every Plan / Build</p>")

    # 1. Demo Scenario
    story = req.get("story", {})
    h.append("<h1>Demo Scenario</h1>")
    h.append(f"<h2>About {e(customer)}</h2><p>{e(req.get('use_case') or '')}</p>")
    if req.get("industry"):
        h.append(f"<p><b>Industry:</b> {e(req['industry'])}</p>")
    h.append("<h2>Audience &amp; Story</h2>")
    if req.get("audience"):
        h.append(f"<p><b>Audience:</b> {e(req['audience'])}</p>")
    h.append(f"<p>Churn over the last 12 months is concentrated in <b>{e(segs[culprit].get('label', culprit))}</b> "
             f"({e(names.get(lead_c, lead_c))}'s team, {money(churn12.get(culprit))}, "
             f"{100 * churn12.get(culprit, 0) / total_churn:.0f}% of all churn). "
             + (f"<b>Root cause:</b> {e(story['root_cause'])} " if story.get("root_cause") else "")
             + (f"<b>Leading indicator:</b> {e(story['leading_indicator'])} " if story.get("leading_indicator") else "")
             + f"<b>Counter-trend:</b> {e(segs[counter].get('label', counter))} ({e(names.get(lead_k, lead_k))}) "
             f"has the least churn and beats quota, so the problem isn't the whole business.</p>")

    # 2. The team
    h.append("<h1>The Team</h1>")
    h.append(f"<p>Revenue Insights shows the leads under <b>{e(names.get(leader, leader))}</b>. "
             f"Always open it as {e(names.get(leader, leader))}: the CEO's view also includes other demos' people.</p>")
    h.append("<table><tr><th>Lead</th><th>Team</th><th>Churn, last 12 mo</th><th>Open renewals (at risk)</th><th>Story</th></tr>")
    stats = _load(os.path.join(OUT, "story_stats.json"), {})
    open_r = stats.get("open_renewals_by_segment", {})
    for s in ranked:
        cls, label = _story_part(segs[s].get("mult", 1))
        r = open_r.get(s, {})
        risk = sum(v for k, v in r.items() if k.startswith("At Risk"))
        own = segs[s]["owner"]
        lead = lead_for(own)
        if lead not in leads and s in opt("OWNER_SPLITS", {}):   # split-role owner: the lead holds the big accounts
            lead = opt("OWNER_SPLITS", {})[s][0]
        note = ("also owned by (split-role: reports outside the team, forecasts through the territory)"
                if own in opt("EXTRA_TEAM", []) else "accounts owned by")
        who = e(names.get(lead, lead)) + (f"<br><span class='subtitle'>{note} {e(names.get(own, own))}</span>"
                                           if own != lead else "")
        h.append(f"<tr><td>{who}</td><td>{e(segs[s].get('label', s))}</td><td>{money(churn12.get(s))}</td>"
                 f"<td>{sum(r.values())} ({risk})</td><td class='tag {cls}'>{label}</td></tr>")
    h.append("</table>")

    # 3. Talk track (structure of the Revenue Intelligence + Tableau Next demo script)
    lc, lk, ld = e(names.get(lead_c, lead_c)), e(names.get(lead_k, lead_k)), e(names.get(leader, leader))
    seg_c, seg_k = e(segs[culprit].get("label", culprit)), e(segs[counter].get("label", counter))
    churn_label = e(C.PRODUCTS[C.CHURN_PRODUCT]["label"]) if getattr(C, "CHURN_PRODUCT", None) in C.PRODUCTS else "an add-on"
    core_label = e(C.PRODUCTS[C.CORE_PRODUCT]["label"]) if getattr(C, "CORE_PRODUCT", None) in C.PRODUCTS else "the core product"
    culprits = [s_ for s_ in ranked if segs[s_].get("mult", 1) >= 1.5]
    behind = list(dict.fromkeys(names.get(lead_for(segs[s_]["owner"]), segs[s_]["owner"]) for s_ in culprits))
    ahead = list(dict.fromkeys(names.get(lead_for(segs[s_]["owner"]), segs[s_]["owner"])
                               for s_ in segs if segs[s_].get("mult", 1) < 0.5))
    h.append("<h1>Demo Talk Track</h1>")
    h.append(f"<p>Follows the standard Revenue Intelligence demo: a sales rep's day ({lc}), then the sales leader "
             f"preparing for the forecast call ({ld}). Each step has what to <b>say</b>, what to <b>click</b>, and what the "
             "audience <b>sees</b>, with this build's people, deals and numbers. Open everything from the "
             "<b>Revenue Insights</b> app. Plan on about 30 minutes.</p>")

    def step(title, items):
        h.append(f"<div class='step'><h2>{e(title)}</h2>" + "".join(f"<p><b>{k}</b> {v}</p>" for k, v in items) + "</div>")

    def part(title):
        h.append(f"<h2 style='margin-top:1.8em'>{e(title)}</h2>")

    team_q = [o for o in opps if o["_seg"] == culprit and qs <= o["CloseDate"] < qe]
    won_q = sum(o["_amount"] for o in team_q if o["_cat"] == "Closed")
    commit_q = sum(o["_amount"] for o in team_q if o["_cat"] == "Commit")
    open_deals = [o for o in team_q if is_open(o)]
    hero_r = hero[6] if hero else None
    rep_deal = hero_r or (sorted(team_open, key=lambda o: (not o["StageName"].startswith("At Risk"), -o["_amount"]))
                          or [None])[0]
    all_q_open = [o for o in opps if qs <= o["CloseDate"] < qe and is_open(o) and o["_amount"] > 0]
    best = sorted((o for o in all_q_open if o["_cat"] == "BestCase"), key=lambda o: -o["_amount"])
    best_deal = best[0] if best else None

    part("Part Zero: Revenue Intelligence on its own")
    step("Set the scene", [
        ("Say:", f"“Revenue Intelligence is purpose-built for pipeline management and forecasting. {e(customer)}'s reps and "
                 "leaders each get role-based dashboards with their own numbers, so everyone works from one snapshot of "
                 f"the business.” Then name the problem: {e(story.get('problems', ['renewals'])[0].lower()) if story.get('problems') else 'renewals'} "
                 f"concentrated in {seg_c}."),
        ("Action:", f"Show the two starting points: the rep's <b>Sales Rep Command Center</b> and the leader's "
                    f"<b>Revenue Insights</b> home.")])

    part(f"Part One: Sales Rep ({names.get(lead_c, lead_c)})")
    step("1. Where do I stand?", [
        ("Say:", f"“As {lc}, I start my day here: where I stand against quota, and the trend, not just a snapshot.”"),
        ("Action:", f"Open <b>Sales Rep Command Center</b> as {lc}. It shows the signed-in user (“Welcome back, …”), so log in "
                    f"as {lc} (Setup → Users → {lc} → Login), or pick {lc} in the user filter if your view has one. Set "
                    f"<b>Forecasting Type</b> to <b>{e(forecast_label)}</b>."),
        ("Audience sees:", f"<b>Performance Trend</b>: {money(won_q)} won so far this quarter against {money(commit_q)} in "
                           "commit, the quota gauge" + (" short of quota" if stretch.get(lead_c, 1) > 1 else "")
                           + ", and the gap to quota.")])
    step("2. What will it take to hit my number?", [
        ("Say:", "“I can see my gap to quota and run what-ifs to see exactly what it takes to close it.”"),
        ("Action:", "Scroll to the <b>What If Calculator</b> and move the slider. Optionally open the <b>Pipeline Overview</b> "
                    "page to show the deals by stage."),
        ("Audience sees:", f"{plural(len(open_deals), 'open deal')} on {lc}'s team closing this quarter, and how much more "
                           "they need to close.")])
    if rep_deal:
        step("3. Act on my priority deal", [
            ("Say:", f"“It points me to the deals that need attention, and I can act without switching screens.”"),
            ("Action:", f"Find <b>{e(rep_deal['Name'])}</b> in the Command Center's opportunity lists (or <b>Stuck "
                        "Opportunities</b> after a Roll) and open the action menu: log a call, create a task, or open the "
                        "record."),
            ("Audience sees:", f"{money(rep_deal['_amount'])}, <b>{e(rep_deal['StageName'])}</b>, closing "
                               f"{date.fromisoformat(rep_deal['CloseDate']):%b %d, %Y}."
                               + (f" Next step: “{e(rep_deal['NextStep'])}”" if rep_deal.get("NextStep") else ""))])
    if hero:
        _, _, val, a_id, when, prods, r = hero
        a = accts[a_id]
        dropped = ", ".join(C.PRODUCTS[p]["label"] for p in prods) if prods else ""
        ever = {li["_product"] for o in opps if o["AccountId"] == a_id
                for li in lines_of[o["Demo_External_ID__c"]] if (li["UnitPrice"] or 0) > 0}
        never = [C.PRODUCTS[p]["label"] for p in C.PRODUCTS if p not in ever]
        items = [("Say:", "“Before my meeting, I want the whole picture of this customer, not just the one deal.”"),
                 ("Action:", f"In <b>Einstein Account Management</b>, pick <b>{e(a['Name'])}</b> in the <b>Account Name</b> "
                             f"filter ({e(a.get('BillingCity') or '')}). Each account sits in exactly one tile, so if it isn't "
                             "in the default list, look under Where to Sell or Most at Risk.")]
        if val:
            items.append(("Audience sees:", f"The product list: <b>{e(dropped)}</b> worth {money(val)} went to $0 at the "
                                            f"{date.fromisoformat(when):%b %Y} renewal, while {core_label} renewed."))
            items.append(("Say:", "“They renewed, so on a won/lost report this account looks fine. It isn't. A dropped "
                                  "product still counts as a won renewal, so it never shows up as churn. That's the early "
                                  "warning before an account leaves.”"))
        if never:
            items.append(("Then:", f"Open <b>Whitespace</b>: products it has never bought ({e(', '.join(never))}) are the next "
                                   "conversation. Whitespace counts anything ever bought, so the dropped product shows as "
                                   "purchased, not as a gap."))
        step(f"4. Prepare for the meeting: {a['Name']}", items)

    part(f"Part Two: Sales Leader ({names.get(leader, leader)})")
    step("5. How is the team pacing?", [
        ("Say:", f"“As {ld}, I need every lead positioned to hit their number, and to step in early when something "
                 "slips.”"),
        ("Action:", f"Log back in as {ld} and open the <b>Revenue Insights</b> home. Hover over each lead to show attainment, "
                    "and open the person filter (don't choose anyone) to show you can filter to one lead."),
        ("Audience sees:", f"All the leads on one view. {' and '.join(e(n) for n in ahead) or lk} "
                           f"{'are' if len(ahead) > 1 else 'is'} tracking well; {' and '.join(e(n) for n in behind) or lc} "
                           f"{'are' if len(behind) > 1 else 'is'} behind, with the most churn ({money(sum(churn12.get(s_, 0) for s_ in culprits))} "
                           "in the last 12 months between them).")])
    step("6. What should I focus on?", [
        ("Say:", "“Revenue Insights surfaces what needs attention, so I don't dig for it.”"
                 + (f" Tie it to the leading indicator: {e(story['leading_indicator'])}" if story.get("leading_indicator") else "")),
        ("Action:", "Scroll to <b>What should I focus on?</b>. Show <b>Opportunities Needing My Attention</b> and "
                    "<b>Top Open Opportunities</b>"
                    + (f". On <b>{e(commit['Name'])}</b>, open the action menu → <b>New Task</b> → “Please validate "
                       f"opportunity”, set a due date, and assign it to {lc}." if commit else ".")),
        ("Audience sees:", (f"<b>{e(commit['Name'])}</b>, {money(commit['_amount'])} in Commit"
                            + (f", next step “{e(commit['NextStep'].rstrip('.'))}”" if commit.get("NextStep") else "") + ". "
                            if commit else "")
                           + "Skip <b>No Next Step</b> and <b>Stuck in Stage</b>: the demo data has little stage history. "
                             "<b>No Activity</b> lists most open deals, because activity is logged on accounts, so point to "
                             f"{lc}'s renewals only.")])
    if best_deal:
        step("7. Which deals can move into Commit?", [
            ("Say:", "“I need more deals in Commit. Revenue Insights brings the biggest Best Case deals to the front.”"),
            ("Action:", "In <b>Top Open Opportunities</b>, click <b>Best Case</b>."),
            ("Audience sees:", f"<b>{e(best_deal['Name'])}</b>, {money(best_deal['_amount'])}, closing "
                               f"{date.fromisoformat(best_deal['CloseDate']):%b %d}: the deal to pull forward.")])
    calc_all = {k: [o for o in opps if qs <= o["CloseDate"] < qe and o["_cat"] == k] for k in ("Closed", "Commit", "BestCase")}
    sums = {k: (len(v), sum(o["_amount"] for o in v)) for k, v in calc_all.items()}
    step("8. Commit Calculator: the number for the forecast call", [
        ("Say:", "“Now I test scenarios and see how each change moves my forecast.”"
                 + (f" Pulling {e(commit['Name'])}: “{lc}'s team carries the most churn"
                    + (f", and this one is still at “{e(commit['NextStep'].rstrip('.'))}”" if commit.get("NextStep") else "")
                    + ", so it stays out of Commit until it's signed.”" if commit else "")),
        ("Action:", "Open <b>Commit Calculator</b> in the Revenue Insights app (not the older Revenue Intelligence app's "
                    "copy)."
                    + (f" Remove <b>{e(commit['Name'])}</b> from Commit" if commit else "")
                    + (f", then add <b>{e(best_deal['Name'])}</b> from Best Case." if best_deal else ".")),
        ("Audience sees:", f"This quarter for the whole team: Won {money(sums['Closed'][1])}, Commit {money(sums['Commit'][1])} "
                           f"({plural(sums['Commit'][0])}), Best Case {money(sums['BestCase'][1])} "
                           f"({plural(sums['BestCase'][0])}). The gap to goal moves as deals come out and go in."),
        ("Tip:", f"If the whole-team view is crowded, filter to {lk}: the healthy team's quarter has deals in every column.")])
    step("Close", [("Say:", f"“With Revenue Intelligence, {ld} sees where the business stands, finds the team that needs help, "
                            "and walks into the forecast call with a number they can defend. "
                            f"{lc} knows exactly which deals to work today.”")])

    # Optional: agent prompts, tailored to the story
    h.append("<h1>Optional: Agentforce for Analytics prompts</h1>")
    h.append("<p>Only if this org has the Analytics Agent (Concierge) set up on Revenue Intelligence data. Ask these in "
             "the agent panel; check the answers before the demo.</p>")
    rep_qs = [f"What is my pipeline by product family?",
              f"What are my top 5 renewals closing this quarter?",
              (f"What is the predicted likelihood of closing the {e(rep_deal['Name'])} deal?" if rep_deal else None),
              (f"Summarize metrics for {e(accts[hero[3]]['Name'])}" if hero else None)]
    lead_qs = [f"Which teams have the most churn this year?",
               f"What are the top 5 opportunities in the Commit forecast category that are at risk?",
               f"Which accounts dropped {churn_label} at renewal?",
               f"Why is churn highest in {seg_c}?",
               "Analyze monthly pipeline for the current quarter"]
    h.append("<h2>As the rep</h2><ul>" + "".join(f"<li>“{q}”</li>" for q in rep_qs if q) + "</ul>")
    h.append("<h2>As the leader</h2><ul>" + "".join(f"<li>“{q}”</li>" for q in lead_qs) + "</ul>")

    # 4. Don't show / before the demo
    h.append("<h1>Don't show</h1><ul>"
             "<li><b>EAM “Sales vs Previous Year”</b> on an account: the template divides by this year's sales, so "
             "drops read far too large. Say the numbers instead.</li>"
             "<li><b>Revenue Insights → Historical Trend → Period Comparison</b>: cumulative forecast items stack into a "
             "“–” bucket and count deals several times. The tiles above it are fine.</li>"
             "<li><b>No Next Step</b> and <b>Stuck in Stage</b> tabs: the demo data has little stage history, so they look odd.</li></ul>")
    counts = stats.get("counts", {})
    h.append("<h1>Before the demo</h1><ul>"
             "<li>On the Update Rev Intel page, run <b>Roll + add deals, then refresh CRM Analytics</b> a day or two before. "
             "It moves deals forward so the “last 7 days” tiles and Changes tabs show activity. The refresh takes about an "
             "hour and the dashboards are half-updated while it runs, so don't run it the day of the demo.</li>"
             f"<li>Click through once: {lc}'s team shows the Commit deal"
             + (f", {e(accts[hero[3]]['Name'])} is in the EAM list with its product drop" if hero else "")
             + f", and the Commit Calculator opens on the current quarter for {lk}.</li>"
             "<li>Numbers here are from the plan at build time; Roll changes some of them.</li></ul>")
    h.append(f"<h1>What was generated</h1><p>{counts.get('accounts', 0)} accounts, {counts.get('opportunities', 0)} "
             f"opportunities, {counts.get('line_items', 0)} line items, {counts.get('contacts', 0)} contacts, "
             f"{counts.get('tasks', 0)} tasks and {counts.get('events', 0)} events.</p>")
    h.append("</body></html>")

    path = os.path.join(DEMO_DIR, f"{os.path.basename(DEMO_DIR)}_demo_walkthrough.html")
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from walkthrough_nav import add_nav
    open(path, "w", encoding="utf-8").write(add_nav("\n".join(h)))
    return path


def run():
    print("✓ walkthrough written:", build())
