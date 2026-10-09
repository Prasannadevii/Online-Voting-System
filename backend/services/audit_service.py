"""Audit log + system events (DB rows and log files)."""
from backend.database.database import db, rows
from backend.utils import logger
from backend.utils.helpers import now_iso


def log_event(conn, action, *, user=None, request_id=None, ip=None, ua=None, details=None,
              severity="INFO", status="OK"):
    """Insert an audit row using an existing connection (so it can join a transaction)."""
    conn.execute(
        "INSERT INTO audit_logs(user_id,action,request_id,ip_address,user_agent,timestamp,"
        "details,severity,status) VALUES (?,?,?,?,?,?,?,?,?)",
        (user, action, request_id, ip, (ua or "")[:200], now_iso(), details, severity, status))
    logger.get("audit").info(f"{request_id} | {user} | {action} | {severity} | {status} | {details}")


def log(db_path, action, **kw):
    try:
        with db(db_path) as conn:
            log_event(conn, action, **kw)
    except Exception as exc:                       # logging must never break a request
        logger.get("error").error(f"audit write failed: {exc}")


def system_event(db_path, event_type, severity, message):
    try:
        with db(db_path) as conn:
            conn.execute("INSERT INTO system_events(event_type,severity,message,timestamp) VALUES (?,?,?,?)",
                         (event_type, severity, message, now_iso()))
    except Exception as exc:
        logger.get("error").error(f"system_event write failed: {exc}")


def query_logs(db_path, *, action=None, user=None, severity=None, date_from=None, date_to=None,
               limit=100, offset=0):
    where, args = [], []
    if action:
        where.append("action = ?"); args.append(action)
    if user:
        where.append("user_id LIKE ?"); args.append(f"%{user}%")
    if severity:
        where.append("severity = ?"); args.append(severity.upper())
    if date_from:
        where.append("timestamp >= ?"); args.append(date_from)
    if date_to:
        where.append("timestamp <= ?"); args.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    with db(db_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM audit_logs {clause}", args).fetchone()[0]
        data = rows(conn.execute(
            f"SELECT id,timestamp,user_id,action,request_id,ip_address,status,severity,details "
            f"FROM audit_logs {clause} ORDER BY id DESC LIMIT ? OFFSET ?", args + [limit, offset]))
        actions = [r[0] for r in conn.execute("SELECT DISTINCT action FROM audit_logs ORDER BY action")]
    return {"total": total, "logs": data, "actions": actions}
