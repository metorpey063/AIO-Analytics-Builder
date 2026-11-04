"""
org_bootstrap.py — zero-click Salesforce / Data 360 setup for AIO.

Replaces the manual External Client App (ECA) checklist in /setup. Uses a
Salesforce CLI session (no app needed) to deploy AIO's two ECAs, read their
consumer keys back, and wait until they're live. After the AIO OAuth login it
finds or creates the Data Cloud Ingest API connector.

Two ECAs are required — they can't be combined:
  - AIO_Analytics_Builder: REST + Data Cloud (api, sfap_api, cdp_query_api,
    cdp_ingest_api, refresh_token). Opaque tokens. No secret (PKCE).
  - AIO_MCP_Client: Tableau Next MCP (mcp_api, refresh_token). Needs
    named-user JWT tokens, which REST and the Data Cloud exchange reject.

CLI:
  python org_bootstrap.py preflight
  python org_bootstrap.py login     --alias aio-dev [--sandbox]
  python org_bootstrap.py apps      --alias aio-dev [--no-mcp] [--update-existing]
  python org_bootstrap.py wait      --alias aio-dev [--no-mcp]
  python org_bootstrap.py authorize --alias aio-dev --profile KEY [--label "My Org"]
  python org_bootstrap.py all       --alias aio-dev --profile KEY [--label ...] [--sandbox] [--no-mcp]

`authorize` runs the AIO browser login, finds/creates the Ingest connector,
tests the Data Cloud exchange, and saves everything to profiles.{KEY}.salesforce.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

CALLBACK_URL = "http://localhost:8080/callback"
DEFAULT_CONNECTOR = "analytics_builder_demo"
REST_SCOPES = "api sfap_api cdp_query_api cdp_ingest_api refresh_token"
MCP_SCOPES = "mcp_api refresh_token"
MCP_URL = "https://api.salesforce.com/platform/mcp/v1/analytics/tableau-next-pilot"

APPS = {
    "rest": {
        "name": "AIO_Analytics_Builder",
        "label": "AIO Analytics Builder",
        "scopes": "Api, RefreshToken, CDPIngest, CDPQuery, SFApiPlatform",
        "jwt": False,
        "secret_optional": True,
    },
    "mcp": {
        "name": "AIO_MCP_Client",
        "label": "AIO MCP Client",
        "scopes": "RefreshToken, MCP",
        "jwt": True,
        "secret_optional": True,
    },
}

_NS = {"m": "http://soap.sforce.com/2006/04/metadata"}
_XML_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'
_UUID_SUFFIX = re.compile(r"_[0-9a-f]{8}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{4}_[0-9a-f]{12}$")


# ── Salesforce CLI helpers ──────────────────────────────────────────────────

def _sf(args, cwd=None, timeout=600):
    """Run an `sf` command with --json and return the parsed result (raises on failure)."""
    r = subprocess.run(["sf", *args, "--json"], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    try:
        body = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"sf {' '.join(args[:3])} failed: {(r.stderr or r.stdout)[:300]}")
    if body.get("status") != 0:
        raise RuntimeError(f"sf {' '.join(args[:3])} failed: {body.get('message', '')[:300]}")
    return body.get("result", {})


def _project_dir():
    d = Path(tempfile.mkdtemp(prefix="aio_bootstrap_"))
    (d / "sfdx-project.json").write_text(json.dumps(
        {"packageDirectories": [{"path": "force-app", "default": True}], "sourceApiVersion": "66.0"}))
    (d / "force-app" / "main" / "default").mkdir(parents=True)
    return d


def preflight():
    """Check the Salesforce CLI is installed. Returns (ok, message)."""
    if not shutil.which("sf"):
        return False, ("Salesforce CLI not found. Install it with `brew install sf` or "
                       "`npm install -g @salesforce/cli`, then re-run setup.")
    r = subprocess.run(["sf", "--version"], capture_output=True, text=True)
    return True, r.stdout.strip()


def cli_login(alias, sandbox=False):
    """Browser login through the Salesforce CLI's built-in app. Returns org info."""
    url = "https://test.salesforce.com" if sandbox else "https://login.salesforce.com"
    res = _sf(["org", "login", "web", "--alias", alias, "--instance-url", url])
    return {"alias": alias, "username": res.get("username", ""),
            "instance_url": res.get("instanceUrl", ""), "org_id": res.get("orgId", "")}


def org_info(alias):
    res = _sf(["org", "display", "--target-org", alias])
    return {"alias": alias, "username": res.get("username", ""),
            "instance_url": res.get("instanceUrl", ""), "org_id": res.get("id", "")}


# ── ECA metadata ────────────────────────────────────────────────────────────

def _eca_files(app, email, consumer_key=""):
    """Metadata files for one ECA, copied from hand-built apps known to work.
    Pass the current consumer_key when updating an existing app so the key never changes."""
    n = app["name"]
    key_line = f"    <consumerKey>{consumer_key}</consumerKey>\n" if consumer_key else ""
    b = lambda v: "true" if v else "false"
    jwt_timeout = "    <namedUserJwtSessionTimeoutType>UserSession</namedUserJwtSessionTimeoutType>\n" if app["jwt"] else ""
    return {
        f"externalClientApps/{n}.eca-meta.xml": f"""<ExternalClientApplication xmlns="http://soap.sforce.com/2006/04/metadata">
    <contactEmail>{email}</contactEmail>
    <distributionState>Local</distributionState>
    <isProtected>false</isProtected>
    <label>{app['label']}</label>
</ExternalClientApplication>""",
        f"extlClntAppOauthSettings/{n}_oauth.ecaOauth-meta.xml": f"""<ExtlClntAppOauthSettings xmlns="http://soap.sforce.com/2006/04/metadata">
    <commaSeparatedOauthScopes>{app['scopes']}</commaSeparatedOauthScopes>
    <externalClientApplication>{n}</externalClientApplication>
    <isFirstPartyAppEnabled>false</isFirstPartyAppEnabled>
    <label>{n}_oauth</label>
</ExtlClntAppOauthSettings>""",
        f"extlClntAppGlobalOauthSets/{n}_glbloauth.ecaGlblOauth-meta.xml": f"""<ExtlClntAppGlobalOauthSettings xmlns="http://soap.sforce.com/2006/04/metadata">
    <callbackUrl>{CALLBACK_URL}</callbackUrl>
{key_line}    <externalClientApplication>{n}</externalClientApplication>
    <isClientCredentialsFlowEnabled>false</isClientCredentialsFlowEnabled>
    <isCodeCredFlowEnabled>true</isCodeCredFlowEnabled>
    <isCodeCredPostOnly>false</isCodeCredPostOnly>
    <isConsumerSecretOptional>{b(app['secret_optional'])}</isConsumerSecretOptional>
    <isDeviceFlowEnabled>false</isDeviceFlowEnabled>
    <isEnforceRefreshTokenTTL>true</isEnforceRefreshTokenTTL>
    <isIntrospectAllTokens>false</isIntrospectAllTokens>
    <isNamedUserJwtEnabled>{b(app['jwt'])}</isNamedUserJwtEnabled>
    <isPkceRequired>true</isPkceRequired>
    <isRefreshTokenRotationEnabled>true</isRefreshTokenRotationEnabled>
    <isSecretRequiredForRefreshToken>false</isSecretRequiredForRefreshToken>
    <isSecretRequiredForTokenExchange>true</isSecretRequiredForTokenExchange>
    <isTokenExchangeEnabled>false</isTokenExchangeEnabled>
    <label>{n}_glbloauth</label>
    <shouldRotateConsumerKey>false</shouldRotateConsumerKey>
    <shouldRotateConsumerSecret>false</shouldRotateConsumerSecret>
</ExtlClntAppGlobalOauthSettings>""",
        f"extlClntAppOauthPolicies/{n}_oauthPlcy.ecaOauthPlcy-meta.xml": f"""<ExtlClntAppOauthConfigurablePolicies xmlns="http://soap.sforce.com/2006/04/metadata">
    <externalClientApplication>{n}</externalClientApplication>
    <ipRelaxationPolicyType>Enforce</ipRelaxationPolicyType>
    <isClientCredentialsFlowEnabled>false</isClientCredentialsFlowEnabled>
    <isGuestCodeCredFlowEnabled>false</isGuestCodeCredFlowEnabled>
    <isTokenExchangeFlowEnabled>false</isTokenExchangeFlowEnabled>
    <label>{n}_oauthPlcy</label>
{jwt_timeout}    <permittedUsersPolicyType>AllSelfAuthorized</permittedUsersPolicyType>
    <refreshTokenPolicyType>SpecificInactivity</refreshTokenPolicyType>
    <refreshTokenValidityPeriod>30</refreshTokenValidityPeriod>
    <refreshTokenValidityUnit>Days</refreshTokenValidityUnit>
    <requiredSessionLevel>STANDARD</requiredSessionLevel>
</ExtlClntAppOauthConfigurablePolicies>""",
        f"extlClntAppPolicies/{n}_plcy.ecaPlcy-meta.xml": f"""<ExtlClntAppConfigurablePolicies xmlns="http://soap.sforce.com/2006/04/metadata">
    <externalClientApplication>{n}</externalClientApplication>
    <isEnabled>true</isEnabled>
    <isOauthPluginEnabled>true</isOauthPluginEnabled>
    <label>{n}_plcy</label>
    <startPage>None</startPage>
</ExtlClntAppConfigurablePolicies>""",
    }


def _existing_apps(alias):
    res = _sf(["org", "list", "metadata", "--metadata-type", "ExternalClientApplication", "--target-org", alias])
    items = res if isinstance(res, list) else ([res] if res else [])
    return {i["fullName"] for i in items}


def _read_app(alias, name):
    """Retrieve an ECA's OAuth settings. Returns {consumer_key, scopes, settings{...}}."""
    d = _project_dir()
    try:
        _sf(["project", "retrieve", "start", "--target-org", alias,
             "--metadata", f"ExtlClntAppGlobalOauthSettings:{name}_glbloauth",
             "--metadata", f"ExtlClntAppOauthSettings:{name}_oauth"], cwd=d)
        base = d / "force-app" / "main" / "default"
        g = ET.parse(base / "extlClntAppGlobalOauthSets" / f"{name}_glbloauth.ecaGlblOauth-meta.xml").getroot()
        o = ET.parse(base / "extlClntAppOauthSettings" / f"{name}_oauth.ecaOauth-meta.xml").getroot()
        settings = {c.tag.split("}")[1]: (c.text or "") for c in g}
        scopes = {s.strip() for s in (o.findtext("m:commaSeparatedOauthScopes", "", _NS)).split(",") if s.strip()}
        return {"consumer_key": settings.get("consumerKey", ""), "scopes": scopes, "settings": settings}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _mismatches(app, found):
    """Why an existing app can't be used by AIO as-is (empty list = compatible)."""
    s, problems = found["settings"], []
    missing = {x.strip() for x in app["scopes"].split(",")} - found["scopes"]
    if missing:
        problems.append(f"missing scopes: {', '.join(sorted(missing))}")
    if s.get("callbackUrl", "").strip() != CALLBACK_URL:
        problems.append(f"callback URL is {s.get('callbackUrl') or '(none)'}")
    if s.get("isCodeCredFlowEnabled") != "true":
        problems.append("Authorization Code and Credentials Flow is off")
    if app["secret_optional"] and s.get("isConsumerSecretOptional") != "true":
        problems.append("requires a consumer secret")
    if s.get("isSecretRequiredForRefreshToken") == "true":
        problems.append("requires a secret on refresh")
    if s.get("isNamedUserJwtEnabled") != ("true" if app["jwt"] else "false"):
        problems.append("JWT access tokens " + ("off (MCP needs them)" if app["jwt"] else "on (REST rejects them)"))
    return problems


def deploy_apps(alias, include_mcp=True, update_existing=False, email=None, apps=None):
    """
    Deploy (or reuse) AIO's ECAs. Returns {kind: {name, consumer_key, status}} where
    status is "created", "reused", "updated", or "needs_update" (with "problems").
    An existing, incompatible app is only overwritten when update_existing=True.
    """
    apps = apps or APPS
    kinds = ["rest", "mcp"] if include_mcp else ["rest"]
    email = email or org_info(alias)["username"]
    existing = _existing_apps(alias)
    out, to_deploy = {}, []
    for k in kinds:
        app = apps[k]
        if app["name"] in existing:
            found = _read_app(alias, app["name"])
            problems = _mismatches(app, found)
            if not problems:
                out[k] = {"name": app["name"], "consumer_key": found["consumer_key"], "status": "reused"}
                continue
            if not update_existing:
                out[k] = {"name": app["name"], "consumer_key": found["consumer_key"],
                          "status": "needs_update", "problems": problems}
                continue
            out[k] = {"name": app["name"], "status": "updated", "keep_key": found["consumer_key"]}
        else:
            out[k] = {"name": app["name"], "status": "created"}
        to_deploy.append((k, app))

    if to_deploy:
        d = _project_dir()
        try:
            base = d / "force-app" / "main" / "default"
            for k, app in to_deploy:
                for rel, xml in _eca_files(app, email, out[k].pop("keep_key", "")).items():
                    p = base / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(_XML_HEAD + xml + "\n")
            _sf(["project", "deploy", "start", "--target-org", alias, "--source-dir", "force-app"], cwd=d)
        finally:
            shutil.rmtree(d, ignore_errors=True)
        for k in kinds:
            if out[k]["status"] in ("created", "updated"):
                out[k]["consumer_key"] = _read_app(alias, apps[k]["name"])["consumer_key"]
    return out


def remove_apps(alias, names):
    """Delete ECAs by name (all five components each). Only call for apps AIO created."""
    d = _project_dir()
    try:
        args = ["project", "delete", "source", "--target-org", alias, "--no-prompt"]
        for n in names:
            for t, suffix in [("ExternalClientApplication", ""), ("ExtlClntAppOauthSettings", "_oauth"),
                              ("ExtlClntAppGlobalOauthSettings", "_glbloauth"),
                              ("ExtlClntAppOauthConfigurablePolicies", "_oauthPlcy"),
                              ("ExtlClntAppConfigurablePolicies", "_plcy")]:
                args += ["--metadata", f"{t}:{n}{suffix}"]
        _sf(args, cwd=d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def wait_until_active(my_domain, consumer_keys, timeout=900, stable=30, on_tick=None):
    """
    Poll the authorize endpoint until every key returns 302 `stable` times in a row
    (400 = not live yet; ~2s apart, so 30 = a clean minute). New apps take from ~20s
    to ~4 min, and login servers pick them up one by one, so a few early 302s aren't
    enough. Use My Domain — login.salesforce.com keeps returning 400 for longer.
    """
    start, ok = time.time(), {k: 0 for k in consumer_keys}
    while time.time() - start < timeout:
        for k in consumer_keys:
            if ok[k] >= stable:
                continue
            r = requests.get(f"{my_domain}/services/oauth2/authorize", allow_redirects=False, params={
                "response_type": "code", "client_id": k, "redirect_uri": CALLBACK_URL,
                "code_challenge": "aio_probe", "code_challenge_method": "S256"})
            ok[k] = ok[k] + 1 if r.status_code == 302 else 0
        if all(v >= stable for v in ok.values()):
            return int(time.time() - start)
        if on_tick:
            on_tick(int(time.time() - start))
        time.sleep(2 if any(ok.values()) else 15)
    raise TimeoutError(f"Apps not active after {timeout}s — wait a few minutes and run `wait` again.")


# ── Ingest connector ────────────────────────────────────────────────────────

def connector_short_name(conn):
    """Bulk Ingest `sourceName`: the connector's UUID name without the UUID suffix."""
    return _UUID_SUFFIX.sub("", conn.get("name", "")) or conn.get("label", "")


def ensure_ingest_connector(sf_token, sf_instance, name=DEFAULT_CONNECTOR):
    """Reuse an existing Ingest API connector (name match first, else any), or create one."""
    h = {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}
    url = f"{sf_instance}/services/data/v62.0/ssot/connections"
    r = requests.get(url, headers=h, params={"connectorType": "IngestApi", "limit": 100})
    r.raise_for_status()
    conns = r.json().get("connections", [])
    match = next((c for c in conns if name.lower() in c.get("name", "").lower()), None) or (conns[0] if conns else None)
    created = False
    if not match:
        r = requests.post(url, headers=h, json={"label": name, "name": name, "connectorType": "IngestApi"})
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Could not create Ingest connector: {r.status_code} {r.text[:300]}")
        match, created = r.json(), True
    return {"connector_sf_id": match["id"], "connector_uuid_name": match["name"],
            "ingestion_connector_name": connector_short_name(match), "created": created}


# ── AIO login + profile save ────────────────────────────────────────────────

def authorize_and_save(profile_key, my_domain, rest_key, mcp_key="", label=None, alias=""):
    """
    AIO browser login with the REST app (no secret), Data Cloud check, connector, and
    profile save. Returns the saved salesforce dict (without tokens) for display.
    """
    from oauth_flow import get_refresh_token
    from connections import get_dc_token, load_full_config, save_full_config, set_active_connection, _EMPTY_PROFILE
    import copy

    tokens = get_refresh_token(rest_key, "", my_domain, scopes=REST_SCOPES)
    sf_token, sf_instance = tokens["access_token"], tokens["instance_url"]
    if alias:
        cli_org = org_info(alias)["org_id"][:15]
        oauth_org = tokens.get("id", "").split("/id/")[-1].split("/")[0][:15]
        if cli_org and oauth_org and cli_org != oauth_org:
            raise RuntimeError(
                f"The AIO login landed in a different org ({oauth_org}) than the CLI login ({cli_org}). "
                "Sign out of all other Salesforce orgs in your browser, log into only the target org, and retry.")
    dc_token, dc_domain = get_dc_token(sf_token, sf_instance)
    conn = ensure_ingest_connector(sf_token, sf_instance)

    full = load_full_config()
    profile = full.get("profiles", {}).get(profile_key) or copy.deepcopy(_EMPTY_PROFILE)
    if label:
        profile["label"] = label
    sf = profile.setdefault("salesforce", {})
    sf.update({
        "sf_login_url": my_domain,
        "client_id": rest_key,
        "client_secret": "",
        "refresh_token": tokens["refresh_token"],
        "code_verifier": tokens.get("code_verifier", ""),
        "data_cloud_domain": dc_domain,
        "connector_sf_id": conn["connector_sf_id"],
        "connector_uuid_name": conn["connector_uuid_name"],
        "ingestion_connector_name": conn["ingestion_connector_name"],
        "sf_cli_alias": alias,
    })
    if mcp_key:
        sf["mcp_client_id"] = mcp_key
        sf["mcp_client_secret"] = ""
    sf.pop("pkce_refresh_mode", None)
    profile["_token_cache"] = {"access_token": sf_token, "instance_url": sf_instance,
                               "expires_at": time.time() + 7200}
    full.setdefault("profiles", {})[profile_key] = profile
    save_full_config(full)
    set_active_connection(load_full_config(), "salesforce", profile_key)

    return {"instance_url": sf_instance, "data_cloud_domain": dc_domain, "connector": conn,
            "client_id": rest_key, "mcp_client_id": mcp_key}


def register_claude_mcp(mcp_key):
    """Point Claude Code's tableau-next-pilot MCP server at the MCP app (user still runs /mcp to log in)."""
    if not shutil.which("claude"):
        return False, "Claude Code CLI not found — skipping MCP registration."
    subprocess.run(["claude", "mcp", "remove", "tableau-next-pilot"], capture_output=True)
    r = subprocess.run(["claude", "mcp", "add", "tableau-next-pilot", "--transport", "http",
                        "--callback-port", "8080", "--scope", "user", "--client-id", mcp_key, MCP_URL],
                       capture_output=True, text=True)
    return r.returncode == 0, (r.stdout or r.stderr).strip()


# ── CLI ─────────────────────────────────────────────────────────────────────

def _print(obj):
    print(json.dumps(obj, indent=2))


def main():
    sys.path.insert(0, str(Path(__file__).parent))
    p = argparse.ArgumentParser(description="Zero-click Salesforce org setup for AIO")
    p.add_argument("command", choices=["preflight", "login", "apps", "wait", "authorize", "mcp", "all"])
    p.add_argument("--alias", default="aio-org")
    p.add_argument("--profile", help="config.json profile key to save into")
    p.add_argument("--label", help="display label for a new profile")
    p.add_argument("--sandbox", action="store_true")
    p.add_argument("--no-mcp", action="store_true")
    p.add_argument("--update-existing", action="store_true",
                   help="overwrite an existing AIO app whose settings AIO can't use")
    a = p.parse_args()

    if a.command == "preflight":
        ok, msg = preflight()
        _print({"ok": ok, "message": msg})
        sys.exit(0 if ok else 1)

    if a.command in ("login", "all"):
        print("Sign out of every other Salesforce org in your default browser first, then log into only the org you want to build in. A browser signed into another org causes 'Cross-org OAuth flows are not supported' errors.", flush=True)
        info = cli_login(a.alias, a.sandbox)
        _print({"step": "login", **info})
        if a.command == "login":
            return

    info = org_info(a.alias)
    my_domain = info["instance_url"]

    if a.command in ("apps", "all"):
        apps = deploy_apps(a.alias, include_mcp=not a.no_mcp, update_existing=a.update_existing)
        _print({"step": "apps", "apps": apps})
        if any(v["status"] == "needs_update" for v in apps.values()):
            print("\nAn existing AIO app has settings AIO can't use. Re-run with --update-existing to fix it.")
            sys.exit(2)
        if a.command == "apps":
            return

    apps = deploy_apps(a.alias, include_mcp=not a.no_mcp) if a.command != "all" else apps
    keys = [v["consumer_key"] for v in apps.values()]

    if a.command in ("wait", "all"):
        secs = wait_until_active(my_domain, keys, on_tick=lambda s: print(f"  waiting for apps to go live... {s}s", flush=True))
        _print({"step": "wait", "active_after_seconds": secs})
        if a.command == "wait":
            return

    if a.command in ("authorize", "all"):
        if not a.profile:
            sys.exit("--profile is required for authorize")
        print("Opening browser for the AIO login — log in and click Allow.", flush=True)
        saved = authorize_and_save(a.profile, my_domain, apps["rest"]["consumer_key"],
                                   apps.get("mcp", {}).get("consumer_key", ""), a.label, a.alias)
        _print({"step": "authorize", **saved})

    if a.command in ("mcp", "all") and "mcp" in apps:
        ok, msg = register_claude_mcp(apps["mcp"]["consumer_key"])
        _print({"step": "mcp", "ok": ok, "message": msg,
                "next": "Run /mcp in Claude Code, select tableau-next-pilot, and log in."})


if __name__ == "__main__":
    main()
