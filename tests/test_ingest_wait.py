"""Post-build checks wait for the Data Cloud ingest instead of failing a build whose data is
still loading.

    python3 -m unittest tests.test_ingest_wait -v

No org or network: the token calls, the ingest-job status and the row-count query are mocked,
and waiting uses a fake clock.
"""
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web-ui"))
sys.modules.setdefault("tableauserverclient", types.ModuleType("tableauserverclient"))

import connections  # noqa: E402

try:
    import builder
except ImportError:                       # pandas etc. not installed
    builder = None


class FakeOrg:
    """An ingest job that finishes after `complete_after` seconds of waiting, and a DLO whose
    rows show in queries `query_lag` seconds after that."""

    def __init__(self, complete_after=0, final="JobComplete", rows=14400, query_lag=0):
        self.clock = 0
        self.complete_after, self.final, self.rows, self.query_lag = complete_after, final, rows, query_lag
        self.status_calls = self.count_calls = 0

    def sleep(self, seconds):
        self.clock += seconds

    def job_state(self):
        return self.final if self.clock >= self.complete_after else "InProgress"

    def get(self, url, headers=None, timeout=None, **kw):
        if "/api/v1/ingest/jobs/" in url:
            self.status_calls += 1
            return mock.Mock(ok=True, json=lambda: {"state": self.job_state()})
        return mock.Mock(ok=True, status_code=200, json=lambda: {"label": url.rsplit("/", 1)[-1].split("?")[0],
                                                                  "visualSpecification": {}, "dataSource": {"name": "SDM"}})

    def post(self, url, headers=None, json=None, timeout=None, **kw):
        assert url.endswith("/ssot/queryv2"), url
        self.count_calls += 1
        loaded = self.job_state() == "JobComplete" and self.clock >= self.complete_after + self.query_lag
        n = self.rows if loaded else 0
        return mock.Mock(ok=True, json=lambda: {"data": [[n]]})


@unittest.skipIf(builder is None, "builder dependencies not installed")
class IngestWait(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.q = mock.Mock(put=lambda m: self.messages.append(m["message"]))
        for target, attr, value in (
                (connections, "get_sf_token", mock.Mock(return_value=("sf", "https://org.example"))),
                (connections, "get_dc_token", mock.Mock(return_value=("dc", "dc.example"))),
                (builder, "_log_path_for", mock.Mock(return_value=None))):
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def use(self, org):
        for attr in ("get", "post"):
            p = mock.patch(f"aio_http.{attr}", side_effect=getattr(org, attr))
            p.start()
            self.addCleanup(p.stop)
        return org

    def cp(self, **extra):
        return {"ingest_job_id": "job-1", "ingest_state": "InProgress", "ingest_done": True,
                "dlo_name": "fact__dll", "sdm_api": "SDM", "measurement_map": {"rate": "rate1"},
                "dim_field_map": {"region": "region1"}, "display_date_api": "Display_Date", **extra}

    def validate(self, cp, org, **kw):
        builder._validate_next_build({}, cp, [], self.q, sleep=org.sleep, **kw)
        return " | ".join(self.messages)

    # --- wait_for_ingest ---------------------------------------------------------------

    def test_waits_until_the_job_completes(self):
        org = self.use(FakeOrg(complete_after=7 * 60))
        cp = self.cp()
        self.assertEqual(builder.wait_for_ingest({}, cp, self.q, sleep=org.sleep), "JobComplete")
        self.assertEqual(cp["ingest_state"], "JobComplete")
        self.assertGreaterEqual(org.clock, 7 * 60)
        self.assertLess(org.clock, 7 * 60 + builder.INGEST_POLL_SECONDS + 1)    # stops as soon as it's done
        self.assertTrue(any("still loading" in m for m in self.messages))

    def test_finished_job_needs_no_call(self):
        org = self.use(FakeOrg())
        cp = self.cp(ingest_state="JobComplete")
        self.assertEqual(builder.wait_for_ingest({}, cp, self.q, sleep=org.sleep), "JobComplete")
        self.assertEqual((org.status_calls, org.clock), (0, 0))

    def test_gives_up_after_the_budget(self):
        org = self.use(FakeOrg(complete_after=10 ** 6))
        cp = self.cp()
        state = builder.wait_for_ingest({}, cp, self.q, budget=600, sleep=org.sleep)
        self.assertEqual(state, "InProgress")
        self.assertEqual(org.clock, 600)

    def test_budget_zero_is_a_single_check(self):
        org = self.use(FakeOrg(complete_after=10 ** 6))
        builder.wait_for_ingest({}, self.cp(), self.q, budget=0, sleep=org.sleep)
        self.assertEqual((org.status_calls, org.clock), (1, 0))

    def test_late_failure_lets_a_rerun_send_the_rows_again(self):
        org = self.use(FakeOrg(complete_after=60, final="Failed"))
        cp = self.cp()
        self.assertEqual(builder.wait_for_ingest({}, cp, self.q, sleep=org.sleep), "Failed")
        self.assertFalse(cp["ingest_done"])

    def test_no_job_recorded(self):
        org = self.use(FakeOrg())
        self.assertEqual(builder.wait_for_ingest({}, {}, self.q, sleep=org.sleep), "unknown")
        self.assertEqual(org.status_calls, 0)

    def test_status_errors_are_not_failures(self):
        org = FakeOrg(complete_after=40)
        calls = {"n": 0}

        def flaky_get(url, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("blip")
            if calls["n"] == 2:
                return mock.Mock(ok=False, status_code=503)
            return org.get(url, **kw)

        p = mock.patch("aio_http.get", side_effect=flaky_get)
        p.start()
        self.addCleanup(p.stop)
        self.assertEqual(builder.wait_for_ingest({}, self.cp(), self.q, sleep=org.sleep), "JobComplete")

    # --- the post-build row check --------------------------------------------------------

    def test_reported_case_good_build_with_slow_ingest_passes(self):
        """Validation starts while the job is still running: it used to read 0 rows and fail."""
        org = self.use(FakeOrg(complete_after=6 * 60))
        out = self.validate(self.cp(), org)
        self.assertIn("✓ SDM query returned 14400 rows", out)
        self.assertNotIn("returned 0 rows", out)
        self.assertNotIn("failed", self.messages[-1])

    def test_rows_that_lag_the_job_are_waited_for(self):
        org = self.use(FakeOrg(complete_after=0, query_lag=45))
        out = self.validate(self.cp(ingest_state="JobComplete"), org)
        self.assertIn("✓ SDM query returned 14400 rows", out)
        self.assertGreaterEqual(org.count_calls, 2)

    def test_still_loading_is_pending_not_failed(self):
        org = self.use(FakeOrg(complete_after=10 ** 6))
        out = self.validate(self.cp(), org, ingest_budget=0)
        self.assertIn("Data is still loading", out)
        self.assertNotIn("✗ SDM query", out)
        self.assertEqual(org.count_calls, 0)                      # never queried an unfinished load
        self.assertIn("still loading, nothing failed", self.messages[-1])

    def test_failed_ingest_fails_the_check(self):
        org = self.use(FakeOrg(complete_after=0, final="Failed"))
        out = self.validate(self.cp(), org)
        self.assertIn("✗ The Data Cloud ingest job failed", out)
        self.assertIn("failed", self.messages[-1])

    def test_really_empty_after_completion_still_fails(self):
        org = self.use(FakeOrg(complete_after=0, rows=0))
        out = self.validate(self.cp(ingest_state="JobComplete"), org)
        self.assertIn("✗ SDM query returned 0 rows after the data load finished", out)
        self.assertLessEqual(org.clock, 120)                      # brief retry, not a long wait

    def test_old_checkpoint_without_a_job_id_counts_as_before(self):
        org = self.use(FakeOrg(complete_after=0))
        cp = self.cp()
        cp.pop("ingest_job_id"); cp.pop("ingest_state")
        self.assertIn("✓ SDM query returned 14400 rows", self.validate(cp, org))

    def test_build_waits_once_then_validation_only_rechecks(self):
        src = (ROOT / "web-ui" / "builder.py").read_text()
        build = src[src.index("def next_build("):src.index("# CRMA build")]
        self.assertEqual(build.count("wait_for_ingest(config, cp, q)"), 1)
        self.assertLess(build.index("wait_for_ingest(config, cp, q)"), build.index("Testing Concierge prompts"))
        self.assertIn("_validate_next_build(config, cp, metric_config, q, ingest_budget=0)", build)
        self.assertIn('cp["ingest_state"] = state', build)


if __name__ == "__main__":
    unittest.main()
