"""Live Tableau Next data apps in the Web UI, without embedding the org.

A deployed Next app is a static build (vendor.iife.js = the platform's UI kit, runtime.js, app.js and
their CSS) that the org runs in a sandboxed about:srcdoc frame. The runtime replaces `fetch` with a
message channel: the frame around it posts {t: "broker-port"} with a MessagePort, every request the app
makes arrives as {t: "data", id, method, url, body}, and the host answers {t: "data:res", id, status,
bodyText}. AIO plays that host: snapshot.py keeps the build files when it photographs the app, the
Web UI builds the same srcdoc page from them, and each data request comes here, is checked against the
same read-only list the org's host enforces, and runs with the connection's own token.
"""

import json
import os
import re
from html import escape

from dataapps import common as C

# The org host's list (host.js `vs`): a data app only reads through these
ALLOWED = [(re.compile(rf"^/services/data/v[\d.]+/{p}$"), m) for p, m in (
    (r"query(?:/[\w-]+)?", "GET"), (r"ssot/query-sql", "POST"), (r"ssot/queryv2/[\w-]+", "GET"),
    (r"semantic-engine/gateway", "POST"), (r"ssot/semantic/models/[^/]+", "GET"), (r"graphql", "POST"))]
_orgs = {}


def build_files(slug):
    """(folder, manifest) of the kept build, or (None, None) when there isn't one."""
    cp = C.load_cp(slug, "next")
    d = cp.get("live_build") or ""
    m = os.path.join(d, "manifest.json")
    if not d or not os.path.exists(m):
        return None, None
    return d, json.load(open(m))


def srcdoc(slug):
    """The app page as the org's host writes it (host.js `Ds`), with the CSS and JS inline: the frame's origin
    is opaque (sandboxed, as in the org), and Chrome blocks its cross-origin loads from localhost (ORB)."""
    d, man = build_files(slug)
    if not man:
        return None
    cp = C.load_cp(slug, "next")
    read = lambda f: open(os.path.join(d, f), encoding="utf-8").read()   # noqa: E731
    # The org's CSP (host.js `Os`), with inline code instead of the asset origin; the app's only way out is the broker
    csp = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
           "font-src data:; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'")
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<meta http-equiv=\"Content-Security-Policy\" content=\"{escape(csp, quote=True)}\">"
            f"<title>{escape(cp.get('label') or slug)}</title>"
            + "".join(f"<style>{read(f).replace('</style', '<\\/style')}</style>" for f in man.get("css", []))
            + "</head><body><div id=\"root\"></div>"
            + "".join(f"<script>{read(f).replace('</script', '<\\/script')}</script>" for f in man.get("js", []))
            + "</body></html>")


def _blocked(method, path, why):
    return 403, json.dumps([{"errorCode": "READ_ONLY", "message": f"Blocked {method} {path}: {why}"}])


def _graphql_read_only(body):
    try:
        b = json.loads(body or "")
    except json.JSONDecodeError:
        return False
    q = b.get("query") if isinstance(b, dict) else None
    return (isinstance(q, str) and set(b) <= {"query", "variables"} and "mutation" not in q.lower()
            and "uiapi" in q)


def request(slug, method, url, body=None):
    """Run one of the app's data requests against its org: (status, body text)."""
    from dataapps import next as N
    method = (method or "GET").upper()
    if not isinstance(url, str) or not url.startswith("/") or url.startswith("//"):
        return _blocked(method, url, "a data app reads org-relative paths only")
    path = url.split("?", 1)[0]
    if not any(rx.match(path) and m == method for rx, m in ALLOWED):
        return _blocked(method, path, "a data app only reads through its query endpoints")
    if path.endswith("/graphql") and not _graphql_read_only(body):
        return _blocked(method, path, "only UI API record queries are allowed")
    cp = C.load_cp(slug, "next")
    if not cp.get("profile"):
        return 404, json.dumps([{"errorCode": "NO_APP", "message": f"No Tableau Next app in demos/{slug}"}])
    org = _orgs.get(cp["profile"]) or _orgs.setdefault(cp["profile"], N.org_for(cp["profile"]))
    headers = org.headers()
    if body is not None:
        headers = {**headers, "Content-Type": "application/json"}
    r = N.requests.request(method, f"{org.instance}{url}", headers=headers, data=body, timeout=180)
    return r.status_code, r.text
