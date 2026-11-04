"""Refresh CRM Analytics apps after CRM data changes: Data Sync, then every recipe the
apps' dashboards depend on, in dependency order.

    python crma_refresh.py --org <alias> --apps Einstein_Account_Management,Revenue_Insights --plan
    python crma_refresh.py --org <alias> --apps Einstein_Account_Management,Revenue_Insights

The chain is discovered, not hard-coded: start from the datasets the apps' dashboards use,
walk back through the recipes that save them (and the datasets those recipes load), then
run the recipes in waves — a recipe starts once every recipe producing its inputs is done.
Recipes in the same wave run in parallel.

Uses the sf CLI's stored auth (no tokens handled here). Running a recipe or sync only
rebuilds CRM Analytics datasets; no CRM records are changed.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

API = "/services/data/v62.0/wave"
DONE = {"Success", "Warning", "Failure", "Failed", "Canceled", "Cancelled"}
OK = {"Success", "Warning"}
TRANSIENT = ("fetch failed", "ECONNRESET", "ETIMEDOUT", "socket hang up")


class Org:
    def __init__(self, alias):
        self.alias = alias

    def rest(self, path, method="GET", body=None):
        args = ["sf", "api", "request", "rest", API + path, "-X", method, "-o", self.alias]
        if body is not None or method != "GET":
            args += ["-b", json.dumps(body if body is not None else {})]   # sf CLI rejects a body-less POST
        for attempt in range(4):
            r = subprocess.run(args, capture_output=True, text=True)
            out = (r.stdout or "").strip()
            if any(t in out + r.stderr for t in TRANSIENT) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            if not out:
                if r.returncode != 0:   # never treat a CLI error as an empty success
                    raise RuntimeError(f"{method} {path}: {(r.stderr or 'no output')[:500]}")
                return {}
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                raise RuntimeError(f"{method} {path}: {out[:500]} {r.stderr[:500]}")

    def pages(self, path, key):
        out, url = [], path
        while url:
            d = self.rest(url)
            out += d.get(key, [])
            nxt = d.get("nextPageUrl")
            url = nxt.split("/wave", 1)[1] if nxt else None
        return out


def discover(org, app_names, exclude=()):
    """Return (recipes_needed, waves). Each recipe: {id, label, dataflow_id, loads, saves}."""
    folders = {f["name"]: f for f in org.pages("/folders?pageSize=200", "folders")}
    missing = [a for a in app_names if a not in folders]
    if missing:
        raise SystemExit(f"App(s) not found: {missing}. Available: {sorted(folders)}")

    needed = set()
    for app in app_names:
        fid = folders[app]["id"]
        for dtype in ("dashboard", "component"):
            for dash in org.pages(f"/dashboards?folderId={fid}&type={dtype}&pageSize=200", "dashboards"):
                needed |= {d["name"] for d in dash.get("datasets", [])}

    recipes = []
    for r in org.pages("/recipes?pageSize=200", "recipes"):
        if any(x.lower() in r["label"].lower() for x in exclude):
            continue
        d = org.rest(f"/recipes/{r['id']}?format=R3")
        nodes = (d.get("recipeDefinition") or {}).get("nodes", {})
        loads = {n["parameters"]["dataset"].get("name") for n in nodes.values()
                 if n["action"] == "load" and n["parameters"]["dataset"].get("type") == "analyticsDataset"}
        saves = {n["parameters"]["dataset"]["name"] for n in nodes.values() if n["action"] == "save"}
        if saves and d.get("targetDataflowId"):
            recipes.append({"id": r["id"], "label": r["label"], "dataflow_id": d["targetDataflowId"],
                            "loads": loads - saves, "saves": saves})

    # walk back from the dashboards' datasets to every recipe that feeds them
    chosen, frontier = {}, set(needed)
    while frontier:
        ds = frontier.pop()
        for r in recipes:
            if ds in r["saves"] and r["id"] not in chosen:
                chosen[r["id"]] = r
                frontier |= r["loads"] - needed
                needed |= r["loads"]

    # waves: a recipe runs after every chosen recipe that saves one of its inputs
    producers = {ds: rid for rid, r in chosen.items() for ds in r["saves"]}
    deps = {rid: {producers[ds] for ds in r["loads"] if ds in producers and producers[ds] != rid}
            for rid, r in chosen.items()}
    waves, done = [], set()
    while len(done) < len(chosen):
        wave = [rid for rid in chosen if rid not in done and deps[rid] <= done]
        if not wave:
            raise SystemExit(f"Dependency cycle among: {[chosen[r]['label'] for r in chosen if r not in done]}")
        waves.append(wave)
        done |= set(wave)
    return chosen, waves


def wait_jobs(org, job_ids, label, timeout_min=120):
    """Poll dataflow jobs until all finish. Returns {job_id: status}."""
    deadline, status = time.time() + timeout_min * 60, {}
    while time.time() < deadline:
        for jid in job_ids:
            if status.get(jid) not in DONE:
                try:
                    status[jid] = org.rest(f"/dataflowjobs/{jid}").get("status")
                except RuntimeError as e:   # network blip: the job keeps running in Salesforce; poll again
                    print(f"  (status check failed, retrying: {str(e)[:80]})")
        if all(s in DONE for s in status.values()):
            return status
        time.sleep(15)
    raise SystemExit(f"Timed out after {timeout_min} min waiting for {label}: {status}")


def run_sync(org, connector_name="SFDC_LOCAL", timeout_min=60):
    conns = org.pages("/dataConnectors?pageSize=200", "dataConnectors")
    conn = next((c for c in conns if c.get("name") == connector_name), None)
    if not conn:
        raise SystemExit(f"Connector {connector_name} not found")
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    resp = org.rest(f"/dataConnectors/{conn['id']}/ingest", "POST")
    if "sync request was sent" not in str(resp.get("message", "")).lower():
        raise SystemExit(f"Data Sync didn't start: {resp}")
    print(f"→ Data Sync ({connector_name}) started")
    time.sleep(20)
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        jobs = [j for j in org.pages("/dataflowjobs?pageSize=200", "dataflowJobs")
                if j["jobType"] == "datasync" and j["startDate"] >= started]
        running = [j for j in jobs if j["status"] not in DONE]
        if jobs and not running:
            failed = sorted({j["label"] for j in jobs if j["status"] not in OK})
            print(f"  sync finished: {len(jobs)} objects" + (f", {len(failed)} failed: {failed[:8]}" if failed else ""))
            return failed
        time.sleep(20)
    raise SystemExit(f"Data Sync still running after {timeout_min} min")


def refresh(alias, apps, plan_only=False, skip_sync=False, exclude=("ED Recipe", "Demo")):
    org = Org(alias)
    chosen, waves = discover(org, apps, exclude)
    print(f"Refresh chain for {', '.join(apps)}:")
    print("  0. Data Sync (SFDC_LOCAL)" + (" — skipped" if skip_sync else ""))
    for i, wave in enumerate(waves, 1):
        print(f"  {i}. " + " | ".join(chosen[r]["label"] for r in wave))
    if plan_only:
        return

    if not skip_sync:
        run_sync(org)
    for i, wave in enumerate(waves, 1):
        jobs = {}
        for rid in wave:
            j = org.rest("/dataflowjobs", "POST", {"dataflowId": chosen[rid]["dataflow_id"], "command": "start"})
            if not j.get("id"):
                raise SystemExit(f"Couldn't start {chosen[rid]['label']}: {j}")
            jobs[j["id"]] = chosen[rid]["label"]
        print(f"→ wave {i}: started {', '.join(jobs.values())}")
        status = wait_jobs(org, list(jobs), f"wave {i}")
        for jid, s in status.items():
            print(f"  {jobs[jid]}: {s}")
        bad = [jobs[j] for j, s in status.items() if s not in OK]
        if bad:
            raise SystemExit(f"Stopped: {bad} failed. Check Data Manager → Jobs Monitor, then rerun "
                             f"(add --skip-sync to skip the sync).")
    print("\nRefresh complete.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org", required=True, help="sf CLI org alias")
    ap.add_argument("--apps", required=True, help="comma-separated app (folder) API names")
    ap.add_argument("--plan", action="store_true", help="show the chain, run nothing")
    ap.add_argument("--skip-sync", action="store_true", help="recipes only (sync already ran)")
    ap.add_argument("--exclude", default="ED Recipe,Demo", help="comma-separated recipe label fragments to skip")
    a = ap.parse_args()
    refresh(a.org, [x.strip() for x in a.apps.split(",")], a.plan, a.skip_sync,
            tuple(x.strip() for x in a.exclude.split(",") if x.strip()))
