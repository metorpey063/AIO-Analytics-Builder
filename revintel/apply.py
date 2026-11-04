"""Write a generated plan to the org through the sf CLI (Bulk API 2.0).

Every step is checkpointed in out/checkpoint.json, so a re-run skips finished steps. Loads are
insert-only (CreatedDate can only be set on insert), so re-running never duplicates records.
`reset` only deletes records on the pool accounts / with the demo's external-ID prefix.
A CSV backup of anything deleted or overwritten is written to out/backup_* first.
One-off org cleanup (another tool's leftovers, unused products) is a skill step, not this module.
"""

import csv
import json
import os
import subprocess
import tempfile
import time

from revintel.config import C, DEMO_DIR, NB_STAGES, OUT, opt

HERE = DEMO_DIR
CP_PATH = os.path.join(OUT, "checkpoint.json")


# ── sf CLI helpers ──────────────────────────────────────────────────────────
TRANSIENT = ("fetch failed", "ECONNRESET", "ETIMEDOUT", "socket hang up")


def sf(*args, check=True):
    for attempt in range(4):
        r = subprocess.run(["sf", *args, "-o", C.ORG_ALIAS, "--json"], capture_output=True, text=True)
        try:
            out = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            out = {"status": 1, "message": r.stdout[-2000:] + r.stderr[-2000:]}
        msg = str(out.get("message", ""))
        if out.get("status", 0) != 0 and any(t in msg for t in TRANSIENT) and attempt < 3:
            time.sleep(5 * (attempt + 1))
            continue
        break
    if check and out.get("status", 0) != 0:
        raise RuntimeError(f"sf {' '.join(args[:3])} failed: {out.get('message') or out}")
    return out.get("result", out)


def query(soql):
    return sf("data", "query", "-q", soql)["records"]


def rest(path, method="GET", body=None):
    args = ["api", "request", "rest", path, "-X", method]
    if body is not None:
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(body, f)
        f.close()
        args += ["-b", "@" + f.name]
    r = subprocess.run(["sf", *args, "-o", C.ORG_ALIAS], capture_output=True, text=True)
    txt = r.stdout.strip()
    try:
        return json.loads(txt) if txt else {}
    except json.JSONDecodeError:
        return {"raw": txt}


def write_csv(path, rows, cols=None):
    cols = cols or sorted({k for r in rows for k in r if not k.startswith("_")})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return path


def bulk(op, sobject, rows, ext_id=None, cols=None):
    """op: import | upsert | update | delete. Raises if any row fails."""
    if not rows:
        return 0
    path = write_csv(os.path.join(OUT, f"_bulk_{op}_{sobject}.csv"), rows, cols)
    args = ["data", op, "bulk", "--sobject", sobject, "--file", path, "--wait", "15"]
    if ext_id:
        args += ["--external-id", ext_id]
    res = sf(*args, check=False)
    # sf CLI result shapes differ by command: numberRecords* (import/upsert/delete) vs *Records (update)
    info = res.get("jobInfo", {})
    failed = int(res.get("numberRecordsFailed") or res.get("failedRecords") or info.get("numberRecordsFailed") or 0)
    processed = int(res.get("numberRecordsProcessed") or res.get("processedRecords")
                    or info.get("numberRecordsProcessed") or 0)
    if failed or (processed == 0 and rows):
        job = res.get("jobId") or res.get("jobInfo", {}).get("id") or res.get("id")
        detail = sf("data", "bulk", "results", "--job-id", job, check=False) if job else res
        raise RuntimeError(f"{op} {sobject}: {failed} of {len(rows)} failed. Job {job}. {json.dumps(detail)[:1500]}")
    print(f"  {op} {sobject}: {processed} ok")
    return processed


def ids_in(ids):
    return "(" + ",".join(f"'{i}'" for i in ids) + ")"


# ── checkpoint ──────────────────────────────────────────────────────────────
def load_cp():
    return json.load(open(CP_PATH)) if os.path.exists(CP_PATH) else {"done": []}


def save_cp(cp):
    json.dump(cp, open(CP_PATH, "w"), indent=1)


def step(cp, name, fn):
    if name in cp["done"]:
        print(f"✓ {name} (already done)")
        return
    print(f"→ {name}")
    fn(cp)
    cp["done"].append(name)
    save_cp(cp)


# ── steps ───────────────────────────────────────────────────────────────────
def pool_ids():
    seed = os.path.join(HERE, "pool_seed.json")
    return [a["id"] for a in (json.load(open(seed)) if os.path.exists(seed) else [])] + \
        [e["id"] for e in getattr(C, "EXTRA_POOL", [])]


def s_sales_process(cp):
    """Optional: give the new-business sales process its own stages (NEW_BUSINESS_PROCESS in config)."""
    process = opt("NEW_BUSINESS_PROCESS", None)
    if not process:
        print("  skipped (NEW_BUSINESS_PROCESS not set)")
        return
    stages = [NB_STAGES["early"], NB_STAGES["mid"], NB_STAGES["late"], "Closed Won", "Closed Lost"]
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "objects"))
    # Opportunity business processes reject <default> on values ("Cannot specify a default on: Opportunity")
    vals = "".join(f"<values><fullName>{v}</fullName></values>"
                   for v in stages)
    open(os.path.join(d, "objects", "Opportunity.object"), "w").write(
        '<?xml version="1.0" encoding="UTF-8"?><CustomObject xmlns="http://soap.sforce.com/2006/04/metadata">'
        f'<businessProcesses><fullName>{process}</fullName><isActive>true</isActive>{vals}'
        '</businessProcesses></CustomObject>')
    open(os.path.join(d, "package.xml"), "w").write(
        '<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata">'
        f'<types><members>Opportunity.{process}</members><name>BusinessProcess</name></types>'
        '<version>62.0</version></Package>')
    sf("project", "deploy", "start", "--metadata-dir", d, "--wait", "10")
    print(f"  {process}: {', '.join(stages)}")


def product_pbes():
    """product key -> standard price book entry Id: config value, else the products step's mapping."""
    path = os.path.join(OUT, "products.json")
    made = json.load(open(path)) if os.path.exists(path) else {}
    return {k: (v.get("pbe") if v.get("pbe") and not str(v.get("pbe")).startswith("<") else made.get(k))
            for k, v in C.PRODUCTS.items()}


def s_products(cp):
    """Find or create each PRODUCTS entry (Product2 + standard PricebookEntry). Keys with a real
    `pbe` in config are left alone; others are matched by name, then created. Mapping → out/products.json."""
    path = os.path.join(OUT, "products.json")
    made = json.load(open(path)) if os.path.exists(path) else {}
    std = C.STD_PRICEBOOK
    for key, p in C.PRODUCTS.items():
        if (p.get("pbe") and not str(p["pbe"]).startswith("<")) or made.get(key):
            continue
        name = p.get("name") or p["label"]
        safe = name.replace("'", "\\'")
        hit = query("SELECT Id, Product2Id FROM PricebookEntry WHERE Pricebook2Id = "
                    f"'{std}' AND Product2.Name = '{safe}' AND CurrencyIsoCode = 'USD' LIMIT 1")
        if hit:
            made[key] = hit[0]["Id"]
            print(f"  {name}: existing price book entry")
        else:
            prod = sf("data", "create", "record", "-s", "Product2", "-v",
                      f"Name='{safe}' Family='{p.get('family', '')}' ProductCode='{p.get('code', key)}' IsActive=true")["id"]
            made[key] = sf("data", "create", "record", "-s", "PricebookEntry", "-v",
                           f"Pricebook2Id={std} Product2Id={prod} UnitPrice={p['list']} IsActive=true CurrencyIsoCode=USD")["id"]
            print(f"  {name}: created product + price book entry")
        json.dump(made, open(path, "w"), indent=1)
    print(f"  {len(C.PRODUCTS)} products ready")


def s_opp_external_id(cp):
    fields = [f["name"] for f in sf("sobject", "describe", "-s", "Opportunity")["fields"]]
    if "Demo_External_ID__c" in fields:
        print("  Opportunity.Demo_External_ID__c already visible")
        return
    tq = rest("/services/data/v62.0/tooling/query?q=" + "SELECT+Id+FROM+CustomField+WHERE+TableEnumOrId='Opportunity'+AND+DeveloperName='Demo_External_ID'")
    if not tq.get("records"):
        r = rest("/services/data/v62.0/tooling/sobjects/CustomField", "POST", {
            "FullName": "Opportunity.Demo_External_ID__c",
            "Metadata": {"label": "Demo External ID", "type": "Text", "length": 80, "externalId": True,
                         "unique": True, "caseSensitive": False, "required": False,
                         "description": "Auto-created by AIO Analytics Builder for demo record linkage"}})
        if not r.get("success"):
            raise RuntimeError(f"field create failed: {r}")
        print("  created Opportunity.Demo_External_ID__c")
    ps = query("SELECT Id FROM PermissionSet WHERE Name = 'AIO_Demo_Field_Access'")
    if not ps:
        raise RuntimeError("AIO_Demo_Field_Access permission set missing (created by crm_upserter on the Account field)")
    if not query(f"SELECT Id FROM FieldPermissions WHERE ParentId = '{ps[0]['Id']}' AND Field = 'Opportunity.Demo_External_ID__c'"):
        sf("data", "create", "record", "-s", "FieldPermissions", "-v",
           f"ParentId={ps[0]['Id']} SobjectType=Opportunity Field=Opportunity.Demo_External_ID__c "
           "PermissionsRead=true PermissionsEdit=true")
        print("  granted read/edit via AIO_Demo_Field_Access")


def s_users(cp):
    ids = list(C.USERS.values())
    write_csv(os.path.join(OUT, "backup_users.csv"),
              query(f"SELECT Id, Name, ManagerId, ForecastEnabled FROM User WHERE Id IN {ids_in(ids)}"),
              ["Id", "Name", "ManagerId", "ForecastEnabled"])
    for u, m in C.MANAGERS.items():
        sf("data", "update", "record", "-s", "User", "-i", C.USERS[u], "-v", f"ManagerId={C.USERS[m]}")
    sf("data", "update", "record", "-s", "User", "-i", C.USERS["alan"], "-v", "ForecastEnabled=true")
    print(f"  {len(C.MANAGERS)} managers set; Alan Reed forecast-enabled")


def s_territories(cp):
    tid = {k: v[0] for k, v in C.TERRITORIES.items()}
    found = {r["DeveloperName"]: r["Id"] for r in query(
        f"SELECT Id, DeveloperName FROM Territory2 WHERE Territory2ModelId = '{C.TERRITORY_MODEL}'")}
    pending = [k for k, v in tid.items() if not v]
    while pending:   # create missing territories, parents first
        for dev in list(pending):
            parent = C.TERRITORIES[dev][1]
            if dev in found:
                tid[dev] = found[dev]
            elif parent and not tid.get(parent):
                continue
            else:
                label = C.TERRITORY_LABELS.get(dev, dev.replace("_", " "))
                tid[dev] = sf("data", "create", "record", "-s", "Territory2", "-v",
                              f"Name='{label}' DeveloperName={dev} Territory2ModelId={C.TERRITORY_MODEL} "
                              f"Territory2TypeId={C.TERRITORY_TYPE} ParentTerritory2Id={tid[parent]}")["id"]
                print(f"  created territory {label}")
            pending.remove(dev)
    existing = query("SELECT Id, Territory2.DeveloperName, UserId, RoleInTerritory2 FROM UserTerritory2Association "
                     f"WHERE Territory2.Territory2ModelId = '{C.TERRITORY_MODEL}'")
    write_csv(os.path.join(OUT, "backup_user_territories.csv"),
              [{"Id": e["Id"], "Territory": e["Territory2"]["DeveloperName"], "UserId": e["UserId"],
                "Role": e["RoleInTerritory2"]} for e in existing])
    have = {(e["Territory2"]["DeveloperName"], e["UserId"]): e for e in existing}
    for dev, u in C.TERRITORY_USERS_REMOVE:
        e = have.get((dev, C.USERS[u]))
        if e:
            sf("data", "delete", "record", "-s", "UserTerritory2Association", "-i", e["Id"])
    for dev, u, role in C.TERRITORY_USERS:
        e = have.get((dev, C.USERS[u]))
        if e and e["RoleInTerritory2"] != role:
            sf("data", "update", "record", "-s", "UserTerritory2Association", "-i", e["Id"], "-v", f"RoleInTerritory2='{role}'")
        elif not e:
            sf("data", "create", "record", "-s", "UserTerritory2Association", "-v",
               f"Territory2Id={tid[dev]} UserId={C.USERS[u]} RoleInTerritory2='{role}'")
    # forecast manager must already be assigned to the territory (and forecast-enabled)
    for dev, (_, _, fu) in C.TERRITORIES.items():
        sf("data", "update", "record", "-s", "Territory2", "-i", tid[dev], "-v", f"ForecastUserId={C.USERS[fu]}")
    cp["territory_ids"] = tid
    print("  forecast managers + user assignments set")


def s_accounts(cp):
    plan = cp["_plan"]
    write_csv(os.path.join(OUT, "backup_accounts.csv"),
              query("SELECT Id, Name, Industry, Type, NumberOfEmployees, AnnualRevenue, BillingCountry, BillingState, "
                    f"BillingCity, OwnerId, Description, Demo_External_ID__c FROM Account WHERE Id IN {ids_in(pool_ids())}"),
              ["Id", "Name", "Industry", "Type", "NumberOfEmployees", "AnnualRevenue", "BillingCountry",
               "BillingState", "BillingCity", "OwnerId", "Description", "Demo_External_ID__c"])
    # Bulk update leaves blank cells unchanged; #N/A clears the old Indiana state on EMEA accounts
    bulk("update", "Account", [{**a, "BillingState": a["BillingState"] or "#N/A"} for a in plan["accounts"]])
    tid = cp["territory_ids"]
    have = {(r["ObjectId"], r["Territory2Id"]) for r in query(
        f"SELECT ObjectId, Territory2Id FROM ObjectTerritory2Association WHERE ObjectId IN {ids_in(pool_ids())}")}
    rows = [{"ObjectId": t["ObjectId"], "Territory2Id": tid[t["Territory2"]], "AssociationCause": "Territory2Manual"}
            for t in plan["territory_assoc"] if (t["ObjectId"], tid[t["Territory2"]]) not in have]
    bulk("import", "ObjectTerritory2Association", rows)


def s_pool_record_type(cp):
    """Move pool accounts to their own record type so EAM can filter to them (Reconfigure → Account Record Type)."""
    rt = query(f"SELECT Id FROM RecordType WHERE SobjectType = 'Account' AND DeveloperName = '{C.POOL_RECORD_TYPE}'")[0]["Id"]
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "profiles"))
    for prof in C.POOL_RECORD_TYPE_PROFILES:
        open(os.path.join(d, "profiles", f"{prof}.profile"), "w").write(
            '<?xml version="1.0" encoding="UTF-8"?><Profile xmlns="http://soap.sforce.com/2006/04/metadata">'
            f'<recordTypeVisibilities><default>false</default><recordType>Account.{C.POOL_RECORD_TYPE}</recordType>'
            '<visible>true</visible></recordTypeVisibilities></Profile>')
    members = "".join(f"<members>{p}</members>" for p in C.POOL_RECORD_TYPE_PROFILES)
    open(os.path.join(d, "package.xml"), "w").write(
        '<?xml version="1.0" encoding="UTF-8"?><Package xmlns="http://soap.sforce.com/2006/04/metadata">'
        f'<types>{members}<name>Profile</name></types><version>62.0</version></Package>')
    sf("project", "deploy", "start", "--metadata-dir", d, "--wait", "10")
    print(f"  {C.POOL_RECORD_TYPE} enabled (not default) on {', '.join(C.POOL_RECORD_TYPE_PROFILES)}")
    rows = query(f"SELECT Id, Name, RecordTypeId FROM Account WHERE Id IN {ids_in(pool_ids())}")
    write_csv(os.path.join(OUT, "backup_pool_record_types.csv"), rows, ["Id", "Name", "RecordTypeId"])
    bulk("update", "Account", [{"Id": r["Id"], "RecordTypeId": rt} for r in rows if r["RecordTypeId"] != rt],
         cols=["Id", "RecordTypeId"])


def s_contacts(cp):
    """Insert-only: skip contacts whose [AIO] key is already in the org."""
    have = {(r["Description"] or "").replace("[AIO] ", "") for r in query(
        f"SELECT Description FROM Contact WHERE AccountId IN {ids_in(pool_ids())}")}
    rows = [{**{k: v for k, v in c.items() if not k.startswith("_")}, "AccountId": c["_acct"],
             "Description": f"[AIO] {c['_key']}"} for c in cp["_plan"]["contacts"] if c["_key"] not in have]
    bulk("import", "Contact", rows)


def s_opportunities(cp):
    """Insert-only: CreatedDate can't be set on existing records, so skip ext ids already in the org."""
    tid = cp["territory_ids"]
    have = {r["Demo_External_ID__c"] for r in query(
        f"SELECT Demo_External_ID__c FROM Opportunity WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'")}
    rows = []
    for o in cp["_plan"]["opportunities"]:
        if o["Demo_External_ID__c"] in have:
            continue
        r = {k: v for k, v in o.items() if not k.startswith("_") and k != "Territory2"}
        r["Territory2Id"] = tid[o["Territory2"]]
        rows.append(r)
    bulk("upsert", "Opportunity", rows, ext_id="Demo_External_ID__c")


def s_line_items(cp):
    opp_ids = {r["Demo_External_ID__c"]: r["Id"] for r in query(
        f"SELECT Id, Demo_External_ID__c FROM Opportunity WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'")}
    existing = {r["OpportunityId"] for r in query(
        f"SELECT OpportunityId FROM OpportunityLineItem WHERE Opportunity.Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'")}
    pbes = product_pbes()
    rows = [{**{k: v for k, v in li.items() if not k.startswith("_")}, "OpportunityId": opp_ids[li["_opp_ext"]],
             "PricebookEntryId": pbes.get(li["_product"]) or li["PricebookEntryId"]}
            for li in cp["_plan"]["line_items"] if opp_ids[li["_opp_ext"]] not in existing]
    bulk("import", "OpportunityLineItem", rows)


def s_activities(cp):
    # Description is long text (not filterable in SOQL), so match the [AIO] key after the query
    cids = {(r["Description"] or "").replace("[AIO] ", ""): r["Id"] for r in query(
        f"SELECT Id, Description FROM Contact WHERE AccountId IN {ids_in(pool_ids())}")
        if (r["Description"] or "").startswith("[AIO]")}
    # insert-only: skip accounts that already have their activities
    done_accts = {r["AccountId"] for r in query(f"SELECT AccountId FROM Task WHERE AccountId IN {ids_in(pool_ids())}")}
    tasks = [{**{k: v for k, v in t.items() if not k.startswith("_")}, "WhatId": t["_acct"], "WhoId": cids[t["_contact"]],
              "Description": "[AIO]"} for t in cp["_plan"]["tasks"] if t["_acct"] not in done_accts]
    events = [{**{k: v for k, v in e.items() if not k.startswith("_")}, "WhatId": e["_acct"], "WhoId": cids[e["_contact"]],
               "Description": "[AIO]"} for e in cp["_plan"]["events"] if e["_acct"] not in done_accts]
    bulk("import", "Task", tasks)
    bulk("import", "Event", events)


def s_owners(cp):
    """Existing records follow the plan's owner (e.g. accounts moved to a hybrid lead's own book)."""
    want = {o["Demo_External_ID__c"]: o["OwnerId"] for o in cp["_plan"]["opportunities"]}
    rows = query(f"SELECT Id, OwnerId, Demo_External_ID__c FROM Opportunity WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'")
    moves = [r for r in rows if r["Demo_External_ID__c"] in want and want[r["Demo_External_ID__c"]] != r["OwnerId"]]
    write_csv(os.path.join(OUT, "backup_opp_owners_8leads.csv"), [{k: v for k, v in r.items() if k != "attributes"} for r in moves])
    bulk("update", "Opportunity", [{"Id": r["Id"], "OwnerId": want[r["Demo_External_ID__c"]]} for r in moves], cols=["Id", "OwnerId"])
    acct_owner = {a["Id"]: a["OwnerId"] for a in cp["_plan"]["accounts"]}
    for sobj in ("Contact", "Task", "Event"):
        recs = query(f"SELECT Id, OwnerId, AccountId FROM {sobj} WHERE AccountId IN {ids_in(pool_ids())}")
        fix = [{"Id": r["Id"], "OwnerId": acct_owner[r["AccountId"]]} for r in recs
               if r["AccountId"] in acct_owner and r["OwnerId"] != acct_owner[r["AccountId"]]]
        bulk("update", sobj, fix, cols=["Id", "OwnerId"])


def s_verify(cp):
    q = lambda s: query(s)
    print("  opps by family:", [(r["fam"], r["n"]) for r in q(
        "SELECT Product2.Family fam, COUNT(Id) n FROM OpportunityLineItem "
        f"WHERE Opportunity.Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%' GROUP BY Product2.Family")])
    print("  opps:", q(f"SELECT COUNT(Id) n FROM Opportunity WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'")[0]["n"],
          "| contacts:", q(f"SELECT COUNT(Id) n FROM Contact WHERE AccountId IN {ids_in(pool_ids())}")[0]["n"],
          "| tasks:", q(f"SELECT COUNT(Id) n FROM Task WHERE AccountId IN {ids_in(pool_ids())}")[0]["n"])
    print("  backdated CreatedDate sample:", q(
        f"SELECT Name, CreatedDate, CloseDate FROM Opportunity WHERE Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%' "
        "ORDER BY CreatedDate ASC LIMIT 1"))


STEPS = [("fix New Business sales process", s_sales_process), ("products", s_products),
         ("Opportunity external ID", s_opp_external_id),
         ("team managers", s_users), ("renewal territories", s_territories), ("pool accounts", s_accounts), ("pool record type", s_pool_record_type),
         ("contacts", s_contacts), ("opportunities", s_opportunities), ("line items", s_line_items),
         ("activities", s_activities), ("owners", s_owners), ("verify", s_verify)]


def apply(plan):
    cp = load_cp()
    cp["_plan"] = plan
    cp["build_date"] = plan["today"]
    for name, fn in STEPS:
        step(cp, name, fn)
    cp.pop("_plan", None)
    save_cp(cp)
    print("\nDone. Next: `team quotas`, then `refresh` (Data Sync + Revenue Intelligence recipes in order).")


def reset(_=None):
    """Remove pool opps (line items cascade), contacts and activities. Accounts, team and territories stay."""
    pids = ids_in(pool_ids())
    for sobj, where in (("Task", f"AccountId IN {pids}"), ("Event", f"AccountId IN {pids}"),
                        ("Opportunity", f"Demo_External_ID__c LIKE '{C.EXT_PREFIX}-%'"),
                        ("Contact", f"AccountId IN {pids}")):
        rows = query(f"SELECT Id FROM {sobj} WHERE {where}")
        bulk("delete", sobj, [{"Id": r["Id"]} for r in rows], cols=["Id"])
    cp = load_cp()
    cp["done"] = [d for d in cp["done"] if d not in ("contacts", "opportunities", "line items", "activities", "verify")]
    save_cp(cp)
    print("Reset done. Run apply to regenerate anchored to today.")
