"""Shared test fixtures: a fresh seeded temp database + Flask app per test class."""
import os
import tempfile
import unittest

from app import create_app
from backend.database.seed import seed_database
from backend.networking import request_manager
from backend.networking.network_monitor import MONITOR

_LOG_DIR = tempfile.mkdtemp(prefix="netvote_testlogs_")      # one log dir for the whole test run
H = {"X-Requested-With": "NetVote", "Content-Type": "application/json"}
SECRET = "test-secret-key"


class NetVoteTestCase(unittest.TestCase):
    rate_limit = False

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self._tmp.name, "test.db")
        seed_database(self.db_path, SECRET, iterations=1000)
        self.app = create_app({"DATABASE_PATH": self.db_path, "SECRET_KEY": SECRET, "TESTING": True,
                               "HASH_ITERATIONS": 1000, "RATE_LIMIT_ENABLED": self.rate_limit,
                               "LOG_DIR": _LOG_DIR})
        MONITOR.reset()
        self.c = self.app.test_client()

    def tearDown(self):
        request_manager.LOG_WRITER.flush()
        self._tmp.cleanup()

    # helpers
    def post(self, path, body=None, client=None, headers=None):
        return (client or self.c).post(path, json=body if body is not None else {}, headers={**H, **(headers or {})})

    def login_voter(self, vid="10012", pw="Voter@123", client=None):
        return self.post("/api/auth/login", {"voter_id": vid, "password": pw}, client)

    def login_admin(self, client=None):
        return self.post("/api/auth/admin-login", {"username": "admin", "password": "Admin@123"}, client)

    def new_client(self, vid="10012"):
        c = self.app.test_client()
        self.login_voter(vid, client=c)
        return c

    def admin_client(self):
        c = self.app.test_client()
        self.login_admin(c)
        return c
