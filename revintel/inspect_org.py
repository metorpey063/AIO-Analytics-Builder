"""Read-only org survey for a Revenue Intelligence demo: `python3 -m revintel <demo> inspect`.

Works with a minimal config (only ORG_ALIAS). Writes out/inspect.json (for the web UI and the
skill's design step) and prints a short report with warnings for the known traps: duplicate
template apps, EAM record-type filters, two "Standard Price Book"s, scheduled Apex that writes
opportunities/quotas, and demo records owned by shared personas.
"""

import json
import os

from revintel import apply as A
from revintel.config import C, opt

TEMPLATES = {"sfdc_internal__RevenueInsights": "Revenue Insights",
             "sfdc_internal__AccountDiscovery": "Einstein Account Management",
             "sfdc_internal__CustomerInsights": "Customer Insights"}
STORY_FIELDS = ["ATR__c", "Product_Churn_ACV__c", "Closed_Lost_ATR__c", "Primary_Loss_Reason__c",
                "Secondary_Loss_Reason__c", "Loss_Commentary__c", "Demo_External_ID__c"]


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as e:   # one failing probe shouldn't stop the survey
        return {"error": str(e)[:300]} if default is None else default


def apps():
    d = A.rest("/services/data/v62.0/wave/folders?pageSize=200")
    out = [{"id": f["id"], "name": f["name"], "label": f["label"], "template": f.get("templateSourceId")}
           for f in d.get("folders", []) if f.get("templateSourceId") in TEMPLATES]
    for f in out:
        if f["template"] == "sfdc_internal__AccountDiscovery":
            tv = A.rest(f"/services/data/v62.0/wave/folders/{f['id']}").get("templateValues") or {}
            f["eam_filters"] = {k: tv.get(k) for k in ("AcctRecordType", "OpptyRecordType", "Has_Products")}
    return out


def opp_stages():
    rts = A.query("SELECT Id, DeveloperName FROM RecordType WHERE SobjectType = 'Opportunity' AND IsActive = true")
    out = {}
    for rt in rts + [{"Id": "012000000000000AAA", "DeveloperName": "Master"}]:
        d = A.rest(f"/services/data/v62.0/ui-api/object-info/Opportunity/picklist-values/{rt['Id']}/StageName")
        out[rt["DeveloperName"]] = {"id": rt["Id"], "stages": [v["value"] for v in d.get("values", [])]}
    return out


def fields():
    have = {}
    for sobj in ("Opportunity", "Account", "OpportunityLineItem"):
        names = {f["name"] for f in A.sf("sobject", "describe", "-s", sobj)["fields"]}
        have[sobj] = [f for f in STORY_FIELDS if f in names] + \
            ([f"(+{len([n for n in names if n.endswith('__c')])} custom fields)"])
    return have


def team():
    leader_role = opt("SALES_LEADER_ROLE", "VP of Sales")
    roles = A.query("SELECT Id, Name, ParentRoleId, ForecastUserId FROM UserRole")
    by_id = {r["Id"]: r for r in roles}
    leader = next((r for r in roles if r["Name"] == leader_role), None)
    if not leader:
        return {"leader_role": leader_role, "error": "role not found"}
    users = {u["Id"]: u for u in A.query("SELECT Id, Name, UserRoleId, ForecastEnabled, IsActive FROM User "
                                         "WHERE IsActive = true AND UserType = 'Standard'")}
    children = [r for r in roles if r["ParentRoleId"] == leader["Id"]]
    rows = []
    for r in children:
        members = [u["Name"] for u in users.values() if u["UserRoleId"] == r["Id"] and u["ForecastEnabled"]]
        fm = users.get(r["ForecastUserId"], {}).get("Name")
        rows.append({"role": r["Name"], "forecast_manager": fm, "forecast_enabled_members": members})
    in_leader_role = [u["Name"] for u in users.values() if u["UserRoleId"] == leader["Id"] and u["ForecastEnabled"]]
    shown = [r["forecast_manager"] or r["forecast_enabled_members"] for r in rows]
    return {"leader_role": leader_role, "users_in_leader_role": in_leader_role, "child_roles": rows,
            "people_under_leader_in_revenue_insights": sum(1 if isinstance(s, str) else len(s) for s in shown)}


def scheduled_apex():
    jobs = A.query("SELECT CronJobDetail.Name, CronJobDetail.JobType, State, NextFireTime, CronExpression "
                   "FROM CronTrigger WHERE State != 'DELETED' AND CronJobDetail.JobType = '7'")
    return [{"name": j["CronJobDetail"]["Name"], "next": j["NextFireTime"], "cron": j["CronExpression"]} for j in jobs]


def run():
    report = {"org": C.ORG_ALIAS}
    report["apps"] = _safe(apps, [])
    dupes = {}
    for a in report["apps"]:
        dupes.setdefault(a["template"], []).append(a["label"])
    report["warnings"] = [f"{TEMPLATES[t]} installed {len(v)}× ({', '.join(v)}) — check which one the dashboards read"
                          for t, v in dupes.items() if len(v) > 1]
    for a in report["apps"]:
        if a.get("eam_filters"):
            report["warnings"].append(f"EAM filters (change via Reconfigure): Opportunity record types "
                                      f"{a['eam_filters']['OpptyRecordType']}, Account record types {a['eam_filters']['AcctRecordType']}")
    apps_for_chain = [a["name"] for a in report["apps"] if a["template"] != "sfdc_internal__CustomerInsights"]
    if apps_for_chain:
        import crma_refresh
        chosen, waves = _safe(lambda: crma_refresh.discover(crma_refresh.Org(C.ORG_ALIAS), apps_for_chain,
                                                            ("ED Recipe", "Demo")), ({}, []))
        report["refresh_chain"] = [[chosen[r]["label"] for r in w] for w in waves]
    report["opportunity_stages"] = _safe(opp_stages)
    pbs = _safe(lambda: A.query("SELECT Id, Name, IsStandard, IsActive FROM Pricebook2"), [])
    report["pricebooks"] = {"standard": [p["Id"] for p in pbs if p.get("IsStandard")],
                            "named_standard": [p["Id"] for p in pbs if p.get("Name") == "Standard Price Book"]}
    if len(report["pricebooks"]["named_standard"]) > 1:
        report["warnings"].append("Several price books are named 'Standard Price Book' — use the IsStandard one "
                                  f"({report['pricebooks']['standard']})")
    report["story_fields"] = _safe(fields)
    report["forecast_types"] = _safe(lambda: [{"label": f["MasterLabel"], "dev": f["DeveloperName"], "role_type": f["RoleType"]}
                                              for f in A.query("SELECT MasterLabel, DeveloperName, RoleType FROM ForecastingType "
                                                               "WHERE IsActive = true")], [])
    report["territory_models"] = _safe(lambda: A.query("SELECT Id, Name, State FROM Territory2Model"), [])
    report["team"] = _safe(team)
    report["scheduled_apex"] = _safe(scheduled_apex, [])
    if report["scheduled_apex"]:
        report["warnings"].append("Scheduled Apex jobs — read each class before loading data; demo-refresh jobs can "
                                  f"create/close/re-date opps or write quotas: {[j['name'] for j in report['scheduled_apex']]}")
    prefix = opt("POOL_PREFIX", "AIO-POOL")
    report["pool"] = _safe(lambda: {
        "tagged_accounts": A.query(f"SELECT COUNT(Id) n FROM Account WHERE Demo_External_ID__c LIKE '{prefix}-%'")[0]["n"],
        "accounts_total": A.query("SELECT COUNT(Id) n FROM Account")[0]["n"]})
    os.makedirs(A.OUT, exist_ok=True)
    json.dump(report, open(os.path.join(A.OUT, "inspect.json"), "w"), indent=1, default=str)

    print(f"Org: {report['org']}")
    print("Apps:", [f"{a['label']} ({TEMPLATES[a['template']]})" for a in report["apps"]])
    for i, w in enumerate(report.get("refresh_chain", []), 1):
        print(f"  refresh wave {i}: {' | '.join(w)}")
    st = report["opportunity_stages"]
    if isinstance(st, dict) and "error" not in st:
        for rt, v in st.items():
            print(f"Stages · {rt}: {v['stages']}")
    print("Story fields:", report["story_fields"])
    print("Forecast types:", [f"{f['label']} ({'territory' if f['role_type'] == 'Y' else 'role'})" for f in report["forecast_types"]])
    t = report["team"]
    if isinstance(t, dict) and "child_roles" in t:
        print(f"Under '{t['leader_role']}': {t['people_under_leader_in_revenue_insights']} people would show in "
              f"Revenue Insights (aim for 7–9)")
        for r in t["child_roles"]:
            print(f"  {r['role']}: manager {r['forecast_manager']} · members {r['forecast_enabled_members']}")
    print("Pool:", report["pool"])
    print("\nWarnings:" if report["warnings"] else "\nNo warnings.")
    for w in report["warnings"]:
        print("  ⚠", w)
    print(f"\nFull report: {os.path.join(A.OUT, 'inspect.json')}")
    return report
