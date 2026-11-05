"""Claude calls for revintel (draft and research). Needs no demo config, so research can run
before an org or folder is chosen.

Credentials, in the web UI's order: Bedrock gateway (ANTHROPIC_BEDROCK_BASE_URL +
ANTHROPIC_AUTH_TOKEN, or config.json "bedrock"), then an Anthropic API key or OAuth token
(ANTHROPIC_API_KEY or config.json "anthropic.api_key").
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = "claude-opus-5-5"
GATEWAY_MODEL = "us.anthropic.claude-opus-5-5"   # Bedrock gateway model ID for the same model


def credentials():
    try:
        aio = json.load(open(os.path.join(ROOT, "config.json")))
    except (OSError, json.JSONDecodeError):
        aio = {}
    url = os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") or (aio.get("bedrock") or {}).get("base_url")
    tok = os.environ.get("ANTHROPIC_AUTH_TOKEN") if os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") \
        else (aio.get("bedrock") or {}).get("auth_token")
    if url and tok:
        return {"mode": "gateway", "base_url": url.rstrip("/"), "token": tok,
                "ca_bundle": os.environ.get("NODE_EXTRA_CA_CERTS") or (aio.get("bedrock") or {}).get("ca_bundle") or True}
    key = os.environ.get("ANTHROPIC_API_KEY") or (aio.get("anthropic") or {}).get("api_key")
    if key:
        return {"mode": "sdk", "key": key}
    raise SystemExit("No Claude credentials: set ANTHROPIC_API_KEY, add an Anthropic key in Setup, "
                     "or run inside a Claude Code session with the Bedrock gateway.")


def call(system, user, effort="high", max_tokens=64000):
    """One Claude call; returns the response text."""
    cred = credentials()
    if cred["mode"] == "gateway":
        # The internal Bedrock gateway speaks Bedrock's /invoke format with an x-api-key header, which the
        # SDK's Bedrock client (SigV4) can't send — same raw call the web UI's chat uses for this gateway.
        import requests
        r = requests.post(f"{cred['base_url']}/model/{GATEWAY_MODEL}/invoke",
                          headers={"x-api-key": cred["token"], "Content-Type": "application/json"},
                          json={"anthropic_version": "bedrock-2023-05-31", "max_tokens": max_tokens,
                                "thinking": {"type": "adaptive"}, "output_config": {"effort": effort},
                                "system": system, "messages": [{"role": "user", "content": user}]},
                          verify=cred["ca_bundle"], timeout=900)
        if r.status_code != 200:
            raise SystemExit(f"Claude call failed ({r.status_code}): {r.text[:500]}")
        body = r.json()
        if body.get("stop_reason") == "refusal":
            raise SystemExit("Claude declined this request — rephrase the answers and try again.")
        if body.get("stop_reason") == "max_tokens":
            raise SystemExit("Claude's reply was cut off (max tokens) — simplify the request and try again.")
        return "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")

    import anthropic
    key = cred["key"]
    client = anthropic.Anthropic(auth_token=key) if key.startswith("sk-ant-oat") else anthropic.Anthropic(api_key=key)
    try:
        # server-side refusal fallback: a declined request is retried on a fallback model inside the same call
        with client.beta.messages.stream(model=MODEL, max_tokens=max_tokens, thinking={"type": "adaptive"},
                                         output_config={"effort": effort}, system=system,
                                         messages=[{"role": "user", "content": user}],
                                         betas=["server-side-fallback-2026-07-01"], fallbacks="default") as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError:
        raise SystemExit("Claude rejected the credentials — check the Anthropic key in Setup.")
    except anthropic.RateLimitError:
        raise SystemExit("Claude rate limit — wait a minute and try again.")
    except anthropic.APIStatusError as e:
        raise SystemExit(f"Claude API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise SystemExit("Couldn't reach the Claude API — check the network.")
    if msg.stop_reason == "refusal":
        raise SystemExit("Claude declined this request — rephrase the answers and try again.")
    if msg.stop_reason == "max_tokens":
        raise SystemExit("Claude's reply was cut off (max tokens) — simplify the request and try again.")
    return "".join(b.text for b in msg.content if b.type == "text")


def extract(text, raw_path=None):
    if raw_path:
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)
        open(raw_path, "w").write(text)
    m = re.search(r"```json\s*(\{.*\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    return m.group(1)


def ask_json(system, user, raw_path=None, effort="high", max_tokens=64000):
    """Call Claude and parse its JSON; on a syntax error, send back the error and the broken JSON once."""
    raw = extract(call(system, user, effort, max_tokens), raw_path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  reply wasn't valid JSON ({e.msg} at line {e.lineno}) — asking Claude to correct it…", flush=True)
        snippet = raw[max(0, e.pos - 300): e.pos + 300]
        fix = (f"This JSON failed to parse: {e.msg} at line {e.lineno} column {e.colno}.\n"
               f"Context around the error:\n{snippet}\n\nReturn the complete corrected JSON object, same content, "
               f"inside a ```json fence and nothing else.\n\n```json\n{raw}\n```")
        raw = extract(call("You fix JSON syntax without changing content.", fix, "low", max_tokens), raw_path)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e2:
            where = f"; raw reply in {raw_path}" if raw_path else ""
            raise SystemExit(f"Claude's reply still isn't valid JSON ({e2.msg} at line {e2.lineno}){where} — try again.")
