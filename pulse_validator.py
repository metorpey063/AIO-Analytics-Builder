"""
Pulse API Validator — Canary site early-warning system

Runs against a Tableau Cloud site on a canary pod (10ax) that receives
releases before production pods. Tests every payload variation used by
/build-demo to detect breaking changes before they hit user sites.

Usage:
    python3 pulse_validator.py              # Run all tests
    python3 pulse_validator.py --quiet      # Only print failures

Integrated into /build-demo: runs automatically once per week (or if the
server build version has changed since last validation).

Release rollout canvas (Tableau Cloud pod deployment schedule):
    https://salesforce.enterprise.slack.com/docs/T7KUQ9FLZ/F094XCHG0Q2
"""

import sys, os, json, time, requests
from datetime import date, datetime
import tableauserverclient as TSC

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from connections import tableau_pulse_headers, tableau_headers

# ── Validation site config ────────────────────────────────────────────────────
# Credentials loaded from config.json under the "pulse_validation" profile.
# To set up: add a profile with server_url, site_name, pat_name, pat_secret
# pointing to a site on a canary pod (10ax or us-west-c).

def _load_validation_config():
    """Load validation site credentials from config.json."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if not os.path.exists(config_path):
        return None
    with open(config_path) as f:
        full = json.load(f)
    profile = full.get("profiles", {}).get("pulse_validation")
    if not profile or not profile.get("tableau", {}).get("pat_secret"):
        return None
    tc = profile["tableau"]
    return {
        "server_url": tc.get("server_url", ""),
        "site_name": tc.get("site_name", ""),
        "pat_name": tc.get("pat_name", ""),
        "pat_secret": tc.get("pat_secret", ""),
    }

VALIDATION_SITE = _load_validation_config()

VALIDATION_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pulse_validation_state.json")

# ── Test payloads ─────────────────────────────────────────────────────────────

def _base_payload(ds_id, field, aggregation, fmt, sentiment, is_running_total, name_suffix):
    return {
        "name": f"__validator_{name_suffix}_{datetime.now().strftime('%H%M%S')}__",
        "description": "Automated validation test — will be deleted immediately",
        "specification": {
            "datasource": {"id": ds_id},
            "basic_specification": {
                "measure": {"field": field, "aggregation": aggregation},
                "time_dimension": {"field": "Date"},
                "filters": [],
            },
            "is_running_total": is_running_total,
        },
        "extension_options": {
            "allowed_dimensions": ["Region"],
            "allowed_granularities": ["GRANULARITY_BY_MONTH", "GRANULARITY_BY_QUARTER", "GRANULARITY_BY_YEAR"],
            "offset_from_today": 0,
            "correlation_candidate_definition_ids": [],
            "use_dynamic_offset": False,
        },
        "representation_options": {
            "type": fmt,
            "sentiment_type": sentiment,
        },
        "insights_options": {"show_insights": True, "settings": []},
        "comparisons": {"comparisons": [
            {"compare_config": {"comparison": "TIME_COMPARISON_PREVIOUS_PERIOD", "comparison_period_override": []}, "index": "0"},
        ]},
    }


def get_test_cases(ds_id):
    """All payload variations used by /build-demo."""
    return [
        {
            "name": "AVERAGE + NUMBER (rate metric)",
            "payload": _base_payload(ds_id, "Score", "AGGREGATION_AVERAGE", "NUMBER_FORMAT_TYPE_NUMBER", "SENTIMENT_TYPE_UP_IS_GOOD", False, "avg_num"),
        },
        {
            "name": "SUM + NUMBER (flow metric)",
            "payload": _base_payload(ds_id, "Volume", "AGGREGATION_SUM", "NUMBER_FORMAT_TYPE_NUMBER", "SENTIMENT_TYPE_UP_IS_GOOD", True, "sum_num"),
        },
        {
            "name": "SUM + CURRENCY (revenue metric)",
            "payload": _base_payload(ds_id, "Revenue", "AGGREGATION_SUM", "NUMBER_FORMAT_TYPE_CURRENCY", "SENTIMENT_TYPE_UP_IS_GOOD", True, "sum_cur"),
        },
        {
            "name": "AVERAGE + CURRENCY (per-unit metric)",
            "payload": _base_payload(ds_id, "Revenue", "AGGREGATION_AVERAGE", "NUMBER_FORMAT_TYPE_CURRENCY", "SENTIMENT_TYPE_UP_IS_GOOD", False, "avg_cur"),
        },
        {
            "name": "DOWN_IS_GOOD sentiment",
            "payload": _base_payload(ds_id, "Cost", "AGGREGATION_AVERAGE", "NUMBER_FORMAT_TYPE_NUMBER", "SENTIMENT_TYPE_DOWN_IS_GOOD", False, "down_good"),
        },
        {
            "name": "COUNT aggregation",
            "payload": _base_payload(ds_id, "Record ID", "AGGREGATION_COUNT", "NUMBER_FORMAT_TYPE_NUMBER", "SENTIMENT_TYPE_UP_IS_GOOD", True, "count"),
        },
    ]


# ── Validation runner ─────────────────────────────────────────────────────────

def ensure_validation_datasource(server, auth_token, site_id, server_url):
    """Ensure a test datasource exists on the validation site. Create if needed."""
    h = {"x-tableau-auth": auth_token, "Accept": "application/json"}

    # Check for existing validation datasource
    all_ds = list(TSC.Pager(server.datasources))
    for ds in all_ds:
        if ds.name == "Pulse Validator":
            # Verify it's in the Pulse catalog
            r = requests.get(f"{server_url}/api/-/pulse/datasources/{ds.id}", headers=h)
            if r.status_code == 200:
                return ds.id
            # Not indexed — wait and retry
            time.sleep(10)
            r = requests.get(f"{server_url}/api/-/pulse/datasources/{ds.id}", headers=h)
            if r.status_code == 200:
                return ds.id

    # Create a minimal .hyper with test fields
    from tableauhyperapi import HyperProcess, Telemetry, Connection, CreateMode, TableDefinition, TableName, SqlType, Inserter

    hyper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pulse_validator.hyper")
    table_def = TableDefinition(
        table_name=TableName("Extract", "Extract"),
        columns=[
            TableDefinition.Column("Record ID", SqlType.text()),
            TableDefinition.Column("Date", SqlType.date()),
            TableDefinition.Column("Region", SqlType.text()),
            TableDefinition.Column("Score", SqlType.double()),
            TableDefinition.Column("Volume", SqlType.double()),
            TableDefinition.Column("Revenue", SqlType.double()),
            TableDefinition.Column("Cost", SqlType.double()),
        ]
    )

    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, hyper_path, CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema("Extract")
            conn.catalog.create_table(table_def)
            with Inserter(conn, table_def) as inserter:
                from dateutil.relativedelta import relativedelta
                today = date.today()
                for m in range(24):
                    d = today - relativedelta(months=m)
                    for region in ["North", "South", "East", "West"]:
                        inserter.add_row([
                            f"R{m:02d}_{region}", d, region,
                            0.85 - m * 0.005, float(100 + m * 2), float(50000 + m * 1000), float(20000 - m * 200),
                        ])
                inserter.execute()

    # Publish
    proj_name = "Pulse Validator"
    all_projects, _ = server.projects.get()
    proj = next((p for p in all_projects if p.name == proj_name), None)
    if not proj:
        proj = server.projects.create(TSC.ProjectItem(name=proj_name))

    ds_item = TSC.DatasourceItem(proj.id, name="Pulse Validator")
    ds_item = server.datasources.publish(ds_item, hyper_path, TSC.Server.PublishMode.Overwrite)

    # Wait for indexing
    time.sleep(12)
    os.remove(hyper_path)
    return ds_item.id


def run_validation(quiet=False):
    """Run all validation tests. Returns (passed, failed, results)."""
    global VALIDATION_SITE
    if VALIDATION_SITE is None:
        VALIDATION_SITE = _load_validation_config()
    if not VALIDATION_SITE:
        if not quiet:
            print("  ⚠ Pulse validation not configured — add a 'pulse_validation' profile to config.json")
        return 0, 0, []
    server_url = VALIDATION_SITE["server_url"].rstrip("/")

    # Sign in
    server = TSC.Server(server_url, use_server_version=True)
    auth = TSC.PersonalAccessTokenAuth(
        VALIDATION_SITE["pat_name"],
        VALIDATION_SITE["pat_secret"],
        site_id=VALIDATION_SITE["site_name"],
    )
    server.auth.sign_in(auth)
    auth_token = server.auth_token
    site_id = server.site_id

    # Get build info
    r = requests.get(f"{server_url}/api/3.29/serverinfo", headers={"Accept": "application/json"})
    build_info = r.json()["serverInfo"]["productVersion"]
    build = build_info["build"]
    version = build_info["value"]

    if not quiet:
        print(f"  Pulse Validator — {server_url}")
        print(f"  Build: {version} ({build})")

    # Ensure datasource exists
    ds_id = ensure_validation_datasource(server, auth_token, site_id, server_url)
    if not quiet:
        print(f"  Datasource: {ds_id}")

    h_pulse = tableau_pulse_headers(auth_token)
    h_rest = {"x-tableau-auth": auth_token, "Accept": "application/json"}
    defs_url = f"{server_url}/api/-/pulse/definitions"

    # Run tests
    test_cases = get_test_cases(ds_id)
    results = []
    passed = 0
    failed = 0

    if not quiet:
        print(f"\n  Running {len(test_cases)} payload tests + 2 operation tests...")

    for tc in test_cases:
        r = requests.post(defs_url, headers=h_pulse, json=tc["payload"])
        if r.status_code in (200, 201):
            passed += 1
            def_id = r.json().get("definition", {}).get("metadata", {}).get("id")
            if def_id:
                requests.delete(f"{defs_url}/{def_id}", headers=h_rest)
            results.append({"name": tc["name"], "status": "PASS", "code": r.status_code})
            if not quiet:
                print(f"    ✓ {tc['name']}")
        else:
            failed += 1
            results.append({"name": tc["name"], "status": "FAIL", "code": r.status_code, "error": r.text[:200]})
            print(f"    ✗ {tc['name']}: {r.status_code} | {r.text[:100]}")

    # Test PATCH use_dynamic_offset on an existing def
    # Create a metric, then PATCH it
    test_payload = _base_payload(ds_id, "Score", "AGGREGATION_AVERAGE", "NUMBER_FORMAT_TYPE_NUMBER", "SENTIMENT_TYPE_UP_IS_GOOD", False, "patch_test")
    r = requests.post(defs_url, headers=h_pulse, json=test_payload)
    if r.status_code in (200, 201):
        def_id = r.json()["definition"]["metadata"]["id"]
        patch_h = {
            "x-tableau-auth": auth_token,
            "Content-Type": "application/vnd.tableau.metricqueryservice.v1.UpdateDefinitionRequest+json",
            "Accept": "application/json",
        }
        r_patch = requests.patch(f"{defs_url}/{def_id}", headers=patch_h, json={
            "extension_options": {"use_dynamic_offset": True}
        })
        if r_patch.status_code in (200, 204):
            passed += 1
            results.append({"name": "PATCH use_dynamic_offset", "status": "PASS", "code": r_patch.status_code})
            if not quiet:
                print(f"    ✓ PATCH use_dynamic_offset")
        else:
            failed += 1
            results.append({"name": "PATCH use_dynamic_offset", "status": "FAIL", "code": r_patch.status_code, "error": r_patch.text[:200]})
            print(f"    ✗ PATCH use_dynamic_offset: {r_patch.status_code}")

        # Test subscription format
        r_metrics = requests.get(f"{defs_url}/{def_id}/metrics", headers=h_rest)
        if r_metrics.status_code == 200:
            metrics = r_metrics.json().get("metrics", [])
            if metrics:
                metric_id = metrics[0]["id"]
                # Create a test group
                grp_h = {"x-tableau-auth": auth_token, "Content-Type": "application/xml", "Accept": "application/xml"}
                grp_xml = '<tsRequest><group name="__validator_group__"><domain name="local" /></group></tsRequest>'
                r_grp = requests.post(f"{server_url}/api/{server.version}/sites/{site_id}/groups", headers=grp_h, data=grp_xml)
                if r_grp.status_code in (200, 201):
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(r_grp.text)
                    grp = root.find(".//{http://tableau.com/api}group")
                    if grp is not None:
                        group_id = grp.get("id")
                        sub_h = {"x-tableau-auth": auth_token, "Content-Type": "application/json", "Accept": "application/json"}
                        r_sub = requests.post(f"{server_url}/api/-/pulse/subscriptions:batchCreate", headers=sub_h, json={
                            "metric_id": metric_id,
                            "followers": [{"group_id": group_id}],
                        })
                        if r_sub.status_code in (200, 201):
                            passed += 1
                            results.append({"name": "Subscription (flat format)", "status": "PASS", "code": r_sub.status_code})
                            if not quiet:
                                print(f"    ✓ Subscription (flat format)")
                        else:
                            failed += 1
                            results.append({"name": "Subscription (flat format)", "status": "FAIL", "code": r_sub.status_code, "error": r_sub.text[:200]})
                            print(f"    ✗ Subscription (flat format): {r_sub.status_code}")
                        # Clean up group
                        requests.delete(f"{server_url}/api/{server.version}/sites/{site_id}/groups/{group_id}", headers={"x-tableau-auth": auth_token})

        # Clean up test metric
        requests.delete(f"{defs_url}/{def_id}", headers=h_rest)

    server.auth.sign_out()

    # Save state
    state = {
        "last_run": datetime.now().isoformat(),
        "build": build,
        "version": version,
        "passed": passed,
        "failed": failed,
        "results": results,
    }
    with open(VALIDATION_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    if not quiet:
        print(f"\n  Results: {passed} passed, {failed} failed")
        if failed == 0:
            print(f"  ✓ All Pulse API payload formats validated on {version} ({build})")
        else:
            print(f"  ⚠ FAILURES DETECTED — Pulse API may have breaking changes")

    return passed, failed, results


def should_run_validation():
    """Check if validation should run (weekly or build changed)."""
    site = _load_validation_config()
    if not site:
        return False
    if not os.path.exists(VALIDATION_STATE_FILE):
        return True

    with open(VALIDATION_STATE_FILE) as f:
        state = json.load(f)

    last_run = datetime.fromisoformat(state.get("last_run", "2000-01-01"))
    days_since = (datetime.now() - last_run).days
    if days_since >= 7:
        return True

    # Check if build changed
    try:
        r = requests.get(f"{site['server_url'].rstrip('/')}/api/3.29/serverinfo",
                        headers={"Accept": "application/json"}, timeout=5)
        if r.status_code == 200:
            current_build = r.json()["serverInfo"]["productVersion"]["build"]
            if current_build != state.get("build"):
                return True
    except Exception:
        pass

    return False


def get_last_validation_status():
    """Return last validation state for display in /build-demo."""
    if not os.path.exists(VALIDATION_STATE_FILE):
        return None
    with open(VALIDATION_STATE_FILE) as f:
        return json.load(f)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    quiet = "--quiet" in sys.argv
    if not quiet:
        print("\n╔══════════════════════════════════════════════════════════╗")
        print("  Pulse API Validator — Canary Pod (10ax)")
        print("╚══════════════════════════════════════════════════════════╝\n")

    passed, failed, results = run_validation(quiet=quiet)
    sys.exit(1 if failed > 0 else 0)
