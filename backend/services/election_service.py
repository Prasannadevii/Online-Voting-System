"""Election lifecycle: NOT_STARTED -> ACTIVE <-> PAUSED -> ENDED."""
from backend.database.database import db
from backend.services import audit_service
from backend.utils.helpers import ApiError, now_iso
from backend.utils.transaction import transaction

TRANSITIONS = {
    "start":  ({"NOT_STARTED"}, "ACTIVE", "ELECTION_STARTED"),
    "pause":  ({"ACTIVE"}, "PAUSED", "ELECTION_PAUSED"),
    "resume": ({"PAUSED"}, "ACTIVE", "ELECTION_RESUMED"),
    "end":    ({"ACTIVE", "PAUSED"}, "ENDED", "ELECTION_ENDED"),
}


def get_election(conn):
    row = conn.execute("SELECT * FROM election_config ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    e = dict(row)
    e["total_registered"] = conn.execute("SELECT COUNT(*) FROM voters").fetchone()[0]
    e["total_votes"] = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    e["turnout_pct"] = round(100 * e["total_votes"] / e["total_registered"], 1) if e["total_registered"] else 0.0
    return e


def current(db_path):
    with db(db_path) as conn:
        return get_election(conn)


def transition(db_path, action, admin, request_id, ip, ua):
    if action not in TRANSITIONS:
        raise ApiError("INVALID_ACTION", "Unknown election action.", 400)
    allowed, new_status, audit_action = TRANSITIONS[action]
    with db(db_path) as conn:
        with transaction(conn):
            el = get_election(conn)
            if not el:
                raise ApiError("NO_ELECTION", "Create an election first.", 404)
            if el["status"] not in allowed:
                raise ApiError("INVALID_STATE", f"Cannot {action} an election that is {el['status']}.", 409)
            if action == "start" and conn.execute(
                    "SELECT COUNT(*) FROM candidates WHERE status='active'").fetchone()[0] < 2:
                raise ApiError("NOT_ENOUGH_CANDIDATES", "At least two active candidates are required.", 409)
            sets, args = "status=?", [new_status]
            if action == "start":
                sets += ", start_time=?"; args.append(now_iso())
            if action == "end":
                sets += ", end_time=?"; args.append(now_iso())
            conn.execute(f"UPDATE election_config SET {sets} WHERE id=?", args + [el["id"]])
            audit_service.log_event(conn, audit_action, user=admin, request_id=request_id, ip=ip, ua=ua,
                                    details=f"{el['status']} -> {new_status}",
                                    severity="WARNING" if action == "end" else "INFO")
        return get_election(conn)


def create(db_path, name, admin, request_id, ip, ua):
    """Create a fresh election. Resets ballots (single-election-at-a-time design)."""
    with db(db_path) as conn:
        with transaction(conn):
            el = get_election(conn)
            if el and el["status"] in ("ACTIVE", "PAUSED"):
                raise ApiError("ELECTION_RUNNING", "End the current election before creating a new one.", 409)
            conn.execute("DELETE FROM votes")
            conn.execute("UPDATE voters SET has_voted=0")
            conn.execute("UPDATE candidates SET vote_count=0")
            conn.execute("INSERT INTO election_config(election_name,status,total_registered,total_votes) "
                         "VALUES (?,?,?,0)", (name, "NOT_STARTED",
                                              conn.execute("SELECT COUNT(*) FROM voters").fetchone()[0]))
            audit_service.log_event(conn, "ELECTION_CREATED", user=admin, request_id=request_id, ip=ip,
                                    ua=ua, details=name, severity="WARNING")
        return get_election(conn)
