"""Request lifecycle: request IDs, rate limiting, security headers, logging, error handling.

CN CONCEPT: HTTP request/response model, status codes (400/401/403/404/405/409/429/500/503),
            application-layer rate limiting, request tracing with correlation IDs.
OS CONCEPT: PRODUCER/CONSUMER - request threads (producers) push log records onto a queue;
            one background writer thread (consumer) batches them into SQLite, so slow disk
            writes never block voters.
"""
import queue
import threading
import time

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException

from backend.database.database import db
from backend.networking.network_monitor import MONITOR
from backend.networking.rate_limiter import SlidingWindowLimiter
from backend.security.auth import current_user
from backend.services import audit_service
from backend.utils import logger
from backend.utils.helpers import ApiError, client_ip, new_request_id, now_iso, valid_request_id

SENSITIVE = {("POST", "/api/auth/login"), ("POST", "/api/auth/register"),
             ("POST", "/api/auth/admin-login"), ("POST", "/api/vote")}
# Polling endpoints used by the dashboards: excluded from statistics so they don't skew them.
MONITORING_PATHS = {"/api/admin/network", "/api/admin/system-health", "/api/admin/dashboard",
                    "/api/admin/concurrency-status", "/api/auth/me"}
RATE_EXEMPT_PREFIXES = ("/api/sim/",)

sensitive_limiter = SlidingWindowLimiter(20, 60, "sensitive (login/register/vote)")
general_limiter = SlidingWindowLimiter(300, 60, "general API")


class RequestLogWriter:
    """Background consumer that persists request rows."""

    def __init__(self):
        self.q = queue.Queue(maxsize=5000)
        self.thread = None
        self.written = self.dropped = 0
        self.db_path = None

    def start(self, db_path):
        self.db_path = db_path
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="request-log-writer", daemon=True)
        self.thread.start()

    def put(self, row):
        try:
            self.q.put_nowait(row)
        except queue.Full:
            self.dropped += 1

    def _run(self):
        while True:
            batch = [self.q.get()]
            try:
                while len(batch) < 100:
                    batch.append(self.q.get_nowait())
            except queue.Empty:
                pass
            try:
                with db(self.db_path) as conn:
                    conn.execute("BEGIN")
                    conn.executemany(
                        "INSERT INTO requests(request_id,request_type,user_id,status,response_code,created_at,"
                        "completed_at,processing_time_ms,ip_address) VALUES (?,?,?,?,?,?,?,?,?)", batch)
                    conn.execute("COMMIT")
                self.written += len(batch)
            except Exception as exc:
                logger.get("error").error(f"request log writer: {exc}")
            finally:
                for _ in batch:
                    self.q.task_done()

    def flush(self, timeout=5.0):
        end = time.time() + timeout
        while self.q.unfinished_tasks and time.time() < end:
            time.sleep(0.01)


LOG_WRITER = RequestLogWriter()


def _is_api():
    return request.path.startswith("/api/")


def init_app(app):
    sensitive_limiter.limit = app.config["RATE_LIMIT_SENSITIVE"]
    sensitive_limiter.window = general_limiter.window = app.config["RATE_LIMIT_WINDOW"]
    general_limiter.limit = app.config["RATE_LIMIT_GENERAL"]
    sensitive_limiter.reset(); general_limiter.reset()
    LOG_WRITER.start(app.config["DATABASE_PATH"])

    @app.before_request
    def _before():
        g.start = time.perf_counter()
        g.counted = _is_api() and request.path not in MONITORING_PATHS
        rid = request.headers.get("X-Request-ID")
        g.request_id = rid if valid_request_id(rid) else new_request_id()
        if g.counted:
            MONITOR.request_started()
        if not _is_api():
            return None
        # --- CSRF defence: state-changing calls must carry a custom header (a cross-site
        # HTML form cannot add one without a CORS pre-flight, which we never allow).
        if request.method in ("POST", "PUT", "DELETE", "PATCH") and \
                request.headers.get("X-Requested-With") != "NetVote":
            raise ApiError("CSRF_BLOCKED", "Missing X-Requested-With header.", 403)
        # --- Rate limiting (application layer)
        if app.config["RATE_LIMIT_ENABLED"] and not request.path.startswith(RATE_EXEMPT_PREFIXES) \
                and request.path not in MONITORING_PATHS:
            ip = client_ip()
            lim = sensitive_limiter if (request.method, request.path) in SENSITIVE else general_limiter
            allowed, retry, _ = lim.check(ip)
            if not allowed:
                if lim.should_flag(ip):
                    audit_service.log(app.config["DATABASE_PATH"], "RATE_LIMIT_TRIGGERED", user=ip,
                                      request_id=g.request_id, ip=ip, ua=request.user_agent.string,
                                      details=f"{lim.name}: > {lim.limit}/{int(lim.window)}s",
                                      severity="WARNING", status="BLOCKED")
                raise ApiError("RATE_LIMITED", "Too many requests. Please wait before trying again.", 429,
                               retry_after=retry)
        return None

    @app.after_request
    def _after(resp):
        rid = getattr(g, "request_id", None)
        if rid:
            resp.headers["X-Request-ID"] = rid
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if _is_api():
            resp.headers["Cache-Control"] = "no-store"
            if resp.status_code == 429 and resp.is_json:
                ra = (resp.get_json(silent=True) or {}).get("error", {}).get("retry_after")
                if ra:
                    resp.headers["Retry-After"] = str(ra)
        else:
            resp.headers.setdefault("Cache-Control", "no-cache")
        if hasattr(g, "start"):
            ms = (time.perf_counter() - g.start) * 1000
            user = current_user()
            uname = (user or {}).get("voter_id") or ((user or {}).get("role") or "-")
            if getattr(g, "counted", False):
                MONITOR.request_finished(request.method, request.path, resp.status_code, ms,
                                         client_ip(), rid)
                logger.get("network").info(f"{rid} | {request.method} {request.path} | {client_ip()} | "
                                           f"USER {uname} | {resp.status_code} | {ms:.0f}ms")
                if request.method != "GET":
                    LOG_WRITER.put((rid, f"{request.method} {request.path}", uname,
                                    "ok" if resp.status_code < 400 else "failed", resp.status_code,
                                    now_iso(), now_iso(), round(ms, 2), client_ip()))
        return resp

    @app.errorhandler(ApiError)
    def _api_error(exc):
        body = {"success": False, "request_id": getattr(g, "request_id", None),
                "error": {"code": exc.code, "message": exc.message}}
        body["error"].update(exc.extra)
        return jsonify(body), exc.status

    def _http(status, code, msg):
        def handler(_e):
            return jsonify({"success": False, "request_id": getattr(g, "request_id", None),
                            "error": {"code": code, "message": msg}}), status
        return handler

    for status, code, msg in ((400, "BAD_REQUEST", "The request could not be understood."),
                              (404, "NOT_FOUND", "The requested resource was not found."),
                              (405, "METHOD_NOT_ALLOWED", "This HTTP method is not allowed here."),
                              (413, "PAYLOAD_TOO_LARGE", "The request is too large."),
                              (415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json.")):
        app.register_error_handler(status, _http(status, code, msg))

    @app.errorhandler(Exception)
    def _unhandled(exc):
        rid = getattr(g, "request_id", None)
        if isinstance(exc, HTTPException):          # any other HTTP error keeps its own status
            return jsonify({"success": False, "request_id": rid,
                            "error": {"code": exc.name.upper().replace(" ", "_"),
                                      "message": exc.description}}), exc.code
        logger.get("error").exception(f"{rid} unhandled error on {request.method} {request.path}: {exc}")
        audit_service.system_event(app.config["DATABASE_PATH"], "SERVER_ERROR", "ERROR",
                                   f"{rid} {type(exc).__name__}")
        # Never leak a stack trace to the browser.
        return jsonify({"success": False, "request_id": rid,
                        "error": {"code": "SERVER_ERROR",
                                  "message": "Something went wrong on the server. Please try again."}}), 500
