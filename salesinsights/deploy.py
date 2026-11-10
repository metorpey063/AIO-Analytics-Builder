"""
Deploy Sales Insights (6 dashboards, 68 vizzes, standalone SDM) to an org with Data Cloud.

Phases, checkpointed in demos/sales_insights/{profile}/checkpoint.json:
  0 preflight   profile auth, ingest connector, refuse the source org, existing-asset check
  1 data        generate CSVs, register schemas, create streams, wait ACTIVE, submit bulk upserts
  2 sdm         workspace + SDM (data objects inline, source apiNames kept)
  3 semantic    parameters -> logical views -> table joins -> calcs -> calc-dimension joins -> metrics (v66.0)
  4 vizzes      68 captured specs, placeholders resolved (v67.0 minorVersion=14)
  5 dashboards  6 captured dashboards, one POST each, all widgets inline
  6 verify      wait for ingest, then every widget/token status Ok and every metric returns data

Asset safety: every created asset is recorded in the checkpoint before anything else happens;
reset() deletes only those.
"""

import json
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from connections import dc_headers, get_dc_token, get_sf_token, load_config, sf_headers  # noqa: E402

from salesinsights import generate  # noqa: E402

PKG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "package")
SOURCE_SDM = "ExtendedSalesInsights"  # exists only in the source org; never deploy there
LABEL = "Sales Insights"
SEM = "v66.0"   # semantic layer: v65.0 ignores customSQLV2 on logical views
VIZ = "v67.0"   # vizzes + dashboards with ?minorVersion=14
MINOR = "minorVersion=14"
SETTERLESS = re.compile(r"setterless' property '([A-Za-z]+)'")


class DeployError(SystemExit):
    pass


# ---- checkpoint ------------------------------------------------------------------------------

def _dir(profile):
    d = os.path.join(ROOT, "demos", "sales_insights", profile)
    os.makedirs(d, exist_ok=True)
    return d


def _load_cp(profile):
    p = os.path.join(_dir(profile), "checkpoint.json")
    if os.path.exists(p):
        return json.load(open(p))
    return {"profile": profile, "done": [], "streams": {}, "jobs": {}, "workspace": None, "sdm": None,
            "semantic": {}, "vizzes": {}, "dashboards": {}, "failures": {}}


def _save_cp(cp):
    with open(os.path.join(_dir(cp["profile"]), "checkpoint.json"), "w") as f:
        json.dump(cp, f, indent=1, default=str)


class _Org:
    def __init__(self, profile):
        self.profile = profile
        self.cfg = load_config(profile)
        self.sf = self.cfg["salesforce"]
        self.refresh()

    def refresh(self):
        self.token, self.inst = get_sf_token(self.cfg, self.profile)
        self.h = sf_headers(self.token)

    def dc(self):
        tok, dom = get_dc_token(self.token, self.inst)
        return dc_headers(tok), tok, dom

    def url(self, path):
        return f"{self.inst}/services/data/{path}"

    def req(self, method, path, body=None, ok=(200, 201, 204)):
        """Request with automatic removal of setterless read-only keys the API rejects."""
        for _ in range(6):
            r = requests.request(method, self.url(path), headers=self.h, json=body)
            if r.status_code == 401:
                self.refresh(); continue
            m = SETTERLESS.search(r.text) if r.status_code == 400 else None
            if m and isinstance(body, dict) and _drop_key(body, m.group(1)):
                continue
            return r
        return r


def _drop_key(o, key):
    found = False
    if isinstance(o, dict):
        if key in o:
            o.pop(key); found = True
        for v in o.values():
            found |= _drop_key(v, key)
    elif isinstance(o, list):
        for v in o:
            found |= _drop_key(v, key)
    return found


def _package():
    return json.load(open(os.path.join(PKG, "sales_insights_package.json"))), \
        json.load(open(os.path.join(PKG, "data_contract.json")))


def _sub(obj, mapping):
    s = json.dumps(obj)
    for k, v in mapping.items():
        s = s.replace(k, v)
    return json.loads(s)


# ---- phase 0 ---------------------------------------------------------------------------------

def _preflight(org, cp):
    r = org.req("GET", f"{SEM}/ssot/semantic/models/{SOURCE_SDM}")
    if r.status_code == 200:
        raise DeployError(f"Refusing to deploy: {org.inst} is the Sales Insights source org ({SOURCE_SDM} exists). "
                          "Pick another profile.")
    for k in ("connector_sf_id", "connector_uuid_name", "ingestion_connector_name"):
        if not org.sf.get(k):
            raise DeployError(f"Profile {org.profile} has no {k}. Run /setup (org_bootstrap.py authorize) for this org first.")
    r = org.req("GET", f"v62.0/ssot/connections/{org.sf['connector_sf_id']}")
    if r.status_code != 200:
        raise DeployError(f"Ingest connector {org.sf['connector_sf_id']} not found on {org.inst}: {r.status_code} {r.text[:200]}")
    if not cp["workspace"]:
        r = org.req("GET", f"{SEM}/tableau/workspaces?limit=200")
        mine = [w for w in (r.json().get("workspaces", []) if r.ok else []) if w.get("label") == LABEL]
        if mine:
            print(f"  note: a '{LABEL}' workspace already exists ({mine[0]['name']}); this deploy creates its own, "
                  "with a numbered apiName")
    print(f"  org {org.inst}, connector {org.sf['ingestion_connector_name']}")


# ---- phase 1: data ---------------------------------------------------------------------------

def _data(org, cp, contract):
    data_dir = os.path.join(_dir(org.profile), "data")
    paths = generate.write_csvs(data_dir)
    cid, cuuid = org.sf["connector_sf_id"], org.sf["connector_uuid_name"]
    existing = {s["name"] for s in org.req("GET", f"v62.0/ssot/connections/{cid}/schema").json().get("schemas", [])}
    for table, spec in contract.items():
        name = cp["streams"].get(table, {}).get("schema", spec["schema"])
        if table in cp["streams"]:
            continue
        if name not in existing:
            body = {"schemas": [{"name": name, "label": name, "schemaType": "IngestApi",
                                 "fields": [{"name": f["name"], "label": f["name"], "dataType": f["dataType"]} for f in spec["fields"]]}]}
            r = org.req("PUT", f"v62.0/ssot/connections/{cid}/schema", body)
            if not r.ok:
                raise DeployError(f"schema {name}: {r.status_code} {r.text[:300]}")
            time.sleep(3)
        payload = {"name": name, "label": name, "datasource": cuuid[:10], "datastreamType": "INGESTAPI",
                   "connectorInfo": {"connectorType": "IngestApi", "connectorDetails": {"name": cuuid, "events": [name]}},
                   "dataLakeObjectInfo": {"label": name, "category": "Other", "dataspaceInfo": [{"name": "default"}],
                                          "dataLakeFieldInputRepresentations": [{"name": "Record_Id", "label": "Record_Id",
                                                                                 "dataType": "Text", "isPrimaryKey": True}],
                                          "eventDateTimeFieldName": "", "recordModifiedFieldName": ""}, "mappings": []}
        r = org.req("POST", "v62.0/ssot/data-streams", payload)
        if r.status_code not in (200, 201):
            raise DeployError(f"stream {name}: {r.status_code} {r.text[:300]}\n"
                              f"If the schema is in use by an old stream, delete that stream in Data Cloud or rerun after reset.")
        j = r.json(); j = j[0] if isinstance(j, list) else j
        cp["streams"][table] = {"schema": name, "stream": j["name"], "dlo": j["dataLakeObjectInfo"]["name"]}
        _save_cp(cp)
        print(f"  stream {j['name']}")
    for table, s in cp["streams"].items():
        for _ in range(60):
            st = org.req("GET", f"v62.0/ssot/data-streams/{s['stream']}").json().get("dataLakeObjectInfo", {}).get("status")
            if st == "ACTIVE":
                break
            time.sleep(10)
        else:
            raise DeployError(f"{s['stream']} never reached ACTIVE")
    time.sleep(30)  # schema propagation to the Bulk API after ACTIVE
    dch, dtok, ddom = org.dc()
    for table, path in paths.items():
        if table in cp["jobs"]:
            continue
        for _ in range(8):
            r = requests.post(f"https://{ddom}/api/v1/ingest/jobs", headers=dch,
                              json={"object": cp["streams"][table]["schema"], "sourceName": org.sf["ingestion_connector_name"],
                                    "operation": "upsert"})
            if r.status_code != 404:
                break
            time.sleep(15)
        if not r.ok:
            raise DeployError(f"ingest job {table}: {r.status_code} {r.text[:300]}")
        jid = r.json()["id"]
        up = requests.put(f"https://{ddom}/api/v1/ingest/jobs/{jid}/batches",
                          headers={"Authorization": f"Bearer {dtok}", "Content-Type": "text/csv"}, data=open(path, "rb").read())
        if not up.ok:
            raise DeployError(f"ingest upload {table}: {up.status_code} {up.text[:300]}")
        requests.patch(f"https://{ddom}/api/v1/ingest/jobs/{jid}", headers=dch, json={"state": "UploadComplete"}).raise_for_status()
        cp["jobs"][table] = jid
        _save_cp(cp)
    print(f"  {len(cp['jobs'])} ingest jobs submitted (they finish in the background; verify waits for them)")


# ---- phase 2: workspace + SDM ------------------------------------------------------------------

def _sdm(org, cp, pkg):
    if not cp["workspace"]:
        r = org.req("POST", f"{SEM}/tableau/workspaces", {"label": LABEL, "description": "Sales Insights (standalone), deployed by AIO"})
        if not r.ok:
            raise DeployError(f"workspace: {r.status_code} {r.text[:300]}")
        cp["workspace"] = {"name": r.json()["name"], "label": r.json().get("label", LABEL)}
        _save_cp(cp)
    if not cp["sdm"]:
        sm = pkg["semanticModel"]
        dlo = {f"{{{{DLO:{t}}}}}": s["dlo"] for t, s in cp["streams"].items()}
        body = {"label": LABEL, "description": sm["description"], "dataspace": "default",
                "semanticDataObjects": _sub(sm["dataObjects"], dlo)}
        if sm.get("businessPreferences"):
            body["businessPreferences"] = sm["businessPreferences"]
        r = org.req("POST", f"{SEM}/ssot/semantic/models", body)
        if not r.ok and "businessPreferences" in body:
            body.pop("businessPreferences")
            r = org.req("POST", f"{SEM}/ssot/semantic/models", body)
            cp["failures"]["business_preferences"] = "SDM create rejected businessPreferences; paste them in the UI"
        if not r.ok:
            raise DeployError(f"SDM: {r.status_code} {r.text[:500]}")
        cp["sdm"] = {"apiName": r.json()["apiName"], "id": r.json()["id"], "label": LABEL}
        _save_cp(cp)
    print(f"  workspace {cp['workspace']['name']}, SDM {cp['sdm']['apiName']} ({cp['sdm']['id']})")


# ---- phase 3: semantic layer ---------------------------------------------------------------------

def _semantic(org, cp, pkg):
    sm, base = pkg["semanticModel"], f"{SEM}/ssot/semantic/models/{cp['sdm']['apiName']}"
    dlo = {f"{{{{DLO:{t}}}}}": s["dlo"] for t, s in cp["streams"].items()}
    done = cp["semantic"]
    fails = cp["failures"].setdefault("semantic", {})

    def post(kind, name, path, body):
        key = f"{kind}:{name}"
        if done.get(key):
            return True
        r = org.req("POST", f"{base}/{path}", body)
        if r.ok or "already exists" in r.text or "DUPLICATE" in r.text:
            done[key] = True; fails.pop(key, None); _save_cp(cp)
            return True
        fails[key] = f"{r.status_code} {r.text[:400]}"; _save_cp(cp)
        print(f"  FAILED {key}: {fails[key][:200]}")
        return False

    calc_names = {c["apiName"] for c in sm["calcs"]}
    def is_calc_join(rel):
        return any(c.get("leftFieldType") == "SemanticField" or c.get("rightFieldType") == "SemanticField"
                   or c["leftSemanticFieldApiName"] in calc_names or c["rightSemanticFieldApiName"] in calc_names
                   for c in rel["criteria"])

    for p in sm["parameters"]:
        post("parameter", p["apiName"], "parameters", dict(p))
    for lv in sm["logicalViews"]:
        post("logical_view", lv["apiName"], "logical-views", _sub(lv, dlo))
    for rel in sm["relationships"]:
        if not is_calc_join(rel):
            post("relationship", rel["apiName"], "relationships", dict(rel))
    for c in sm["calcs"]:
        body = {k: v for k, v in c.items() if k != "_kind"}
        path = "calculated-dimensions" if c["_kind"] == "dimensions" else "calculated-measurements"
        post("calc", c["apiName"], path, body)
    for rel in sm["relationships"]:
        if is_calc_join(rel):
            post("relationship", rel["apiName"], "relationships", dict(rel))
    for m in sm["metrics"]:
        post("metric", m["apiName"], "metrics", dict(m))
    # Joins must come back with criteria (an empty list breaks every query)
    r = org.req("GET", f"{base}/relationships")
    empty = [x["apiName"] for x in r.json().get("items", []) if not x.get("criteria")] if r.ok else []
    if empty:
        fails["relationships_without_criteria"] = empty
    n = len(sm["parameters"]) + len(sm["logicalViews"]) + len(sm["relationships"]) + len(sm["calcs"]) + len(sm["metrics"])
    print(f"  semantic objects: {sum(1 for v in done.values() if v)}/{n} created, {len(fails)} failed")
    if fails:
        raise DeployError("Semantic layer incomplete (see checkpoint failures.semantic). Fix and rerun deploy; it resumes.")


# ---- phases 4-5: vizzes, dashboards ----------------------------------------------------------------

def _base_map(cp):
    return {"{{SDM_API_NAME}}": cp["sdm"]["apiName"], "{{SDM_ID}}": cp["sdm"]["id"], "{{SDM_LABEL}}": cp["sdm"]["label"],
            "{{WORKSPACE_API_NAME}}": cp["workspace"]["name"], "{{WORKSPACE_LABEL}}": cp["workspace"]["label"]}


def _create_named(org, path, body, name):
    """POST with the source name; on a name clash (another deploy in this org) retry with a suffix."""
    for i in range(0, 4):
        body["name"] = name if i == 0 else f"{name}_{i + 1}"
        r = org.req("POST", f"{path}?{MINOR}", body)
        if r.ok:
            return r.json().get("name", body["name"]), None
        if not re.search(r"already|duplicate|unique|in use", r.text, re.I):
            return None, f"{r.status_code} {r.text[:400]}"
    return None, f"{r.status_code} {r.text[:400]}"


def _vizzes(org, cp, pkg):
    fails = cp["failures"].setdefault("vizzes", {})
    base = _base_map(cp)
    for name, spec in pkg["visualizations"].items():
        if name in cp["vizzes"]:
            continue
        created, err = _create_named(org, f"{VIZ}/tableau/visualizations", _sub(spec, base), name)
        if created:
            cp["vizzes"][name] = created; fails.pop(name, None)
        else:
            fails[name] = err; print(f"  FAILED viz {name}: {err[:200]}")
        _save_cp(cp)
    print(f"  vizzes: {len(cp['vizzes'])}/{len(pkg['visualizations'])}")
    if fails:
        raise DeployError("Some vizzes failed (see checkpoint failures.vizzes). Fix and rerun deploy; it resumes.")


def _dashboards(org, cp, pkg):
    fails = cp["failures"].setdefault("dashboards", {})
    m = _base_map(cp)
    m.update({f"{{{{VIZ_NAME_{k}}}}}": v for k, v in cp["vizzes"].items()})
    for name, spec in pkg["dashboards"].items():
        if name in cp["dashboards"]:
            continue
        body = _sub(spec, m)
        left = sorted(set(re.findall(r"\{\{[^}]+\}\}", json.dumps(body))))
        if left:
            fails[name] = f"unresolved placeholders {left[:5]}"; _save_cp(cp); continue
        created, err = _create_named(org, f"{VIZ}/tableau/dashboards", body, name)
        if created:
            cp["dashboards"][name] = created; fails.pop(name, None)
        else:
            fails[name] = err; print(f"  FAILED dashboard {name}: {err[:200]}")
        _save_cp(cp)
    print(f"  dashboards: {len(cp['dashboards'])}/{len(pkg['dashboards'])}")
    if fails:
        raise DeployError("Some dashboards failed (see checkpoint failures.dashboards). Fix and rerun deploy; it resumes.")


# ---- phase 6: verify -----------------------------------------------------------------------------

def _query(org, sdm, body):
    r = org.req("POST", "v65.0/semantic-engine/gateway", dict(body, semanticModelApiName=sdm, dataspace="default"))
    if not r.ok:
        return None, r.text[:300]
    return r.json().get("queryResults", {}).get("queryData", {}).get("rows", []), None


def _verify(org, cp, pkg):
    dch, _, ddom = org.dc()
    for table, jid in cp["jobs"].items():
        for _ in range(90):
            st = requests.get(f"https://{ddom}/api/v1/ingest/jobs/{jid}", headers=dch).json().get("state")
            if st in ("JobComplete", "Failed", "Aborted"):
                break
            time.sleep(10)
        if st != "JobComplete":
            raise DeployError(f"ingest {table} ended {st}")
    print("  all ingest jobs complete")
    sdm, problems = cp["sdm"]["apiName"], []
    time.sleep(20)
    for m in pkg["semanticModel"]["metrics"]:
        rows, err = _query(org, sdm, {"structuredMetricQuery": {"model_api_name": sdm, "time_grain": "Year",
                                                               "submetric_definition": {"metric_api_name": m["apiName"]}}})
        vals = [v for r in (rows or []) for v in r["values"][1:] if isinstance(v, (int, float))]
        ok = bool(vals) and any(vals)
        # show this year's value: the last bucket is next year, where only open deals close (often 0)
        this_year = [r["values"][1] for r in rows or [] if str(r["values"][0]).startswith(time.strftime("%Y"))]
        shown = this_year[0] if this_year and this_year[0] is not None else next((v for v in reversed(vals) if v), None)
        print(f"  metric {m['apiName']}: {'ok, this year ' + str(round(shown, 3) if isinstance(shown, float) else shown) if ok else 'NO DATA ' + str(err or rows)[:120]}")
        if not ok:
            problems.append(f"metric {m['apiName']} returned no data")
    for name, api in cp["dashboards"].items():
        d = org.req("GET", f"{VIZ}/tableau/dashboards/{api}?{MINOR}").json()
        widgets = d.get("widgets", {})
        bad = [(w["name"], w["type"], w.get("status")) for w in widgets.values() if w.get("status") not in (None, "Ok")]
        tokens = [t for w in widgets.values() for t in (w.get("dynamicTokens") or {}).values()]
        bad_t = [t["name"] for t in tokens if t.get("status") not in (None, "Ok")]
        print(f"  {name}: {len(widgets)} widgets, {len(tokens)} tokens, {len(bad)} widget problems, {len(bad_t)} token problems")
        if bad or bad_t:
            problems.append(f"{name}: widgets {bad[:5]} tokens {bad_t[:5]}")
    cp["verify"] = {"problems": problems, "at": time.strftime("%Y-%m-%d %H:%M")}
    _save_cp(cp)
    if problems:
        raise DeployError("Verify found problems:\n  " + "\n  ".join(problems))


# ---- entry points ----------------------------------------------------------------------------------

PHASES = [("preflight", _preflight), ("data", _data), ("sdm", _sdm), ("semantic", _semantic),
          ("vizzes", _vizzes), ("dashboards", _dashboards), ("verify", _verify)]


def deploy(profile):
    pkg, contract = _package()
    cp = _load_cp(profile)
    org = _Org(profile)
    cp["instance"] = org.inst
    for name, fn in PHASES:
        if name in cp["done"] and name != "preflight":
            print(f"[{name}] done (checkpoint)"); continue
        print(f"[{name}]")
        org.refresh()
        args = {"data": (org, cp, contract)}.get(name, (org, cp) if name == "preflight" else (org, cp, pkg))
        fn(*args)
        if name not in cp["done"]:
            cp["done"].append(name)
        _save_cp(cp)
    ws = cp["workspace"]["name"]
    print(f"\nDone. Open Tableau Next -> workspace '{cp['workspace']['label']}' ({ws}).")
    print("Share it in the UI: Share -> All Internal Users -> View (the API rejects sharing).")
    if cp["failures"].get("business_preferences"):
        print("Business preferences were not accepted by the API; paste package businessPreferences into the SDM in the UI.")


def check(profile):
    """Read-only preflight: auth, ingest connector, source-org guard, and any earlier deploy here."""
    cp = _load_cp(profile)
    org = _Org(profile)
    print("[check]")
    _preflight(org, cp)
    if cp.get("instance") and cp["instance"] != org.inst:
        print(f"  note: checkpoint is for {cp['instance']}; this profile now points at {org.inst}")
    if cp["done"]:
        print(f"  earlier deploy: phases done {cp['done']}; deploy resumes from there")
    else:
        print("  no earlier deploy for this profile")
    print("check ok: ready to deploy")


def status(profile):
    cp = _load_cp(profile)
    print(json.dumps({"instance": cp.get("instance"), "done": cp["done"], "workspace": cp["workspace"], "sdm": cp["sdm"],
                      "streams": len(cp["streams"]), "ingest_jobs": len(cp["jobs"]), "semantic": sum(1 for v in cp["semantic"].values() if v),
                      "vizzes": len(cp["vizzes"]), "dashboards": cp["dashboards"],
                      "failures": {k: (len(v) if isinstance(v, dict) else v) for k, v in cp["failures"].items()},
                      "verify": cp.get("verify")}, indent=1))


def reset(profile):
    """Delete only what this profile's checkpoint says the deploy created."""
    cp = _load_cp(profile)
    org = _Org(profile)
    if cp.get("instance") and cp["instance"] != org.inst:
        raise DeployError(f"Checkpoint is for {cp['instance']} but the profile now points at {org.inst}; not deleting.")
    def gone(r):
        return r.status_code in (200, 204, 404)
    for name, api in list(cp["dashboards"].items()):
        r = org.req("DELETE", f"{VIZ}/tableau/dashboards/{api}?{MINOR}")
        print(f"  dashboard {api}: {r.status_code}")
        if gone(r): cp["dashboards"].pop(name); _save_cp(cp)
    for name, api in list(cp["vizzes"].items()):
        r = org.req("DELETE", f"{VIZ}/tableau/visualizations/{api}?{MINOR}")
        if gone(r): cp["vizzes"].pop(name); _save_cp(cp)
        else: print(f"  viz {api}: {r.status_code} {r.text[:150]}")
    print(f"  vizzes left: {len(cp['vizzes'])}")
    if cp["sdm"]:
        r = org.req("DELETE", f"{SEM}/ssot/semantic/models/{cp['sdm']['apiName']}")
        print(f"  SDM {cp['sdm']['apiName']}: {r.status_code}")
        if gone(r): cp["sdm"] = None; cp["semantic"] = {}; _save_cp(cp)
    if cp["workspace"]:
        r = org.req("DELETE", f"{SEM}/tableau/workspaces/{cp['workspace']['name']}")
        print(f"  workspace {cp['workspace']['name']}: {r.status_code}")
        if gone(r): cp["workspace"] = None; _save_cp(cp)
    for table, s in list(cp["streams"].items()):
        r = org.req("DELETE", f"v62.0/ssot/data-streams/{s['stream']}?shouldDeleteDataLakeObject=true")
        print(f"  stream {s['stream']}: {r.status_code}")
        if gone(r): cp["streams"].pop(table); cp["jobs"].pop(table, None); _save_cp(cp)
    cp["done"] = [p for p in cp["done"] if p == "preflight"] if cp["streams"] else []
    cp["failures"] = {}
    _save_cp(cp)
    print("reset done" if not (cp["dashboards"] or cp["vizzes"] or cp["sdm"] or cp["workspace"] or cp["streams"])
          else "reset incomplete; rerun reset")
