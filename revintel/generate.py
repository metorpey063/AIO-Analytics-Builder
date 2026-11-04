"""Deterministic CRM history generator for Revenue Intelligence demos (no org calls).

generate(pool, today) -> dict of record lists. Same seed + same anchor date = same story,
so refreshing dates is just reset + regenerate anchored to a new today. Everything
customer-specific comes from the demo folder's config (see revintel/config_template.py);
defaults reproduce the KnowBe4 build.
"""

import calendar
import json
import os
import random
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sales_insights_data_gen import FIRST_NAMES, LAST_NAMES  # noqa: E402

from revintel.config import C, DEMO_DIR, FIELDS, NB_STAGES, OPP_TYPES, RENEWAL_STAGES, opt  # noqa: E402

_lr = os.path.join(DEMO_DIR, "loss_reasons.json")
LOSS_REASONS = json.load(open(_lr)) if os.path.exists(_lr) else {}   # Primary -> valid Secondary values

CORE = C.CORE_PRODUCT                               # always held; seat add-ons, contraction and upsell use it
CHURN_PRODUCT = opt("CHURN_PRODUCT", None)          # dropped on renewals whenever held (the product-churn story)
LAUNCHED = opt("LAUNCHED_PRODUCTS", {})             # product -> months since launch (can't be sold before)
PIPELINE_PRODUCTS = opt("PIPELINE_PRODUCTS", list(C.EXPANSION_WEIGHTS))   # gap-fill pipeline: first not owned
PIPELINE_FALLBACK = opt("PIPELINE_FALLBACK", PIPELINE_PRODUCTS[-1] if PIPELINE_PRODUCTS else CORE)
CORE_TIERS = opt("CORE_TIERS", {})                 # Account.Type -> tier label on the core product
CUSTOMER_LABEL = opt("CUSTOMER_LABEL", "Customer")
SEAT_ADDON_NEXT_STEP = opt("SEAT_ADDON_NEXT_STEP", "Hand off to CSM; provision the new users.")
TASK_SUBJECTS = opt("TASK_SUBJECTS", ["Call – renewal check-in", "Email – usage report",
                                      "Call – adoption review", "Email – renewal quote"])
EVENT_SUBJECTS = opt("EVENT_SUBJECTS", {"upcoming": "QBR – programme review", "past": "Renewal planning meeting"})
COMMENTARY = opt("COMMENTARY", {})                  # secondary loss reason -> commentary text


def fx(**kw):
    """Map logical renewal fields (atr, product_churn, …) to the org's field names, skipping
    fields the org doesn't have (FIELDS value None) and empty values."""
    return {FIELDS[k]: v for k, v in kw.items() if FIELDS.get(k) and v not in (None, "")}


def add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def signal_ramp(d, today, onset, duration, shape="accelerating"):
    months_from_onset = months_between(today, d) - onset
    if months_from_onset <= 0:
        return 0.0
    progress = min(1.0, months_from_onset / duration)
    return progress ** 2 if shape == "accelerating" else progress


def p_signal(kind, d, today, mult):
    """Probability for a signal at date d. Counter-trend segments (mult < 0) get no baseline,
    so a random large loss can't hide the story."""
    s = C.SIGNAL[kind]
    base = s["base"] if mult > 0 else 0.0
    return max(0.0, min(s.get("cap", 0.6), base + s["mag"] * signal_ramp(d, today, s["onset"], s["duration"]) * mult))


def draw(*key):
    """Stable uniform draw per (account, renewal, outcome) — tuning one rule doesn't reshuffle the rest."""
    return random.Random("|".join(map(str, (C.SEED,) + key))).random()


def iso_dt(d, hour=15):
    return datetime(d.year, d.month, d.day, hour, 0, 0).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def r100(x):
    return int(round(x / 100.0)) * 100


def pick_weighted(rng, weights):
    items = list(weights)
    return rng.choices(items, weights=[weights[i] for i in items], k=1)[0]


def pick_reason(rng, seg):
    mix = C.SEGMENTS[seg]["reasons"]
    primary = rng.choices(list(mix), weights=[v[0] for v in mix.values()], k=1)[0]
    secondary = rng.choice(mix[primary][1])
    assert not LOSS_REASONS or secondary in LOSS_REASONS.get(primary, []), (primary, secondary)
    return primary, secondary




def fill_gaps(accounts, opps, olis, today):
    """Every pool account gets a won deal this calendar year (EAM YTD Spend) and open
    pipeline (EAM Pipeline). Appended with their own ext ids and stable draws, so the
    main history above is unchanged."""
    renewal = C.RT["renewal"]
    jan1 = date(today.year, 1, 1)
    by_acct = {}
    for o in opps:
        by_acct.setdefault(o["AccountId"], []).append(o)
    lines_by_opp = {}
    for li in olis:
        lines_by_opp.setdefault(li["_opp_ext"], []).append(li)
    for acct in accounts:
        mine = by_acct.get(acct["Id"], [])
        S = C.SEGMENTS[acct["_seg"]]
        owner, base = acct["OwnerId"], acct["Demo_External_ID__c"][-3:]
        held = {li["_product"]: li["UnitPrice"] for o in mine if o["StageName"] == "Closed Won"
                for li in lines_by_opp.get(o["Demo_External_ID__c"], []) if li["UnitPrice"] > 0}
        seats = int(round(acct["NumberOfEmployees"] * .9, -1))

        def add(suffix, name, stage, close, created, prod, price, desc, next_step):
            ext = f"{C.EXT_PREFIX}-{base}-{suffix}"
            opps.append({"Demo_External_ID__c": ext, "Name": name, "AccountId": acct["Id"],
                         "RecordTypeId": C.RT["new"], "Type": OPP_TYPES["addon"], "StageName": stage,
                         "CloseDate": close.isoformat(), "CreatedDate": iso_dt(created), "OwnerId": owner,
                         "Territory2": S["territory"], "Pricebook2Id": C.STD_PRICEBOOK, "CurrencyIsoCode": "USD",
                         "Description": desc, "NextStep": next_step})
            olis.append({"_opp_ext": ext, "PricebookEntryId": C.PRODUCTS[prod]["pbe"], "Quantity": 1,
                         "UnitPrice": price, "ServiceDate": add_months(close, 12).isoformat(),
                         "Description": f"{product_label(prod, acct)} – {desc}", "_product": prod})

        won_ytd = any(o["StageName"] == "Closed Won" and o["CloseDate"] >= jan1.isoformat() for o in mine)
        if not won_ytd and (today - jan1).days > 20:
            close = jan1 + timedelta(days=int(draw(acct["Id"], "ytd") * ((today - jan1).days - 15)) + 5)
            add_seats = int(round(seats * (.08 + .12 * draw(acct["Id"], "ytd_seats")), -1))
            price = r100(held.get(CORE, C.PRODUCTS[CORE]["list"]) * add_seats / max(seats, 1))
            add("Y1", f"{acct['Name']} – {C.PRODUCTS[CORE]['label']} Seat Add-On {close.year}", "Closed Won", close,
                close - timedelta(days=21), CORE, max(price, 1200),
                f"{add_seats:,} additional users (co-termed to renewal)", SEAT_ADDON_NEXT_STEP)

        has_open = any(not o["StageName"].startswith("Closed") for o in mine)
        if not has_open:
            prod = next((p for p in PIPELINE_PRODUCTS if p not in held), PIPELINE_FALLBACK)
            days = 20 + int(draw(acct["Id"], "pipe") * 100)
            stage = NB_STAGES["late"] if days < 45 else NB_STAGES["mid"] if days < 90 else NB_STAGES["early"]
            scale = (acct["NumberOfEmployees"] / 2000.0) ** 0.85
            add("P1", f"{acct['Name']} – {C.PRODUCTS[prod]['label']} Expansion", stage, today + timedelta(days=days),
                today - timedelta(days=10 + int(draw(acct["Id"], "pipe_c") * 30)), prod,
                r100(C.PRODUCTS[prod]["list"] * scale * .9), f"{seats:,} {C.UNIT[prod]}",
                C.NEXT_STEPS[stage].format(lead=C.PRODUCTS[prod]["label"], add=C.PRODUCTS[prod]["label"])[:255])


def fill_recent_bookings(accounts, opps, olis, today, months_back=3, types=None, tag="M",
                         scale=1.0, count_types=None, min_need=2000):
    """Annual renewals make monthly bookings lumpy, and Revenue Insights defaults to Previous
    Month. Give each rep add-on wins in each of the last N months (and month-to-date) close to
    their usual monthly expansion rate, so recent attainment isn't 0% by accident of the calendar."""
    types = types or (OPP_TYPES["addon"],)
    by_owner = {}
    for a in accounts:
        by_owner.setdefault(a["OwnerId"], []).append(a)
    start = add_months(date(today.year, today.month, 1), -12)
    for owner, accts in by_owner.items():
        exp = [o for o in opps if o["OwnerId"] == owner and o["Type"] in types
               and o["StageName"] == "Closed Won" and start.isoformat() <= o["CloseDate"] < today.isoformat()]
        amt = {o["Demo_External_ID__c"]: sum(li["UnitPrice"] for li in olis if li["_opp_ext"] == o["Demo_External_ID__c"]) for o in exp}
        target = scale * sum(amt.values()) / 12.0
        counted = [o for o in opps if o["OwnerId"] == owner and o["StageName"] == "Closed Won"
                   and o["Type"] in (count_types or types)]
        if not target:
            continue
        for back in range(months_back, -1, -1):
            m0 = add_months(date(today.year, today.month, 1), -back)
            m1 = add_months(m0, 1) - timedelta(days=1) if back else today - timedelta(days=1)
            if m1 < m0:
                continue
            frac = 1.0 if back else (today - m0).days / 30.0
            have = sum(sum(li["UnitPrice"] for li in olis if li["_opp_ext"] == o["Demo_External_ID__c"])
                       for o in counted if m0.isoformat() <= o["CloseDate"] <= m1.isoformat())
            need = target * frac * (0.9 + 0.4 * draw(owner, m0, "book")) - have
            if need < min_need:
                continue
            acct = accts[int(draw(owner, m0, "acct") * len(accts))]
            S = C.SEGMENTS[acct["_seg"]]
            close = m0 + timedelta(days=int(draw(owner, m0, "day") * max(1, (m1 - m0).days)))
            seats = max(10, int(round(need / max(1, C.PRODUCTS[CORE]["list"] / 2000), -1)))
            ext = f"{C.EXT_PREFIX}-{acct['Demo_External_ID__c'][-3:]}-{tag}{m0:%y%m}"
            opps.append({"Demo_External_ID__c": ext, "Name": f"{acct['Name']} – {C.PRODUCTS[CORE]['label']} Seat Add-On {m0:%b %Y}",
                         "AccountId": acct["Id"], "RecordTypeId": C.RT["new"], "Type": OPP_TYPES["addon"],
                         "StageName": "Closed Won", "CloseDate": close.isoformat(),
                         "CreatedDate": iso_dt(close - timedelta(days=14)), "OwnerId": owner,
                         "Territory2": S["territory"], "Pricebook2Id": C.STD_PRICEBOOK, "CurrencyIsoCode": "USD",
                         "Description": f"{OPP_TYPES['addon']}: {seats:,} additional {C.PRODUCTS[CORE]['label']} users.",
                         "NextStep": SEAT_ADDON_NEXT_STEP})
            olis.append({"_opp_ext": ext, "PricebookEntryId": C.PRODUCTS[CORE]["pbe"], "Quantity": 1,
                         "UnitPrice": r100(need), "ServiceDate": add_months(close, 12).isoformat(),
                         "Description": f"{product_label(CORE, acct)} – {seats:,} additional users", "_product": CORE})


def product_label(prod, acct):
    label = C.PRODUCTS[prod]["label"]
    tier = CORE_TIERS.get(acct["Type"]) if prod == CORE else None
    return f"{label} {tier}" if tier else label


def assign_pool(pool, rng):
    """Map each pool account to (segment, Account.Type) and re-skinned fields.

    Generic pool entries carry everything explicitly (segment, type, name, country, state,
    city, industry — the EXTRA_POOL format). The KnowBe4 build used a legacy layout
    (EMEA_RESKIN + SEGMENT_SIZES) that's kept so its history stays identical."""
    if not hasattr(C, "EMEA_RESKIN"):
        accounts = []
        add_explicit_pool(accounts, pool, rng)
        add_extra_pool(accounts)
        apply_owner_splits(accounts)
        return accounts
    emea = [a for a in pool if a["name"] in C.EMEA_RESKIN]
    namr = [a for a in pool if a["name"] not in C.EMEA_RESKIN]
    assert len(emea) == 20 and len(namr) == 35, (len(emea), len(namr))
    rng.shuffle(namr)
    rng.shuffle(emea)
    out = []
    for group, sizes in ((namr, C.SEGMENT_SIZES), (emea, C.EMEA_SIZES)):
        i = 0
        for seg, n, typ in sizes:
            for a in group[i:i + n]:
                out.append((a, seg, typ))
            i += n
    accounts = []
    for idx, (a, seg, typ) in enumerate(sorted(out, key=lambda t: t[0]["name"]), start=1):
        lo, hi = C.EMPLOYEES[typ]
        emp = rng.randint(lo, hi)
        if a["name"] in C.EMEA_RESKIN:
            name, country, city = C.EMEA_RESKIN[a["name"]]
            state = ""
        else:
            name = a["name"]
            country, state, city = rng.choice(C.NAMR_LOCATIONS)
        accounts.append({
            "Id": a["id"], "Name": name, "Industry": a["industry"], "Type": typ,
            "NumberOfEmployees": emp, "AnnualRevenue": r100(emp * rng.uniform(150000, 320000)),
            "BillingCountry": country, "BillingState": state, "BillingCity": city,
            "OwnerId": user_id(C.SEGMENTS[seg]["owner"]),
            "Demo_External_ID__c": f"{C.POOL_PREFIX}-{idx:03d}",
            "Description": f"{CUSTOMER_LABEL} customer · {C.SEGMENTS[seg]['region']} {typ}",
            "_seg": seg, "_orig_name": a["name"],
        })
    add_extra_pool(accounts)
    apply_owner_splits(accounts)
    return accounts


def user_id(key):
    """Org user Id for a USERS key (placeholder until `revintel team people` creates a new user)."""
    return C.USERS.get(key, f"<new user: {key}>")


def add_extra_pool(accounts):
    """Accounts added after the first build (EXTRA_POOL) — appended with their own rng so
    the original pool's generated history is unchanged."""
    add_explicit_pool(accounts, getattr(C, "EXTRA_POOL", []), random.Random(C.SEED + 1))


def add_explicit_pool(accounts, entries, rng):
    for e in entries:
        S = C.SEGMENTS[e["segment"]]
        lo, hi = S.get("employees") or C.EMPLOYEES[e["type"]]
        emp = rng.randint(lo, hi)
        accounts.append({
            "Id": e["id"], "Name": e["name"], "Industry": e["industry"], "Type": e["type"],
            "NumberOfEmployees": emp, "AnnualRevenue": r100(emp * rng.uniform(150000, 320000)),
            "BillingCountry": e["country"], "BillingState": e["state"], "BillingCity": e["city"],
            "OwnerId": user_id(S["owner"]),
            "Demo_External_ID__c": f"{C.POOL_PREFIX}-{len(accounts) + 1:03d}",
            "Description": f"{CUSTOMER_LABEL} customer · {S['region']} {e['type']}",
            "_seg": e["segment"], "_orig_name": e.get("orig_name", ""),
        })


def apply_owner_splits(accounts):
    """Hybrid leads carry their own book: the N largest accounts of a segment move to them."""
    for seg, (lead, n) in getattr(C, "OWNER_SPLITS", {}).items():
        mine = sorted((a for a in accounts if a["_seg"] == seg), key=lambda a: -a["NumberOfEmployees"])
        for a in mine[:n]:
            a["OwnerId"] = user_id(lead)


def generate(pool, today=None):
    today = today or date.today()
    rng = random.Random(C.SEED)
    accounts = assign_pool(pool, rng)
    opps, olis, contacts, tasks, events, terr_assoc = [], [], [], [], [], []

    for acct in accounts:
        seg = acct["_seg"]
        S = C.SEGMENTS[seg]
        owner = acct["OwnerId"]
        mult = S["mult"]
        scale = (acct["NumberOfEmployees"] / 2000.0) ** 0.85
        coupled = rng.random() < S["coupled_p"]
        terr_assoc.append({"ObjectId": acct["Id"], "Territory2": S["territory"]})
        seq = [0]

        def new_opp(name, rt, typ, stage, close, created, lines, **extra):
            seq[0] += 1
            ext = f"{C.EXT_PREFIX}-{acct['Demo_External_ID__c'][-3:]}-{seq[0]:02d}"
            o = {"Demo_External_ID__c": ext, "Name": name, "AccountId": acct["Id"],
                 "RecordTypeId": C.RT[rt], "Type": typ, "StageName": stage,
                 "CloseDate": close.isoformat(), "CreatedDate": iso_dt(min(created, today - timedelta(days=1))),
                 "OwnerId": owner, "Territory2": S["territory"], "Pricebook2Id": C.STD_PRICEBOOK,
                 "CurrencyIsoCode": "USD"}
            o.update({k: v for k, v in extra.items() if v not in (None, "")})
            prods = sorted((p for p, *_ in lines), key=lambda p: (p != CORE, -dict((l[0], l[1]) for l in lines)[p]))
            labels = ", ".join(product_label(p, acct) for p in prods)
            add = next((p for p in C.EXPANSION_WEIGHTS if p not in prods), PIPELINE_FALLBACK)
            o["NextStep"] = C.NEXT_STEPS.get(stage, "").format(
                lead=C.PRODUCTS[prods[0]]["label"], add=C.PRODUCTS[add]["label"])[:255]
            if rt == "renewal":
                summary = f"Annual renewal: {labels}. {seats:,} users. ATR ${extra.get(FIELDS['atr'] or '') or 0:,.0f}."
            else:
                summary = f"{typ}: {labels} for {seats:,} users."
            o["Description"] = (summary + " " + o.get("Description", "")).strip()
            opps.append(o)
            for prod, price, end, desc in lines:
                desc = f"{product_label(prod, acct)} – {seats:,} {C.UNIT[prod]}" + (f" · {desc}" if desc else "")
                olis.append({"_opp_ext": ext, "PricebookEntryId": C.PRODUCTS[prod]["pbe"], "Quantity": 1,
                             "UnitPrice": price, "ServiceDate": end.isoformat() if end else "",
                             "Description": desc, "_product": prod})
            return o

        # ── initial contract ──
        focus = seg in C.FOCUS["segments"]
        if focus:
            window_end = add_months(date(today.year, today.month, 1), C.FOCUS["months_ahead"] + 1) - timedelta(days=1)
            target = today + timedelta(days=rng.randint(3, (window_end - today).days))
            start = add_months(target, -12 * rng.randint(1, 2))
        else:
            start = add_months(today, -rng.randint(13, 35)) - timedelta(days=rng.randint(0, 27))
        seats = int(round(acct["NumberOfEmployees"] * rng.uniform(.85, 1.0), -1))
        held = {CORE: r100(C.PRODUCTS[CORE]["list"] * scale * rng.uniform(.9, 1.05))}
        for prod, p in {**C.ATTACH[acct["Type"]], **S.get("attach", {})}.items():
            if rng.random() < p:
                held[prod] = r100(C.PRODUCTS[prod]["list"] * scale * rng.uniform(.9, 1.05))
        end = {p: add_months(start, 12) for p in held}
        new_opp(f"{acct['Name']} – {OPP_TYPES['new']} {start.year}", "new", OPP_TYPES["new"], "Closed Won",
                start, start - timedelta(days=rng.randint(45, 120)),
                [(p, v, end[p], "") for p, v in held.items()])

        churned = False
        k = 1
        while not churned:
            anniv = add_months(start, 12 * k)
            prev = add_months(start, 12 * (k - 1))
            if anniv > today + timedelta(days=300):
                break

            # ── mid-term expansions (whitespace closes; counter-trend in NAMR ENT) ──
            for attempt in range(2):
                if rng.random() >= S["expansion_p"] * (1 if attempt == 0 else .7):
                    continue
                close = prev + timedelta(days=rng.randint(60, 160) + 140 * attempt)
                avail = {p: w for p, w in C.EXPANSION_WEIGHTS.items() if p not in held
                         and not (p in LAUNCHED and close < add_months(today, -LAUNCHED[p]))}
                for p, factor in S.get("boost", {}).items():   # e.g. counter-trend segment adopting a new product
                    if p in avail:
                        avail[p] *= factor
                if avail and close <= today + timedelta(days=180):
                    prod = pick_weighted(rng, avail)
                    price = r100(C.PRODUCTS[prod]["list"] * scale * rng.uniform(.85, 1.0))
                    created = close - timedelta(days=rng.randint(30, 90))
                    name = f"{acct['Name']} – {C.PRODUCTS[prod]['label']} Expansion"
                    if close < today:
                        won = rng.random() < S.get("expansion_win_p", .4)
                        new_opp(name, "new", OPP_TYPES["addon"], "Closed Won" if won else "Closed Lost",
                                close, created, [(prod, price, add_months(close, 12), "")])
                        if won:
                            held[prod] = price
                            # coupled accounts keep the product's own end date (GTM 2024 co-term story)
                            end[prod] = add_months(close, 12) if coupled else anniv
                    else:
                        days = (close - today).days
                        stage = NB_STAGES["late"] if days < 45 else NB_STAGES["mid"] if days < 100 else NB_STAGES["early"]
                        new_opp(name, "new", OPP_TYPES["addon"], stage, close, created,
                                [(prod, price, add_months(close, 12), "")])

            atr = sum(held.values())
            rname = f"{acct['Name']} – Renewal {anniv:%b %Y}"
            created = anniv - timedelta(days=120)

            if anniv <= today - timedelta(days=30):
                # ── closed renewal ──
                if draw(acct["Id"], k, "churn") < p_signal("churn", anniv, today, mult):
                    prim, sec = pick_reason(rng, seg)
                    close = anniv + timedelta(days=rng.randint(0, 30))
                    new_opp(rname, "renewal", OPP_TYPES["renewal"], "Closed Lost", close, created,
                            [(p, v, end[p], "Not renewed") for p, v in held.items()],
                            **fx(atr=atr, closed_lost_atr=atr, primary_reason=prim, secondary_reason=sec,
                                 commentary=COMMENTARY.get(sec, "")),
                            Description="Full churn: all products lost at renewal.")
                    churned = True
                    break
                dropped = None
                if len(held) > 1 and draw(acct["Id"], k, "drop") < p_signal("drop", anniv, today, mult):
                    # the churn product is dropped whenever it's held (KnowBe4 BRD: "renew KSAT, drop Defend")
                    dropped = CHURN_PRODUCT if CHURN_PRODUCT in held else \
                        pick_weighted(rng, {p: w for p, w in C.DROP_WEIGHTS.items() if p in held})
                contract = draw(acct["Id"], k, "contraction") < p_signal("contraction", anniv, today, mult)
                upsell = rng.random() < S.get("renewal_upsell_p", .15)
                lines, new_held, lost = [], {}, 0
                for p, v in held.items():
                    if p == dropped:
                        lines.append((p, 0, end[p], f"Dropped at renewal – product churn (ATR ${v:,})"))
                        continue
                    nv = v * rng.uniform(1.02, 1.06)
                    note = "Renewed"
                    if contract and p == CORE:
                        nv = v * rng.uniform(.70, .88)
                        note = f"Contraction – seats reduced (ATR ${v:,})"
                        lost += v - nv
                    elif upsell and p == CORE:
                        nv = v * rng.uniform(1.08, 1.25)
                        note = "Upsell – seats added"
                    nv = r100(nv)
                    new_held[p] = nv
                    lines.append((p, nv, end[p], note))
                churn_acv = held[dropped] if dropped else None
                extra = fx(atr=atr, product_churn=churn_acv)
                if ((churn_acv or 0) + lost) / atr >= C.REASON_THRESHOLD:
                    prim, sec = pick_reason(rng, seg)
                    extra.update(fx(primary_reason=prim, secondary_reason=sec, commentary=COMMENTARY.get(sec, "")))
                if dropped:
                    extra["Description"] = (f"Renewed with product churn: {C.PRODUCTS[dropped]['label']} "
                                            f"dropped (${churn_acv:,} ATR).")
                close = anniv - timedelta(days=rng.randint(0, 20)) if rng.random() < .7 \
                    else anniv + timedelta(days=rng.randint(1, 45))   # grace period
                new_opp(rname, "renewal", OPP_TYPES["renewal"], "Closed Won", close, created, lines, **extra)
                held = new_held
                for p in held:
                    end[p] = add_months(end[p], 12)
            else:
                # ── open renewal ──
                days = (anniv - today).days
                extra = fx(atr=atr)
                uplift = rng.uniform(1.0, 1.07)
                lines = [(p, r100(v * uplift), end[p], "") for p, v in held.items()]
                close = anniv
                risk = C.SIGNAL["risk"]
                p_risk = (C.FOCUS["counter_trend_risk_p"] if focus else 0.0) if mult < 0 \
                    else risk["base"] + risk["mag"] * mult
                if focus:   # forecast demo: mostly healthy pipeline with a few at-risk calls
                    p_risk = min(p_risk, C.FOCUS["max_risk_p"])
                at_risk = days <= risk["horizon_days"] and draw(acct["Id"], k, "risk") < p_risk
                if at_risk:
                    stage = pick_weighted(rng, S["risk_mix"])
                    prim, sec = pick_reason(rng, seg)
                    extra.update(fx(primary_reason=prim, secondary_reason=sec, commentary=COMMENTARY.get(sec, "")))
                    if stage == RENEWAL_STAGES["risk_contraction"]:
                        lines = [(p, r100(v * (.72 if p == CORE else 1.0)), e, "Expected seat reduction" if p == CORE else d)
                                 for p, v, e, d in lines]
                    elif stage == RENEWAL_STAGES["risk_timing"]:
                        close = anniv + timedelta(days=rng.randint(30, 60))
                        if focus:   # slips, but stays inside the Nov–Jan forecast window
                            close = min(close, window_end)
                else:
                    stage = (RENEWAL_STAGES["past_due"] if days <= 0 else
                             RENEWAL_STAGES["confirmed"] if days < 25 and draw(acct["Id"], k, "confirm") < .6 else
                             RENEWAL_STAGES["late"] if days < 55 else
                             RENEWAL_STAGES["mid"] if days < 80 else RENEWAL_STAGES["early"])
                    # Amount differs from ATR: seat growth on some, uplift on the rest
                    if draw(acct["Id"], k, "upsell") < C.FOCUS["upsell_p"]:
                        lines = [(p, r100(v * (rng.uniform(1.1, 1.3) if p == CORE else 1.0)), e,
                                  "Seat expansion at renewal" if p == CORE else d) for p, v, e, d in lines]
                # co-term flag (Ask 4 / R4.1): product end dates > 90 days from the renewal
                far = [(p, e) for p, v, e, d in lines if e and abs((e - anniv).days) > 90]
                lines = [(p, v, e, d or (f"Co-termed – own end date {e:%d %b %Y} ({abs((e - anniv).days)} days apart)"
                                        if (p, e) in far else "")) for p, v, e, d in lines]
                if close < today:   # anniversary passed but still open (grace period): expected close moves forward
                    close = today + timedelta(days=5 + int(draw(acct["Id"], k, "grace") * 20))
                if far:
                    p, e = far[0]
                    extra["Description"] = (f"Co-termed renewal: {C.PRODUCTS[p]['label']} ends {e:%d %b %Y}, "
                                            f"{abs((e - anniv).days)} days from the renewal date – needs decoupling (R4.1).")
                new_opp(rname, "renewal", OPP_TYPES["renewal"], stage, close,
                        min(created, today - timedelta(days=rng.randint(1, 20))), lines, **extra)
                break
            k += 1

        # ── contacts + activities (engagement drops first where churn follows) ──
        n_contacts = C.CONTACTS_PER_SEGMENT[acct["Type"]]
        domain = "".join(c for c in acct["Name"].lower() if c.isalnum())[:18] + \
            (".com" if acct["BillingCountry"] in ("United States", "Canada") else ".eu")
        acct_contacts = []
        for i in range(n_contacts):
            fn, ln = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            ce = {"_acct": acct["Id"], "FirstName": fn, "LastName": ln, "Title": C.CONTACT_TITLES[i % len(C.CONTACT_TITLES)],
                  "Email": f"{fn.lower()}.{ln.lower()}@{domain}", "OwnerId": owner,
                  "_key": f"{acct['Demo_External_ID__c']}-C{i + 1}"}
            contacts.append(ce)
            acct_contacts.append(ce)
        if churned:
            continue
        eng = S["engagement"]
        engaged = acct_contacts[:max(1, round(n_contacts * eng))]
        n_tasks = round(4 + 10 * eng)
        recent_gap = 5 if eng > .7 else 20 if eng > .5 else 50
        for t in range(n_tasks):
            d = today - timedelta(days=recent_gap + int((180 - recent_gap) * t / max(1, n_tasks - 1)) + rng.randint(0, 6))
            tasks.append({"_acct": acct["Id"], "_contact": rng.choice(engaged)["_key"], "OwnerId": owner,
                          "Subject": rng.choice(TASK_SUBJECTS),
                          "ActivityDate": d.isoformat(), "Status": "Completed", "Priority": "Normal"})
        if eng > .5:
            nd = today + timedelta(days=rng.randint(3, 21))
            tasks.append({"_acct": acct["Id"], "_contact": engaged[0]["_key"], "OwnerId": owner,
                          "Subject": "Call – renewal next steps", "ActivityDate": nd.isoformat(),
                          "Status": "Not Started", "Priority": "High"})
            ed = today + timedelta(days=rng.randint(5, 30))
            events.append({"_acct": acct["Id"], "_contact": engaged[0]["_key"], "OwnerId": owner,
                           "Subject": EVENT_SUBJECTS["upcoming"],
                           "StartDateTime": iso_dt(ed, 16), "EndDateTime": iso_dt(ed, 17)})
        pd = today - timedelta(days=recent_gap + rng.randint(10, 40))
        events.append({"_acct": acct["Id"], "_contact": engaged[0]["_key"], "OwnerId": owner,
                       "Subject": EVENT_SUBJECTS["past"], "StartDateTime": iso_dt(pd, 16),
                       "EndDateTime": iso_dt(pd, 17)})

    fill_gaps(accounts, opps, olis, today)
    fill_recent_bookings(accounts, opps, olis, today)
    # top-up to the rep's full non-renewal run rate (New Business + Add-On), which is what quotas use
    fill_recent_bookings(accounts, opps, olis, today, types=(OPP_TYPES["new"], OPP_TYPES["addon"]), tag="T")
    # floor: every rep books at least ~30% of their average month (renewals included) — matches the quota floor
    fill_recent_bookings(accounts, opps, olis, today, types=(OPP_TYPES["new"], OPP_TYPES["addon"], OPP_TYPES["renewal"]),
                         tag="F", scale=C.QUOTA_FLOOR, min_need=300)

    # Territory2 stays a developer name here; apply resolves it to an Id
    # (new territories don't exist until apply creates them).
    return {"today": today.isoformat(), "accounts": accounts, "opportunities": opps, "line_items": olis,
            "contacts": contacts, "tasks": tasks, "events": events, "territory_assoc": terr_assoc}
