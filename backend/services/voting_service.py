"""THE core of NetVote: the transactional, synchronised, idempotent vote operation."""
import sqlite3
import time
from datetime import datetime

from backend.concurrency.vote_lock import LockTimeout
from backend.database.database import db
from backend.security.hashing import GENESIS_HASH, chain_hash, voter_ref
from backend.services import audit_service, election_service
from backend.utils import logger
from backend.utils.helpers import now_iso
from backend.utils.transaction import transaction


class VoteError(Exception):
    def __init__(self, code, message, status, **extra):
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra


def cast_vote(db_path, voter_id, candidate_id, request_id, ip, user_agent, *, lock, ref_secret,
              trace=None, work_delay=0.0, fail_at=None, audit=True):
    """Record one vote. Returns a dict, or raises VoteError.

    work_delay / fail_at / trace exist ONLY for the educational demos (they run against an
    isolated demo database); production callers never set them.
    """
    t = trace or (lambda *_a, **_k: None)
    ref = voter_ref(voter_id, ref_secret)
    try:
        t("LOCK_WAIT")
        # ---- OS CONCEPT: CRITICAL SECTION ------------------------------------------
        # Many request threads may arrive here at the same moment. RACE CONDITION: two
        # threads could both read has_voted=0 and both insert a vote. The mutex makes the
        # check-then-act sequence below indivisible. `with` guarantees release even on errors.
        with lock:
            t("LOCK_ACQUIRED")
            with db(db_path) as conn:
                return _critical_section(conn, voter_id, ref, candidate_id, request_id, ip,
                                         user_agent, t, work_delay, fail_at)
    except VoteError as exc:
        if audit and exc.code in ("ALREADY_VOTED", "ELECTION_CLOSED", "INVALID_CANDIDATE", "REQUEST_ID_CONFLICT"):
            audit_service.log(db_path, "DUPLICATE_VOTE" if exc.code == "ALREADY_VOTED" else "VOTE_REJECTED",
                              user=voter_id, request_id=request_id, ip=ip, ua=user_agent,
                              details=exc.code, severity="WARNING", status="REJECTED")
        raise
    except LockTimeout:
        audit_service.system_event(db_path, "LOCK_TIMEOUT", "ERROR", "vote lock wait timed out")
        raise VoteError("SERVICE_BUSY", "Voting service is temporarily unavailable. "
                        "Your vote has NOT been recorded.", 503)
    except sqlite3.OperationalError as exc:        # e.g. database is locked
        logger.get("error").error(f"vote DB operational error {request_id}: {exc}")
        audit_service.system_event(db_path, "DATABASE_ERROR", "ERROR", str(exc)[:200])
        raise VoteError("SERVICE_UNAVAILABLE", "Voting service is temporarily unavailable. "
                        "Your vote has NOT been recorded.", 503)
    except sqlite3.Error as exc:
        logger.get("error").error(f"vote DB error {request_id}: {exc}")
        audit_service.system_event(db_path, "DATABASE_ERROR", "ERROR", str(exc)[:200])
        raise VoteError("DATABASE_ERROR", "A database error occurred. Your vote has NOT been recorded.", 500)
    finally:
        t("UNLOCK")


def _critical_section(conn, voter_id, ref, candidate_id, request_id, ip, ua, t, work_delay, fail_at):
    # OS/DB CONCEPT: ATOMICITY - BEGIN IMMEDIATE ... COMMIT, or ROLLBACK on any exception.
    with transaction(conn):
        # 0. IDEMPOTENCY (CN reliability): a retried request id returns the ORIGINAL result.
        prior = conn.execute("SELECT transaction_id,timestamp,status,voter_ref FROM votes WHERE request_id=?",
                             (request_id,)).fetchone()
        if prior:
            if prior["voter_ref"] != ref:
                raise VoteError("REQUEST_ID_CONFLICT", "This request ID belongs to another request.", 409)
            t("REPLAY")
            return {"transaction_id": prior["transaction_id"], "timestamp": prior["timestamp"],
                    "status": prior["status"], "replayed": True}

        # 1-2. election must be ACTIVE
        el = election_service.get_election(conn)
        if not el or el["status"] != "ACTIVE":
            state = el["status"] if el else "NOT_CREATED"
            raise VoteError("ELECTION_CLOSED", f"Voting is not open right now (election is {state}).", 403)
        # 3-4. voter exists and is active
        voter = conn.execute("SELECT has_voted,status FROM voters WHERE voter_id=?", (voter_id,)).fetchone()
        if not voter:
            raise VoteError("INVALID_VOTER", "Voter not found.", 404)
        if voter["status"] != "active":
            raise VoteError("VOTER_SUSPENDED", "This voter account is suspended.", 403)
        # 5. the CHECK of check-then-act
        t("CHECK has_voted=%s" % bool(voter["has_voted"]))
        if voter["has_voted"]:
            old = conn.execute("SELECT transaction_id,timestamp FROM votes WHERE voter_ref=?", (ref,)).fetchone()
            raise VoteError("ALREADY_VOTED", "You have already cast your vote.", 409,
                            transaction_id=old["transaction_id"] if old else None,
                            voted_at=old["timestamp"] if old else None)
        # 6. candidate must exist and be active
        cand = conn.execute("SELECT id FROM candidates WHERE id=? AND status='active'", (candidate_id,)).fetchone()
        if not cand:
            raise VoteError("INVALID_CANDIDATE", "That candidate does not exist.", 404)
        if work_delay:
            time.sleep(work_delay)           # demo only: makes lock waiting visible
        # 7. the ACT: append to the hash-chained ledger
        last = conn.execute("SELECT id,vote_hash FROM votes ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = last["vote_hash"] if last else GENESIS_HASH
        seq = (last["id"] if last else 0) + 1
        tx_id = f"VOTE-{datetime.now().year}-{seq:05d}"
        ts = now_iso()
        vhash = chain_hash(prev_hash, tx_id, ref, candidate_id, ts)
        conn.execute("INSERT INTO votes(transaction_id,voter_ref,candidate_id,request_id,timestamp,status,"
                     "prev_hash,vote_hash) VALUES (?,?,?,?,?,?,?,?)",
                     (tx_id, ref, candidate_id, request_id, ts, "confirmed", prev_hash, vhash))
        t("INSERT vote")
        if fail_at == "after_vote_insert":
            raise RuntimeError("simulated failure after INSERT (rollback demo)")
        conn.execute("UPDATE voters SET has_voted=1 WHERE voter_id=?", (voter_id,))
        conn.execute("UPDATE candidates SET vote_count=vote_count+1 WHERE id=?", (candidate_id,))
        conn.execute("UPDATE election_config SET total_votes=total_votes+1 WHERE id=?", (el["id"],))
        audit_service.log_event(conn, "VOTE_SUCCESS", user=voter_id, request_id=request_id, ip=ip, ua=ua,
                                details=tx_id)
    t("COMMIT")
    return {"transaction_id": tx_id, "timestamp": ts, "status": "confirmed", "replayed": False,
            "receipt": vhash[:16]}


def vote_status(db_path, voter_id, ref_secret):
    ref = voter_ref(voter_id, ref_secret)
    with db(db_path) as conn:
        v = conn.execute("SELECT has_voted FROM voters WHERE voter_id=?", (voter_id,)).fetchone()
        row = conn.execute("SELECT transaction_id,timestamp,status,request_id,vote_hash FROM votes "
                           "WHERE voter_ref=?", (ref,)).fetchone()
    if not v:
        return None
    if row:
        return {"has_voted": True, "transaction_id": row["transaction_id"], "timestamp": row["timestamp"],
                "status": "verified", "request_id": row["request_id"], "receipt": row["vote_hash"][:16]}
    return {"has_voted": False}


def verify_ledger(db_path):
    """Recompute the hash chain and cross-check counters. Detects tampering/inconsistency."""
    with db(db_path) as conn:
        votes = conn.execute("SELECT * FROM votes ORDER BY id").fetchall()
        prev, problems = GENESIS_HASH, []
        for v in votes:
            if v["prev_hash"] != prev:
                problems.append(f"{v['transaction_id']}: broken link to previous vote")
            expected = chain_hash(v["prev_hash"], v["transaction_id"], v["voter_ref"],
                                  v["candidate_id"], v["timestamp"])
            if expected != v["vote_hash"]:
                problems.append(f"{v['transaction_id']}: contents do not match hash (modified)")
            prev = v["vote_hash"]
        per_cand = {r[0]: r[1] for r in conn.execute("SELECT candidate_id,COUNT(*) FROM votes GROUP BY candidate_id")}
        for c in conn.execute("SELECT id,name,vote_count FROM candidates"):
            if c["vote_count"] != per_cand.get(c["id"], 0):
                problems.append(f"counter mismatch for {c['name']}: {c['vote_count']} vs {per_cand.get(c['id'], 0)} ledger votes")
        voted = conn.execute("SELECT COUNT(*) FROM voters WHERE has_voted=1").fetchone()[0]
        if voted != len(votes):
            problems.append(f"voters marked voted ({voted}) != ledger votes ({len(votes)})")
    return {"valid": not problems, "votes_checked": len(votes), "problems": problems,
            "head": prev[:16] if votes else None}
