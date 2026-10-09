import sqlite3
import tempfile
import os
import unittest

from backend.concurrency import race_demo
from backend.concurrency.vote_lock import InstrumentedLock
from backend.database.database import connect, db
from backend.services import concurrency_service, voting_service
from backend.utils.transaction import transaction
from backend.networking import request_manager
from tests.base import NetVoteTestCase


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.folder, self.path = race_demo.make_demo_db(True, 2)
        self.lock = InstrumentedLock("t", 5)
        self.kw = dict(lock=self.lock, ref_secret=race_demo.DEMO_SECRET, audit=False)

    def tearDown(self):
        race_demo.cleanup(self.folder)

    def snap(self):
        with db(self.path) as c:
            return (c.execute("SELECT COUNT(*) FROM votes").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM voters WHERE has_voted=1").fetchone()[0],
                    c.execute("SELECT COALESCE(SUM(vote_count),0) FROM candidates").fetchone()[0])

    def test_failure_mid_vote_rolls_everything_back(self):
        with self.assertRaises(RuntimeError):
            voting_service.cast_vote(self.path, "D0001", 1, "REQ-2026-ROLLB001", "x", "t",
                                     fail_at="after_vote_insert", **self.kw)
        self.assertEqual(self.snap(), (0, 0, 0))                      # insert was undone
        r = voting_service.cast_vote(self.path, "D0001", 1, "REQ-2026-ROLLB002", "x", "t", **self.kw)
        self.assertEqual(self.snap(), (1, 1, 1))
        self.assertEqual(r["status"], "confirmed")

    def test_lock_released_after_failure(self):
        with self.assertRaises(RuntimeError):
            voting_service.cast_vote(self.path, "D0001", 1, "REQ-2026-ROLLB003", "x", "t",
                                     fail_at="after_vote_insert", **self.kw)
        self.assertFalse(self.lock.stats()["locked_now"])             # "with" released it

    def test_transaction_manager_commit_and_rollback(self):
        conn = connect(self.path)
        conn.execute("CREATE TABLE t(x INTEGER)")
        with transaction(conn):
            conn.execute("INSERT INTO t VALUES (1)")
        with self.assertRaises(ValueError):
            with transaction(conn):
                conn.execute("INSERT INTO t VALUES (2)")
                raise ValueError("boom")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
        conn.close()

    def test_database_constraint_blocks_duplicate_even_without_app_checks(self):
        voting_service.cast_vote(self.path, "D0001", 1, "REQ-2026-CONSTR01", "x", "t", **self.kw)
        conn = connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):               # UNIQUE(voter_ref) is the last line of defence
            conn.execute("INSERT INTO votes(transaction_id,voter_ref,candidate_id,request_id,timestamp) "
                         "SELECT 'VOTE-X', voter_ref, 1, 'REQ-2026-OTHER001', 'now' FROM votes LIMIT 1")
        conn.close()

    def test_foreign_key_enforced(self):
        conn = connect(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO votes(transaction_id,voter_ref,candidate_id,request_id,timestamp) "
                         "VALUES ('V','r',999,'REQ-2026-FK000001','now')")
        conn.close()

    def test_ledger_detects_tampering(self):
        for i in (1, 2):
            voting_service.cast_vote(self.path, f"D000{i}", i, f"REQ-2026-LEDG000{i}", "x", "t", **self.kw)
        self.assertTrue(voting_service.verify_ledger(self.path)["valid"])
        with db(self.path) as c:
            c.execute("UPDATE votes SET candidate_id=3 WHERE id=1")
        self.assertFalse(voting_service.verify_ledger(self.path)["valid"])

    def test_demo_services(self):
        self.assertTrue(concurrency_service.rollback_demo()["atomic"])
        self.assertTrue(concurrency_service.retry_demo()["idempotent"])
        self.assertEqual(concurrency_service.tamper_demo()["result"], "TAMPERING DETECTED")


class DatabaseErrorTests(NetVoteTestCase):
    def test_database_error_returns_503_not_stack_trace(self):
        self.login_voter()
        request_manager.LOG_WRITER.flush()
        os.replace(self.db_path, self.db_path + ".bak")               # break the database
        with open(self.db_path, "w") as f:
            f.write("not a database")
        r = self.post("/api/vote", {"candidate_id": 1})
        self.assertIn(r.status_code, (500, 503))
        body = r.get_data(as_text=True)
        self.assertNotIn("Traceback", body)
        self.assertIn("request_id", body)
