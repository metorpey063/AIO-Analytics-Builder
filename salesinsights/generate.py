"""
Synthetic Sales Insights data: seeded, anchored to today, shaped to package/data_contract.json.

Deals are simulated stage by stage over 24 months, so Opportunity, Opportunity_History (one row per
change), Opportunity_Historical_Trend (one row per stage segment), Forecasting_Fact and activities
all agree with each other. Values follow what the Sales Insights calcs compare against:
  - flags are lowercase text 'true' / 'false' (string comparison is case-sensitive)
  - Opportunity forecast category uses labels (Best Case, Commit, ...), which match the calcs and the
    Forecast Category parameter; Opportunity_History uses API values (BestCase, Forecast, ...)
  - quarters are named "FQ{n} FY {yyyy}" (Start_Date_One_Period_Ago_RI_clc builds that string)

Baseline story (generic, drillable):
  - Team Harbor is behind: lower win rate and smaller deals than Summit and Ridge
  - two Harbor reps hold most pushed, stalled and neglected deals
  - lead conversion ranges from ~60% (Referral) to ~10% (Trade Show)
  - some open deals have no activity, which fills the Leaderboard "No Activity" tab
"""

import csv
import json
import os
import random
from datetime import date, datetime, timedelta, timezone

SEED = 20261105
HISTORY_MONTHS = 24
FAR_FUTURE = datetime(2099, 12, 31, tzinfo=timezone.utc)
CONTRACT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "package", "data_contract.json")

# ---- Org: 1 sales leader, 3 managers, 4 reps each --------------------------------------------
LEADER = "Morgan Reyes"
TEAMS = {  # team -> (manager, reps, win rate, deal size multiplier)
    "Summit": ("Priya Natarajan", ["Ethan Brooks", "Sofia Marin", "Liam Okafor", "Grace Liu"], 0.46, 1.10),
    "Ridge": ("Daniel Kowalski", ["Ava Thompson", "Noah Fischer", "Maya Patel", "Owen Gallagher"], 0.40, 1.00),
    "Harbor": ("Rachel Kim", ["Lucas Moreau", "Chloe Bennett", "Mateo Silva", "Hannah Weiss"], 0.27, 0.80),
}
TROUBLE_REPS = {"Lucas Moreau", "Mateo Silva"}  # pushed / stalled / neglected deals cluster here

# ---- Vocabularies ------------------------------------------------------------------------------
STAGES = ["Created", "Targeting", "Needs Analysis", "Proposal", "Negotiations", "Closed Won", "Closed Lost"]
OPEN_STAGES = STAGES[:5]
FORECAST = {  # stage -> (Opportunity label, Opportunity_History API value)
    "Created": ("Pipeline", "Pipeline"), "Targeting": ("Pipeline", "Pipeline"),
    "Needs Analysis": ("Pipeline", "Pipeline"), "Proposal": ("Best Case", "BestCase"),
    "Negotiations": ("Commit", "Forecast"), "Closed Won": ("Closed", "Closed"), "Closed Lost": ("Omitted", "Omitted"),
}
STAGE_DAYS = {"Created": 5, "Targeting": 12, "Needs Analysis": 16, "Proposal": 18, "Negotiations": 14}
INDUSTRIES = ["Technology", "Healthcare", "Financial Services", "Retail", "Manufacturing", "Media", "Energy", "Education"]
ACCOUNT_TYPES = [("Customer - Direct", 35), ("Prospect", 40), ("Customer - Channel", 15), ("Channel Partner / Reseller", 10)]
OPP_TYPES = [("New Customer", 55), ("Existing Customer - Upgrade", 20), ("Add-On Business", 15), ("Existing Business", 10)]
LEAD_SOURCES = {  # source -> (share of leads, conversion rate)
    "Referral": (12, 0.62), "Partner Referral": (12, 0.50), "Web": (22, 0.34), "Marketing Campaign": (18, 0.28),
    "Social Media": (12, 0.20), "Cold Outbound": (14, 0.14), "Trade Show": (10, 0.10),
}
PRODUCTS = {  # family -> products
    "Platform": ["Core Platform", "Platform Enterprise", "Data Connectors", "Workflow Automation"],
    "Analytics": ["Analytics Suite", "Forecasting Add-on", "Embedded Dashboards", "AI Insights"],
    "Services": ["Implementation", "Premium Support", "Training Package", "Managed Services"],
}
NEXT_STEPS = ["Schedule discovery call", "Send proposal", "Confirm budget with finance", "Technical deep dive",
              "Security review", "Executive alignment meeting", "Negotiate pricing", "Send revised quote",
              "Legal redlines", "Confirm decision timeline", "Book product demo", "Share ROI analysis",
              "Follow up on pilot results", "Procurement paperwork", ""]
LEAD_STATUS_OPEN = [("New", 40), ("Working", 35), ("Nurturing", 25)]
LOCATIONS = [  # (country, state, city, weight)
    ("United States", "CA", "San Francisco", 9), ("United States", "CA", "Los Angeles", 6), ("United States", "NY", "New York", 10),
    ("United States", "TX", "Austin", 6), ("United States", "TX", "Dallas", 5), ("United States", "IL", "Chicago", 7),
    ("United States", "WA", "Seattle", 6), ("United States", "MA", "Boston", 6), ("United States", "GA", "Atlanta", 5),
    ("United States", "CO", "Denver", 4), ("United States", "FL", "Miami", 4), ("United States", "NC", "Charlotte", 3),
    ("United States", "OH", "Columbus", 3), ("United States", "MN", "Minneapolis", 3),
    ("Canada", "ON", "Toronto", 5), ("Canada", "BC", "Vancouver", 3),
    ("United Kingdom", "England", "London", 5), ("United Kingdom", "Scotland", "Edinburgh", 2),
    ("Australia", "NSW", "Sydney", 3), ("Australia", "VIC", "Melbourne", 2),
]
NAME_A = ["North", "Blue", "Silver", "Iron", "Summit", "Bright", "Clear", "Granite", "Harbor", "Cedar", "Atlas",
          "Pioneer", "Vertex", "Crescent", "Evergreen", "Keystone", "Lumen", "Meridian", "Orchid", "Quantum",
          "Redwood", "Sterling", "Trident", "Union", "Willow", "Apex", "Beacon", "Cobalt", "Delta", "Falcon"]
NAME_B = ["Logistics", "Health", "Systems", "Foods", "Energy", "Capital", "Labs", "Retail", "Manufacturing",
          "Media", "Networks", "Partners", "Analytics", "Industries", "Solutions", "Group", "Holdings", "Learning"]
FIRST = ["James", "Olivia", "Benjamin", "Emma", "Henry", "Isabella", "Samuel", "Mia", "Jack", "Amelia", "Leo",
         "Harper", "Caleb", "Evelyn", "Isaac", "Abigail", "Julian", "Ella", "Aaron", "Scarlett", "Miles", "Nora",
         "Adrian", "Layla", "Elijah", "Zoe", "Ryan", "Lily", "Nathan", "Aria"]
LAST = ["Carter", "Hughes", "Price", "Bennett", "Foster", "Coleman", "Russell", "Griffin", "Hayes", "Myers",
        "Ford", "Hamilton", "Graham", "Sullivan", "Wallace", "West", "Cole", "Jordan", "Reynolds", "Ellis"]


def _pick(rng, weighted):
    return rng.choices([v for v, _ in weighted], weights=[w for _, w in weighted])[0]


def _b(flag):
    return "true" if flag else "false"


class _Gen:
    def __init__(self, today, seed):
        self.rng = random.Random(seed)
        self.now = datetime(today.year, today.month, today.day, 17, 0, tzinfo=timezone.utc)
        self.start = self.now - timedelta(days=HISTORY_MONTHS * 30.44)
        self.t = {}

    def ts(self, d):
        return d.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # -- people ---------------------------------------------------------------------------------
    def people(self):
        users, urf, self.reps = [], [], []
        def add(uid, name, parents):
            users.append({"User_Id": uid, "Full_Name": name, "First_Name": name.split()[0]})
            for p in parents or [None]:
                urf.append({"Record_Id": f"{uid}_{p or 'top'}", "User_Id": uid, "Full_Name": name, "Parent_Name": p or ""})
        add("USR-001", LEADER, None)
        n = 2
        for team, (mgr, reps, win, size) in TEAMS.items():
            mid = f"USR-{n:03d}"; n += 1
            add(mid, mgr, [LEADER])
            for rep in reps:
                rid = f"USR-{n:03d}"; n += 1
                add(rid, rep, [mgr, LEADER])
                self.reps.append({"id": rid, "name": rep, "team": team, "win": win, "size": size,
                                  "trouble": rep in TROUBLE_REPS})
        for u in users:
            u["Record_Id"] = u["User_Id"]
        self.t["User"], self.t["User_Role_Flattened"] = users, urf

    # -- accounts, addresses, products ----------------------------------------------------------
    def accounts(self):
        rng, accts, cpa, names = self.rng, [], [], set()
        while len(names) < 360:
            names.add(f"{rng.choice(NAME_A)} {rng.choice(NAME_B)}")
        for i, name in enumerate(sorted(names)):
            aid = f"ACC-{i + 1:04d}"
            tier = rng.choices(["small", "mid", "large"], weights=[45, 35, 20])[0]
            emp = {"small": (20, 250), "mid": (250, 2500), "large": (2500, 40000)}[tier]
            employees = rng.randint(*emp)
            rep = self.reps[i % len(self.reps)]
            accts.append({"Record_Id": aid, "Account_Id": aid, "Account_Name": name, "Account_Type": _pick(rng, ACCOUNT_TYPES),
                          "Annual_Revenue_Amount": round(employees * rng.uniform(120_000, 380_000), -3),
                          "Employee_Count": employees, "Owner": rep["id"], "Primary_Industry": rng.choice(INDUSTRIES),
                          "_tier": tier, "_rep": rep})
            cpa.append(self._address(aid))
        self.t["Account"], self.t["Contact_Point_Address"] = accts, cpa
        prods, n = [], 1
        for fam, names_ in PRODUCTS.items():
            for p in names_:
                pid = f"PRD-{n:03d}"; n += 1
                prods.append({"Record_Id": pid, "Product_Id": pid, "Product_Name": p, "Product_Family": fam})
        self.t["Product"] = prods
        self.t["Opportunity_Stage"] = [{"Record_Id": s, "Label": s, "Sort_Order": i + 1} for i, s in enumerate(STAGES)]

    def _address(self, party):
        country, state, city, _ = self.rng.choices(LOCATIONS, weights=[w for *_, w in LOCATIONS])[0]
        return {"Record_Id": party, "Party": party, "City": city, "State_Province": state, "Country": country}

    # -- opportunities --------------------------------------------------------------------------
    def opportunities(self):
        rng = self.rng
        opps, hist, trend, opp_prod, ff, tasks = [], [], [], [], [], []
        by_rep = {}
        for a in self.t["Account"]:
            by_rep.setdefault(a["_rep"]["id"], []).append(a)
        products = self.t["Product"]
        n = 0
        for rep in self.reps:
            month = self.start
            while month < self.now:
                recent = (self.now - month).days < 120  # pipeline growth: fuller open-deal views
                for _ in range(rng.randint(9, 13) if recent else rng.randint(5, 9)):
                    created = month + timedelta(days=rng.uniform(0, 30), hours=rng.uniform(8, 18))
                    if created >= self.now - timedelta(days=1):
                        continue
                    n += 1
                    acct = rng.choice(by_rep[rep["id"]])
                    o, h, tr, acts = self._simulate(n, rep, acct, created)
                    opps.append(o); hist += h; trend += tr; tasks += acts
                    for p in rng.sample(products, rng.choice([1, 1, 2, 2, 3])):
                        opp_prod.append({"Record_Id": f"{o['Opportunity_Id']}_{p['Product_Id']}",
                                         "Opportunity": o["Opportunity_Id"], "Product": p["Product_Id"]})
                    ff.append({"Record_Id": f"{o['Opportunity_Id']}_FF", "Opportunity": o["Opportunity_Id"],
                               "_close": o["_close"], "Target_Value": o["Total_Amount"]})
                month += timedelta(days=30.44)
        self.t.update(Opportunity=opps, Opportunity_History=hist, Opportunity_Historical_Trend=trend,
                      Opportunity_Product=opp_prod, Forecasting_Fact=ff, Task=tasks)

    def _simulate(self, n, rep, acct, created):
        rng, oid = self.rng, f"OPP-{n:05d}"
        size = {"small": 18_000, "mid": 45_000, "large": 110_000}[acct["_tier"]] * rep["size"]
        amount = round(max(4_000, rng.lognormvariate(0, 0.45) * size), -2)
        won = rng.random() < rep["win"]
        lost_at = rng.choice(["Targeting", "Needs Analysis", "Proposal", "Negotiations"])
        slow = 1.8 if rep["trouble"] else 1.0
        push_p = 0.55 if rep["trouble"] else 0.12
        neglect = rng.random() < (0.30 if rep["trouble"] else 0.05)
        close = created + timedelta(days=rng.randint(55, 110))
        prev_close, prev_amt = None, None
        hist, segs, t, stage = [], [], created, "Created"
        freeze_at = self.now - timedelta(days=rng.randint(65, 140)) if neglect else None

        def change(when, stg, amt, cls):
            nonlocal prev_close, prev_amt
            hist.append({"Record_Id": f"{oid}_H{len(hist) + 1}", "Opportunity_History_Id": f"{oid}_H{len(hist) + 1}",
                         "Opportunity": oid, "Created_Date": when, "Opportunity_Stage": stg,
                         "Forecast_Category": FORECAST[stg][1], "Close_Date": cls, "Previous_Close_Date": prev_close,
                         "Total_Sale_Amount": amt, "Previous_Total_Sale_Amount": prev_amt})
            prev_close, prev_amt = cls, amt

        change(t, stage, amount, close)
        seg_start = t
        while stage in OPEN_STAGES:
            dwell = timedelta(days=rng.expovariate(1 / (STAGE_DAYS[stage] * slow)) + 1)
            nxt = t + dwell
            # pushes: the close date passes while the deal is still open
            while close < min(nxt, self.now) and stage in OPEN_STAGES:
                if rng.random() < push_p or close < t:
                    pushed_on = max(t, close - timedelta(days=rng.randint(0, 5)))
                    close = close + timedelta(days=rng.randint(21, 60))
                    if rng.random() < 0.3:
                        amount = round(amount * rng.uniform(0.75, 1.15), -2)
                    change(pushed_on, stage, amount, close)
                else:
                    nxt = min(nxt, close)
                    break
            if nxt >= self.now or (freeze_at and nxt >= freeze_at):
                break
            segs.append((stage, seg_start, nxt, close))
            t = seg_start = nxt
            if stage == lost_at and not won:
                stage = "Closed Lost"
            elif stage == "Negotiations":
                stage = "Closed Won" if won else "Closed Lost"
            else:
                stage = OPEN_STAGES[OPEN_STAGES.index(stage) + 1]
            if stage in ("Closed Won", "Closed Lost"):
                close = t
            change(t, stage, amount, close)
        closed = stage not in OPEN_STAGES
        segs.append((stage, seg_start, t if closed else FAR_FUTURE, close))
        trend = [{"Record_Id": f"{oid}_T{i + 1}", "Opportunity": oid, "Created_Date": s, "Effective_From_Date": s,
                  "Effective_To_Date": e, "New_Close_Date": c} for i, (stg, s, e, c) in enumerate(segs)]
        last_change = max(h["Created_Date"] for h in hist)
        # activities: none on neglected deals (No Activity tab); recent touches on active open deals
        acts, last_act = [], None
        if not (neglect and not closed):
            span_end = t if closed else self.now
            for _ in range(rng.randint(1, 6)):
                when = created + (span_end - created) * rng.random()
                last_act = max(last_act or when, when)
                acts.append({"Record_Id": f"{oid}_A{len(acts) + 1}", "Task_Task_Id": f"{oid}_A{len(acts) + 1}",
                             "Task_Related_To_Item": oid})
        opp = {"Record_Id": oid, "Opportunity_Id": oid, "Name": "", "Opportunity_Name": "", "CustomerAccount": acct["Account_Id"],
               "OwnerUser": rep["id"], "Created_Date": created, "Close_Date": close, "Is_Closed": _b(closed),
               "Is_Won": _b(stage == "Closed Won"), "Opportunity_Stage": stage, "Opportunity_Forecast_Category1": FORECAST[stage][0],
               "Total_Amount": amount, "Last_Modified_Date": last_change, "Last_Activity_Date": last_act,
               "Lead_Source": _pick(rng, [(s, w) for s, (w, _) in LEAD_SOURCES.items()]),
               "Opportunity_Type": _pick(rng, OPP_TYPES), "Next_Step": "" if closed else rng.choice(NEXT_STEPS), "_close": close}
        label = f"{acct['Account_Name']} - {opp['Opportunity_Type'].split(' - ')[-1]}"
        opp["Name"] = opp["Opportunity_Name"] = f"{label} {n % 97 + 1}"
        return opp, hist, trend, acts

    # -- forecasting periods --------------------------------------------------------------------
    def periods(self):
        periods, qid = [], {}
        for y in range(self.start.year - 1, self.now.year + 2):
            for q in range(1, 5):
                pid = f"BP-{y}Q{q}"
                qid[(y, q)] = pid
                periods.append({"Record_Id": pid, "Business_Period_Id": pid, "Fully_Qualified_Name": f"FQ{q} FY {y}",
                                "Is_Forecast_Period": "true", "Start_Date": date(y, 3 * q - 2, 1)})
            for m in range(1, 13):
                pid = f"BP-{y}M{m:02d}"
                periods.append({"Record_Id": pid, "Business_Period_Id": pid,
                                "Fully_Qualified_Name": f"{date(y, m, 1):%B} FY {y}", "Is_Forecast_Period": "false",
                                "Start_Date": date(y, m, 1)})
        for f in self.t["Forecasting_Fact"]:
            c = f.pop("_close")
            f["Business_Period"] = qid[(c.year, (c.month - 1) // 3 + 1)]
        self.t["Business_Period"] = periods

    # -- leads and calendar events --------------------------------------------------------------
    def leads(self):
        rng, leads = self.rng, []
        accts = self.t["Account"]
        for i in range(1100):
            lid = f"LEAD-{i + 1:05d}"
            src = _pick(rng, [(s, w) for s, (w, _) in LEAD_SOURCES.items()])
            created = self.now - timedelta(days=rng.uniform(1, 365), hours=rng.uniform(0, 9))
            conv_date = created + timedelta(days=rng.randint(4, 45))
            converted = rng.random() < LEAD_SOURCES[src][1] and conv_date < self.now
            acct = rng.choice(accts)
            rep = rng.choice(self.reps)
            loc = self._address(lid)
            self.t["Contact_Point_Address"].append(loc)
            leads.append({"Record_Id": lid, "Lead_Id": lid, "Person_Name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                          "Company_Name": acct["Account_Name"], "Industry": acct["Primary_Industry"], "Lead_Source": src,
                          "Lead_Status": "Converted" if converted else _pick(rng, LEAD_STATUS_OPEN),
                          "Is_Converted": _b(converted), "Created_Date": created,
                          "Converted_Date": conv_date if converted else None,
                          "Converted_To_Account": acct["Account_Id"] if converted else "", "Owner": rep["id"],
                          "City": loc["City"], "State_Province": loc["State_Province"]})
        self.t["Lead"] = leads
        self.t["Calendar_Event"] = [{"Record_Id": f"EVT-{i + 1:05d}", "Calendar_Event_Calendar_Event_Id": f"EVT-{i + 1:05d}"}
                                    for i in range(400)]

    def run(self):
        self.people(); self.accounts(); self.opportunities(); self.periods(); self.leads()
        for a in self.t["Account"]:
            a.pop("_tier"); a.pop("_rep")
        for o in self.t["Opportunity"]:
            o.pop("_close")
        return self.t


def generate(today=None, seed=SEED):
    return _Gen(today or datetime.now(timezone.utc).date(), seed).run()


def _fmt(v, dtype):
    if v is None or v == "":
        return ""
    if dtype == "DateTime":
        return v.strftime("%Y-%m-%dT%H:%M:%S.000Z") if isinstance(v, datetime) else f"{v.isoformat()}T00:00:00.000Z"
    if dtype == "Date":
        return (v.date() if isinstance(v, datetime) else v).isoformat()
    if dtype == "Number":
        return f"{v:g}" if isinstance(v, float) else str(v)
    return str(v)


def validate(tables, contract=None):
    """Return a list of problems. Empty means the data matches the contract and the story holds."""
    contract = contract or json.load(open(CONTRACT))
    errs = []
    for t, spec in contract.items():
        rows = tables.get(t)
        if not rows:
            errs.append(f"{t}: no rows"); continue
        want = {f["name"] for f in spec["fields"]}
        missing = want - set(rows[0])
        if missing:
            errs.append(f"{t}: missing columns {sorted(missing)}")
        ids = [r["Record_Id"] for r in rows]
        if len(ids) != len(set(ids)):
            errs.append(f"{t}: duplicate Record_Id")
    ids = lambda t, k: {r[k] for r in tables[t]}
    checks = [("Opportunity", "CustomerAccount", "Account", "Account_Id"), ("Opportunity", "OwnerUser", "User", "User_Id"),
              ("Opportunity_History", "Opportunity", "Opportunity", "Opportunity_Id"),
              ("Opportunity_Historical_Trend", "Opportunity", "Opportunity", "Opportunity_Id"),
              ("Opportunity_Product", "Product", "Product", "Product_Id"), ("Forecasting_Fact", "Business_Period", "Business_Period", "Business_Period_Id"),
              ("Task", "Task_Related_To_Item", "Opportunity", "Opportunity_Id"), ("Lead", "Owner", "User", "User_Id"),
              ("Opportunity", "Opportunity_Stage", "Opportunity_Stage", "Label")]
    for t, k, rt, rk in checks:
        bad = {r[k] for r in tables[t] if r[k]} - ids(rt, rk)
        if bad:
            errs.append(f"{t}.{k}: {len(bad)} values not in {rt}.{rk}")
    for t, k in (("Opportunity", "Is_Closed"), ("Opportunity", "Is_Won"), ("Lead", "Is_Converted")):
        bad = {r[k] for r in tables[t]} - {"true", "false"}
        if bad:
            errs.append(f"{t}.{k}: values must be lowercase true/false, got {bad}")
    labels = {"Best Case", "Closed", "Commit", "Omitted", "Pipeline"}  # Forecast_Category_Name_RI_prm values
    if {r["Opportunity_Forecast_Category1"] for r in tables["Opportunity"]} - labels:
        errs.append("Opportunity_Forecast_Category1 has values outside the Forecast Category parameter")
    o = tables["Opportunity"]
    if not any(r["Is_Closed"] == "false" and not r["Last_Activity_Date"] for r in o):
        errs.append("story: no open deals without activity (No Activity tab would be empty)")
    for mgr in [m for m, *_ in TEAMS.values()]:
        if not any(r["Parent_Name"] == mgr for r in tables["User_Role_Flattened"]):
            errs.append(f"story: Team Member filter value {mgr} has no rows")
    return errs


def summary(tables):
    o = tables["Opportunity"]
    users = {u["User_Id"]: u["Full_Name"] for u in tables["User"]}
    team_of = {}
    for team, (mgr, reps, *_r) in TEAMS.items():
        for rep in reps:
            team_of[rep] = team
    lines = [f"{t}: {len(r):,} rows" for t, r in tables.items()]
    for team in TEAMS:
        mine = [r for r in o if team_of.get(users[r["OwnerUser"]]) == team]
        closed = [r for r in mine if r["Is_Closed"] == "true"]
        won = [r for r in closed if r["Is_Won"] == "true"]
        lines.append(f"team {team}: {len(mine)} opps, win rate {len(won) / max(1, len(closed)):.0%}, "
                     f"won ${sum(r['Total_Amount'] for r in won):,.0f}")
    pushes = {}
    for h in tables["Opportunity_History"]:
        if h["Previous_Close_Date"] and h["Close_Date"] > h["Previous_Close_Date"] and h["Opportunity_Stage"] not in ("Closed Won", "Closed Lost"):
            rep = users[next_opp_owner(tables, h["Opportunity"])]
            pushes[rep] = pushes.get(rep, 0) + 1
    top = sorted(pushes.items(), key=lambda x: -x[1])[:3]
    lines.append("most pushes: " + ", ".join(f"{k} {v}" for k, v in top))
    no_act = [r for r in o if r["Is_Closed"] == "false" and not r["Last_Activity_Date"]]
    lines.append(f"open deals with no activity: {len(no_act)}")
    leads = tables["Lead"]
    for src in LEAD_SOURCES:
        ls = [l for l in leads if l["Lead_Source"] == src]
        lines.append(f"  leads {src}: {len(ls)}, converted {sum(l['Is_Converted'] == 'true' for l in ls) / max(1, len(ls)):.0%}")
    return "\n".join(lines)


_owner_cache = {}


def next_opp_owner(tables, oid):
    if not _owner_cache:
        _owner_cache.update({r["Opportunity_Id"]: r["OwnerUser"] for r in tables["Opportunity"]})
    return _owner_cache[oid]


def write_csvs(out_dir, today=None):
    contract = json.load(open(CONTRACT))
    tables = generate(today)
    errs = validate(tables, contract)
    if errs:
        raise SystemExit("generate: data failed validation:\n  " + "\n  ".join(errs))
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    for t, spec in contract.items():
        cols = [f["name"] for f in spec["fields"]]
        types = {f["name"]: f["dataType"] for f in spec["fields"]}
        path = os.path.join(out_dir, f"{spec['schema']}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(cols)
            for r in tables[t]:
                w.writerow([_fmt(r.get(c), types[c]) for c in cols])
        paths[t] = path
    print(summary(tables))
    print(f"wrote {len(paths)} CSVs to {out_dir}")
    return paths
