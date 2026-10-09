"""Orchestrates the educational demonstrations (all use isolated demo databases)."""
import http.client
import socket
import threading
import time

from backend.concurrency import os_demos, race_demo
from backend.concurrency.thread_manager import WorkerPool
from backend.concurrency.vote_lock import InstrumentedLock
from backend.database.database import db
from backend.networking import tcp_demo_client
from backend.networking.network_monitor import MONITOR
from backend.networking.rate_limiter import SlidingWindowLimiter
from backend.security.hashing import hash_password
from backend.services import audit_service, voting_service
from backend.utils.helpers import ApiError, new_request_id

DEMO_GUARD = threading.Lock()      # one demo at a time (also an OS mutex example)
LABEL = "EDUCATIONAL SIMULATION - isolated demo database; the real election is untouched"


class demo_slot:
    def __enter__(self):
        if not DEMO_GUARD.acquire(blocking=False):
            raise ApiError("DEMO_BUSY", "Another demonstration is running. Try again in a moment.", 409)

    def __exit__(self, *a):
        DEMO_GUARD.release()


def concurrency_test(real_db, mode, n, sync, executor):
    with demo_slot():
        return race_demo.run_concurrency_test(real_db, mode, n, sync, executor)


def rollback_demo():
    with demo_slot():
        folder, path = race_demo.make_demo_db(True, 1)
        lock = InstrumentedLock("rollback_demo", 10)
        try:
            def snap():
                with db(path) as c:
                    return {"votes_in_ledger": c.execute("SELECT COUNT(*) FROM votes").fetchone()[0],
                            "voter_has_voted": c.execute("SELECT has_voted FROM voters").fetchone()[0],
                            "candidate_1_count": c.execute("SELECT vote_count FROM candidates WHERE id=1").fetchone()[0]}
            before = snap()
            steps = [{"step": "BEGIN IMMEDIATE", "detail": "transaction opened, write lock taken"}]
            try:
                voting_service.cast_vote(path, "D0001", 1, "REQ-2026-ROLLBK01", "127.0.0.1", "demo", lock=lock,
                                         ref_secret=race_demo.DEMO_SECRET, fail_at="after_vote_insert", audit=False)
            except RuntimeError as exc:
                steps += [{"step": "INSERT INTO votes", "detail": "row written inside the open transaction"},
                          {"step": "FAILURE", "detail": str(exc)},
                          {"step": "ROLLBACK", "detail": "all changes since BEGIN are undone"}]
            after_fail = snap()
            r = voting_service.cast_vote(path, "D0001", 1, "REQ-2026-ROLLBK02", "127.0.0.1", "demo", lock=lock,
                                         ref_secret=race_demo.DEMO_SECRET, audit=False)
            after_ok = snap()
            return {"label": LABEL, "before": before, "after_failure": after_fail, "after_retry": after_ok,
                    "steps": steps, "retry_transaction": r["transaction_id"],
                    "atomic": after_fail == before,
                    "result": "ROLLBACK SUCCESSFUL - no partial vote remained" if after_fail == before else "INCONSISTENT"}
        finally:
            race_demo.cleanup(folder)


def retry_demo():
    with demo_slot():
        folder, path = race_demo.make_demo_db(True, 1)
        lock = InstrumentedLock("retry_demo", 10)
        rid, kw = "REQ-2026-RETRY001", dict(lock=lock, ref_secret=race_demo.DEMO_SECRET, audit=False)
        try:
            log = []
            first = voting_service.cast_vote(path, "D0001", 1, rid, "127.0.0.1", "demo", **kw)
            log.append({"who": "client", "msg": f"POST /api/vote  Request-ID {rid}"})
            log.append({"who": "server", "msg": f"vote committed -> {first['transaction_id']}"})
            log.append({"who": "network", "msg": "RESPONSE LOST (simulated) - client sees a timeout"})
            second = voting_service.cast_vote(path, "D0001", 1, rid, "127.0.0.1", "demo", **kw)
            log.append({"who": "client", "msg": f"RETRY same Request-ID {rid}"})
            log.append({"who": "server", "msg": f"replayed={second['replayed']} -> original {second['transaction_id']} returned, no new vote"})
            try:
                voting_service.cast_vote(path, "D0001", 1, "REQ-2026-RETRY002", "127.0.0.1", "demo", **kw)
                other = "accepted (BUG)"
            except voting_service.VoteError as exc:
                other = f"rejected: {exc.code}"
            log.append({"who": "server", "msg": f"a NEW request id for the same voter is {other}"})
            with db(path) as c:
                n = c.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
            return {"label": LABEL, "log": log, "votes_in_ledger": n, "first": first, "retry": second,
                    "idempotent": second["replayed"] and second["transaction_id"] == first["transaction_id"] and n == 1,
                    "result": "DUPLICATE OPERATION PREVENTED" if n == 1 else "FAILED"}
        finally:
            race_demo.cleanup(folder)


def ratelimit_demo(limit=20, attempts=30):
    lim = SlidingWindowLimiter(limit, 60, "demo")
    seq = []
    for i in range(1, attempts + 1):
        allowed, retry, remaining = lim.check("demo-client")
        seq.append({"n": i, "status": 200 if allowed else 429, "remaining": remaining, "retry_after": retry})
    blocked = sum(1 for s in seq if s["status"] == 429)
    return {"label": "EDUCATIONAL SIMULATION - separate limiter instance (the real limiter is not affected)",
            "limit": limit, "window_s": 60, "attempts": attempts, "allowed": attempts - blocked,
            "blocked": blocked, "sequence": seq,
            "result": f"First {limit} requests allowed, next {blocked} got HTTP 429 Too Many Requests"}


def tamper_demo():
    with demo_slot():
        folder, path = race_demo.make_demo_db(True, 6)
        lock = InstrumentedLock("tamper_demo", 10)
        try:
            for i in range(1, 6):
                voting_service.cast_vote(path, f"D{i:04d}", (i % 3) + 1, f"REQ-2026-TAMP{i:04d}", "127.0.0.1",
                                         "demo", lock=lock, ref_secret=race_demo.DEMO_SECRET, audit=False)
            clean = voting_service.verify_ledger(path)
            with db(path) as c:                      # an attacker edits history directly in SQL
                c.execute("UPDATE votes SET candidate_id=(candidate_id % 3)+1 WHERE transaction_id LIKE '%00002'")
            tampered = voting_service.verify_ledger(path)
            return {"label": LABEL, "before_tamper": clean, "after_tamper": tampered,
                    "result": "TAMPERING DETECTED" if not tampered["valid"] else "not detected",
                    "note": "The hash chain makes modification EVIDENT. It does not prevent it and is not a "
                            "substitute for access control or a real, audited election system."}
        finally:
            race_demo.cleanup(folder)


def tcp_demo():
    with demo_slot():
        folder, path = race_demo.make_demo_db(True, 1)
        try:
            out = tcp_demo_client.run_full_demo(path, InstrumentedLock("tcp_demo", 10), race_demo.DEMO_SECRET,
                                                hash_password("demo-pass", 1000))
            out["label"] = "EDUCATIONAL SIMULATION - real TCP sockets on 127.0.0.1, isolated demo database"
            return out
        finally:
            race_demo.cleanup(folder)


def deadlock_demo(strategy):
    if strategy not in ("deadlock", "lock_ordering", "timeout_backoff", "try_lock"):
        raise ApiError("INVALID_FIELD", "Unknown strategy.", 400)
    with demo_slot():
        out = os_demos.run_deadlock(strategy)
        out["label"] = "EDUCATIONAL SIMULATION - private locks, unrelated to the voting lock"
        return out


# ------------------------------------------------------------------ network simulation
def _timed_get(host, port, path, timeout_s, rid):
    t0 = time.perf_counter()
    status, outcome = None, "OK"
    conn = http.client.HTTPConnection(host, port, timeout=timeout_s)
    try:
        conn.request("GET", path, headers={"X-Request-ID": rid})
        resp = conn.getresponse()
        resp.read()
        status = resp.status
    except (socket.timeout, TimeoutError):
        outcome = "TIMEOUT"          # CN CONCEPT: the client gave up waiting for the server's reply
    except OSError:
        outcome = "ERROR"
    finally:
        conn.close()
    ms = (time.perf_counter() - t0) * 1000
    if outcome == "OK" and ms >= 500:
        outcome = "DELAYED"
    return {"ms": round(ms, 1), "status": outcome, "http_status": status, "request_id": rid}


def network_test(host, port, delay_ms, timeout_ms, burst, db_path, admin, ip):
    """REAL loopback HTTP requests to this server's /api/sim/ping endpoint."""
    with demo_slot():
        base = _timed_get(host, port, "/api/sim/ping?delay=0", timeout_ms / 1000, new_request_id())
        sim = _timed_get(host, port, f"/api/sim/ping?delay={delay_ms}", timeout_ms / 1000, new_request_id())
        if sim["status"] == "TIMEOUT":
            MONITOR.record_timeout()
            audit_service.log(db_path, "NETWORK_TIMEOUT", user=admin, request_id=sim["request_id"], ip=ip,
                              details=f"client timeout {timeout_ms} ms < server delay {delay_ms} ms",
                              severity="WARNING", status="TIMEOUT")
        out = {"label": "Real loopback HTTP requests; delay applies only to /api/sim/ping, never to voting",
               "delay_ms": delay_ms, "timeout_ms": timeout_ms, "normal": base, "simulated": sim,
               "verdict": {"TIMEOUT": "TIMEOUT - client gave up before the server answered",
                           "DELAYED": "DELAYED - answered, but slowly",
                           "OK": "OK - answered quickly", "ERROR": "ERROR"}[sim["status"]]}
        if burst:
            pool = WorkerPool(min(burst, 32), "burst")
            futs = [pool.submit(_timed_get, host, port, "/api/sim/ping?delay=0", 5, new_request_id())
                    for _ in range(burst)]
            res = [f.result() for f in futs]
            pool.shutdown()
            ms = [r["ms"] for r in res]
            out["burst"] = {"requests": burst, "ok": sum(r["status"] == "OK" for r in res),
                            "avg_ms": round(sum(ms) / len(ms), 1), "max_ms": max(ms),
                            "workers": pool.max_workers}
        return out
