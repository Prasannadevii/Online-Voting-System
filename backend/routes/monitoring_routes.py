"""Live monitoring endpoints (polled by the dashboards)."""
from flask import Blueprint, current_app

from backend.networking import request_manager
from backend.networking.network_monitor import MONITOR
from backend.security.auth import login_required
from backend.services import monitoring_service, voting_service
from backend.utils.helpers import ok

bp = Blueprint("monitoring", __name__, url_prefix="/api/admin")


@bp.get("/dashboard")
@login_required("admin")
def dashboard():
    return ok(monitoring_service.dashboard(current_app.config["DATABASE_PATH"]))


@bp.get("/network")
@login_required("admin")
def network():
    return ok({"snapshot": MONITOR.snapshot(), "series": MONITOR.series(90),
               "rate_limit": {"sensitive": request_manager.sensitive_limiter.stats(),
                              "general": request_manager.general_limiter.stats()},
               "concurrency": monitoring_service.concurrency_status()})


@bp.get("/system-health")
@login_required("admin")
def system_health():
    return ok(monitoring_service.system_health(current_app.config["DATABASE_PATH"]))


@bp.get("/concurrency-status")
@login_required("admin")
def concurrency_status():
    return ok(monitoring_service.concurrency_status())


@bp.get("/ledger-verify")
@login_required("admin")
def ledger_verify():
    return ok({"ledger": voting_service.verify_ledger(current_app.config["DATABASE_PATH"])})
