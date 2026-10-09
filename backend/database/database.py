"""SQLite access layer.

DATABASE CONCEPT: every thread uses its own connection (sqlite3 connections must not be
shared freely between threads). WAL mode lets readers proceed while one writer commits.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path, timeout: float = 15.0) -> sqlite3.Connection:
    # isolation_level=None => autocommit; we issue BEGIN/COMMIT/ROLLBACK explicitly
    # (see utils/transaction.py) so transaction boundaries are visible in the code.
    conn = sqlite3.connect(str(path), timeout=timeout, isolation_level=None,
                           check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def db(path, timeout: float = 15.0):
    conn = connect(path, timeout)
    try:
        yield conn
    finally:
        conn.close()


def init_db(path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with db(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def rows(cursor) -> list:
    return [dict(r) for r in cursor.fetchall()]
