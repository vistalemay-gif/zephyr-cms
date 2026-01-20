import sqlite3
import os
from datetime import datetime, date
from flask import Flask, g, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------- CONFIG ----------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = "/tmp/data.db" if os.environ.get("RENDER") else os.path.join(APP_DIR, "data.db")

app = Flask(__name__)
app.secret_key = "replace_with_a_random_secret"

# ---------------- MENU PRICES ----------------
MENU_PRICES = {
    "budbod": {"pork": 85, "chicken": 85, "hungarian": 85, "rice": 15, "egg": 15},
    "burger": {"quarter": 80, "half_pound": 155, "jalapeno": 15, "cheese": 15, "bbq_sauce": 15},
    "busog_combo": {"Q1": 115, "H1": 185},
    "fries": {"small": 25, "medium": 35, "large": 45}
}

# ---------------- DATABASE ----------------
def get_db():
    if "_db" not in g:
        g._db = sqlite3.connect(DATABASE, check_same_thread=False)
        g._db.row_factory = sqlite3.Row
    return g._db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("_db", None)
    if db:
        db.close()

def init_db():
    db = get_db()
    c = db.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            display_name TEXT,
            full_name TEXT,
            phone TEXT,
            email TEXT
        )
    """)

    # Customers table
    c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            order_name TEXT,
            amount REAL,
            visit_date TEXT,
            archived INTEGER DEFAULT 0,
            visit_count INTEGER DEFAULT 1,
            category TEXT DEFAULT 'New',
            notes TEXT
        )
    """)

    # Feedback table
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            order_name TEXT,
            rating INTEGER,
            comment TEXT,
            created_at TEXT
        )
    """)

    # Activity logs
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            action TEXT,
            timestamp TEXT
        )
    """)

    # Insert default users if they don't exist
    c.execute("INSERT OR IGNORE INTO users (username,password,role) VALUES (?,?,?)",
              ("admin", generate_password_hash("adminpass"), "admin"))
    c.execute("INSERT OR IGNORE INTO users (username,password,role) VALUES (?,?,?)",
              ("staff", generate_password_hash("staffpass"), "staff"))

    db.commit()

# Initialize DB on first run
with app.app_context():
    init_db()

# ---------------- LOGGING ----------------
def log_action(user, action):
    db = get_db()
    db.execute("INSERT INTO activity_logs (user,action,timestamp) VALUES (?,?,?)",
               (user, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()

# ---------------- ROUTES ----------------
@app.route("/")
def splash():
    return render_template("splash.html")

@app.route("/login", methods=["GET","POST"])
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
        return render_template("login.html", error="Invalid login")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    today = date.today().isoformat()
    db = get_db()
    db.commit()

    # Fetch only active customers once
    customers = db.execute(
        "SELECT * FROM customers WHERE archived=0 ORDER BY visit_date DESC"
    ).fetchall()

    total_count = db.execute(
        "SELECT COUNT(*) FROM customers WHERE archived=0"
    ).fetchone()[0]

    total_earnings = db.execute(
        "SELECT SUM(amount) FROM customers WHERE archived=0"
    ).fetchone()[0] or 0

    today_count = db.execute(
        "SELECT COUNT(*) FROM customers WHERE visit_date=? AND archived=0",
        (today,)
    ).fetchone()[0]

    daily_earnings = db.execute(
        "SELECT SUM(amount) FROM customers WHERE visit_date=? AND archived=0",
        (today,)
    ).fetchone()[0] or 0

    month_start = today[:7] + "-01"
    monthly_earnings = db.execute(
        "SELECT SUM(amount) FROM customers WHERE visit_date>=? AND archived=0",
        (month_start,)
    ).fetchone()[0] or 0

    # Display name
    user_row = db.execute(
        "SELECT display_name FROM users WHERE username=?",
        (session.get("user"),)
    ).fetchone()
    display_name = user_row["display_name"] if user_row else session.get("user")

    return render_template(
        "dashboard.html",
        customers=customers,
        today_count=today_count,
        total_earnings=total_earnings,
        daily_earnings=daily_earnings,
        monthly_earnings=monthly_earnings,
        display_name=display_name
    )

# ---------------- ADD CUSTOMER ----------------
@app.route("/add_customer", methods=["GET"])
def add_customer_page():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("add_customer.html")

@app.route("/add_customer", methods=["POST"])
def add_customer():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()

    name = request.form.get("name")
    visit_date = request.form.get("visit_date")

    order_types = request.form.getlist("order_type[]")
    quantities = request.form.getlist("quantity[]")
    amounts = request.form.getlist("amount[]")

    total_amount = 0
    orders = []

    for i in range(len(order_types)):
        qty = int(quantities[i])
        amt = float(amounts[i])
        total_amount += qty * amt
        orders.append(f"{order_types[i]} x{qty}")

    # COUNT PREVIOUS VISITS (NOT MERGING RECORDS)
    visit_count = db.execute(
        "SELECT COUNT(*) FROM customers WHERE name=?",
        (name,)
    ).fetchone()[0] + 1

    # CATEGORY LOGIC
    category = "Old" if visit_count > 3 else "New"

    # ALWAYS INSERT NEW ROW
    db.execute("""
        INSERT INTO customers
        (name, order_name, amount, visit_date, visit_count, category, archived)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (
        name,
        " | ".join(orders),
        total_amount,
        visit_date,
        visit_count,
        category
    ))

    db.commit()
    log_action(session["user"], f"Added customer {name}")

    return redirect(url_for("dashboard"))

# ---------------- CUSTOMER RECORDS ----------------
@app.route("/customer_records", methods=["GET","POST"])
def customer_records():
    if "user" not in session: return redirect(url_for("login"))
    db = get_db()
    selected_date = request.form.get("date") if request.method=="POST" else None
    records = db.execute("SELECT * FROM customers WHERE visit_date=? ORDER BY visit_date DESC", (selected_date,)).fetchall() if selected_date else []
    return render_template("customer_records.html", records=records, selected_date=selected_date)

# ---------------- FEEDBACK ----------------
@app.route("/feedback", methods=["GET","POST"])
def feedback():
    db = get_db()
    if request.method=="POST":
        db.execute("""INSERT INTO feedback (name,order_name,rating,comment,created_at) VALUES (?,?,?,?,?)""",
                   (request.form["name"], request.form["order"], request.form["rating"], request.form["comment"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
        return "Thank you for your feedback!"
    return render_template("feedback.html")

@app.route("/view_feedback")
def view_feedback():
    db = get_db()
    rows = db.execute("SELECT * FROM feedback ORDER BY created_at DESC").fetchall()
    return render_template("view_feedback.html", feedbacks=rows)

# ---------------- PROFILE ----------------
@app.route("/profile", methods=["GET","POST"])
def profile():
    if "user" not in session: return redirect(url_for("login"))
    db = get_db()
    if request.method=="POST":
        db.execute("UPDATE users SET full_name=?, phone=?, email=? WHERE username=?",
                   (request.form.get("full_name"), request.form.get("phone"), request.form.get("email"), session["user"]))
        db.commit()
        flash("Profile updated successfully!", "success")
    user = db.execute("SELECT username,role,full_name,phone,email FROM users WHERE username=?",(session["user"],)).fetchone()
    return render_template("profile.html", user=user)

# ---------------- CHANGE PASSWORD ----------------
@app.route("/change_password", methods=["POST"])
def change_password():
    if "user" not in session: return redirect(url_for("login"))
    db = get_db()
    current = request.form.get("current_password")
    new = request.form.get("new_password")
    user = db.execute("SELECT password FROM users WHERE username=?",(session["user"],)).fetchone()
    if not check_password_hash(user["password"], current):
        flash("Current password is incorrect", "danger")
        return redirect(url_for("profile"))
    db.execute("UPDATE users SET password=? WHERE username=?",(generate_password_hash(new), session["user"]))
    db.commit()
    flash("Password changed successfully!", "success")
    return redirect(url_for("profile"))

# ---------------- ARCHIVE / DELETE ----------------
@app.route("/archive_customer/<int:customer_id>", methods=["POST"])
def archive_customer(customer_id):
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    db.execute(
        "UPDATE customers SET archived=1 WHERE id=?",
        (customer_id,)
    )
    db.commit()

    log_action(session["user"], f"Archived customer ID {customer_id}")
    return redirect(url_for("dashboard"))

@app.route("/delete_customer/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    db.execute(
        "DELETE FROM customers WHERE id=?",
        (customer_id,)
    )
    db.commit()

    log_action(session["user"], f"Deleted customer ID {customer_id}")
    return redirect(url_for("dashboard"))

# ---------------- ADMIN ----------------
@app.route("/archived_customers")
def archived_customers():
    if "user" not in session or session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    db = get_db()
    customers = db.execute("SELECT * FROM customers WHERE archived=1").fetchall()
    return render_template("archived_customers.html", customers=customers)

@app.route("/activity_logs")
def activity_logs():
    if "user" not in session or session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    db = get_db()
    logs = db.execute("SELECT * FROM activity_logs ORDER BY timestamp DESC").fetchall()
    return render_template("activity_logs.html", logs=logs)

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/manifest.json")
def manifest():
    return app.send_from_directory("static", "manifest.json")

# ---------------- RUN ----------------
if __name__=="__main__":
    app.run(debug=True)
