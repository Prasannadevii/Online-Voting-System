"""Public / voter read endpoints: election info, candidates, profile, results, receipts."""
from flask import Blueprint, current_app, request

from backend.database.database import db, rows
from backend.security.auth import current_user, login_required
from backend.services import election_service, voting_service
from backend.utils.helpers import ApiError, ok

bp = Blueprint("voter", __name__, url_prefix="/api")


def _path():
    return current_app.config["DATABASE_PATH"]


@bp.get("/election")
def election():
    with db(_path()) as c:
        el = election_service.get_election(c)
        tail = rows(c.execute("SELECT transaction_id,vote_hash FROM votes ORDER BY id DESC LIMIT 5"))
    if not el:
        raise ApiError("NO_ELECTION", "No election has been created yet.", 404)
    # Public ledger tail: transaction ids + truncated hashes only (no choices, no voters).
    el["ledger_tail"] = [{"transaction_id": r["transaction_id"], "hash": (r["vote_hash"] or "")[:12]} for r in tail]
    return ok({"election": el})


@bp.get("/candidates")
def candidates():
    with db(_path()) as c:
        data = rows(c.execute("SELECT id,name,party,symbol,color,description FROM candidates "
                              "WHERE status='active' ORDER BY id"))
    return ok({"candidates": data})


@bp.get("/voter/profile")
@login_required("voter")
def profile():
    user = current_user()
    st = voting_service.vote_status(_path(), user["voter_id"], current_app.config["SECRET_KEY"])
    el = election_service.current(_path())
    return ok({"profile": {"voter_id": user["voter_id"], "name": user["name"], **(st or {"has_voted": False})},
               "election": el})


@bp.get("/results")
def results():
    user = current_user()
    el = election_service.current(_path())
    if not el:
        raise ApiError("NO_ELECTION", "No election has been created yet.", 404)
    is_admin = user and user["role"] == "admin"
    if not is_admin and el["status"] != "ENDED":
        # Ballot secrecy / fairness: results are published only after the election ends.
        raise ApiError("RESULTS_NOT_PUBLISHED", "Results will be published when the election ends.", 403,
                       election_status=el["status"])
    with db(_path()) as c:
        cands = rows(c.execute("SELECT id,name,party,symbol,color,vote_count FROM candidates "
                               "WHERE status='active' ORDER BY vote_count DESC, id"))
    total = sum(x["vote_count"] for x in cands)
    for x in cands:
        x["percent"] = round(100 * x["vote_count"] / total, 1) if total else 0.0
    return ok({"election": el, "results": cands, "total_votes": total, "final": el["status"] == "ENDED",
               "live": el["status"] != "ENDED"})


@bp.get("/verify-receipt")
def verify_receipt():
    tx = (request.args.get("transaction_id") or "").strip()[:40]
    with db(_path()) as c:
        row = c.execute("SELECT transaction_id,timestamp,status,vote_hash FROM votes WHERE transaction_id=?",
                        (tx,)).fetchone()
    if not row:
        return ok({"found": False})
    return ok({"found": True, "transaction_id": row["transaction_id"], "timestamp": row["timestamp"],
               "status": "verified", "hash": row["vote_hash"][:16]})
