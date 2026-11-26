import sqlite3
from decimal import Decimal, InvalidOperation

from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)

from db import get_db
from routes.auth import role_required
from routes.student import order_code

bp = Blueprint("admin", __name__)

PAPER_ORDER = {"A4": 0, "Letter": 1, "Legal": 2}
COLOR_ORDER = {"bw": 0, "color": 1}
COLOR_LABELS = {"bw": "Black and white", "color": "Color"}
MAX_PRICE = Decimal("10000")
LOG_LIMIT = 500


def parse_price(text):
    text = (text or "").strip()
    if not text:
        raise ValueError("Enter a price.")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError("Enter a number.")
    if not value.is_finite():
        raise ValueError("Enter a number.")
    if value < 0:
        raise ValueError("Price cannot be negative.")
    if value > MAX_PRICE:
        raise ValueError("Price cannot be more than 10,000.")
    if value != value.quantize(Decimal("0.01")):
        raise ValueError("Use at most 2 decimal places.")
    return float(value)


def load_rates(conn):
    rows = conn.execute(
        "SELECT rate_id, paper_size, color_mode, price_per_page "
        "FROM pricing_rates"
    ).fetchall()
    rates = []
    for row in rows:
        rate = dict(row)
        rate["color_label"] = COLOR_LABELS.get(rate["color_mode"],
                                               rate["color_mode"])
        rate["input"] = "%.2f" % rate["price_per_page"]
        rate["error"] = None
        rates.append(rate)
    rates.sort(key=lambda r: (PAPER_ORDER.get(r["paper_size"], 99),
                              COLOR_ORDER.get(r["color_mode"], 99)))
    return rates


def save_rates(conn, updates):
    try:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "UPDATE pricing_rates SET price_per_page = ? WHERE rate_id = ?",
            updates,
        )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise


@bp.route("/admin/pricing", methods=["GET", "POST"])
@role_required("admin")
def pricing():
    conn = get_db()
    try:
        rates = load_rates(conn)
        if request.method == "GET":
            return render_template("admin/pricing.html", rates=rates)

        values = {}
        has_errors = False
        for rate in rates:
            rate["input"] = request.form.get("rate_%d" % rate["rate_id"], "")
            try:
                values[rate["rate_id"]] = parse_price(rate["input"])
            except ValueError as exc:
                rate["error"] = str(exc)
                has_errors = True

        if has_errors:
            flash("Nothing was saved. Fix the prices marked below.", "error")
            return render_template("admin/pricing.html", rates=rates), 400

        updates = [(values[r["rate_id"]], r["rate_id"]) for r in rates
                   if values[r["rate_id"]] != r["price_per_page"]]
        if not updates:
            flash("No changes to save.", "warning")
            return redirect(url_for("admin.pricing"))

        try:
            save_rates(conn, updates)
        except sqlite3.Error:
            flash("The rates could not be saved. Nothing was changed.",
                  "error")
            return redirect(url_for("admin.pricing"))
        flash("Saved %d rate%s." % (len(updates),
                                    "" if len(updates) == 1 else "s"),
              "success")
        return redirect(url_for("admin.pricing"))
    finally:
        conn.close()


def parse_order_filter(text):
    cleaned = text.strip().upper()
    if cleaned.startswith("CP-"):
        cleaned = cleaned[3:]
    if not cleaned.isdigit() or int(cleaned) < 1:
        raise ValueError("Enter an order number such as 12 or CP-000012.")
    return int(cleaned)


@bp.route("/admin/audit-log")
@role_required("admin")
def audit_log():
    raw_filter = request.args.get("order_id", "").strip()
    order_filter = None
    error = None
    if raw_filter:
        try:
            order_filter = parse_order_filter(raw_filter)
        except ValueError as exc:
            error = str(exc)

    entries = []
    truncated = False
    if error is None:
        sql = (
            "SELECT s.log_id, s.order_id, s.old_status, s.new_status, "
            "s.changed_at, u.name AS changed_by_name, "
            "u.role AS changed_by_role, o.original_filename, "
            "c.name AS customer_name "
            "FROM status_logs s "
            "JOIN print_orders o ON o.order_id = s.order_id "
            "JOIN users c ON c.user_id = o.user_id "
            "LEFT JOIN users u ON u.user_id = s.changed_by "
        )
        args = []
        if order_filter is not None:
            sql += "WHERE s.order_id = ? "
            args.append(order_filter)
        sql += "ORDER BY s.changed_at DESC, s.log_id DESC LIMIT ?"
        args.append(LOG_LIMIT + 1)

        conn = get_db()
        try:
            rows = conn.execute(sql, args).fetchall()
        finally:
            conn.close()
        truncated = len(rows) > LOG_LIMIT
        for row in rows[:LOG_LIMIT]:
            entry = dict(row)
            entry["code"] = order_code(entry["order_id"])
            entries.append(entry)

    page = render_template("admin/audit_log.html", entries=entries,
                           raw_filter=raw_filter, error=error,
                           truncated=truncated, limit=LOG_LIMIT)
    return page, (400 if error else 200)
