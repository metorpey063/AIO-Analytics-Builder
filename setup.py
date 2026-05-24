"""
Analytics Builder setup wizard.
Called by the /setup slash command — Claude reads this file and follows the steps.
Can also be run directly: python3 setup.py
"""

import json
import os
import sys
import requests

from connections import (
    load_full_config,
    save_full_config,
    save_profile,
    set_active_profile,
    delete_profile,
    list_profiles,
    get_profile,
    make_profile_key,
    _EMPTY_PROFILE,
)

import copy


# ── Profile helpers ────────────────────────────────────────────────────────────

def is_section_configured(section: str, profile: dict) -> bool:
    s = profile.get(section, {})
    if section == "tableau":
        return bool(s.get("server_url") and s.get("site_name") and s.get("pat_secret"))
    if section == "salesforce":
        return bool(s.get("client_id") and s.get("refresh_token") and s.get("data_cloud_domain"))
    if section == "google":
        return bool(s.get("client_id") and s.get("client_secret") and s.get("refresh_token"))
    return False


def print_profiles(profiles: list[dict]):
    for i, p in enumerate(profiles, 1):
        active_marker = " ← active" if p["active"] else ""
        print(f"    {i}  {p['label']}  [{p['capabilities']}]{active_marker}")


# ── Profile selection (first question in wizard) ───────────────────────────────

def select_profile(full_config: dict) -> tuple[str, dict]:
    """
    Ask the user whether to use a saved profile or create a new one.
    Returns (profile_key, profile_dict) — the profile_dict is a mutable working copy.
    """
    profiles = list_profiles(full_config)

    print("\n" + "=" * 60)
    print("  Analytics Builder — Connection Manager")
    print("=" * 60)

    if not profiles:
        print("\n  No saved connections found. Let's set one up.\n")
        return _create_new_profile(full_config)

    print("\n  Saved connections:\n")
    print_profiles(profiles)
    print(f"\n    {len(profiles) + 1}  Set up a new connection")
    print()

    choice = input(f"  Choose a connection (1–{len(profiles) + 1}): ").strip()

    try:
        idx = int(choice) - 1
    except ValueError:
        print("  Invalid choice, try again.")
        return select_profile(full_config)

    if idx == len(profiles):
        return _create_new_profile(full_config)

    if 0 <= idx < len(profiles):
        selected = profiles[idx]
        key = selected["key"]
        set_active_profile(full_config, key)
        print(f"\n  Using: {selected['label']}")
        profile = get_profile(full_config, key)

        # Offer to manage this profile
        action = input("  (U)se as-is, (R)econfigure, or (D)elete? [U]: ").strip().lower()
        if action in ("d", "delete"):
            confirm = input(f"  Delete '{selected['label']}'? This cannot be undone. [y/N]: ").strip().lower()
            if confirm in ("y", "yes"):
                delete_profile(full_config, key)
                print(f"  Deleted '{selected['label']}'.")
                return select_profile(full_config)
            return select_profile(full_config)
        if action in ("r", "reconfigure"):
            return key, profile
        # Use as-is — skip straight to validation
        return key, None  # None signals: skip setup steps, go straight to validate

    print("  Invalid choice, try again.")
    return select_profile(full_config)


def _create_new_profile(full_config: dict) -> tuple[str, dict]:
    label = input("  Name this connection (e.g. 'Engine Demo Org', 'Acme Sandbox'): ").strip()
    if not label:
        label = "My Org"
    key = make_profile_key(label)

    # Avoid key collision
    existing_keys = set(full_config.get("profiles", {}).keys())
    base_key = key
    counter = 2
    while key in existing_keys:
        key = f"{base_key}_{counter}"
        counter += 1

    profile = copy.deepcopy(_EMPTY_PROFILE)
    profile["label"] = label
    return key, profile


# ── Connection steps ───────────────────────────────────────────────────────────

def test_tableau(profile: dict) -> bool:
    try:
        import tableauserverclient as TSC
        tc = profile["tableau"]
        auth = TSC.PersonalAccessTokenAuth(tc["pat_name"], tc["pat_secret"], site_id=tc["site_name"])
        server = TSC.Server(tc["server_url"], use_server_version=True)
        server.auth.sign_in(auth)
        r = requests.get(
            f"{tc['server_url'].rstrip('/')}/api/-/pulse/definitions?page_size=1",
            headers={"x-tableau-auth": server.auth_token, "Accept": "application/json"},
        )
        server.auth.sign_out()
        return r.status_code == 200
    except Exception as e:
        print(f"    Error: {e}")
        return False


def setup_tableau(profile: dict) -> dict:
    print("\n" + "=" * 60)
    print("  Tableau Cloud Connection")
    print("=" * 60)
    print("""
  You'll need a Personal Access Token (PAT) from Tableau Cloud.

  To create one:
    1. Sign in to your Tableau Cloud site
    2. Click your avatar (top right) → Account Settings
    3. Scroll to "Personal Access Tokens"
    4. Click "Create new token", give it a name (e.g. "Claude Code")
    5. Copy the token secret — it's only shown once
""")

    server_url = input("  Tableau Cloud URL (e.g. https://us-east-1.online.tableau.com/): ").strip()
    if not server_url.startswith("http"):
        server_url = "https://" + server_url
    if not server_url.endswith("/"):
        server_url += "/"

    site_name = input("  Site name (the slug in your URL, e.g. 'mycompanysite'): ").strip()
    pat_secret = input("  PAT secret: ").strip()

    profile["tableau"].update({
        "server_url": server_url,
        "site_name": site_name,
        "pat_secret": pat_secret,
    })

    print("\n  Testing connection...", end="", flush=True)
    if test_tableau(profile):
        print(" OK")
        return profile
    else:
        print(" FAILED")
        print("  Check your URL, site name, and PAT secret and try again.")
        sys.exit(1)


def test_salesforce(profile: dict) -> tuple[bool, str, str]:
    """Returns (ok, sf_instance, dc_domain)."""
    try:
        sf = profile["salesforce"]
        r = requests.post(
            f"{sf['sf_login_url']}/services/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": sf["refresh_token"],
                "client_id": sf["client_id"],
                "client_secret": sf["client_secret"],
            },
        )
        if r.status_code != 200:
            print(f"    SF token error: {r.text}")
            return False, "", ""
        sf_token = r.json()["access_token"]
        sf_instance = r.json()["instance_url"]

        r2 = requests.post(
            f"{sf_instance}/services/a360/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "urn:salesforce:grant-type:external:cdp",
                "subject_token": sf_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            },
        )
        if r2.status_code != 200:
            print(f"    DC token error: {r2.text}")
            return False, sf_instance, ""
        dc_domain = r2.json()["instance_url"]
        return True, sf_instance, dc_domain
    except Exception as e:
        print(f"    Error: {e}")
        return False, "", ""


def setup_salesforce(profile: dict) -> dict:
    print("\n" + "=" * 60)
    print("  Salesforce Connected App")
    print("=" * 60)
    print("""
  You need a Connected App (or External Client App) in your
  Salesforce org with the correct OAuth scopes.

  ── Creating a Connected App ───────────────────────────────
  1. In Salesforce Setup, search for "App Manager"
  2. Click "New Connected App" (top right)
  3. Fill in:
       Connected App Name:  Analytics Builder
       API Name:            Analytics_Builder  (auto-fills)
       Contact Email:       your email
  4. Check "Enable OAuth Settings"
  5. Callback URL:  http://localhost:8080/callback
  6. Selected OAuth Scopes — add ALL of these:
       • Access and manage your data (api)
       • Access Tableau Analytics APIs (sfap_api)
       • Access Data Cloud Ingestion API resources (cdp_ingest_api)
       • Access Data Cloud Query API resources (cdp_query_api)
       • Perform requests at any time (refresh_token, offline_access)
  7. Uncheck "Require Proof Key for Code Exchange (PKCE)"
  8. Click Save — wait 2-10 minutes for Salesforce to activate it

  ── Getting your credentials ──────────────────────────────
  After saving, click "Manage Consumer Details" (you may need
  to verify your identity). Copy the Consumer Key and Secret.

""")

    org_type = input("  Is this a sandbox org? [y/N]: ").strip().lower()
    login_url = "https://test.salesforce.com" if org_type in ("y", "yes") else "https://login.salesforce.com"
    print(f"  Using login URL: {login_url}")

    client_id = input("\n  Consumer Key (Client ID): ").strip()
    client_secret = input("  Consumer Secret (Client Secret): ").strip()

    profile["salesforce"].update({
        "sf_login_url": login_url,
        "client_id": client_id,
        "client_secret": client_secret,
    })

    print("\n  Opening browser for Salesforce authorization...")
    print("  Log in and click Allow, then return to this terminal.\n")

    from oauth_flow import get_refresh_token
    try:
        tokens = get_refresh_token(client_id, client_secret, login_url)
    except RuntimeError as e:
        print(f"\n  Authorization failed: {e}")
        sys.exit(1)

    profile["salesforce"]["refresh_token"] = tokens["refresh_token"]
    sf_instance = tokens["instance_url"]
    print(f"\n  Authorized. Instance: {sf_instance}")

    print("  Testing Data Cloud connection...", end="", flush=True)
    ok, _, dc_domain = test_salesforce(profile)
    if ok:
        profile["salesforce"]["data_cloud_domain"] = dc_domain
        print(f" OK\n  DC domain: {dc_domain}")
        return profile
    else:
        print(" FAILED")
        print("  Data Cloud token exchange failed. Ensure Data Cloud is enabled in your org.")
        sys.exit(1)


def discover_connector(sf_token: str, sf_instance: str, connector_name: str) -> dict | None:
    r = requests.get(
        f"{sf_instance}/services/data/v62.0/ssot/connections",
        headers={"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"},
        params={"connectorType": "IngestApi", "limit": 100},  # IngestApi casing is required
    )
    if r.status_code != 200:
        return None
    connections = r.json().get("connections", [])
    for c in connections:
        label = c.get("label", "").lower()
        name = c.get("name", "").lower()
        if connector_name.lower() in label or connector_name.lower() in name:
            return c
    return connections[0] if connections else None


def create_connector(sf_token: str, sf_instance: str, connector_name: str) -> dict:
    r = requests.post(
        f"{sf_instance}/services/data/v62.0/ssot/connections",
        headers={"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"},
        json={"connectorType": "INGEST_API", "label": connector_name, "name": connector_name},
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create connector: {r.status_code} {r.text}")
    return r.json()


def setup_connector(profile: dict) -> dict:
    print("\n" + "=" * 60)
    print("  Data Cloud Ingest Connector")
    print("=" * 60)
    print("""
  The demo builder pushes synthetic data into Salesforce Data
  Cloud using an Ingest API connector. We'll look for an
  existing one first, then create one if needed.
""")

    sf = profile["salesforce"]
    r = requests.post(
        f"{sf['sf_login_url']}/services/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": sf["refresh_token"],
            "client_id": sf["client_id"],
            "client_secret": sf["client_secret"],
        },
    )
    sf_token = r.json()["access_token"]
    sf_instance = r.json()["instance_url"]

    connector_name = sf.get("ingestion_connector_name", "analytics_builder_demo")

    print(f"  Looking for Ingest API connector...", end="", flush=True)
    connector = discover_connector(sf_token, sf_instance, connector_name)

    if connector:
        found_name = connector.get("label") or connector.get("name", "")
        found_id = connector.get("id", connector.get("developerName", ""))
        print(f" Found: '{found_name}'")
        use_it = input("  Use this connector? [Y/n]: ").strip().lower()
        if use_it in ("", "y", "yes"):
            profile["salesforce"]["connector_sf_id"] = found_id
            profile["salesforce"]["connector_uuid_name"] = connector.get("name", "")
            profile["salesforce"]["ingestion_connector_name"] = found_name
            return profile

    print(" Not found — creating new connector...")
    custom_name = input(f"  Connector name [{connector_name}]: ").strip() or connector_name

    try:
        new_connector = create_connector(sf_token, sf_instance, custom_name)
        conn_id = new_connector.get("id", new_connector.get("developerName", ""))
        print(f"  Created: {custom_name} (ID: {conn_id})")
        profile["salesforce"]["ingestion_connector_name"] = custom_name
        profile["salesforce"]["connector_sf_id"] = conn_id
        profile["salesforce"]["connector_uuid_name"] = new_connector.get("name", "")
        return profile
    except RuntimeError as e:
        print(f"\n  Could not create connector: {e}")
        print("  Create one manually in Data Cloud > Ingest API and re-run /setup.")
        return profile


def setup_google(profile: dict) -> dict:
    print("\n" + "=" * 60)
    print("  Google Drive / Docs Connection  (optional)")
    print("=" * 60)
    print("""
  This lets /build-demo output walkthrough documents directly
  as Google Docs in your Drive, instead of (or in addition to)
  a local .docx file.

  You need a Google Cloud project with the Google Docs API and
  Google Drive API enabled, and an OAuth 2.0 Desktop Client ID.

  ── Quick setup ────────────────────────────────────────────
  1. Go to console.cloud.google.com
  2. Create a project (or use an existing one)
  3. Enable "Google Docs API" and "Google Drive API"
  4. Go to APIs & Services → Credentials
  5. Click "Create Credentials" → OAuth client ID
  6. Application type: Desktop app
  7. Download the JSON — you need the client_id and client_secret
  8. Under "OAuth consent screen", add your Google account as a
     Test User (if the app is in Testing mode)
""")

    client_id = input("  Google OAuth Client ID: ").strip()
    client_secret = input("  Google OAuth Client Secret: ").strip()

    if not client_id or not client_secret:
        print("  Skipping Google setup — no credentials entered.")
        return profile

    if "google" not in profile:
        profile["google"] = {}
    profile["google"].update({"client_id": client_id, "client_secret": client_secret, "refresh_token": ""})

    print("\n  Opening browser for Google authorization...")
    print("  Sign in and click Allow, then return to this terminal.\n")

    from google_auth import get_google_refresh_token
    try:
        tokens = get_google_refresh_token(client_id, client_secret)
    except RuntimeError as e:
        print(f"\n  Authorization failed: {e}")
        return profile

    profile["google"]["refresh_token"] = tokens["refresh_token"]
    print("  Google Drive authorized.")
    return profile


def test_google(profile: dict) -> bool:
    try:
        import requests as _req
        g = profile.get("google", {})
        r = _req.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": g["refresh_token"],
                "client_id": g["client_id"],
                "client_secret": g["client_secret"],
            },
        )
        if r.status_code != 200:
            return False
        access_token = r.json()["access_token"]
        r2 = _req.get(
            "https://www.googleapis.com/drive/v3/about?fields=user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return r2.status_code == 200
    except Exception as e:
        print(f"    Error: {e}")
        return False


# ── Mode selection ─────────────────────────────────────────────────────────────

MODES = {
    "1": ("tableau_pulse", "Tableau Cloud + Pulse",               ["tableau"]),
    "2": ("tableau_next",  "Tableau Next (Salesforce Data Cloud)", ["salesforce", "connector"]),
    "3": ("both",          "Both",                                 ["tableau", "salesforce", "connector"]),
}


def select_mode() -> list[str]:
    print("""
  Which solution do you want to configure?

    1  Tableau Cloud + Pulse
         Publish Pulse metrics to Tableau Cloud.
         Requires a Personal Access Token (PAT).

    2  Tableau Next  (Salesforce Data Cloud)
         Build Tableau Next demos via Salesforce Data Cloud.
         Requires a Salesforce Connected App and OAuth authorization.

    3  Both
         Configure Tableau Cloud and Salesforce/Data Cloud.
         Needed to use all output modes in /build-demo.
""")
    choice = input("  Enter 1, 2, or 3: ").strip()
    if choice not in MODES:
        print("  Invalid choice. Please enter 1, 2, or 3.")
        return select_mode()
    _, label, steps = MODES[choice]
    print(f"\n  Got it — configuring: {label}\n")

    # Always offer Google Drive as an optional add-on
    google = input("  Also configure Google Drive output? (optional) [y/N]: ").strip().lower()
    if google in ("y", "yes"):
        steps = steps + ["google"]

    return steps


# ── Final validation ───────────────────────────────────────────────────────────

def validate_profile(profile: dict, steps: list[str]):
    print("\n" + "=" * 60)
    print("  VALIDATION — Testing configured connections")
    print("=" * 60)

    all_ok = True
    missing = []

    if "tableau" in steps:
        ok = test_tableau(profile)
        print(f"  Tableau Cloud + Pulse API:  {'OK' if ok else 'FAIL'}")
        if not ok:
            all_ok = False
            missing.append("Tableau Cloud")

    if "salesforce" in steps:
        ok_sf, sf_instance, dc_domain = test_salesforce(profile)
        print(f"  Salesforce OAuth:           {'OK  — ' + sf_instance if ok_sf else 'FAIL'}")
        print(f"  Data Cloud:                 {'OK  — ' + dc_domain if ok_sf else 'FAIL'}")
        if not ok_sf:
            all_ok = False
            missing.append("Salesforce / Data Cloud")

    if "connector" in steps:
        connector_id = profile["salesforce"].get("connector_sf_id", "")
        print(f"  DC Ingest Connector:        {'OK  — ' + connector_id if connector_id else 'NOT SET'}")
        if not connector_id:
            all_ok = False
            missing.append("DC Ingest Connector")

    if "google" in steps:
        ok_g = test_google(profile)
        print(f"  Google Drive:               {'OK' if ok_g else 'FAIL'}")
        if not ok_g:
            all_ok = False
            missing.append("Google Drive")

    print("=" * 60)
    if all_ok:
        print("\n  ALL SYSTEMS GO\n  You're ready to build demos. Run /build-demo to get started.\n")
    else:
        print(f"\n  Incomplete: {', '.join(missing)}")
        print("  Re-run /setup to fix the missing items.\n")


# ── Main entry point ───────────────────────────────────────────────────────────

def run_setup():
    print("\n" + "=" * 60)
    print("  Analytics Builder — Setup Wizard")
    print("=" * 60)

    full_config = load_full_config()
    profile_key, profile = select_profile(full_config)

    # None profile means "use as-is" — just validate
    if profile is None:
        profile = full_config["profiles"][profile_key]
        steps = []
        if is_section_configured("tableau", profile):
            steps.append("tableau")
        if is_section_configured("salesforce", profile):
            steps += ["salesforce", "connector"]
        validate_profile(profile, steps)
        return

    steps = select_mode()

    if "tableau" in steps:
        if is_section_configured("tableau", profile):
            reconfig = input("  Tableau already configured. Reconfigure? [y/N]: ").strip().lower()
            if reconfig in ("y", "yes"):
                profile = setup_tableau(profile)
        else:
            profile = setup_tableau(profile)

    if "salesforce" in steps:
        if is_section_configured("salesforce", profile):
            reconfig = input("\n  Salesforce already configured. Reconfigure? [y/N]: ").strip().lower()
            if reconfig in ("y", "yes"):
                profile = setup_salesforce(profile)
        else:
            profile = setup_salesforce(profile)

    if "connector" in steps:
        connector_id = profile["salesforce"].get("connector_sf_id", "")
        if connector_id:
            reconfig = input(f"\n  Connector already configured (ID: {connector_id}). Reconfigure? [y/N]: ").strip().lower()
            if reconfig in ("y", "yes"):
                profile = setup_connector(profile)
        else:
            profile = setup_connector(profile)

    if "google" in steps:
        if is_section_configured("google", profile):
            reconfig = input("\n  Google Drive already configured. Reconfigure? [y/N]: ").strip().lower()
            if reconfig in ("y", "yes"):
                profile = setup_google(profile)
        else:
            profile = setup_google(profile)

    # Save and activate
    save_profile(full_config, profile_key, profile)
    set_active_profile(full_config, profile_key)
    print(f"\n  Profile '{profile.get('label', profile_key)}' saved and set as active.")

    validate_profile(profile, steps)


if __name__ == "__main__":
    run_setup()
