"""Team, forecasting and quotas for a Revenue Intelligence demo.

    python3 -m revintel <demo> team people     # create new users + lead roles (before `apply`)
    python3 -m revintel <demo> team reassign   # move other demos' opps off the team; roles under CEO
    python3 -m revintel <demo> team quotas     # rebuild monthly quotas from the loaded book (after `apply`)

Revenue Insights shows the forecast managers of the sales leader's child roles, so LEAD_ROLES
decides who appears under the leader (aim for 7–9). Quotas: rep = renewal ATR due that month +
non-renewal run rate, never below QUOTA_FLOOR × the rep's average month, × STRETCH (story);
lead = own book + their reps; sales leader = sum of leads. Every step backs up to out/ first.
"""

import json
import os
from collections import defaultdict
from datetime import date

from revintel import apply as A
from revintel.config import C, FIELDS, OPP_TYPES, opt

U = C.USERS
CP_PATH = os.path.join(A.OUT, "team_checkpoint.json")
LEADER = opt("SALES_LEADER", "elliot")                 # USERS key of the sales leader (e.g. EVP Renewals)
LEADER_ROLE = opt("SALES_LEADER_ROLE", "VP of Sales")  # role whose children are the leads
CEO = opt("CEO", None)                                 # USERS key above the leader (quota = leader + others)
RENEWAL_RT = opt("RENEWAL_RECORD_TYPE", "Renewal")     # Opportunity record type developer name


def load_cp():
    return json.load(open(CP_PATH)) if os.path.exists(CP_PATH) else {"done": []}


def save_cp(cp):
    json.dump(cp, open(CP_PATH, "w"), indent=1)


def ids(users):
    return A.ids_in([U[u] for u in users])


def backup(name, rows):
    rows = [{k: v for k, v in r.items() if k != "attributes"} for r in rows]
    A.write_csv(os.path.join(A.OUT, f"backup_{name}.csv"), rows) if rows else None
    print(f"  {len(rows)} rows backed up → out/backup_{name}.csv")


def team_keys():
    return list(dict.fromkeys([LEADER] + list(C.LEADS) + [r for reps in C.LEADS.values() for r in reps]
                              + opt("EXTRA_TEAM", [])))


# ── reassign ────────────────────────────────────────────────────────────────
def s_reassign(cp):
    """Other demos' opps owned by team users inflate attainment — move them to OTHER_DEMO_OWNER."""
    target = opt("OTHER_DEMO_OWNER", None)
    if not target:
        print("  skipped (OTHER_DEMO_OWNER not set)")
        return
    rows = A.query("SELECT Id, Name, OwnerId FROM Opportunity WHERE OwnerId IN " + ids(team_keys()) +
                   f" AND (Demo_External_ID__c = null OR (NOT Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'))")
    backup("other_demo_opp_owners", rows)
    A.bulk("update", "Opportunity", [{"Id": r["Id"], "OwnerId": target} for r in rows], cols=["Id", "OwnerId"])


def s_roles_under_ceo(cp):
    """Roles that shouldn't roll up to the sales leader (e.g. channel) report to the CEO role."""
    names = opt("ROLES_UNDER_CEO", [])
    if not names:
        print("  skipped (ROLES_UNDER_CEO not set)")
        return
    roles = {r["Name"]: r for r in A.query("SELECT Id, Name, ParentRoleId FROM UserRole")}
    ceo_role = roles[opt("CEO_ROLE", "CEO")]["Id"]
    backup("roles_under_ceo", [dict(roles[n]) for n in names])
    for n in names:
        A.sf("data", "update", "record", "-s", "UserRole", "-i", roles[n]["Id"], "-v", f"ParentRoleId={ceo_role}")
        print(f"  {n} now reports to {opt('CEO_ROLE', 'CEO')}")


# ── people ──────────────────────────────────────────────────────────────────
def s_new_users(cp):
    """Create NEW_USERS (fictional personas; no welcome email). Ids saved to new_users.json."""
    path = os.path.join(A.HERE, "new_users.json")
    made = json.load(open(path)) if os.path.exists(path) else {}
    if not opt("NEW_USERS", []):
        print("  skipped (no NEW_USERS)")
        return
    me = A.query(f"SELECT Email FROM User WHERE Id = '{U[CEO or LEADER]}'")[0]
    profile = A.query(f"SELECT Id FROM Profile WHERE Name = '{opt('NEW_USER_PROFILE', 'SDO-Sales')}'")[0]["Id"]
    org = A.query("SELECT Id FROM Organization")[0]["Id"].lower()
    tag = opt("USER_TAG", C.EXT_PREFIX.split("-")[-1].lower())
    for key, first, last, title, tz in C.NEW_USERS:
        if key in made:
            continue
        username = f"{first}.{last}.{tag}@{org}.demo".lower()
        found = A.query(f"SELECT Id FROM User WHERE Username = '{username}'")
        if found:
            made[key] = found[0]["Id"]
        else:
            r = A.sf("data", "create", "record", "-s", "User", "-v",
                     f"FirstName='{first}' LastName='{last}' Username='{username}' Email='{me['Email']}' "
                     f"Alias='{(first[0] + last)[:8].lower()}' Title='{title}' ProfileId={profile} "
                     f"TimeZoneSidKey={tz} LocaleSidKey=en_US EmailEncodingKey=UTF-8 LanguageLocaleKey=en_US "
                     f"ForecastEnabled=true ManagerId={U[LEADER]}")
            made[key] = r["id"]
            print(f"  created {first} {last} ({title})")
        json.dump(made, open(path, "w"), indent=1)
    U.update(made)
    print("  new users:", made)


def s_lead_roles(cp):
    """One role per lead under the leader's role (forecast manager = lead); SUB_ROLES under a lead."""
    roles = {r["DeveloperName"]: r for r in A.query("SELECT Id, Name, DeveloperName, ParentRoleId FROM UserRole")}
    leader_role = next(r["Id"] for r in roles.values() if r["Name"] == LEADER_ROLE)
    backup("roles_before_lead_roles",
           A.query("SELECT Id, Name, UserRoleId, ManagerId FROM User WHERE Id IN " + ids(team_keys())))
    role_id = {}
    for name, dev, reuse, lead in C.LEAD_ROLES:
        if reuse and reuse in roles:
            rid = roles[reuse]["Id"]
            A.sf("data", "update", "record", "-s", "UserRole", "-i", rid, "-v", f"Name='{name}' ParentRoleId={leader_role}")
        elif dev in roles:
            rid = roles[dev]["Id"]
        else:
            rid = A.sf("data", "create", "record", "-s", "UserRole", "-v",
                       f"Name='{name}' DeveloperName={dev} ParentRoleId={leader_role} RollupDescription='{name}'")["id"]
            print(f"  created role {name}")
        role_id[lead] = rid
    for lead, rid in role_id.items():
        A.sf("data", "update", "record", "-s", "User", "-i", U[lead], "-v",
             f"UserRoleId={rid} ManagerId={U[C.MANAGERS.get(lead, LEADER)]} ForecastEnabled=true")
    for name, dev, parent_lead, members in opt("SUB_ROLES", []):
        rid = roles[dev]["Id"] if dev in roles else A.sf(
            "data", "create", "record", "-s", "UserRole", "-v",
            f"Name='{name}' DeveloperName={dev} ParentRoleId={role_id[parent_lead]} RollupDescription='{name}'")["id"]
        A.sf("data", "update", "record", "-s", "UserRole", "-i", rid, "-v", f"Name='{name}' ParentRoleId={role_id[parent_lead]}")
        for m in members:
            A.sf("data", "update", "record", "-s", "User", "-i", U[m], "-v", f"UserRoleId={rid} ManagerId={U[parent_lead]}")
    for lead, rid in role_id.items():   # forecast manager last: the user must already hold the role
        A.sf("data", "update", "record", "-s", "UserRole", "-i", rid, "-v", f"ForecastUserId={U[lead]}")
    print(f"  {len(role_id)} lead roles under {LEADER_ROLE}")


# ── quotas ──────────────────────────────────────────────────────────────────
def quota_months():
    y, m, n = opt("QUOTA_START", (date.today().year - 1, date.today().month)) + (opt("QUOTA_COUNT", 18),)
    return [(y + (m - 1 + i) // 12, (m - 1 + i) % 12 + 1) for i in range(n)]


def month_key(d):
    return (int(d[:4]), int(d[5:7]))


def books():
    """Per rep per month: renewal ATR due, non-renewal bookings, all won; per territory: ATR due."""
    owner_of = {v: k for k, v in U.items()}
    tid = {v: k for k, v in (A.load_cp().get("territory_ids") or {}).items()}
    atr, exp, won, terr = (defaultdict(float) for _ in range(4))
    f_atr = FIELDS["atr"]
    for o in A.query(f"SELECT OwnerId, CloseDate, {f_atr}, Amount, StageName, IsWon, Type, Territory2Id, "
                     f"RecordType.DeveloperName FROM Opportunity WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'"):
        rep, m = owner_of.get(o["OwnerId"]), month_key(o["CloseDate"])
        if o["IsWon"]:
            won[(rep, m)] += o["Amount"] or 0
        if o["RecordType"]["DeveloperName"] == RENEWAL_RT:
            atr[(rep, m)] += o[f_atr] or 0
            if o["Territory2Id"] in tid:
                terr[(tid[o["Territory2Id"]], m)] += o[f_atr] or 0
        elif o["Type"] in (OPP_TYPES["new"], OPP_TYPES["addon"]) and o["IsWon"] and o["CloseDate"] < date.today().isoformat():
            exp[(rep, m)] += o["Amount"] or 0
    return atr, exp, won, terr


def rep_quotas(atr, exp, won, months):
    q = {}
    for rep, stretch in C.STRETCH.items():
        exp_target = sum(exp[(rep, m)] for m in months[:13]) / 12.0
        floor = opt("QUOTA_FLOOR", 0.3) * sum(won[(rep, m)] for m in months[:13]) / 12.0
        for m in months:
            q[(rep, m)] = int(round(max(atr[(rep, m)] + exp_target, floor) * stretch, -3))
    return q


def s_quotas(cp):
    months = quota_months()
    ftypes = {r["DeveloperName"]: r["Id"] for r in A.query("SELECT Id, DeveloperName FROM ForecastingType WHERE IsActive = true")}
    role_types = [t for t in opt("ROLE_FORECAST_TYPES", ["OpportunityAmount"]) if t in ftypes]
    terr_type = opt("TERRITORY_FORECAST_TYPE", None)
    terr_type = terr_type if terr_type in ftypes else None
    people = list(C.STRETCH) + [LEADER] + ([CEO] if CEO else [])
    start, end = date(*months[0], 1).isoformat(), date(*months[-1], 1).isoformat()
    types = [ftypes[t] for t in role_types + ([terr_type] if terr_type else [])]
    old = A.query("SELECT Id, QuotaOwnerId, ForecastingTypeId, Territory2Id, StartDate, QuotaAmount FROM ForecastingQuota "
                  f"WHERE QuotaOwnerId IN {ids(people)} AND StartDate >= {start} AND StartDate <= {end} "
                  f"AND ForecastingTypeId IN {A.ids_in(types)}")
    backup("team_quotas", old)

    atr, exp, won, terr = books()
    q = rep_quotas(atr, exp, won, months)
    others = defaultdict(float)   # the CEO also carries other personas' existing quotas
    if CEO and opt("OTHER_QUOTA_OWNERS", []):
        for r in A.query("SELECT QuotaAmount, StartDate, ForecastingTypeId FROM ForecastingQuota "
                         f"WHERE QuotaOwnerId IN {A.ids_in(C.OTHER_QUOTA_OWNERS)} AND StartDate >= {start} AND StartDate <= {end}"):
            others[(r["ForecastingTypeId"], month_key(r["StartDate"]))] += r["QuotaAmount"] or 0
    sub_members = [m for _, _, _, members in opt("SUB_ROLES", []) for m in members]
    tids = A.load_cp().get("territory_ids") or {}
    parents = {t: v[1] for t, v in C.TERRITORIES.items()}
    leaves = [t for t in C.TERRITORIES if t not in parents.values()]

    rows = []
    for m in months:
        sd = date(*m, 1).isoformat()
        lead_q = {lead: q.get((lead, m), 0) + sum(q[(r, m)] for r in reps) for lead, reps in C.LEADS.items()}
        leader_q = sum(lead_q.values())
        for t in role_types:
            amounts = {**lead_q, **{r: q[(r, m)] for r in sub_members}, LEADER: leader_q}
            if CEO:
                amounts[CEO] = leader_q + int(others[(ftypes[t], m)])
            rows += [{"QuotaOwnerId": U[u], "ForecastingTypeId": ftypes[t], "StartDate": sd, "QuotaAmount": a,
                      "CurrencyIsoCode": "USD"} for u, a in amounts.items()]
        if terr_type:
            leaf = {t: int(round(terr[(t, m)], -3)) for t in leaves}
            def total(t):
                return leaf.get(t, 0) + sum(total(k) for k, p in parents.items() if p == t)
            for t in C.TERRITORIES:
                rows.append({"QuotaOwnerId": U[C.TERRITORIES[t][2]], "ForecastingTypeId": ftypes[terr_type],
                             "Territory2Id": tids[t], "StartDate": sd, "QuotaAmount": total(t), "CurrencyIsoCode": "USD"})

    A.bulk("delete", "ForecastingQuota", [{"Id": r["Id"]} for r in old], cols=["Id"])
    A.bulk("import", "ForecastingQuota", rows)
    cur = date(date.today().year, date.today().month, 1).isoformat()
    first = ftypes[role_types[0]] if role_types else None
    print("  this month's quotas:", {u: r["QuotaAmount"] for u in [LEADER] + list(C.LEADS)
                                     for r in rows if r["QuotaOwnerId"] == U[u] and r["ForecastingTypeId"] == first
                                     and r["StartDate"] == cur})


STEPS = [("reassign other demos' opps", s_reassign), ("roles under CEO", s_roles_under_ceo),
         ("new users", s_new_users), ("lead roles", s_lead_roles), ("quotas", s_quotas)]
PHASES = {"reassign": ["reassign other demos' opps", "roles under CEO"],
          "people": ["new users", "lead roles"], "quotas": ["quotas"]}
ALWAYS_RERUN = {"quotas"}   # depends on the loaded book — rebuild every time it's asked for


def run(phase=None):
    if phase and phase not in PHASES:
        raise SystemExit(f"Unknown team phase {phase!r}; use one of {list(PHASES)}")
    only = PHASES[phase] if phase else [n for n, _ in STEPS]
    cp = load_cp()
    for name, fn in STEPS:
        if name not in only:
            continue
        if name in cp["done"] and name not in ALWAYS_RERUN:
            print(f"✓ {name} (already done)")
            continue
        print(f"→ {name}")
        fn(cp)
        if name not in cp["done"]:
            cp["done"].append(name)
        save_cp(cp)
