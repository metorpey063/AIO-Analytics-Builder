"""Embedding live Tableau content inside the Web UI (verified 2026-11-25; not on a page yet).

What works: a live Tableau Next DASHBOARD renders inside AIO's page (sign-in, framing and the SDK all
verified on AIO Dev). What doesn't, yet: data apps on either platform. The Next SDK's dashboard
component (2.1.0) won't load a data app ("dashboard Component failed to load"), and an embedded Tableau
Cloud view loads but its data app can't fetch its own package (`/api/exp/.../packages/...` returns 401
"No authentication credentials" to the embedded session). So the Data Apps page keeps the rendered
image + Open link, and this module is the ready plumbing for live dashboards (e.g. in My Demos).

Tableau Next: the Analytics Embedding SDK (Lightning Out 2.0) renders the app in the page. It signs in with
a frontdoor URL, minted here through the Salesforce CLI session (`sf org open --url-only`): AIO's own OAuth
token lacks the `web` scope `/services/oauth2/singleaccess` needs. The org must trust the Web UI's origin
under Setup → Session Settings → Trusted Domains for Inline Frames (IFrame type Lightning Out);
`next_trust()` adds it (IframeWhiteListUrlSettings, merged with the entries already there).

Tableau Cloud: the Embedding API v3 renders the app's view, signed in with a connected app JWT
(see cloud_* below).
"""

import json
import os
import shutil
import subprocess
import tempfile

from dataapps import common as C

SETTINGS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<IframeWhiteListUrlSettings xmlns="http://soap.sforce.com/2006/04/metadata">
{entries}
</IframeWhiteListUrlSettings>
"""


def _sf(args, timeout=240, cwd=None):
    r = subprocess.run(["sf"] + args + ["--json"], capture_output=True, text=True, timeout=timeout, cwd=cwd)
    try:
        return json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {"status": 1, "message": (r.stderr or r.stdout)[:400]}


def cli_alias(profile):
    """The Salesforce CLI alias for a connection: the one setup saved, else the CLI org on the same instance."""
    import connections as conn
    cfg = conn.load_config(profile, connection_type="salesforce")
    sf = cfg.get("salesforce", {})
    if sf.get("sf_cli_alias"):
        return sf["sf_cli_alias"]
    instance = ((cfg.get("_token_cache") or {}).get("instance_url") or sf.get("sf_login_url", "")).rstrip("/")
    res = _sf(["org", "list"]).get("result", {})
    for o in res.get("nonScratchOrgs", []) + res.get("scratchOrgs", []):
        if o.get("instanceUrl", "").rstrip("/") == instance and o.get("connectedStatus") == "Connected":
            return o.get("alias") or o.get("username")
    raise SystemExit("Live preview needs a Salesforce CLI login for this org. Run `sf org login web` for it "
                     "(or set the connection up again with automatic setup).")


def next_embed(profile):
    """{orgUrl, authCredential} for the Analytics Embedding SDK."""
    alias = cli_alias(profile)
    res = _sf(["org", "open", "--target-org", alias, "--url-only", "--path", "/lightning"], timeout=120)
    url = (res.get("result") or {}).get("url", "")
    if "frontdoor" not in url:
        raise SystemExit(f"Couldn't get a sign-in link from the Salesforce CLI ({res.get('message', 'no URL')}).")
    host = url.split("/secur/")[0]
    return {"orgUrl": host.replace(".my.salesforce.com", ".lightning.force.com"), "authCredential": url}


def _retrieve_trusted(alias, work):
    os.makedirs(os.path.join(work, "force-app"), exist_ok=True)
    json.dump({"packageDirectories": [{"path": "force-app", "default": True}], "sourceApiVersion": "66.0"},
              open(os.path.join(work, "sfdx-project.json"), "w"))
    _sf(["project", "retrieve", "start", "-m", "IframeWhiteListUrlSettings", "-o", alias], timeout=300, cwd=work)
    path = os.path.join(work, "force-app", "main", "default", "iframeWhiteListUrlSettings",
                        "IframeWhiteListUrlSettings.iframeWhiteListUrlSettings-meta.xml")
    entries = []
    if os.path.exists(path):
        import re
        xml = open(path).read()
        for ctx, url in re.findall(r"<context>([^<]+)</context>\s*<url>([^<]+)</url>", xml):
            entries.append((ctx, url))
    return path, entries


def _origin_forms(origin):
    """The forms a trusted entry for this origin can take ("http://localhost:5100" or "localhost:5100")."""
    bare = origin.split("://", 1)[-1].rstrip("/")
    return {origin.rstrip("/"), bare}


TRUST_CACHE = os.path.join(C.ROOT, "demos", ".embed_trust.json")   # "{alias} {origin}": true, once seen


def _trust_cache():
    try:
        return json.load(open(TRUST_CACHE))
    except (OSError, json.JSONDecodeError):
        return {}


def _remember_trust(alias, origin):
    cache = _trust_cache()
    cache[f"{alias} {origin.rstrip('/')}"] = True
    os.makedirs(os.path.dirname(TRUST_CACHE), exist_ok=True)
    json.dump(cache, open(TRUST_CACHE, "w"))


def next_trusted(profile, origin):
    """True when the org already lets this origin frame Lightning Out. A yes is remembered (the metadata read
    takes ~30 s), so only the first preview per org and address pays for it."""
    alias = cli_alias(profile)
    if _trust_cache().get(f"{alias} {origin.rstrip('/')}"):
        return True
    work = tempfile.mkdtemp(prefix="aio_iframe_")
    try:
        _, entries = _retrieve_trusted(alias, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    ok = any(ctx == "LightningOut" and url.rstrip("/") in _origin_forms(origin) for ctx, url in entries)
    if ok:
        _remember_trust(alias, origin)
    return ok


def next_trust(profile, origin):
    """Add the origin to Trusted Domains for Inline Frames (Lightning Out), keeping every existing entry."""
    alias = cli_alias(profile)
    work = tempfile.mkdtemp(prefix="aio_iframe_")
    try:
        path, entries = _retrieve_trusted(alias, work)
        if any(ctx == "LightningOut" and url.rstrip("/") in _origin_forms(origin) for ctx, url in entries):
            return {"added": False}
        entries.append(("LightningOut", origin.rstrip("/")))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        body = "\n".join(f"    <iframeWhiteListUrls>\n        <context>{c}</context>\n        <url>{u}</url>\n"
                         f"    </iframeWhiteListUrls>" for c, u in entries)
        open(path, "w").write(SETTINGS_XML.format(entries=body))
        res = _sf(["project", "deploy", "start", "-m", "IframeWhiteListUrlSettings", "-o", alias], timeout=600, cwd=work)
        if res.get("status") != 0:
            raise SystemExit(f"Couldn't add {origin} to Trusted Domains for Inline Frames: "
                             f"{json.dumps(res.get('result', res))[:500]}")
        _remember_trust(alias, origin)
        return {"added": True}
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ── Tableau Cloud ────────────────────────────────────────────────────────────

CONNECTED_APP_NAME = "AIO Data App Previews"


class NeedsSetup(Exception):
    """The site has no AIO connected app yet (a site admin creates it once with cloud_setup)."""


def _b64(raw):
    import base64
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _jwt(client_id, secret_id, secret, username, minutes=5):
    """A connected-app token for the Embedding API: HS256, scope views:embed, valid a few minutes."""
    import hashlib
    import hmac
    import time
    import uuid
    head = {"alg": "HS256", "typ": "JWT", "kid": secret_id, "iss": client_id}
    body = {"iss": client_id, "aud": "tableau", "sub": username, "jti": str(uuid.uuid4()),
            "exp": int(time.time()) + minutes * 60,
            "scp": ["tableau:views:embed"]}
    signing = f"{_b64(json.dumps(head).encode())}.{_b64(json.dumps(body).encode())}"
    sig = hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64(sig)}"


def cloud_setup(profile, origin):
    """Create AIO's connected app (direct trust) on the site, allowed only on localhost, and save its keys."""
    import aio_http as requests
    import connections as conn
    from dataapps.cloud import Site
    site = Site(profile)
    try:
        ver = site.server.version
        base = f"{site.base}/api/{ver}/sites/{site.site_id}/connected-applications"
        h = site.headers()
        r = requests.post(base, headers=h, timeout=60, json={"connectedApplication": {
            "name": CONNECTED_APP_NAME, "enabled": True, "domainSafelist": "localhost", "unrestrictedEmbedding": False}})
        if r.status_code not in (200, 201):
            raise SystemExit(f"Couldn't create the connected app ({r.status_code}): {r.text[:300]}. "
                             "This needs a site administrator.")
        client_id = r.json()["connectedApplication"]["clientId"]
        r = requests.post(f"{base}/{client_id}/secrets", headers=h, timeout=60, json={})
        if r.status_code not in (200, 201):
            raise SystemExit(f"Couldn't create the connected app's secret ({r.status_code}): {r.text[:300]}")
        sec = r.json()["connectedApplicationSecret"]
        username = site.server.users.get_by_id(site.server.user_id).name
    finally:
        site.close()
    with conn.config_lock():
        full = conn.load_full_config()
        tc = full["profiles"][profile].setdefault("tableau", {})
        tc.update({"embed_client_id": client_id, "embed_secret_id": sec["id"], "embed_secret": sec["value"],
                   "embed_username": username})
        conn.save_full_config(full)
    return {"created": True, "client_id": client_id}


def cloud_embed(cp, origin):
    """{src, token} for the Embedding API's <tableau-viz>: the app's view and a fresh connected-app token."""
    import tableauserverclient as TSC  # noqa: F401
    import connections as conn
    from dataapps.cloud import Site
    tc = conn.load_config(cp["profile"], connection_type="tableau_cloud")["tableau"]
    if not tc.get("embed_client_id"):
        raise NeedsSetup("Live preview on Tableau Cloud needs AIO's connected app on the site (one-time, site admin).")
    site = Site(cp["profile"])
    try:
        wb = site.server.workbooks.get_by_id(cp["workbook_id"])
        site.server.workbooks.populate_views(wb)
        view = wb.views[0]
    finally:
        site.close()
    path = view.content_url.replace("/sheets/", "/")
    src = f"{tc['server_url'].rstrip('/')}/t/{tc['site_name']}/views/{path}"
    return {"src": src, "token": _jwt(tc["embed_client_id"], tc["embed_secret_id"], tc["embed_secret"], tc["embed_username"])}
