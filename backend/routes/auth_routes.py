"""Authentication endpoints."""
from flask import Blueprint, current_app, request

from backend.security import validation
from backend.security.auth import current_user, login_session
from backend.services import audit_service, auth_service, election_service
from backend.utils.helpers import client_ip, ok
from flask import g as flask_g, session

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _ctx():
    return (current_app.config["DATABASE_PATH"], current_app.config["HASH_ITERATIONS"],
            flask_g.request_id, client_ip(), request.user_agent.string)


@bp.post("/register")
def register():
    path, iters, rid, ip, ua = _ctx()
    data = validation.validate_registration(validation.json_body(request))
    auth_service.register_voter(path, data, iters, rid, ip, ua)
    return ok({"message": "Registration successful. You can now log in."}, status=201)


@bp.post("/login")
def login():
    path, iters, rid, ip, ua = _ctx()
    data = validation.json_body(request)
    validation.require_fields(data, "voter_id", "password")
    voter_id = validation.clean_str(data["voter_id"], "Voter ID", 1, 40)
    row = auth_service.login_voter(path, voter_id, str(data["password"]), iters, rid, ip, ua)
    login_session("voter", row["id"], voter_id=row["voter_id"], name=row["name"])
    return ok({"role": "voter", "name": row["name"], "voter_id": row["voter_id"]})


@bp.post("/admin-login")
def admin_login():
    path, iters, rid, ip, ua = _ctx()
    data = validation.json_body(request)
    validation.require_fields(data, "username", "password")
    username = validation.clean_str(data["username"], "Username", 1, 40)
    row = auth_service.login_admin(path, username, str(data["password"]), iters, rid, ip, ua)
    login_session("admin", row["id"], name=row["username"])
    return ok({"role": "admin", "name": row["username"]})


@bp.post("/logout")
def logout():
    user = current_user()
    if user:
        audit_service.log(current_app.config["DATABASE_PATH"], "LOGOUT", user=user.get("voter_id") or user["name"],
                          request_id=flask_g.request_id, ip=client_ip(), ua=request.user_agent.string)
    session.clear()
    return ok({"message": "Logged out."})


@bp.get("/me")
def me():
    user = current_user()
    el = election_service.current(current_app.config["DATABASE_PATH"])
    return ok({"authenticated": bool(user), "user": user,
               "election_status": el["status"] if el else None})
