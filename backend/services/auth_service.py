"""Voter registration and voter/admin login."""
import sqlite3

from backend.database.database import db
from backend.security.hashing import burn_time, hash_password, verify_password
from backend.services import audit_service
from backend.utils.helpers import ApiError, now_iso


def register_voter(db_path, data, iterations, request_id, ip, ua):
    pw_hash = hash_password(data["password"], iterations)
    try:
        with db(db_path) as conn:
            conn.execute("INSERT INTO voters(voter_id,name,email,password_hash,created_at) VALUES (?,?,?,?,?)",
                         (data["voter_id"], data["name"], data["email"], pw_hash, now_iso()))
            audit_service.log_event(conn, "VOTER_REGISTERED", user=data["voter_id"], request_id=request_id,
                                    ip=ip, ua=ua)
    except sqlite3.IntegrityError as exc:
        # DATABASE CONCEPT: uniqueness is enforced by UNIQUE constraints, so two simultaneous
        # registrations cannot both succeed.
        field = "email" if "email" in str(exc).lower() else "Voter ID"
        raise ApiError("DUPLICATE_" + field.upper().replace(" ", "_"),
                       f"That {field} is already registered.", 409)


def login_voter(db_path, voter_id, password, iterations, request_id, ip, ua):
    with db(db_path) as conn:
        row = conn.execute("SELECT * FROM voters WHERE voter_id=?", (voter_id,)).fetchone()
        if not row:
            burn_time(password, iterations)
        if not row or not verify_password(row["password_hash"], password):
            audit_service.log_event(conn, "LOGIN_FAILED", user=voter_id, request_id=request_id, ip=ip, ua=ua,
                                    severity="WARNING", status="DENIED")
            raise ApiError("INVALID_CREDENTIALS", "Invalid voter ID or password.", 401)
        if row["status"] != "active":
            audit_service.log_event(conn, "LOGIN_FAILED", user=voter_id, request_id=request_id, ip=ip, ua=ua,
                                    details="suspended", severity="WARNING", status="DENIED")
            raise ApiError("ACCOUNT_SUSPENDED", "This account is suspended. Contact the administrator.", 403)
        conn.execute("UPDATE voters SET last_login=? WHERE id=?", (now_iso(), row["id"]))
        audit_service.log_event(conn, "LOGIN_SUCCESS", user=voter_id, request_id=request_id, ip=ip, ua=ua)
        return dict(row)


def login_admin(db_path, username, password, iterations, request_id, ip, ua):
    with db(db_path) as conn:
        row = conn.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        if not row:
            burn_time(password, iterations)
        if not row or not verify_password(row["password_hash"], password):
            audit_service.log_event(conn, "ADMIN_LOGIN_FAILED", user=username, request_id=request_id, ip=ip,
                                    ua=ua, severity="WARNING", status="DENIED")
            raise ApiError("INVALID_CREDENTIALS", "Invalid username or password.", 401)
        conn.execute("UPDATE admins SET last_login=? WHERE id=?", (now_iso(), row["id"]))
        audit_service.log_event(conn, "ADMIN_LOGIN", user=username, request_id=request_id, ip=ip, ua=ua)
        return dict(row)
