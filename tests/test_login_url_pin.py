"""A connection on a generic login URL is pinned to its org's My Domain after a successful login.

Seen 2026-11-16: Tableau Next & Slack used login.salesforce.com. Clicking MCP right after
authorizing AIO Dev (a My Domain connection) sent the browser to AIO Dev with Tableau Next &
Slack's app ID, and the login failed cross-org. No org or network needed:
python3 -m unittest tests.test_login_url_pin -v
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
sys.path.insert(0, str(ROOT / "web-ui"))
sys.modules.setdefault("tableauserverclient", types.ModuleType("tableauserverclient"))

import connections  # noqa: E402
import app as webapp  # noqa: E402

MY_DOMAIN = "https://acme-dev-ed.my.salesforce.com"
LOCAL = {"Host": "localhost:5100", "Origin": "http://localhost:5100"}


class PinRules(unittest.TestCase):
    def pin(self, login, instance):
        sf = {"sf_login_url": login} if login is not None else {}
        return connections.pin_login_url(sf, instance), sf.get("sf_login_url")

    def test_generic_production_url_becomes_my_domain(self):
        self.assertEqual(self.pin("https://login.salesforce.com", MY_DOMAIN + "/"), (True, MY_DOMAIN))

    def test_missing_url_counts_as_generic(self):
        self.assertEqual(self.pin(None, MY_DOMAIN), (True, MY_DOMAIN))

    def test_sandbox_url_becomes_sandbox_my_domain(self):
        sb = "https://acme--dev.sandbox.my.salesforce.com"
        self.assertEqual(self.pin("https://test.salesforce.com/", sb), (True, sb))

    def test_existing_my_domain_is_never_changed(self):
        other = "https://other-org.my.salesforce.com"
        self.assertEqual(self.pin(other, MY_DOMAIN), (False, other))

    def test_only_a_my_domain_is_used(self):
        for instance in ("https://na123.salesforce.com", "http://acme.my.salesforce.com", "",
                         "https://acme.my.salesforce.com.evil.example"):
            self.assertEqual(self.pin("https://login.salesforce.com", instance)[0], False, instance)


class PinnedOnLogin(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = Path(tmp.name) / "config.json"
        for p in (mock.patch.object(connections, "CONFIG_FILE", str(self.cfg)),
                  mock.patch.object(webapp, "CONFIG_PATH", self.cfg)):
            p.start()
            self.addCleanup(p.stop)
        connections.save_full_config({
            "active_salesforce": "c", "active_tableau_cloud": "c",
            "profiles": {"c": {"salesforce": {"sf_login_url": "https://login.salesforce.com", "client_id": "cid",
                                              "refresh_token": "rt", "mcp_client_id": "mcp-cid"}}}})

    def login_url(self):
        return json.loads(self.cfg.read_text())["profiles"]["c"]["salesforce"]["sf_login_url"]

    def test_token_refresh_pins_the_connection(self):
        resp = mock.Mock(status_code=200, text="")
        resp.json.return_value = {"access_token": "at", "instance_url": MY_DOMAIN}
        with mock.patch.object(connections.requests, "post", return_value=resp):
            connections.get_sf_token(profile_key="c")
        self.assertEqual(self.login_url(), MY_DOMAIN)

    def test_oauth_button_pins_the_connection(self):
        tokens = {"refresh_token": "rt2", "access_token": "at", "instance_url": MY_DOMAIN}
        with mock.patch("oauth_flow.get_refresh_token", return_value=tokens):
            r = webapp.app.test_client().post("/api/oauth/start", json={"profile_key": "c"}, headers=LOCAL)
        self.assertTrue(r.get_json()["ok"], r.get_json())
        self.assertEqual(self.login_url(), MY_DOMAIN)

    def test_mcp_button_pins_the_connection(self):
        tokens = {"refresh_token": "mrt", "access_token": "at", "instance_url": MY_DOMAIN}
        with mock.patch("oauth_flow.get_refresh_token", return_value=tokens):
            r = webapp.app.test_client().post("/api/oauth/mcp", json={"profile_key": "c"}, headers=LOCAL)
        self.assertTrue(r.get_json()["ok"], r.get_json())
        self.assertEqual(self.login_url(), MY_DOMAIN)

    def test_cached_token_writes_nothing(self):
        full = connections.load_full_config()
        full["profiles"]["c"]["_token_cache"] = {"access_token": "cached", "instance_url": MY_DOMAIN,
                                                 "expires_at": time.time() + 3600}
        connections.save_full_config(full)
        before = self.cfg.read_text()
        with mock.patch.object(connections.requests, "post", side_effect=AssertionError("no refresh")):
            connections.get_sf_token(profile_key="c")
        self.assertEqual(self.cfg.read_text(), before)


if __name__ == "__main__":
    unittest.main()
