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


def _story(**plan):
    """A story shaped like the one from the live test (Region values are states, not 'West')."""
    return {
        "story_summary": "Approval rate is falling in the West region (Oregon/Northern California).",
        "signal_description": "Loan Approval Rate declines in the West, worst in Auto loans.",
        "dimensions": ["Region", "Product Type", "Segment"],
        "dimension_values": {"Region": ["Washington State", "Oregon", "Northern California", "Alaska"],
                             "Product Type": ["Auto", "Mortgage", "Personal"],
                             "Segment": ["Prime", "Near Prime"]},
        "metric_config": [{"label": "Loan Approval Rate", "is_primary": True},
                          {"label": "Days to Decision"}, {"label": "Member NPS"}],
        "signal_plan": {"culprit": {"dimension": "Region", "value": "West"},
                        "culprit_detail": {"dimension": "Product Type", "value": "Auto"},
                        "counter_trend_metric": "Member NPS", "onset_months_ago": 6, **plan},
    }


GOOD_PLAN = {"culprit": {"dimension": "Region", "value": "Oregon"},
             "culprit_detail": {"dimension": "Product Type", "value": "Auto"},
             "counter_trend_metric": "Member NPS", "onset_months_ago": 6}


class SignalPlanMatchesTheStory(unittest.TestCase):
    """A plan that names a value the story doesn't have is fixed at the Story step, or refused."""

    @classmethod
    def setUpClass(cls):
        try:
            import builder
        except ImportError as e:
            raise unittest.SkipTest(f"builder dependencies not installed: {e}")
        cls.b = builder

    def test_live_case_is_reported(self):
        problems = self.b.signal_plan_problems(_story())
        self.assertEqual(len(problems), 1)
        self.assertIn('culprit.value "West" is not a value of Region', problems[0])

    def test_every_kind_of_mismatch(self):
        cases = {
            "not one of the dimensions": _story(culprit={"dimension": "Territory", "value": "Oregon"}),
            "culprit_detail.value": _story(culprit=GOOD_PLAN["culprit"], culprit_detail={"dimension": "Segment", "value": "Enterprise"}),
            "different dimension": _story(culprit=GOOD_PLAN["culprit"], culprit_detail={"dimension": "Region", "value": "Alaska"}),
            "is not a metric label": _story(culprit=GOOD_PLAN["culprit"], counter_trend_metric="Net Promoter"),
            "is the primary metric": _story(culprit=GOOD_PLAN["culprit"], counter_trend_metric="Loan Approval Rate"),
        }
        for expected, story in cases.items():
            self.assertIn(expected, " | ".join(self.b.signal_plan_problems(story)), expected)
        self.assertEqual(self.b.signal_plan_problems({**_story(), "signal_plan": {}}), ["signal_plan is missing"])

    def test_good_plan_has_no_problems_and_no_claude_call(self):
        ask = mock.Mock()
        story = self.b.ensure_valid_signal_plan(_story(**GOOD_PLAN), ask)
        ask.assert_not_called()
        self.assertEqual(story["signal_plan"]["culprit"]["value"], "Oregon")

    def test_case_and_spacing_are_fixed_without_asking(self):
        ask = mock.Mock()
        story = self.b.ensure_valid_signal_plan(
            _story(culprit={"dimension": "region", "value": " northern  california"}, counter_trend_metric="member nps"), ask)
        ask.assert_not_called()
        self.assertEqual(story["signal_plan"]["culprit"], {"dimension": "Region", "value": "Northern California"})
        self.assertEqual(story["signal_plan"]["counter_trend_metric"], "Member NPS")

    def test_a_dimension_without_listed_values_is_not_checked(self):
        story = _story()
        story["dimension_values"].pop("Region")     # dropped earlier as generic placeholders
        self.assertEqual(self.b.signal_plan_problems(story), [])

    def test_claude_corrects_the_plan_once(self):
        reply = "```json\n" + json.dumps({"signal_plan": GOOD_PLAN, "story_summary": "Approval rate is falling in Oregon.",
                                          "signal_description": "Worst in Oregon Auto loans."}) + "\n```"
        ask = mock.Mock(return_value=reply)
        story = self.b.ensure_valid_signal_plan(_story(), ask)
        ask.assert_called_once()
        prompt = ask.call_args[0][0]
        self.assertIn('culprit.value "West"', prompt)
        self.assertIn("Northern California", prompt)             # the allowed values are in the request
        self.assertEqual(story["signal_plan"], GOOD_PLAN)
        self.assertEqual(story["story_summary"], "Approval rate is falling in Oregon.")
        self.assertEqual(self.b.signal_plan_problems(story), [])

    def test_still_wrong_after_one_try_is_a_clear_error(self):
        ask = mock.Mock(return_value=json.dumps({"signal_plan": {**GOOD_PLAN, "culprit": {"dimension": "Region", "value": "Pacific"}}}))
        with self.assertRaises(RuntimeError) as err:
            self.b.ensure_valid_signal_plan(_story(), ask)
        ask.assert_called_once()                                  # one correction, not a loop
        self.assertIn("isn't in its own data", str(err.exception))
        self.assertIn('"Pacific"', str(err.exception))
        self.assertIn("Generate again", str(err.exception))

    def test_unusable_reply_or_failed_call_is_the_same_clear_error(self):
        for ask in (mock.Mock(return_value="Sorry, I can't."), mock.Mock(side_effect=TimeoutError("slow"))):
            with self.assertRaises(RuntimeError) as err:
                self.b.ensure_valid_signal_plan(_story(), ask)
            self.assertIn('"West"', str(err.exception))

    def test_story_endpoint_returns_the_error_to_the_story_step(self):
        with mock.patch.object(self.b, "generate_story", side_effect=RuntimeError(
                "The generated story names a segment that isn't in its own data (x). Click Generate again to get a new story.")):
            r = webapp.app.test_client().post("/api/build/generate-story", json={"company": "Acme"},
                                               headers={"Host": "localhost:5100"})
        body = r.get_json()
        self.assertFalse(body["ok"])
        self.assertIn("Click Generate again", body["error"])

    def test_generate_story_runs_the_check(self):
        """End to end with the model mocked: a bad plan from the story call is corrected by the second call."""
        bad = _story()
        replies = [json.dumps(bad), json.dumps({"signal_plan": GOOD_PLAN})]
        research = types.ModuleType("researcher")           # no web research in a unit test
        research.research_company = lambda **kw: {}
        research.format_research_for_prompt = lambda r: ""
        with mock.patch.object(webapp, "_get_chat_config", return_value={"mode": "anthropic_sdk", "api_key": "k"}), \
                mock.patch.dict(sys.modules, {"researcher": research}), \
                mock.patch.object(self.b, "_find_existing_demo", return_value=None), \
                mock.patch.object(self.b, "_claude_text", side_effect=replies) as call:
            out = self.b.generate_story("Harborview Credit Union", "Banking", "loan approvals", "COO", research_depth="none")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(out["signal_plan"]["culprit"]["value"], "Oregon")


class SchemaFollowsTheFields(unittest.TestCase):
    """A rebuild with different metrics or dimensions must not reuse the old Data Cloud schema."""

    @classmethod
    def setUpClass(cls):
        try:
            import builder
        except ImportError as e:
            raise unittest.SkipTest(f"builder dependencies not installed: {e}")
        cls.b = builder

    def schema(self, name, fields, extra=()):
        return {"name": name, "fields": [{"name": f} for f in list(fields) + list(extra)]}

    OLD = ["record_id", "date", "day_offset", "entity_id", "product_type", "days_to_loan_decision", "loan_volume"]
    NEW = ["record_id", "date", "day_offset", "entity_id", "region", "loan_approval_rate", "member_nps"]

    def test_no_schema_yet(self):
        self.assertEqual(self.b.pick_schema_name("harborview", self.NEW, []), ("harborview", False))

    def test_same_fields_reuse_the_schema(self):
        existing = [self.schema("harborview", self.NEW, extra=["DataSourceId", "DataSourceObjectId"])]
        self.assertEqual(self.b.pick_schema_name("harborview", list(reversed(self.NEW)), existing), ("harborview", True))

    def test_different_fields_get_a_new_name(self):
        name, exists = self.b.pick_schema_name("harborview", self.NEW, [self.schema("harborview", self.OLD)])
        self.assertRegex(name, r"^harborview_[0-9a-f]{6}$")
        self.assertFalse(exists)

    def test_the_new_name_is_stable_and_reused_next_time(self):
        first, _ = self.b.pick_schema_name("harborview", self.NEW, [self.schema("harborview", self.OLD)])
        again, exists = self.b.pick_schema_name(
            "harborview", self.NEW, [self.schema("harborview", self.OLD), self.schema(first, self.NEW)])
        self.assertEqual(again, first)
        self.assertTrue(exists)

    def test_a_third_story_gets_its_own_name(self):
        a, _ = self.b.pick_schema_name("harborview", self.NEW, [self.schema("harborview", self.OLD)])
        b, _ = self.b.pick_schema_name("harborview", self.NEW + ["segment"], [self.schema("harborview", self.OLD)])
        self.assertNotEqual(a, b)

    def test_signature_tracks_metrics_and_dimensions_not_their_order(self):
        story = {"dimensions": ["Region", "Product Type"]}
        metrics = [{"label": "Loan Approval Rate"}, {"label": "Member NPS"}]
        sig = self.b.schema_signature(story, metrics)
        self.assertEqual(sig, self.b.schema_signature({"dimensions": ["Product Type", "Region"]}, list(reversed(metrics))))
        self.assertNotEqual(sig, self.b.schema_signature(story, metrics + [{"label": "Loan Volume"}]))
        self.assertNotEqual(sig, self.b.schema_signature({"dimensions": ["Region", "Segment"]}, metrics))

    def test_build_uses_it(self):
        src = (ROOT / "web-ui" / "builder.py").read_text()
        self.assertIn("pick_schema_name(", src.split("# --- Phase 2: Schema + Stream ---")[1].split("# --- Phase 3")[0])
        self.assertNotIn('schema_exists = any(s.get("name") == schema_name', src)


if __name__ == "__main__":
    unittest.main()
