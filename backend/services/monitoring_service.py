"""System health, dashboard aggregation and concurrency status (all computed from live data)."""
import os
import threading
import time

from backend.concurrency.thread_manager import APP_POOL
from backend.concurrency.vote_lock import VOTE_LOCK
from backend.database.database import db, rows
from backend.networking import request_manager
from backend.networking.network_monitor import MONITOR
from backend.services import election_service, voting_service

try:
    import psutil
    _PROC = psutil.Process(os.getpid())
except Exception:                                    # psutil optional
    psutil, _PROC = None, None

_START = time.time()


def concurrency_status():
    q = request_manager.LOG_WRITER
    lock = VOTE_LOCK.stats()
    pool = APP_POOL.stats()
    return {"active_threads": threading.active_count(),
            "thread_names": sorted({t.name.split("-")[0] for t in threading.enumerate()})[:12],
            "worker_pool": pool, "log_queue_depth": q.q.unfinished_tasks, "log_rows_written": q.written,
            "log_rows_dropped": q.dropped, "lock": lock,
            "queued_requests": lock["waiting_now"] + pool["queued"] + q.q.unfinished_tasks,
            "inflight_requests": MONITOR.inflight}


def system_health(db_path):
    comps, last_error, last_vote = [], None, None
    t0 = time.perf_counter()
    try:
        with db(db_path) as c:
            c.execute("SELECT 1").fetchone()
            check = c.execute("PRAGMA quick_check").fetchone()[0]
            db_ms = (time.perf_counter() - t0) * 1000
            last_error = c.execute("SELECT event_type,message,timestamp FROM system_events "
                                   "WHERE severity IN ('ERROR','CRITICAL') ORDER BY id DESC LIMIT 1").fetchone()
            last_vote = c.execute("SELECT timestamp,transaction_id FROM votes ORDER BY id DESC LIMIT 1").fetchone()
            admins = c.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
            el = election_service.get_election(c)
        db_state = "healthy" if check == "ok" and db_ms < 100 else ("warning" if check == "ok" else "critical")
        db_note = f"quick_check={check}, query {db_ms:.1f} ms"
    except Exception as exc:
        db_state, db_note, db_ms, admins, el = "critical", f"unreachable: {type(exc).__name__}", 0, 0, None
    snap, lock, writer = MONITOR.snapshot(), VOTE_LOCK.stats(), request_manager.LOG_WRITER
    srv_err = (100 * snap["server_errors"] / snap["total_requests"]) if snap["total_requests"] else 0
    comps.append({"name": "Server", "state": "healthy", "note": f"up {int(time.time() - _START)} s, "
                                                                 f"{threading.active_count()} threads"})
    comps.append({"name": "Database", "state": db_state, "note": db_note})
    comps.append({"name": "Authentication", "state": "healthy" if admins else "critical",
                  "note": f"{admins} admin account(s); sessions signed + HttpOnly"})
    comps.append({"name": "Voting Service",
                  "state": "critical" if lock["timeouts"] else ("healthy" if el and el["status"] == "ACTIVE" else "warning"),
                  "note": f"election {el['status'] if el else 'none'}; lock timeouts {lock['timeouts']}"})
    comps.append({"name": "Network Monitor", "state": "healthy" if srv_err < 5 else ("warning" if srv_err < 20 else "critical"),
                  "note": f"5xx rate {srv_err:.1f}% over {snap['total_requests']} requests"})
    comps.append({"name": "Audit Logger", "state": "healthy" if writer.thread and writer.thread.is_alive() and not writer.dropped else "warning",
                  "note": f"writer thread alive, queue {writer.q.unfinished_tasks}, dropped {writer.dropped}"})
    sysinfo = {"uptime_s": int(time.time() - _START), "active_threads": threading.active_count(),
               "request_queue": writer.q.unfinished_tasks,
               "db_size_kb": round(os.path.getsize(db_path) / 1024, 1) if os.path.exists(db_path) else 0,
               "cpu_pct": None, "memory_mb": None, "system_cpu_pct": None}
    if psutil:
        try:
            sysinfo["cpu_pct"] = _PROC.cpu_percent(interval=None)
            sysinfo["memory_mb"] = round(_PROC.memory_info().rss / 1048576, 1)
            sysinfo["system_cpu_pct"] = psutil.cpu_percent(interval=None)
        except Exception:
            pass
    worst = "critical" if any(c["state"] == "critical" for c in comps) else (
        "warning" if any(c["state"] == "warning" for c in comps) else "healthy")
    return {"overall": worst, "components": comps, "system": sysinfo,
            "last_error": dict(last_error) if last_error else None,
            "last_successful_vote": dict(last_vote) if last_vote else None,
            "psutil_available": psutil is not None}


def dashboard(db_path):
    with db(db_path) as c:
        el = election_service.get_election(c)
        cands = rows(c.execute("SELECT id,name,party,symbol,color,vote_count FROM candidates "
                               "WHERE status='active' ORDER BY id"))
        events = rows(c.execute("SELECT timestamp,event_type,severity,message FROM system_events "
                                "ORDER BY id DESC LIMIT 8"))
        audit = rows(c.execute("SELECT timestamp,user_id,action,status FROM audit_logs ORDER BY id DESC LIMIT 8"))
    snap = MONITOR.snapshot()
    health = system_health(db_path)
    return {"election": el, "candidates": cands, "network": snap, "events": events, "recent_audit": audit,
            "concurrency": concurrency_status(), "health": health["overall"],
            "rate_limit": {"sensitive": request_manager.sensitive_limiter.stats(),
                           "general": request_manager.general_limiter.stats()},
            "ledger": voting_service.verify_ledger(db_path)}
