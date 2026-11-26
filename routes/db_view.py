import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, abort, render_template

from db import get_db
from routes.auth import login_required

bp = Blueprint("db_view", __name__)

ROW_LIMIT = 500
HIGHLIGHT_SECONDS = 30
HIDDEN_COLUMNS = ("password_hash",)

OBJECTS = {
    "users": {
        "kind": "table",
        "count": "SELECT COUNT(*) FROM users",
        "rows": "SELECT * FROM users ORDER BY user_id LIMIT %d" % ROW_LIMIT,
        "time": (),
    },
    "pricing_rates": {
        "kind": "table",
        "count": "SELECT COUNT(*) FROM pricing_rates",
        "rows": "SELECT * FROM pricing_rates ORDER BY rate_id LIMIT %d" % ROW_LIMIT,
        "time": (),
    },
    "print_orders": {
        "kind": "table",
        "count": "SELECT COUNT(*) FROM print_orders",
        "rows": "SELECT * FROM print_orders ORDER BY order_id DESC LIMIT %d" % ROW_LIMIT,
        "time": ("updated_at", "created_at"),
    },
    "payments": {
        "kind": "table",
        "count": "SELECT COUNT(*) FROM payments",
        "rows": "SELECT * FROM payments ORDER BY payment_id DESC LIMIT %d" % ROW_LIMIT,
        "time": ("paid_at",),
    },
    "status_logs": {
        "kind": "table",
        "count": "SELECT COUNT(*) FROM status_logs",
        "rows": "SELECT * FROM status_logs ORDER BY log_id DESC LIMIT %d" % ROW_LIMIT,
        "time": ("changed_at",),
    },
    "v_queue": {
        "kind": "view",
        "count": "SELECT COUNT(*) FROM v_queue",
        "rows": "SELECT * FROM v_queue LIMIT %d" % ROW_LIMIT,
        "time": ("updated_at", "created_at"),
    },
    "v_order_details": {
        "kind": "view",
        "count": "SELECT COUNT(*) FROM v_order_details",
        "rows": "SELECT * FROM v_order_details LIMIT %d" % ROW_LIMIT,
        "time": ("updated_at", "created_at"),
    },
}


def open_readonly():
    conn = get_db()
    conn.execute("PRAGMA query_only = ON")
    return conn


def ages_in_seconds(value):
    if not isinstance(value, str):
        return []
    try:
        stamp = datetime.fromisoformat(value.strip())
    except ValueError:
        return []
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
        return [(now_utc - stamp).total_seconds()]
    return [(now_utc - stamp).total_seconds(),
            (datetime.now() - stamp).total_seconds()]


def is_recent(row, time_columns):
    keys = row.keys()
    for column in time_columns:
        if column not in keys:
            continue
        for age in ages_in_seconds(row[column]):
            if -2 <= age <= HIGHLIGHT_SECONDS:
                return True
    return False


def show_value(column, value):
    if column in HIDDEN_COLUMNS and value is not None:
        return "(hidden)"
    return value


def count_rows(conn, name):
    try:
        return conn.execute(OBJECTS[name]["count"]).fetchone()[0]
    except sqlite3.Error:
        return None


@bp.route("/db")
@login_required
def index():
    conn = open_readonly()
    try:
        entries = [{"name": name, "kind": info["kind"],
                    "count": count_rows(conn, name)}
                   for name, info in OBJECTS.items()]
    finally:
        conn.close()
    return render_template("db_view.html", mode="index", entries=entries,
                           names=list(OBJECTS), highlight=HIGHLIGHT_SECONDS)


@bp.route("/db/<table>")
@login_required
def show_table(table):
    if table not in OBJECTS:
        abort(404)
    info = OBJECTS[table]

    conn = open_readonly()
    error = None
    columns = []
    rows = []
    total = None
    try:
        try:
            cursor = conn.execute(info["rows"])
            columns = [d[0] for d in cursor.description]
            raw_rows = cursor.fetchall()
            total = conn.execute(info["count"]).fetchone()[0]
        except sqlite3.Error as exc:
            error = "This %s could not be read: %s" % (info["kind"], exc)
            raw_rows = []
    finally:
        conn.close()

    has_time = any(c in columns for c in info["time"])
    for raw in raw_rows:
        rows.append({
            "cells": [show_value(c, raw[c]) for c in columns],
            "key": str(raw[columns[0]]),
            "recent": has_time and is_recent(raw, info["time"]),
        })

    page = render_template("db_view.html", mode="table", name=table,
                           kind=info["kind"], columns=columns, rows=rows,
                           total=total, limit=ROW_LIMIT, error=error,
                           track_diff=not has_time, names=list(OBJECTS),
                           highlight=HIGHLIGHT_SECONDS)
    return page, (500 if error else 200)
