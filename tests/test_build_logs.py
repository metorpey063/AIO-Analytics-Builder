"""Each build writes its own log; deleting a Pulse demo removes its group; requirements agree
with the known-good set.

    python3 -m unittest tests.test_build_logs -v

No org, site or network is touched.
"""
import queue
import re
import sys
import tempfile
import threading
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
from progress import ProgressChannel  # noqa: E402

try:
    import builder
except ImportError as e:                      # pandas etc. not installed
    builder = None
    BUILDER_SKIP = f"builder dependencies not installed: {e}"


@unittest.skipIf(builder is None, "builder dependencies not installed")
class OneLogPerBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def lines(self, name):
        return (self.tmp / name).read_text().splitlines()

    def test_two_builds_at_once_keep_their_own_logs(self):
        """The live case: a Tableau Next and a Pulse build started together."""
        both_started, results = threading.Barrier(2), {}

        def build(name, n):
            q = ProgressChannel()
            builder.start_build_log(q, str(self.tmp / f"{name}_build.log"), f"=== {name} ===\n")
            both_started.wait(5)              # the other build has now started too
            for i in range(n):
                builder.progress(q, "step", f"{name} line {i}", i)
            results[name] = q

        threads = [threading.Thread(target=build, args=("cobalt_ridge", 200)),
                   threading.Thread(target=build, args=("lumen_harbor", 200))]
        [t.start() for t in threads]
        [t.join(10) for t in threads]

        for name in ("cobalt_ridge", "lumen_harbor"):
            log = self.lines(f"{name}_build.log")
            self.assertEqual(log[0], f"=== {name} ===")
            self.assertEqual(len(log), 201, name)
            self.assertTrue(all(name in line for line in log), f"{name}'s log has another build's lines")

    def test_a_build_that_started_first_keeps_logging_to_its_own_file(self):
        """Old behaviour: after a second build started, the first one's lines went to the second's log."""
        first, second = ProgressChannel(), ProgressChannel()
        builder.start_build_log(first, str(self.tmp / "first.log"), "=== first ===\n")
        builder.progress(first, "init", "first: starting")
        builder.start_build_log(second, str(self.tmp / "second.log"), "=== second ===\n")   # same thread, even
        builder.progress(first, "ingest", "first: ingest")
        builder.progress(second, "init", "second: starting")
        builder.progress(first, "done", "first: done")
        self.assertEqual(self.lines("first.log"),
                         ["=== first ===", "[init] first: starting", "[ingest] first: ingest", "[done] first: done"])
        self.assertEqual(self.lines("second.log"), ["=== second ===", "[init] second: starting"])

    def test_helper_threads_of_a_build_log_to_that_build(self):
        q = ProgressChannel()
        builder.start_build_log(q, str(self.tmp / "a.log"), "=== a ===\n")
        t = threading.Thread(target=builder.progress, args=(q, "poll", "from a helper thread"))
        t.start(); t.join(5)
        self.assertEqual(self.lines("a.log")[-1], "[poll] from a helper thread")

    def test_progress_still_reaches_the_page(self):
        q = ProgressChannel()
        builder.start_build_log(q, str(self.tmp / "a.log"), "h\n")
        builder.progress(q, "ingest", "Ingesting...", 30)
        events, _ = q.read_from(0, timeout=0)
        self.assertEqual(events[0][1], {"stage": "ingest", "message": "Ingesting...", "pct": 30})

    def test_plain_queue_and_no_queue_callers(self):
        q = queue.Queue()                     # CLI paths pass a plain queue, or None
        builder.start_build_log(q, str(self.tmp / "cli.log"), "h\n")
        builder.progress(q, "a", "with a queue")
        builder.progress(None, "b", "no queue: this thread's build log")
        self.assertEqual(self.lines("cli.log"), ["h", "[a] with a queue", "[b] no queue: this thread's build log"])

    def test_nothing_is_logged_before_a_build_starts(self):
        done = []

        def fresh_thread():
            builder.progress(mock.Mock(), "x", "no log file yet")   # must not raise or write anywhere
            done.append(builder._log_path_for(mock.Mock()))

        t = threading.Thread(target=fresh_thread); t.start(); t.join(5)
        self.assertEqual(done, [None])

    def test_no_shared_log_path_is_left(self):
        self.assertFalse(hasattr(builder, "_build_log_file"))
        self.assertNotIn("global _build_log_file", (ROOT / "web-ui" / "builder.py").read_text())


class PulseGroupCleanup(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        p = mock.patch.object(connections, "CONFIG_FILE", str(tmp / "config.json"))
        p.start(); self.addCleanup(p.stop)
        connections.save_full_config({"active_salesforce": None, "active_tableau_cloud": "site",
                                      "profiles": {"site": {"label": "Site", "tableau": {"pat_secret": "x"}}}})
        self.server = mock.Mock(server_address="https://site.example/", version="3.27")
        p = mock.patch.object(connections, "get_tableau_token", return_value=(self.server, "tok", "SITE1"))
        p.start(); self.addCleanup(p.stop)
        self.deleted, self.status = [], 204

        def fake_delete(url, headers=None, timeout=None, **kw):
            self.deleted.append(url)
            return mock.Mock(ok=self.status < 400, status_code=self.status)

        p = mock.patch("aio_http.delete", side_effect=fake_delete); p.start(); self.addCleanup(p.stop)

    CP = {"build_type": "pulse", "_profile_key": "site", "pulse_def_ids": ["d1", "d2"],
          "pulse_project_id": "p1", "pulse_project_name": "Lumen Harbor Logistics",
          "pulse_group_id": "g-123", "pulse_group_name": "Lumen Harbor Logistics | 2026-11-16 15:40"}

    def test_group_is_deleted_by_its_checkpoint_id(self):
        results = webapp._delete_remote_assets(dict(self.CP))
        groups = [u for u in self.deleted if "/groups/" in u]
        self.assertEqual(groups, ["https://site.example/api/3.27/sites/SITE1/groups/g-123"])
        self.assertIn("Group Lumen Harbor Logistics | 2026-11-16 15:40: deleted", results)
        self.server.projects.delete.assert_called_once_with("p1")
        self.server.auth.sign_out.assert_called_once()

    def test_groups_are_never_listed_or_matched_by_name(self):
        with mock.patch("aio_http.get") as get:
            webapp._delete_remote_assets(dict(self.CP))
        get.assert_not_called()
        self.assertEqual(len([u for u in self.deleted if "/groups" in u]), 1)

    def test_no_group_id_means_no_group_call(self):
        cp = {k: v for k, v in self.CP.items() if not k.startswith("pulse_group")}
        webapp._delete_remote_assets(cp)
        self.assertFalse([u for u in self.deleted if "/groups" in u])

    def test_a_group_already_gone_counts_as_deleted(self):
        self.status = 404
        results = webapp._delete_remote_assets({"build_type": "pulse", "_profile_key": "site", "pulse_group_id": "g-123"})
        self.assertIn("Group g-123: deleted", results)

    def test_a_failed_delete_is_reported(self):
        self.status = 403
        results = webapp._delete_remote_assets({"build_type": "pulse", "_profile_key": "site", "pulse_group_id": "g-123"})
        self.assertIn("Group g-123: 403", results)

    def test_build_saves_the_group_name_with_its_id(self):
        src = (ROOT / "web-ui" / "builder.py").read_text()
        self.assertIn('cp["pulse_group_name"] = group_name', src)


class Requirements(unittest.TestCase):
    def vt(self, v):
        return tuple(int(x) for x in re.findall(r"\d+", v)[:4])

    def test_known_good_versions_satisfy_requirements(self):
        good = {}
        for line in (ROOT / "requirements-known-good.txt").read_text().splitlines():
            if "==" in line and not line.startswith("#"):
                name, version = line.split("==")
                good[name.lower().replace("_", "-")] = version
        for line in (ROOT / "requirements.txt").read_text().split():
            m = re.fullmatch(r"([A-Za-z0-9_.\-]+)>=([0-9.]+)(?:,<([0-9.]+))?", line)
            self.assertIsNotNone(m, f"unexpected requirement line: {line}")
            name, low, high = m.groups()
            have = good[name.lower()]
            self.assertGreaterEqual(self.vt(have), self.vt(low), line)
            if high:
                self.assertLess(self.vt(have), self.vt(high), line)

    def test_updater_still_reads_every_line(self):
        """deps.py and install.py parse requirements.txt themselves: no comments, one `>=` first."""
        import deps
        lines = (ROOT / "requirements.txt").read_text().split()
        self.assertTrue(all(re.match(r"^[A-Za-z0-9_.\-]+>=", l) for l in lines))
        with mock.patch.object(deps.md, "version", return_value="0.0.1"):       # everything too old
            self.assertEqual(deps.missing(), lines)
        with mock.patch.object(deps.md, "version", return_value="999.0"):       # newer than any bound
            self.assertEqual(deps.missing(), [])        # an installed package is never forced down by the updater


if __name__ == "__main__":
    unittest.main()
