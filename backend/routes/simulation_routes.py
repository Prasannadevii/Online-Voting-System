"""Educational demonstrations. Every one runs on an isolated demo DB / simulation."""
import time

from flask import Blueprint, current_app, g, request

from backend.security import validation
from backend.security.auth import current_user, login_required
from backend.services import audit_service, concurrency_service as cs
from backend.concurrency import os_demos, race_demo
from backend.utils.helpers import ApiError, client_ip, ok

bp = Blueprint("simulation", __name__, url_prefix="/api")


@bp.get("/sim/ping")
def ping():
    """Harmless endpoint for the network lab: sleeps `delay` ms (max 5 s). Touches no data."""
    try:
        delay = max(0, min(int(request.args.get("delay", 0)), 5000))
    except ValueError:
        raise ApiError("INVALID_FIELD", "delay must be an integer (ms).", 400)
    time.sleep(delay / 1000)
    return ok({"pong": True, "delay_ms": delay, "server_time": time.strftime("%H:%M:%S")})


def _audit(action, details):
    audit_service.log(current_app.config["DATABASE_PATH"], action, user=current_user()["name"],
                      request_id=g.request_id, ip=client_ip(), ua=request.user_agent.string, details=details)


@bp.post("/admin/concurrency-test")
@login_required("admin")
def concurrency_test():
    d = validation.json_body(request)
    mode = d.get("mode", "same_voter")
    sync = d.get("synchronization", True)
    executor = d.get("executor", "threads")
    n = validation.parse_int(d.get("requests", 100), "requests")
    if mode not in ("same_voter", "multiple_voters") or executor not in ("threads", "pool") \
            or not isinstance(sync, bool):
        raise ApiError("INVALID_FIELD", "Invalid test parameters.", 400)
    if not 2 <= n <= current_app.config["MAX_CONCURRENCY_TEST"]:
        raise ApiError("INVALID_FIELD", f"requests must be 2-{current_app.config['MAX_CONCURRENCY_TEST']}.", 400)
    result = cs.concurrency_test(current_app.config["DATABASE_PATH"], mode, n, sync, executor)
    _audit("CONCURRENCY_TEST", f"{mode} n={n} sync={sync} -> {result['race_condition']}")
    return ok({"result": result})


@bp.post("/admin/network-test")
@login_required("admin")
def network_test():
    d = validation.json_body(request)
    delay = validation.parse_int(d.get("delay_ms", 0), "delay_ms")
    timeout = validation.parse_int(d.get("timeout_ms", 2000), "timeout_ms")
    burst = validation.parse_int(d.get("burst", 0), "burst")
    if not (0 <= delay <= 5000 and 100 <= timeout <= 10000 and 0 <= burst <= 300):
        raise ApiError("INVALID_FIELD", "delay 0-5000 ms, timeout 100-10000 ms, burst 0-300.", 400)
    host, _, port = request.host.partition(":")
    result = cs.network_test(host or "127.0.0.1", int(port or 80), delay, timeout, burst,
                             current_app.config["DATABASE_PATH"], current_user()["name"], client_ip())
    return ok({"result": result})


@bp.post("/admin/demo/<name>")
@login_required("admin")
def demo(name):
    d = request.get_json(silent=True) or {}
    if name == "race-trace":
        result = race_demo.race_trace(bool(d.get("synchronization", True)))
        result["label"] = cs.LABEL
    elif name == "deadlock":
        result = cs.deadlock_demo(d.get("strategy", "deadlock"))
    elif name == "starvation":
        result = os_demos.run_starvation()
    elif name == "rollback":
        result = cs.rollback_demo()
    elif name == "retry":
        result = cs.retry_demo()
    elif name == "rate-limit":
        result = cs.ratelimit_demo()
    elif name == "tamper":
        result = cs.tamper_demo()
    elif name == "tcp":
        result = cs.tcp_demo()
    else:
        raise ApiError("NOT_FOUND", "Unknown demonstration.", 404)
    _audit("DEMO_RUN", name)
    return ok({"result": result})
