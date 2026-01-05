import sqlite3
import os
from datetime import date, datetime
from flask import Flask, g, render_template, request, redirect, url_for, session, Response
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(APP_DIR, "data.db")

app = Flask(__name__)
app.secret_key = "replace_with_a_random_secret"

# ---------------- DB CONNECTION ----------------
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

# ---------------- DB INIT ----------------
def init_db():
    db = get_db()
    c = db.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            order_name TEXT,
            amount REAL,
            visit_date TEXT,
            archived INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            action TEXT,
            timestamp TEXT
        )
    """)

    c.execute("INSERT OR IGNORE INTO users VALUES (NULL, ?, ?, ?)",
              ("admin", generate_password_hash("adminpass"), "admin"))
    c.execute("INSERT OR IGNORE INTO users VALUES (NULL, ?, ?, ?)",
              ("staff", generate_password_hash("staffpass"), "staff"))

    db.commit()

if not os.path.exists(DATABASE):
    with app.app_context():
        init_db()

# ---------------- LOG ACTION ----------------
def log_action(user, action):
    if user:
        db = get_db()
        db.execute(
            "INSERT INTO activity_logs (user, action, timestamp) VALUES (?, ?, ?)",
            (user, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        db.commit()

# ---------------- ROUTES ----------------
@app.route("/")
def splash():
    return render_template("splash.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_db().execute(
            "SELECT * FROM users WHERE username=?",
            (request.form["username"],)
        ).fetchone()

        if user and check_password_hash(user["password"], request.form["password"]):
            session["user"] = user["username"]
            session["role"] = user["role"]
            log_action(user["username"], "Logged in")
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    selected_date = request.args.get("date")
    today = date.today().isoformat()

    if selected_date:
        customers = db.execute("""
            SELECT id, name, order_name AS "order", amount, visit_date
            FROM customers
            WHERE visit_date=? AND archived=0
        """, (selected_date,)).fetchall()
    else:
        customers = db.execute("""
            SELECT id, name, order_name AS "order", amount, visit_date
            FROM customers
            WHERE archived=0
        """).fetchall()

    daily_count = db.execute(
        "SELECT COUNT(*) FROM customers WHERE visit_date=? AND archived=0",
        (today,)
    ).fetchone()[0]

    total_count = db.execute(
        "SELECT COUNT(*) FROM customers WHERE archived=0"
    ).fetchone()[0]

    monthly_count = db.execute("""
        SELECT COUNT(*) FROM customers
        WHERE strftime('%Y-%m', visit_date)=strftime('%Y-%m','now')
        AND archived=0
    """).fetchone()[0]

    return render_template(
        "dashboard.html",
        customers=customers,
        daily_count=daily_count,
        total_count=total_count,
        monthly_count=monthly_count,
        selected_date=selected_date
    )

@app.route("/add_customer", methods=["POST"])
def add_customer():
    db = get_db()
    db.execute("""
        INSERT INTO customers (name, order_name, amount, visit_date)
        VALUES (?, ?, ?, ?)
    """, (
        request.form["name"],
        request.form["order"],
        request.form["amount"],
        request.form["visit_date"]
    ))
    db.commit()
    log_action(session["user"], "Added customer")
    return redirect(url_for("dashboard"))

@app.route("/archive_customer/<int:id>")
def archive_customer(id):
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    get_db().execute("UPDATE customers SET archived=1 WHERE id=?", (id,))
    get_db().commit()
    return redirect(url_for("dashboard"))

@app.route("/export_csv")
def export_csv():
    if session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    customers = get_db().execute("""
        SELECT name, order_name, amount, visit_date
        FROM customers WHERE archived=0
    """).fetchall()

    def generate():
        yield "Name,Order,Amount,Date\n"
        for c in customers:
            yield f"{c['name']},{c['order_name']},{c['amount']},{c['visit_date']}\n"

    return Response(generate(), mimetype="text/csv")

@app.route("/logout")
def logout():
    log_action(session.get("user"), "Logged out")
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
