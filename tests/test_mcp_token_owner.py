"""A rotated MCP refresh token is saved under the connection it belongs to, never the active one.

Seen 2026-11-16: MCPClient saved AIO Dev's rotated MCP token under the active connection (Tableau
Next & Slack). AIO Dev kept a retired token (invalid_grant on its next build) and Tableau Next &
Slack got another org's token (app_not_found). No org or network needed:
python3 -m unittest tests.test_mcp_token_owner -v
"""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web-ui"))
sys.modules.setdefault("tableauserverclient", types.ModuleType("tableauserverclient"))

import connections  # noqa: E402
import mcp_client  # noqa: E402


def _profile(login, cid, mcp_cid, mcp_rt):
    return {"salesforce": {"sf_login_url": login, "client_id": cid, "refresh_token": "rest-" + cid,
                           "mcp_client_id": mcp_cid, "mcp_refresh_token": mcp_rt}}


class McpTokenSavedUnderItsOwnConnection(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = Path(tmp.name) / "config.json"
        p = mock.patch.object(connections, "CONFIG_FILE", str(self.cfg))
        p.start()
        self.addCleanup(p.stop)
        connections.save_full_config({
            "active_salesforce": "active", "active_tableau_cloud": "active",
            "profiles": {"active": _profile("https://active.example", "cid-a", "mcp-a", "mrt-a"),
                         "other": _profile("https://other.example", "cid-b", "mcp-b", "mrt-b")}})

    def refresh(self, rotated):
        def fake_post(url, data=None, **kw):
            resp = mock.Mock(status_code=200, text="")
            resp.json.return_value = {"access_token": "at", **({"refresh_token": rotated} if rotated else {})}
            return resp
        return fake_post

    def saved(self):
        return {k: p["salesforce"]["mcp_refresh_token"] for k, p in json.loads(self.cfg.read_text())["profiles"].items()}

    def test_rotated_token_goes_to_its_own_connection(self):
        client = mcp_client.MCPClient(connections.load_config("other"))
        with mock.patch.object(mcp_client.requests, "post", side_effect=self.refresh("mrt-b2")):
            client.authenticate()
        self.assertEqual(self.saved(), {"active": "mrt-a", "other": "mrt-b2"})
        self.assertEqual(client.sf["mcp_refresh_token"], "mrt-b2")

    def test_active_connection_still_works(self):
        client = mcp_client.MCPClient(connections.load_config("active"))
        with mock.patch.object(mcp_client.requests, "post", side_effect=self.refresh("mrt-a2")):
            client.authenticate()
        self.assertEqual(self.saved(), {"active": "mrt-a2", "other": "mrt-b"})

    def test_rest_token_rotating_meanwhile_does_not_lose_it(self):
        config = connections.load_config("other")
        full = connections.load_full_config()          # the REST login rotates during the build
        full["profiles"]["other"]["salesforce"]["refresh_token"] = "rest-rotated"
        connections.save_full_config(full)
        with mock.patch.object(mcp_client.requests, "post", side_effect=self.refresh("mrt-b2")):
            mcp_client.MCPClient(config).authenticate()
        self.assertEqual(self.saved()["other"], "mrt-b2")

    def test_no_rotation_writes_nothing(self):
        before = self.cfg.read_text()
        with mock.patch.object(mcp_client.requests, "post", side_effect=self.refresh(None)):
            mcp_client.MCPClient(connections.load_config("other")).authenticate()
        self.assertEqual(self.cfg.read_text(), before)

    def test_unknown_token_is_not_saved_anywhere(self):
        config = {"salesforce": {"sf_login_url": "https://x.example", "client_id": "c",
                                 "mcp_client_id": "mcp-b", "mcp_refresh_token": "not-saved"}}
        before = self.cfg.read_text()
        with mock.patch.object(mcp_client.requests, "post", side_effect=self.refresh("mrt-new")):
            mcp_client.MCPClient(config).authenticate()
        self.assertEqual(self.cfg.read_text(), before)


if __name__ == "__main__":
    unittest.main()
