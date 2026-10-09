"""Small shared helpers: timestamps, request IDs, JSON envelopes."""
import re
import secrets
from datetime import datetime

from flask import g, jsonify, request

REQUEST_ID_RE = re.compile(r"^REQ-\d{4}-[A-Z0-9]{6,16}$")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_request_id() -> str:
    """CN CONCEPT: a correlation ID lets one client/server exchange be traced end-to-end
    (browser -> server log -> audit log -> error message)."""
    return f"REQ-{datetime.now().year}-{secrets.token_hex(4).upper()}"


def valid_request_id(value) -> bool:
    return isinstance(value, str) and bool(REQUEST_ID_RE.match(value))


def client_ip() -> str:
    return request.remote_addr or "unknown"


def ok(data=None, status=200, **extra):
    body = {"success": True, "request_id": getattr(g, "request_id", None)}
    if data:
        body.update(data)
    body.update(extra)
    return jsonify(body), status


def fail(code, message, status=400, **extra):
    body = {"success": False, "request_id": getattr(g, "request_id", None),
            "error": {"code": code, "message": message}}
    body.update(extra)
    return jsonify(body), status


class ApiError(Exception):
    """Raised anywhere in a route/service; converted to a JSON error by the app."""

    def __init__(self, code, message, status=400, **extra):
        super().__init__(message)
        self.code, self.message, self.status, self.extra = code, message, status, extra
