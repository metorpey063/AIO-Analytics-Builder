"""
AIO Analytics Builder — Web UI
Local web server providing a visual, guided experience for building demo assets.
"""

import json
import os
import sys
import queue
import threading
import time
import webbrowser
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response

# Add parent directory so we can import AIO modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

app = Flask(__name__)
app.secret_key = os.urandom(24)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


@app.context_processor
def inject_connection_status():
    """Make has_tableau / has_salesforce / version available in every template."""
    config = _load_config()
    version = ""
    version_path = PROJECT_ROOT / "VERSION"
    if version_path.exists():
        version = version_path.read_text().strip()
    commit_count = ""
    try:
        import subprocess
        git_env = {**os.environ, "PATH": os.environ.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin:/usr/bin"}
        commit_count = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(PROJECT_ROOT), stderr=subprocess.DEVNULL, env=git_env,
        ).decode().strip()
    except Exception:
        commit_count = "—"
    return {
        "has_tableau": bool(config.get("tableau", {}).get("pat_secret")),
        "has_salesforce": bool(config.get("salesforce", {}).get("refresh_token")),
        "app_version": version,
        "commit_count": commit_count,
    }

# ---------------------------------------------------------------------------
# SSE progress streaming
# ---------------------------------------------------------------------------
progress_queues: dict[str, queue.Queue] = {}


JOB_LOG = {}   # build id -> recent progress lines, kept for the assistant (the SSE queue is consumed as it streams)


def send_progress(build_id: str, stage: str, message: str, pct: int = -1):
    """Push a progress event to the SSE stream for a given build."""
    q = progress_queues.get(build_id)
    if q:
        q.put({"stage": stage, "message": message, "pct": pct})
    if stage != "heartbeat":
        log = JOB_LOG.setdefault(build_id, {"started": time.strftime("%H:%M:%S"), "lines": [], "state": "running"})
        log["lines"] = (log["lines"] + [f"[{stage}] {message}"])[-300:]
        if stage in ("done", "error"):
            log["state"] = stage
        while len(JOB_LOG) > 20:
            JOB_LOG.pop(next(iter(JOB_LOG)))


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    config = _load_config()
    has_tableau = bool(config.get("tableau", {}).get("pat_secret"))
    has_salesforce = bool(config.get("salesforce", {}).get("refresh_token"))
    changelog = _parse_changelog(limit=5)
    return render_template("index.html", has_tableau=has_tableau, has_salesforce=has_salesforce,
                           changelog=changelog)


@app.route("/setup")
def setup():
    from connections import load_full_config, set_active_profile
    edit_key = request.args.get("profile")
    is_editing = bool(edit_key)
    full = load_full_config()

    if edit_key and edit_key in full.get("profiles", {}):
        set_active_profile(full, edit_key)
        config = _load_config()
        active_conn = full["profiles"][edit_key]
        active_label = active_conn.get("label", "")
        tc = active_conn.get("tableau", {})
        sf = active_conn.get("salesforce", {})
    else:
        config = {"tableau": {}, "salesforce": {}}
        active_label = ""
        edit_key = ""
        tc = {}
        sf = {}

    return render_template("setup.html", config=config,
                           edit_profile_key=edit_key or "",
                           edit_profile_label=active_label,
                           is_editing=is_editing,
                           edit_has_tableau=bool(tc.get("pat_secret") and tc.get("site_name")),
                           edit_has_salesforce=bool(sf.get("refresh_token") and sf.get("client_id")))


@app.route("/build")
def build():
    config = _load_config()
    has_tableau = bool(config.get("tableau", {}).get("pat_secret"))
    has_salesforce = bool(config.get("salesforce", {}).get("refresh_token"))
    return render_template("build.html", has_tableau=has_tableau, has_salesforce=has_salesforce)


@app.route("/close-loop/<slug>")
def close_loop_page(slug):
    """Standalone Phase 6 page for a completed demo build."""
    import json as _json
    cp_path = PROJECT_ROOT / "demos" / slug / f"{slug}_checkpoint.json"
    if not cp_path.exists():
        return f"Demo '{slug}' not found", 404
    cp = _json.loads(cp_path.read_text())
    story = cp.get("story", {})
    return render_template("close_loop.html",
                           slug=slug,
                           company=story.get("company", slug),
                           headline=story.get("headline", ""),
                           primary_metric=story.get("primary_metric", ""),
                           dimensions=story.get("dimensions", []),
                           entity_field=story.get("entity_field", ""))


@app.route("/connections")
def connections():
    from connections import load_full_config
    full = load_full_config()
    active_sf = full.get("active_salesforce")
    active_tc = full.get("active_tableau_cloud")

    tableau_conns = []
    salesforce_conns = []
    for key, p in full.get("profiles", {}).items():
        tc = p.get("tableau", {})
        sf = p.get("salesforce", {})
        if tc.get("pat_secret") and tc.get("site_name"):
            tableau_conns.append({
                "key": key,
                "label": p.get("label", key),
                "active": key == active_tc,
                "server": tc.get("server_url", ""),
                "site": tc.get("site_name", ""),
                "has_pat": bool(tc.get("pat_secret")),
            })
        if sf.get("refresh_token") and (sf.get("client_id") or sf.get("data_cloud_domain")):
            salesforce_conns.append({
                "key": key,
                "label": p.get("label", key),
                "active": key == active_sf,
                "login_url": sf.get("sf_login_url", ""),
                "dc_domain": sf.get("data_cloud_domain", ""),
                "connector": sf.get("ingestion_connector_name", ""),
                "has_eca": bool(sf.get("client_id")),
                "has_oauth": bool(sf.get("refresh_token")),
                "has_connector": bool(sf.get("ingestion_connector_name") or sf.get("connector_sf_id")),
                "has_dc_domain": bool(sf.get("data_cloud_domain")),
                "has_mcp": bool(sf.get("mcp_client_id")),
            })

    return render_template("connections.html",
                           tableau_conns=tableau_conns,
                           salesforce_conns=salesforce_conns,
                           active_sf=active_sf,
                           active_tc=active_tc)


@app.route("/demos")
def demos():
    demos_dir = PROJECT_ROOT / "demos"
    demo_list = []
    if demos_dir.exists():
        for d in sorted(demos_dir.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                checkpoint = d / f"{d.name}_checkpoint.json"
                info = {"slug": d.name, "path": str(d)}
                if checkpoint.exists():
                    try:
                        cp = json.loads(checkpoint.read_text())
                        info["company"] = cp.get("company", d.name)
                        info["build_date"] = cp.get("build_date", "")
                        # Show all output types that were built
                        types = []
                        if cp.get("pulse_done"): types.append("pulse")
                        if cp.get("sdm_done") or cp.get("viz_done"): types.append("next")
                        if cp.get("crma_dataset_id") or cp.get("crma_dashboard_id"): types.append("crma")
                        info["build_type"] = ", ".join(types) if types else cp.get("build_type", "unknown")
                        info["build_types"] = types
                    except json.JSONDecodeError:
                        info["company"] = d.name
                else:
                    info["company"] = d.name

                # Ensure build_date always includes time
                import datetime
                bd = info.get("build_date", "")
                if not bd:
                    mtime = d.stat().st_mtime
                    info["build_date"] = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                elif len(bd) == 10:
                    # Date-only from older checkpoint — append time from folder mtime
                    mtime = d.stat().st_mtime
                    info["build_date"] = bd + " " + datetime.datetime.fromtimestamp(mtime).strftime("%H:%M")

                walkthroughs = sorted(list(d.glob("*walkthrough*.html")) + list(d.glob("*walkthrough*.docx")))
                info["walkthroughs"] = [{"name": w.name, "slug": d.name} for w in walkthroughs]

                demo_list.append(info)

    # Sort by build date (most recent first), then by name
    demo_list.sort(key=lambda x: x.get("build_date", ""), reverse=True)
    return render_template("demos.html", demos=demo_list)


@app.route("/api/demos/<slug>/concierge", methods=["POST"])
def retry_concierge(slug):
    """Re-ask a Tableau Next demo's Concierge questions and update its walkthrough."""
    demo_dir = PROJECT_ROOT / "demos" / slug
    if not (demo_dir / f"{slug}_checkpoint.json").exists():
        return jsonify({"ok": False, "error": "Demo not found"})
    from builder import recapture_concierge
    try:
        res = recapture_concierge(slug, str(demo_dir))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]})
    return jsonify({"ok": res["captured"] > 0, **res})


@app.route("/api/demos/<slug>/delete", methods=["POST"])
def delete_demo(slug):
    """Delete a demo folder and optionally clean up remote assets."""
    import shutil
    demos_dir = PROJECT_ROOT / "demos" / slug
    if not demos_dir.exists():
        return jsonify({"ok": False, "error": "Demo not found"})

    data = request.get_json(silent=True) or {}
    delete_remote = data.get("delete_remote", False)
    remote_results = []

    if delete_remote:
        cp_path = demos_dir / f"{slug}_checkpoint.json"
        if cp_path.exists():
            try:
                cp = json.loads(cp_path.read_text())
                remote_results = _delete_remote_assets(cp)
            except Exception as e:
                remote_results.append(f"Error reading checkpoint: {e}")

    try:
        shutil.rmtree(str(demos_dir))
        return jsonify({"ok": True, "remote_results": remote_results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "remote_results": remote_results})


def _delete_remote_assets(cp):
    """Delete remote assets from Tableau Cloud or Tableau Next based on checkpoint."""
    import requests as req
    results = []
    build_type = cp.get("build_type", "")

    if build_type == "pulse":
        try:
            from connections import get_tableau_token, tableau_headers, tableau_pulse_headers
            server, auth_token, site_id = get_tableau_token()
            base = server.server_address.rstrip("/")
            h_pulse = {"x-tableau-auth": auth_token, "Accept": "application/json", "Content-Type": "application/json"}

            for def_id in cp.get("pulse_def_ids", []):
                r = req.delete(f"{base}/api/-/pulse/definitions/{def_id}", headers=h_pulse)
                results.append(f"Pulse definition {def_id}: {'deleted' if r.ok else r.status_code}")

            if cp.get("pulse_project_id"):
                import tableauserverclient as TSC
                try:
                    server.projects.delete(cp["pulse_project_id"])
                    results.append(f"Project {cp.get('pulse_project_name', '')}: deleted")
                except Exception as e:
                    results.append(f"Project delete failed: {e}")

            server.auth.sign_out()
        except Exception as e:
            results.append(f"Pulse cleanup error: {e}")

    elif build_type == "next":
        try:
            from connections import get_sf_token, sf_headers
            sf_token, sf_instance = get_sf_token()
            h = sf_headers(sf_token)

            for dash in cp.get("all_dash_apis", []):
                r = req.delete(f"{sf_instance}/services/data/v66.0/tableau/dashboards/{dash}?minorVersion=12", headers=h)
                results.append(f"Dashboard {dash}: {'deleted' if r.ok else r.status_code}")

            for viz in cp.get("all_viz_apis", []):
                r = req.delete(f"{sf_instance}/services/data/v66.0/tableau/visualizations/{viz}?minorVersion=12", headers=h)
                results.append(f"Viz {viz}: {'deleted' if r.ok else r.status_code}")

            for sdm in cp.get("all_sdm_apis", []):
                r = req.delete(f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{sdm}", headers=h)
                results.append(f"SDM {sdm}: {'deleted' if r.ok else r.status_code}")

            for ws in cp.get("all_ws_apis", []):
                r = req.delete(f"{sf_instance}/services/data/v65.0/tableau/workspaces/{ws}", headers=h)
                results.append(f"Workspace {ws}: {'deleted' if r.ok else r.status_code}")
        except Exception as e:
            results.append(f"Next cleanup error: {e}")

    return results


@app.route("/api/demos/<slug>/open")
def open_demo_folder(slug):
    """Open a demo folder in Finder/Explorer."""
    import subprocess, platform as plat
    demos_dir = PROJECT_ROOT / "demos" / slug
    if not demos_dir.exists():
        return jsonify({"ok": False, "error": "Demo folder not found"})
    try:
        if plat.system() == "Darwin":
            subprocess.Popen(["open", str(demos_dir)])
        elif plat.system() == "Windows":
            subprocess.Popen(["explorer", str(demos_dir)])
        else:
            subprocess.Popen(["xdg-open", str(demos_dir)])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/stats")
def get_stats():
    """Aggregate stats across all demos for the home page stats strip."""
    demos_dir = PROJECT_ROOT / "demos"
    total_demos = 0
    total_metrics = 0
    total_dashboards = 0
    total_vizzes = 0
    total_rows = 0

    if demos_dir.exists():
        for d in demos_dir.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            cp_files = list(d.glob("*_checkpoint.json"))
            if cp_files:
                try:
                    cp = json.loads(cp_files[0].read_text())
                    total_demos += 1
                    total_metrics += len(cp.get("metric_apis", []) or cp.get("pulse_metric_ids", []))
                    total_dashboards += 1 if cp.get("dash_api") or cp.get("dash_done") else 0
                    total_vizzes += len([v for v in (cp.get("viz_apis", []) or cp.get("all_viz_apis", [])) if v])
                except Exception:
                    pass
            csv_files = list(d.glob("*.csv"))
            for cf in csv_files[:1]:
                try:
                    with open(str(cf)) as f:
                        total_rows += sum(1 for _ in f) - 1
                except Exception:
                    pass

    return jsonify({
        "demos": total_demos,
        "metrics": total_metrics,
        "dashboards": total_dashboards,
        "vizzes": total_vizzes,
        "rows": total_rows,
    })


@app.route("/api/demos/<slug>/build-log")
def view_build_log(slug):
    """Return the build log as plain text."""
    log_path = PROJECT_ROOT / "demos" / slug / f"{slug}_build.log"
    if not log_path.exists():
        return "No build log found for this demo.", 404
    return Response(log_path.read_text(), mimetype="text/plain")


@app.route("/api/demos/<slug>/walkthrough/<filename>")
def open_walkthrough(slug, filename):
    """Open a walkthrough file with the system default application."""
    import subprocess, platform as plat
    demos_dir = PROJECT_ROOT / "demos" / slug
    filepath = demos_dir / filename
    if not filepath.exists() or not (filename.endswith(".html") or filename.endswith(".docx")):
        return jsonify({"ok": False, "error": "File not found"}), 404
    try:
        if plat.system() == "Darwin":
            subprocess.Popen(["open", str(filepath)])
        elif plat.system() == "Windows":
            subprocess.Popen(["start", "", str(filepath)], shell=True)
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.route("/api/test-tableau", methods=["POST"])
def test_tableau():
    """Test Tableau Cloud connection and return live site details."""
    try:
        from connections import get_tableau_token, tableau_headers, load_config
        import requests as req
        profile_key = (request.get_json(silent=True) or {}).get("profile_key")
        config = load_config(profile_key)
        tc = config["tableau"]
        server, token, site_id = get_tableau_token(config)
        base = tc["server_url"].rstrip("/")
        h = tableau_headers(token)

        pulse_ok = False
        pulse_count = 0
        try:
            r = req.get(f"{base}/api/-/pulse/definitions?page_size=1", headers=h)
            pulse_ok = r.status_code == 200
            if pulse_ok:
                pulse_count = r.json().get("total_count", 0)
        except Exception:
            pass

        ds_count = 0
        try:
            all_ds, _ = server.datasources.get()
            ds_count = len(all_ds) if all_ds else 0
        except Exception:
            pass

        project_count = 0
        try:
            all_proj, _ = server.projects.get()
            project_count = len(all_proj) if all_proj else 0
        except Exception:
            pass

        wb_count = 0
        try:
            all_wb, _ = server.workbooks.get()
            wb_count = len(all_wb) if all_wb else 0
        except Exception:
            pass

        server.auth.sign_out()
        return jsonify({
            "ok": True,
            "site_id": site_id,
            "site_name": tc.get("site_name", ""),
            "server_url": tc.get("server_url", ""),
            "pulse_api": pulse_ok,
            "pulse_definitions": pulse_count,
            "datasources": ds_count,
            "workbooks": wb_count,
            "projects": project_count,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/test-salesforce", methods=["POST"])
def test_salesforce():
    """Test Salesforce + Data Cloud connections and return live org details."""
    try:
        from connections import get_sf_token, get_dc_token, sf_headers as sfh, load_config
        import requests as req
        profile_key = (request.get_json(silent=True) or {}).get("profile_key")
        config = load_config(profile_key)
        sf_token, sf_instance = get_sf_token(config)
        h = sfh(sf_token)

        identity = {}
        try:
            r = req.get(f"{sf_instance}/services/oauth2/userinfo",
                        headers={"Authorization": f"Bearer {sf_token}"})
            if r.ok:
                ui = r.json()
                identity["username"] = ui.get("preferred_username", "")
                identity["org_id"] = ui.get("organization_id", "")
                identity["display_name"] = ui.get("name", "")
        except Exception:
            pass

        dc_ok = False
        dc_domain = ""
        try:
            dc_token, dc_domain = get_dc_token(sf_token, sf_instance)
            dc_ok = True
        except Exception:
            pass

        workspaces = []
        try:
            r = req.get(f"{sf_instance}/services/data/v65.0/tableau/workspaces", headers=h)
            if r.ok:
                workspaces = [{"name": w.get("label", w.get("name", "")),
                               "api": w.get("name", "")}
                              for w in r.json().get("workspaces", [])]
        except Exception:
            pass

        sdm_count = 0
        try:
            r = req.get(f"{sf_instance}/services/data/v65.0/ssot/semantic/models", headers=h)
            if r.ok:
                sdm_count = len(r.json().get("items", []))
        except Exception:
            pass

        connector_name = config.get("salesforce", {}).get("ingestion_connector_name", "")
        connector_ok = False
        try:
            r = req.get(f"{sf_instance}/services/data/v62.0/ssot/connections",
                        headers=h, params={"connectorType": "IngestApi", "limit": 100})
            if r.ok:
                for c in r.json().get("connections", []):
                    if connector_name and connector_name in c.get("name", ""):
                        connector_ok = True
                        break
        except Exception:
            pass

        mcp_ok = False
        mcp_error = ""
        try:
            from mcp_client import MCPClient
            mcp = MCPClient(config)
            mcp_error = f"available={mcp.available}, client_id={bool(mcp.mcp_client_id)}, refresh={bool(mcp.sf.get('mcp_refresh_token'))}"
            if mcp.available:
                mcp.authenticate()
                mcp_ok = True
                mcp_error = ""
            else:
                mcp_error = f"No mcp_client_id in profile. Keys: {list(config.get('salesforce', {}).keys())[:8]}"
        except Exception as e:
            mcp_error = f"Auth failed: {str(e)[:200]}"

        return jsonify({
            "ok": True,
            "instance": sf_instance,
            "username": identity.get("username", ""),
            "display_name": identity.get("display_name", ""),
            "org_id": identity.get("org_id", ""),
            "data_cloud": dc_ok,
            "dc_domain": dc_domain,
            "workspaces": workspaces,
            "sdm_count": sdm_count,
            "connector_ok": connector_ok,
            "connector_name": connector_name,
            "mcp_ok": mcp_ok,
            "mcp_error": mcp_error,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def _schedule_restart(delay=1.5):
    """Re-exec the server after the response is sent. It runs without the reloader, so this is the
    only way to load new code. The page waits for /api/version to answer again."""
    def _restart():
        os.environ["AIO_RESTARTED"] = "1"   # don't open another browser tab
        os.closerange(3, 4096)   # werkzeug's listening socket is inheritable and would keep the port busy
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Timer(delay, _restart).start()


@app.route("/api/restart", methods=["POST"])
def restart_server():
    """Restart the server (sidebar restart button) so code changes on disk are loaded."""
    _schedule_restart()
    return jsonify({"ok": True, "message": "Restarting"})


@app.route("/api/test-mcp", methods=["POST"])
def test_mcp():
    """Check if Tableau Next MCP server is configured and reachable."""
    try:
        mcp_config = PROJECT_ROOT / ".mcp.json"
        if not mcp_config.exists():
            return jsonify({"ok": False, "configured": False,
                            "error": "No .mcp.json found — MCP not configured"})
        mcp = json.loads(mcp_config.read_text())
        servers = mcp.get("mcpServers", {})
        has_next_pilot = "tableau-next-pilot" in servers or "tableau-next-beta" in servers or "Tableau Next Beta" in servers
        has_knowledge = "tableau-knowledge" in servers
        return jsonify({
            "ok": True,
            "configured": True,
            "tableau_next_pilot": has_next_pilot,
            "tableau_knowledge": has_knowledge,
            "servers": list(servers.keys()),
        })
    except Exception as e:
        return jsonify({"ok": False, "configured": False, "error": str(e)})


@app.route("/api/switch-profile", methods=["POST"])
def switch_profile():
    """Switch the active connection. Supports per-type switching via conn_type."""
    try:
        from connections import load_full_config, set_active_profile, set_active_connection
        data = request.get_json(silent=True)
        key = data.get("key")
        conn_type = data.get("conn_type")
        if not key:
            return jsonify({"ok": False, "error": "No connection key provided"})
        full = load_full_config()
        if key not in full.get("profiles", {}):
            return jsonify({"ok": False, "error": f"Connection '{key}' not found"})
        if conn_type in ("salesforce", "tableau_cloud"):
            set_active_connection(full, conn_type, key)
        else:
            set_active_profile(full, key)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/version", methods=["GET"])
def version_check():
    """Compare local version against remote origin/main."""
    import subprocess
    local_version = ""
    version_path = PROJECT_ROOT / "VERSION"
    if version_path.exists():
        local_version = version_path.read_text().strip()

    remote_version = local_version
    behind = False
    try:
        subprocess.run(["git", "fetch", "origin", "main", "--quiet"],
                       cwd=str(PROJECT_ROOT), capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "show", "origin/main:VERSION"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            remote_version = result.stdout.strip()

        rev_list = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=5,
        )
        if rev_list.returncode == 0:
            behind = int(rev_list.stdout.strip()) > 0
    except Exception:
        pass

    return jsonify({
        "local": local_version,
        "remote": remote_version,
        "behind": behind,
        # only when GitHub has commits this copy doesn't: a copy that's ahead (unpushed work) has a
        # different VERSION too, and offering it GitHub's older version as an "update" would be wrong
        "update_available": behind,
    })


@app.route("/api/update", methods=["POST"])
def update():
    """Reset to origin/main (same strategy as /update CLI skill). Protects config.json and demos/.
    Installs the incoming version's new dependencies first (pip failure = no update), then restarts
    the server so the new code and packages are loaded."""
    import subprocess
    import tempfile
    import time
    run = lambda cmd: subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30)
    try:
        run(["git", "fetch", "origin", "main", "--quiet"])
        rev_before = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        rev_remote = run(["git", "rev-parse", "origin/main"]).stdout.strip()
        backup_note = ""
        if rev_before != rev_remote:
            if run(["git", "merge-base", "--is-ancestor", rev_remote, rev_before]).returncode == 0:
                # Only ahead: unpushed local commits and nothing new upstream. A reset would delete them.
                return jsonify({"ok": True, "updated": False,
                                "output": "Already up to date. This copy also has commits that aren't on GitHub yet."})
            if run(["git", "merge-base", "--is-ancestor", rev_before, rev_remote]).returncode != 0:
                # Diverged: keep the local commits on a branch before matching GitHub
                branch = "backup/pre-update-" + time.strftime("%Y%m%d-%H%M%S")
                if run(["git", "branch", branch, rev_before]).returncode == 0:
                    backup_note = f"\nYour local commits were saved to branch {branch}."
        deps_note = ""
        incoming = run(["git", "show", "origin/main:requirements.txt"])
        if incoming.returncode == 0 and rev_before != run(["git", "rev-parse", "origin/main"]).stdout.strip():
            import deps
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
                tf.write(incoming.stdout)
            try:
                res = deps.sync(path=tf.name, log=lambda m: None)
            finally:
                os.unlink(tf.name)
            if not res["ok"]:
                return jsonify({"ok": False, "updated": False,
                                "output": "Couldn't install the update's new dependencies, so the update wasn't "
                                          "applied: " + res["output"]})
            deps_note = res["output"] if res["installed"] else ""
        run(["git", "stash", "push", "-m", "pre-update-stash", "--", "config.json"])
        result = run(["git", "reset", "--hard", "origin/main"])
        run(["git", "stash", "pop"])
        rev_after = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        updated = rev_before != rev_after
        output = result.stdout.strip() or result.stderr.strip()
        if updated:
            log = run(["git", "log", "--oneline", f"{rev_before[:8]}..HEAD"])
            output += "\n" + log.stdout.strip() + ("\n" + deps_note if deps_note else "") + backup_note

            _schedule_restart()
        return jsonify({"ok": True, "updated": updated, "output": output})
    except Exception as e:
        return jsonify({"ok": False, "updated": False, "output": str(e)})


@app.route("/api/setup/create-profile", methods=["POST"])
def create_profile():
    """Create a new connection profile (or switch to existing) with the given label."""
    try:
        from connections import load_full_config, save_profile, set_active_profile, make_profile_key, get_profile
        data = request.get_json(silent=True) or {}
        label = data.get("label", "").strip()
        if not label:
            return jsonify({"ok": False, "error": "Profile name is required"})

        full = load_full_config()
        key = make_profile_key(label)

        if key in full.get("profiles", {}):
            set_active_profile(full, key)
            return jsonify({"ok": True, "key": key, "existing": True})

        import copy
        from connections import _EMPTY_PROFILE
        profile = copy.deepcopy(_EMPTY_PROFILE)
        profile["label"] = label
        save_profile(full, key, profile)
        set_active_profile(full, key)
        return jsonify({"ok": True, "key": key, "existing": False})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def _auto_ctx():
    """Profile key + CLI alias for the automatic org setup routes."""
    from connections import load_full_config
    data = request.get_json(silent=True) or {}
    full = load_full_config()
    key = data.get("profile_key") or full.get("active_salesforce")
    if not key or key not in full.get("profiles", {}):
        raise RuntimeError("No active connection. Create one in Step 1 first.")
    return data, full, key, "aio-" + key.replace("_", "-")


@app.route("/api/setup/auto/login", methods=["POST"])
def auto_setup_login():
    """Automatic setup 1/4: Salesforce CLI preflight + browser login (no app needed)."""
    try:
        import org_bootstrap as ob
        ok, msg = ob.preflight()
        if not ok:
            return jsonify({"ok": False, "error": msg, "no_cli": True})
        data, _, _, alias = _auto_ctx()
        return jsonify({"ok": True, **ob.cli_login(alias, bool(data.get("sandbox")))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/setup/auto/apps", methods=["POST"])
def auto_setup_apps():
    """Automatic setup 2/4: deploy or reuse AIO's External Client Apps."""
    try:
        import org_bootstrap as ob
        data, _, _, alias = _auto_ctx()
        include_mcp = bool(data.get("include_mcp", True))
        apps = ob.deploy_apps(alias, include_mcp=include_mcp, update_existing=bool(data.get("update_existing")))
        needs_update = any(v["status"] == "needs_update" for v in apps.values())
        servers = ob.ensure_mcp_servers(alias) if include_mcp and not needs_update else {}
        return jsonify({"ok": True, "apps": apps, "needs_update": needs_update, "mcp_servers": servers})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/setup/auto/wait", methods=["POST"])
def auto_setup_wait():
    """Automatic setup 3/4: block until the new apps are live on every login server."""
    try:
        import org_bootstrap as ob
        data, _, _, alias = _auto_ctx()
        secs = ob.wait_until_active(ob.org_info(alias)["instance_url"], data.get("keys", []))
        return jsonify({"ok": True, "seconds": secs})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/setup/auto/authorize", methods=["POST"])
def auto_setup_authorize():
    """Automatic setup 4/4: AIO browser login, Data Cloud check, Ingest connector, profile save."""
    try:
        import org_bootstrap as ob
        data, full, key, alias = _auto_ctx()
        saved = ob.authorize_and_save(key, ob.org_info(alias)["instance_url"], data["rest_key"],
                                      data.get("mcp_key", ""), full["profiles"][key].get("label"), alias)
        return jsonify({"ok": True, **saved})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/oauth/mcp", methods=["POST"])
def oauth_mcp():
    """Run OAuth flow specifically for the MCP ECA to get an MCP refresh token."""
    try:
        from connections import load_full_config, save_full_config
        data = request.get_json(silent=True) or {}
        full = load_full_config()
        key = data.get("profile_key") or full.get("active_salesforce")
        if not key or key not in full.get("profiles", {}):
            return jsonify({"ok": False, "error": "No active profile."})

        sf = full["profiles"][key].get("salesforce", {})
        mcp_client_id = sf.get("mcp_client_id", "")
        mcp_client_secret = sf.get("mcp_client_secret", "")
        sf_login_url = sf.get("sf_login_url", "https://login.salesforce.com")

        if not mcp_client_id:
            return jsonify({"ok": False, "error": "No MCP Consumer Key configured."})

        from oauth_flow import get_refresh_token
        tokens = get_refresh_token(mcp_client_id, mcp_client_secret, sf_login_url,
                                   scopes="mcp_api refresh_token")

        full["profiles"][key]["salesforce"]["mcp_refresh_token"] = tokens["refresh_token"]
        if tokens.get("code_verifier"):
            full["profiles"][key]["salesforce"]["mcp_code_verifier"] = tokens["code_verifier"]
        full["profiles"][key].pop("_token_cache", None)
        save_full_config(full)

        return jsonify({"ok": True, "instance_url": tokens.get("instance_url", "")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/oauth/start", methods=["POST"])
def oauth_start():
    """Run the Salesforce OAuth browser flow and save the refresh token."""
    try:
        from connections import load_full_config, save_full_config

        data = request.get_json(silent=True) or {}
        full = load_full_config()
        key = data.get("profile_key") or full.get("active_salesforce")
        if not key or key not in full.get("profiles", {}):
            return jsonify({"ok": False, "error": "No active profile. Run Setup first."})

        sf = full["profiles"][key].get("salesforce", {})
        client_id = sf.get("client_id", "")
        client_secret = sf.get("client_secret", "")
        sf_login_url = sf.get("sf_login_url", "https://login.salesforce.com")

        if not client_id:
            return jsonify({"ok": False,
                            "error": "No Client ID configured. Fill in the Client ID in Step 2 first."})

        from oauth_flow import get_refresh_token
        tokens = get_refresh_token(client_id, client_secret, sf_login_url)

        full["profiles"][key]["salesforce"]["refresh_token"] = tokens["refresh_token"]
        if tokens.get("code_verifier"):
            full["profiles"][key]["salesforce"]["code_verifier"] = tokens["code_verifier"]
        full["profiles"][key]["salesforce"].pop("pkce_refresh_mode", None)
        full["profiles"][key].pop("_token_cache", None)
        save_full_config(full)

        return jsonify({
            "ok": True,
            "instance_url": tokens.get("instance_url", ""),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/save-config", methods=["POST"])
def save_config():
    """Save config.json — updates the active profile within the full config structure."""
    try:
        from connections import load_full_config, save_full_config
        data = request.get_json(silent=True)
        full = load_full_config()

        # Anthropic API key is global (not per-profile) — save it even without a profile
        if "anthropic" in data:
            full.setdefault("anthropic", {}).update(data["anthropic"])

        key = full.get("active_salesforce")
        if key and key in full.get("profiles", {}):
            profile = full["profiles"][key]
            if "tableau" in data:
                profile.setdefault("tableau", {}).update(data["tableau"])
            if "salesforce" in data:
                profile.setdefault("salesforce", {}).update(data["salesforce"])
            full["profiles"][key] = profile
        elif "tableau" in data or "salesforce" in data:
            return jsonify({"ok": False, "error": "No active profile found. Create a connection in Setup first."})

        save_full_config(full)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/profiles/list", methods=["GET"])
def profiles_list():
    """Return connections with org details for the build destination picker."""
    from connections import load_full_config
    full = load_full_config()
    active_sf = full.get("active_salesforce")
    active_tc = full.get("active_tableau_cloud")
    result = []
    for key, p in full.get("profiles", {}).items():
        tc = p.get("tableau", {})
        sf = p.get("salesforce", {})
        entry = {
            "key": key,
            "label": p.get("label", key),
            "active": key == active_sf or key == active_tc,
            "active_salesforce": key == active_sf,
            "active_tableau_cloud": key == active_tc,
            "has_tableau": bool(tc.get("pat_secret") and tc.get("site_name")),
            "has_salesforce": bool(sf.get("refresh_token") and sf.get("client_id")),
            "tableau_site": tc.get("site_name", ""),
            "tableau_server": tc.get("server_url", ""),
            "sf_login_url": sf.get("sf_login_url", ""),
            "dc_domain": sf.get("data_cloud_domain", ""),
        }
        result.append(entry)
    return jsonify(result)


@app.route("/api/close-loop/search-record", methods=["POST"])
def close_loop_search_record():
    """Search for a CRM record by name or ID for golden record selection."""
    try:
        from connections import load_config, get_sf_token
        from close_loop import search_golden_record
        data = request.get_json(silent=True) or {}
        record_type = data.get("record_type", "Account")
        search = data.get("search", "")
        config = load_config(connection_type="salesforce")
        sf_token, sf_instance = get_sf_token(config)
        h = {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}
        records = search_golden_record(sf_instance, h, record_type, search)
        return jsonify({"ok": True, "records": records})
    except Exception as e:
        return jsonify({"ok": False, "records": [], "error": str(e)})


@app.route("/api/close-loop/deploy", methods=["POST"])
def close_loop_deploy():
    """Deploy close-the-loop Flows for a demo."""
    try:
        data = request.get_json(silent=True) or {}
        slug = data.get("slug", "")
        action = data.get("action", "task")
        trigger = data.get("trigger", "slack_button")
        notify = data.get("notify", "chatter")
        golden_record = data.get("golden_record")

        if not slug:
            return jsonify({"ok": False, "error": "No slug provided"})

        # Save golden record to checkpoint BEFORE running build so cmd_plan reads it
        import json as _json
        cp_path = PROJECT_ROOT / "demos" / slug / f"{slug}_checkpoint.json"
        if golden_record and cp_path.exists():
            cp = _json.loads(cp_path.read_text())
            cp["golden_record"] = golden_record
            cp_path.write_text(_json.dumps(cp, indent=2, default=str))

        import subprocess
        cmd = ["python3", str(PROJECT_ROOT / "close_loop.py"), "build",
               "--slug", slug, "--action", action, "--trigger", trigger, "--notify", notify]
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            flow_names = [line.strip() for line in result.stdout.split("\n")
                          if "AiO_" in line and ("Flow" in line or "deployed" in line.lower())]
            return jsonify({"ok": True, "flows": flow_names, "output": result.stdout[-500:]})
        else:
            return jsonify({"ok": False, "error": result.stderr[-500:] or result.stdout[-500:]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/demos/list", methods=["GET"])
def demos_list_api():
    """Return list of existing demos with metadata for the build page picker."""
    demos_dir = PROJECT_ROOT / "demos"
    result = []
    if demos_dir.exists():
        for d in sorted(demos_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            csv_files = sorted(d.glob("*.csv"))
            if not csv_files:
                continue
            info = {"slug": d.name, "company": d.name.replace("_", " ").title()}
            cp_file = d / f"{d.name}_checkpoint.json"
            if cp_file.exists():
                try:
                    cp = json.loads(cp_file.read_text())
                    info["company"] = cp.get("company", info["company"])
                    info["build_type"] = cp.get("build_type", "")
                except (json.JSONDecodeError, KeyError):
                    pass
            try:
                import pandas as _pd
                df = _pd.read_csv(str(csv_files[-1]), nrows=1)
                info["columns"] = list(df.columns)
            except Exception:
                info["columns"] = []
            result.append(info)
    return jsonify(result)


@app.route("/api/build/upload", methods=["POST"])
def build_upload():
    """Extract text from uploaded files (PDF, DOCX, PPTX, TXT, CSV, images). Optional form field
    max_chars (default 15000, up to 100000) — the Update Rev Intel page sends more for long BRDs."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"})
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename"})

    fname = f.filename.lower()
    try:
        limit = max(1000, min(int(request.form.get("max_chars", 15000)), 100000))
    except ValueError:
        limit = 15000
    try:
        if fname.endswith(".txt") or fname.endswith(".md"):
            text = f.read().decode("utf-8", errors="replace")
        elif fname.endswith(".csv"):
            text = f.read().decode("utf-8", errors="replace")
            lines = text.strip().split("\n")
            if len(lines) > 50:
                text = "\n".join(lines[:50]) + f"\n... ({len(lines)} total rows)"
        elif fname.endswith(".pdf"):
            try:
                import pypdf as _pdf   # cleaner text than PyPDF2 (keeps words on one line)
            except ImportError:
                import PyPDF2 as _pdf
            reader = _pdf.PdfReader(f)
            pages = []
            for page in reader.pages[:60]:
                pages.append(page.extract_text() or "")
            import re as _re
            text = _re.sub(r"[^\S\n]{2,}", " ", "\n".join(pages))   # collapse padded word gaps
        elif fname.endswith(".docx"):
            import docx
            doc = docx.Document(f)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            for t in doc.tables:   # BRD requirements usually live in tables
                rows = [" | ".join(c.text.strip() for c in r.cells) for r in t.rows]
                text += "\n\n" + "\n".join(r for r in rows if r.strip(" |"))
        elif fname.endswith(".pptx"):
            import io, zipfile, re as _re, html as _html
            z = zipfile.ZipFile(io.BytesIO(f.read()))
            slides = sorted((n for n in z.namelist() if _re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                            key=lambda n: int(_re.search(r"(\d+)\.xml$", n).group(1)))
            parts = []
            for i, n in enumerate(slides, 1):
                xml = z.read(n).decode("utf-8", errors="replace")
                paras = ["".join(_re.findall(r"<a:t[^>]*>([^<]*)</a:t>", para))
                         for para in _re.findall(r"<a:p[ >].*?</a:p>", xml, _re.S)]
                body = "\n".join(_html.unescape(x) for x in paras if x.strip())
                if body:
                    parts.append(f"[Slide {i}]\n{body}")
            text = "\n\n".join(parts)
        elif fname.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            import base64
            data = f.read()
            b64 = base64.b64encode(data).decode("ascii")
            ext = fname.rsplit(".", 1)[-1]
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
            return jsonify({"ok": True, "filename": f.filename, "type": "image",
                            "data_url": f"data:{mime};base64,{b64}"})
        else:
            text = f.read().decode("utf-8", errors="replace")

        if len(text) > limit:
            text = text[:limit] + "\n... (truncated)"

        return jsonify({"ok": True, "filename": f.filename, "type": "text", "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to read {f.filename}: {str(e)[:200]}"})


@app.route("/api/build/generate-story", methods=["POST"])
def build_generate_story():
    """Use Claude API to generate story + metrics from user inputs."""
    data = request.get_json(silent=True) or {}
    try:
        from builder import generate_story
        result = generate_story(
            company=data.get("company", ""),
            industry=data.get("industry", ""),
            use_case=data.get("use_case", ""),
            audience=data.get("audience", ""),
            notes=data.get("notes", ""),
            research_depth=data.get("research_depth", "quick"),
            dashboard_template=data.get("dashboard_template", "z_layout"),
        )
        if not result.get("metric_config"):
            return jsonify({"ok": False, "error": "AI returned a response but no metrics were generated. Try again with more detail about the use case."})
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)[:500]})


@app.route("/api/build/start", methods=["POST"])
def build_start():
    """Kick off a real demo build in a background thread."""
    import re as _re
    data = request.get_json(silent=True) or {}
    company = data.get("company", "Demo")
    build_id = _re.sub(r"[^a-z0-9]+", "_", company.lower()).strip("_")

    progress_queues[build_id] = queue.Queue()

    demo_name = data.get("demo_name", "") or company
    build_config = {
        "company": company,
        "demo_name": demo_name,
        "industry": data.get("industry", ""),
        "use_case": data.get("use_case", ""),
        "audience": data.get("audience", ""),
        "notes": data.get("notes", ""),
        "research_depth": data.get("research_depth", "quick"),
        "story_config": data.get("story_config", {}),
        "profile_key": data.get("profile_key"),
        "pulse_profile_key": data.get("pulse_profile_key"),
        "next_profile_key": data.get("next_profile_key"),
        "crma_profile_key": data.get("crma_profile_key"),
        "advanced": data.get("advanced", {}),
        "outputs": data.get("outputs", {"csv": True}),
        "dashboard_template": data.get("dashboard_template", "z_layout"),
        "dashboard_templates": data.get("dashboard_templates") or [],
        "brand": data.get("brand", {}),
    }

    def _run():
        from builder import run_build
        run_build(build_id, build_config, progress_queues[build_id])

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return jsonify({"ok": True, "build_id": build_id})


# ---------------------------------------------------------------------------
# Update Rev Intel (/update-rev-intel skill) — Q&A capture + revintel engine runner
# ---------------------------------------------------------------------------
REVINTEL_SAFE = {"inspect": [], "plan": [], "refresh-plan": ["refresh", "--plan"], "draft": ["draft"],
                 "roll-plan": ["roll"], "add-plan": ["add"]}
REVINTEL_BUILD_ALL = [["team", "people"], ["apply"], ["team", "reassign"], ["team", "quotas"], ["refresh"]]
REVINTEL_MOVE_ALL = [["roll", "--apply"], ["add", "--apply"], ["refresh"]]
REVINTEL_WRITES = {"team-people": ["team", "people"], "apply": ["apply"], "team-reassign": ["team", "reassign"],
                   "team-quotas": ["team", "quotas"], "refresh": ["refresh"], "roll": ["roll", "--apply"], "add": ["add", "--apply"]}


def _revintel_dir(slug):
    import re as _re
    if not _re.fullmatch(r"[a-z0-9_]{2,60}", slug or ""):
        raise ValueError("Demo folder name must be lowercase letters, numbers and underscores")
    return PROJECT_ROOT / "demos" / slug


@app.route("/deploy-sales-insights")
def deploy_sales_insights_page():
    """Deploy Sales Insights (/deploy-sales-insights skill): runs the salesinsights engine."""
    return render_template("sales_insights.html")


# Sales Insights jobs: polled (not SSE) so a page reload during a 10-15 minute deploy reconnects.
SI_JOBS = {}        # job id -> {profile, action, lines, state, rc}
SI_RUNNING = {}     # profile -> job id currently running
SI_ACTIONS = {"check": False, "status": False, "deploy": True, "reset": True}  # action -> writes to the org


def _si_checkpoint(key):
    p = PROJECT_ROOT / "demos" / "sales_insights" / key / "checkpoint.json"
    if not p.exists():
        return None
    try:
        cp = json.loads(p.read_text())
    except Exception:
        return None
    return {"instance": cp.get("instance"), "done": cp.get("done", []),
            "workspace": (cp.get("workspace") or {}).get("name"), "workspace_label": (cp.get("workspace") or {}).get("label"),
            "sdm": (cp.get("sdm") or {}).get("apiName"), "vizzes": len(cp.get("vizzes") or {}),
            "dashboards": len(cp.get("dashboards") or {}), "streams": len(cp.get("streams") or {}),
            "verify": cp.get("verify"),
            "business_preferences_manual": bool((cp.get("failures") or {}).get("business_preferences"))}


@app.route("/api/sales-insights/profiles")
def sales_insights_profiles():
    """Salesforce connections with their org URL and this page's deploy state per connection."""
    from connections import load_full_config
    full = load_full_config()
    out = []
    for key, p in full.get("profiles", {}).items():
        sf = p.get("salesforce", {})
        if not (sf.get("refresh_token") and sf.get("client_id")):
            continue
        instance = (p.get("_token_cache") or {}).get("instance_url") or sf.get("sf_login_url", "")
        out.append({"key": key, "label": p.get("label", key), "instance": instance,
                    "active": key == full.get("active_salesforce"),
                    "has_connector": bool(sf.get("connector_sf_id")),
                    "running": SI_RUNNING.get(key), "deploy": _si_checkpoint(key)})
    return jsonify({"ok": True, "profiles": out})


@app.route("/api/sales-insights/run", methods=["POST"])
def sales_insights_run():
    """Run one salesinsights command for a connection in the background."""
    import subprocess
    import uuid as _uuid
    from connections import load_full_config
    data = request.get_json() or {}
    action, key = data.get("action"), data.get("profile")
    if action not in SI_ACTIONS:
        return jsonify({"ok": False, "error": f"Unknown action {action!r}"}), 400
    if key not in load_full_config().get("profiles", {}):
        return jsonify({"ok": False, "error": "Pick a Salesforce connection first."}), 400
    if SI_ACTIONS[action] and not data.get("confirmed"):
        return jsonify({"ok": False, "error": "This writes to the org — confirm first."}), 400
    if SI_RUNNING.get(key):
        return jsonify({"ok": True, "job_id": SI_RUNNING[key], "already_running": True})
    job_id = f"si_{_uuid.uuid4().hex[:8]}"
    job = SI_JOBS[job_id] = {"profile": key, "action": action, "lines": [], "state": "running", "rc": None}
    SI_RUNNING[key] = job_id
    log_dir = PROJECT_ROOT / "demos" / "sales_insights" / key
    log_dir.mkdir(parents=True, exist_ok=True)

    def _run():
        cmd = ["python3", "-u", "-m", "salesinsights", action, "--profile", key]
        job["lines"].append("$ python3 " + " ".join(cmd[2:]))
        try:
            with open(log_dir / f"{action}.log", "a") as log:
                p = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
                for line in p.stdout:
                    job["lines"].append(line.rstrip()); log.write(line); log.flush()
                p.wait()
            job["rc"] = p.returncode
            job["state"] = "done" if p.returncode == 0 else "error"
        except Exception as e:
            job["lines"].append(f"error: {e}"); job["state"] = "error"
        finally:
            SI_RUNNING.pop(key, None)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/sales-insights/job/<job_id>")
def sales_insights_job(job_id):
    """New log lines since ?since=N, the job state, and the connection's checkpoint once finished."""
    job = SI_JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Unknown job (the server may have restarted). Check status."}), 404
    since = int(request.args.get("since", 0))
    return jsonify({"ok": True, "lines": job["lines"][since:], "next": len(job["lines"]), "state": job["state"],
                    "action": job["action"], "profile": job["profile"],
                    "deploy": _si_checkpoint(job["profile"]) if job["state"] != "running" else None})


@app.route("/transfer-assets")
def transfer_assets_page():
    """Transfer Assets (/transfer-assets skill): copies Tableau Next dashboards between orgs."""
    return render_template("transfer_assets.html")


# Transfer jobs: polled like Sales Insights, so a reload during a long transfer reconnects.
XFER_JOBS = {}      # job id -> {action, slug, lines, state, rc}
XFER_RUNNING = {}   # slug -> job id currently running


def _xfer_slug(target, workspace_label):
    import re as _re
    return "transfer_" + _re.sub(r"[^a-z0-9]+", "_", f"{target}_{workspace_label}".lower()).strip("_")[:60]


@app.route("/api/transfer/login")
def transfer_login():
    """Can this connection log in without a browser? Expired logins get a Reconnect button."""
    import transfer_assets as xfer
    return jsonify(xfer.login_status(request.args.get("profile", "")))


@app.route("/api/transfer/dashboards")
def transfer_dashboards():
    """Read-only: the Tableau Next dashboards in one org."""
    import transfer_assets as xfer
    key = request.args.get("profile", "")
    try:
        return jsonify({"ok": True, "dashboards": xfer.list_dashboards(xfer.Org(key, allow_browser=False))})
    except xfer.AuthError as e:
        return jsonify({"ok": False, "error": str(e), "reconnect": e.reconnect}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"Couldn't list dashboards: {e}"}), 400


@app.route("/api/transfer/run", methods=["POST"])
def transfer_run():
    """plan (read-only: packages the dashboards, checks the target's data), run (writes to the target)
    or remove (deletes only what this transfer created in the target)."""
    import subprocess
    import uuid as _uuid
    from connections import load_full_config
    data = request.get_json() or {}
    action, src, tgt = data.get("action"), data.get("source"), data.get("target")
    names = [n for n in data.get("dashboards", []) if n]
    label = (data.get("workspace_label") or "").strip()
    profiles = load_full_config().get("profiles", {})
    if action not in ("plan", "run", "remove"):
        return jsonify({"ok": False, "error": f"Unknown action {action!r}"}), 400
    if src not in profiles or tgt not in profiles:
        return jsonify({"ok": False, "error": "Pick a source and a target connection."}), 400
    if src == tgt:
        return jsonify({"ok": False, "error": "The source and target must be different orgs."}), 400
    if not names or not label:
        return jsonify({"ok": False, "error": "Pick at least one dashboard and name the workspace."}), 400
    if action in ("run", "remove") and not data.get("confirmed"):
        return jsonify({"ok": False, "error": "This writes to the target org — confirm first."}), 400
    slug = _xfer_slug(tgt, label)
    if XFER_RUNNING.get(slug):
        return jsonify({"ok": True, "job_id": XFER_RUNNING[slug], "slug": slug, "already_running": True})
    job_id = f"xf_{_uuid.uuid4().hex[:8]}"
    job = XFER_JOBS[job_id] = {"action": action, "slug": slug, "lines": [], "state": "running", "rc": None}
    XFER_RUNNING[slug] = job_id
    cmd = ["python3", "-u", "transfer_assets.py", action, "--source", src, "--target", tgt,
           "--dashboards", ",".join(names), "--slug", slug]
    if action == "plan":
        cmd.append("--fresh")
    elif action == "run":
        cmd += ["--workspace-label", label]

    def _run():
        job["lines"].append("$ python3 " + " ".join(cmd[2:]))
        try:
            log_path = PROJECT_ROOT / "demos" / slug / f"transfer_{action}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as log:
                # No hidden browser logins from a background job: an expired token prints AUTH_ERROR instead
                env = dict(os.environ, AIO_NO_BROWSER_REAUTH="1")
                p = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1, env=env)
                for line in p.stdout:
                    job["lines"].append(line.rstrip()); log.write(line); log.flush()
                p.wait()
            job["rc"] = p.returncode
            job["state"] = "done" if p.returncode == 0 else "error"
        except Exception as e:
            job["lines"].append(f"error: {e}"); job["state"] = "error"
        finally:
            XFER_RUNNING.pop(slug, None)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id, "slug": slug})


@app.route("/api/transfer/job/<job_id>")
def transfer_job(job_id):
    """New log lines since ?since=N, the job state, and the transfer checkpoint once finished."""
    job = XFER_JOBS.get(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Unknown job (the server may have restarted)."}), 404
    since = int(request.args.get("since", 0))
    cp = None
    if job["state"] != "running":
        p = PROJECT_ROOT / "demos" / job["slug"] / f"{job['slug']}_transfer_checkpoint.json"
        cp = json.loads(p.read_text()) if p.exists() else None
    return jsonify({"ok": True, "lines": job["lines"][since:], "next": len(job["lines"]), "state": job["state"],
                    "action": job["action"], "slug": job["slug"], "checkpoint": cp})


@app.route("/update-rev-intel")
def update_rev_intel_page():
    return render_template("rev_intel.html", slug=request.args.get("slug", ""))


@app.route("/api/rev-intel/orgs")
def rev_intel_orgs():
    """Connected sf CLI orgs (the revintel engine writes through the sf CLI)."""
    import subprocess
    try:
        out = subprocess.run(["sf", "org", "list", "--json"], capture_output=True, text=True, timeout=60).stdout
        res = json.loads(out).get("result", {})
        orgs = [{"alias": o.get("alias") or o.get("username"), "username": o.get("username"),
                 "instance": o.get("instanceUrl")}
                for o in res.get("nonScratchOrgs", []) + res.get("scratchOrgs", [])
                if o.get("connectedStatus") == "Connected"]
        return jsonify({"ok": True, "orgs": orgs})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/rev-intel/request/<slug>")
def rev_intel_load(slug):
    d = _revintel_dir(slug)
    req = d / "rev_intel_request.json"
    report = {}
    for name in ("inspect", "story_stats"):
        f = d / "out" / f"{name}.json"
        if f.exists():
            report[name] = json.loads(f.read_text())
    for name in ("draft_notes",):
        f = d / "out" / f"{name}.json"
        if f.exists():
            report[name] = json.loads(f.read_text())
    has_config = any((d / n).exists() for n in ("config.py", "config.json")) or bool(list(d.glob("*_config.py")))
    review = _rev_intel_review(d, report.get("inspect"))
    return jsonify({"ok": True, "request": json.loads(req.read_text()) if req.exists() else None,
                    "report": report, "has_config": has_config, "review": review})


def _rev_intel_review(d, inspect):
    """Human-readable summary of a drafted config.json for the review panel, plus EAM wizard answers."""
    cfg_path = d / "config.json"
    if not cfg_path.exists():
        return None
    cfg = json.loads(cfg_path.read_text())
    if "SEGMENTS" not in cfg:
        return None
    users = {u["id"]: u["name"] for u in ((inspect or {}).get("org_facts") or {}).get("users", [])}
    names = {k: users.get(v, v) for k, v in (cfg.get("USERS") or {}).items()}
    names.update({u[0]: f"{u[1]} {u[2]} (new)" for u in cfg.get("NEW_USERS", [])})
    def role(m):
        return "culprit" if m >= 1.5 else "counter-trend" if m < 0 else "flat" if m < 0.5 else "moderate"
    segments = [{"segment": k, "region": v.get("region"), "owner": names.get(v.get("owner"), v.get("owner")),
                 "story": role(v.get("mult", 1)), "mult": v.get("mult")} for k, v in cfg["SEGMENTS"].items()]
    leads = [{"lead": names.get(k, k), "reps": [names.get(r, r) for r in reps]} for k, reps in (cfg.get("LEADS") or {}).items()]
    products = [{"key": k, "label": v.get("label"), "list": v.get("list"), "exists": bool(v.get("pbe")),
                 "core": k == cfg.get("CORE_PRODUCT"), "dropped": k == cfg.get("CHURN_PRODUCT"),
                 "new": k in (cfg.get("LAUNCHED_PRODUCTS") or {})} for k, v in (cfg.get("PRODUCTS") or {}).items()]
    eam = None
    for a in (inspect or {}).get("apps", []):
        if a.get("eam_filters"):
            opp_rts = set(a["eam_filters"].get("OpptyRecordType") or [])
            renewal_rt = cfg.get("RENEWAL_RECORD_TYPE", "Renewal")
            eam = {"current": a["eam_filters"],
                   "needed": {"Opportunity record types": sorted(opp_rts | {renewal_rt}),
                              "Account record types": [cfg.get("POOL_RECORD_TYPE", "Business_Account")]},
                   "changes_needed": renewal_rt not in opp_rts or
                   (a["eam_filters"].get("AcctRecordType") or []) != [cfg.get("POOL_RECORD_TYPE", "Business_Account")]}
    return {"customer": cfg.get("CUSTOMER_LABEL"), "leader": names.get(cfg.get("SALES_LEADER"), cfg.get("SALES_LEADER")),
            "segments": segments, "leads": leads, "products": products, "pool_size": len(json.loads((d / "pool_seed.json").read_text()))
            if (d / "pool_seed.json").exists() else 0, "eam": eam, "status": cfg.get("_status")}


@app.route("/api/rev-intel/save", methods=["POST"])
def rev_intel_save():
    """Save the Q&A answers; create a minimal config.json (org only) so Inspect can run."""
    data = request.get_json() or {}
    try:
        d = _revintel_dir(data.get("slug"))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    d.mkdir(parents=True, exist_ok=True)
    (d / "rev_intel_request.json").write_text(json.dumps(data, indent=1))
    has_config = any((d / n).exists() for n in ("config.py", "config.json")) or bool(list(d.glob("*_config.py")))
    if not has_config and data.get("org_alias"):
        (d / "config.json").write_text(json.dumps({"ORG_ALIAS": data["org_alias"], "POOL_PREFIX": "AIO-POOL",
                                                   "_status": "draft — /update-rev-intel fills in the rest"}, indent=1))
    return jsonify({"ok": True, "path": str(d / "rev_intel_request.json")})


@app.route("/api/rev-intel/run", methods=["POST"])
def rev_intel_run():
    """Run one revintel command in the background; stream its output on /api/build/progress/<id>."""
    import subprocess
    import uuid as _uuid
    data = request.get_json() or {}
    action = data.get("action")
    if action in REVINTEL_WRITES and not data.get("confirmed"):
        return jsonify({"ok": False, "error": "This step writes to the org — confirm first."}), 400
    if action in ("build-all", "move-all") and not data.get("confirmed"):
        return jsonify({"ok": False, "error": "This writes to the org — confirm first."}), 400
    if action not in REVINTEL_SAFE and action not in REVINTEL_WRITES and action not in ("build-all", "move-all", "draft-feedback"):
        return jsonify({"ok": False, "error": f"Unknown action {action!r}"}), 400
    try:
        d = _revintel_dir(data.get("slug"))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if action == "build-all":
        steps = REVINTEL_BUILD_ALL
    elif action == "move-all":
        steps = REVINTEL_MOVE_ALL
    elif action == "draft-feedback":
        fb = (data.get("feedback") or "").strip()
        if not fb:
            return jsonify({"ok": False, "error": "Describe the changes you want."}), 400
        steps = [["draft", "--feedback", fb]]
    else:
        steps = [(REVINTEL_SAFE.get(action) or REVINTEL_WRITES.get(action)) or [action]]
    job_id = f"revintel_{_uuid.uuid4().hex[:8]}"
    progress_queues[job_id] = queue.Queue()

    def _run():
        for i, args in enumerate(steps, 1):
            shown = ["python3 -m revintel", f"demos/{d.name}"] + [a if len(a) < 60 else a[:57] + "…" for a in args]
            label = f"[{i}/{len(steps)}] " if len(steps) > 1 else ""
            send_progress(job_id, "start", label + "$ " + " ".join(shown))
            try:
                p = subprocess.Popen(["python3", "-u", "-m", "revintel", str(d)] + args, cwd=str(PROJECT_ROOT),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in p.stdout:
                    send_progress(job_id, "log", line.rstrip())
                p.wait()
            except Exception as e:
                send_progress(job_id, "error", str(e))
                return
            if p.returncode != 0:
                send_progress(job_id, "error", f"{' '.join(args[:2])} failed (exit {p.returncode}) — see the log above. "
                                               "Fix it and run again; finished steps are skipped.")
                return
        send_progress(job_id, "done", f"{action} finished", 100)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "build_id": job_id})


REVINTEL_RESEARCH = {}   # job id -> suggested answers, read once by the page


@app.route("/api/rev-intel/research", methods=["POST"])
def rev_intel_research():
    """Research the customer and suggest answers for the Q&A (read-only; no org or demo folder needed)."""
    import uuid as _uuid
    data = request.get_json() or {}
    if not (data.get("customer") or "").strip():
        return jsonify({"ok": False, "error": "Enter the customer name first."}), 400
    job_id = f"riresearch_{_uuid.uuid4().hex[:8]}"
    progress_queues[job_id] = queue.Queue()

    def _run():
        from revintel import research
        try:
            REVINTEL_RESEARCH[job_id] = research.run(data, lambda m: send_progress(job_id, "log", m))
        except (SystemExit, Exception) as e:
            send_progress(job_id, "error", f"Research failed: {e}")
            return
        send_progress(job_id, "done", "Research finished — suggested answers filled in", 100)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "build_id": job_id})


@app.route("/api/rev-intel/research/<job_id>")
def rev_intel_research_result(job_id):
    res = REVINTEL_RESEARCH.pop(job_id, None)
    return jsonify({"ok": res is not None, "result": res})


@app.route("/api/build/progress/<build_id>")
def build_progress(build_id):
    """SSE endpoint streaming build progress."""
    def stream():
        q = progress_queues.get(build_id)
        if not q:
            yield f"data: {json.dumps({'stage': 'error', 'message': 'Unknown build', 'pct': -1})}\n\n"
            return
        while True:
            try:
                msg = q.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("stage") == "done" or msg.get("stage") == "error":
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'stage': 'heartbeat', 'message': '', 'pct': -1})}\n\n"

    return Response(stream(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Chat bot (Claude API)
# ---------------------------------------------------------------------------

CHAT_MODEL = "claude-haiku-4-5-20251001"   # story generation (builder.py) and the credentials Test button


def _get_chat_config():
    """Resolve chat API credentials. Returns dict with mode + params, or None.
    Order and sources live in claude_credentials.py (Claude Code settings are read automatically)."""
    from claude_credentials import resolve
    return resolve()


def _assistant_jobs(job_id=None):
    """Recent jobs for the assistant: Build Demo / Rev Intel progress and Sales Insights runs."""
    jobs = {k: {"kind": "build" if k.startswith("build") else k.split("_")[0], **v} for k, v in JOB_LOG.items()}
    for k, j in SI_JOBS.items():
        jobs[k] = {"kind": f"sales insights {j['action']} ({j['profile']})", "state": j["state"], "lines": j["lines"],
                   "started": ""}
    if not jobs:
        return "No jobs have run since the Web UI server started."
    if job_id:
        j = jobs.get(job_id)
        if not j:
            return f"No job {job_id}. Known: {', '.join(jobs)}"
        return f"{job_id} ({j['kind']}, {j['state']})\n" + "\n".join(j["lines"][-200:])
    return "\n".join(f"{k}: {j['kind']}, {j['state']}, {len(j['lines'])} lines; last: {(j['lines'] or [''])[-1][:200]}"
                     for k, j in reversed(list(jobs.items())))


def _assistant_connections():
    from connections import load_full_config
    full = load_full_config()
    rows = []
    for key, p in full.get("profiles", {}).items():
        sf, tc = p.get("salesforce", {}), p.get("tableau", {})
        org = (p.get("_token_cache") or {}).get("instance_url") or sf.get("sf_login_url", "")
        rows.append(f"{key} ({p.get('label', key)}): "
                    + (f"Salesforce {org}{' [active]' if key == full.get('active_salesforce') else ''}"
                       f"{', Data Cloud connector ' + sf['ingestion_connector_name'] if sf.get('ingestion_connector_name') else ''}"
                       if sf.get("refresh_token") else "no Salesforce")
                    + " | " + (f"Tableau Cloud {tc.get('server_url', '')} site {tc.get('site_name', '')}"
                               f"{' [active]' if key == full.get('active_tableau_cloud') else ''}"
                               if tc.get("pat_secret") else "no Tableau Cloud"))
    return "\n".join(rows) or "No connections saved yet."


def _assistant_summary():
    try:
        from connections import load_full_config
        full = load_full_config()
        prof = full.get("profiles", {})
        sf = prof.get(full.get("active_salesforce") or "", {})
        tc = prof.get(full.get("active_tableau_cloud") or "", {})
        sf_org = (sf.get("_token_cache") or {}).get("instance_url") or (sf.get("salesforce") or {}).get("sf_login_url")
        return (f"Active Salesforce connection: {sf.get('label', 'none')}{' (' + sf_org + ')' if sf_org else ''}. "
                f"Active Tableau Cloud connection: {tc.get('label', 'none')}. "
                f"{len(prof)} saved connections; use list_connections for details.")
    except Exception:
        return "Connections: use list_connections."


@app.route("/api/chat", methods=["POST"])
def chat():
    """Stream the assistant's answer (status lines while it reads docs and logs, then the text)."""
    import assistant
    cfg = _get_chat_config()
    if not cfg:
        return jsonify({"ok": False, "error": "Claude isn't connected yet. "
                        "Open Setup → AI Configuration to connect it."}), 400
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"ok": False, "error": "No messages provided"}), 400
    providers = {"jobs": _assistant_jobs, "connections": _assistant_connections, "summary": _assistant_summary}

    def stream():
        try:
            for event in assistant.chat(cfg, messages, data.get("page_context", {}), providers):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)[:300]})}\n\n"

    return Response(stream(), mimetype="text/event-stream")


@app.route("/api/chat/status", methods=["GET"])
def chat_status():
    """Check if chat is available, and where the credentials come from (no secrets)."""
    from claude_credentials import describe
    return jsonify(describe(_get_chat_config()))


@app.route("/api/chat/test", methods=["POST"])
def chat_test():
    """Send one tiny request with the credentials AIO would use."""
    from claude_credentials import describe, test
    cfg = _get_chat_config()
    if not cfg:
        return jsonify({"ok": False, "error": "No Claude credentials found."})
    ok, msg = test(cfg, CHAT_MODEL)
    return jsonify({"ok": ok, "message": msg, **describe(cfg)})


@app.route("/api/chat/use-claude-code", methods=["POST"])
def chat_use_claude_code():
    """Drop the "use my own key" preference so Claude Code's credentials are used again."""
    from connections import load_full_config, save_full_config
    from claude_credentials import describe
    full = load_full_config()
    full.pop("ai_preference", None)
    save_full_config(full)
    return jsonify({"ok": True, **describe(_get_chat_config())})


@app.route("/api/chat/save-key", methods=["POST"])
def chat_save_key():
    """Save AI chat credentials to config.json (global, not per-profile)."""
    try:
        from connections import load_full_config, save_full_config
        data = request.get_json(silent=True) or {}
        full = load_full_config()

        mode = data.get("mode", "anthropic")
        if mode == "bedrock":
            base_url = data.get("base_url", "").strip()
            auth_token = data.get("auth_token", "").strip()
            if not base_url or not auth_token:
                return jsonify({"ok": False, "error": "Both Gateway URL and Auth Token are required"})
            full["bedrock"] = {"base_url": base_url, "auth_token": auth_token}
            full.pop("anthropic", None)
            full["ai_preference"] = "saved"   # an explicit choice beats Claude Code's credentials
        else:
            api_key = data.get("api_key", "").strip()
            if not api_key:
                return jsonify({"ok": False, "error": "No API key provided"})
            full.setdefault("anthropic", {})["api_key"] = api_key
            full.pop("bedrock", None)
            full["ai_preference"] = "saved"   # an explicit choice beats Claude Code's credentials

        save_full_config(full)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_changelog(limit=5) -> list:
    """Parse CHANGELOG.md into a list of {date, title, bullets} dicts."""
    changelog_path = PROJECT_ROOT / "CHANGELOG.md"
    if not changelog_path.exists():
        return []

    import re
    entries = []
    current = None
    for line in changelog_path.read_text().splitlines():
        heading = re.match(r'^## (\d{4}-\d{2}-\d{2}) — (.+)$', line)
        if heading:
            if current:
                entries.append(current)
                if len(entries) >= limit:
                    break
            current = {"date": heading.group(1), "title": heading.group(2), "bullets": []}
            continue
        if current and line.startswith("- **"):
            bullet = re.sub(r'\*\*([^*]+)\*\*', r'\1', line.lstrip("- "))
            bullet = bullet.split(":")[0] if ":" in bullet else bullet
            if len(bullet) > 80:
                bullet = bullet[:77] + "..."
            current["bullets"].append(bullet)

    if current and len(entries) < limit:
        entries.append(current)
    return entries


def _load_config() -> dict:
    """Load the active profile as a flat {tableau, salesforce} dict for templates."""
    try:
        from connections import load_config
        return load_config()
    except Exception:
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text())
                if "profiles" in raw:
                    key = raw.get("active_profile")
                    if key and key in raw["profiles"]:
                        return raw["profiles"][key]
                return raw
            except json.JSONDecodeError:
                pass
        return {}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("AIO_PORT", 5100))
    print(f"\n  AIO Analytics Builder")
    print(f"  http://localhost:{port}\n")
    if not os.environ.get("WERKZEUG_RUN_MAIN") and not os.environ.get("AIO_RESTARTED"):
        webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
