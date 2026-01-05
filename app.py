import sqlite3
import os
import csv
from datetime import date, datetime
from flask import Flask, g, render_template, request, redirect, url_for, session, Response
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------- CONFIG ----------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(APP_DIR, "data.db")

app = Flask(__name__)
app.secret_key = "replace_with_a_random_secret"  # Replace with a secure random key

# ---------------------- DATABASE CONNECTION ----------------------
def get_db():
    if "_database" not in g:
        g._database = sqlite3.connect(DATABASE)
        g._database.row_factory = sqlite3.Row
    return g._database

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop("_database", None)
    if db:
        db.close()

# ---------------------- DATABASE INITIALIZATION ----------------------
def init_db():
    db = get_db()
    cursor = db.cursor()

    # USERS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    # CUSTOMERS TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            visit_date TEXT,
            archived INTEGER DEFAULT 0
        )
    """)

    # ACTIVITY LOG TABLE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            action TEXT,
            timestamp TEXT
        )
    """)

    # DEFAULT USERS
    cursor.execute(
        "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
        ("admin", generate_password_hash("adminpass"), "admin")
    )
    cursor.execute(
        "INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
        ("staff", generate_password_hash("staffpass"), "staff")
    )

    db.commit()

# Initialize DB only if it doesn't exist
if not os.path.exists(DATABASE):
    with app.app_context():
        init_db()

# ---------------------- ACTIVITY LOGGER ----------------------
def log_action(user, action):
    if user:  # Avoid logging None users
        db = get_db()
        db.execute("""
            INSERT INTO activity_logs (user, action, timestamp)
            VALUES (?, ?, ?)
        """, (user, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()

# ---------------------- ROUTES ----------------------
@app.route("/")
def splash():
    return render_template("splash.html")

# ---------------------- LOGIN ----------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            session["role"] = user["role"]

            log_action(user["username"], "Logged in")
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")

# ---------------------- DASHBOARD ----------------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    selected_date = request.args.get("date")
    today = date.today().isoformat()
    db = get_db()

    if selected_date:
        customers = db.execute("""
            SELECT * FROM customers
            WHERE visit_date = ? AND archived = 0
        """, (selected_date,)).fetchall()
    else:
        customers = db.execute("SELECT * FROM customers WHERE archived = 0").fetchall()

    daily_count = db.execute(
        "SELECT COUNT(*) FROM customers WHERE visit_date = ? AND archived = 0", (today,)
    ).fetchone()[0]

    total_count = db.execute("SELECT COUNT(*) FROM customers WHERE archived = 0").fetchone()[0]

    monthly_count = db.execute("""
        SELECT COUNT(*) FROM customers
        WHERE strftime('%Y-%m', visit_date) = strftime('%Y-%m', 'now')
          AND archived = 0
    """).fetchone()[0]

    return render_template(
        "dashboard.html",
        customers=customers,
        daily_count=daily_count,
        total_count=total_count,
        monthly_count=monthly_count,
        selected_date=selected_date
    )

# ---------------------- ADD CUSTOMER ----------------------
@app.route("/add_customer", methods=["POST"])
def add_customer():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    db.execute("""
        INSERT INTO customers (name, email, phone, visit_date)
        VALUES (?, ?, ?, ?)
    """, (
        request.form.get("name"),
        request.form.get("email"),
        request.form.get("phone"),
        request.form.get("visit_date")
    ))
    db.commit()
    log_action(session["user"], "Added a customer")
    return redirect(url_for("dashboard"))

# ---------------------- ARCHIVE & RESTORE ----------------------
@app.route("/archive_customer/<int:id>")
def archive_customer(id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    db = get_db()
    db.execute("UPDATE customers SET archived = 1 WHERE id = ?", (id,))
    db.commit()
    log_action(session["user"], f"Archived customer {id}")
    return redirect(url_for("dashboard"))

@app.route("/restore_customer/<int:id>")
def restore_customer(id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    db = get_db()
    db.execute("UPDATE customers SET archived = 0 WHERE id = ?", (id,))
    db.commit()
    log_action(session["user"], f"Restored customer {id}")
    return redirect(url_for("archived_customers"))

@app.route("/archived_customers")
def archived_customers():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    db = get_db()
    customers = db.execute("SELECT * FROM customers WHERE archived = 1").fetchall()
    return render_template("archived_customers.html", customers=customers)

# ---------------------- ACTIVITY LOGS ----------------------
@app.route("/activity_logs")
def activity_logs():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    db = get_db()
    logs = db.execute("SELECT * FROM activity_logs ORDER BY timestamp DESC").fetchall()
    return render_template("activity_logs.html", logs=logs)

# ---------------------- EXPORT CSV ----------------------
@app.route("/export_csv")
def export_csv():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    selected_date = request.args.get("date")
    db = get_db()

    if selected_date:
        customers = db.execute("SELECT * FROM customers WHERE visit_date = ? AND archived = 0", (selected_date,)).fetchall()
    else:
        customers = db.execute("SELECT * FROM customers WHERE archived = 0").fetchall()

    def generate():
        yield "ID,Name,Email,Phone,Visit Date\n"
        for c in customers:
            yield f"{c['id']},{c['name']},{c['email']},{c['phone']},{c['visit_date']}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=customers.csv"}
    )

# ---------------------- LOGOUT ----------------------
@app.route("/logout")
def logout():
    log_action(session.get("user"), "Logged out")
    session.clear()
    return redirect(url_for("login"))

# ---------------------- PWA FILES ----------------------
@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/service-worker.js")
def service_worker():
    return app.send_static_file("service-worker.js")

# ---------------------- RUN ----------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
