"""
Core connection module for AIO Analytics Builder.
Handles Tableau Cloud (PAT) and Salesforce/Data Cloud (OAuth) auth.

Connections are stored in config.json under "profiles" (kept for storage compat).
Each entry is one org or site with its own credentials.

Two independent "active" pointers control defaults:
  active_salesforce    — the SF / Data 360 connection (used by Next, CRMA builds)
  active_tableau_cloud — the Tableau Cloud connection (used by Pulse builds)

The build flow picks the connection at output-selection time. If the user
selects a non-active connection, the UI prompts re-authentication.
"""

import contextlib
import json
import os
import tempfile
import threading
import aio_http as requests
import tableauserverclient as TSC

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

_EMPTY_PROFILE = {
    "tableau": {
        "server_url": "",
        "site_name": "",
        "pat_name": "Claude Code",
        "pat_secret": "",
    },
    "salesforce": {
        "sf_login_url": "https://login.salesforce.com",
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
        "data_cloud_domain": "",
        "ingestion_connector_name": "analytics_builder_demo",
        "connector_sf_id": "",
        "connector_uuid_name": "",
    },
    "google": {
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
    },
    "slack": {
        "workspace_id": "",
        "channel_id": "",
        "channel_name": "",
        "app_id": "",
    },
}


# ── File-level helpers ─────────────────────────────────────────────────────────

def load_full_config() -> dict:
    """Load the raw config file. Migrates old formats automatically."""
    if not os.path.exists(CONFIG_FILE):
        return {"active_salesforce": None, "active_tableau_cloud": None, "profiles": {}}

    with open(CONFIG_FILE) as f:
        raw = json.load(f)

    changed = False

    # Migrate v1: flat format (no "profiles" key)
    if "profiles" not in raw:
        profile = {
            "label": raw.get("_label", "Default"),
            "tableau": raw.get("tableau", {}),
            "salesforce": raw.get("salesforce", {}),
        }
        raw = {
            "active_salesforce": "default",
            "active_tableau_cloud": "default",
            "profiles": {"default": profile},
        }
        changed = True

    # Migrate v2: single active_profile → split active per type
    if "active_profile" in raw:
        old_active = raw.pop("active_profile")
        if "active_salesforce" not in raw:
            raw["active_salesforce"] = old_active
        if "active_tableau_cloud" not in raw:
            raw["active_tableau_cloud"] = old_active
        changed = True

    # Ensure both active keys exist
    if "active_salesforce" not in raw:
        raw["active_salesforce"] = None
        changed = True
    if "active_tableau_cloud" not in raw:
        raw["active_tableau_cloud"] = None
        changed = True

    if changed:
        save_full_config(raw)

    return raw


_config_thread_lock = threading.RLock()
_config_lock_depth = 0     # only touched while holding _config_thread_lock


@contextlib.contextmanager
def config_lock():
    """Hold this around any load -> change -> save of config.json.

    Build threads, Web UI requests and the CLI/subprocess tools all rewrite the file (every
    token refresh does), and Salesforce rotates refresh tokens: a lost write there means a
    forced re-login. The thread lock covers this process; the flock on config.json.lock
    covers the others. Re-entrant within a thread.
    """
    global _config_lock_depth
    with _config_thread_lock:
        fh = None
        if _config_lock_depth == 0:
            # Outermost entry only: a second flock from the same process (on a new file handle)
            # would wait on the first forever
            try:
                import fcntl
                fh = open(CONFIG_FILE + ".lock", "a")
                fcntl.flock(fh, fcntl.LOCK_EX)
            except (ImportError, OSError):
                fh = None   # no flock here (Windows, read-only dir): the thread lock still applies
        _config_lock_depth += 1
        try:
            yield
        finally:
            _config_lock_depth -= 1
            if fh:
                fh.close()   # closing releases the flock


def save_full_config(full_config: dict):
    """Write config.json atomically and readable only by the user (it holds org secrets).

    The new content goes to a temp file in the same folder, then replaces the old file in one
    step, so a crash mid-write can't leave a truncated config."""
    folder = os.path.dirname(os.path.abspath(CONFIG_FILE))
    with config_lock():
        fd, tmp = tempfile.mkstemp(prefix=".config.json.", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "w") as f:   # mkstemp creates the file 0600
                json.dump(full_config, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, CONFIG_FILE)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise


def secure_config_file():
    """Tighten an existing config.json that was written with default permissions."""
    with contextlib.suppress(OSError):
        if os.path.exists(CONFIG_FILE) and os.stat(CONFIG_FILE).st_mode & 0o077:
            os.chmod(CONFIG_FILE, 0o600)


def _resolve_key(full: dict, profile_key: str = None, connection_type: str = None) -> str | None:
    """Resolve which profile key to use."""
    if profile_key:
        return profile_key
    if connection_type == "tableau_cloud":
        return full.get("active_tableau_cloud") or full.get("active_salesforce")
    return full.get("active_salesforce") or full.get("active_tableau_cloud")


def _sf_key_for(full: dict, sf: dict, profile_key: str = None) -> str | None:
    """The connection a Salesforce config belongs to, for its token cache and saved tokens.
    Callers often pass only a connection's config (get_sf_token(config)). Falling back to the
    active connection there returned the active org's cached token for another connection, and
    saved that connection's refreshed tokens over the active one's. Match the config's own
    credentials instead; None (no cache, nothing saved) when no connection matches."""
    profiles = full.get("profiles", {})
    if profile_key:
        return profile_key if profile_key in profiles else None
    rt, cid = sf.get("refresh_token"), sf.get("client_id")
    matches = [k for k, p in profiles.items()
               if rt and p.get("salesforce", {}).get("refresh_token") == rt
               and p.get("salesforce", {}).get("client_id") == cid]
    return matches[0] if len(matches) == 1 else None


GENERIC_LOGIN_URLS = {"https://login.salesforce.com", "https://test.salesforce.com"}


def pin_login_url(sf: dict, instance_url: str) -> bool:
    """Swap a generic login URL for the org's own My Domain (from a token response), in place.
    A connection on login.salesforce.com signs in to whichever org the browser is logged into, so
    an OAuth or MCP click while signed into another org fails cross-org, or saves the wrong org's
    tokens. A My Domain always lands in its own org and accepts the same tokens. Only replaces a
    generic URL, and only with a *.my.salesforce.com address. Returns True when it changed."""
    from urllib.parse import urlparse
    current = (sf.get("sf_login_url") or "https://login.salesforce.com").rstrip("/")
    u = urlparse(instance_url or "")
    if current not in GENERIC_LOGIN_URLS or u.scheme != "https" or not (u.hostname or "").endswith(".my.salesforce.com"):
        return False
    sf["sf_login_url"] = f"https://{u.hostname}"
    return True


def load_config(profile_key: str = None, connection_type: str = None) -> dict:
    """
    Returns a connection's {tableau, salesforce, ...} dict.

    Resolution order:
      1. Explicit profile_key (backward compat)
      2. Active connection for the requested type
      3. active_salesforce as fallback
    """
    full = load_full_config()
    key = _resolve_key(full, profile_key, connection_type)
    if not key or key not in full.get("profiles", {}):
        raise RuntimeError(
            "No active connection found. Run /setup to configure one."
        )
    return full["profiles"][key]


# ── Connection management ────────────────────────────────────────────────────

def list_connections(full_config: dict, conn_type: str = None) -> list[dict]:
    """List connections, optionally filtered by type.

    conn_type: "salesforce" | "tableau_cloud" | None (all)
    """
    active_sf = full_config.get("active_salesforce")
    active_tc = full_config.get("active_tableau_cloud")
    result = []
    for key, profile in full_config.get("profiles", {}).items():
        tc = profile.get("tableau", {})
        sf = profile.get("salesforce", {})
        has_tableau = bool(tc.get("pat_secret") and tc.get("site_name"))
        has_sf = bool(sf.get("refresh_token"))

        if conn_type == "salesforce" and not has_sf:
            continue
        if conn_type == "tableau_cloud" and not has_tableau:
            continue

        caps = []
        if has_tableau:
            caps.append("Tableau Cloud")
        if has_sf:
            caps.append("Salesforce / Data 360")

        result.append({
            "key": key,
            "label": profile.get("label", key),
            "capabilities": ", ".join(caps) if caps else "not configured",
            "active_salesforce": key == active_sf,
            "active_tableau_cloud": key == active_tc,
            "active": key == active_sf or key == active_tc,
            "has_tableau": has_tableau,
            "has_sf": has_sf,
        })
    return result


def get_active_key(full_config: dict, conn_type: str) -> str | None:
    """Return the key of the active connection for a given type."""
    if conn_type == "tableau_cloud":
        return full_config.get("active_tableau_cloud")
    return full_config.get("active_salesforce")


def set_active_connection(full_config: dict, conn_type: str, key: str):
    """Set the active connection for a specific type only."""
    if conn_type == "tableau_cloud":
        full_config["active_tableau_cloud"] = key
    else:
        full_config["active_salesforce"] = key
    save_full_config(full_config)


# ── Backward-compat aliases ──────────────────────────────────────────────────

def list_profiles(full_config: dict) -> list[dict]:
    return list_connections(full_config)


def get_profile(full_config: dict, key: str) -> dict:
    import copy
    return copy.deepcopy(full_config.get("profiles", {}).get(key, _EMPTY_PROFILE))


def save_profile(full_config: dict, key: str, profile: dict):
    if "profiles" not in full_config:
        full_config["profiles"] = {}
    full_config["profiles"][key] = profile
    # Auto-set active for whichever types this profile has credentials for
    tc = profile.get("tableau", {})
    sf = profile.get("salesforce", {})
    if full_config.get("active_salesforce") is None and sf.get("refresh_token"):
        full_config["active_salesforce"] = key
    if full_config.get("active_tableau_cloud") is None and tc.get("pat_secret"):
        full_config["active_tableau_cloud"] = key
    save_full_config(full_config)


def set_active_profile(full_config: dict, key: str):
    """Backward compat — sets active for whichever types the profile supports."""
    profile = full_config.get("profiles", {}).get(key, {})
    tc = profile.get("tableau", {})
    sf = profile.get("salesforce", {})
    if sf.get("refresh_token"):
        full_config["active_salesforce"] = key
    if tc.get("pat_secret") and tc.get("site_name"):
        full_config["active_tableau_cloud"] = key
    if not sf.get("refresh_token") and not tc.get("pat_secret"):
        full_config["active_salesforce"] = key
        full_config["active_tableau_cloud"] = key
    save_full_config(full_config)


def delete_profile(full_config: dict, key: str):
    full_config.get("profiles", {}).pop(key, None)
    for active_key in ("active_salesforce", "active_tableau_cloud"):
        if full_config.get(active_key) == key:
            remaining = list(full_config.get("profiles", {}).keys())
            full_config[active_key] = remaining[0] if remaining else None
    save_full_config(full_config)


def make_profile_key(label: str) -> str:
    """Turn a human label into a safe dict key."""
    import re
    key = label.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return key or "connection"


# ── Tableau Cloud (Pulse) ────────────────────────────────────────────────────

def get_tableau_token(config=None):
    """Returns (server, auth_token, site_id) for Tableau Cloud REST API calls."""
    if config is None:
        config = load_config(connection_type="tableau_cloud")
    tc = config["tableau"]
    auth = TSC.PersonalAccessTokenAuth(tc["pat_name"], tc["pat_secret"], site_id=tc["site_name"])
    server = TSC.Server(tc["server_url"], use_server_version=True)
    server.auth.sign_in(auth)
    return server, server.auth_token, server.site_id


def tableau_headers(auth_token):
    return {
        "x-tableau-auth": auth_token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def tableau_pulse_headers(auth_token):
    return {
        "x-tableau-auth": auth_token,
        "Content-Type": "application/vnd.tableau.metricqueryservice.v1.CreateDefinitionRequest+json",
        "Accept": "application/json",
    }


# ── Salesforce + Data Cloud (Tableau Next) ──────────────────────────────────

def _is_expired_refresh_token(response):
    """Check if a token request failed due to an expired/revoked refresh token."""
    if response.status_code != 400:
        return False
    try:
        body = response.json()
    except Exception:
        body = {}
    err = body.get("error", "")
    desc = body.get("error_description", "").lower()
    if "code verifier" in desc or "code_verifier" in desc:
        return False
    if "app_not_found" in err or "app not installed" in desc:
        return False
    if "invalid client" in desc or "client_id" in desc:
        return False
    return (
        "expired access/refresh token" in desc
        or "token has been expired" in desc
        or "refresh token has expired" in desc
        or (err == "invalid_grant" and "expired" in desc)
    )


class ReauthRequired(RuntimeError):
    """The refresh token expired and this process can't open a browser login (AIO_NO_BROWSER_REAUTH)."""

    def __init__(self, profile_key):
        self.profile_key = profile_key
        super().__init__(f"The Salesforce login for '{profile_key}' expired. Reconnect it (Connections → OAuth), then retry.")


def _reauth_via_browser(sf, profile_key=None, allow_browser=True):
    """Run the OAuth browser flow to get a fresh refresh token.
    Background jobs (Web UI subprocesses) set AIO_NO_BROWSER_REAUTH: a hidden login there can't be
    completed and fights over the callback port, so they get ReauthRequired instead."""
    if not allow_browser or os.environ.get("AIO_NO_BROWSER_REAUTH"):
        raise ReauthRequired(profile_key)
    from oauth_flow import get_refresh_token

    print("\n⚠  Refresh token expired (Salesforce enforces a 30-day idle TTL).")
    print("   Opening browser to re-authenticate…\n")

    tokens = get_refresh_token(
        sf["client_id"],
        sf.get("client_secret", ""),
        sf.get("sf_login_url", "https://login.salesforce.com"),
    )

    full = load_full_config()
    key = _sf_key_for(full, sf, profile_key)
    if key:
        full["profiles"][key]["salesforce"]["refresh_token"] = tokens["refresh_token"]
        if tokens.get("code_verifier"):
            full["profiles"][key]["salesforce"]["code_verifier"] = tokens["code_verifier"]
        full["profiles"][key]["salesforce"].pop("pkce_refresh_mode", None)
        pin_login_url(full["profiles"][key]["salesforce"], tokens.get("instance_url", ""))
        import time as _time
        full["profiles"][key]["_token_cache"] = {
            "access_token": tokens["access_token"],
            "instance_url": tokens["instance_url"],
            "expires_at": _time.time() + 7200,
        }
        save_full_config(full)

    return tokens["access_token"], tokens["instance_url"]


def get_sf_token(config=None, profile_key=None, allow_browser=True):
    """Returns (sf_token, sf_instance) via refresh_token grant.
    allow_browser=False raises ReauthRequired instead of opening a login when the refresh token expired."""
    full = load_full_config()
    if config is None:
        config = load_config(profile_key, connection_type="salesforce")
        profile_key = profile_key or _resolve_key(full, connection_type="salesforce")
    sf = config["salesforce"]
    key = _sf_key_for(full, sf, profile_key)
    profile_key = key   # re-auth saves under the same connection

    import time as _time
    if key:
        cached = full["profiles"][key].get("_token_cache", {})
        cached_token = cached.get("access_token", "")
        cached_instance = cached.get("instance_url", "")
        cached_expiry = cached.get("expires_at", 0)
        if cached_token and cached_instance and _time.time() < cached_expiry - 60:
            return cached_token, cached_instance

    data = {
        "grant_type": "refresh_token",
        "refresh_token": sf["refresh_token"],
        "client_id": sf["client_id"],
    }
    if sf.get("client_secret"):
        data["client_secret"] = sf["client_secret"]

    pkce_mode = sf.get("pkce_refresh_mode")
    if pkce_mode == "required" and sf.get("code_verifier"):
        data["code_verifier"] = sf["code_verifier"]
    elif pkce_mode == "rejected":
        pass
    else:
        pass

    r = requests.post(f"{sf['sf_login_url']}/services/oauth2/token", data=data)

    if _is_expired_refresh_token(r):
        return _reauth_via_browser(sf, profile_key, allow_browser)

    if r.status_code == 400 and sf.get("code_verifier"):
        err_text = r.text.lower()
        if "invalid code verifier" in err_text or "code verifier required" in err_text:
            data["code_verifier"] = sf["code_verifier"]
            r = requests.post(f"{sf['sf_login_url']}/services/oauth2/token", data=data)
            if _is_expired_refresh_token(r):
                return _reauth_via_browser(sf, profile_key, allow_browser)
            pkce_mode = "required"
        elif "unexpected code verifier" in err_text:
            data.pop("code_verifier", None)
            r = requests.post(f"{sf['sf_login_url']}/services/oauth2/token", data=data)
            if _is_expired_refresh_token(r):
                return _reauth_via_browser(sf, profile_key, allow_browser)
            pkce_mode = "rejected"

    r.raise_for_status()
    body = r.json()

    new_refresh = body.get("refresh_token")
    with config_lock():
        full = load_full_config()
        if key and key in full.get("profiles", {}):
            if new_refresh and new_refresh != sf["refresh_token"]:
                full["profiles"][key]["salesforce"]["refresh_token"] = new_refresh
                sf["refresh_token"] = new_refresh
            if pkce_mode and sf.get("pkce_refresh_mode") != pkce_mode:
                full["profiles"][key]["salesforce"]["pkce_refresh_mode"] = pkce_mode
            if pin_login_url(full["profiles"][key]["salesforce"], body.get("instance_url", "")):
                sf["sf_login_url"] = full["profiles"][key]["salesforce"]["sf_login_url"]
            full["profiles"][key]["_token_cache"] = {
                "access_token": body["access_token"],
                "instance_url": body["instance_url"],
                "expires_at": _time.time() + 7200,
            }
            save_full_config(full)

    return body["access_token"], body["instance_url"]


def get_dc_token(sf_token, sf_instance):
    """Exchange SF token for Data Cloud token. Returns (dc_token, dc_domain)."""
    r = requests.post(
        f"{sf_instance}/services/a360/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:salesforce:grant-type:external:cdp",
            "subject_token": sf_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        },
    )
    r.raise_for_status()
    body = r.json()
    return body["access_token"], body["instance_url"]


def get_all_tokens(config=None):
    """Returns (sf_token, sf_instance, dc_token, dc_domain)."""
    if config is None:
        config = load_config(connection_type="salesforce")
    sf_token, sf_instance = get_sf_token(config)
    dc_token, dc_domain = get_dc_token(sf_token, sf_instance)
    return sf_token, sf_instance, dc_token, dc_domain


def sf_headers(sf_token):
    return {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}


def dc_headers(dc_token):
    return {"Authorization": f"Bearer {dc_token}", "Content-Type": "application/json"}


# ── Google Docs / Drive ─────────────────────────────────────────────────────

def get_google_token(config=None) -> str:
    if config is None:
        config = load_config()
    g = config.get("google", {})
    if not g.get("refresh_token"):
        raise RuntimeError(
            "Google credentials not configured. Run /setup and choose 'Add Google Drive output'."
        )
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": g["refresh_token"],
            "client_id": g["client_id"],
            "client_secret": g["client_secret"],
        },
    )
    r.raise_for_status()
    return r.json()["access_token"]


def has_google_config(config=None) -> bool:
    if config is None:
        try:
            config = load_config()
        except RuntimeError:
            return False
    g = config.get("google", {})
    return bool(g.get("client_id") and g.get("client_secret") and g.get("refresh_token"))


# ── Validation ──────────────────────────────────────────────────────────────

def validate_all():
    """Test all connections in the active profile and print a status report."""
    config = load_config()
    tc = config["tableau"]
    results = {}

    print("\nAIO Analytics Builder — Connection Validation")
    print("=" * 50)

    try:
        server, auth_token, site_id = get_tableau_token(config)
        base = tc["server_url"].rstrip("/")
        r = requests.get(
            f"{base}/api/-/pulse/definitions?page_size=1",
            headers=tableau_headers(auth_token),
        )
        r.raise_for_status()
        server.auth.sign_out()
        print(f"  Tableau Cloud (PAT):   OK  — site: {tc['site_name']}")
        print(f"  Tableau Pulse API:     OK  — {r.status_code}")
        results["tableau"] = True
    except Exception as e:
        print(f"  Tableau Cloud:         FAIL — {e}")
        results["tableau"] = False

    try:
        sf_token, sf_instance = get_sf_token(config)
        print(f"  Salesforce OAuth:      OK  — {sf_instance}")
        results["salesforce"] = True
    except Exception as e:
        print(f"  Salesforce OAuth:      FAIL — {e}")
        results["salesforce"] = False

    try:
        sf_token, sf_instance = get_sf_token(config)
        dc_token, dc_domain = get_dc_token(sf_token, sf_instance)
        r = requests.get(
            f"{sf_instance}/services/data/v62.0/ssot/data-lake-objects",
            headers=sf_headers(sf_token),
        )
        print(f"  Data Cloud token:      OK  — domain: {dc_domain}")
        print(f"  Data Cloud API:        {'OK' if r.status_code in (200, 204) else 'FAIL'}  — {r.status_code}")
        results["data_cloud"] = True
    except Exception as e:
        print(f"  Data Cloud:            FAIL — {e}")
        results["data_cloud"] = False

    if has_google_config(config):
        try:
            access_token = get_google_token(config)
            r = requests.get(
                "https://www.googleapis.com/drive/v3/about?fields=user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            r.raise_for_status()
            email = r.json().get("user", {}).get("emailAddress", "?")
            print(f"  Google Drive:          OK  — {email}")
            results["google"] = True
        except Exception as e:
            print(f"  Google Drive:          FAIL — {e}")
            results["google"] = False
    else:
        print(f"  Google Drive:          not configured (optional)")

    print("=" * 50)
    all_ok = all(results.values())
    print(f"  Overall: {'ALL SYSTEMS GO' if all_ok else 'ISSUES FOUND — see above'}\n")
    return all_ok


if __name__ == "__main__":
    import sys as _sys
    if _sys.argv[1:2] == ["token"]:
        # Print AIO's own Salesforce token (refreshed if needed) for manual API
        # calls. `sf org display` hides the CLI's token, and the CLI session
        # isn't AIO's: AIO keeps its token in config.json `_token_cache`.
        # Usage: python connections.py token [profile_key]
        _token, _instance = get_sf_token(profile_key=_sys.argv[2] if len(_sys.argv) > 2 else None)
        print(f"SF_INSTANCE={_instance}")
        print(f"SF_TOKEN={_token}")
    else:
        validate_all()
