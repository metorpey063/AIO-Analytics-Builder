"""
Slack setup for /close-loop.

Saves Slack IDs under the active (or chosen) /setup profile's "slack" key, then runs a
read-only check against the org. No Slack token is stored — posts go through
Salesforce's native Slack Flow action using the existing Salesforce connection.

/setup never asks about Slack. /close-loop calls this (non-interactive flags) only when the
user picks Slack as the notify target.

Usage:
  python setup_slack.py [--profile key]                                    # interactive prompts
  python setup_slack.py --channel-id C… --workspace-id T… \\
      [--channel-name demo-alerts] [--app-id A…] [--profile key]           # save without prompts
  python setup_slack.py --show [--profile key]                             # print saved IDs + check
  python setup_slack.py --check [--profile key]                            # check only
"""

import argparse
import json
import sys

from connections import load_full_config, save_profile, get_sf_token, sf_headers

SLACK_KEYS = ("workspace_id", "channel_id", "channel_name", "app_id")

INSTRUCTIONS = """
  Slack alerts for /close-loop  (optional)

  /close-loop posts the demo's insight to Slack via Salesforce's
  native Slack action, so the alert comes from Salesforce itself.

  ── Prerequisites (in the demo org) ─────────────────────────
  1. Setup → Slack → connect the org to a Slack workspace
     (Sales Cloud for Slack / Salesforce for Slack app installed)
  2. Your user has connected their Slack account
  3. Invite the Salesforce app to the target channel

  Find IDs in Slack:
  - Channel ID: channel → View channel details → bottom of the About tab (starts with C)
  - Workspace ID: starts with T — NOT the subdomain in the URL.
    Workspace menu → Settings → About, or the T… segment in app.slack.com/client/T…/…
  - App ID (optional): starts with A. Leave blank unless the check says it's needed.
  Without Slack, /close-loop falls back to a Chatter post.
"""


def _resolve_key(full, profile_key):
    key = profile_key or full.get("active_profile")
    if not key or key not in full.get("profiles", {}):
        raise SystemExit("No connection profile found. Run /setup first.")
    return key


def save(values, profile_key=None):
    """Merge the given Slack IDs into the profile (blank/None values keep what's saved)."""
    full = load_full_config()
    key = _resolve_key(full, profile_key)
    profile = full["profiles"][key]
    slack = dict(profile.get("slack", {}))
    for k in SLACK_KEYS:
        v = (values.get(k) or "").strip()
        if v:
            slack[k] = v.lstrip("#") if k == "channel_name" else v
    profile["slack"] = slack
    save_profile(full, key, profile)
    print(f"  Saved Slack settings to profile '{key}': "
          + ", ".join(f"{k}={slack.get(k, '') or '—'}" for k in SLACK_KEYS))
    return key


def run(profile_key=None):
    full = load_full_config()
    key = _resolve_key(full, profile_key)
    profile = full["profiles"][key]
    current = profile.get("slack", {})
    print(INSTRUCTIONS)
    print(f"  Profile: {profile.get('label', key)}")

    def ask(label, field):
        cur = current.get(field, "")
        return input(f"  {label}{f' [{cur}]' if cur else ''}: ").strip() or cur

    values = {"channel_id": ask("Slack Channel ID (C…)", "channel_id")}
    if not values["channel_id"]:
        print("  Skipping Slack setup — no channel entered.")
        return False
    values["channel_name"] = ask("Channel name (display only, e.g. demo-alerts)", "channel_name")
    values["workspace_id"] = ask("Slack Workspace ID (T…)", "workspace_id")
    values["app_id"] = ask("Slack App ID (A…, optional)", "app_id")
    save(values, key)
    return check(key)


def check(profile_key=None):
    """Read-only org check with plain-language fixes. Returns True if Slack posts will work."""
    from close_loop import preflight, slack_diagnose
    full = load_full_config()
    key = _resolve_key(full, profile_key)
    slack = full["profiles"][key].get("slack", {})
    try:
        token, inst = get_sf_token(profile_key=key)
        h = sf_headers(token)
        diag = slack_diagnose(preflight(inst, h, slack), slack, inst, h)
    except Exception as e:
        print(f"  Slack check error: {e}")
        return False
    print(f"  Slack (native SF action): {'READY' if diag['ready'] else 'NOT READY — Chatter fallback'}")
    for i in diag["issues"]:
        print(f"   ✗ {i['problem']}\n     → {i['fix']}")
    if diag["suggested"]:
        print(f"   Found IDs in an existing Slack Flow: {diag['suggested']}")
    return diag["ready"]


def main():
    ap = argparse.ArgumentParser(description="Configure Slack for /close-loop")
    ap.add_argument("--profile", help="config.json profile key (default: active profile)")
    ap.add_argument("--show", action="store_true", help="print saved Slack settings and run the check")
    ap.add_argument("--check", action="store_true", help="only run the read-only org check")
    for k in SLACK_KEYS:
        ap.add_argument(f"--{k.replace('_', '-')}", dest=k, help=f"save {k} without prompting")
    a = ap.parse_args()
    given = {k: getattr(a, k) for k in SLACK_KEYS if getattr(a, k)}
    if given:
        key = save(given, a.profile)
        sys.exit(0 if check(key) else 2)
    if a.show:
        full = load_full_config()
        key = _resolve_key(full, a.profile)
        print(json.dumps({k: full["profiles"][key].get("slack", {}).get(k, "") for k in SLACK_KEYS}, indent=2))
        check(key)
    elif a.check:
        sys.exit(0 if check(a.profile) else 2)
    else:
        run(a.profile)


if __name__ == "__main__":
    main()
