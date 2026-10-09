"""Structured logging to logs/application.log, network.log, audit.log, error.log."""
import logging
import os
from logging.handlers import RotatingFileHandler

_configured = False


def setup_logging(log_dir: str) -> None:
    global _configured
    if _configured:
        return
    os.makedirs(log_dir, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    for name, fname, level in (("netvote.app", "application.log", logging.INFO),
                               ("netvote.network", "network.log", logging.INFO),
                               ("netvote.audit", "audit.log", logging.INFO),
                               ("netvote.error", "error.log", logging.ERROR)):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = False
        h = RotatingFileHandler(os.path.join(log_dir, fname), maxBytes=1_000_000,
                                backupCount=3, encoding="utf-8", delay=True)
        h.setFormatter(fmt)
        lg.addHandler(h)
    _configured = True


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"netvote.{name}")
