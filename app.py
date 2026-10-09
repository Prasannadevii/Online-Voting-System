"""NetVote application factory.

Browser --HTTP/TCP--> Flask (threaded: one thread per connection) --> services --> SQLite
"""
import os
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, send_from_directory

from config import BASE_DIR, Config
from backend.database.database import db, init_db
from backend.networking import request_manager
from backend.networking.network_monitor import MONITOR
from backend.utils import logger

FRONTEND_DIR = BASE_DIR / "frontend"
PAGE_RE = re.compile(r"^[a-z0-9-]+\.html$")


def create_app(overrides=None) -> Flask:
    app = Flask(__name__, static_folder=str(BASE_DIR / "static"), static_url_path="/static")
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=app.config["SESSION_MINUTES"])
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024                  # reject oversized bodies (413)
    app.json.sort_keys = False

    logger.setup_logging(app.config["LOG_DIR"])
    if not os.path.exists(app.config["DATABASE_PATH"]):
        init_db(app.config["DATABASE_PATH"])
    MONITOR.set_server(app.config["HOST"], app.config["PORT"])
    request_manager.init_app(app)

    from backend.routes import (admin_routes, auth_routes, monitoring_routes, simulation_routes,
                                voter_routes, voting_routes)
    for mod in (auth_routes, voter_routes, voting_routes, admin_routes, monitoring_routes, simulation_routes):
        app.register_blueprint(mod.bp)

    @app.get("/")
    def home():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:page>")
    def pages(page):
        if (PAGE_RE.match(page) or re.match(r"^[a-zA-Z0-9_\-\.]+\.(jpeg|jpg|png|svg|ico|webp)$", page)) and (FRONTEND_DIR / page).is_file():
            return send_from_directory(FRONTEND_DIR, page)
        from backend.utils.helpers import ApiError
        raise ApiError("NOT_FOUND", "Page not found.", 404)

    logger.get("app").info("NetVote started")
    return app


if __name__ == "__main__":
    from run import main
    main()
