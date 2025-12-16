import sqlite3
from flask import Flask, g, render_template, request, redirect, url_for, session
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# ---------------------- CONFIG ----------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(APP_DIR, "data.db")

app = Flask(__name__)
app.secret_key = "replace_with_a_random_secret"

# ---------------------- DATABASE CONNECTION ----------------------
def get_db():
    if "_database" not in g:
        g._database = sqlite3.connect(DATABASE)
        g._database.row_factory = sqlite3.Row
    return g._database

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop("_database", None)
    if db is not None:
        db.close()

# ---------------------- DATABASE INITIALIZATION ----------------------
def init_db():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            date TEXT
        )
    """)

    # Default users with hashed passwords
    cursor.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)",
                   ("admin", generate_password_hash("adminpass")))
    cursor.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)",
                   ("client", generate_password_hash("clientpass")))

    db.commit()

# Initialize DB if it doesn't exist
if not os.path.exists(DATABASE):
    with app.app_context():
        init_db()

# ---------------------- ROUTES ----------------------
@app.route("/")
def splash():
    return render_template("splash.html")  # simplified name

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user"] = username
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    date_filter = request.args.get("date")
    if date_filter:
        customers = db.execute("SELECT * FROM customers WHERE date=?", (date_filter,)).fetchall()
    else:
        customers = db.execute("SELECT * FROM customers").fetchall()

    return render_template("dashboard.html", customers=customers, datetime=datetime)

@app.route("/add_customer", methods=["POST"])
def add_customer():
    name = request.form.get("name")
    email = request.form.get("email")
    phone = request.form.get("phone")
    date = request.form.get("date") or datetime.today().strftime("%Y-%m-%d")

    db = get_db()
    db.execute(
        "INSERT INTO customers (name, email, phone, date) VALUES (?, ?, ?, ?)",
        (name, email, phone, date)
    )
    db.commit()
    return redirect(url_for("dashboard"))

@app.route("/delete_customer/<int:id>")
def delete_customer(id):
    db = get_db()
    db.execute("DELETE FROM customers WHERE id=?", (id,))
    db.commit()
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# ---------------------- PWA SUPPORT ----------------------
@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/service-worker.js")
def service_worker():
    return app.send_static_file("service-worker.js")

# ---------------------- RUN ----------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
