from functools import wraps

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, session)

import db

bp = Blueprint("auth", __name__)

PSU_DOMAIN = "psu.palawan.edu.ph"

ROLE_HOME = {
    "student": "/orders",
    "faculty": "/orders",
    "staff": "/staff/queue",
    "admin": "/staff/queue",
}


def _is_logged_in():
    return "user_id" in session and session.get("role") in ROLE_HOME


def _is_psu_email(email):
    local, _, domain = email.rpartition("@")
    return bool(local) and domain == PSU_DOMAIN


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def _deny_anonymous():
    if request.path.startswith("/api/"):
        return jsonify(error="Login required"), 401
    flash("Please log in first.", "warning")
    if request.method == "GET":
        return redirect("/login?next=" + request.full_path.rstrip("?"))
    return redirect("/login")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _is_logged_in():
            return _deny_anonymous()
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not _is_logged_in():
                return _deny_anonymous()
            if session["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _render_login(status=200):
    users = db.get_db().execute(
        "SELECT user_id, name, email, role FROM users ORDER BY user_id"
    ).fetchall()
    page = render_template("login.html", users=users, next_url=request.values.get("next", ""))
    return page, status


@bp.route("/")
def index():
    if not _is_logged_in():
        return redirect("/login")
    return redirect(ROLE_HOME[session["role"]])


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if _is_logged_in():
            return redirect("/")
        return _render_login()

    email = request.form.get("email", "").strip().lower()
    if not _is_psu_email(email):
        flash("Only @psu.palawan.edu.ph accounts can log in.", "error")
        return _render_login(400)

    user = db.get_db().execute(
        "SELECT user_id, name, role FROM users WHERE lower(email) = ?", (email,)
    ).fetchone()
    if user is None:
        flash("No account found for that email.", "error")
        return _render_login(400)

    session.clear()
    session["user_id"] = user["user_id"]
    session["role"] = user["role"]
    session["user_name"] = user["name"]
    flash(f"Welcome, {user['name']}.", "success")
    return redirect(_safe_next(request.form.get("next")) or ROLE_HOME[user["role"]])


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("/login")
