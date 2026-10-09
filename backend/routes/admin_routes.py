"""Admin management: voters, candidates, election control, audit logs, settings."""
import sqlite3

from flask import Blueprint, current_app, g, request

from backend.database.database import db, rows
from backend.security import validation
from backend.security.auth import current_user, login_required
from backend.security.hashing import hash_password, verify_password
from backend.services import audit_service, election_service
from backend.utils.helpers import ApiError, client_ip, ok
from backend.utils.transaction import transaction

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _path():
    return current_app.config["DATABASE_PATH"]


def _who():
    return current_user()["name"]


def _ctx():
    return _who(), g.request_id, client_ip(), request.user_agent.string


# ------------------------------------------------------------------ election control
@bp.post("/election/<action>")
@login_required("admin")
def election_action(action):
    el = election_service.transition(_path(), action, *_ctx())
    return ok({"election": el, "message": f"Election {action} successful."})


@bp.post("/election/create")
@login_required("admin")
def election_create():
    data = validation.json_body(request)
    validation.require_fields(data, "election_name")
    name = validation.clean_str(data["election_name"], "Election name", 3, 100)
    return ok({"election": election_service.create(_path(), name, *_ctx())}, status=201)


# ------------------------------------------------------------------ voters
@bp.get("/voters")
@login_required("admin")
def voters():
    q = (request.args.get("q") or "").strip()[:40]
    limit = min(int(request.args.get("limit", 50) or 50), 200)
    offset = max(int(request.args.get("offset", 0) or 0), 0)
    where, args = "", []
    if q:
        where, args = "WHERE voter_id LIKE ? OR name LIKE ? OR email LIKE ?", [f"%{q}%"] * 3
    with db(_path()) as c:
        total = c.execute(f"SELECT COUNT(*) FROM voters {where}", args).fetchone()[0]
        data = rows(c.execute(f"SELECT voter_id,name,email,has_voted,status,created_at,last_login FROM voters "
                              f"{where} ORDER BY id LIMIT ? OFFSET ?", args + [limit, offset]))
    return ok({"voters": data, "total": total})        # note: never includes anybody's choice


@bp.put("/voters/<voter_id>/status")
@login_required("admin")
def voter_status(voter_id):
    status = validation.json_body(request).get("status")
    if status not in ("active", "suspended"):
        raise ApiError("INVALID_FIELD", "status must be 'active' or 'suspended'.", 400)
    with db(_path()) as c:
        cur = c.execute("UPDATE voters SET status=? WHERE voter_id=?", (status, voter_id))
        if cur.rowcount == 0:
            raise ApiError("NOT_FOUND", "Voter not found.", 404)
        audit_service.log_event(c, "VOTER_" + status.upper(), user=_who(), request_id=g.request_id,
                                ip=client_ip(), ua=request.user_agent.string, details=voter_id, severity="WARNING")
    return ok({"message": f"Voter {voter_id} is now {status}."})


# ------------------------------------------------------------------ candidates
def _structure_locked():
    el = election_service.current(_path())
    return bool(el and el["status"] in ("ACTIVE", "PAUSED"))


@bp.post("/candidates")
@login_required("admin")
def candidate_create():
    if _structure_locked():
        raise ApiError("CANDIDATES_LOCKED", "Candidates cannot be added while an election is running.", 409)
    d = validation.validate_candidate(validation.json_body(request))
    with db(_path()) as c:
        cur = c.execute("INSERT INTO candidates(name,party,symbol,color,description) VALUES (?,?,?,?,?)",
                        (d["name"], d["party"], d["symbol"], d["color"], d["description"]))
        audit_service.log_event(c, "CANDIDATE_CREATED", user=_who(), request_id=g.request_id, ip=client_ip(),
                                ua=request.user_agent.string, details=f"{d['name']} ({d['party']})")
    return ok({"id": cur.lastrowid}, status=201)


@bp.put("/candidates/<int:cid>")
@login_required("admin")
def candidate_update(cid):
    d = validation.validate_candidate(validation.json_body(request))
    with db(_path()) as c:
        old = c.execute("SELECT name,party FROM candidates WHERE id=?", (cid,)).fetchone()
        if not old:
            raise ApiError("NOT_FOUND", "Candidate not found.", 404)
        if _structure_locked() and (old["name"] != d["name"] or old["party"] != d["party"]):
            raise ApiError("CANDIDATES_LOCKED", "Name/party cannot change while an election is running "
                                                "(description, symbol and colour can).", 409)
        c.execute("UPDATE candidates SET name=?,party=?,symbol=?,color=?,description=? WHERE id=?",
                  (d["name"], d["party"], d["symbol"], d["color"], d["description"], cid))
        audit_service.log_event(c, "CANDIDATE_UPDATED", user=_who(), request_id=g.request_id, ip=client_ip(),
                                ua=request.user_agent.string, details=f"id={cid}")
    return ok({"message": "Candidate updated."})


@bp.delete("/candidates/<int:cid>")
@login_required("admin")
def candidate_delete(cid):
    if _structure_locked():
        raise ApiError("CANDIDATES_LOCKED", "Candidates cannot be removed while an election is running.", 409)
    with db(_path()) as c:
        try:
            with transaction(c):
                row = c.execute("SELECT name,vote_count FROM candidates WHERE id=?", (cid,)).fetchone()
                if not row:
                    raise ApiError("NOT_FOUND", "Candidate not found.", 404)
                if row["vote_count"]:
                    raise ApiError("HAS_VOTES", "A candidate with recorded votes cannot be deleted.", 409)
                c.execute("DELETE FROM candidates WHERE id=?", (cid,))
                audit_service.log_event(c, "CANDIDATE_DELETED", user=_who(), request_id=g.request_id,
                                        ip=client_ip(), ua=request.user_agent.string, details=row["name"],
                                        severity="WARNING")
        except sqlite3.IntegrityError:
            raise ApiError("HAS_VOTES", "Candidate is referenced by recorded votes.", 409)
    return ok({"message": "Candidate deleted."})


@bp.get("/candidates")
@login_required("admin")
def candidates_admin():
    with db(_path()) as c:
        data = rows(c.execute("SELECT id,name,party,symbol,color,description,vote_count,status FROM candidates ORDER BY id"))
    return ok({"candidates": data, "locked": _structure_locked()})


# ------------------------------------------------------------------ audit logs
@bp.get("/audit-logs")
@login_required("admin")
def audit_logs():
    a = request.args
    sev = (a.get("severity") or "").upper() or None
    result = audit_service.query_logs(_path(), action=a.get("action") or None, user=(a.get("user") or None),
                                      severity=sev, date_from=a.get("date_from") or None,
                                      date_to=a.get("date_to") or None,
                                      limit=min(int(a.get("limit", 100) or 100), 500),
                                      offset=max(int(a.get("offset", 0) or 0), 0))
    return ok(result)


# ------------------------------------------------------------------ settings
@bp.get("/settings")
@login_required("admin")
def settings():
    c = current_app.config
    return ok({"settings": {"host": c["HOST"], "port": c["PORT"], "debug": c["DEBUG"],
                            "rate_limit_sensitive": f"{c['RATE_LIMIT_SENSITIVE']} / {c['RATE_LIMIT_WINDOW']} s / IP",
                            "rate_limit_general": f"{c['RATE_LIMIT_GENERAL']} / {c['RATE_LIMIT_WINDOW']} s / IP",
                            "password_hashing": f"PBKDF2-SHA256, {c['HASH_ITERATIONS']} iterations",
                            "session_minutes": c["SESSION_MINUTES"], "lock_timeout_s": c["LOCK_TIMEOUT_S"],
                            "database": c["DATABASE_PATH"].replace("\\", "/").split("/")[-1]}})


@bp.post("/change-password")
@login_required("admin")
def change_password():
    d = validation.json_body(request)
    validation.require_fields(d, "current_password", "new_password")
    new = d["new_password"]
    if not isinstance(new, str) or len(new) < 8 or new.isalpha() or new.isdigit():
        raise ApiError("WEAK_PASSWORD", "New password needs 8+ characters with letters and digits.", 400)
    uid = current_user()["uid"]
    with db(_path()) as c:
        row = c.execute("SELECT password_hash FROM admins WHERE id=?", (uid,)).fetchone()
        if not row or not verify_password(row["password_hash"], str(d["current_password"])):
            raise ApiError("INVALID_CREDENTIALS", "Current password is incorrect.", 401)
        c.execute("UPDATE admins SET password_hash=? WHERE id=?",
                  (hash_password(new, current_app.config["HASH_ITERATIONS"]), uid))
        audit_service.log_event(c, "ADMIN_PASSWORD_CHANGED", user=_who(), request_id=g.request_id,
                                ip=client_ip(), ua=request.user_agent.string, severity="WARNING")
    return ok({"message": "Password changed."})
