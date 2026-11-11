"""
Transfer Tableau Next dashboards between orgs (engine for /transfer-assets and the Web UI).

Uses the Package & Deploy service (https://next-package-deploy.demo.tableau.com):
  1. package   — read-only on the source org: dashboard + vizzes + SDM + calcs + metrics → JSON
  2. data      — makes sure every Ingest API DLO the package uses exists in the target org:
                 reuses a stream built from the same schema, or registers the schema, creates the
                 stream and copies the rows from the source (Data Cloud Query API → Bulk Ingest)
  3. deploy    — patches source DLO names to the target's, then deploys. The first dashboard
                 creates the workspace + SDM; the rest deploy into that same workspace + SDM

The source org is never written to. Checkpoint: demos/{slug}/{slug}_transfer_checkpoint.json

CLI:
  python transfer_assets.py list    --profile <key>
  python transfer_assets.py package --source <key> --dashboards a,b --slug <slug>
  python transfer_assets.py plan    --source <key> --target <key> --slug <slug>      # read-only
  python transfer_assets.py run     --source <key> --target <key> --dashboards a,b --slug <slug>
                                    [--workspace-label "..."] [--sdm-name ...]
  python transfer_assets.py verify  --source <key> --target <key> --slug <slug>      # read-only
  python transfer_assets.py remove  --target <key> --slug <slug> [--workspaces a,b]  # only what it created
"""

import argparse
import io
import json
import os
import re
import sys
import time

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import connections as conn

DEPLOY_BASE = "https://next-package-deploy.demo.tableau.com"
API = "v62.0"
DLO_RE = re.compile(r"[A-Za-z0-9_]+__dll")
# Columns Data Cloud adds to every Ingest API DLO; never part of the ingest schema
SYSTEM_COLUMNS = {"cdp_sys_SourceVersion", "DataSource", "DataSourceObject", "KQ_record_id"}


def _log(on_progress, msg, pct=-1):
    if on_progress:
        on_progress(msg, pct)
    else:
        print(msg, flush=True)


def _step(on_progress, name, detail="", done=False):
    """Step marker the Web UI turns into badges: `[name] detail` while running, `[name] done` at the end."""
    _log(on_progress, f"[{name}] done" if done else f"[{name}] {detail}".rstrip())


class AuthError(RuntimeError):
    """A profile can't log in. `reconnect` means a fresh OAuth login fixes it."""

    def __init__(self, key, label, message, reconnect):
        self.key, self.label, self.reconnect = key, label, reconnect
        super().__init__(message)


# ── Orgs ──────────────────────────────────────────────────────────────────────

class Org:
    """One Salesforce profile from config.json, with fresh tokens on demand."""

    def __init__(self, profile_key, allow_browser=True):
        self.key = profile_key
        self.allow_browser = allow_browser
        self.config = conn.load_config(profile_key, connection_type="salesforce")
        self.sf = self.config["salesforce"]
        self.label = self.config.get("label") or profile_key
        try:
            self.token()  # sets self.instance
        except conn.ReauthRequired:
            raise AuthError(profile_key, self.label, f"The Salesforce login for {self.label} expired.", True)
        except requests.HTTPError as e:
            try:
                desc = e.response.json().get("error_description") or e.response.text[:200]
            except ValueError:
                desc = e.response.text[:200]
            if "client identifier invalid" in desc or "invalid_client" in desc:
                raise AuthError(profile_key, self.label,
                                f"{self.label}: Salesforce doesn't recognize AIO's app ID for this org ({desc}). "
                                "Re-run setup for this connection.", False)
            raise AuthError(profile_key, self.label, f"{self.label} login failed: {desc}", True)

    def token(self):
        tok, inst = conn.get_sf_token(self.config, profile_key=self.key, allow_browser=self.allow_browser)[:2]
        self.instance = inst
        return tok

    def headers(self):
        return conn.sf_headers(self.token())

    def svc_headers(self):
        tok = self.token()
        return {"Authorization": f"Bearer {tok}", "X-Instance-Url": self.instance,
                "Content-Type": "application/json"}

    def get(self, path, **kw):
        h = self.headers()
        return requests.get(f"{self.instance}/services/data/{API}/{path}", headers=h, timeout=120, **kw)

    def dc(self):
        tok, dom = conn.get_dc_token(self.token(), self.instance)[:2]
        return tok, dom

    def ingest_connector(self):
        """(id, uuid_name, short_name) of this org's AIO Ingest API connector."""
        r = self.get("ssot/connections", params={"connectorType": "IngestApi", "limit": 100})
        conns = r.json().get("connections", []) if r.ok else []
        short = self.sf.get("ingestion_connector_name", "")
        match = [c for c in conns if c.get("id") == self.sf.get("connector_sf_id")] or \
                [c for c in conns if short and c.get("name", "").startswith(short)] or conns
        if not match:
            raise RuntimeError(f"No Ingest API connector on {self.label}. Run setup for this org first.")
        c = match[0]
        uuid_name = c["name"]
        short_name = re.sub(r"_[0-9a-f]{8}(_[0-9a-f]{4}){3}_[0-9a-f]{12}$", "", uuid_name)
        return c["id"], uuid_name, short_name

    def schemas(self, connector_id):
        r = self.get(f"ssot/connections/{connector_id}/schema")
        return r.json().get("schemas", []) if r.ok else []

    def streams(self, refresh=False):
        if getattr(self, "_streams", None) is not None and not refresh:
            return self._streams
        self._streams = out = []
        while True:  # limit tops out at 200; nextPageUrl appears only when there are more
            r = self.get("ssot/data-streams", params={"limit": 200, "offset": len(out)})
            r.raise_for_status()
            j = r.json()
            out.extend(j.get("dataStreams", []))
            if not j.get("nextPageUrl") or not j.get("dataStreams"):
                return out


def login_status(profile_key):
    """Can this profile log in without a browser? For the Web UI's pre-check."""
    try:
        org = Org(profile_key, allow_browser=False)
        return {"ok": True, "label": org.label, "instance": org.instance}
    except AuthError as e:
        return {"ok": False, "label": e.label, "error": str(e), "reconnect": e.reconnect}


# ── Checkpoint ────────────────────────────────────────────────────────────────

def demo_dir(slug):
    d = os.path.join(ROOT, "demos", slug)
    os.makedirs(d, exist_ok=True)
    return d


def load_cp(slug):
    p = os.path.join(demo_dir(slug), f"{slug}_transfer_checkpoint.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def save_cp(slug, cp):
    p = os.path.join(demo_dir(slug), f"{slug}_transfer_checkpoint.json")
    json.dump(cp, open(p, "w"), indent=2)


# ── 1. Package (source, read-only) ────────────────────────────────────────────

def list_dashboards(org):
    r = requests.get(f"{DEPLOY_BASE}/api/v1/dashboards/list", headers=org.svc_headers(), timeout=120)
    r.raise_for_status()
    return [{"name": d["name"], "label": d.get("label", d["name"]),
             "workspace": d.get("workspaceIdOrApiName", ""),
             "template": (d.get("templateSource") or {}).get("name", "")}
            for d in r.json().get("dashboards", [])]


def package_dashboards(org, names, slug, on_progress=None):
    """Package each dashboard; returns {name: package_data}. Saves each package JSON."""
    h = org.svc_headers()
    jobs = {}
    for n in names:
        r = requests.post(f"{DEPLOY_BASE}/api/v1/dashboards/package", headers=h,
                          json={"dashboard_api_name": n}, timeout=120)
        r.raise_for_status()
        jobs[n] = r.json()["job_id"]
    out = {}
    for n, job in jobs.items():
        for _ in range(120):
            s = requests.get(f"{DEPLOY_BASE}/api/v1/dashboards/package/status/{job}",
                             headers=h, timeout=120).json()
            if s.get("status") not in ("pending", "running", "queued"):
                break
            time.sleep(5)
        if s.get("status") != "completed" or not s.get("package_data"):
            raise RuntimeError(f"Packaging {n} failed: {s.get('error') or s.get('status')}")
        out[n] = s["package_data"]
        json.dump(out[n], open(os.path.join(demo_dir(slug), f"{n}_package.json"), "w"), indent=1)
        _step(on_progress, "package", f"Packaged {len(out)}/{len(jobs)}: {n}")
    return out


def package_dlos(package_data):
    return sorted(set(DLO_RE.findall(json.dumps(package_data))))


# ── 2. Data (find or build the target DLOs) ───────────────────────────────────

def source_dataset(src, dlo):
    """Describe an Ingest API DLO in the source org: stream, schema name, fields, primary key.
    Returns None for DLOs that aren't Ingest API (CRM `_Home__dll` objects exist in every org)."""
    stream = next((s for s in src.streams()
                   if (s.get("dataLakeObjectInfo") or {}).get("name") == dlo), None)
    if not stream or (stream.get("connectorInfo") or {}).get("connectorType") != "IngestApi":
        return None
    detail = src.get(f"ssot/data-streams/{stream['name']}").json()
    dl_fields = (detail.get("dataLakeObjectInfo") or {}).get("dataLakeFieldInfoRepresentation", [])
    # The stream GET has no schema/event name; it's the stream name minus connector prefix + hash.
    # Look it up on every Ingest connector, since the demo may not use this profile's connector.
    r = src.get("ssot/connections", params={"connectorType": "IngestApi", "limit": 100})
    for c in (r.json().get("connections", []) if r.ok else []):
        for sch in src.schemas(c["id"]):
            name = sch["name"]
            if re.search(rf"_{re.escape(name)}_[0-9A-F]{{8}}$", stream["name"]):
                pk = next((f["name"] for f in dl_fields if f.get("isPrimaryKey")), None)
                field_names = [f["name"] for f in sch["fields"]]
                if not pk or pk not in field_names:
                    pk = "record_id" if "record_id" in field_names else field_names[0]
                return {"dlo": dlo, "stream": stream["name"], "schema": name,
                        "fields": [{"name": f["name"], "label": f.get("label", f["name"]),
                                    "dataType": f["dataType"]} for f in sch["fields"]],
                        "pk": pk}
    raise RuntimeError(f"Couldn't find the ingest schema behind {stream['name']} in {src.label}")


def find_target_stream(tgt, schema_name, refresh=False):
    """An existing target stream built from this schema → (stream_name, dlo_name) or None."""
    for s in tgt.streams(refresh):
        if re.search(rf"_{re.escape(schema_name)}_[0-9A-F]{{8}}$", s.get("name", "")) and \
           (s.get("connectorInfo") or {}).get("connectorType") == "IngestApi":
            return s["name"], s["dataLakeObjectInfo"]["name"]
    return None


def create_target_stream(tgt, ds, on_progress=None):
    """Register the schema (if missing) and create the stream; wait for ACTIVE."""
    cid, cuuid, _ = tgt.ingest_connector()
    h = tgt.headers()
    if not any(s["name"] == ds["schema"] for s in tgt.schemas(cid)):
        _log(on_progress, f"[data] Registering schema {ds['schema']}...")
        new = {"name": ds["schema"], "label": ds["schema"], "schemaType": "IngestApi",
               "fields": ds["fields"]}
        r = requests.put(f"{tgt.instance}/services/data/{API}/ssot/connections/{cid}/schema",
                         headers=h, json={"schemas": [new]}, timeout=120)
        if not r.ok:
            raise RuntimeError(f"Schema registration failed: {r.status_code} {r.text[:300]}")
        time.sleep(10)
    _log(on_progress, f"[data] Creating data stream for {ds['schema']}...")
    payload = {
        "name": ds["schema"], "label": ds["schema"], "datasource": cuuid[:10],
        "datastreamType": "INGESTAPI",
        "connectorInfo": {"connectorType": "IngestApi",
                          "connectorDetails": {"name": cuuid, "events": [ds["schema"]]}},
        "dataLakeObjectInfo": {
            "label": ds["schema"], "category": "Other", "dataspaceInfo": [{"name": "default"}],
            "dataLakeFieldInputRepresentations": [
                {"name": ds["pk"], "label": ds["pk"], "dataType": "Text", "isPrimaryKey": True}],
            "eventDateTimeFieldName": "", "recordModifiedFieldName": "",
        },
        "mappings": [],
    }
    for attempt in range(4):
        r = requests.post(f"{tgt.instance}/services/data/{API}/ssot/data-streams",
                          headers=tgt.headers(), json=payload, timeout=120)
        if r.status_code in (200, 201):
            break
        found = find_target_stream(tgt, ds["schema"], refresh=True)
        if found:
            break
        time.sleep(15)  # schema propagation
    else:
        raise RuntimeError(f"Stream creation failed: {r.status_code} {r.text[:300]}")
    found = find_target_stream(tgt, ds["schema"], refresh=True)
    if not found:
        body = r.json()
        body = body[0] if isinstance(body, list) else body
        found = (body["name"], body["dataLakeObjectInfo"]["name"])
    stream_name, dlo_name = found
    for i in range(36):
        st = tgt.get(f"ssot/data-streams/{stream_name}").json()
        if (st.get("dataLakeObjectInfo") or {}).get("status") == "ACTIVE":
            break
        _log(on_progress, f"[data] Waiting for {dlo_name} to go ACTIVE... ({(i + 1) * 10}s)")
        time.sleep(10)
    time.sleep(30)  # Bulk API lags ACTIVE by 15-30s
    return stream_name, dlo_name


def query_rows(org, sql):
    """Run a Data Cloud query and return a DataFrame (follows nextBatchId pages)."""
    tok, dom = org.dc()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    r = requests.post(f"https://{dom}/api/v2/query", headers=h, json={"sql": sql}, timeout=300)
    if not r.ok:
        raise RuntimeError(f"Query failed on {org.label}: {r.status_code} {r.text[:300]}")
    j = r.json()
    cols = [c for c, _ in sorted(j["metadata"].items(), key=lambda kv: kv[1]["placeInOrder"])]
    rows = list(j.get("data", []))
    while j.get("nextBatchId"):
        r = requests.get(f"https://{dom}/api/v2/query/{j['nextBatchId']}", headers=h, timeout=300)
        r.raise_for_status()
        j = r.json()
        rows.extend(j.get("data", []))
    return pd.DataFrame(rows, columns=cols)


def copy_rows(src, tgt, ds, slug, on_progress=None):
    """Copy every row of the source DLO into the target schema via Bulk Ingest (upsert)."""
    cols = ", ".join(f"{f['name']}__c" for f in ds["fields"])
    df = query_rows(src, f"SELECT {cols} FROM {ds['dlo']}")
    df.columns = [c[:-3] if c.endswith("__c") else c for c in df.columns]
    _log(on_progress, f"[data] Downloaded {len(df):,} rows from {src.label}")
    df.to_csv(os.path.join(demo_dir(slug), f"{ds['schema']}_transferred.csv"), index=False)

    _, _, short = tgt.ingest_connector()
    tok, dom = tgt.dc()
    jh = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    for attempt in range(8):
        r = requests.post(f"https://{dom}/api/v1/ingest/jobs", headers=jh, timeout=120,
                          json={"object": ds["schema"], "sourceName": short, "operation": "upsert"})
        if r.status_code != 404:
            break
        _log(on_progress, f"[data] Schema not ready for ingest yet, retrying... ({attempt + 1}/8)")
        time.sleep(15)
    if not r.ok:
        raise RuntimeError(f"Ingest job failed: {r.status_code} {r.text[:300]}")
    job = r.json()["id"]
    for start in range(0, len(df), 100_000):
        buf = io.StringIO()
        df.iloc[start:start + 100_000].to_csv(buf, index=False, lineterminator="\n")
        r = requests.put(f"https://{dom}/api/v1/ingest/jobs/{job}/batches", timeout=300,
                         headers={"Authorization": f"Bearer {tok}", "Content-Type": "text/csv"},
                         data=buf.getvalue().encode("utf-8"))
        r.raise_for_status()
    requests.patch(f"https://{dom}/api/v1/ingest/jobs/{job}", headers=jh,
                   json={"state": "UploadComplete"}, timeout=120).raise_for_status()
    for i in range(60):
        state = requests.get(f"https://{dom}/api/v1/ingest/jobs/{job}", headers=jh, timeout=120).json()
        if state.get("state") == "JobComplete":
            break
        if state.get("state") in ("Failed", "Aborted"):
            raise RuntimeError(f"Ingest failed: {state}")
        _log(on_progress, f"[data] Data Cloud is loading the rows: {state.get('state')} ({(i + 1) * 10}s)")
        time.sleep(10)
    return len(df)


def ensure_target_data(src, tgt, dlos, slug, cp, on_progress=None):
    """Map every source Ingest DLO to a target DLO with data. Returns {source_dlo: target_dlo}."""
    dlo_map = cp.setdefault("dlo_map", {})
    for dlo in dlos:
        if dlo in dlo_map:
            continue
        ds = source_dataset(src, dlo)
        if ds is None:
            _log(on_progress, f"[data] {dlo} isn't an Ingest API object; using the same name in the target")
            dlo_map[dlo] = dlo
            continue
        found = find_target_stream(tgt, ds["schema"])
        if found:
            _log(on_progress, f"[data] Target already has {ds['schema']} ({found[1]}); refreshing its rows")
            stream_name, tgt_dlo = found
        else:
            stream_name, tgt_dlo = create_target_stream(tgt, ds, on_progress)
        rows = copy_rows(src, tgt, ds, slug, on_progress)
        dlo_map[dlo] = tgt_dlo
        cp.setdefault("streams", {})[tgt_dlo] = {"stream": stream_name, "schema": ds["schema"], "rows": rows}
        save_cp(slug, cp)
    return dlo_map


def wait_for_rows(tgt, dlo, expected, on_progress=None, timeout=600):
    """Bulk ingest reports JobComplete before rows are queryable; wait until they are."""
    n = 0
    for i in range(timeout // 15):
        try:
            n = int(query_rows(tgt, f"SELECT COUNT(*) FROM {dlo}").iloc[0, 0])
        except RuntimeError:
            n = 0
        if n >= expected:
            return n
        _log(on_progress, f"[data] {dlo}: {n:,}/{expected:,} rows queryable...")
        time.sleep(15)
    return n


# ── 3. Deploy (target) ────────────────────────────────────────────────────────

def patch_package(package_data, dlo_map):
    s = json.dumps(package_data)
    for a, b in dlo_map.items():
        s = s.replace(a, b)
    return json.loads(s)


def deploy(tgt, package_data, workspace=None, sdm=None, workspace_label=None, sdm_name=None,
           on_progress=None):
    """Deploy one package. New workspace + SDM unless `workspace`/`sdm` (existing apiNames) are given."""
    h = tgt.svc_headers()
    if workspace and sdm:
        r = requests.post(f"{DEPLOY_BASE}/api/v1/deployment/validate-requirements", headers=h,
                          timeout=120, json={"package_data": package_data, "sdm_api_name": sdm})
        v = r.json() if r.ok else {}
        missing = v.get("missing") or {}
        if any(missing.values()):
            raise RuntimeError(f"Target SDM {sdm} is missing: {json.dumps(missing)[:500]}")
        body = {"workspace_choice": "existing", "workspace_api_name": workspace,
                "sdm_choice": "existing", "sdm_api_name": sdm}
    else:
        body = {"workspace_choice": "create", "workspace_label": workspace_label,
                "sdm_choice": "create", "sdm_api_name": sdm_name}
    body.update({"package_data": package_data, "dependency_map": {}, "dry_run": False,
                 "skip_validation": False})
    r = requests.post(f"{DEPLOY_BASE}/api/v1/deployment/deploy", headers=h, json=body, timeout=300)
    if not r.ok:
        raise RuntimeError(f"Deploy request failed: {r.status_code} {r.text[:500]}")
    job = r.json()["job_id"]
    seen = 0
    for _ in range(180):
        time.sleep(5)
        s = requests.get(f"{DEPLOY_BASE}/api/v1/deployment/deploy/status/{job}",
                         headers=tgt.svc_headers(), timeout=120).json()
        for step in (s.get("steps") or [])[seen:]:
            _log(on_progress, f"  {step}")
        seen = len(s.get("steps") or [])
        if s.get("status") in ("completed", "done", "success"):
            return s
        if s.get("status") in ("failed", "error"):
            raise RuntimeError(f"Deploy failed: {s.get('error')}")
    raise RuntimeError("Deploy timed out after 15 minutes")


def load_packages(src, dashboards, slug, on_progress=None):
    """Package any dashboard without a saved package; return {name: package_data} for all."""
    todo = [d for d in dashboards if not os.path.exists(os.path.join(demo_dir(slug), f"{d}_package.json"))]
    packages = package_dashboards(src, todo, slug, on_progress) if todo else {}
    for d in dashboards:
        packages.setdefault(d, json.load(open(os.path.join(demo_dir(slug), f"{d}_package.json"))))
    return packages


def plan(source, target, dashboards, slug, on_progress=None):
    """Read-only preview: what each dashboard brings and what the target needs for its data."""
    src, tgt = Org(source), Org(target)
    _step(on_progress, "package", f"Packaging {len(dashboards)} dashboard(s) from {src.label}")
    packages = load_packages(src, dashboards, slug, on_progress)
    _step(on_progress, "package", done=True)
    sdms = {p["components"]["semanticModel"].get("label") for p in packages.values()}
    dlos = sorted({x for p in packages.values() for x in package_dlos(p)})
    _step(on_progress, "source", f"Finding the data behind {len(dlos)} object(s) in {src.label} (listing streams takes ~30s)")
    sources = {dlo: source_dataset(src, dlo) for dlo in dlos}
    _step(on_progress, "source", done=True)
    _step(on_progress, "target", f"Checking {tgt.label} for the same data (~30s)")
    data = []
    for dlo in dlos:
        ds = sources[dlo]
        found = find_target_stream(tgt, ds["schema"]) if ds else (None, dlo)
        data.append({"source_dlo": dlo, "schema": ds and ds["schema"], "target_dlo": found and found[1],
                     "action": "reuse + refresh rows" if (ds and found) else ("same object" if not ds else "create + copy rows")})
    _step(on_progress, "target", done=True)
    return {"source": src.label, "target": tgt.label,
            "dashboards": [{"name": n, "label": p["components"]["dashboard"].get("label", n),
                            "vizzes": len(p["components"].get("visualizations", {})),
                            "metrics": len(p["components"].get("metrics", [])),
                            "semantic_model": p["components"]["semanticModel"].get("label")}
                           for n, p in packages.items()],
            "single_sdm": len(sdms) == 1, "data": data}


def run(source, target, dashboards, slug, workspace_label=None, sdm_name=None, on_progress=None):
    src, tgt = Org(source), Org(target)
    cp = load_cp(slug)
    cp.update({"source": source, "target": target, "dashboards": dashboards})
    save_cp(slug, cp)

    _step(on_progress, "package", f"Packaging {len(dashboards)} dashboard(s) from {src.label}")
    packages = load_packages(src, dashboards, slug, on_progress)
    _step(on_progress, "package", done=True)

    _step(on_progress, "data", f"Checking data in {tgt.label}")
    dlos = sorted({x for p in packages.values() for x in package_dlos(p)})
    dlo_map = ensure_target_data(src, tgt, dlos, slug, cp, on_progress)
    for tdlo, info in cp.get("streams", {}).items():
        n = wait_for_rows(tgt, tdlo, info["rows"], on_progress)
        _step(on_progress, "data", f"{n:,} rows ready in {tdlo}")
    _step(on_progress, "data", done=True)

    first = packages[dashboards[0]]
    workspace_label = workspace_label or first["components"]["dashboard"].get("label", slug)
    sdm_name = sdm_name or re.sub(r"\W+", "_", first["components"]["semanticModel"].get("label", slug)).strip("_")
    done = cp.setdefault("deployed", {})
    for i, d in enumerate(dashboards):
        if d in done:
            continue
        _step(on_progress, "deploy", f"{i + 1}/{len(dashboards)}: {d}")
        pkg = patch_package(packages[d], dlo_map)
        s = deploy(tgt, pkg, cp.get("workspace"), cp.get("sdm"), workspace_label, sdm_name, on_progress)
        created = cp.setdefault("created", {"workspaces": [], "sdms": []})
        if s.get("workspace_api_name") and s["workspace_api_name"] not in created["workspaces"]:
            created["workspaces"].append(s["workspace_api_name"])
        if _created_sdm(s) and _created_sdm(s) not in created["sdms"]:
            created["sdms"].append(_created_sdm(s))
        cp["workspace"] = cp.get("workspace") or s.get("workspace_api_name")
        cp["sdm"] = cp.get("sdm") or _created_sdm(s)
        done[d] = {"url": s.get("workspace_url"), "status": s}
        save_cp(slug, cp)
    _step(on_progress, "deploy", done=True)
    _step(on_progress, "verify", "Checking every metric against the source")
    verify(source, target, slug, on_progress)
    _step(on_progress, "verify", done=True)
    return load_cp(slug)


def metric_totals(org, sdm):
    """{metric apiName: [yearly values]} from a live SDM query (same call as salesinsights verify)."""
    r = requests.get(f"{org.instance}/services/data/v65.0/ssot/semantic/models/{sdm}/metrics",
                     headers=org.headers(), timeout=120)
    out = {}
    for m in (r.json().get("metrics", []) if r.ok else []):
        q = {"semanticModelApiName": sdm, "dataspace": "default",
             "structuredMetricQuery": {"model_api_name": sdm, "time_grain": "Year",
                                       "submetric_definition": {"metric_api_name": m["apiName"]}}}
        g = requests.post(f"{org.instance}/services/data/v65.0/semantic-engine/gateway",
                          headers=org.headers(), json=q, timeout=120)
        rows = g.json().get("queryResults", {}).get("queryData", {}).get("rows", []) if g.ok else []
        out[m["apiName"]] = [round(float(v), 4) for row in rows for v in row["values"][1:]
                             if isinstance(v, (int, float))]
    return out


def verify(source, target, slug, on_progress=None):
    """Every target metric returns the same values as the source's. Returns {metric: ok}."""
    src, tgt = Org(source), Org(target)
    cp = load_cp(slug)
    first = json.load(open(os.path.join(demo_dir(slug), f"{cp['dashboards'][0]}_package.json")))
    want = metric_totals(src, first["components"]["semanticModel"]["apiName"])
    got = metric_totals(tgt, cp["sdm"])
    result = {}
    for m, vals in want.items():
        result[m] = bool(vals) and got.get(m) == vals
        _log(on_progress, f"  {'✓' if result[m] else '✕'} {m}: source {vals[-3:]} target {got.get(m, [])[-3:]}")
    cp["verify"] = {"at": time.strftime("%Y-%m-%d %H:%M"), "metrics": result}
    save_cp(slug, cp)
    return result


def remove(target, slug, workspaces=None, on_progress=None):
    """Delete what this transfer created in the target: dashboards, vizzes, workspaces, SDMs.
    Only names recorded in the checkpoint's `created` lists are touched. Data streams stay."""
    tgt = Org(target)
    cp = load_cp(slug)
    created = cp.get("created", {"workspaces": [], "sdms": []})
    wss = [w for w in (workspaces or created["workspaces"]) if w in created["workspaces"]]
    base = f"{tgt.instance}/services/data/v66.0"
    sdms = set()
    for ws in wss:
        r = requests.get(f"{base}/tableau/workspaces/{ws}/assets", headers=tgt.headers(), timeout=120)
        assets = r.json().get("workspaceAssets", []) if r.ok else []
        for kind, path in (("AnalyticsDashboard", "dashboards"), ("AnalyticsVisualization", "visualizations")):
            for a in assets:
                if a["assetType"] == kind and a.get("assetUsageType") == "Created":
                    d = requests.delete(f"{base}/tableau/{path}/{a['name']}?minorVersion=12",
                                        headers=tgt.headers(), timeout=120)
                    _log(on_progress, f"  delete {path[:-1]} {a['name']}: {d.status_code}")
        sdms |= {a["name"] for a in assets if a["assetType"] == "SemanticModel"} & set(created["sdms"])
        d = requests.delete(f"{base}/tableau/workspaces/{ws}", headers=tgt.headers(), timeout=120)
        _log(on_progress, f"  delete workspace {ws}: {d.status_code}")
        created["workspaces"].remove(ws)
    for sdm in sdms:
        d = requests.delete(f"{base}/ssot/semantic/models/{sdm}", headers=tgt.headers(), timeout=120)
        _log(on_progress, f"  delete semantic model {sdm}: {d.status_code}")
        if d.ok or d.status_code == 404:
            created["sdms"].remove(sdm)
    for name, info in list(cp.get("deployed", {}).items()):
        if (info.get("status") or {}).get("workspace_api_name") in wss:
            cp["deployed"].pop(name)
    if cp.get("workspace") in wss:
        cp["workspace"] = cp["sdm"] = None
    save_cp(slug, cp)


def _created_sdm(status):
    """The deploy status names the workspace but not the SDM; the SDM is only in a step message."""
    for step in status.get("steps") or []:
        m = re.match(r"Semantic Model '([^']+)' created", step)
        if m:
            return m.group(1)
    return status.get("sdm_api_name")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Transfer Tableau Next dashboards between orgs")
    p.add_argument("command", choices=["list", "package", "plan", "run", "verify", "remove"])
    p.add_argument("--profile")
    p.add_argument("--source")
    p.add_argument("--target")
    p.add_argument("--dashboards", default="")
    p.add_argument("--slug")
    p.add_argument("--workspace-label")
    p.add_argument("--sdm-name")
    p.add_argument("--workspaces", help="remove: only these created workspaces (default: all)")
    p.add_argument("--fresh", action="store_true", help="re-package even if a saved package exists")
    a = p.parse_args()
    names = [x for x in a.dashboards.split(",") if x]

    if a.command == "list":
        print(json.dumps(list_dashboards(Org(a.profile or a.source)), indent=2))
    elif a.command == "package":
        pk = package_dashboards(Org(a.source), names, a.slug)
        print(json.dumps({n: package_dlos(v) for n, v in pk.items()}, indent=2))
    elif a.command == "plan":
        if a.fresh:
            for n in names:
                f = os.path.join(demo_dir(a.slug), f"{n}_package.json")
                if os.path.exists(f):
                    os.remove(f)
        print("PLAN_JSON " + json.dumps(plan(a.source, a.target, names, a.slug)))
    elif a.command == "run":
        cp = run(a.source, a.target, names, a.slug, a.workspace_label, a.sdm_name)
        print("RESULT_JSON " + json.dumps({"workspace": cp.get("workspace"), "sdm": cp.get("sdm"),
                                           "dlo_map": cp.get("dlo_map"), "verify": cp.get("verify"),
                                           "deployed": {n: {"url": v.get("url")} for n, v in cp["deployed"].items()}}))
    elif a.command == "remove":
        remove(a.target, a.slug, [w for w in (a.workspaces or "").split(",") if w] or None)
    elif a.command == "verify":
        ok = verify(a.source, a.target, a.slug)
        sys.exit(0 if ok and all(ok.values()) else 1)


if __name__ == "__main__":
    try:
        main()
    except AuthError as e:
        print("AUTH_ERROR " + json.dumps({"profile": e.key, "label": e.label, "message": str(e),
                                          "reconnect": e.reconnect}), flush=True)
        sys.exit(3)
