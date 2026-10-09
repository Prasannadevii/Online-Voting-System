"""EDUCATIONAL SIMULATION - race condition laboratory.

SAFETY: everything here runs against a throw-away database in a temp folder. The unsafe
function refuses to touch the real election database, and the production vote path
(voting_service.cast_vote) has no 'unsafe' switch at all.

OS CONCEPT: RACE CONDITION / LOST UPDATE
  unsafe: READ has_voted -> (another thread runs here) -> WRITE vote   (check-then-act)
  unsafe: READ vote_count -> +1 -> WRITE vote_count                    (read-modify-write)
"""
import os
import shutil
import statistics
import tempfile
import threading
import time
import uuid

from backend.concurrency.thread_manager import WorkerPool
from backend.concurrency.vote_lock import InstrumentedLock
from backend.database.database import db, init_db
from backend.security.hashing import voter_ref
from backend.services import voting_service
from backend.utils.helpers import now_iso

DEMO_SECRET = "demo-secret-not-for-production"


def make_demo_db(sync: bool, voters: int = 1, candidates: int = 3):
    """Create an isolated demo DB. With sync disabled the UNIQUE index is dropped too, so the
    race is visible (with it, SQLite itself would catch the duplicate)."""
    folder = tempfile.mkdtemp(prefix="netvote_demo_")
    path = os.path.join(folder, "demo.db")
    init_db(path)
    with db(path) as c:
        if not sync:
            c.execute("DROP INDEX IF EXISTS ux_votes_voter")
        c.executemany("INSERT INTO voters(voter_id,name,email,password_hash,created_at) VALUES (?,?,?,?,?)",
                      [(f"D{i:04d}", f"Demo {i}", f"d{i}@demo.test", "x", now_iso()) for i in range(1, voters + 1)])
        c.executemany("INSERT INTO candidates(name,party) VALUES (?,?)",
                      [(f"Demo Candidate {i}", f"Party {i}") for i in range(1, candidates + 1)])
        c.execute("INSERT INTO election_config(election_name,status,total_registered) VALUES ('DEMO','ACTIVE',?)",
                  (voters,))
    return folder, path


def cleanup(folder):
    shutil.rmtree(folder, ignore_errors=True)


def cast_vote_unsafe(db_path, real_db_path, voter_id, candidate_id, request_id, trace=None, delay=0.002):
    """Deliberately WITHOUT lock or transaction. Demo database only."""
    if os.path.abspath(db_path) == os.path.abspath(real_db_path):
        raise PermissionError("Unsafe mode may never run against the real election database.")
    t = trace or (lambda *_a, **_k: None)
    with db(db_path, timeout=60) as c:
        t("READ has_voted")
        row = c.execute("SELECT has_voted FROM voters WHERE voter_id=?", (voter_id,)).fetchone()
        t("READ has_voted=%s" % bool(row["has_voted"]))
        if row["has_voted"]:
            raise voting_service.VoteError("ALREADY_VOTED", "already voted", 409)
        time.sleep(delay)                          # <-- the window in which the race happens
        tx = f"VOTE-DEMO-{uuid.uuid4().hex[:8]}"
        c.execute("INSERT INTO votes(transaction_id,voter_ref,candidate_id,request_id,timestamp) VALUES (?,?,?,?,?)",
                  (tx, voter_ref(voter_id, DEMO_SECRET), candidate_id, request_id, now_iso()))
        t("INSERT vote")
        c.execute("UPDATE voters SET has_voted=1 WHERE voter_id=?", (voter_id,))
        cnt = c.execute("SELECT vote_count FROM candidates WHERE id=?", (candidate_id,)).fetchone()[0]
        time.sleep(delay / 2)
        c.execute("UPDATE candidates SET vote_count=? WHERE id=?", (cnt + 1, candidate_id))   # lost-update risk
        t("COMMIT (no real transaction)")
        return {"transaction_id": tx}


def _pct(vals, p):
    if not vals:
        return 0
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def run_concurrency_test(real_db_path, mode="same_voter", n=100, sync=True, executor="threads"):
    """Fire n genuinely concurrent vote attempts at an isolated demo database."""
    voters = 1 if mode == "same_voter" else n
    folder, path = make_demo_db(sync, voters)
    lock = InstrumentedLock("demo_lock", 60.0)
    results, lock_res = [], threading.Lock()
    barrier = threading.Barrier(n, timeout=30) if executor == "threads" else None
    peak_threads = [threading.active_count()]
    t_zero = [0.0]

    def attempt(i):
        voter = "D0001" if mode == "same_voter" else f"D{i + 1:04d}"
        cand = (i % 3) + 1
        rid = f"REQ-DEMO-{i:05d}"
        if barrier:
            try:
                barrier.wait()                      # all threads released at the same instant
            except threading.BrokenBarrierError:
                pass
        t0 = time.perf_counter()
        start_ms = (t0 - t_zero[0]) * 1000
        peak_threads[0] = max(peak_threads[0], threading.active_count())
        outcome, lock_wait = "error", 0.0
        try:
            if sync:
                voting_service.cast_vote(path, voter, cand, rid, "127.0.0.1", "demo", lock=lock,
                                         ref_secret=DEMO_SECRET, audit=False)
                lock_wait = lock.last_wait * 1000
            else:
                cast_vote_unsafe(path, real_db_path, voter, cand, rid)
            outcome = "success"
        except voting_service.VoteError as exc:
            outcome = "rejected" if exc.code == "ALREADY_VOTED" else "error"
        except Exception:
            outcome = "error"
        t1 = time.perf_counter()
        with lock_res:
            results.append({"i": i, "start_ms": round(start_ms, 2), "wait_ms": round(lock_wait, 2),
                            "end_ms": round((t1 - t_zero[0]) * 1000, 2), "ms": round((t1 - t0) * 1000, 2),
                            "outcome": outcome})

    pool_stats = None
    t_zero[0] = time.perf_counter()
    try:
        if executor == "threads":
            threads = [threading.Thread(target=attempt, args=(i,), name=f"voter-{i}") for i in range(n)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            created = n
        else:                                       # bounded thread pool: tasks queue up
            pool = WorkerPool(min(n, 16), "lab")
            futs = [pool.submit(attempt, i) for i in range(n)]
            for f in futs:
                f.result()
            pool_stats = pool.stats()
            pool.shutdown()
            created = pool.max_workers
        total_s = time.perf_counter() - t_zero[0]

        with db(path) as c:
            vote_rows = c.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
            dup = c.execute("SELECT COALESCE(SUM(n-1),0) FROM (SELECT COUNT(*) n FROM votes GROUP BY voter_ref "
                            "HAVING n>1)").fetchone()[0]
            counter_sum = c.execute("SELECT COALESCE(SUM(vote_count),0) FROM candidates").fetchone()[0]
            has_voted = c.execute("SELECT COUNT(*) FROM voters WHERE has_voted=1").fetchone()[0]
        lost_updates = max(0, vote_rows - counter_sum)
        ms = [r["ms"] for r in results]
        success = sum(r["outcome"] == "success" for r in results)
        rejected = sum(r["outcome"] == "rejected" for r in results)
        errors = sum(r["outcome"] == "error" for r in results)
        race = dup > 0 or lost_updates > 0
        if sync:
            verdict = "PREVENTED" if not race else "FAILED"
        else:
            verdict = "RACE CONDITION OCCURRED" if race else "NOT TRIGGERED THIS RUN (timing dependent) - run again"
        results.sort(key=lambda r: r["start_ms"])
        step = max(1, len(results) // 100)
        return {
            "mode": mode, "synchronization": sync, "executor": executor,
            "requests_sent": n, "requests_completed": len(results), "successful_votes": success,
            "rejected_requests": rejected, "errors": errors,
            "duplicate_votes": int(dup), "lost_updates": int(lost_updates),
            "ledger_rows": vote_rows, "voters_marked_voted": has_voted, "counter_sum": counter_sum,
            "race_condition": verdict, "race_detected": race,
            "threads_used": created, "peak_active_threads": peak_threads[0],
            "avg_ms": round(statistics.mean(ms), 2) if ms else 0, "max_ms": round(max(ms), 2) if ms else 0,
            "p95_ms": round(_pct(ms, 95), 2), "execution_ms": round(total_s * 1000, 1),
            "lock": lock.stats() if sync else None, "pool": pool_stats,
            "timeline": results[::step][:100],
            "label": "EDUCATIONAL SIMULATION - isolated demo database; the real election is untouched",
        }
    finally:
        cleanup(folder)


def race_trace(sync: bool):
    """Two voters-threads, same voter id. Returns the REAL ordered event trace for animation."""
    folder, path = make_demo_db(sync, 1)
    events, ev_lock = [], threading.Lock()
    t0 = time.perf_counter()
    lock = InstrumentedLock("trace_lock", 30.0)
    barrier = threading.Barrier(2, timeout=10)

    def worker(name):
        def trace(op, **_):
            with ev_lock:
                events.append({"t_ms": round((time.perf_counter() - t0) * 1000, 1), "thread": name, "op": op})
        try:
            barrier.wait()
            if sync:
                voting_service.cast_vote(path, "D0001", 1, f"REQ-DEMO-{name[-1]}", "127.0.0.1", "demo", lock=lock,
                                         ref_secret=DEMO_SECRET, trace=trace, work_delay=0.15, audit=False)
                trace("RESULT: vote accepted")
            else:
                cast_vote_unsafe(path, "", "D0001", 1, f"REQ-DEMO-{name[-1]}", trace=trace, delay=0.15)
                trace("RESULT: vote accepted")
        except voting_service.VoteError as exc:
            trace(f"RESULT: REJECTED ({exc.code})")
        except Exception as exc:
            trace(f"RESULT: error {type(exc).__name__}")

    try:
        ths = [threading.Thread(target=worker, args=(f"Thread {i}",)) for i in (1, 2)]
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        with db(path) as c:
            n = c.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
        events.sort(key=lambda e: e["t_ms"])
        return {"synchronization": sync, "events": events, "votes_recorded": n,
                "result": ("RACE CONDITION PREVENTED" if n == 1 else "DUPLICATE VOTE") if sync else
                          ("DUPLICATE VOTE (race condition)" if n > 1 else "not triggered this run")}
    finally:
        cleanup(folder)
