import sqlite3
from datetime import datetime

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, session, url_for)

from db import get_db
from routes.auth import role_required
from routes.student import order_code
from services import orders

bp = Blueprint("staff", __name__)

STAFF_ROLES = ("staff", "admin")
STATUS_FLOW = ("Pending", "Processing", "Ready for Pickup", "Completed")
ACTIVE_STATUSES = STATUS_FLOW[:3]
PAYMENT_METHODS = ("cash", "gcash", "maya")

CONFLICT_MESSAGE = ("Someone else updated this order while you were looking "
                    "at it. Reload the page to see the latest version.")


def next_status(current):
    position = STATUS_FLOW.index(current)
    if position + 1 < len(STATUS_FLOW):
        return STATUS_FLOW[position + 1]
    return None


def prepare(row):
    data = dict(row)
    data["code"] = order_code(data["order_id"])
    data["customer"] = (data.get("user_name") or data.get("name")
                        or data.get("customer_name") or "")
    return data


def database_message(exc):
    text = str(exc).strip()
    if "UNIQUE" in text.upper():
        return "This order has already been paid."
    return text or "The database rejected this change."


@bp.route("/staff/queue")
@role_required(*STAFF_ROLES)
def queue():
    selected = request.args.get("status", "all")
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM v_queue ORDER BY created_at ASC, order_id ASC"
        ).fetchall()
        items = [prepare(r) for r in rows]
    finally:
        conn.close()

    counts = {status: 0 for status in ACTIVE_STATUSES}
    for item in items:
        counts[item["order_status"]] = counts.get(item["order_status"], 0) + 1
    total = len(items)

    if selected in ACTIVE_STATUSES:
        items = [i for i in items if i["order_status"] == selected]
    else:
        selected = "all"

    return render_template("staff/queue.html", orders=items, counts=counts,
                           total=total, selected=selected,
                           statuses=ACTIVE_STATUSES,
                           refreshed_at=datetime.now().strftime("%H:%M:%S"))


@bp.route("/staff/orders/<int:order_id>")
@role_required(*STAFF_ROLES)
def order_page(order_id):
    conn = get_db()
    try:
        row = orders.get_order(conn, order_id)
        if row is None:
            abort(404)
        order = prepare(row)
        owner = conn.execute(
            "SELECT name FROM users WHERE user_id = ?", (order["user_id"],)
        ).fetchone()
        if owner:
            order["customer"] = owner["name"]
        history = conn.execute(
            "SELECT s.old_status, s.new_status, s.changed_at, "
            "u.name AS changed_by_name "
            "FROM status_logs s JOIN users u ON u.user_id = s.changed_by "
            "WHERE s.order_id = ? ORDER BY s.log_id",
            (order_id,),
        ).fetchall()
        payment = conn.execute(
            "SELECT p.amount, p.method, p.paid_at, u.name AS received_by_name "
            "FROM payments p JOIN users u ON u.user_id = p.received_by "
            "WHERE p.order_id = ?",
            (order_id,),
        ).fetchone()
        history = [dict(h) for h in history]
        payment = dict(payment) if payment else None
    finally:
        conn.close()
    return render_template("staff/order.html", order=order, history=history,
                           payment=payment,
                           next_status=next_status(order["order_status"]),
                           payment_methods=PAYMENT_METHODS)


@bp.route("/staff/orders/<int:order_id>/advance", methods=["POST"])
@role_required(*STAFF_ROLES)
def advance(order_id):
    conn = get_db()
    try:
        if orders.get_order(conn, order_id) is None:
            abort(404)
        try:
            version = int(request.form.get("version", ""))
        except ValueError:
            flash("The order version is missing. Reload the page and try "
                  "again.", "error")
        else:
            try:
                new_status = orders.advance_status(conn, order_id, version,
                                                   session["user_id"])
                flash("Order %s is now %s." % (order_code(order_id),
                                               new_status), "success")
            except orders.ConflictError:
                conn.rollback()
                flash(CONFLICT_MESSAGE, "warning")
            except sqlite3.Error as exc:
                conn.rollback()
                flash(database_message(exc), "error")
            except ValueError as exc:
                conn.rollback()
                flash(str(exc), "error")
    finally:
        conn.close()
    return redirect(url_for("staff.order_page", order_id=order_id))


@bp.route("/staff/orders/<int:order_id>/pay", methods=["POST"])
@role_required(*STAFF_ROLES)
def pay(order_id):
    method = request.form.get("method", "")
    conn = get_db()
    try:
        if orders.get_order(conn, order_id) is None:
            abort(404)
        if method not in PAYMENT_METHODS:
            flash("Pick cash, GCash or Maya as the payment method.", "error")
        else:
            try:
                orders.mark_paid(conn, order_id, session["user_id"], method)
                flash("Payment recorded for %s." % order_code(order_id),
                      "success")
            except sqlite3.Error as exc:
                conn.rollback()
                flash(database_message(exc), "error")
            except ValueError as exc:
                conn.rollback()
                flash(str(exc), "error")
    finally:
        conn.close()
    return redirect(url_for("staff.order_page", order_id=order_id))
