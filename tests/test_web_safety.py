"""Web UI safety: request guards, demo-folder names, config writes, progress replay, updater.

    python3 -m unittest tests.test_web_safety -v

No org, Tableau site or network is touched: the app runs under Flask's test client against a
temporary project folder, and the build itself is replaced by a fake.
"""
import json
import os
import stat
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

# connections.py imports the Tableau client at module level; these tests never call it
sys.modules.setdefault("tableauserverclient", types.ModuleType("tableauserverclient"))

import connections  # noqa: E402
import progress  # noqa: E402
import app as webapp  # noqa: E402

LOCAL = {"Host": "localhost:5100"}


class TempProject(unittest.TestCase):
    """Point the app and the config store at a throwaway folder."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "demos").mkdir()
        (self.tmp / "keep.txt").write_text("project file")
        self.cfg = self.tmp / "config.json"
        patches = [
            mock.patch.object(webapp, "PROJECT_ROOT", self.tmp),
            mock.patch.object(webapp, "DEMOS_ROOT", self.tmp / "demos"),
            mock.patch.object(webapp, "CONFIG_PATH", self.cfg),
            mock.patch.object(connections, "CONFIG_FILE", str(self.cfg)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        webapp.progress_queues.clear()
        self.client = webapp.app.test_client()

    def demo(self, slug):
        d = self.tmp / "demos" / slug
        d.mkdir()
        (d / f"{slug}_checkpoint.json").write_text("{}")
        return d


class RequestGuards(TempProject):
    def test_local_browser_requests_pass(self):
        self.demo("acme")
        r = self.client.post("/api/demos/acme/delete", headers={**LOCAL, "Origin": "http://localhost:5100",
                                                                "Sec-Fetch-Site": "same-origin"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_loopback_ip_and_scripts_pass(self):
        # 127.0.0.1 in the address bar, and curl-style clients with no browser headers
        self.demo("acme")
        r = self.client.post("/api/demos/acme/delete", headers={"Host": "127.0.0.1:5100"})
        self.assertEqual(r.status_code, 200)

    def test_foreign_host_is_refused(self):
        # DNS rebinding: attacker.example re-pointed at 127.0.0.1
        r = self.client.get("/api/profiles/list", headers={"Host": "attacker.example:5100"})
        self.assertEqual(r.status_code, 403)

    def test_cross_site_post_is_refused(self):
        with mock.patch.object(webapp, "_schedule_restart") as restart:
            r = self.client.post("/api/restart", headers={**LOCAL, "Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        restart.assert_not_called()

    def test_other_local_port_is_refused(self):
        d = self.demo("acme")
        r = self.client.post("/api/demos/acme/delete", headers={**LOCAL, "Origin": "http://localhost:3000"})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(d.exists())

    def test_cross_site_get_to_api_is_refused(self):
        # e.g. <img src="http://localhost:5100/api/demos/x/open"> on another site
        self.demo("acme")
        with mock.patch("subprocess.Popen") as popen:
            r = self.client.get("/api/demos/acme/open", headers={**LOCAL, "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(r.status_code, 403)
        popen.assert_not_called()

    def test_static_files_in_subfolders_are_served(self):
        for path in ("/static/js/app.js", "/static/css/style.css", "/static/img/templates/z_layout.png"):
            r = self.client.get(path, headers=LOCAL)
            self.assertEqual(r.status_code, 200, path)
            r.close()

    def test_every_page_renders(self):
        for path in ("/", "/build", "/demos", "/setup", "/connections", "/transfer-assets",
                     "/deploy-sales-insights", "/update-rev-intel"):
            self.assertEqual(self.client.get(path, headers=LOCAL).status_code, 200, path)

    def test_links_into_pages_still_work(self):
        # A link to the app from Slack or a doc is a cross-site navigation to a page, not an API call
        r = self.client.get("/build", headers={**LOCAL, "Sec-Fetch-Site": "cross-site"})
        self.assertNotEqual(r.status_code, 403)


class DemoFolderNames(TempProject):
    def test_dotdot_cannot_delete_the_project(self):
        for path in ("/api/demos/../delete", "/api/demos/%2e%2e/delete", "/api/demos/./delete"):
            r = self.client.post(path, headers=LOCAL)
            self.assertIn(r.status_code, (404, 405), path)
        self.assertTrue((self.tmp / "keep.txt").exists())
        self.assertTrue((self.tmp / "demos").exists())

    def test_safe_name(self):
        for good in ("acme", "waste_connections_route_ops", "Acme Corp", "a-b.c", "acme_walkthrough.docx"):
            self.assertTrue(webapp._safe_name(good), good)
        for bad in ("", ".", "..", ".hidden", "a/b", "a\\b", "a\x00b", None, 5, "x" * 151):
            self.assertFalse(webapp._safe_name(bad), repr(bad))

    def test_demo_dir_refuses_symlink_out_of_demos(self):
        outside = Path(tempfile.mkdtemp())
        os.symlink(outside, self.tmp / "demos" / "link")
        with self.assertRaises(ValueError):
            webapp._demo_dir("link")

    def test_delete_removes_only_the_demo(self):
        d = self.demo("acme")
        other = self.demo("other")
        r = self.client.post("/api/demos/acme/delete", headers=LOCAL)
        self.assertTrue(r.get_json()["ok"])
        self.assertFalse(d.exists())
        self.assertTrue(other.exists())

    def test_close_loop_deploy_rejects_bad_slug(self):
        with mock.patch("subprocess.run") as run:
            r = self.client.post("/api/close-loop/deploy", json={"slug": "../.."}, headers=LOCAL)
        self.assertFalse(r.get_json()["ok"])
        run.assert_not_called()


class ConfigStore(TempProject):
    def test_save_is_private_and_complete(self):
        connections.save_full_config({"profiles": {"a": {"label": "A"}}})
        self.assertEqual(stat.S_IMODE(self.cfg.stat().st_mode), 0o600)
        self.assertEqual(json.loads(self.cfg.read_text())["profiles"]["a"]["label"], "A")
        self.assertEqual([p.name for p in self.tmp.glob(".config.json.*")], [])   # no temp files left

    def test_failed_save_keeps_the_old_file(self):
        connections.save_full_config({"ok": 1})
        with self.assertRaises(TypeError):
            connections.save_full_config({"bad": object()})
        self.assertEqual(json.loads(self.cfg.read_text()), {"ok": 1})
        self.assertEqual([p.name for p in self.tmp.glob(".config.json.*")], [])

    def test_secure_config_file_tightens_old_installs(self):
        self.cfg.write_text("{}")
        os.chmod(self.cfg, 0o644)
        connections.secure_config_file()
        self.assertEqual(stat.S_IMODE(self.cfg.stat().st_mode), 0o600)

    def test_concurrent_updates_are_not_lost(self):
        connections.save_full_config({"n": 0, "profiles": {}, "active_salesforce": None,
                                      "active_tableau_cloud": None})

        def bump():
            for _ in range(40):
                with connections.config_lock():
                    full = connections.load_full_config()
                    full["n"] += 1
                    connections.save_full_config(full)

        threads = [threading.Thread(target=bump) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(connections.load_full_config()["n"], 320)

    def test_other_processes_wait_for_the_lock(self):
        """The CLI tools and Web UI job subprocesses share config.json with the server."""
        import subprocess
        connections.save_full_config({"n": 0, "profiles": {}, "active_salesforce": None,
                                      "active_tableau_cloud": None})
        code = ("import sys, types; sys.modules['tableauserverclient'] = types.ModuleType('t'); "
                f"sys.path.insert(0, {str(ROOT)!r}); import connections as c; c.CONFIG_FILE = {str(self.cfg)!r}\n"
                "for _ in range(40):\n"
                "    with c.config_lock():\n"
                "        full = c.load_full_config(); full['n'] += 1; c.save_full_config(full)\n")
        procs = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(4)]
        self.assertEqual([p.wait(60) for p in procs], [0, 0, 0, 0])
        self.assertEqual(connections.load_full_config()["n"], 160)

    def test_lock_is_reentrant(self):
        with connections.config_lock():
            with connections.config_lock():
                connections.save_full_config({"x": 1})
        self.assertEqual(json.loads(self.cfg.read_text()), {"x": 1})

    def test_token_refresh_keeps_a_concurrent_change(self):
        """A refresh must merge into the file as it is now, not overwrite it with an older copy."""
        base = {"active_salesforce": "p", "active_tableau_cloud": None,
                "profiles": {"p": {"label": "P", "salesforce": {
                    "sf_login_url": "https://login.example", "client_id": "cid", "refresh_token": "old"}}}}
        connections.save_full_config(base)
        config = {"salesforce": dict(base["profiles"]["p"]["salesforce"])}

        def fake_post(url, data=None, **kw):
            # While the token call is in flight, the user saves an API key in the Web UI
            full = connections.load_full_config()
            full["anthropic"] = {"api_key": "saved-during-refresh"}
            connections.save_full_config(full)
            resp = mock.Mock(status_code=200, text="")
            resp.json.return_value = {"access_token": "at", "instance_url": "https://org.example",
                                      "refresh_token": "rotated"}
            return resp

        with mock.patch.object(connections.requests, "post", side_effect=fake_post):
            token, instance = connections.get_sf_token(config, profile_key="p")
        after = connections.load_full_config()
        self.assertEqual(token, "at")
        self.assertEqual(after["profiles"]["p"]["salesforce"]["refresh_token"], "rotated")
        self.assertEqual(after["anthropic"]["api_key"], "saved-during-refresh")


class ProgressReplay(unittest.TestCase):
    def test_every_reader_sees_every_event(self):
        ch = progress.ProgressChannel()
        for i in range(3):
            ch.put({"stage": "log", "message": str(i)})
        first, cur1 = ch.read_from(0, timeout=0)
        second, cur2 = ch.read_from(0, timeout=0)     # a second tab, or a reload
        self.assertEqual([m["message"] for _, m in first], ["0", "1", "2"])
        self.assertEqual(first, second)
        self.assertEqual(cur1, 3)

    def test_resume_after_last_seen(self):
        ch = progress.ProgressChannel()
        for i in range(5):
            ch.put({"stage": "log", "message": str(i)})
        events, _ = ch.read_from(3, timeout=0)
        self.assertEqual([i for i, _ in events], [3, 4])

    def test_reader_wakes_when_an_event_arrives(self):
        ch = progress.ProgressChannel()
        threading.Timer(0.1, ch.put, [{"stage": "done", "message": "ok"}]).start()
        events, _ = ch.read_from(0, timeout=5)
        self.assertEqual(events[0][1]["stage"], "done")
        self.assertTrue(ch.finished)
        self.assertFalse(ch.running())

    def test_old_events_drop_but_cursors_hold(self):
        ch = progress.ProgressChannel()
        with mock.patch.object(progress, "MAX_EVENTS", 10):
            for i in range(25):
                ch.put({"stage": "log", "message": str(i)})
        events, cursor = ch.read_from(0, timeout=0)
        self.assertEqual([i for i, _ in events], list(range(15, 25)))
        self.assertEqual(cursor, 25)

    def test_prune_keeps_running_jobs(self):
        chans = {}
        for i in range(30):
            c = chans[f"done{i}"] = progress.ProgressChannel()
            c.put({"stage": "done"})
        chans["live"] = progress.ProgressChannel()
        progress.prune(chans)
        self.assertIn("live", chans)
        self.assertEqual(len(chans), progress.MAX_FINISHED_CHANNELS + 1)
        self.assertNotIn("done0", chans)
        self.assertIn("done29", chans)


class BuildJobs(TempProject):
    def start_fake_build(self):
        """Replace the real build with one that reports two lines, then waits to be released."""
        release, calls = threading.Event(), []

        def run_build(build_id, build_config, q):
            calls.append(build_id)
            q.put({"stage": "start", "message": "one", "pct": 1})
            q.put({"stage": "log", "message": "two", "pct": 2})
            release.wait(5)
            q.put({"stage": "done", "message": "finished", "pct": 100})

        fake = types.ModuleType("builder")
        fake.run_build = run_build
        p = mock.patch.dict(sys.modules, {"builder": fake})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(release.set)
        return release, calls

    def read_stream(self, build_id, headers=None):
        r = self.client.get(f"/api/build/progress/{build_id}", headers={**LOCAL, **(headers or {})})
        return [json.loads(line[6:]) for line in r.get_data(as_text=True).splitlines() if line.startswith("data: ")]

    def test_second_start_joins_the_running_build(self):
        release, calls = self.start_fake_build()
        a = self.client.post("/api/build/start", json={"company": "Acme Corp"}, headers=LOCAL).get_json()
        b = self.client.post("/api/build/start", json={"company": "Acme Corp"}, headers=LOCAL).get_json()
        self.assertTrue(a["ok"] and b["ok"])
        self.assertEqual(a["build_id"], b["build_id"])
        self.assertTrue(b.get("already_running"))
        release.set()
        webapp.progress_queues[a["build_id"]].thread.join(5)
        self.assertEqual(calls, ["acme_corp"])          # one build ran, not two

    def test_stream_replays_and_resumes(self):
        release, _ = self.start_fake_build()
        bid = self.client.post("/api/build/start", json={"company": "Acme"}, headers=LOCAL).get_json()["build_id"]
        release.set()
        webapp.progress_queues[bid].thread.join(5)
        full = [m["message"] for m in self.read_stream(bid)]
        again = [m["message"] for m in self.read_stream(bid)]           # reload: same history
        tail = [m["message"] for m in self.read_stream(bid, {"Last-Event-ID": "0"})]   # auto-reconnect
        self.assertEqual(full, ["one", "two", "finished"])
        self.assertEqual(again, full)
        self.assertEqual(tail, ["two", "finished"])

    def test_finished_build_can_be_started_again(self):
        release, calls = self.start_fake_build()
        release.set()
        for _ in range(2):
            bid = self.client.post("/api/build/start", json={"company": "Acme"}, headers=LOCAL).get_json()["build_id"]
            webapp.progress_queues[bid].thread.join(5)
        self.assertEqual(calls, ["acme", "acme"])

    def test_crashed_build_releases_the_page(self):
        fake = types.ModuleType("builder")
        fake.run_build = mock.Mock(side_effect=SystemExit(1))
        with mock.patch.dict(sys.modules, {"builder": fake}):
            bid = self.client.post("/api/build/start", json={"company": "Boom"}, headers=LOCAL).get_json()["build_id"]
            webapp.progress_queues[bid].thread.join(5)
        self.assertEqual(self.read_stream(bid)[-1]["stage"], "error")

    def test_unknown_build(self):
        self.assertEqual(self.read_stream("nope")[0]["message"], "Unknown build")


class Updater(TempProject):
    def test_update_never_touches_the_stash(self):
        cmds = []

        def fake_run(cmd, **kw):
            cmds.append(cmd)
            return mock.Mock(returncode=0, stdout="abc123\n", stderr="")

        with mock.patch("subprocess.run", side_effect=fake_run):
            r = self.client.post("/api/update", headers=LOCAL)
        self.assertTrue(r.get_json()["ok"])
        self.assertIn(["git", "reset", "--hard", "origin/main"], cmds)
        self.assertFalse([c for c in cmds if "stash" in c])


class JobRunners(unittest.TestCase):
    def test_background_tools_use_this_interpreter(self):
        src = (ROOT / "web-ui" / "app.py").read_text()
        self.assertNotIn('["python3"', src)

    def test_debugger_is_off_unless_asked(self):
        src = (ROOT / "web-ui" / "app.py").read_text()
        self.assertNotIn("debug=True", src)


if __name__ == "__main__":
    unittest.main()
