import os
import sqlite3

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)

from db import get_db
from routes.auth import role_required
from services import files, orders, pricing

bp = Blueprint("student", __name__)

PAPER_SIZES = ("A4", "Letter", "Legal")
COLOR_MODES = (("bw", "Black & white"), ("color", "Color"))
STUDENT_ROLES = ("student", "faculty")


def order_code(order_id):
    return "CP-%06d" % order_id


def upload_dir():
    folder = current_app.config.get("UPLOAD_DIR")
    if not folder:
        folder = os.path.join(current_app.root_path, "uploads")
    os.makedirs(folder, exist_ok=True)
    return folder


def whole_number(value, label):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("%s must be a whole number." % label)
    if number < 1:
        raise ValueError("%s must be at least 1." % label)
    return number


def choice(value, allowed, label):
    if value not in allowed:
        raise ValueError("Pick a valid %s." % label)
    return value


def clean_row(row):
    data = dict(row)
    data["code"] = order_code(data["order_id"])
    return data


def remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def render_form(form, error=None, status=200):
    page = render_template("student/new_order.html",
                           form=form,
                           error=error,
                           paper_sizes=PAPER_SIZES,
                           color_modes=COLOR_MODES)
    return page, status


@bp.route("/api/price", methods=["POST"])
@role_required(*STUDENT_ROLES)
def api_price():
    data = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        paper_size = choice(data.get("paper_size"), PAPER_SIZES, "paper size")
        color_mode = choice(data.get("color_mode"),
                            [c[0] for c in COLOR_MODES], "color mode")
        page_count = whole_number(data.get("page_count"), "Page count")
        copies = whole_number(data.get("copies"), "Copies")
        total = pricing.calculate_total(conn, paper_size, color_mode,
                                        page_count, copies)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
    return jsonify({"total": total, "display": "\u20b1{:,.2f}".format(total)})


@bp.route("/orders/new", methods=["GET", "POST"])
@role_required(*STUDENT_ROLES)
def new_order():
    if request.method == "GET":
        return render_form({"paper_size": "A4", "color_mode": "bw",
                            "copies": "1", "page_count": ""})

    form = {
        "paper_size": request.form.get("paper_size", ""),
        "color_mode": request.form.get("color_mode", ""),
        "copies": request.form.get("copies", ""),
        "page_count": request.form.get("page_count", "").strip(),
    }
    upload = request.files.get("file")
    file_info = None
    conn = None
    try:
        if upload is None or not upload.filename:
            raise ValueError("Choose a file to upload.")
        paper_size = choice(form["paper_size"], PAPER_SIZES, "paper size")
        color_mode = choice(form["color_mode"],
                            [c[0] for c in COLOR_MODES], "color mode")
        copies = whole_number(form["copies"], "Copies")
        typed_pages = None
        if form["page_count"]:
            typed_pages = whole_number(form["page_count"], "Page count")

        file_info = files.validate_and_save(upload, upload_dir())
        page_count = file_info["detected_page_count"] or typed_pages
        if page_count is None:
            raise ValueError("Enter the number of pages for this file.")

        conn = get_db()
        order_id = orders.create_order(conn, session["user_id"], file_info,
                                       paper_size, color_mode, page_count,
                                       copies)
    except ValueError as exc:
        if file_info:
            remove_quietly(file_info["stored_path"])
        return render_form(form, str(exc), 400)
    except sqlite3.Error:
        if file_info:
            remove_quietly(file_info["stored_path"])
        return render_form(form, "The order could not be saved. Try again.",
                           500)
    finally:
        if conn is not None:
            conn.close()

    flash("Order %s submitted." % order_code(order_id), "success")
    return redirect(url_for("student.order_detail", order_id=order_id))


@bp.route("/orders")
@role_required(*STUDENT_ROLES)
def my_orders():
    conn = get_db()
    try:
        rows = orders.list_orders_for_user(conn, session["user_id"])
        items = [clean_row(r) for r in rows]
    finally:
        conn.close()
    return render_template("student/my_orders.html", orders=items)


@bp.route("/orders/<int:order_id>")
@role_required(*STUDENT_ROLES)
def order_detail(order_id):
    conn = get_db()
    try:
        row = orders.get_order(conn, order_id)
        if row is None or row["user_id"] != session["user_id"]:
            abort(404)
        history = conn.execute(
            "SELECT s.old_status, s.new_status, s.changed_at, u.name AS changed_by_name "
            "FROM status_logs s JOIN users u ON u.user_id = s.changed_by "
            "WHERE s.order_id = ? ORDER BY s.log_id",
            (order_id,),
        ).fetchall()
        payment = conn.execute(
            "SELECT p.amount, p.method, p.paid_at FROM payments p "
            "WHERE p.order_id = ?",
            (order_id,),
        ).fetchone()
        order = clean_row(row)
        history = [dict(h) for h in history]
        payment = dict(payment) if payment else None
    finally:
        conn.close()
    return render_template("student/order_detail.html", order=order,
                           history=history, payment=payment)
