"""Fixes from the live test of v2.17.3: story plan on the Build page, demo-scoped CRM
Account IDs, remote cleanup (right org, streams, Accounts), and the CSV written once.

    python3 -m unittest tests.test_live_findings -v

No org or network is touched; HTTP calls are mocked.
"""
import json
import re
import shutil
import subprocess
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
import crm_upserter  # noqa: E402
import app as webapp  # noqa: E402


class StoryPlanOnBuildPage(unittest.TestCase):
    """The Build page must send the generated story whole; it used to drop signal_plan."""

    def final_story(self, story_js):
        html = (ROOT / "web-ui" / "templates" / "build.html").read_text()
        block = re.search(r"const finalStoryConfig = \{.*?\n    \};", html, re.S).group(0)
        script = f"""
            const fields = {{'story-summary': {{value: 'edited summary'}}, 'story-signal': {{value: 'edited signal'}}}};
            const document = {{getElementById: id => fields[id] || null}};
            const editedMetrics = [{{label: 'Edited Metric'}}];
            const storyConfig = {story_js};
            {block}
            console.log(JSON.stringify(finalStoryConfig));
        """
        return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_generated_keys_survive_and_edits_win(self):
        plan = {"culprit": {"dimension": "Region", "value": "West"}, "counter_trend_metric": "NPS"}
        story = {"story_summary": "generated", "signal_plan": plan, "dimensions": ["Region"],
                 "dimension_values": {"Region": ["West", "East"]}, "metric_config": [{"label": "Old"}],
                 "audience": "CFO", "a_key_added_later": 1}
        out = self.final_story(json.dumps(story))
        self.assertEqual(out["signal_plan"], plan)
        self.assertEqual(out["a_key_added_later"], 1)                    # new keys can't be dropped again
        self.assertEqual(out["story_summary"], "edited summary")         # what the user typed wins
        self.assertEqual(out["metric_config"], [{"label": "Edited Metric"}])
        self.assertEqual(out["audience_context"], "CFO")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_no_generated_story(self):
        out = self.final_story("null")
        self.assertEqual(out["dimensions"], ["Region", "Category", "Segment"])
        self.assertNotIn("signal_plan", out)

    def test_page_starts_from_the_whole_story(self):
        html = (ROOT / "web-ui" / "templates" / "build.html").read_text()
        block = re.search(r"const finalStoryConfig = \{.*?\n    \};", html, re.S).group(0)
        self.assertIn("...(storyConfig || {})", block)


class DemoScopedAccountIds(unittest.TestCase):
    def test_two_demos_never_share_an_id(self):
        a = crm_upserter.demo_external_id("acme_churn", "E-0001")
        b = crm_upserter.demo_external_id("harborview_loans", "E-0001")
        self.assertEqual(a, "acme_churn-E-0001")
        self.assertNotEqual(a, b)

    def test_fits_the_field(self):
        ext = crm_upserter.demo_external_id("x" * 200, "E-0001")
        self.assertLessEqual(len(ext), 80)
        self.assertTrue(ext.endswith("-E-0001"))

    def test_builder_uses_it(self):
        src = (ROOT / "web-ui" / "builder.py").read_text()
        self.assertIn('"Demo_External_ID__c": demo_external_id(slug, eid)', src)
        self.assertNotIn('"Demo_External_ID__c": eid,', src)


class DeleteRecordsById(unittest.TestCase):
    def test_batches_of_200_and_counts(self):
        ids = [f"001{i:012d}" for i in range(450)]
        calls = []

        def fake_delete(url, headers=None, params=None, timeout=None):
            batch = params["ids"].split(",")
            calls.append(len(batch))
            body = [{"success": True} for _ in batch]
            if len(calls) == 3:   # last batch: one already deleted, one real failure
                body[0] = {"success": False, "errors": [{"statusCode": "ENTITY_IS_DELETED"}]}
                body[1] = {"success": False, "errors": [{"statusCode": "DELETE_FAILED"}]}
            return mock.Mock(ok=True, json=lambda: body)

        with mock.patch.object(crm_upserter.requests, "delete", side_effect=fake_delete):
            deleted, failed = crm_upserter.delete_records_by_id("tok", "https://org.example", ids)
        self.assertEqual(calls, [200, 200, 50])
        self.assertEqual((deleted, failed), (449, 1))

    def test_http_failure_counts_the_batch(self):
        with mock.patch.object(crm_upserter.requests, "delete", return_value=mock.Mock(ok=False, status_code=500, text="")):
            self.assertEqual(crm_upserter.delete_records_by_id("t", "https://o", ["a", "b"]), (0, 2))


class RemoteCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        cfg = self.tmp / "config.json"
        p = mock.patch.object(connections, "CONFIG_FILE", str(cfg))
        p.start(); self.addCleanup(p.stop)
        sf = lambda n: {"sf_login_url": f"https://{n}.example", "client_id": "c", "refresh_token": "r"}
        connections.save_full_config({
            "active_salesforce": "active_org", "active_tableau_cloud": "active_org",
            "profiles": {"active_org": {"label": "Active", "salesforce": sf("active"), "tableau": {}},
                         "demo_org": {"label": "Demo", "salesforce": sf("demo"), "tableau": {}}}})
        self.deleted, self.token_keys = [], []

        def fake_token(config=None, profile_key=None, allow_browser=True):
            self.token_keys.append(profile_key)
            return "tok", config["salesforce"]["sf_login_url"]

        def fake_delete(url, headers=None, params=None, timeout=None):
            self.deleted.append(url if not params else url + "?ids=" + params["ids"])
            return mock.Mock(ok=True, json=lambda: [{"success": True} for _ in params["ids"].split(",")] if params else {})

        for target, attr, fn in ((connections, "get_sf_token", fake_token),):
            p = mock.patch.object(target, attr, side_effect=fn); p.start(); self.addCleanup(p.stop)
        p = mock.patch("requests.delete", side_effect=fake_delete); p.start(); self.addCleanup(p.stop)

    CP = {"build_type": "next", "_profile_key": "demo_org", "all_dash_apis": ["dash"], "all_viz_apis": ["viz"],
          "all_sdm_apis": ["sdm"], "all_ws_apis": ["ws"], "all_stream_names": ["stream_A1"],
          "stream_name": "stream_A1", "crm_account_ids": {"s-E-0001": "001A", "s-E-0002": "001B"}}

    def test_deletes_go_to_the_org_the_demo_was_built_in(self):
        webapp._delete_remote_assets(dict(self.CP))
        self.assertEqual(self.token_keys, ["demo_org"])
        self.assertTrue(self.deleted)
        self.assertTrue(all(u.startswith("https://demo.example/") for u in self.deleted), self.deleted)

    def test_per_output_key_wins(self):
        webapp._delete_remote_assets({**self.CP, "_profile_key": "active_org", "_next_profile_key": "demo_org"})
        self.assertEqual(self.token_keys, ["demo_org"])

    def test_old_checkpoint_uses_the_active_connection(self):
        cp = {k: v for k, v in self.CP.items() if k != "_profile_key"}
        webapp._delete_remote_assets(cp)
        self.assertTrue(all(u.startswith("https://active.example/") for u in self.deleted))

    def test_removed_connection_deletes_nothing(self):
        results = webapp._delete_remote_assets({**self.CP, "_profile_key": "gone_org"})
        self.assertEqual(self.deleted, [])
        self.assertIn("no longer exists", " ".join(results))

    def test_stream_is_deleted_with_its_dlo_after_the_sdm(self):
        webapp._delete_remote_assets(dict(self.CP))
        stream = [i for i, u in enumerate(self.deleted) if "/ssot/data-streams/stream_A1?shouldDeleteDataLakeObject=true" in u]
        sdm = [i for i, u in enumerate(self.deleted) if "/ssot/semantic/models/sdm" in u]
        self.assertEqual(len(stream), 1)
        self.assertLess(sdm[0], stream[0])

    def test_a_stream_the_build_only_found_is_left_alone(self):
        cp = {k: v for k, v in self.CP.items() if k != "all_stream_names"}
        webapp._delete_remote_assets(cp)
        self.assertFalse([u for u in self.deleted if "data-streams" in u])

    def test_unscoped_accounts_are_left_in_place(self):
        results = webapp._delete_remote_assets(dict(self.CP))
        self.assertFalse([u for u in self.deleted if "composite/sobjects" in u])
        self.assertIn("left in place", " ".join(results))

    def test_scoped_accounts_are_deleted(self):
        results = webapp._delete_remote_assets({**self.CP, "crm_ids_scoped": True})
        self.assertEqual([u.split("?ids=")[1] for u in self.deleted if "composite/sobjects" in u], ["001A,001B"])
        self.assertIn("CRM Accounts: 2 deleted", results)

    def test_pulse_only_checkpoint_never_touches_salesforce(self):
        with mock.patch.object(connections, "get_tableau_token", side_effect=RuntimeError("no site")):
            results = webapp._delete_remote_assets({"build_type": "pulse", "pulse_def_ids": ["d1"]})
        self.assertEqual(self.token_keys, [])
        self.assertIn("Pulse cleanup error", results[0])


class CsvWrittenOnce(unittest.TestCase):
    def test_same_data_is_written_and_logged_once_per_run(self):
        try:
            import builder
            import pandas as pd
        except ImportError as e:
            self.skipTest(f"builder dependencies not installed: {e}")
        tmp = tempfile.mkdtemp()
        df, q = pd.DataFrame({"a": [1, 2]}), mock.Mock()
        with mock.patch.object(pd.DataFrame, "to_csv", autospec=True, side_effect=pd.DataFrame.to_csv) as to_csv, \
                mock.patch.object(builder, "_build_log_file", None):
            first = builder.csv_build("b", df, "acme", tmp, q)      # the CSV step
            second = builder.csv_build("b", df, "acme", tmp, q)     # the Tableau Next step
            self.assertEqual(first, second)
            self.assertEqual(to_csv.call_count, 1)
            self.assertEqual(q.put.call_count, 2)                    # "Exporting" + "exported", once
            builder.csv_build("b", pd.DataFrame({"a": [3]}), "acme", tmp, q)   # a new run's data is written
            self.assertEqual(to_csv.call_count, 2)
        self.assertEqual(Path(first).read_text().split(), ["a", "3"])


if __name__ == "__main__":
    unittest.main()
