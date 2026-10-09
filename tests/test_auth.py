from tests.base import H, NetVoteTestCase


class AuthTests(NetVoteTestCase):
    def reg(self, **over):
        d = {"voter_id": "NEW001", "name": "New Voter", "email": "new@example.test",
             "password": "Passw0rd1", "confirm_password": "Passw0rd1"}
        d.update(over)
        return self.post("/api/auth/register", d)

    def test_registration_success_and_password_is_hashed(self):
        r = self.reg()
        self.assertEqual(r.status_code, 201)
        from backend.database.database import db
        with db(self.db_path) as c:
            h = c.execute("SELECT password_hash FROM voters WHERE voter_id='NEW001'").fetchone()[0]
        self.assertNotIn("Passw0rd1", h)
        self.assertTrue(h.startswith("pbkdf2:sha256"))

    def test_registration_validation(self):
        self.assertEqual(self.reg(email="not-an-email").status_code, 400)
        self.assertEqual(self.reg(password="short1", confirm_password="short1").status_code, 400)
        self.assertEqual(self.reg(password="allletters", confirm_password="allletters").status_code, 400)
        self.assertEqual(self.reg(confirm_password="Different1").status_code, 400)
        self.assertEqual(self.reg(voter_id="a b").status_code, 400)
        r = self.post("/api/auth/register", {"voter_id": "X1"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"]["code"], "MISSING_FIELDS")

    def test_registration_uniqueness(self):
        self.assertEqual(self.reg().status_code, 201)
        self.assertEqual(self.reg(email="other@example.test").status_code, 409)       # same voter id
        self.assertEqual(self.reg(voter_id="NEW002").status_code, 409)                  # same email

    def test_login_success_and_me(self):
        self.assertEqual(self.login_voter().status_code, 200)
        me = self.c.get("/api/auth/me").get_json()
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["user"]["role"], "voter")

    def test_invalid_login_is_generic(self):
        wrong = self.login_voter(pw="nope")
        unknown = self.login_voter(vid="99999")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.get_json()["error"]["message"], unknown.get_json()["error"]["message"])

    def test_malformed_json_is_400(self):
        r = self.c.post("/api/auth/login", data="{not json", headers={"X-Requested-With": "NetVote", "Content-Type": "application/json"})
        self.assertEqual(r.status_code, 400)

    def test_logout_clears_session(self):
        self.login_voter()
        self.post("/api/auth/logout")
        self.assertFalse(self.c.get("/api/auth/me").get_json()["authenticated"])

    def test_authentication_required(self):
        self.assertEqual(self.c.get("/api/voter/profile").status_code, 401)
        self.assertEqual(self.post("/api/vote", {"candidate_id": 1}).status_code, 401)
        self.assertEqual(self.c.get("/api/admin/voters").status_code, 401)

    def test_authorization_roles(self):
        self.login_voter()
        self.assertEqual(self.c.get("/api/admin/voters").status_code, 403)       # voter -> admin API
        self.assertEqual(self.post("/api/admin/election/pause").status_code, 403)
        a = self.admin_client()
        self.assertEqual(a.get("/api/admin/voters").status_code, 200)
        self.assertEqual(self.post("/api/vote", {"candidate_id": 1}, client=a).status_code, 403)  # admin cannot vote

    def test_admin_login_failure_and_hash(self):
        r = self.post("/api/auth/admin-login", {"username": "admin", "password": "bad"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.login_admin().status_code, 200)

    def test_suspended_voter_cannot_login(self):
        a = self.admin_client()
        a.put("/api/admin/voters/10012/status", json={"status": "suspended"}, headers=H)
        self.assertEqual(self.login_voter().status_code, 403)

    def test_cookie_flags(self):
        r = self.login_voter()
        cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
