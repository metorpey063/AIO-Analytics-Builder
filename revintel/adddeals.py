"""Add deals to a built demo: `python3 -m revintel <demo> add [--apply] [--count N] [--date YYYY-MM-DD] [--force]`.

`roll` moves the deals that already exist; this adds new ones, so Revenue Insights' "New" tab and
pipeline coverage change from week to week and EAM's product funnel gets new expansion deals.
Each new opportunity is an expansion on an existing pool account for a product it doesn't own (the
whitespace EAM shows), created today (CreatedDate can't be back-dated, and today is right for "new").
Segments follow the story: counter-trend segments generate more pipeline than culprit ones, and a
segment's `boost` weights its favourite products (e.g. AIDA in NAMR Enterprise).

Dry run by default: prints what would be created and writes out/add_plan.json. `--apply` inserts
the opportunities, their line items and a first logged activity, and saves the created external IDs
in out/add_<date>.json. The count is `per_day` x the days since the last run (default 1.2/day, so about
8 a week; `--count N` overrides). Tune with ADD = {...} in the config (see DEFAULTS). Run `refresh`
afterwards so CRM Analytics picks the new deals up.
"""

import json
import os
from datetime import date, timedelta

from revintel import apply as A
from revintel.config import C, NB_STAGES, OPP_TYPES, OUT, opt
from revintel.generate import PIPELINE_PRODUCTS, TASK_SUBJECTS, add_months, r100
from revintel.roll import clamp, money, product_name, rng_for

DEFAULTS = {"per_day": 1.2, "max_per_run": 15, "default_days": 7,
            "stage_mix": [0.65, 0.25, 0.10],           # early / mid / late new-business stage
            "close_days": [(75, 140), (45, 90), (20, 50)],
            "first_task_p": 0.5}                       # share of new deals with a logged first activity
R = {**DEFAULTS, **opt("ADD", {})}
WEIGHTS = opt("EXPANSION_WEIGHTS", None) or {p: 1 for p in PIPELINE_PRODUCTS}


def key_for(line_name):
    """Config product key for an OpportunityLineItem's Product2.Name."""
    for k in C.PRODUCTS:
        n = product_name(k)
        if n and (line_name or "").startswith(n.split(" (")[0]):
            return k
    return None


def load_accounts():
    opps = A.query("SELECT Id, AccountId, Account.Name, Account.Demo_External_ID__c, Account.NumberOfEmployees, OwnerId, "
                   "Territory2Id, Territory2.DeveloperName, Type, StageName, IsClosed FROM Opportunity "
                   f"WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'")
    lines = A.query("SELECT UnitPrice, Product2.Name, Opportunity.AccountId, Opportunity.StageName FROM OpportunityLineItem "
                    f"WHERE Opportunity.Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'")
    terr_seg = {v.get("territory"): k for k, v in C.SEGMENTS.items()}
    accts = {}
    for o in opps:
        a = accts.setdefault(o["AccountId"], {"id": o["AccountId"], "name": o["Account"]["Name"],
                                             "ext": o["Account"]["Demo_External_ID__c"],
                                             "employees": o["Account"]["NumberOfEmployees"] or 1000,
                                             "held": set(), "open_nb": 0, "owner": None, "terr_id": None, "seg": None})
        renewal = o["Type"] == OPP_TYPES["renewal"]
        if renewal or not a["owner"]:
            a["owner"], a["terr_id"] = o["OwnerId"], o["Territory2Id"]
            a["seg"] = terr_seg.get((o.get("Territory2") or {}).get("DeveloperName"), a["seg"])
        if not renewal and not o["IsClosed"]:
            a["open_nb"] += 1
    for l in lines:
        k = key_for(l["Product2"]["Name"])
        owner = accts.get(l["Opportunity"]["AccountId"])
        if owner and k and l["UnitPrice"] and l["Opportunity"]["StageName"] != "Closed Lost":
            owner["held"].add(k)
    return [a for a in accts.values() if a["owner"] and a["terr_id"]]


def choose(accts, n, today):
    """Weighted sample of n accounts without replacement (counter-trend segments weigh more)."""
    scored = []
    for a in accts:
        mult = C.SEGMENTS.get(a["seg"], {}).get("mult", 1.0)
        w = clamp(1.4 - 0.4 * mult, 0.2, 2.0) * (0.5 if a["open_nb"] else 1.0) * (0 if a["open_nb"] >= 2 else 1)
        if w > 0:
            scored.append((rng_for(a["id"], "newpick", today).random() ** (1 / w), a))
    return [a for _, a in sorted(scored, key=lambda x: -x[0])[:n]]


def build(accts_picked, today, have):
    opps, olis, tasks, seq = [], [], [], 0
    pbes = A.product_pbes()
    for a in accts_picked:
        seg = C.SEGMENTS.get(a["seg"], {})
        rng = rng_for(a["id"], "newopp", today)
        weights = {p: w * seg.get("boost", {}).get(p, 1) for p, w in WEIGHTS.items() if p in C.PRODUCTS and p not in a["held"]}
        if not weights:
            continue
        prod = rng.choices(list(weights), weights=list(weights.values()), k=1)[0]
        label = C.PRODUCTS[prod]["label"]
        i = rng.choices(range(3), weights=R["stage_mix"], k=1)[0]
        stage = (NB_STAGES["early"], NB_STAGES["mid"], NB_STAGES["late"])[i]
        close = today + timedelta(days=rng.randint(*R["close_days"][i]))
        scale = (a["employees"] / 2000.0) ** 0.85
        price = max(r100(C.PRODUCTS[prod]["list"] * scale * 0.9), 1200)
        seq += 1
        ext = f"{C.EXT_PREFIX}-{(a['ext'] or '000')[-3:]}-A{today:%y%m%d}{seq:02d}"
        if ext in have:
            continue
        opps.append({"Demo_External_ID__c": ext, "Name": f"{a['name']} – {label} Expansion", "AccountId": a["id"],
                     "RecordTypeId": C.RT["new"], "Type": OPP_TYPES["addon"], "StageName": stage,
                     "CloseDate": close.isoformat(), "OwnerId": a["owner"], "Territory2Id": a["terr_id"],
                     "Pricebook2Id": C.STD_PRICEBOOK, "CurrencyIsoCode": "USD",
                     "Description": f"{OPP_TYPES['addon']}: {label} for {a['name']}.",
                     "NextStep": (C.NEXT_STEPS.get(stage) or "Confirm the buying team and timeline.").format(lead=label, add=label)[:255],
                     "_seg": a["seg"], "_prod": label, "_price": price})
        olis.append({"_opp_ext": ext, "PricebookEntryId": pbes.get(prod) or C.PRODUCTS[prod].get("pbe"), "Quantity": 1,
                     "UnitPrice": price, "ServiceDate": add_months(close, 12).isoformat(), "Description": f"{label} – new expansion"})
        if rng.random() < R["first_task_p"]:
            tasks.append({"_opp_ext": ext, "OwnerId": a["owner"], "Subject": rng.choice(TASK_SUBJECTS),
                          "ActivityDate": today.isoformat(), "Status": "Completed", "Priority": "Normal"})
    return opps, olis, tasks


def run(apply=False, count=None, on=None, force=False):
    today = date.fromisoformat(on) if on else date.today()
    if apply and today > date.today():
        raise SystemExit("--apply won't write future-dated changes. Use --date with a past or current date.")
    cp = A.load_cp()
    if apply and cp.get("last_add") == today.isoformat() and not force:
        raise SystemExit(f"Already added deals today ({today}). Use --force to add more.")
    last = date.fromisoformat(cp["last_add"]) if cp.get("last_add") else today - timedelta(days=R["default_days"])
    n = count if count is not None else clamp(round(R["per_day"] * max((today - last).days, 1)), 1, R["max_per_run"])
    accts = load_accounts()
    if not accts:
        raise SystemExit(f"No demo accounts found for '{C.EXT_PREFIX}-%' in {C.ORG_ALIAS}. Load the demo data first (apply).")
    have = {r["Demo_External_ID__c"] for r in A.query(
        f"SELECT Demo_External_ID__c FROM Opportunity WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%-A{today:%y%m%d}%'")}
    opps, olis, tasks = build(choose(accts, int(n), today), today, have)

    print(f"Add deals for {today} on {C.ORG_ALIAS}: {len(opps)} new expansion deals ({n:.0f} requested, "
          f"{(today - last).days} days since the last run){'' if apply else '   [DRY RUN — nothing is written]'}")
    print(f"  +{money(sum(o['_price'] for o in opps))} pipeline, {len(tasks)} with a logged first activity")
    by_seg = {}
    for o in opps:
        by_seg.setdefault(o["_seg"] or "?", []).append(o)
    for seg, os_ in sorted(by_seg.items(), key=lambda kv: -C.SEGMENTS.get(kv[0], {}).get("mult", 0)):
        print(f"    {seg:<9} mult {C.SEGMENTS.get(seg, {}).get('mult', '-'):<5} {len(os_)} deals  {money(sum(o['_price'] for o in os_))}")
    for o in opps:
        print(f"    {o['Name'][:58]:<58} {o['StageName']:<15} closes {o['CloseDate']}  {money(o['_price'])}")
    os.makedirs(OUT, exist_ok=True)
    json.dump({"date": today.isoformat(), "opportunities": opps, "line_items": olis, "tasks": tasks},
              open(os.path.join(OUT, "add_plan.json"), "w"), indent=1)
    if not apply:
        print("\nPlan written to out/add_plan.json. Run again with --apply to create them in the org.")
        return
    if not opps:
        print("Nothing to create.")
        return
    rows = [{k: v for k, v in o.items() if not k.startswith("_")} for o in opps]
    A.bulk("upsert", "Opportunity", rows, ext_id="Demo_External_ID__c")
    ids = {r["Demo_External_ID__c"]: r["Id"] for r in A.query(
        "SELECT Id, Demo_External_ID__c FROM Opportunity WHERE Demo_External_ID__c IN "
        f"{A.ids_in([o['Demo_External_ID__c'] for o in opps])}")}
    A.bulk("import", "OpportunityLineItem", [{**{k: v for k, v in l.items() if not k.startswith("_")},
                                              "OpportunityId": ids[l["_opp_ext"]]} for l in olis])
    A.bulk("import", "Task", [{**{k: v for k, v in t.items() if not k.startswith("_")}, "WhatId": ids[t["_opp_ext"]]} for t in tasks])
    json.dump({"created": ids}, open(os.path.join(OUT, f"add_{today}.json"), "w"), indent=1)
    cp["last_add"] = today.isoformat()
    A.save_cp(cp)
    print(f"Created {len(ids)} opportunities (ids in out/add_{today}.json). Run `refresh` so CRM Analytics sees them.")
