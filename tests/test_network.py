import json
import socket
import struct
import threading
import unittest
import urllib.request
from http.cookiejar import CookieJar

from werkzeug.serving import make_server

from backend.networking import request_manager
from backend.networking.network_monitor import MONITOR
from backend.networking.rate_limiter import SlidingWindowLimiter
from backend.networking.tcp_demo_client import framing_experiment
from backend.networking.tcp_demo_server import MAX_FRAME, recv_exact, recv_msg, send_msg
from backend.services import concurrency_service
from tests.base import H, NetVoteTestCase


class HttpBehaviourTests(NetVoteTestCase):
    def test_security_headers(self):
        r = self.c.get("/login.html")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("script-src 'self'", r.headers["Content-Security-Policy"])

    def test_error_codes_are_json_with_request_id(self):
        r = self.c.get("/api/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.get_json()["error"]["code"], "NOT_FOUND")
        self.assertIn("request_id", r.get_json())
        r = self.c.delete("/api/candidates", headers=H)
        self.assertEqual(r.status_code, 405)                         # invalid HTTP method
        self.assertEqual(r.get_json()["error"]["code"], "METHOD_NOT_ALLOWED")

    def test_csrf_header_required_for_writes(self):
        r = self.c.post("/api/auth/login", json={"voter_id": "10012", "password": "Voter@123"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"]["code"], "CSRF_BLOCKED")

    def test_unhandled_exception_hides_stack_trace(self):
        @self.app.get("/api/boom")
        def boom():
            raise RuntimeError("secret internal detail")
        r = self.c.get("/api/boom")
        self.assertEqual(r.status_code, 500)
        body = r.get_data(as_text=True)
        self.assertNotIn("secret internal detail", body)
        self.assertNotIn("Traceback", body)
        self.assertRegex(r.get_json()["request_id"], r"^REQ-")

    def test_oversized_body_rejected(self):
        r = self.c.post("/api/auth/login", data="x" * 70000, headers=H)
        self.assertEqual(r.status_code, 413)

    def test_page_allowlist_blocks_traversal(self):
        self.assertEqual(self.c.get("/..%2Fconfig.py").status_code, 404)
        self.assertEqual(self.c.get("/config.py").status_code, 404)

    def test_monitor_counts_real_requests(self):
        MONITOR.reset()
        for _ in range(5):
            self.c.get("/api/candidates")
        self.c.get("/api/nope")
        s = MONITOR.snapshot()
        self.assertEqual(s["total_requests"], 6)
        self.assertEqual(s["successful"], 5)
        self.assertEqual(s["failed"], 1)
        self.assertEqual(s["status_codes"]["404"], 1)
        self.assertGreaterEqual(s["requests_per_second"], 0)
        self.assertEqual(s["active_connections"], 0)

    def test_requests_table_persisted_by_background_writer(self):
        self.login_voter()
        self.post("/api/vote", {"candidate_id": 1, "request_id": "REQ-2026-TRACE001"})
        request_manager.LOG_WRITER.flush()
        from backend.database.database import db
        with db(self.db_path) as c:
            row = c.execute("SELECT request_type,response_code FROM requests WHERE request_id='REQ-2026-TRACE001'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["request_type"], "POST /api/vote")


class RateLimitTests(NetVoteTestCase):
    rate_limit = True

    def test_sensitive_endpoint_returns_429(self):
        codes = [self.login_voter(pw="wrong").status_code for _ in range(25)]
        self.assertEqual(codes[:20], [401] * 20)
        self.assertEqual(set(codes[20:]), {429})
        r = self.login_voter(pw="wrong")
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.get_json()["error"]["code"], "RATE_LIMITED")
        self.assertIn("Retry-After", r.headers)
        self.assertGreaterEqual(request_manager.sensitive_limiter.stats()["blocked"], 5)

    def test_rate_limit_event_audited_once(self):
        for _ in range(30):
            self.login_voter(pw="wrong")
        from backend.database.database import db
        with db(self.db_path) as c:
            n = c.execute("SELECT COUNT(*) FROM audit_logs WHERE action='RATE_LIMIT_TRIGGERED'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_limiter_unit_window(self):
        lim = SlidingWindowLimiter(3, 0.2)
        self.assertEqual([lim.check("a")[0] for _ in range(4)], [True, True, True, False])
        self.assertTrue(lim.check("b")[0])                           # other client unaffected
        import time
        time.sleep(0.25)
        self.assertTrue(lim.check("a")[0])                           # window slid


class TcpFramingTests(unittest.TestCase):
    def test_roundtrip_and_prefix_format(self):
        a, b = socket.socketpair()
        frame = send_msg(a, "HELLO|CLIENT001")
        self.assertEqual(frame[:4], struct.pack("!I", len("HELLO|CLIENT001")))
        self.assertEqual(recv_msg(b)[0], "HELLO|CLIENT001")
        a.close(); b.close()

    def test_recv_exact_reassembles_partial_reads(self):
        a, b = socket.socketpair()
        payload = b"X" * 1000
        threading.Thread(target=lambda: [a.send(payload[i:i + 7]) for i in range(0, 1000, 7)]).start()
        self.assertEqual(recv_exact(b, 1000), payload)
        a.close(); b.close()

    def test_two_messages_one_stream_are_split_correctly(self):
        a, b = socket.socketpair()
        send_msg(a, "ONE"); send_msg(a, "TWO")                       # may arrive in a single recv()
        self.assertEqual((recv_msg(b)[0], recv_msg(b)[0]), ("ONE", "TWO"))
        a.close(); b.close()

    def test_oversized_frame_rejected(self):
        a, b = socket.socketpair()
        a.sendall(struct.pack("!I", MAX_FRAME + 1))
        with self.assertRaises(ValueError):
            recv_msg(b)
        a.close(); b.close()

    def test_connection_closed_detected(self):
        a, b = socket.socketpair()
        a.close()
        with self.assertRaises(ConnectionError):
            recv_msg(b)
        b.close()

    def test_unframed_recv_merges_messages(self):
        self.assertTrue(framing_experiment()["merged"])

    def test_full_protocol_session(self):
        out = concurrency_service.tcp_demo()
        replies = [t["text"] for t in out["transcript"] if t["dir"] == "server"]
        self.assertEqual(replies[0], "WELCOME|CLIENT001")
        self.assertEqual(replies[1], "AUTH_OK")
        self.assertTrue(replies[2].startswith("VOTE_ACK|VOTE-"))
        self.assertEqual(replies[3], "ERROR|ALREADY_VOTED")
        self.assertEqual(replies[4], "BYE")


class LiveServerTests(NetVoteTestCase):
    """Real sockets: werkzeug server on a free port, real HTTP client, real timeout."""

    def setUp(self):
        super().setUp()
        self.srv = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.port = self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def tearDown(self):
        self.srv.shutdown()
        super().tearDown()

    def call(self, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None, headers=H)
        return json.load(self.opener.open(req, timeout=20))

    def test_network_timeout_simulation_is_real(self):
        self.call("/api/auth/admin-login", {"username": "admin", "password": "Admin@123"})
        r = self.call("/api/admin/network-test", {"delay_ms": 800, "timeout_ms": 300, "burst": 0})["result"]
        self.assertEqual(r["normal"]["status"], "OK")
        self.assertEqual(r["simulated"]["status"], "TIMEOUT")
        self.assertGreaterEqual(r["simulated"]["ms"], 280)
        r2 = self.call("/api/admin/network-test", {"delay_ms": 600, "timeout_ms": 5000, "burst": 0})["result"]
        self.assertEqual(r2["simulated"]["status"], "DELAYED")
        self.assertEqual(MONITOR.snapshot()["timeouts"], 1)

    def test_burst_shows_up_in_monitor(self):
        self.call("/api/auth/admin-login", {"username": "admin", "password": "Admin@123"})
        MONITOR.reset()
        out = self.call("/api/admin/network-test", {"delay_ms": 0, "timeout_ms": 2000, "burst": 40})["result"]
        self.assertEqual(out["burst"]["ok"], 40)
        self.assertGreaterEqual(MONITOR.snapshot()["total_requests"], 40)

    def test_concurrency_endpoint_over_http(self):
        self.call("/api/auth/admin-login", {"username": "admin", "password": "Admin@123"})
        r = self.call("/api/admin/concurrency-test", {"mode": "same_voter", "requests": 100, "synchronization": True})["result"]
        self.assertEqual((r["successful_votes"], r["rejected_requests"], r["duplicate_votes"]), (1, 99, 0))
        # the REAL election must be untouched by the lab
        stats = self.call("/api/election")["election"]
        self.assertEqual(stats["total_votes"], 5)
