"""Flask dashboard for the RFID attendance project."""
from __future__ import annotations

import csv
import hmac
import os
import secrets
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
secret_key = os.getenv("FLASK_SECRET_KEY")
if not secret_key:
    # Safe for local development only. Set FLASK_SECRET_KEY for persistent sessions.
    secret_key = secrets.token_hex(32)
app.config.update(
    SECRET_KEY=secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)
app.permanent_session_lifetime = timedelta(minutes=30)
CSV_FILE = Path(os.getenv("ATTENDANCE_CSV", str(BASE_DIR / "attendance.csv")))
HEADERS = ["Timestamp", "Name", "RegNo", "UID", "Status", "Duration"]


def ensure_csv() -> None:
    """Create an empty attendance file only when one does not already exist."""
    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_FILE.exists():
        with CSV_FILE.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(HEADERS)


def login_required() -> bool:
    return bool(session.get("user"))


def valid_csrf() -> bool:
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))


@app.context_processor
def inject_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf_token"]}


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not valid_csrf():
            abort(400, "Invalid or missing CSRF token. Refresh the page and try again.")
        expected_username = os.getenv("DASHBOARD_USERNAME", "")
        expected_password = os.getenv("DASHBOARD_PASSWORD", "")
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if not expected_username or not expected_password:
            return render_template("login.html", error="Dashboard credentials are not configured. Set DASHBOARD_USERNAME and DASHBOARD_PASSWORD in your local .env file."), 503
        if hmac.compare_digest(username, expected_username) and hmac.compare_digest(password, expected_password):
            session.clear()
            session.permanent = True
            session["user"] = username
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("welcome"))
        return render_template("login.html", error="Invalid username or password."), 401
    return render_template("login.html")


@app.route("/welcome")
def welcome():
    if not login_required():
        return redirect(url_for("login"))
    return render_template("welcome.html")


@app.route("/logout", methods=["POST"])
def logout():
    if not login_required():
        return redirect(url_for("login"))
    if not valid_csrf():
        abort(400, "Invalid or missing CSRF token.")
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    if not login_required():
        return redirect(url_for("login"))
    ensure_csv()
    return render_template("index.html")


@app.route("/clear", methods=["POST"])
def clear():
    if not login_required():
        return redirect(url_for("login"))
    if not valid_csrf():
        abort(400, "Invalid or missing CSRF token.")
    # Keep the current file, but reset its contents only after an authenticated POST.
    with CSV_FILE.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(HEADERS)
    return redirect(url_for("index"))


@app.route("/data")
def data():
    if not login_required():
        return jsonify({"error": "Authentication required"}), 401
    ensure_csv()
    rows = []
    with CSV_FILE.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({key: (row.get(key) or "") for key in HEADERS})
    current_status = {}
    for row in rows:
        if row["UID"]:
            current_status[row["UID"]] = row["Status"]
    present = sum(status == "Entered" for status in current_status.values())
    exited = sum(status == "Exited" for status in current_status.values())
    return jsonify({"data": rows[::-1], "total": len(rows), "present": present, "exited": exited})


ensure_csv()

if __name__ == "__main__":
    # Debug mode is intentionally disabled by default.
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=False)
