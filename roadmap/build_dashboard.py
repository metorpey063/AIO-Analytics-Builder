"""Build the AIO Roadmap Votes dashboard in Tableau Next (Tableau Next & Slack org).

Data: the Roadmap_Vote__c CRM data stream (Roadmap_Vote_c_Home__dll). Each vote row
is one voter's ranked pick and carries its item's title, status, source and rank
(formula fields), so the model is a single fact data object. Points: 1st = 3, 2nd = 2, 3rd = 1.

  python3 roadmap/build_dashboard.py                    build (resumes from the checkpoint)
  python3 roadmap/build_dashboard.py --rebuild          delete the dashboard assets this script created, then build
  python3 roadmap/build_dashboard.py --rebuild-stream   also delete and recreate the votes data stream
                                                        (needed after adding fields to Roadmap_Vote__c)
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from connections import load_config, get_sf_token, sf_headers  # noqa: E402
from viz_builder import build_viz_payload  # noqa: E402
from viz_validator import is_valid  # noqa: E402
from dashboard_builder import build_dashboard_payload  # noqa: E402

PROFILE = "tableau_next_slack"
EXPECTED_INSTANCE = "trailsignup-5a85b0dc8e453e"
VOTE_OBJECT = "Roadmap_Vote__c"
VOTE_STREAM = "Roadmap_Vote_c_Home"
VOTE_DLO = "Roadmap_Vote_c_Home__dll"
# CRM fields copied to Data Cloud (types must match the CRM field; checkboxes are Boolean)
VOTE_FIELDS = {
    "Id": "Text", "Name": "Text", "Item__c": "Text", "Voter_Id__c": "Text", "Active__c": "Boolean",
    "Active_Vote__c": "Number", "Pick_Rank__c": "Number", "Points__c": "Number", "First_Choice__c": "Number",
    "Item_Title__c": "Text", "Item_Status__c": "Text", "Item_Source__c": "Text", "Item_Priority_Rank__c": "Number",
    "CreatedDate": "DateTime", "LastModifiedDate": "DateTime", "SystemModstamp": "DateTime", "IsDeleted": "Text",
}
CP_PATH = Path(__file__).resolve().parent / "roadmap_dashboard_checkpoint.json"
LABEL = "AIO Roadmap Votes"
V65 = "services/data/v65.0"
V62 = "services/data/v62.0"
V66 = "services/data/v66.0"

DIM_DESCRIPTIONS = {
    "Item_Title": "The roadmap item or SE idea that was voted on. Use this to rank items by votes.",
    "Item_Status": "Roadmap status of the item: In progress, Next, Planned or Suggested (an SE idea).",
    "Item_Source": "Roadmap = curated in ROADMAP.md; SE suggestion = an idea an SE added in the Web UI.",
    "Voter_Id": "Anonymous AIO install ID. Count distinct values to get the number of voters.",
    "Item": "Salesforce ID of the roadmap item.",
    "CreatedDate": "When the vote was first cast. Use this for votes over time.",
}
CLCS = [
    {"api": "Points_clc", "label": "Points", "expr": "SUM([{do}].[{points}])",
     "singular": "point", "plural": "points"},
    {"api": "First_Choices_clc", "label": "First Choices", "expr": "SUM([{do}].[{first}])",
     "singular": "first choice", "plural": "first choices"},
    {"api": "Voters_clc", "label": "Voters", "expr": "COUNTD(IF [{do}].[{active}] = 1 THEN [{do}].[{voter}] END)",
     "singular": "voter", "plural": "voters"},
]


def base_name(field):
    """CRM DLO field name without its custom suffix (Item_Title_c -> Item_Title)."""
    return re.sub(r"(_{1,2}c)+$", "", field)


def load_cp():
    return json.loads(CP_PATH.read_text()) if CP_PATH.exists() else {}


def save_cp(cp):
    CP_PATH.write_text(json.dumps(cp, indent=2))


class Org:
    def __init__(self):
        config = load_config(PROFILE)
        token, self.instance = get_sf_token(config, profile_key=PROFILE, allow_browser=False)
        if EXPECTED_INSTANCE not in self.instance:
            raise SystemExit(f"Profile {PROFILE} points at {self.instance}, not the Tableau Next & Slack org")
        self.h = sf_headers(token)

    def call(self, method, path, body=None, ok=(200, 201, 204)):
        r = requests.request(method, f"{self.instance}/{path}", headers=self.h, json=body, timeout=120)
        if r.status_code not in ok:
            raise RuntimeError(f"{method} {path.split('?')[0]} -> {r.status_code} {r.text[:400]}")
        return r.json() if r.text.strip() else {}


def ensure_stream(org):
    """Create the votes CRM data stream if it doesn't exist, run it, and wait for ACTIVE."""
    r = requests.get(f"{org.instance}/{V62}/ssot/data-streams/{VOTE_STREAM}", headers=org.h, timeout=60)
    if r.status_code != 200:
        print("Creating the votes data stream...")
        org.call("POST", f"{V62}/ssot/data-streams", {
            "name": VOTE_STREAM, "label": f"{VOTE_OBJECT}_Home", "datastreamType": "SFDC",
            "connectorInfo": {"connectorType": "SalesforceDotCom",
                              "connectorDetails": {"name": "SalesforceDotCom_Home", "sourceObject": VOTE_OBJECT}},
            "dataLakeObjectInfo": {
                "label": f"{VOTE_OBJECT}_Home", "category": "Other", "dataspaceInfo": [{"name": "default"}],
                "dataLakeFieldInputRepresentations": [
                    {"name": f.replace("__c", "_c"), "label": f, "dataType": t, "isPrimaryKey": f == "Id"}
                    for f, t in VOTE_FIELDS.items()],
                "eventDateTimeFieldName": "", "recordModifiedFieldName": "SystemModstamp"},
            "mappings": []})
    for _ in range(40):
        st = org.call("GET", f"{V62}/ssot/data-streams/{VOTE_STREAM}")
        if (st.get("dataLakeObjectInfo") or {}).get("status") == "ACTIVE":
            break
        time.sleep(15)
    else:
        raise RuntimeError("Votes data stream didn't become ACTIVE")
    org.call("POST", f"{V62}/ssot/data-streams/{VOTE_STREAM}/actions/run", {})


def delete_stream(org):
    print("Deleting the votes data stream and its DLO...")
    org.call("DELETE", f"{V62}/ssot/data-streams/{VOTE_STREAM}?shouldDeleteDataLakeObject=true", ok=(200, 204, 404))
    for _ in range(40):
        r = requests.get(f"{org.instance}/{V62}/ssot/data-lake-objects/{VOTE_DLO}", headers=org.h, timeout=60)
        if r.status_code == 404 or not r.json().get("dataLakeObjects"):
            return
        time.sleep(15)
    raise RuntimeError(f"{VOTE_DLO} still exists")


def cleanup(org, cp):
    """Delete only what this script created (tracked in the checkpoint)."""
    for d in cp.get("all_dash_apis", []):
        org.call("DELETE", f"{V66}/tableau/dashboards/{d}", ok=(200, 204, 404))
    for v in cp.get("all_viz_apis", []):
        org.call("DELETE", f"{V66}/tableau/visualizations/{v}?minorVersion=12", ok=(200, 204, 404))
    for s in cp.get("all_sdm_apis", []):
        org.call("DELETE", f"{V65}/ssot/semantic/models/{s}", ok=(200, 204, 404))
    for w in cp.get("all_ws_apis", []):
        org.call("DELETE", f"{V65}/tableau/workspaces/{w}", ok=(200, 204, 404))
    save_cp({})
    return {}


def build(org, cp):
    for k in ("all_ws_apis", "all_sdm_apis", "all_viz_apis", "all_dash_apis"):
        cp.setdefault(k, [])

    if not cp.get("sdm_done"):
        print("Workspace + semantic model...")
        ws = org.call("POST", f"{V65}/tableau/workspaces", {"label": LABEL})
        cp["ws_api"] = ws["name"]
        cp["all_ws_apis"].append(cp["ws_api"])
        save_cp(cp)
        sdm = org.call("POST", f"{V65}/ssot/semantic/models",
                       {"label": LABEL, "dataspace": "default", "agentEnabled": True})
        cp["sdm_api"], cp["sdm_id"] = sdm["apiName"], sdm.get("id")
        cp["all_sdm_apis"].append(cp["sdm_api"])
        save_cp(cp)
        do = org.call("POST", f"{V65}/ssot/semantic/models/{cp['sdm_api']}/data-objects", {
            "dataLakeObjectName": VOTE_DLO, "dataObjectName": VOTE_DLO, "label": "Roadmap Votes",
            "dataObjectType": "dlo", "shouldIncludeAllFields": True})
        cp["do_api"] = do["apiName"]
        detail = org.call("GET", f"{V65}/ssot/semantic/models/{cp['sdm_api']}/data-objects/{cp['do_api']}")
        cp["dim_field_map"] = {base_name(d["dataObjectFieldName"]): d["apiName"]
                               for d in detail.get("semanticDimensions", [])}
        cp["measurement_map"] = {base_name(m["dataObjectFieldName"]): m["apiName"]
                                 for m in detail.get("semanticMeasurements", [])}
        for dim in detail.get("semanticDimensions", []):
            base = base_name(dim["dataObjectFieldName"])
            desc = DIM_DESCRIPTIONS.get(base)
            if desc:
                org.call("PUT", f"{V65}/ssot/semantic/models/{cp['sdm_api']}/data-objects/{cp['do_api']}/dimensions/{dim['apiName']}",
                         {"apiName": dim["apiName"], "label": dim.get("label", base),
                          "dataObjectFieldName": dim["dataObjectFieldName"], "description": desc}, ok=(200, 201, 204, 400))
        cp["sdm_done"] = True
        save_cp(cp)
    print(f"  SDM {cp['sdm_api']}  DO {cp['do_api']}")

    dims = {base_name(k): v for k, v in cp["dim_field_map"].items()}
    meas = {base_name(k): v for k, v in cp["measurement_map"].items()}

    def dim(name):
        if name not in dims:
            raise RuntimeError(f"No dimension {name} in {sorted(dims)}")
        return dims[name]

    def measure(name):
        if name not in meas:
            raise RuntimeError(f"No measurement {name} in {sorted(meas)}")
        return meas[name]

    if not cp.get("metrics_done"):
        print("Calculated measures + metrics...")
        refs = {"do": cp["do_api"], "points": measure("Points"), "first": measure("First_Choice"),
                "active": measure("Active_Vote"), "voter": dim("Voter_Id")}
        date_ref = {"tableFieldReference": {"fieldApiName": dim("CreatedDate"), "tableApiName": cp["do_api"]}}
        dim_refs = [{"tableFieldReference": {"fieldApiName": dim(d), "tableApiName": cp["do_api"]}}
                    for d in ("Item_Title", "Item_Status", "Item_Source")]
        cp["metric_apis"] = []
        for c in CLCS:
            org.call("POST", f"{V65}/ssot/semantic/models/{cp['sdm_api']}/calculated-measurements", {
                "apiName": c["api"], "label": c["label"], "aggregationType": "UserAgg", "dataType": "Number",
                "decimalPlace": 0, "directionality": "Up", "displayCategory": "Continuous",
                "expression": c["expr"].format(**refs), "filters": [], "isOverrideBase": False, "isVisible": True,
                "level": "AggregateFunction", "overriddenProperties": [], "semanticDataType": "None"})
            mtc = org.call("POST", f"{V66}/ssot/semantic/models/{cp['sdm_api']}/metrics?minorVersion=12", {
                "apiName": c["api"].replace("_clc", "_mtc"), "label": c["label"],
                "measurementReference": {"calculatedFieldApiName": c["api"]},
                "timeDimensionReference": date_ref, "timeGrains": ["Week", "Month", "Quarter", "Year"],
                "aggregationType": "UserAgg", "additionalDimensions": dim_refs,
                "insightsSettings": {"insightsDimensionsReferences": dim_refs, "sentiment": "SentimentTypeUpIsGood",
                                     "singularNoun": c["singular"], "pluralNoun": c["plural"]}})
            cp["metric_apis"].append(mtc.get("apiName", c["api"].replace("_clc", "_mtc")))
        cp["metrics_done"] = True
        save_cp(cp)
    print(f"  metrics {cp['metric_apis']}")

    if not cp.get("viz_done"):
        print("Visualizations...")
        plan = [
            ("horizontal_bar", "aio_roadmap_points_by_item", "Points by Item (1st = 3, 2nd = 2, 3rd = 1)",
             {"category": "Item_Title", "amount": "Points"}),
            ("horizontal_bar", "aio_roadmap_first_choices", "First Choices by Item",
             {"category": "Item_Title", "amount": "First_Choice"}),
            ("donut", "aio_roadmap_points_by_source", "Roadmap vs SE Ideas (points)",
             {"category": "Item_Source", "amount": "Points"}),
        ]
        cp["viz_apis"] = []
        for template, name, label, fm in plan:
            payload = build_viz_payload(template_name=template, viz_name=name, viz_label=label,
                                        sdm_api=cp["sdm_api"], ws_api=cp["ws_api"], do_api=cp["do_api"],
                                        field_map=fm, dim_field_map=dims, measurements=meas)
            ok, results = is_valid(payload)
            if not ok:
                print(f"  validation warnings for {label}: {results}")
            for f in payload.get("fields", {}).values():
                if f.get("role") == "Measure":
                    f["function"] = "Sum"
            v = org.call("POST", f"{V66}/tableau/visualizations?minorVersion=12", payload)
            cp["viz_apis"].append(v.get("name", name))
            cp["all_viz_apis"].append(v.get("name", name))
            save_cp(cp)
        cp["viz_done"] = True
        save_cp(cp)
    print(f"  vizzes {cp['viz_apis']}")

    if not cp.get("dash_done"):
        print("Dashboard...")
        payload = build_dashboard_payload(dash_name="aio_roadmap_votes", dash_label=LABEL, ws_api=cp["ws_api"],
                                          sdm_api=cp["sdm_api"], sdm_id=cp.get("sdm_id"),
                                          metric_apis=cp["metric_apis"], viz_apis=cp["viz_apis"])
        d = org.call("POST", f"{V66}/tableau/dashboards?minorVersion=12", payload)
        cp["dash_api"] = d.get("name", "aio_roadmap_votes")
        cp["all_dash_apis"].append(cp["dash_api"])
        for v in cp["viz_apis"]:
            org.call("POST", f"{V65}/tableau/workspaces/{cp['ws_api']}/assets",
                     {"assetApiName": v, "assetType": "visualization"}, ok=(200, 201, 204, 400, 409))
        org.call("POST", f"{V65}/tableau/workspaces/{cp['ws_api']}/assets",
                 {"assetApiName": cp["dash_api"], "assetType": "dashboard"}, ok=(200, 201, 204, 400, 409))
        cp["dash_done"] = True
        save_cp(cp)
    print(f"  dashboard {cp['dash_api']}")
    ui = org.instance.replace(".my.salesforce.com", ".lightning.force.com")
    print(f"\nOpen the workspace (dashboard: {LABEL}): {ui}/tableau/workspace/{cp['ws_api']}")
    return cp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--rebuild-stream", action="store_true")
    args = ap.parse_args()
    org = Org()
    cp = load_cp()
    if args.rebuild or args.rebuild_stream:
        cp = cleanup(org, cp)
    if args.rebuild_stream:
        delete_stream(org)
    ensure_stream(org)
    build(org, cp)


if __name__ == "__main__":
    main()
