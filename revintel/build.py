"""plan: generate the story locally, print story stats, write CSVs + plan.json to out/."""

import collections
import csv
import json
import os
import sys
from datetime import date

from revintel.config import C, DEMO_DIR, FIELDS, OUT  # noqa: E402
from revintel import generate as G  # noqa: E402


def load_pool():
    path = os.path.join(DEMO_DIR, "pool_seed.json")
    return json.load(open(path)) if os.path.exists(path) else []


def write_csv(name, rows):
    os.makedirs(OUT, exist_ok=True)
    cols = sorted({k for r in rows for k in r if not k.startswith("_")})
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def story_stats(d):
    """Story check: counts, win rate, churn by segment by half-year, open renewals, co-terms,
    product churn and whitespace. Returned as a dict (web UI / --json) and printed."""
    o, li = d["opportunities"], d["line_items"]
    seg = {a["Id"]: a["_seg"] for a in d["accounts"]}
    renewal = C.RT["renewal"]
    closed = [x for x in o if x["StageName"] in ("Closed Won", "Closed Lost")]
    nb = [x for x in closed if x["RecordTypeId"] != renewal]
    churn = collections.defaultdict(lambda: collections.defaultdict(int))
    for x in o:
        if x["RecordTypeId"] == renewal and x["StageName"].startswith("Closed"):
            h = x["CloseDate"][:4] + ("H1" if int(x["CloseDate"][5:7]) <= 6 else "H2")
            churn[seg[x["AccountId"]]][h] += sum(x.get(FIELDS[k] or "", 0) or 0 for k in ("product_churn", "closed_lost_atr"))
    halves = sorted({h for v in churn.values() for h in v})
    open_r = collections.defaultdict(collections.Counter)
    for x in o:
        if x["RecordTypeId"] == renewal and not x["StageName"].startswith("Closed"):
            open_r[seg[x["AccountId"]]][x["StageName"]] += 1
    live = {x["Demo_External_ID__c"]: x["AccountId"] for x in o if x["StageName"] != "Closed Lost"}
    pen = collections.defaultdict(set)
    for x in li:
        if x["_opp_ext"] in live and x["UnitPrice"] > 0:
            pen[x["_product"]].add(live[x["_opp_ext"]])
    stats = {
        "anchor_date": d["today"],
        "counts": {k: len(v) for k, v in d.items() if isinstance(v, list)},
        "win_rate": {"all": round(sum(x["StageName"] == "Closed Won" for x in closed) / max(1, len(closed)), 3),
                     "new_and_expansion": round(sum(x["StageName"] == "Closed Won" for x in nb) / max(1, len(nb)), 3)},
        "close_dates": [min(x["CloseDate"] for x in o), max(x["CloseDate"] for x in o)] if o else [],
        "churn_by_segment_half": {s: {h: churn[s][h] for h in halves} for s in C.SEGMENTS},
        "open_renewals_by_segment": {s: dict(open_r[s]) for s in C.SEGMENTS},
        "co_termed_open_renewals": sum("Co-termed" in x.get("Description", "") for x in o),
        "products_dropped": dict(collections.Counter(x["_product"] for x in li if "Dropped at renewal" in x["Description"])),
        "whitespace_accounts_per_product": {p: len(pen[p]) for p in C.PRODUCTS},
    }
    print(stats["counts"])
    print(f"win rate: all {stats['win_rate']['all']:.0%}, new/expansion {stats['win_rate']['new_and_expansion']:.0%}")
    print("close dates:", " → ".join(stats["close_dates"]))
    print("\nchurn $ (Closed Lost ATR + Product Churn ACV) by segment, by half:")
    print("  " + " " * 9 + "".join(f"{h:>10}" for h in halves))
    for s_ in C.SEGMENTS:
        print(f"  {s_:<9}" + "".join(f"{churn[s_][h] / 1000:>9.0f}K" for h in halves))
    print("\nopen renewals by segment:")
    for s_ in C.SEGMENTS:
        print(f"  {s_:<9}", dict(open_r[s_]))
    print("\nco-termed open renewals (>90 days):", stats["co_termed_open_renewals"])
    print("products dropped on won renewals:", stats["products_dropped"])
    print("whitespace – accounts owning each product:", stats["whitespace_accounts_per_product"])
    return stats


def build_date():
    """Anchor incremental runs to the original build date so the plan matches what's in the
    org. A date refresh (reset → apply --today) deliberately re-anchors to today."""
    cp = os.path.join(OUT, "checkpoint.json")
    if "--today" in sys.argv or not os.path.exists(cp):
        return date.today()
    return date.fromisoformat(json.load(open(cp)).get("build_date") or date.today().isoformat())


def validate(pool):
    """Fail early, in plain words, on an unfilled or inconsistent config (template placeholders,
    unknown keys). Returns a list of problems; empty = OK."""
    problems = []
    def placeholder(v):
        return isinstance(v, str) and "<" in v and ">" in v
    for name in ("ORG_ALIAS", "EXT_PREFIX", "STD_PRICEBOOK", "CORE_PRODUCT", "TERRITORY_MODEL"):
        if placeholder(getattr(C, name, "<missing>")):
            problems.append(f"{name} is not set")
    for k, v in getattr(C, "RT", {}).items():
        if placeholder(v):
            problems.append(f"RT['{k}'] is not set")
    if not getattr(C, "PRODUCTS", {}):
        problems.append("PRODUCTS is empty")
    elif getattr(C, "CORE_PRODUCT", None) not in C.PRODUCTS:
        problems.append(f"CORE_PRODUCT {getattr(C, 'CORE_PRODUCT', None)!r} isn't a PRODUCTS key")
    if not getattr(C, "SEGMENTS", {}):
        problems.append("SEGMENTS is empty")
    people = set(getattr(C, "USERS", {})) | {u[0] for u in getattr(C, "NEW_USERS", [])}
    for seg, S in getattr(C, "SEGMENTS", {}).items():
        if S.get("owner") not in people:
            problems.append(f"segment {seg}: owner {S.get('owner')!r} isn't in USERS or NEW_USERS")
        if S.get("territory") not in getattr(C, "TERRITORIES", {}):
            problems.append(f"segment {seg}: territory {S.get('territory')!r} isn't in TERRITORIES")
    entries = list(pool) + list(getattr(C, "EXTRA_POOL", []))
    if not entries:
        problems.append("no pool accounts (pool_seed.json / EXTRA_POOL)")
    for e in entries:
        if "segment" in e and e["segment"] not in getattr(C, "SEGMENTS", {}):
            problems.append(f"pool account {e.get('name')}: unknown segment {e['segment']!r}")
    return problems


def plan(today=None, json_out=False):
    problems = validate(load_pool())
    if problems:
        raise SystemExit("Config isn't ready:\n  - " + "\n  - ".join(problems))
    today = today or build_date()
    print(f"(plan anchored to {today})")
    d = G.generate(load_pool(), today)
    stats = story_stats(d)
    for k in ("accounts", "opportunities", "line_items", "contacts", "tasks", "events"):
        write_csv(f"{k}.csv", d[k])
    json.dump(d, open(os.path.join(OUT, "plan.json"), "w"), indent=1, default=str)
    json.dump(stats, open(os.path.join(OUT, "story_stats.json"), "w"), indent=1)
    if json_out:
        print(json.dumps(stats))
    print(f"\nCSVs + plan.json written to {OUT} (nothing sent to the org)")
    return d
