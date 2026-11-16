"""aio_http: requests with a default timeout, and nothing else changed.

    python3 -m unittest tests.test_aio_http -v
"""
import http.server
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
import aio_http  # noqa: E402

BUILD_PATH = ["connections.py", "web-ui/builder.py", "web-ui/app.py", "web-ui/mcp_client.py", "crm_upserter.py",
              "template_deployer.py", "transfer_assets.py", "close_loop.py", "crma_uploader.py",
              "crma_dashboard_builder.py", "prep_flow_builder.py", "salesinsights/deploy.py",
              "compose_dashboard_runner.py"]


class DefaultTimeout(unittest.TestCase):
    def call(self, fn, *args, **kwargs):
        with mock.patch.object(requests, "request", return_value="resp") as real:
            self.assertEqual(fn(*args, **kwargs), "resp")
        return real.call_args

    def test_every_verb_gets_the_default(self):
        for verb in ("get", "post", "put", "patch", "delete", "head", "options"):
            args, kwargs = self.call(getattr(aio_http, verb), "https://x.example/a")
            self.assertEqual(args, (verb, "https://x.example/a"), verb)
            self.assertEqual(kwargs["timeout"], aio_http.DEFAULT_TIMEOUT, verb)

    def test_a_callers_own_timeout_wins(self):
        self.assertEqual(self.call(aio_http.get, "https://x", timeout=5)[1]["timeout"], 5)
        self.assertIsNone(self.call(aio_http.post, "https://x", timeout=None)[1]["timeout"])

    def test_arguments_pass_through_unchanged(self):
        _, kw = self.call(aio_http.post, "https://x", data="d", json={"a": 1}, headers={"h": "1"}, verify="/ca.pem")
        self.assertEqual((kw["data"], kw["json"], kw["headers"], kw["verify"]), ("d", {"a": 1}, {"h": "1"}, "/ca.pem"))
        _, kw = self.call(aio_http.get, "https://x", {"q": "1"})          # params given positionally
        self.assertEqual(kw["params"], {"q": "1"})
        _, kw = self.call(aio_http.put, "https://x", b"csv")              # data given positionally
        self.assertEqual(kw["data"], b"csv")

    def test_default_never_shortens_a_working_call(self):
        connect, read = aio_http.DEFAULT_TIMEOUT
        self.assertGreaterEqual(read, 600)      # Salesforce's own limit for a synchronous request
        self.assertGreaterEqual(connect, 10)

    def test_everything_else_is_requests_itself(self):
        self.assertIs(aio_http.exceptions, requests.exceptions)
        self.assertIs(aio_http.RequestException, requests.RequestException)
        self.assertIs(aio_http.HTTPError, requests.HTTPError)
        self.assertIs(aio_http.utils, requests.utils)
        with self.assertRaises(AttributeError):
            aio_http.no_such_thing


class RealRequests(unittest.TestCase):
    """Against a local server: same responses as requests, and a stalled server now ends the call."""

    @classmethod
    def setUpClass(cls):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/stall":
                    cls.release.wait(10)          # accept the request, then say nothing
                    return
                body = b'{"ok": true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(n)
                self.send_response(201)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        cls.release = threading.Event()
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.release.set()
        cls.server.shutdown()

    def test_same_result_as_requests(self):
        no_proxy = {"http": None, "https": None}
        a = aio_http.get(self.base + "/x", proxies=no_proxy)
        b = requests.get(self.base + "/x", proxies=no_proxy)
        self.assertEqual((a.status_code, a.json()), (b.status_code, b.json()))
        r = aio_http.post(self.base + "/echo", json={"k": "v"}, proxies=no_proxy)
        self.assertEqual((r.status_code, r.json()), (201, {"k": "v"}))

    def test_a_stalled_server_no_longer_hangs_the_caller(self):
        with mock.patch.object(aio_http, "DEFAULT_TIMEOUT", (2, 0.5)):
            with self.assertRaises(aio_http.exceptions.Timeout):      # same exception type callers already catch
                aio_http.get(self.base + "/stall", proxies={"http": None, "https": None})


class BuildPathUsesIt(unittest.TestCase):
    def test_no_bare_requests_import_on_the_build_path(self):
        import re
        for rel in BUILD_PATH:
            src = (ROOT / rel).read_text()
            self.assertIsNone(re.search(r"^\s*import requests\b", src, re.M), rel)
            self.assertIn("import aio_http as", src, rel)

    def test_modules_import_and_see_the_wrapper(self):
        import types
        sys.modules.setdefault("tableauserverclient", types.ModuleType("tableauserverclient"))
        import connections, crm_upserter
        self.assertIs(connections.requests, aio_http)
        self.assertIs(crm_upserter.requests, aio_http)


if __name__ == "__main__":
    unittest.main()
