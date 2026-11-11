"""Roll the demo forward in time: `python3 -m revintel <demo> roll [--apply] [--date YYYY-MM-DD] [--force] [--refresh]`.

A full `reset` + `apply --today` re-dates everything but throws the history away, and a fresh load
has no week-over-week movement: Revenue Insights' "last 7 days" deltas and its Opportunity Changes
tabs read OpportunityHistory, which only EDITS create. `roll` plays the days since the last roll
forward with small, story-consistent edits to the demo's open opportunities:

  - deals reach their close date and close (won / lost) or slip, culprit segments slipping and
    dropping a product more often, counter-trend segments less
  - stages advance as the close date nears (Created -> Discovery -> Negotiations -> Confirmed), and
    healthy deals sometimes turn At Risk (culprit segments more often) or recover (counter-trend)
  - amounts and close dates drift a little (culprit segments mostly down and later)
  - activity is logged against the opportunities themselves (RI's "No Activity" reads that); at-risk
    and quiet culprit deals get none, so that list shows the deals worth coaching on

Dry run by default: it prints what would change and the effect on this month's Closed Won and Commit,
writes out/roll_plan.json, and touches nothing. `--apply` backs up the before-values (out/backup_roll_*)
and writes. Draws are seeded per (opportunity, day), so a plan is repeatable, and `last_roll` in the
checkpoint stops a second run on the same day from applying the same edits twice. Run
`refresh` (or add --refresh) afterwards: the dashboards only see changes after Data Sync + the recipes.
Tune with a ROLL = {...} dict in the config (see DEFAULTS).
"""

import json
import os
import random
from datetime import date, timedelta

from revintel import apply as A
from revintel.config import C, FIELDS, OPP_TYPES, OUT, RENEWAL_STAGES, opt
from revintel.generate import COMMENTARY, TASK_SUBJECTS, fx, pick_reason

DEFAULTS = {"nudge_p": 0.05,        # per open deal per day: an amount or close-date drift
            "risk_p": 0.012,        # per healthy renewal per day (x segment multiplier): turns At Risk
            "recover_p": 0.03,      # per At Risk renewal per day in a counter-trend segment: recovers
            "slip_base": 0.12, "slip_per_mult": 0.10,    # chance a due deal slips instead of closing
            "drop_p_per_mult": 0.16,  # chance a won culprit renewal drops its churn product
            "activity_p": 0.08,     # per deal per day inside 45 days of close: a logged activity
            "seed_days": 14,        # first roll only: backfill activity over this many days
            "max_days": 45,         # longest gap simulated day by day
            "early_window_days": 21,
            "close_size_scale": 250000,
            "close_max_amount": 400000}  # forced closes skip deals above this, keeping the headline deals open  # forced closes: a deal this size is half as likely as a tiny one  # --close may close a deal up to this many days before its close date
R = {**DEFAULTS, **opt("ROLL", {})}

RISK = {"contraction": RENEWAL_STAGES.get("risk_contraction"), "timing": RENEWAL_STAGES.get("risk_timing"),
        "churn": next((k for s in C.SEGMENTS.values() for k in s.get("risk_mix", {}) if "churn" in k.lower()), None)}
LADDER = [RENEWAL_STAGES["early"], RENEWAL_STAGES["mid"], RENEWAL_STAGES["late"], RENEWAL_STAGES["confirmed"]]
TERR_SEG = {v.get("territory"): k for k, v in C.SEGMENTS.items()}
CORE = opt("CORE_PRODUCT", None)
CHURN_PRODUCT = opt("CHURN_PRODUCT", None)


def rng_for(*key):
    return random.Random("|".join(map(str, (C.SEED, "roll") + key)))


def rnd(*key):
    return rng_for(*key).random()


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def risk_kind(stage):
    s = (stage or "").lower()
    return None if not s.startswith("at risk") else "churn" if "churn" in s else "timing" if "timing" in s else "contraction"


def product_name(key):
    p = (C.PRODUCTS.get(key) or {}) if key else {}
    return p.get("name") or p.get("label")


def money(x):
    return f"${x:,.0f}"


# ── load ────────────────────────────────────────────────────────────────────
def load_open():
    atr = FIELDS.get("atr")
    cols = ("Id, Name, StageName, ForecastCategoryName, CloseDate, Amount, Type, OwnerId, AccountId, NextStep, "
            "Territory2.DeveloperName" + (f", {atr}" if atr else ""))
    rows = A.query(f"SELECT {cols} FROM Opportunity WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%' AND IsClosed = false")
    states = []
    for o in rows:
        seg = TERR_SEG.get((o.get("Territory2") or {}).get("DeveloperName"))
        mult = C.SEGMENTS[seg]["mult"] if seg else 1.0
        states.append({"id": o["Id"], "name": o["Name"], "stage": o["StageName"], "orig_stage": o["StageName"],
                       "close": date.fromisoformat(o["CloseDate"]), "orig_close": date.fromisoformat(o["CloseDate"]),
                       "amount": o["Amount"] or 0, "atr": o.get(atr) if atr else None, "owner": o["OwnerId"],
                       "next_step": o.get("NextStep"), "seg": seg, "mult": mult,
                       "renewal": o["Type"] == OPP_TYPES["renewal"], "category": o["ForecastCategoryName"],
                       "result": None, "scale": 1.0, "drop": False, "slips": 0, "events": [], "tasks": []})
    scores = load_scores()
    for st in states:
        st["score"] = scores.get(st["id"])
    return states


def load_scores():
    """Einstein opportunity scores (0-1) by opportunity Id; empty if the org doesn't have scoring."""
    try:
        return {r["BaseId"]: r["Score"] / 100 for r in A.query("SELECT BaseId, Score FROM OpportunityScore")}
    except Exception:
        return {}


def load_lines(ids):
    out = {}
    for i in range(0, len(ids), 150):
        for r in A.query("SELECT Id, OpportunityId, UnitPrice, Quantity, Product2.Name FROM OpportunityLineItem "
                         f"WHERE OpportunityId IN {A.ids_in(ids[i:i + 150])}"):
            out.setdefault(r["OpportunityId"], []).append(r)
    return out


# ── simulation ──────────────────────────────────────────────────────────────
def is_quiet(s):
    return risk_kind(s["stage"]) == "churn" or (s["mult"] >= 1.5 and rnd(s["id"], "quiet") < 0.5)


def slip(s, d, lo, hi, why):
    s["close"] = d + timedelta(days=rng_for(s["id"], d, "slipdays").randint(lo, hi))
    s["slips"] += 1
    if s["stage"] == RENEWAL_STAGES["confirmed"]:
        s["stage"] = RENEWAL_STAGES["late"]   # a slipped commit drops back to best case
    s["events"].append((d, "slip", why))


def day_step(s, d):
    if s.get("frozen"):
        return
    m, k, rid = s["mult"], risk_kind(s["stage"]), s["id"]
    seg = C.SEGMENTS.get(s["seg"], {})
    if s["close"] <= d:                                   # due: close, or slip
        r = rnd(rid, "due", d)
        if not s["renewal"]:
            p_win = seg.get("expansion_win_p", 0.6)
            if r < p_win:
                s["result"] = "won"
            elif r < p_win + (1 - p_win) * 0.5:
                slip(s, d, 7, 21, "expansion slipped")
            else:
                s["result"] = "lost"
        elif k == "churn":
            if r < clamp(0.7 + 0.1 * max(m, 0), 0.5, 0.92):
                s["result"] = "lost"
            else:
                slip(s, d, 14, 30, "churn risk bought time")
        elif k == "timing":
            if r < 0.7:
                slip(s, d, 30, 45, "procurement delay")
            else:
                s["result"] = "won"
        elif k == "contraction":
            if r < 0.75:
                s["result"] = "won"
            else:
                slip(s, d, 14, 30, "seat true-down negotiation")
        elif r < clamp(R["slip_base"] + R["slip_per_mult"] * m
                       + (0.6 * (0.5 - s["score"]) if s.get("score") is not None else 0), 0.02, 0.5):
            slip(s, d, 7, 21, "renewal slipped")
        else:
            s["result"] = "won"
            if CHURN_PRODUCT and m >= 1.5 and rnd(rid, "drop") < clamp(R["drop_p_per_mult"] * m, 0, 0.6):
                s["drop"] = True
        if s["result"]:
            s["events"].append((d, s["result"], ""))
        return
    days_left = (s["close"] - d).days
    if s["renewal"] and k is None:
        want = 3 if days_left < 25 and rnd(rid, "confirm") < 0.6 else 2 if days_left < 55 else 1 if days_left < 80 else 0
        cur = LADDER.index(s["stage"]) if s["stage"] in LADDER else None
        if cur is not None and want > cur:
            s["stage"] = LADDER[want]
            s["events"].append((d, "advance", s["stage"]))
        elif days_left <= 90 and rnd(rid, "risk", d) < clamp(R["risk_p"] * max(m, 0.2), 0, 0.06):
            mix = {n: w for n, w in seg.get("risk_mix", {}).items() if n}
            if mix:
                s["stage"] = rng_for(rid, d, "riskkind").choices(list(mix), weights=list(mix.values()), k=1)[0]
                s["events"].append((d, "at-risk", s["stage"]))
    elif s["renewal"] and m <= 0.5 and rnd(rid, "recover", d) < R["recover_p"]:
        s["stage"] = RENEWAL_STAGES["late"]
        s["events"].append((d, "recover", s["stage"]))
    if rnd(rid, "nudge", d) < R["nudge_p"]:               # drift: amount or close date, biased by the story
        bad = clamp(0.5 + 0.25 * (m - 0.5), 0.15, 0.92)
        down = rnd(rid, "sign", d) < bad
        if rnd(rid, "nk", d) < 0.5 and s["renewal"]:
            delta = rng_for(rid, d, "delta").uniform(0.04, 0.12)
            s["scale"] *= (1 - delta) if down else (1 + delta)
            s["events"].append((d, "amount", f"{'-' if down else '+'}{delta:.0%}"))
        else:
            n = rng_for(rid, d, "days").randint(3, 12)
            s["close"] = s["close"] + timedelta(days=n) if down else max(d + timedelta(days=2), s["close"] - timedelta(days=n))
            s["events"].append((d, "close-date", f"{'later' if down else 'earlier'} {n}d"))
    if days_left <= 45 and not is_quiet(s) and rnd(rid, "act", d) < R["activity_p"]:
        s["tasks"].append(d)


def parse_close(spec, today):
    """'today=3,2026-11-04=1' -> [(date, count), ...] sorted by date. Future dates are refused."""
    out = []
    for part in (spec or "").split(","):
        if not part.strip():
            continue
        when, _, n = part.partition("=")
        when = when.strip().lower()
        d = today if when == "today" else today - timedelta(days=1) if when == "yesterday" else date.fromisoformat(when)
        if d > today:
            raise SystemExit(f"--close can't use a future date ({d}).")
        out.append((d, int(n or 1)))
    return sorted(out)


def force_close(states, specs):
    """Close deals as won on given dates (back-dating is fine: the Closed Won line reads CloseDate).
    Picks Commit / Best Case deals due within early_window_days, weighting Commit, higher Einstein
    scores and healthier segments, so the story holds. Returns the chosen states."""
    def weight(s):
        sc = 0.5 if s.get("score") is None else clamp(s["score"], 0.1, 1.0)
        # smaller deals close more often than the few huge ones, so a month doesn't drain its commit in one go
        return ((1.5 if s["category"] == "Commit" else 1.0) * sc * clamp(1.3 - 0.4 * s["mult"], 0.3, 1.5)
                / (1 + (s["amount"] or 0) / R["close_size_scale"]))
    picked = []
    for d, n in specs:
        pool = [s for s in states if not s["result"] and risk_kind(s["stage"]) != "churn"
                and s["category"] in ("Commit", "Best Case") and not s.get("frozen")
                and (s["amount"] or 0) <= R["close_max_amount"]
                and s["close"] <= d + timedelta(days=R["early_window_days"])]
        pool.sort(key=lambda s: -(rnd(s["id"], "force", d) ** (1 / max(weight(s), 0.01))))
        for s in pool[:n]:
            s["result"], s["close"], s["forced"] = "won", d, True
            if s["renewal"] and CHURN_PRODUCT and s["mult"] >= 1.5 and rnd(s["id"], "drop") < clamp(R["drop_p_per_mult"] * s["mult"], 0, 0.6):
                s["drop"] = True
            s["events"].append((d, "won", "closed early" if d < s["orig_close"] else "closed"))
            picked.append(s)
    return picked


def seed_tasks(states, today):
    """First roll only: backfill a couple of logged activities on each deal near close."""
    for s in states:
        if is_quiet(s) or (s["close"] - today).days > 60:
            continue
        for i in range(1, rng_for(s["id"], "seedn").randint(1, 3) + 1):
            s["tasks"].append(today - timedelta(days=rng_for(s["id"], "seed", i).randint(1, R["seed_days"])))


def simulate(states, first, today, seeded):
    d = first
    while d <= today:
        for s in states:
            if not s["result"]:
                day_step(s, d)
        d += timedelta(days=1)
    if not seeded:
        seed_tasks(states, today)


# ── translate to record edits ───────────────────────────────────────────────
def build_edits(states, lines, today):
    opp_rows, oli_rows, task_rows, backup = [], [], [], []
    churn_label, core_label = product_name(CHURN_PRODUCT), product_name(CORE)
    for s in states:
        row, changed = {"Id": s["id"]}, False
        if s["stage"] != s["orig_stage"] or s["result"]:
            row["StageName"] = {"won": "Closed Won", "lost": "Closed Lost"}.get(s["result"], s["stage"])
            changed = True
        if s["close"] != s["orig_close"]:
            row["CloseDate"] = s["close"].isoformat()
            changed = True
            if s["slips"] and not s["result"]:
                row["NextStep"] = "Close date moved; confirm the revised timeline with the customer."
        if s["result"] == "lost" and FIELDS.get("closed_lost_atr") and s["atr"]:
            row[FIELDS["closed_lost_atr"]] = s["atr"]
        ls = lines.get(s["id"], [])
        core = next((l for l in ls if core_label and l["Product2"]["Name"].startswith(core_label.split(" (")[0])), None)
        if s["scale"] != 1.0 and core and core["UnitPrice"]:
            oli_rows.append({"Id": core["Id"], "UnitPrice": round(core["UnitPrice"] * s["scale"], -2) or core["UnitPrice"]})
            backup.append({"object": "OpportunityLineItem", "Id": core["Id"], "UnitPrice": core["UnitPrice"]})
        if s["drop"]:
            gone = next((l for l in ls if churn_label and l["Product2"]["Name"].startswith(churn_label.split(" (")[0])
                         and l["UnitPrice"]), None)
            if gone:
                oli_rows.append({"Id": gone["Id"], "UnitPrice": 0})
                backup.append({"object": "OpportunityLineItem", "Id": gone["Id"], "UnitPrice": gone["UnitPrice"]})
                row.update(fx(product_churn=gone["UnitPrice"]))
                if s["atr"] and gone["UnitPrice"] / s["atr"] >= C.REASON_THRESHOLD and s["seg"]:
                    prim, sec = pick_reason(rng_for(s["id"], "reason"), s["seg"])
                    row.update(fx(primary_reason=prim, secondary_reason=sec, commentary=COMMENTARY.get(sec, "")))
                changed = True
                s["events"].append((today, "product-drop", f"{churn_label} {money(gone['UnitPrice'])}"))
        if changed or len(row) > 1:
            opp_rows.append(row)
            backup.append({"object": "Opportunity", "Id": s["id"], "StageName": s["orig_stage"],
                           "CloseDate": s["orig_close"].isoformat(), "NextStep": s["next_step"] or ""})
        for t in s["tasks"]:
            task_rows.append({"WhatId": s["id"], "OwnerId": s["owner"], "Subject": rng_for(s["id"], t, "subj").choice(TASK_SUBJECTS),
                              "ActivityDate": t.isoformat(), "Status": "Completed", "Priority": "Normal"})
    return opp_rows, oli_rows, task_rows, backup


def month_effect(states, lines, today, cats):
    """This month's Closed Won and Commit before and after the roll (the numbers RI's tiles show)."""
    def amount_after(s):
        a = s["amount"]
        if s["scale"] != 1.0:
            core_label = product_name(CORE)
            core = next((l for l in lines.get(s["id"], []) if core_label and l["Product2"]["Name"].startswith(core_label.split(" (")[0])), None)
            a += (core["UnitPrice"] * (s["scale"] - 1)) if core else s["amount"] * (s["scale"] - 1) * 0.5
        if s["drop"]:
            churn_label = product_name(CHURN_PRODUCT)
            gone = next((l for l in lines.get(s["id"], []) if churn_label and l["Product2"]["Name"].startswith(churn_label.split(" (")[0])), None)
            a -= gone["UnitPrice"] if gone else 0
        return a
    in_month = lambda d: (d.year, d.month) == (today.year, today.month)
    before = {"commit": sum(s["amount"] for s in states if s["category"] == "Commit" and in_month(s["orig_close"])), "won": 0}
    after = {"commit": 0, "won": 0}
    for s in states:
        if s["result"] == "won" and in_month(s["close"]):
            after["won"] += amount_after(s)
        elif not s["result"] and in_month(s["close"]) and cats.get(s["stage"]) == "Commit":
            after["commit"] += amount_after(s)
    return before, after


# ── command ─────────────────────────────────────────────────────────────────
def run(apply=False, refresh=False, on=None, force=False, close=None, close_only=False, keep=None, max_deal=None):
    today = date.fromisoformat(on) if on else date.today()
    specs = parse_close(close, today)
    if max_deal:
        R["close_max_amount"] = max_deal
    if apply and today > date.today():
        raise SystemExit("--apply won't write future-dated changes. Use --date with a past or current date.")
    cp = A.load_cp()
    last = date.fromisoformat(cp.get("last_roll") or cp.get("build_date") or (today - timedelta(days=1)).isoformat())
    if apply and cp.get("last_roll") == today.isoformat() and not force and not close_only:
        raise SystemExit(f"Already rolled today ({today}). Use --force to run again.")
    first = max(last + timedelta(days=1), today - timedelta(days=R["max_days"] - 1))
    states = load_open()
    if not states:
        raise SystemExit(f"No open opportunities with Demo_External_ID__c '{C.EXT_PREFIX}-%' in {C.ORG_ALIAS}. "
                         "Load the demo data first (apply).")
    names = [k.strip().lower() for k in (keep or "").split(",") if k.strip()]
    for st in states:   # --keep: deals whose name contains one of these are left exactly as they are this run
        st["frozen"] = any(k in st["name"].lower() for k in names)
    if names:
        print(f"Keeping as-is this run: {[st['name'] for st in states if st['frozen']]}")
    cats = {s["orig_stage"]: s["category"] for s in states}
    cats.update({"Closed Won": "Closed", "Closed Lost": "Omitted"})
    forced = force_close(states, specs) if specs else []   # reserve these first; the day simulation skips closed deals
    if not close_only:
        simulate(states, first, today, bool(cp.get("roll_seeded")))
    touched = [s for s in states if s["result"] or s["scale"] != 1.0 or s["drop"]]
    lines = load_lines([s["id"] for s in touched]) if touched else {}
    opp_rows, oli_rows, task_rows, backup = build_edits(states, lines, today)
    before, after = month_effect(states, lines, today, cats)

    ev = [(s, e) for s in states for e in s["events"]]
    n = lambda kind: sum(1 for _, e in ev if e[1] == kind)
    won = [s for s in states if s["result"] == "won"]
    lost = [s for s in states if s["result"] == "lost"]
    print(f"Roll {first} → {today} ({(today - first).days + 1} days) on {C.ORG_ALIAS}, {len(states)} open deals"
          f"{'' if apply else '   [DRY RUN — nothing is written]'}")
    print(f"  closed won  {len(won):>3}  {money(sum(s['amount'] for s in won))}   closed lost {len(lost):>3}  {money(sum(s['amount'] for s in lost))}"
          f"   slipped {n('slip')}")
    print(f"  stage moves {n('advance'):>3}   turned at-risk {n('at-risk')}   recovered {n('recover')}   "
          f"amount changes {n('amount')}   close-date moves {n('close-date')}   product drops {n('product-drop')}")
    quiet = sum(1 for s in states if not s["result"] and is_quiet(s))
    print(f"  activities  {len(task_rows):>3} logged on {sum(1 for s in states if s['tasks'])} deals; {quiet} quiet deals get none (No Activity list)")
    print(f"  this month: closed won {money(before['won'])} → {money(after['won'])}   commit {money(before['commit'])} → {money(after['commit'])}")
    by_seg = {}
    for s in states:
        if s["events"]:
            by_seg.setdefault(s["seg"] or "?", []).append(s)
    for seg, ss in sorted(by_seg.items(), key=lambda kv: -C.SEGMENTS.get(kv[0], {}).get("mult", 0)):
        k = [e[1] for s in ss for e in s["events"]]
        print(f"    {seg:<9} mult {C.SEGMENTS.get(seg, {}).get('mult', '-'):<5} won {k.count('won'):>2}  lost {k.count('lost'):>2}  "
              f"slip {k.count('slip'):>2}  at-risk {k.count('at-risk'):>2}  amount {k.count('amount'):>2}  drops {k.count('product-drop'):>2}")
    if forced:
        print(f"  forced closes ({len(forced)}, {money(sum(s['amount'] for s in forced))}):")
        for s in sorted(forced, key=lambda x: (x["close"], x["name"])):
            sc = "" if s.get("score") is None else f" score {s['score'] * 100:.0f}"
            print(f"    {s['close']}  {s['name'][:50]:<50} {s['seg'] or '?':<9} {money(s['amount']):>11}{sc}"
                  f"{'  (drops ' + product_name(CHURN_PRODUCT) + ')' if s['drop'] else ''}")
    print("  examples:")
    for s, e in sorted(ev, key=lambda x: (x[1][0], x[0]["name"]))[-12:]:
        print(f"    {e[0]}  {s['name'][:48]:<48} {e[1]} {e[2]}")
    os.makedirs(OUT, exist_ok=True)
    json.dump({"from": first.isoformat(), "to": today.isoformat(), "opportunity_updates": opp_rows,
               "line_item_updates": oli_rows, "tasks": task_rows}, open(os.path.join(OUT, "roll_plan.json"), "w"), indent=1, default=str)
    if not apply:
        print("\nPlan written to out/roll_plan.json. Run again with --apply to write it to the org.")
        return
    A.write_csv(os.path.join(OUT, f"backup_roll_{today}.csv"), backup)
    print(f"\nBackup of before-values: out/backup_roll_{today}.csv")
    A.bulk("update", "OpportunityLineItem", oli_rows, cols=["Id", "UnitPrice"])
    if opp_rows:
        A.bulk("update", "Opportunity", opp_rows)
    A.bulk("import", "Task", task_rows, cols=["WhatId", "OwnerId", "Subject", "ActivityDate", "Status", "Priority"])
    if not close_only:
        cp["last_roll"], cp["roll_seeded"] = today.isoformat(), True
    A.save_cp(cp)
    print("Rolled. CRM Analytics only sees this after Data Sync + the recipes: run `refresh` (about 45–60 minutes).")
    if refresh:
        import crma_refresh
        crma_refresh.refresh(C.ORG_ALIAS, C.REFRESH_APPS)
