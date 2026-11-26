import os
import sqlite3
from contextlib import contextmanager

from flask import current_app, g, has_app_context

import config


def open_connection(path=None):
    if path is None:
        path = current_app.config["DATABASE"] if has_app_context() else config.DATABASE
    if path != ":memory:" and not os.path.exists(path):
        raise FileNotFoundError(
            "Database file not found: " + path + ". Run: python db/init_db.py"
        )
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if not has_app_context():
        return open_connection()
    if "db" not in g:
        g.db = open_connection()
    return g.db


def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction(conn=None):
    owns_connection = conn is None and not has_app_context()
    if conn is None:
        conn = get_db()
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()
