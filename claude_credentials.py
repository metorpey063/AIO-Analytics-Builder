"""
claude_credentials.py — find the Claude credentials for AIO's own Claude calls
(Web UI chat, Web UI story generation, revintel drafting).

The Salesforce Claude Code rollout writes the Bedrock gateway URL, auth token and
corporate CA bundle into ~/.claude/settings.json under "env". Reading them there means
users never copy `echo $ANTHROPIC_AUTH_TOKEN` into the Web UI, and AIO follows the token
if the rollout changes it.

Order (first match wins):
  1. Environment variables (the server was started inside a Claude Code session)
  2. Claude Code settings files ("env": ANTHROPIC_BEDROCK_BASE_URL + ANTHROPIC_AUTH_TOKEN,
     or ANTHROPIC_API_KEY)
  3. config.json "bedrock" (pasted gateway token)
  4. ANTHROPIC_API_KEY environment variable
  5. config.json "anthropic.api_key" (pasted key or `claude setup-token` token)
If config.json has "ai_preference": "saved" (the user chose "Use a different key"),
3 and 5 move ahead of everything else.

Returned dicts:
  {"mode": "bedrock_gateway", "base_url", "token", "ca_bundle", "source"}
  {"mode": "anthropic_sdk", "api_key", "source"}
"""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

# Claude Code's own precedence: user settings < project settings < local project settings
SETTINGS_FILES = [
    Path.home() / ".claude" / "settings.json",
    Path.home() / ".claude" / "settings.local.json",
    ROOT / ".claude" / "settings.json",
    ROOT / ".claude" / "settings.local.json",
]

SOURCE_LABELS = {
    "claude_code_session": "your Claude Code session",
    "claude_code_settings": "your Claude Code settings",
    "saved_gateway": "the gateway token saved in AIO",
    "env_api_key": "the ANTHROPIC_API_KEY environment variable",
    "saved_api_key": "the API key saved in AIO",
}


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def claude_code_env():
    """Merged "env" block from Claude Code's settings files."""
    env = {}
    for f in SETTINGS_FILES:
        env.update(_read_json(f).get("env") or {})
    return env


def _gateway(url, token, ca, source):
    if url and token:
        return {"mode": "bedrock_gateway", "base_url": url.rstrip("/"), "token": token,
                "ca_bundle": ca or True, "source": source}
    return None


def _api_key(key, source):
    return {"mode": "anthropic_sdk", "api_key": key, "source": source} if key else None


def resolve(full_config=None):
    """Return the credentials AIO should use, or None if nothing is configured."""
    full = full_config if full_config is not None else _read_json(CONFIG_PATH)
    cc = claude_code_env()
    saved_bedrock = full.get("bedrock") or {}
    # A pasted gateway token has no CA bundle; borrow Claude Code's (the corporate proxy needs it)
    saved_ca = saved_bedrock.get("ca_bundle") or os.environ.get("NODE_EXTRA_CA_CERTS") or cc.get("NODE_EXTRA_CA_CERTS")

    candidates = {
        "claude_code_session": lambda: _gateway(os.environ.get("ANTHROPIC_BEDROCK_BASE_URL"),
                                                os.environ.get("ANTHROPIC_AUTH_TOKEN"),
                                                os.environ.get("NODE_EXTRA_CA_CERTS"), "claude_code_session"),
        "claude_code_settings": lambda: (_gateway(cc.get("ANTHROPIC_BEDROCK_BASE_URL"), cc.get("ANTHROPIC_AUTH_TOKEN"),
                                                  cc.get("NODE_EXTRA_CA_CERTS"), "claude_code_settings")
                                         or _api_key(cc.get("ANTHROPIC_API_KEY"), "claude_code_settings")),
        "saved_gateway": lambda: _gateway(saved_bedrock.get("base_url"), saved_bedrock.get("auth_token"),
                                          saved_ca, "saved_gateway"),
        "env_api_key": lambda: _api_key(os.environ.get("ANTHROPIC_API_KEY"), "env_api_key"),
        "saved_api_key": lambda: _api_key((full.get("anthropic") or {}).get("api_key"), "saved_api_key"),
    }
    order = list(candidates)
    if full.get("ai_preference") == "saved":
        order = ["saved_gateway", "saved_api_key"] + [k for k in order if k not in ("saved_gateway", "saved_api_key")]
    for k in order:
        cred = candidates[k]()
        if cred:
            return cred
    return None


def claude_code_available():
    """True if Claude Code's session or settings hold usable credentials."""
    cc = claude_code_env()
    return bool((os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") and os.environ.get("ANTHROPIC_AUTH_TOKEN"))
                or (cc.get("ANTHROPIC_BEDROCK_BASE_URL") and cc.get("ANTHROPIC_AUTH_TOKEN"))
                or cc.get("ANTHROPIC_API_KEY"))


def describe(cred):
    """Secret-free description for the UI."""
    out = {"available": bool(cred), "claude_code_available": claude_code_available()}
    if cred:
        out.update({"source": cred["source"],
                    "kind": "Salesforce gateway" if cred["mode"] == "bedrock_gateway" else "Anthropic API",
                    "source_label": SOURCE_LABELS.get(cred["source"], cred["source"]),
                    "auto": cred["source"].startswith("claude_code")})
    return out


def test(cred, model="claude-haiku-4-5-20251001"):
    """Send one tiny request. Returns (ok, message)."""
    import requests
    msg = [{"role": "user", "content": "Reply with OK."}]
    try:
        if cred["mode"] == "bedrock_gateway":
            r = requests.post(f"{cred['base_url']}/model/{model}/invoke",
                              headers={"x-api-key": cred["token"], "Content-Type": "application/json"},
                              json={"anthropic_version": "bedrock-2023-05-31", "max_tokens": 5, "messages": msg},
                              verify=cred["ca_bundle"], timeout=30)
        else:
            key = cred["api_key"]
            auth = {"Authorization": f"Bearer {key}"} if key.startswith("sk-ant-oat") else {"x-api-key": key}
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers={**auth, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                              json={"model": model, "max_tokens": 5, "messages": msg}, timeout=30)
    except requests.exceptions.SSLError:
        return False, "SSL error reaching the gateway — the corporate CA bundle is missing or out of date."
    except requests.exceptions.RequestException as e:
        return False, f"Couldn't reach Claude: {str(e)[:200]}"
    if r.status_code == 200:
        return True, "Claude responded."
    if r.status_code in (401, 403):
        if cred["source"].startswith("claude_code"):
            return False, ("Your Claude Code credentials were found, but Claude rejected them. "
                           "Restart Claude Code, or reinstall it from the rollout, then test again.")
        return False, "Claude rejected this key — check it and save it again."
    return False, f"Claude returned {r.status_code}: {r.text[:200]}"


if __name__ == "__main__":
    c = resolve()
    print(json.dumps(describe(c), indent=2))
    if c:
        print(test(c))
