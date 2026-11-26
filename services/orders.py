import sqlite3
from datetime import datetime, timezone

import db
from services import pricing


class ConflictError(Exception):
    pass


NEXT_STATUS = {
    "Pending": "Processing",
    "Processing": "Ready for Pickup",
    "Ready for Pickup": "Completed",
}

PAYMENT_METHODS = ("cash", "gcash", "maya")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def create_order(conn, user_id, file_info, paper_size, color_mode, page_count, copies):
    total = pricing.calculate_total(conn, paper_size, color_mode, page_count, copies)
    now = _now()
    try:
        with db.transaction(conn):
            cur = conn.execute(
                """
                INSERT INTO print_orders
                    (user_id, original_filename, file_path, paper_size, color_mode,
                     page_count, copies, total_price, last_modified_by,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    file_info["original_filename"],
                    file_info["stored_path"],
                    paper_size,
                    color_mode,
                    page_count,
                    copies,
                    total,
                    user_id,
                    now,
                    now,
                ),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError as e:
        raise ValueError(f"Could not create order: {e}") from e


def get_order(conn, order_id):
    return conn.execute(
        """
        SELECT o.*, u.name AS user_name, u.email AS user_email
        FROM print_orders o
        JOIN users u ON u.user_id = o.user_id
        WHERE o.order_id = ?
        """,
        (order_id,),
    ).fetchone()


def list_orders_for_user(conn, user_id):
    return conn.execute(
        """
        SELECT * FROM print_orders
        WHERE user_id = ?
        ORDER BY created_at DESC, order_id DESC
        """,
        (user_id,),
    ).fetchall()


def list_queue(conn):
    return conn.execute("SELECT * FROM v_queue").fetchall()


def advance_status(conn, order_id, expected_version, changed_by):
    row = conn.execute(
        "SELECT order_status FROM print_orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Order not found")

    next_status = NEXT_STATUS.get(row["order_status"])
    if next_status is None:
        raise ValueError("Order is already Completed")

    try:
        with db.transaction(conn):
            cur = conn.execute(
                """
                UPDATE print_orders
                SET order_status = ?,
                    version = version + 1,
                    last_modified_by = ?,
                    updated_at = ?
                WHERE order_id = ? AND version = ?
                """,
                (next_status, changed_by, _now(), order_id, expected_version),
            )
            if cur.rowcount == 0:
                raise ConflictError(
                    "This order was changed by someone else. Reload and try again."
                )
    except sqlite3.IntegrityError as e:
        raise ValueError(str(e)) from e
    return next_status


def mark_paid(conn, order_id, received_by, method):
    if method not in PAYMENT_METHODS:
        raise ValueError("Payment method must be cash, gcash, or maya")

    order = conn.execute(
        "SELECT total_price, payment_status FROM print_orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    if order is None:
        raise ValueError("Order not found")
    if order["payment_status"] == "paid":
        raise ValueError("Order is already paid")

    try:
        with db.transaction(conn):
            cur = conn.execute(
                """
                INSERT INTO payments (order_id, amount, method, received_by, paid_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, order["total_price"], method, received_by, _now()),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError as e:
        raise ValueError(f"Could not record payment: {e}") from e
