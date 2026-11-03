"""ONLINE SERVICE HUB - deployable Flask website.

Customer accounts: Full Name + WhatsApp Number ONLY (no email, no password).
Orders are NOT complete without payment: checkout shows manual JazzCash
details and requires a transaction ID. An order appears in the Admin
Dashboard immediately, and the customer gets an in-account confirmation.
Payment is verified manually by the admin - there is NO real payment
gateway and NO real email sending in this app. See README.md.
"""
import hashlib
import html
import os
import re
import sqlite3
from datetime import datetime

from flask import Flask, g, redirect, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("OSH_DB", os.path.join(BASE_DIR, "data.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("OSH_SECRET", "change-me-in-production")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

# ---------------------------------------------------------------- helpers
def esc(v):
    return html.escape("" if v is None else str(v))

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc=None):
    d = g.pop("db", None)
    if d is not None:
        d.close()

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, whatsapp TEXT NOT NULL UNIQUE, created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        price REAL NOT NULL DEFAULT 0, stock TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, item_id INTEGER NOT NULL, qty INTEGER NOT NULL DEFAULT 1,
        total REAL NOT NULL, payment_method TEXT NOT NULL DEFAULT 'JazzCash',
        transaction_id TEXT NOT NULL, payment_status TEXT NOT NULL DEFAULT 'pending',
        order_status TEXT NOT NULL DEFAULT 'Placed',
        created TEXT NOT NULL,
        full_name TEXT NOT NULL DEFAULT '', delivery_address TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT '', state_province TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL DEFAULT '', postal_code TEXT NOT NULL DEFAULT '',
        mobile_number TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, item_id INTEGER NOT NULL,
        rating INTEGER NOT NULL, comment TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending', created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL, message TEXT NOT NULL, created TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    # Order details (English labels) - required for every order, product or service.
    # Fresh DBs get the columns in the CREATE TABLE above; existing DBs are
    # migrated in place below so old orders keep working.
    existing_cols = [r[1] for r in con.execute("PRAGMA table_info(orders)").fetchall()]
    for col in ("full_name", "delivery_address", "country", "state_province",
                "city", "postal_code", "mobile_number"):
        if col not in existing_cols:
            con.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    defaults = {
        "support_name": "Hammad",
        "support_number": "03704984676",
        "jazzcash_number": "03297972918",
        "jazzcash_name": "Parveen Khalid",
        "about_text": "ONLINE SERVICE HUB - ALL ONLINE SERVICES IN ONE PLACE. Since 2025, we bring digital services and physical products together in one place, with simple ordering, clear pricing and WhatsApp support.",
        "admin_pin_hash": hashlib.sha256(b"admin123").hexdigest(),
    }
    for k, v in defaults.items():
        con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
    con.commit()
    con.close()

def setting(key):
    row = db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""

def set_setting(key, value):
    db().execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    db().commit()

def wa_link():
    digits = re.sub(r"\D", "", setting("support_number"))
    if digits.startswith("0"):
        digits = "92" + digits[1:]
    return "https://wa.me/" + digits

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def notify(user_id, message):
    db().execute("INSERT INTO notifications(user_id, message, created) VALUES(?, ?, ?)",
                 (user_id, message, now()))
    db().commit()

def money(v):
    try:
        return f"Rs {float(v):,.0f}"
    except Exception:
        return f"Rs {v}"

def fmt_item_type(t):
    return "Digital Service" if t == "digital" else "Physical Product"

def order_field(order, key):
    """Safe read for order-detail columns (old rows may predate a column)."""
    try:
        return order[key] or ""
    except Exception:
        return ""

ORDER_DETAIL_FIELDS = [
    ("full_name", "Full Name"),
    ("delivery_address", "Full Delivery Address"),
    ("country", "Country"),
    ("state_province", "State / Province"),
    ("city", "City"),
    ("postal_code", "Postal / Zip Code"),
    ("mobile_number", "Mobile Number"),
]

def order_details_html(order):
    rows = "".join(
        f"<p>{label}: {esc(order_field(order, key))}</p>"
        for key, label in ORDER_DETAIL_FIELDS)
    return f"<h2>Order Details</h2>{rows}"

# ---------------------------------------------------------------- page shell
def page(title, body, user=None):
    u = user if user is not None else current_user()
    is_admin = bool(session.get("admin"))
    nav_user = ""
    if u:
        nav_user = (f'<a href="/dashboard">Dashboard ({esc(u["name"])})</a> '
                    f'<a href="/logout">Logout</a>')
    else:
        nav_user = '<a href="/login">Login</a> <a href="/register">Register</a>'
    admin_link = '<a href="/admin">Admin</a>' if is_admin else '<a href="/admin/login">Admin</a>'
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} - ONLINE SERVICE HUB</title>
<link rel="stylesheet" href="/static/style.css"></head><body>
<header><div class="wrap head">
<a class="brand" href="/"><img src="/static/logo.jpg" alt="ONLINE SERVICE HUB logo">
<span><b>ONLINE SERVICE HUB</b><small>ALL ONLINE SERVICES IN ONE PLACE &middot; SINCE 2025</small></span></a>
<nav><a href="/">Home</a><a href="/services">Services &amp; Products</a><a href="/about">About</a>
<a href="/contact">Contact</a>{nav_user}{admin_link}</nav></div></header>
<main class="wrap">{body}</main>
<footer><div class="wrap foot"><div><b>ONLINE SERVICE HUB</b><br>
ALL ONLINE SERVICES IN ONE PLACE &middot; SINCE 2025<br>
Support: {esc(setting("support_name"))} &middot; WhatsApp: {esc(setting("support_number"))}</div>
<div><a href="/privacy">Privacy Policy</a> &middot; <a href="/terms">Terms &amp; Conditions</a>
&middot; <a href="/about">About</a> &middot; <a href="/contact">Contact</a></div></div></footer>
<a class="wa" href="{wa_link()}" target="_blank" rel="noopener">WhatsApp Support</a>
</body></html>"""

def flash():
    msg = session.pop("msg", None)
    return f'<div class="msg">{esc(msg)}</div>' if msg else ""

def item_card(it):
    return (f'<div class="card"><h3>{esc(it["name"])}</h3>'
            f'<span class="tag">{fmt_item_type(it["type"])}</span>'
            f'<p>{esc(it["description"] or "Details on request.")}</p>'
            f'<p class="price">{money(it["price"])}</p>'
            f'<a class="btn" href="/item/{it["id"]}">View &amp; Order</a></div>')

def tracking_steps(order):
    steps = ["Placed", "Payment verified", "Processing", "Completed"]
    cur = order["order_status"]
    idx = {"Placed": 0, "Payment verified": 1, "Processing": 2, "Completed": 3}.get(cur, 0)
    if order["payment_status"] == "rejected":
        return "<p><b>Payment rejected by admin.</b> Please contact support on WhatsApp.</p>"
    out = '<ol class="steps">'
    for i, s in enumerate(steps):
        cls = "done" if i <= idx else ""
        out += f'<li class="{cls}">{s}</li>'
    out += "</ol>"
    return out

# ---------------------------------------------------------------- public pages
@app.route("/")
def home():
    items = db().execute("SELECT * FROM items WHERE active=1 ORDER BY id DESC LIMIT 12").fetchall()
    revs = db().execute(
        "SELECT r.*, u.name AS uname, i.name AS iname FROM reviews r "
        "JOIN users u ON u.id=r.user_id JOIN items i ON i.id=r.item_id "
        "WHERE r.status='approved' ORDER BY r.id DESC LIMIT 6").fetchall()
    if items:
        catalog = "".join(item_card(it) for it in items)
    else:
        catalog = ('<div class="empty"><h3>Services &amp; products coming soon</h3>'
                   '<p>No services or products have been listed yet. The owner adds '
                   'them from the Admin Dashboard, and they appear here automatically. '
                   'For help, contact support on WhatsApp.</p></div>')
    rev_html = "".join(
        f'<div class="card"><p>{"★" * int(r["rating"])}</p><p>{esc(r["comment"])}</p>'
        f'<small>{esc(r["uname"])} &middot; {esc(r["iname"])}</small></div>' for r in revs) \
        or "<p>No reviews yet.</p>"
    body = (flash() + f'<section class="hero"><h1>All online services in one place</h1>'
            f'<p>{esc(setting("about_text"))}</p>'
            f'<a class="btn" href="/services">Browse Services &amp; Products</a> '
            f'<a class="btn outline" href="{wa_link()}" target="_blank" rel="noopener">WhatsApp Support</a></section>'
            f'<h2>Services &amp; Products</h2><div class="grid">{catalog}</div>'
            f'<h2>Customer Reviews</h2><div class="grid">{rev_html}</div>')
    return page("Home", body)

@app.route("/services")
def services():
    q = (request.args.get("q") or "").strip()
    t = request.args.get("type") or ""
    sql = "SELECT * FROM items WHERE active=1"
    args = []
    if t in ("digital", "physical"):
        sql += " AND type=?"; args.append(t)
    if q:
        sql += " AND (name LIKE ? OR description LIKE ?)"; args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY id DESC"
    items = db().execute(sql, args).fetchall()
    cards = "".join(item_card(it) for it in items) or \
        ('<div class="empty"><p>No items in this category yet. The owner adds '
         'services and products from the Admin Dashboard.</p></div>')
    body = (flash() + '<h1>Services &amp; Products</h1>'
            '<form class="filters" method="get"><input name="q" placeholder="Search" value="' + esc(q) + '">'
            '<select name="type"><option value="">All</option>'
            '<option value="digital"' + (' selected' if t == "digital" else '') + '>Digital Services</option>'
            '<option value="physical"' + (' selected' if t == "physical" else '') + '>Physical Products</option>'
            '</select><button class="btn" type="submit">Search</button></form>'
            '<p><a href="/services">All</a> | <a href="/services?type=digital">Digital Services</a> | '
            '<a href="/services?type=physical">Physical Products</a></p>'
            f'<div class="grid">{cards}</div>')
    return page("Services & Products", body)

@app.route("/about")
def about():
    return page("About Us", f"<h1>About Us</h1><p>{esc(setting('about_text'))}</p>"
                            f"<p>Support contact: {esc(setting('support_name'))} "
                            f"on WhatsApp {esc(setting('support_number'))}.</p>")

@app.route("/contact")
def contact():
    return page("Contact & Support",
                f"<h1>Contact &amp; Support</h1><p>Support contact: <b>{esc(setting('support_name'))}</b></p>"
                f"<p>WhatsApp: <b>{esc(setting('support_number'))}</b></p>"
                f'<p><a class="btn" href="{wa_link()}" target="_blank" rel="noopener">Chat on WhatsApp</a></p>')

@app.route("/privacy")
def privacy():
    return page("Privacy Policy",
                "<h1>Privacy Policy</h1><p>We collect only what registration asks for: "
                "your Full Name and WhatsApp Number, plus the details of orders you place. "
                "We use this information only to process orders, show your order history and "
                "provide support. We do not sell your information. Contact support on WhatsApp "
                "if you want your account details corrected or removed.</p>")

@app.route("/terms")
def terms():
    return page("Terms & Conditions",
                "<h1>Terms &amp; Conditions</h1><p>By using ONLINE SERVICE HUB you agree to "
                "these terms. Prices shown are for the listed service or product. An order is "
                "not complete without payment: you must pay by the JazzCash details shown at "
                "checkout and enter a valid transaction ID. The admin verifies payment before "
                "an order is processed. If payment cannot be verified, the order will be marked "
                "rejected and you should contact support on WhatsApp. The owner may change "
                "listings and prices from the Admin Dashboard.</p>")

# ---------------------------------------------------------------- customer auth
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        wa = (request.form.get("whatsapp") or "").strip()
        if not name or not wa:
            session["msg"] = "Please enter both Full Name and WhatsApp Number."
            return redirect(url_for("register"))
        con = db()
        try:
            con.execute("INSERT INTO users(name, whatsapp, created) VALUES(?, ?, ?)",
                        (name, wa, now())); con.commit()
        except sqlite3.IntegrityError:
            session["msg"] = "This WhatsApp Number is already registered. Please log in."
            return redirect(url_for("login"))
        u = con.execute("SELECT * FROM users WHERE whatsapp=?", (wa,)).fetchone()
        session["user_id"] = u["id"]
        session["msg"] = f"Welcome, {name}! Your account is ready."
        return redirect(url_for("dashboard"))
    return page("Register", flash() + """<h1>Customer Registration</h1>
<p>Only two details are needed: Full Name and WhatsApp Number.</p>
<form method="post"><label>Full Name<br><input name="name" required></label><br>
<label>WhatsApp Number<br><input name="whatsapp" required placeholder="03xxxxxxxxx"></label><br>
<button class="btn" type="submit">Create Account</button></form>
<p>Already have an account? <a href="/login">Login</a></p>""")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        wa = (request.form.get("whatsapp") or "").strip()
        u = db().execute("SELECT * FROM users WHERE whatsapp=? AND name=?", (wa, name)).fetchone()
        if not u:
            session["msg"] = "No account found with that Full Name and WhatsApp Number. Please register first."
            return redirect(url_for("login"))
        session["user_id"] = u["id"]
        return redirect(url_for("dashboard"))
    return page("Login", flash() + """<h1>Customer Login</h1>
<form method="post"><label>Full Name<br><input name="name" required></label><br>
<label>WhatsApp Number<br><input name="whatsapp" required></label><br>
<button class="btn" type="submit">Login</button></form>
<p>New here? <a href="/register">Register</a></p>""")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    u = current_user()
    if not u:
        session["msg"] = "Please log in first."
        return redirect(url_for("login"))
    orders = db().execute(
        "SELECT o.*, i.name AS iname FROM orders o JOIN items i ON i.id=o.item_id "
        "WHERE o.user_id=? ORDER BY o.id DESC", (u["id"],)).fetchall()
    notes = db().execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 10",
                         (u["id"],)).fetchall()
    oh = "".join(
        f'<div class="card"><b>Order #{o["id"]}</b> &middot; {esc(o["iname"])} &times; {o["qty"]}<br>'
        f'Total: {money(o["total"])} &middot; Payment: {esc(o["payment_status"])}<br>'
        f'Status: {esc(o["order_status"])}<br>'
        f'<a href="/order/{o["id"]}">View details &amp; tracking</a></div>' for o in orders) \
        or "<p>No orders yet.</p>"
    nh = "".join(f'<li>{esc(n["created"])} &mdash; {esc(n["message"])}</li>' for n in notes) or "<li>No notifications yet.</li>"
    body = (flash() + f"<h1>Dashboard</h1><p>Welcome, <b>{esc(u['name'])}</b> "
            f"({esc(u['whatsapp'])}).</p><h2>Order Confirmation &amp; Notifications</h2><ul>{nh}</ul>"
            f"<h2>Order History</h2><div class='grid'>{oh}</div>"
            f'<p><a class="btn" href="/services">Browse Services &amp; Products</a></p>')
    return page("Dashboard", body, user=u)

# ---------------------------------------------------------------- ordering
@app.route("/item/<int:item_id>")
def item_detail(item_id):
    it = db().execute("SELECT * FROM items WHERE id=? AND active=1", (item_id,)).fetchone()
    if not it:
        return page("Not found", "<h1>Item not found</h1>"), 404
    u = current_user()
    revs = db().execute(
        "SELECT r.*, u.name AS uname FROM reviews r JOIN users u ON u.id=r.user_id "
        "WHERE r.item_id=? AND r.status='approved' ORDER BY r.id DESC", (item_id,)).fetchall()
    rev_html = "".join(
        f'<div class="card"><p>{"★" * int(r["rating"])}</p><p>{esc(r["comment"])}</p>'
        f'<small>{esc(r["uname"])}</small></div>' for r in revs) or "<p>No reviews yet.</p>"
    review_form = ""
    if u:
        review_form = (f'<h3>Leave a review</h3><form method="post" action="/review/{item_id}">'
                       '<label>Rating (1-5)<br><input type="number" name="rating" min="1" max="5" value="5" required></label><br>'
                       '<label>Comment<br><textarea name="comment" required></textarea></label><br>'
                       '<button class="btn" type="submit">Submit Review</button></form>'
                       '<p>Reviews are shown after admin approval.</p>')
    body = (flash() + f"<h1>{esc(it['name'])}</h1><span class='tag'>{fmt_item_type(it['type'])}</span>"
            f"<p>{esc(it['description'])}</p>"
            f"<p>{esc(it['stock'])}</p><p class='price'>{money(it['price'])}</p>"
            f'<form method="get" action="/checkout/{item_id}"><label>Quantity<br>'
            f'<input type="number" name="qty" min="1" value="1" required></label><br>'
            f'<button class="btn" type="submit">Order Now &amp; Pay</button></form>'
            f"<h2>Reviews &amp; Ratings</h2><div class='grid'>{rev_html}</div>{review_form}")
    return page(it["name"], body, user=u)

@app.route("/review/<int:item_id>", methods=["POST"])
def add_review(item_id):
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    try:
        rating = int(request.form.get("rating") or 5)
    except ValueError:
        rating = 5
    rating = max(1, min(5, rating))
    db().execute("INSERT INTO reviews(user_id, item_id, rating, comment, created) VALUES(?, ?, ?, ?, ?)",
                 (u["id"], item_id, rating, (request.form.get("comment") or "").strip(), now()))
    db().commit()
    session["msg"] = "Thank you! Your review is waiting for admin approval."
    return redirect(f"/item/{item_id}")

@app.route("/checkout/<int:item_id>", methods=["GET", "POST"])
def checkout(item_id):
    u = current_user()
    if not u:
        session["msg"] = "Please register or log in first (Full Name + WhatsApp Number only)."
        return redirect(url_for("register"))
    it = db().execute("SELECT * FROM items WHERE id=? AND active=1", (item_id,)).fetchone()
    if not it:
        return page("Not found", "<h1>Item not found</h1>"), 404
    try:
        qty = int(request.args.get("qty") or request.form.get("qty") or 1)
    except ValueError:
        qty = 1
    qty = max(1, qty)
    total = float(it["price"]) * qty
    if request.method == "POST":
        txn = (request.form.get("transaction_id") or "").strip()
        # Required order details, in English, for every item type.
        details = {}
        for key, _label in ORDER_DETAIL_FIELDS:
            details[key] = (request.form.get(key) or "").strip()
        missing = [label for key, label in ORDER_DETAIL_FIELDS if not details[key]]
        if missing:
            session["msg"] = ("Please fill in all required order details: " + ", ".join(missing) + ".")
            return redirect(f"/checkout/{item_id}?qty={qty}")
        if not txn:
            session["msg"] = "Payment is required: please enter your JazzCash transaction ID. An order is not complete without payment."
            return redirect(f"/checkout/{item_id}?qty={qty}")
        con = db()
        cur = con.execute(
            "INSERT INTO orders(user_id, item_id, qty, total, payment_method, transaction_id, created, "
            "full_name, delivery_address, country, state_province, city, postal_code, mobile_number) "
            "VALUES(?, ?, ?, ?, 'JazzCash', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (u["id"], item_id, qty, total, txn, now(),
             details["full_name"], details["delivery_address"], details["country"],
             details["state_province"], details["city"], details["postal_code"],
             details["mobile_number"]))
        oid = cur.lastrowid
        con.commit()
        notify(u["id"], f"Order Confirmation: Order #{oid} placed for {it['name']}. Payment is pending admin verification.")
        session["msg"] = f"Order Confirmation: Order #{oid} received. Payment is pending admin verification."
        return redirect(f"/order/{oid}")
    body = (flash() + f"<h1>Checkout</h1><p>{esc(it['name'])} &times; {qty} = <b>{money(total)}</b></p>"
            "<h2>Order Details</h2><p>All fields below are required, for any product or service.</p>"
            "<h2>Pay now - JazzCash (manual payment, no automatic gateway)</h2>"
            f"<p>Send <b>{money(total)}</b> to JazzCash number <b>{esc(setting('jazzcash_number'))}</b> "
            f"(account name: <b>{esc(setting('jazzcash_name'))}</b>), then enter your transaction ID below.</p>"
            f'<form method="post"><input type="hidden" name="qty" value="{qty}">'
            f'<label>Full Name<br><input name="full_name" value="{esc(u["name"])}" required></label><br>'
            '<label>Full Delivery Address<br><textarea name="delivery_address" required></textarea></label><br>'
            '<label>Country<br><input name="country" required></label><br>'
            '<label>State / Province<br><input name="state_province" required></label><br>'
            '<label>City<br><input name="city" required></label><br>'
            '<label>Postal / Zip Code<br><input name="postal_code" required></label><br>'
            f'<label>Mobile Number<br><input name="mobile_number" value="{esc(u["whatsapp"])}" required></label><br>'
            '<label>JazzCash Transaction ID<br><input name="transaction_id" required placeholder="Enter transaction ID"></label><br>'
            '<button class="btn" type="submit">Confirm Payment &amp; Place Order</button></form>'
            "<p>Without all order details and a transaction ID the order will not be placed. After the admin verifies "
            "your payment, the order status updates in your dashboard.</p>")
    return page("Checkout", body, user=u)

@app.route("/order/<int:order_id>")
def order_detail(order_id):
    u = current_user()
    is_admin = bool(session.get("admin"))
    if not u and not is_admin:
        return redirect(url_for("login"))
    o = db().execute(
        "SELECT o.*, i.name AS iname, i.type AS itype, u.name AS uname, u.whatsapp AS uw "
        "FROM orders o JOIN items i ON i.id=o.item_id JOIN users u ON u.id=o.user_id WHERE o.id=?",
        (order_id,)).fetchone()
    if not o:
        return page("Not found", "<h1>Order not found</h1>"), 404
    if not is_admin and u["id"] != o["user_id"]:
        return page("Not allowed", "<h1>You cannot view this order.</h1>"), 403
    body = (flash() + f"<h1>Order #{o['id']}</h1>"
            f"<p>Customer: {esc(o['uname'])} ({esc(o['uw'])})</p>"
            f"<p>Item: {esc(o['iname'])} ({fmt_item_type(o['itype'])}) &times; {o['qty']}</p>"
            f"<p>Total: {money(o['total'])}</p>"
            f"<p>Payment: JazzCash &middot; Transaction ID: {esc(o['transaction_id'])} &middot; "
            f"Payment status: <b>{esc(o['payment_status'])}</b></p>"
            f"<p>Order status: <b>{esc(o['order_status'])}</b></p>"
            f"{order_details_html(o)}"
            f"<h2>Order Tracking</h2>{tracking_steps(o)}")
    if is_admin:
        body += "<p><a href='/dashboard'>Back to Dashboard</a> | <a href='/admin/orders'>Admin Orders</a></p>"
    else:
        body += "<p><a href='/dashboard'>Back to Dashboard</a></p>"
    return page(f"Order #{o['id']}", body, user=u)

# ---------------------------------------------------------------- admin
def require_admin():
    if not session.get("admin"):
        session["msg"] = "Admin login required."
        return redirect(url_for("admin_login"))
    return None

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pin = request.form.get("pin") or ""
        if hashlib.sha256(pin.encode()).hexdigest() == setting("admin_pin_hash"):
            session["admin"] = True
            return redirect(url_for("admin_home"))
        session["msg"] = "Wrong admin PIN."
        return redirect(url_for("admin_login"))
    return page("Admin Login", flash() + """<h1>Admin Login</h1>
<p>Admin access is PIN-protected. First PIN: <b>admin123</b> - change it in Site Settings after login.</p>
<form method="post"><label>Admin PIN<br><input type="password" name="pin" required></label><br>
<button class="btn" type="submit">Login as Admin</button></form>""")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/")

@app.route("/admin")
def admin_home():
    r = require_admin()
    if r:
        return r
    con = db()
    counts = {
        "items": con.execute("SELECT COUNT(*) c FROM items").fetchone()["c"],
        "orders": con.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"],
        "customers": con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "pending_payments": con.execute("SELECT COUNT(*) c FROM orders WHERE payment_status='pending'").fetchone()["c"],
        "reviews": con.execute("SELECT COUNT(*) c FROM reviews WHERE status='pending'").fetchone()["c"],
    }
    body = (flash() + "<h1>Admin Dashboard</h1><p>Complete control over the whole website.</p>"
            f"<div class='grid'><div class='card'><b>Services &amp; Products</b><br>{counts['items']}</div>"
            f"<div class='card'><b>Orders</b><br>{counts['orders']}</div>"
            f"<div class='card'><b>Customers</b><br>{counts['customers']}</div>"
            f"<div class='card'><b>Payments pending</b><br>{counts['pending_payments']}</div>"
            f"<div class='card'><b>Reviews pending</b><br>{counts['reviews']}</div></div>"
            "<p><a class='btn' href='/admin/items'>Services &amp; Products</a> "
            "<a class='btn' href='/admin/orders'>Orders &amp; Payments</a> "
            "<a class='btn' href='/admin/customers'>Customers</a> "
            "<a class='btn' href='/admin/reviews'>Reviews</a> "
            "<a class='btn' href='/admin/settings'>Site Settings</a> "
            "<a class='btn outline' href='/admin/logout'>Logout</a></p>")
    return page("Admin Dashboard", body)

@app.route("/admin/items", methods=["GET", "POST"])
def admin_items():
    r = require_admin()
    if r:
        return r
    if request.method == "POST":
        db().execute("INSERT INTO items(type, name, description, price, stock, created) VALUES(?, ?, ?, ?, ?, ?)",
                     (request.form.get("type"), (request.form.get("name") or "").strip(),
                      (request.form.get("description") or "").strip(),
                      float(request.form.get("price") or 0),
                      (request.form.get("stock") or "").strip(), now()))
        db().commit()
        session["msg"] = "Item added."
        return redirect(url_for("admin_items"))
    items = db().execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    rows = "".join(
        f'<div class="card"><b>{esc(it["name"])}</b> ({fmt_item_type(it["type"])}) - {money(it["price"])} '
        f'<br><a href="/admin/items/{it["id"]}/edit">Edit</a> '
        f'<form method="post" action="/admin/items/{it["id"]}/delete" style="display:inline">'
        f'<button type="submit" onclick="return confirm(\'Delete this item?\')">Delete</button></form></div>'
        for it in items) or "<p>No items yet. Add the first service or product below.</p>"
    body = (flash() + "<h1>Services &amp; Products - Admin</h1><div class='grid'>" + rows + "</div>"
            """<h2>Add new service / product</h2><form method="post">
            <label>Type<br><select name="type"><option value="digital">Digital Service</option>
            <option value="physical">Physical Product</option></select></label><br>
            <label>Name<br><input name="name" required></label><br>
            <label>Description<br><textarea name="description"></textarea></label><br>
            <label>Price (Rs)<br><input type="number" step="1" min="0" name="price" required></label><br>
            <label>Stock / delivery info (for physical products)<br><input name="stock"></label><br>
            <button class="btn" type="submit">Add Item</button></form>""")
    return page("Admin - Items", body)

@app.route("/admin/items/<int:item_id>/edit", methods=["GET", "POST"])
def admin_item_edit(item_id):
    r = require_admin()
    if r:
        return r
    it = db().execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not it:
        return page("Not found", "<h1>Item not found</h1>"), 404
    if request.method == "POST":
        db().execute("UPDATE items SET type=?, name=?, description=?, price=?, stock=?, active=? WHERE id=?",
                     (request.form.get("type"), (request.form.get("name") or "").strip(),
                      (request.form.get("description") or "").strip(),
                      float(request.form.get("price") or 0),
                      (request.form.get("stock") or "").strip(),
                      1 if request.form.get("active") else 0, item_id))
        db().commit()
        session["msg"] = "Item updated."
        return redirect(url_for("admin_items"))
    body = (flash() + f"<h1>Edit: {esc(it['name'])}</h1><form method='post'>"
            f"<label>Type<br><select name='type'><option value='digital'{' selected' if it['type']=='digital' else ''}>Digital Service</option>"
            f"<option value='physical'{' selected' if it['type']=='physical' else ''}>Physical Product</option></select></label><br>"
            f"<label>Name<br><input name='name' value='{esc(it['name'])}' required></label><br>"
            f"<label>Description<br><textarea name='description'>{esc(it['description'])}</textarea></label><br>"
            f"<label>Price (Rs)<br><input type='number' step='1' min='0' name='price' value='{it['price']}' required></label><br>"
            f"<label>Stock / delivery info<br><input name='stock' value='{esc(it['stock'])}'></label><br>"
            f"<label><input type='checkbox' name='active'{' checked' if it['active'] else ''}> Active (visible to customers)</label><br>"
            f"<button class='btn' type='submit'>Save Changes</button></form>")
    return page("Edit Item", body)

@app.route("/admin/items/<int:item_id>/delete", methods=["POST"])
def admin_item_delete(item_id):
    r = require_admin()
    if r:
        return r
    db().execute("DELETE FROM items WHERE id=?", (item_id,)); db().commit()
    session["msg"] = "Item deleted."
    return redirect(url_for("admin_items"))

@app.route("/admin/orders", methods=["GET", "POST"])
def admin_orders():
    r = require_admin()
    if r:
        return r
    if request.method == "POST":
        oid = int(request.form.get("order_id"))
        action = request.form.get("action")
        con = db()
        o = con.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if o:
            if action == "verify":
                con.execute("UPDATE orders SET payment_status='verified', order_status='Payment verified' WHERE id=?", (oid,))
                con.commit(); notify(o["user_id"], f"Payment confirmed for Order #{oid}. Your order is now being processed.")
            elif action == "reject":
                con.execute("UPDATE orders SET payment_status='rejected', order_status='Cancelled' WHERE id=?", (oid,))
                con.commit(); notify(o["user_id"], f"Payment could not be verified for Order #{oid}. Please contact support.")
            elif action in ("Processing", "Completed", "Cancelled"):
                con.execute("UPDATE orders SET order_status=? WHERE id=?", (action, oid))
                con.commit(); notify(o["user_id"], f"Order #{oid} status updated to {action}.")
        session["msg"] = "Order updated."
        return redirect(url_for("admin_orders"))
    orders = db().execute(
        "SELECT o.*, i.name AS iname, u.name AS uname, u.whatsapp AS uw FROM orders o "
        "JOIN items i ON i.id=o.item_id JOIN users u ON u.id=o.user_id ORDER BY o.id DESC").fetchall()
    rows = "".join(
        f'<div class="card"><b>Order #{o["id"]}</b> &middot; {esc(o["iname"])} &times; {o["qty"]} &middot; {money(o["total"])}<br>'
        f'Customer: {esc(o["uname"])} ({esc(o["uw"])})<br>Transaction ID: {esc(o["transaction_id"])}<br>'
        f'Full Name: {esc(order_field(o, "full_name"))}<br>'
        f'Full Delivery Address: {esc(order_field(o, "delivery_address"))}<br>'
        f'Country: {esc(order_field(o, "country"))} &middot; State / Province: {esc(order_field(o, "state_province"))} &middot; City: {esc(order_field(o, "city"))}<br>'
        f'Postal / Zip Code: {esc(order_field(o, "postal_code"))} &middot; Mobile Number: {esc(order_field(o, "mobile_number"))}<br>'
        f'Payment: {esc(o["payment_status"])} &middot; Status: {esc(o["order_status"])}<br>'
        f'<form method="post" style="display:inline"><input type="hidden" name="order_id" value="{o["id"]}">'
        f'<button name="action" value="verify">Verify Payment</button> '
        f'<button name="action" value="reject">Reject Payment</button> '
        f'<button name="action" value="Processing">Processing</button> '
        f'<button name="action" value="Completed">Completed</button></form> '
        f'<a href="/order/{o["id"]}">View</a></div>' for o in orders) or "<p>No orders yet.</p>"
    return page("Admin - Orders", flash() + "<h1>Orders &amp; Payments</h1><div class='grid'>" + rows + "</div>")

@app.route("/admin/customers")
def admin_customers():
    r = require_admin()
    if r:
        return r
    users = db().execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    rows = "".join(
        f'<div class="card"><b>{esc(u["name"])}</b><br>WhatsApp: {esc(u["whatsapp"])}<br>'
        f'Registered: {esc(u["created"])}</div>' for u in users) or "<p>No customers yet.</p>"
    return page("Admin - Customers", flash() + "<h1>Customers</h1><div class='grid'>" + rows + "</div>")

@app.route("/admin/reviews", methods=["GET", "POST"])
def admin_reviews():
    r = require_admin()
    if r:
        return r
    if request.method == "POST":
        rid = int(request.form.get("review_id")); action = request.form.get("action")
        if action == "approve":
            db().execute("UPDATE reviews SET status='approved' WHERE id=?", (rid,))
        else:
            db().execute("DELETE FROM reviews WHERE id=?", (rid,))
        db().commit(); session["msg"] = "Review updated."
        return redirect(url_for("admin_reviews"))
    revs = db().execute(
        "SELECT r.*, u.name AS uname, i.name AS iname FROM reviews r "
        "JOIN users u ON u.id=r.user_id JOIN items i ON i.id=r.item_id ORDER BY r.id DESC").fetchall()
    rows = "".join(
        f'<div class="card"><p>{"★" * int(rv["rating"])} {esc(rv["comment"])}</p>'
        f'<small>{esc(rv["uname"])} &middot; {esc(rv["iname"])} &middot; {esc(rv["status"])}</small><br>'
        f'<form method="post" style="display:inline"><input type="hidden" name="review_id" value="{rv["id"]}">'
        f'<button name="action" value="approve">Approve</button> '
        f'<button name="action" value="delete">Delete</button></form></div>' for rv in revs) or "<p>No reviews yet.</p>"
    return page("Admin - Reviews", flash() + "<h1>Reviews &amp; Ratings</h1><div class='grid'>" + rows + "</div>")

@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    r = require_admin()
    if r:
        return r
    if request.method == "POST":
        for k in ("support_name", "support_number", "jazzcash_number", "jazzcash_name", "about_text"):
            set_setting(k, (request.form.get(k) or "").strip())
        new_pin = (request.form.get("new_admin_pin") or "").strip()
        if new_pin:
            set_setting("admin_pin_hash", hashlib.sha256(new_pin.encode()).hexdigest())
            session["msg"] = "Settings saved. Admin PIN changed - use the new PIN next time."
        else:
            session["msg"] = "Settings saved."
        return redirect(url_for("admin_settings"))
    body = (flash() + "<h1>Site Settings</h1><form method='post'>"
            f"<label>Support Name<br><input name='support_name' value='{esc(setting('support_name'))}' required></label><br>"
            f"<label>Support WhatsApp Number<br><input name='support_number' value='{esc(setting('support_number'))}' required></label><br>"
            f"<label>JazzCash Number<br><input name='jazzcash_number' value='{esc(setting('jazzcash_number'))}' required></label><br>"
            f"<label>JazzCash Account Name<br><input name='jazzcash_name' value='{esc(setting('jazzcash_name'))}' required></label><br>"
            f"<label>About Text<br><textarea name='about_text'>{esc(setting('about_text'))}</textarea></label><br>"
            "<label>New Admin PIN (leave blank to keep current PIN)<br><input type='password' name='new_admin_pin'></label><br>"
            "<button class='btn' type='submit'>Save Settings</button></form>")
    return page("Admin - Settings", body)

# ---------------------------------------------------------------- main
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)

# Initialise on import too (for gunicorn / Render start command)
init_db()
