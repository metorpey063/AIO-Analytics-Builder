"""
Salesforce OAuth browser flow for AIO Analytics Builder.
Opens a browser, catches the auth code on localhost:8080/callback,
exchanges it for tokens, and returns the refresh token.
"""

import http.server
import json
import os
import threading
import urllib.parse
import webbrowser
from urllib.parse import urlencode

CALLBACK_PORT = 8080
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"

_auth_code = None
_auth_error = None
_server_ready = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code, _auth_error
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _auth_code = params["code"][0]
            message = "Authorization successful! You can close this tab and return to the terminal."
        elif "error" in params:
            _auth_error = params.get("error_description", params.get("error", ["Unknown error"]))[0]
            message = f"Authorization failed: {_auth_error}"
        else:
            message = "Unexpected callback. Return to terminal."

        body = f"""<!DOCTYPE html>
<html><head><title>AIO Analytics Builder</title>
<style>body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f4f6f8}}
.box{{text-align:center;padding:40px;background:white;border-radius:12px;box-shadow:0 2px 16px rgba(0,0,0,.1);max-width:400px}}</style>
</head><body><div class="box"><h2>AIO Analytics Builder</h2><p>{message}</p></div></body></html>""".encode()

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # suppress default request logging


def run_oauth_flow(client_id: str, sf_login_url: str = "https://login.salesforce.com") -> dict:
    """
    Runs the full browser-based OAuth flow.
    Returns a dict with access_token, refresh_token, instance_url.
    Raises RuntimeError on failure.
    """
    global _auth_code, _auth_error
    _auth_code = None
    _auth_error = None

    import requests

    # Start local callback server
    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # Build authorization URL
    scopes = "api sfap_api cdp_query_api cdp_ingest_api refresh_token"
    auth_params = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": scopes,
    })
    auth_url = f"{sf_login_url}/services/oauth2/authorize?{auth_params}"

    print(f"\n  Opening browser for Salesforce authorization...")
    print(f"  If it doesn't open automatically, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    print("  Waiting for authorization (60s timeout)...")
    timeout = 60
    import time
    elapsed = 0
    while _auth_code is None and _auth_error is None and elapsed < timeout:
        time.sleep(0.5)
        elapsed += 0.5

    server.shutdown()

    if _auth_error:
        raise RuntimeError(f"Salesforce authorization failed: {_auth_error}")
    if _auth_code is None:
        raise RuntimeError("Timed out waiting for Salesforce authorization. Check your browser.")

    return _auth_code


def exchange_code_for_tokens(auth_code: str, client_id: str, client_secret: str,
                              sf_login_url: str = "https://login.salesforce.com") -> dict:
    """Exchange auth code for access + refresh tokens."""
    import requests
    r = requests.post(
        f"{sf_login_url}/services/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
        },
    )
    if r.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({r.status_code}): {r.text}")
    return r.json()


def get_refresh_token(client_id: str, client_secret: str,
                       sf_login_url: str = "https://login.salesforce.com") -> dict:
    """
    Full OAuth flow: open browser → catch code → exchange for tokens.
    Returns the full token response dict (contains access_token, refresh_token, instance_url).
    """
    auth_code = run_oauth_flow(client_id, sf_login_url)
    tokens = exchange_code_for_tokens(auth_code, client_id, client_secret, sf_login_url)
    return tokens


if __name__ == "__main__":
    # Quick test — reads client_id/secret from config.json if available
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
        sf = config.get("salesforce", {})
        client_id = sf.get("client_id", "")
        client_secret = sf.get("client_secret", "")
        sf_login_url = sf.get("sf_login_url", "https://login.salesforce.com")
        if client_id:
            tokens = get_refresh_token(client_id, client_secret, sf_login_url)
            print("Refresh token:", tokens.get("refresh_token", "")[:40], "...")
        else:
            print("No client_id in config.json — run /setup first")
    else:
        print("No config.json found — run /setup first")
