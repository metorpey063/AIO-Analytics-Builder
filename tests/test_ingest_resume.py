"""The Tableau Next ingest step survives a dropped status check and a build resumed mid-load.

Seen 2026-11-17 on AIO Dev:
- one status check got ('Connection aborted.', ConnectionResetError(54, ...)) and the whole build
  failed, because the 5-minute ingest loop only handled error responses;
- running that build again failed with 409 Conflict: its earlier job was still loading (Data Cloud
  allows one open job per object) and the checkpoint didn't have the job ID yet.

    python3 -m unittest tests.test_ingest_resume -v

No org or network: Data Cloud is a fake, and waiting uses a fake clock.
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

import aio_http  # noqa: E402

try:
    import builder
except ImportError:                       # pandas etc. not installed
    builder = None

DC = "dc.example"
OBJ = "acme_demo"


def resp(status=200, body=None):
    r = mock.Mock(status_code=status, ok=200 <= status < 300, text=str(body))
    r.json.return_value = body or {}
    if status >= 400:
        r.raise_for_status.side_effect = Exception(f"{status} Client Error")
    return r


class FakeDataCloud:
    """Jobs keyed by id: state plus how many more polls until it finishes."""

    def __init__(self):
        self.jobs, self.created, self.aborted, self.clock = {}, [], [], 0
        self.fail_next_status = 0

    def add(self, job_id, state, polls_left=0, final="JobComplete", obj=OBJ):
        self.jobs[job_id] = {"state": state, "left": polls_left, "final": final, "object": obj}

    def sleep(self, s):
        self.clock += s

    def get(self, url, headers=None, params=None, timeout=None, **kw):
        if url.endswith("/api/v1/ingest/jobs"):
            return resp(200, {"data": [{"id": k, "state": j["state"], "object": j["object"]} for k, j in self.jobs.items()]})
        job_id = url.rsplit("/", 1)[1]
        if self.fail_next_status:
            self.fail_next_status -= 1
            raise ConnectionResetError(54, "Connection reset by peer")
        j = self.jobs[job_id]
        if j["state"] in ("UploadComplete", "InProgress"):
            if j["left"] <= 0:
                j["state"] = j["final"]
            else:
                j["left"] -= 1
        return resp(200, {"state": j["state"]})

    def post(self, url, headers=None, json=None, **kw):
        if any(j["object"] == json["object"] and j["state"] in builder.INGEST_OPEN_STATES for j in self.jobs.values()):
            return resp(409, {"error": "Conflict"})
        job_id = f"new{len(self.created) + 1}"
        self.add(job_id, "Open")
        self.created.append(job_id)
        return resp(201, {"id": job_id})

    def patch(self, url, headers=None, json=None, **kw):
        job_id = url.rsplit("/", 1)[1]
        if json.get("state") == "Aborted":
            self.aborted.append(job_id)
        self.jobs[job_id]["state"] = json["state"]
        return resp(200, {"state": json["state"]})


@unittest.skipIf(builder is None, "builder dependencies not installed")
class IngestResume(unittest.TestCase):
    def setUp(self):
        self.dc = FakeDataCloud()
        for name in ("get", "post", "patch"):
            p = mock.patch.object(aio_http, name, side_effect=getattr(self.dc, name))
            p.start()
            self.addCleanup(p.stop)
        self.msgs = []
        p = mock.patch.object(builder, "progress", side_effect=lambda q, s, m, pct=-1: self.msgs.append(m))
        p.start()
        self.addCleanup(p.stop)

    def create(self, cp):
        return builder._create_ingest_job(DC, {}, {"object": OBJ, "sourceName": "c", "operation": "upsert"},
                                          cp, None, sleep=self.dc.sleep, poll=20, budget=1200)

    # -- dropped status checks ------------------------------------------------------------
    def test_dropped_connection_is_a_failed_check_not_a_failed_job(self):
        self.dc.add("j1", "InProgress", polls_left=5)
        self.dc.fail_next_status = 1
        self.assertIsNone(builder._ingest_job_state(DC, {}, "j1"))
        self.assertEqual(builder._ingest_job_state(DC, {}, "j1"), "InProgress")

    def test_error_response_is_a_failed_check(self):
        with mock.patch.object(aio_http, "get", return_value=resp(503, {})):
            self.assertIsNone(builder._ingest_job_state(DC, {}, "j1"))

    # -- resuming a build whose earlier job is still around --------------------------------
    def test_resume_waits_for_a_running_earlier_job_then_loads_this_run(self):
        self.dc.add("old", "InProgress", polls_left=3)
        cp = {"ingest_job_pending": "old"}
        builder._clear_previous_ingest(DC, {}, cp, OBJ, None, sleep=self.dc.sleep, poll=20, budget=1200)
        self.assertEqual(self.dc.jobs["old"]["state"], "JobComplete")
        self.assertNotIn("ingest_job_pending", cp)
        self.assertEqual(self.create(cp), "new1")
        self.assertEqual(self.dc.aborted, [])

    def test_resume_with_a_finished_earlier_job_just_creates(self):
        self.dc.add("old", "JobComplete")
        cp = {"ingest_job_pending": "old"}
        builder._clear_previous_ingest(DC, {}, cp, OBJ, None, sleep=self.dc.sleep)
        self.assertEqual(self.dc.clock, 0)
        self.assertEqual(self.create(cp), "new1")

    def test_resume_with_a_failed_earlier_job_just_creates(self):
        self.dc.add("old", "Failed")
        cp = {"ingest_job_pending": "old"}
        builder._clear_previous_ingest(DC, {}, cp, OBJ, None, sleep=self.dc.sleep)
        self.assertEqual(self.create(cp), "new1")

    def test_resume_aborts_this_builds_unfinished_upload(self):
        self.dc.add("old", "Open")
        cp = {"ingest_job_pending": "old"}
        builder._clear_previous_ingest(DC, {}, cp, OBJ, None, sleep=self.dc.sleep)
        self.assertEqual(self.dc.aborted, ["old"])
        self.assertEqual(self.create(cp), "new1")

    def test_still_running_after_the_budget_stops_with_a_clear_message(self):
        self.dc.add("old", "InProgress", polls_left=10_000)
        with self.assertRaisesRegex(RuntimeError, "still running after 20 min"):
            builder._clear_previous_ingest(DC, {}, {"ingest_job_pending": "old"}, OBJ, None,
                                           sleep=self.dc.sleep, poll=20, budget=1200)

    # -- 409 Conflict on create (the checkpoint didn't know about the job) -----------------
    def test_409_waits_for_the_open_job_then_retries_once(self):
        self.dc.add("orphan", "InProgress", polls_left=2)          # lost from the checkpoint
        cp = {}
        self.assertEqual(self.create(cp), "new1")
        self.assertEqual(self.dc.jobs["orphan"]["state"], "JobComplete")
        self.assertTrue(any("already open" in m for m in self.msgs))

    def test_409_never_aborts_an_open_job_aio_did_not_create(self):
        self.dc.add("someone_elses", "Open")
        with self.assertRaisesRegex(RuntimeError, "wasn't started by this build"):
            self.create({})
        self.assertEqual(self.dc.aborted, [])

    def test_open_jobs_on_other_objects_are_ignored(self):
        self.dc.add("other", "InProgress", polls_left=10_000, obj="another_demo")
        self.assertEqual(self.create({}), "new1")
        self.assertEqual(self.dc.clock, 0)


if __name__ == "__main__":
    unittest.main()
