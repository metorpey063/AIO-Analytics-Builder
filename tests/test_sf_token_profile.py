"""get_sf_token(config) must use that connection's own tokens, never the active connection's.

Seen 2026-11-16: Test on the AIO Dev card returned the Tableau Next & Slack org, because a config
passed without its key fell back to the active connection's token cache. A refresh in that state
saved AIO Dev's tokens over the active connection's. No org or network needed:
python3 -m unittest tests.test_sf_token_profile -v
"""
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("tableauserverclient", types.ModuleType("tableauserverclient"))

import connections  # noqa: E402


def _sf(login, cid, rt):
    return {"sf_login_url": login, "client_id": cid, "refresh_token": rt}


class SfTokenUsesItsOwnConnection(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = Path(tmp.name) / "config.json"
        p = mock.patch.object(connections, "CONFIG_FILE", str(self.cfg))
        p.start()
        self.addCleanup(p.stop)
        connections.save_full_config({
            "active_salesforce": "active", "active_tableau_cloud": "active",
            "profiles": {
                "active": {"salesforce": _sf("https://active.example", "cid-a", "rt-a"),
                           "_token_cache": {"access_token": "token-a", "instance_url": "https://org-a.example",
                                            "expires_at": time.time() + 3600}},
                "other": {"salesforce": _sf("https://other.example", "cid-b", "rt-b")},
            }})

    def other_config(self):
        return connections.load_config("other")

    def fake_refresh(self, url, data=None, **kw):
        self.assertEqual(url, "https://other.example/services/oauth2/token")
        self.assertEqual(data["client_id"], "cid-b")
        resp = mock.Mock(status_code=200, text="")
        resp.json.return_value = {"access_token": "token-b", "instance_url": "https://org-b.example",
                                  "refresh_token": "rt-b2"}
        return resp

    def test_config_without_key_does_not_get_active_cached_token(self):
        with mock.patch.object(connections.requests, "post", side_effect=self.fake_refresh):
            token, instance = connections.get_sf_token(self.other_config())
        self.assertEqual((token, instance), ("token-b", "https://org-b.example"))

    def test_refresh_saves_under_its_own_connection(self):
        with mock.patch.object(connections.requests, "post", side_effect=self.fake_refresh):
            connections.get_sf_token(self.other_config())
        full = json.loads(self.cfg.read_text())
        self.assertEqual(full["profiles"]["other"]["salesforce"]["refresh_token"], "rt-b2")
        self.assertEqual(full["profiles"]["other"]["_token_cache"]["instance_url"], "https://org-b.example")
        self.assertEqual(full["profiles"]["active"]["salesforce"]["refresh_token"], "rt-a")
        self.assertEqual(full["profiles"]["active"]["_token_cache"]["access_token"], "token-a")

    def test_second_call_uses_its_own_cache(self):
        with mock.patch.object(connections.requests, "post", side_effect=self.fake_refresh):
            connections.get_sf_token(self.other_config())
        with mock.patch.object(connections.requests, "post", side_effect=AssertionError("no refresh")):
            token, _ = connections.get_sf_token(self.other_config())
        self.assertEqual(token, "token-b")

    def test_no_config_still_means_active_connection(self):
        with mock.patch.object(connections.requests, "post", side_effect=AssertionError("no refresh")):
            token, instance = connections.get_sf_token()
        self.assertEqual((token, instance), ("token-a", "https://org-a.example"))

    def test_unknown_config_is_not_saved_anywhere(self):
        before = self.cfg.read_text()
        loose = {"salesforce": _sf("https://other.example", "cid-b", "not-saved")}
        with mock.patch.object(connections.requests, "post", side_effect=self.fake_refresh):
            token, _ = connections.get_sf_token(loose)
        self.assertEqual(token, "token-b")
        self.assertEqual(self.cfg.read_text(), before)

    def test_browser_reauth_saves_under_its_own_connection(self):
        expired = mock.Mock(status_code=400, text='{"error":"invalid_grant"}')
        expired.json.return_value = {"error": "invalid_grant", "error_description": "expired access/refresh token"}
        login = {"refresh_token": "rt-b-new", "access_token": "token-b", "instance_url": "https://org-b.example"}
        with mock.patch.object(connections.requests, "post", return_value=expired), \
             mock.patch.object(connections, "_is_expired_refresh_token", return_value=True), \
             mock.patch.dict("os.environ", {}, clear=False), \
             mock.patch("oauth_flow.get_refresh_token", return_value=login):
            connections.os.environ.pop("AIO_NO_BROWSER_REAUTH", None)
            connections.get_sf_token(self.other_config())
        full = json.loads(self.cfg.read_text())
        self.assertEqual(full["profiles"]["other"]["salesforce"]["refresh_token"], "rt-b-new")
        self.assertEqual(full["profiles"]["active"]["salesforce"]["refresh_token"], "rt-a")


if __name__ == "__main__":
    unittest.main()
