import threading
import unittest

from backend.concurrency import os_demos, race_demo
from backend.concurrency.thread_manager import WorkerPool
from backend.concurrency.vote_lock import InstrumentedLock
from backend.database.database import db
from tests.base import NetVoteTestCase


class HTTPConcurrencyTests(NetVoteTestCase):
    """100 simultaneous HTTP vote requests for the SAME voter against the real vote path."""

    def test_100_simultaneous_requests_same_voter(self):
        n = 100
        clients = [self.new_client("10015") for _ in range(n)]       # same voter, 100 sessions
        barrier = threading.Barrier(n)
        codes, lock = [], threading.Lock()

        def fire(i):
            barrier.wait()
            r = self.post("/api/vote", {"candidate_id": 2, "request_id": f"REQ-2026-CONC{i:04d}"}, client=clients[i])
            with lock:
                codes.append(r.status_code)

        ts = [threading.Thread(target=fire, args=(i,)) for i in range(n)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(codes.count(201), 1, codes)                  # exactly one success
        self.assertEqual(codes.count(409), n - 1, codes)              # all others rejected safely
        with db(self.db_path) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM votes").fetchone()[0], 6)        # 5 seeded + 1
            self.assertEqual(c.execute("SELECT COUNT(*) FROM votes v JOIN voters ON 1=1 "
                                       "WHERE voters.voter_id='10015' AND 0").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT vote_count FROM candidates WHERE id=2").fetchone()[0], 2)
        ledger = self.admin_client().get("/api/admin/ledger-verify").get_json()["ledger"]
        self.assertTrue(ledger["valid"], ledger["problems"])           # no database corruption

    def test_many_different_voters_all_succeed_consistently(self):
        voters = [str(10006 + i) for i in range(10)]                    # 10006..10015 unvoted
        clients = [self.new_client(v) for v in voters]
        barrier = threading.Barrier(len(voters))
        codes = []

        def fire(i):
            barrier.wait()
            codes.append(self.post("/api/vote", {"candidate_id": (i % 5) + 1}, client=clients[i]).status_code)

        ts = [threading.Thread(target=fire, args=(i,)) for i in range(len(voters))]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(codes.count(201), 10)
        ledger = self.admin_client().get("/api/admin/ledger-verify").get_json()["ledger"]
        self.assertTrue(ledger["valid"], ledger["problems"])
        self.assertEqual(ledger["votes_checked"], 15)


class LabTests(unittest.TestCase):
    REAL = "/nonexistent/real.db"

    def test_sync_enabled_prevents_race(self):
        r = race_demo.run_concurrency_test(self.REAL, "same_voter", 100, True)
        self.assertEqual(r["successful_votes"], 1)
        self.assertEqual(r["rejected_requests"], 99)
        self.assertEqual(r["duplicate_votes"], 0)
        self.assertEqual(r["lost_updates"], 0)
        self.assertEqual(r["race_condition"], "PREVENTED")
        self.assertGreater(r["lock"]["contended"], 0)

    def test_sync_disabled_demonstrates_race(self):
        r = race_demo.run_concurrency_test(self.REAL, "same_voter", 50, False)
        self.assertTrue(r["race_detected"], r)                          # duplicates and/or lost updates
        self.assertGreater(r["duplicate_votes"], 0)

    def test_multiple_voters_sync_consistent(self):
        r = race_demo.run_concurrency_test(self.REAL, "multiple_voters", 60, True)
        self.assertEqual(r["successful_votes"], 60)
        self.assertEqual(r["counter_sum"], 60)

    def test_thread_pool_executor_mode(self):
        r = race_demo.run_concurrency_test(self.REAL, "same_voter", 40, True, "pool")
        self.assertEqual(r["successful_votes"], 1)
        self.assertEqual(r["pool"]["completed"], 40)

    def test_unsafe_mode_refuses_real_database(self):
        with self.assertRaises(PermissionError):
            race_demo.cast_vote_unsafe("/tmp/x.db", "/tmp/x.db", "D0001", 1, "REQ-2026-AAAAAA")

    def test_race_trace_safe_vs_unsafe(self):
        self.assertEqual(race_demo.race_trace(True)["votes_recorded"], 1)
        self.assertEqual(race_demo.race_trace(False)["votes_recorded"], 2)

    def test_lock_statistics_and_timeout(self):
        lock = InstrumentedLock("t", timeout=0.2)
        with lock:
            self.assertTrue(lock.stats()["locked_now"])
            from backend.concurrency.vote_lock import LockTimeout
            with self.assertRaises(LockTimeout):
                with lock:
                    pass
        self.assertEqual(lock.stats()["timeouts"], 1)

    def test_deadlock_detected_and_prevented(self):
        self.assertTrue(os_demos.run_deadlock("deadlock")["deadlock_detected"])
        self.assertFalse(os_demos.run_deadlock("lock_ordering")["deadlock_detected"])
        self.assertFalse(os_demos.run_deadlock("try_lock")["deadlock_detected"])

    def test_starvation_policies(self):
        p = {x["policy"]: x for x in os_demos.run_starvation()["policies"]}
        self.assertGreater(p["priority"]["low_priority_wait"], p["aging"]["low_priority_wait"])
        self.assertGreater(p["aging"]["low_priority_wait"], p["fifo"]["low_priority_wait"])

    def test_worker_pool_counters(self):
        pool = WorkerPool(4)
        [f.result() for f in [pool.submit(lambda: 1) for _ in range(10)]]
        self.assertEqual(pool.stats()["completed"], 10)
        pool.shutdown()
