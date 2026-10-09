"""Session-based authentication + role-based authorisation."""
from functools import wraps

from flask import session

from backend.utils.helpers import ApiError


def login_session(role: str, uid, **extra) -> None:
    session.clear()                      # prevents session fixation
    session.permanent = True
    session.update({"role": role, "uid": uid, **extra})


def current_user():
    if "role" not in session:
        return None
    return {"role": session["role"], "uid": session.get("uid"),
            "voter_id": session.get("voter_id"), "name": session.get("name")}


def login_required(role: str):
    """401 = not authenticated, 403 = authenticated but wrong role (authorisation)."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            user = current_user()
            if not user:
                raise ApiError("UNAUTHENTICATED", "Please log in to continue.", 401)
            if user["role"] != role:
                raise ApiError("FORBIDDEN", "You do not have permission to access this resource.", 403)
            return fn(*a, **kw)
        return wrapper
    return deco
