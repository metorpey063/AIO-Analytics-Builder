"""
Google OAuth2 browser flow for AIO Analytics Builder.
Obtains a refresh token for the Google Docs + Drive APIs.
Called from setup.py when the user chooses to add Google Drive output.

Usage:
    tokens = get_google_refresh_token(client_id, client_secret)
    # returns {"refresh_token": "...", "access_token": "..."}
"""

import json
import os
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from google_auth_oauthlib.flow import Flow

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

REDIRECT_URI = "http://localhost:8081/callback"
PORT = 8081


def get_google_refresh_token(client_id: str, client_secret: str) -> dict:
    """
    Run the OAuth2 Authorization Code flow in a local browser window.
    Returns {"refresh_token": str, "access_token": str}.
    Raises RuntimeError if the flow times out or the user denies access.
    """
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.oauth2session.params["access_type"] = "offline"
    flow.oauth2session.params["prompt"] = "consent"

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    callback_code = [None]
    callback_error = [None]
    server_ready = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # suppress access logs

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                callback_code[0] = params["code"][0]
                self._respond("Authorization successful! You can close this tab.")
            elif "error" in params:
                callback_error[0] = params["error"][0]
                self._respond(f"Authorization failed: {params['error'][0]}")
            else:
                self._respond("Unexpected callback — no code or error in query string.")

        def _respond(self, message: str):
            body = f"<html><body><h2>{message}</h2></body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = HTTPServer(("localhost", PORT), CallbackHandler)
    httpd.timeout = 120

    def serve():
        server_ready.set()
        httpd.handle_request()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    server_ready.wait()

    print(f"\n  Opening browser for Google authorization...")
    webbrowser.open(auth_url)
    print(f"  If the browser didn't open, visit:\n  {auth_url}\n")

    t.join(timeout=130)

    if callback_error[0]:
        raise RuntimeError(f"Google auth denied: {callback_error[0]}")
    if not callback_code[0]:
        raise RuntimeError("Google auth timed out — no callback received within 2 minutes.")

    flow.fetch_token(code=callback_code[0])
    creds = flow.credentials

    return {
        "refresh_token": creds.refresh_token,
        "access_token":  creds.token,
    }
