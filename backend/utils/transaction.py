"""Transaction manager.

OS/DB CONCEPT - ATOMICITY: all statements inside `with transaction(conn):` either all
become permanent (COMMIT) or none do (ROLLBACK). BEGIN IMMEDIATE additionally takes
SQLite's write lock up-front, so even a second *process* cannot interleave.
"""
import sqlite3
from contextlib import contextmanager


@contextmanager
def transaction(conn, immediate: bool = True):
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
