import sqlite3
import os
from datetime import datetime, date
from flask import Flask, g, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(APP_DIR, "data.db")

app = Flask(__name__)
app.secret_key = "replace_with_a_random_secret"

# ---------------- MENU PRICES ----------------
MENU_PRICES = {
    "budbod": {
        "pork": 85,
        "chicken": 85,
        "hungarian": 85,
        "rice": 15,
        "egg": 15
    },
    "burger": {
        "quarter": 80,
        "half_pound": 155,
        "jalapeno": 15,
        "cheese": 15,
        "bbq_sauce": 15
    },
    "busog_combo": {
        "Q1": 115,
        "H1": 185
    },
    "fries": {
        "small": 25,
        "medium": 35,
        "large": 45
    }
}

# ---------------- DATABASE ----------------
def get_db():
    if "_db" not in g:
        g._db = sqlite3.connect(
            DATABASE,
            check_same_thread=False
        )
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
            name TEXT,
            order_name TEXT,
            amount REAL,
            visit_date TEXT,
            archived INTEGER DEFAULT 0
        )
    """)

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

    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            action TEXT,
            timestamp TEXT
        )
    """)

    c.execute(
        "INSERT OR IGNORE INTO users VALUES (NULL,?,?,?)",
        ("admin", generate_password_hash("adminpass"), "admin")
    )

    # Add column display_name if not exists
    c.execute("ALTER TABLE users ADD COLUMN display_name TEXT")  # Only if you don't already have it

    # Existing tables...
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            display_name TEXT
        )
    """)
    db.commit()

if not os.path.exists(DATABASE):
    with app.app_context():
        init_db()
    
with app.app_context():
    db = get_db()
    # Add full_name, phone, email columns if they don't exist
    try:
        db.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        db.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        db.execute("ALTER TABLE users ADD COLUMN email TEXT")
        db.commit()
        print("Added missing profile columns to users table")
    except sqlite3.OperationalError:
        # Columns already exist
        print("Profile columns already exist")

with app.app_context():
    db = get_db()
    try:
        db.execute("ALTER TABLE customers ADD COLUMN visit_count INTEGER DEFAULT 1")
        db.execute("ALTER TABLE customers ADD COLUMN category TEXT DEFAULT 'New'")
        db.execute("ALTER TABLE customers ADD COLUMN notes TEXT")
        db.commit()
        print("Added missing columns to customers table")
    except sqlite3.OperationalError:
        print("Customers table columns already exist")

# ---------------- LOGGING ----------------
def log_action(user, action):
    get_db().execute(
        "INSERT INTO activity_logs (user, action, timestamp) VALUES (?,?,?)",
        (user, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    get_db().commit()

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

        return render_template("login.html", error="Invalid login")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    from datetime import date

    today = date.today().isoformat()
    db = get_db()

# Archive all previous records automatically
    db.execute("UPDATE customers SET archived=1 WHERE visit_date < ?", (today,))
    db.commit()

    # Customers
    customers = db.execute(
    "SELECT * FROM customers WHERE archived=0 ORDER BY visit_date DESC"
).fetchall()

    customers = db.execute(
    "SELECT * FROM customers ORDER BY visit_date DESC"
).fetchall()

    total_count = db.execute(
        "SELECT COUNT(*) FROM customers WHERE archived=0"
    ).fetchone()[0]

    total_earnings = db.execute(
        "SELECT SUM(amount) FROM customers WHERE archived=0"
    ).fetchone()[0] or 0

    # Get display name for profile
    today_count = db.execute(
        "SELECT COUNT(*) FROM customers WHERE visit_date=? AND archived=0",
        (today,)
    ).fetchone()[0]

    # Display name (unchanged)
    user_row = db.execute(
        "SELECT display_name FROM users WHERE username=?",
        (session.get("user"),)
    ).fetchone()
    display_name = user_row["display_name"] if user_row else session.get("user")
    
# Daily earnings
    daily_earnings = db.execute(
    "SELECT SUM(amount) FROM customers WHERE visit_date=? AND archived=0",
    (today,)
).fetchone()[0] or 0

# Monthly earnings
    month_start = today[:7] + "-01"
    monthly_earnings = db.execute(
    "SELECT SUM(amount) FROM customers WHERE visit_date>=? AND archived=0",
    (month_start,)
).fetchone()[0] or 0


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
@app.route("/add-customer")
def add_customer_page():
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
        otype = order_types[i]
        qty = int(quantities[i])
        amt = float(amounts[i])

        line_total = qty * amt
        total_amount += line_total
        orders.append(f"{otype} x{qty}")

    existing = db.execute(
    "SELECT id, visit_count FROM customers WHERE name=? AND archived=0",
    (name,)
).fetchone()

    if existing:db.execute("""
        UPDATE customers
        SET visit_count = visit_count + 1,
            amount = amount + ?,
            visit_date = ?
        WHERE id=?
    """, (total_amount, visit_date, existing["id"]))
    else:
     db.execute("""
        INSERT INTO customers
        (name, order_name, amount, visit_date, visit_count, category)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        name,
        " | ".join(orders),
        total_amount,
        visit_date,
        1,
        "New"
    ))

# AUTO CATEGORY
    db.execute("""
    UPDATE customers
    SET category = CASE
        WHEN visit_count >= 10 THEN 'VIP'
        WHEN visit_count >= 5 THEN 'Regular'
        ELSE 'New'
    END
    """)
    db.commit()

    log_action(session["user"], "Added customer")
    return redirect(url_for("dashboard"))

# ---------------- FEEDBACK ----------------
@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        get_db().execute(
            "INSERT INTO feedback (name, order_name, rating, comment, created_at) VALUES (?,?,?,?,?)",
            (
                request.form["name"],
                request.form["order"],
                request.form["rating"],
                request.form["comment"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        get_db().commit()
        return "Thank you for your feedback!"

    return render_template("feedback.html")

@app.route("/view_feedback")
def view_feedback():
    rows = get_db().execute(
        "SELECT * FROM feedback ORDER BY created_at DESC"
    ).fetchall()
    return render_template("view_feedback.html", feedbacks=rows)

# ---------------- ADMIN ----------------
# Archived Customers (Admin only)
@app.route("/archived_customers")
def archived_customers():
    if "user" not in session or session.get("role") != "admin":
        return redirect(url_for("dashboard"))

    db = get_db()
    # Only fetch archived customers
    customers = db.execute("SELECT * FROM customers WHERE archived=1").fetchall()
    return render_template("archived_customers.html", customers=customers)

# Activity Logs (Admin only)
@app.route("/activity_logs")
def activity_logs():
    if "user" not in session or session.get("role") != "admin":
        return redirect(url_for("dashboard"))
    logs = get_db().execute("SELECT * FROM activity_logs ORDER BY timestamp DESC").fetchall()
    return render_template("activity_logs.html", logs=logs)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()

    if request.method == "POST":
        full_name = request.form.get("full_name")
        phone = request.form.get("phone")
        email = request.form.get("email")

        db.execute("""
            UPDATE users 
            SET full_name=?, phone=?, email=?
            WHERE username=?
        """, (full_name, phone, email, session["user"]))
        db.commit()

        flash("Profile updated successfully!", "success")

    user = db.execute("""
        SELECT username, role, full_name, phone, email
        FROM users WHERE username=?
    """, (session["user"],)).fetchone()

    return render_template("profile.html", user=user)

@app.route("/change_password", methods=["POST"])
def change_password():
    if "user" not in session:
        return redirect(url_for("login"))

    current = request.form.get("current_password")
    new = request.form.get("new_password")

    db = get_db()
    user = db.execute(
        "SELECT password FROM users WHERE username=?",
        (session["user"],)
    ).fetchone()

    if not check_password_hash(user["password"], current):
        flash("Current password is incorrect", "danger")
        return redirect(url_for("profile"))

    db.execute(
        "UPDATE users SET password=? WHERE username=?",
        (generate_password_hash(new), session["user"])
    )
    db.commit()

    flash("Password changed successfully!", "success")
    return redirect(url_for("profile"))

@app.route("/archive_customer/<int:customer_id>", methods=["POST"])
def archive_customer(customer_id):
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    db.execute("UPDATE customers SET archived=1 WHERE id=?", (customer_id,))
    db.commit()

    log_action(session["user"], f"Archived customer ID {customer_id}")
    return redirect(url_for("dashboard"))

@app.route("/delete_customer/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    db.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    db.commit()

    log_action(session["user"], f"Deleted customer ID {customer_id}")
    return redirect(url_for("dashboard"))

@app.route("/customer_records", methods=["GET", "POST"])
def customer_records():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    selected_date = None
    records = []

    if request.method == "POST":
        selected_date = request.form.get("date")
        records = db.execute(
            "SELECT * FROM customers WHERE visit_date=? ORDER BY visit_date DESC",
            (selected_date,)
        ).fetchall()

    return render_template("customer_records.html", records=records, selected_date=selected_date)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/manifest.json")
def manifest():
    return app.send_from_directory("static", "manifest.json")

if __name__ == "__main__":
    app.run(debug=True)
