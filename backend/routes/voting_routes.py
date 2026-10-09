"""POST /api/vote and GET /api/vote/status."""
from flask import Blueprint, current_app, g, request

from backend.concurrency.vote_lock import VOTE_LOCK
from backend.security import validation
from backend.security.auth import current_user, login_required
from backend.services import audit_service, voting_service
from backend.utils.helpers import ApiError, client_ip, ok, valid_request_id

bp = Blueprint("voting", __name__, url_prefix="/api")


@bp.post("/vote")
@login_required("voter")
def vote():
    user = current_user()
    data = validation.json_body(request)
    validation.require_fields(data, "candidate_id")
    candidate_id = validation.parse_int(data["candidate_id"], "candidate_id")
    # IDEMPOTENCY KEY: client-chosen request id; a retry re-sends the SAME id.
    rid = data.get("request_id") or g.request_id
    if not valid_request_id(rid):
        raise ApiError("INVALID_REQUEST_ID", "request_id must look like REQ-2026-A82F91B3.", 400)
    g.request_id = rid
    db_path = current_app.config["DATABASE_PATH"]
    audit_service.log(db_path, "VOTE_REQUEST", user=user["voter_id"], request_id=rid, ip=client_ip(),
                      ua=request.user_agent.string, details="vote submitted")
    try:
        result = voting_service.cast_vote(db_path, user["voter_id"], candidate_id, rid, client_ip(),
                                          request.user_agent.string, lock=VOTE_LOCK,
                                          ref_secret=current_app.config["SECRET_KEY"])
    except voting_service.VoteError as exc:
        raise ApiError(exc.code, exc.message, exc.status, **exc.extra)
    return ok({"transaction_id": result["transaction_id"], "status": result["status"],
               "timestamp": result["timestamp"], "replayed": result["replayed"],
               "receipt": result.get("receipt"),
               "message": ("This request was already processed - original result returned."
                           if result["replayed"] else "Your vote has been recorded.")},
              status=200 if result["replayed"] else 201)


@bp.get("/vote/status")
@login_required("voter")
def status():
    user = current_user()
    st = voting_service.vote_status(current_app.config["DATABASE_PATH"], user["voter_id"],
                                    current_app.config["SECRET_KEY"])
    return ok(st or {"has_voted": False})
