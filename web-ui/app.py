"""
AIO Analytics Builder — Web UI
Local web server providing a visual, guided experience for building demo assets.
"""

import json
import os
import sys
import queue
import threading
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


def send_progress(build_id: str, stage: str, message: str, pct: int = -1):
    """Push a progress event to the SSE stream for a given build."""
    q = progress_queues.get(build_id)
    if q:
        q.put({"stage": stage, "message": message, "pct": pct})


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
    full = load_full_config()

    if edit_key and edit_key in full.get("profiles", {}):
        set_active_profile(full, edit_key)
        config = _load_config()
        active_profile = full["profiles"][edit_key]
        active_label = active_profile.get("label", "")
        tc = active_profile.get("tableau", {})
        sf = active_profile.get("salesforce", {})
    elif full.get("active_profile") and full["active_profile"] in full.get("profiles", {}):
        edit_key = full["active_profile"]
        active_profile = full["profiles"][edit_key]
        config = _load_config()
        active_label = active_profile.get("label", "")
        tc = active_profile.get("tableau", {})
        sf = active_profile.get("salesforce", {})
    else:
        config = {"tableau": {}, "salesforce": {}}
        active_label = ""
        tc = {}
        sf = {}

    return render_template("setup.html", config=config,
                           edit_profile_key=edit_key or "",
                           edit_profile_label=active_label,
                           edit_has_tableau=bool(tc.get("pat_secret") and tc.get("site_name")),
                           edit_has_salesforce=bool(sf.get("refresh_token") and sf.get("client_id")))


@app.route("/build")
def build():
    config = _load_config()
    has_tableau = bool(config.get("tableau", {}).get("pat_secret"))
    has_salesforce = bool(config.get("salesforce", {}).get("refresh_token"))
    return render_template("build.html", has_tableau=has_tableau, has_salesforce=has_salesforce)


@app.route("/connections")
def connections():
    from connections import load_full_config
    full = load_full_config()
    active_key = full.get("active_profile")

    tableau_conns = []
    salesforce_conns = []
    for key, p in full.get("profiles", {}).items():
        tc = p.get("tableau", {})
        sf = p.get("salesforce", {})
        base = {
            "key": key,
            "label": p.get("label", key),
            "active": key == active_key,
        }
        if tc.get("pat_secret") and tc.get("site_name"):
            tableau_conns.append({
                **base,
                "server": tc.get("server_url", ""),
                "site": tc.get("site_name", ""),
                "has_pat": bool(tc.get("pat_secret")),
            })
        if sf.get("refresh_token") and (sf.get("client_id") or sf.get("data_cloud_domain")):
            salesforce_conns.append({
                **base,
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
                           active_key=active_key)


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

                walkthroughs = sorted(d.glob("*walkthrough*.docx"))
                info["walkthroughs"] = [{"name": w.name, "slug": d.name} for w in walkthroughs]

                demo_list.append(info)

    # Sort by build date (most recent first), then by name
    demo_list.sort(key=lambda x: x.get("build_date", ""), reverse=True)
    return render_template("demos.html", demos=demo_list)


@app.route("/api/demos/<slug>/delete", methods=["POST"])
def delete_demo(slug):
    """Delete a demo folder and optionally clean up remote assets."""
    import shutil
    demos_dir = PROJECT_ROOT / "demos" / slug
    if not demos_dir.exists():
        return jsonify({"ok": False, "error": "Demo not found"})

    data = request.json or {}
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
    """Open a walkthrough .docx file with the system default application."""
    import subprocess, platform as plat
    demos_dir = PROJECT_ROOT / "demos" / slug
    filepath = demos_dir / filename
    if not filepath.exists() or not filename.endswith(".docx"):
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
        profile_key = (request.json or {}).get("profile_key")
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
        profile_key = (request.json or {}).get("profile_key")
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


@app.route("/api/restart", methods=["POST"])
def restart_server():
    """Trigger Flask reloader by touching a .py file."""
    import pathlib
    trigger = pathlib.Path(__file__).resolve()
    trigger.touch()
    return jsonify({"ok": True, "message": "Restart triggered"})


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
    """Switch the active connection profile."""
    try:
        from connections import load_full_config, set_active_profile
        data = request.json
        key = data.get("key")
        if not key:
            return jsonify({"ok": False, "error": "No profile key provided"})
        full = load_full_config()
        if key not in full.get("profiles", {}):
            return jsonify({"ok": False, "error": f"Profile '{key}' not found"})
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
        "update_available": local_version != remote_version or behind,
    })


@app.route("/api/update", methods=["POST"])
def update():
    """Reset to origin/main (same strategy as /update CLI skill). Protects config.json and demos/."""
    import subprocess
    run = lambda cmd: subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30)
    try:
        run(["git", "fetch", "origin", "main", "--quiet"])
        rev_before = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        run(["git", "stash", "push", "-m", "pre-update-stash", "--", "config.json"])
        result = run(["git", "reset", "--hard", "origin/main"])
        run(["git", "stash", "pop"])
        rev_after = run(["git", "rev-parse", "HEAD"]).stdout.strip()
        updated = rev_before != rev_after
        output = result.stdout.strip() or result.stderr.strip()
        if updated:
            log = run(["git", "log", "--oneline", f"{rev_before[:8]}..HEAD"])
            output += "\n" + log.stdout.strip()
        return jsonify({"ok": True, "updated": updated, "output": output})
    except Exception as e:
        return jsonify({"ok": False, "updated": False, "output": str(e)})


@app.route("/api/setup/create-profile", methods=["POST"])
def create_profile():
    """Create a new connection profile (or switch to existing) with the given label."""
    try:
        from connections import load_full_config, save_profile, set_active_profile, make_profile_key, get_profile
        data = request.json or {}
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


@app.route("/api/oauth/mcp", methods=["POST"])
def oauth_mcp():
    """Run OAuth flow specifically for the MCP ECA to get an MCP refresh token."""
    try:
        from connections import load_full_config, save_full_config
        data = request.json or {}
        full = load_full_config()
        key = data.get("profile_key") or full.get("active_profile")
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
        save_full_config(full)

        return jsonify({"ok": True, "instance_url": tokens.get("instance_url", "")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/oauth/start", methods=["POST"])
def oauth_start():
    """Run the Salesforce OAuth browser flow and save the refresh token."""
    try:
        from connections import load_full_config, save_full_config

        data = request.json or {}
        full = load_full_config()
        key = data.get("profile_key") or full.get("active_profile")
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
        data = request.json
        full = load_full_config()

        # Anthropic API key is global (not per-profile) — save it even without a profile
        if "anthropic" in data:
            full.setdefault("anthropic", {}).update(data["anthropic"])

        key = full.get("active_profile")
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
    """Return connection profiles with org details for the build destination picker."""
    from connections import load_full_config
    full = load_full_config()
    active_key = full.get("active_profile")
    result = []
    for key, p in full.get("profiles", {}).items():
        tc = p.get("tableau", {})
        sf = p.get("salesforce", {})
        entry = {
            "key": key,
            "label": p.get("label", key),
            "active": key == active_key,
            "has_tableau": bool(tc.get("pat_secret") and tc.get("site_name")),
            "has_salesforce": bool(sf.get("refresh_token") and sf.get("client_id")),
            "tableau_site": tc.get("site_name", ""),
            "tableau_server": tc.get("server_url", ""),
            "sf_login_url": sf.get("sf_login_url", ""),
            "dc_domain": sf.get("data_cloud_domain", ""),
        }
        result.append(entry)
    return jsonify(result)


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
    """Extract text from uploaded files (PDF, DOCX, TXT, CSV, images)."""
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"})
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename"})

    fname = f.filename.lower()
    try:
        if fname.endswith(".txt") or fname.endswith(".md"):
            text = f.read().decode("utf-8", errors="replace")
        elif fname.endswith(".csv"):
            text = f.read().decode("utf-8", errors="replace")
            lines = text.strip().split("\n")
            if len(lines) > 50:
                text = "\n".join(lines[:50]) + f"\n... ({len(lines)} total rows)"
        elif fname.endswith(".pdf"):
            import PyPDF2
            reader = PyPDF2.PdfReader(f)
            pages = []
            for page in reader.pages[:20]:
                pages.append(page.extract_text() or "")
            text = "\n".join(pages)
        elif fname.endswith(".docx"):
            import docx
            doc = docx.Document(f)
            text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
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

        if len(text) > 15000:
            text = text[:15000] + "\n... (truncated)"

        return jsonify({"ok": True, "filename": f.filename, "type": "text", "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to read {f.filename}: {str(e)[:200]}"})


@app.route("/api/build/generate-story", methods=["POST"])
def build_generate_story():
    """Use Claude API to generate story + metrics from user inputs."""
    data = request.json or {}
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
    data = request.json or {}
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
        "brand": data.get("brand", {}),
    }

    def _run():
        from builder import run_build
        run_build(build_id, build_config, progress_queues[build_id])

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return jsonify({"ok": True, "build_id": build_id})


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

def _build_chat_system_prompt() -> str:
    """Build a system prompt with live context about the user's AIO environment."""
    parts = ["You are the AIO Analytics Builder assistant. You help Tableau and Salesforce "
             "Solutions Engineers build compelling demo assets. Be concise and helpful. "
             "Answer questions about AIO features, Tableau Pulse, Tableau Next, Data Cloud, "
             "Salesforce, demo building, and anything related to the user's connected environment.\n"]

    config = _load_config()
    tc = config.get("tableau", {})
    sf = config.get("salesforce", {})

    if tc.get("pat_secret"):
        parts.append(f"Tableau Cloud: connected to {tc.get('server_url', '?')} "
                     f"(site: {tc.get('site_name', '?')})")
    else:
        parts.append("Tableau Cloud: not configured")

    if sf.get("refresh_token"):
        parts.append(f"Salesforce: connected (DC domain: {sf.get('data_cloud_domain', 'unknown')}, "
                     f"connector: {sf.get('ingestion_connector_name', 'unknown')})")
    else:
        parts.append("Salesforce: not configured")

    demos_dir = PROJECT_ROOT / "demos"
    if demos_dir.exists():
        demo_names = [d.name for d in demos_dir.iterdir()
                      if d.is_dir() and not d.name.startswith(".")]
        if demo_names:
            parts.append(f"Existing demos: {', '.join(sorted(demo_names))}")

    parts.append("\nAvailable build targets: Tableau Pulse (.hyper + metrics), "
                 "Tableau Next (Data Cloud + SDM + vizzes + dashboard), CSV export.")
    parts.append("Available skills: /setup (configure connections), /build-demo (generate demos), "
                 "/refresh-dates (update Pulse dates), /transfer-assets (clone between orgs).")

    return "\n".join(parts)


CHAT_MODEL = "claude-haiku-4-5-20251001"


def _get_chat_config():
    """Resolve chat API credentials. Returns dict with mode + params, or None."""
    # 1. Check env vars (Claude Code session)
    bedrock_url = os.environ.get("ANTHROPIC_BEDROCK_BASE_URL", "")
    bedrock_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    ca_bundle = os.environ.get("NODE_EXTRA_CA_CERTS", "")

    if bedrock_url and bedrock_token:
        return {
            "mode": "bedrock_gateway",
            "base_url": bedrock_url.rstrip("/"),
            "token": bedrock_token,
            "ca_bundle": ca_bundle or True,
        }

    # 2. Check config.json for saved Bedrock or Anthropic credentials
    try:
        full = json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}
    except (json.JSONDecodeError, OSError):
        full = {}

    bedrock_cfg = full.get("bedrock", {})
    if bedrock_cfg.get("base_url") and bedrock_cfg.get("auth_token"):
        return {
            "mode": "bedrock_gateway",
            "base_url": bedrock_cfg["base_url"].rstrip("/"),
            "token": bedrock_cfg["auth_token"],
            "ca_bundle": bedrock_cfg.get("ca_bundle", True),
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        api_key = full.get("anthropic", {}).get("api_key", "")
    if api_key:
        return {"mode": "anthropic_sdk", "api_key": api_key}

    return None


@app.route("/api/chat", methods=["POST"])
def chat():
    """Stream a Claude response for the chat widget."""
    cfg = _get_chat_config()
    if not cfg:
        return jsonify({"ok": False, "error": "No API key found. "
                        "Set ANTHROPIC_API_KEY env var or add it in Setup."}), 400

    data = request.json or {}
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"ok": False, "error": "No messages provided"}), 400

    system_prompt = _build_chat_system_prompt()

    if cfg["mode"] == "bedrock_gateway":
        return _chat_via_bedrock_gateway(cfg, messages, system_prompt)
    elif cfg.get("api_key", "").startswith("sk-ant-oat"):
        return _chat_via_bearer_token(cfg, messages, system_prompt)
    else:
        return _chat_via_anthropic_sdk(cfg, messages, system_prompt)


def _chat_via_bedrock_gateway(cfg, messages, system_prompt):
    """Chat via Bedrock gateway using /invoke (non-streaming — gateway uses
    binary event stream format that requires AWS SDK to parse)."""
    import requests as req

    url = f"{cfg['base_url']}/model/{CHAT_MODEL}/invoke"
    headers = {"x-api-key": cfg["token"], "Content-Type": "application/json"}
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": messages,
    }

    def stream():
        try:
            r = req.post(url, headers=headers, json=body,
                         verify=cfg["ca_bundle"], timeout=60)
            if r.status_code == 200:
                resp = r.json()
                text = ""
                for block in resp.get("content", []):
                    if block.get("type") == "text":
                        text += block["text"]
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'text': r.text[:300]})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)[:300]})}\n\n"

    return Response(stream(), mimetype="text/event-stream")


def _chat_via_bearer_token(cfg, messages, system_prompt):
    """Chat via raw HTTP with Bearer auth (for OAuth tokens from claude setup-token)."""
    import requests as req

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": CHAT_MODEL,
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": messages,
    }

    def stream():
        try:
            r = req.post(url, headers=headers, json=body, timeout=60)
            if r.status_code == 200:
                resp = r.json()
                text = ""
                for block in resp.get("content", []):
                    if block.get("type") == "text":
                        text += block["text"]
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'text': f'Error code: {r.status_code} - {r.text[:300]}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)[:300]})}\n\n"

    return Response(stream(), mimetype="text/event-stream")


def _chat_via_anthropic_sdk(cfg, messages, system_prompt):
    """Stream chat via standard Anthropic SDK."""
    import anthropic
    client = anthropic.Anthropic(api_key=cfg["api_key"])

    def stream():
        try:
            with client.messages.stream(
                model=CHAT_MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
            ) as resp:
                for text in resp.text_stream:
                    yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)[:300]})}\n\n"

    return Response(stream(), mimetype="text/event-stream")


@app.route("/api/chat/status", methods=["GET"])
def chat_status():
    """Check if chat is available (API credentials found)."""
    return jsonify({"available": _get_chat_config() is not None})


@app.route("/api/chat/save-key", methods=["POST"])
def chat_save_key():
    """Save AI chat credentials to config.json (global, not per-profile)."""
    try:
        from connections import load_full_config, save_full_config
        data = request.json or {}
        full = load_full_config()

        mode = data.get("mode", "anthropic")
        if mode == "bedrock":
            base_url = data.get("base_url", "").strip()
            auth_token = data.get("auth_token", "").strip()
            if not base_url or not auth_token:
                return jsonify({"ok": False, "error": "Both Gateway URL and Auth Token are required"})
            full["bedrock"] = {"base_url": base_url, "auth_token": auth_token}
            full.pop("anthropic", None)
        else:
            api_key = data.get("api_key", "").strip()
            if not api_key:
                return jsonify({"ok": False, "error": "No API key provided"})
            full.setdefault("anthropic", {})["api_key"] = api_key
            full.pop("bedrock", None)

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
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open(f"http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)
