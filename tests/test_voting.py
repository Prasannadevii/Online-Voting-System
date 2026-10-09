from backend.database.database import db
from tests.base import H, NetVoteTestCase


class VotingTests(NetVoteTestCase):
    def count(self, sql):
        with db(self.db_path) as c:
            return c.execute(sql).fetchone()[0]

    def test_candidate_retrieval(self):
        r = self.c.get("/api/candidates").get_json()
        self.assertEqual(len(r["candidates"]), 5)
        self.assertIn("party", r["candidates"][0])

    def test_vote_success_returns_receipt(self):
        self.login_voter()
        r = self.post("/api/vote", {"candidate_id": 2})
        self.assertEqual(r.status_code, 201)
        j = r.get_json()
        self.assertRegex(j["transaction_id"], r"^VOTE-\d{4}-\d{5}$")
        self.assertRegex(j["request_id"], r"^REQ-\d{4}-[A-Z0-9]+$")
        self.assertEqual(j["status"], "confirmed")
        self.assertEqual(self.count("SELECT COUNT(*) FROM votes"), 6)       # 5 seeded + 1
        self.assertEqual(self.count("SELECT vote_count FROM candidates WHERE id=2"), 2)

    def test_duplicate_vote_rejected(self):
        self.login_voter()
        first = self.post("/api/vote", {"candidate_id": 1}).get_json()
        r = self.post("/api/vote", {"candidate_id": 3})
        self.assertEqual(r.status_code, 409)
        e = r.get_json()["error"]
        self.assertEqual(e["code"], "ALREADY_VOTED")
        self.assertEqual(e["transaction_id"], first["transaction_id"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM votes"), 6)

    def test_invalid_candidate(self):
        self.login_voter()
        self.assertEqual(self.post("/api/vote", {"candidate_id": 999}).status_code, 404)
        self.assertEqual(self.post("/api/vote", {"candidate_id": "abc"}).status_code, 400)
        self.assertEqual(self.post("/api/vote", {}).status_code, 400)
        self.assertEqual(self.count("SELECT has_voted FROM voters WHERE voter_id='10012'"), 0)

    def test_election_closed_paused_and_ended(self):
        a = self.admin_client()
        self.post("/api/admin/election/pause", client=a)
        self.login_voter()
        r = self.post("/api/vote", {"candidate_id": 1})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"]["code"], "ELECTION_CLOSED")
        self.post("/api/admin/election/resume", client=a)
        self.assertEqual(self.post("/api/vote", {"candidate_id": 1}).status_code, 201)
        self.post("/api/admin/election/end", client=a)
        self.assertEqual(self.post("/api/vote", {"candidate_id": 1}, client=self.new_client("10013")).status_code, 403)

    def test_request_id_header_echo_and_format(self):
        r = self.c.get("/api/candidates")
        self.assertRegex(r.headers["X-Request-ID"], r"^REQ-\d{4}-[A-Z0-9]{6,16}$")
        r = self.c.get("/api/candidates", headers={"X-Request-ID": "REQ-2026-ABCDEF12"})
        self.assertEqual(r.headers["X-Request-ID"], "REQ-2026-ABCDEF12")
        r = self.c.get("/api/candidates", headers={"X-Request-ID": "evil header; <script>"})
        self.assertRegex(r.headers["X-Request-ID"], r"^REQ-")

    def test_idempotent_retry_returns_original(self):
        self.login_voter()
        rid = "REQ-2026-IDEMP001"
        a = self.post("/api/vote", {"candidate_id": 1, "request_id": rid})
        b = self.post("/api/vote", {"candidate_id": 1, "request_id": rid})
        self.assertEqual(a.status_code, 201)
        self.assertEqual(b.status_code, 200)
        self.assertTrue(b.get_json()["replayed"])
        self.assertEqual(a.get_json()["transaction_id"], b.get_json()["transaction_id"])
        self.assertEqual(self.count("SELECT COUNT(*) FROM votes"), 6)

    def test_request_id_cannot_be_hijacked_by_another_voter(self):
        self.login_voter()
        self.post("/api/vote", {"candidate_id": 1, "request_id": "REQ-2026-SHARED01"})
        other = self.new_client("10013")
        r = self.post("/api/vote", {"candidate_id": 1, "request_id": "REQ-2026-SHARED01"}, client=other)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["error"]["code"], "REQUEST_ID_CONFLICT")

    def test_bad_request_id_format(self):
        self.login_voter()
        self.assertEqual(self.post("/api/vote", {"candidate_id": 1, "request_id": "bogus"}).status_code, 400)

    def test_results_hidden_until_end_but_admin_sees_live(self):
        self.login_voter()
        r = self.c.get("/api/results")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["error"]["code"], "RESULTS_NOT_PUBLISHED")
        a = self.admin_client()
        live = a.get("/api/results").get_json()
        self.assertEqual(live["total_votes"], 5)
        self.post("/api/admin/election/end", client=a)
        final = self.app.test_client().get("/api/results").get_json()
        self.assertTrue(final["final"])
        self.assertAlmostEqual(sum(x["percent"] for x in final["results"]), 100, delta=0.6)

    def test_ballot_secrecy_in_admin_views(self):
        a = self.admin_client()
        body = a.get("/api/admin/voters").get_data(as_text=True)
        self.assertNotIn("candidate", body)
        with db(self.db_path) as c:                   # votes table holds a pseudonym, not the voter id
            refs = [r[0] for r in c.execute("SELECT voter_ref FROM votes")]
        self.assertTrue(all(r not in ("10001", "10002") for r in refs))
        self.assertTrue(all(len(r) == 24 for r in refs))

    def test_vote_status_and_receipt_verification(self):
        self.login_voter()
        self.assertFalse(self.c.get("/api/vote/status").get_json()["has_voted"])
        tx = self.post("/api/vote", {"candidate_id": 4}).get_json()["transaction_id"]
        st = self.c.get("/api/vote/status").get_json()
        self.assertTrue(st["has_voted"])
        self.assertEqual(st["transaction_id"], tx)
        v = self.c.get(f"/api/verify-receipt?transaction_id={tx}").get_json()
        self.assertTrue(v["found"])
        self.assertNotIn("candidate", str(v))
        self.assertFalse(self.c.get("/api/verify-receipt?transaction_id=NOPE").get_json()["found"])

    def test_audit_trail_records_vote_and_duplicate(self):
        self.login_voter()
        self.post("/api/vote", {"candidate_id": 1})
        self.post("/api/vote", {"candidate_id": 1})
        logs = self.admin_client().get("/api/admin/audit-logs?user=10012").get_json()
        actions = {x["action"] for x in logs["logs"]}
        self.assertTrue({"LOGIN_SUCCESS", "VOTE_REQUEST", "VOTE_SUCCESS", "DUPLICATE_VOTE"} <= actions)
        sev = self.admin_client().get("/api/admin/audit-logs?severity=WARNING").get_json()
        self.assertTrue(all(x["severity"] == "WARNING" for x in sev["logs"]))

    def test_election_state_machine(self):
        a = self.admin_client()
        self.assertEqual(self.post("/api/admin/election/start", client=a).status_code, 409)    # already ACTIVE
        self.assertEqual(self.post("/api/admin/election/resume", client=a).status_code, 409)
        self.assertEqual(self.post("/api/admin/election/pause", client=a).status_code, 200)
        self.assertEqual(self.post("/api/admin/election/end", client=a).status_code, 200)
        self.assertEqual(self.post("/api/admin/election/pause", client=a).status_code, 409)    # ENDED
        r = self.post("/api/admin/election/create", {"election_name": "Second Election"}, client=a)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.count("SELECT COUNT(*) FROM votes"), 0)                           # ballots reset

    def test_candidate_management_rules(self):
        a = self.admin_client()
        body = {"name": "Test Person", "party": "Test Party", "symbol": "T", "color": "#112233", "description": "x"}
        self.assertEqual(self.post("/api/admin/candidates", body, client=a).status_code, 409)  # election running
        self.post("/api/admin/election/end", client=a)
        r = self.post("/api/admin/candidates", body, client=a)
        self.assertEqual(r.status_code, 201)
        cid = r.get_json()["id"]
        self.assertEqual(a.delete(f"/api/admin/candidates/{cid}", headers=H).status_code, 200)
        self.assertEqual(a.delete("/api/admin/candidates/1", headers=H).status_code, 409)      # has votes
