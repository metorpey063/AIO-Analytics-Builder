"""
Core connection module for AIO Analytics Builder.
Handles both Tableau Cloud (PAT) and Salesforce/Data Cloud (OAuth) auth.
Supports multiple named profiles so SEs can switch between orgs.
"""

import json
import os
import requests
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
}


# ── File-level helpers ─────────────────────────────────────────────────────────

def load_full_config() -> dict:
    """Load the raw config file. Migrates old flat format to profiles automatically."""
    if not os.path.exists(CONFIG_FILE):
        return {"active_profile": None, "profiles": {}}

    with open(CONFIG_FILE) as f:
        raw = json.load(f)

    # Migrate old flat format (no "profiles" key) to profile structure
    if "profiles" not in raw:
        profile = {
            "label": raw.get("_label", "Default"),
            "tableau": raw.get("tableau", {}),
            "salesforce": raw.get("salesforce", {}),
        }
        migrated = {
            "active_profile": "default",
            "profiles": {"default": profile},
        }
        save_full_config(migrated)
        return migrated

    return raw


def save_full_config(full_config: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(full_config, f, indent=2)


def load_config(profile_key: str = None) -> dict:
    """
    Returns the active profile's {tableau, salesforce} dict.
    This is the main entry point for all auth code — same return shape as before.
    Pass profile_key to load a specific profile instead of the active one.
    """
    full = load_full_config()
    key = profile_key or full.get("active_profile")
    if not key or key not in full.get("profiles", {}):
        raise RuntimeError(
            "No active connection profile found. Run /setup to configure one."
        )
    return full["profiles"][key]


# ── Profile management ─────────────────────────────────────────────────────────

def list_profiles(full_config: dict) -> list[dict]:
    """Returns list of profile summaries for display."""
    active = full_config.get("active_profile")
    result = []
    for key, profile in full_config.get("profiles", {}).items():
        tc = profile.get("tableau", {})
        sf = profile.get("salesforce", {})
        has_tableau = bool(tc.get("pat_secret") and tc.get("site_name"))
        has_sf = bool(sf.get("refresh_token") and sf.get("data_cloud_domain"))
        caps = []
        if has_tableau:
            caps.append("Tableau Cloud")
        if has_sf:
            caps.append("Salesforce/DC")
        result.append({
            "key": key,
            "label": profile.get("label", key),
            "capabilities": ", ".join(caps) if caps else "not configured",
            "active": key == active,
        })
    return result


def get_profile(full_config: dict, key: str) -> dict:
    """Return a profile dict by key, or an empty profile template."""
    import copy
    return copy.deepcopy(full_config.get("profiles", {}).get(key, _EMPTY_PROFILE))


def save_profile(full_config: dict, key: str, profile: dict):
    """Write a profile back to the full config and persist to disk."""
    if "profiles" not in full_config:
        full_config["profiles"] = {}
    full_config["profiles"][key] = profile
    if full_config.get("active_profile") is None:
        full_config["active_profile"] = key
    save_full_config(full_config)


def set_active_profile(full_config: dict, key: str):
    full_config["active_profile"] = key
    save_full_config(full_config)


def delete_profile(full_config: dict, key: str):
    full_config.get("profiles", {}).pop(key, None)
    if full_config.get("active_profile") == key:
        remaining = list(full_config.get("profiles", {}).keys())
        full_config["active_profile"] = remaining[0] if remaining else None
    save_full_config(full_config)


def make_profile_key(label: str) -> str:
    """Turn a human label into a safe dict key."""
    import re
    key = label.lower().strip()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    key = key.strip("_")
    return key or "profile"


# ── Tableau Cloud (Pulse) ──────────────────────────────────────────────────────

def get_tableau_token(config=None):
    """Returns (server, auth_token, site_id) for Tableau Cloud REST API calls."""
    if config is None:
        config = load_config()
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


# ── Salesforce + Data Cloud (Tableau Next) ────────────────────────────────────

def get_sf_token(config=None, profile_key=None):
    """Returns (sf_token, sf_instance) via refresh_token grant.
    Supports PKCE orgs (includes code_verifier if saved in config).
    Handles orgs that reject code_verifier by retrying without it.
    Saves rotated refresh token back to config.json if one is returned."""
    if config is None:
        config = load_config(profile_key)
    sf = config["salesforce"]

    data = {
        "grant_type": "refresh_token",
        "refresh_token": sf["refresh_token"],
        "client_id": sf["client_id"],
    }
    if sf.get("client_secret"):
        data["client_secret"] = sf["client_secret"]

    # Try WITHOUT code_verifier first (works for most orgs).
    # Only add it if the org requires it ("invalid code verifier" error).
    # This order prevents burning the refresh token on orgs that reject it.
    r = requests.post(f"{sf['sf_login_url']}/services/oauth2/token", data=data)

    # If org REQUIRES code_verifier ("invalid code verifier"), retry with it
    if r.status_code == 400 and "invalid code verifier" in r.text.lower() and sf.get("code_verifier"):
        data["code_verifier"] = sf["code_verifier"]
        r = requests.post(f"{sf['sf_login_url']}/services/oauth2/token", data=data)

    r.raise_for_status()
    body = r.json()

    # Handle refresh token rotation: save new token if returned
    new_refresh = body.get("refresh_token")
    full = load_full_config()
    key = profile_key or full.get("active_profile")
    if key and key in full.get("profiles", {}):
        changed = False
        if new_refresh and new_refresh != sf["refresh_token"]:
            full["profiles"][key]["salesforce"]["refresh_token"] = new_refresh
            sf["refresh_token"] = new_refresh
            changed = True
        if changed:
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
        config = load_config()
    sf_token, sf_instance = get_sf_token(config)
    dc_token, dc_domain = get_dc_token(sf_token, sf_instance)
    return sf_token, sf_instance, dc_token, dc_domain


def sf_headers(sf_token):
    return {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}


def dc_headers(dc_token):
    return {"Authorization": f"Bearer {dc_token}", "Content-Type": "application/json"}


# ── Google Docs / Drive ───────────────────────────────────────────────────────

def get_google_token(config=None) -> str:
    """
    Exchange the stored Google refresh token for a fresh access token.
    Returns the access_token string.
    Raises RuntimeError if the google section is missing or unconfigured.
    """
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
    """Returns True if Google credentials are present and non-empty."""
    if config is None:
        try:
            config = load_config()
        except RuntimeError:
            return False
    g = config.get("google", {})
    return bool(g.get("client_id") and g.get("client_secret") and g.get("refresh_token"))


# ── Validation ────────────────────────────────────────────────────────────────

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
    validate_all()
