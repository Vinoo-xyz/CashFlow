from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime, date
from functools import wraps
import csv, io, os, re

app = Flask(__name__)

# Secret key diambil dari environment saat online.
# Nilai default ini hanya untuk penggunaan lokal.
app.secret_key = os.environ.get("CASHFLOW_SECRET", "cashflow-local-development-secret")

# Database tetap SQLite agar semua fitur V4 tetap sama.
# Saat di-host, DATABASE_PATH bisa diarahkan ke persistent disk, misalnya:
# /var/data/cashflow_v4.db
DB = os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "cashflow_v4.db")
)

# Cookie lebih aman saat aplikasi berjalan melalui HTTPS di hosting.
if os.environ.get("FLASK_ENV") == "production" or os.environ.get("RENDER"):
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
        name TEXT NOT NULL,
        amount INTEGER NOT NULL CHECK(amount > 0),
        category TEXT NOT NULL,
        note TEXT DEFAULT '',
        transaction_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        amount INTEGER NOT NULL CHECK(amount >= 0),
        UNIQUE(user_id, month),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS category_budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        category TEXT NOT NULL,
        amount INTEGER NOT NULL CHECK(amount >= 0),
        UNIQUE(user_id, month, category),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        target INTEGER NOT NULL CHECK(target > 0),
        saved INTEGER NOT NULL DEFAULT 0 CHECK(saved >= 0),
        deadline TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS recurring (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
        name TEXT NOT NULL,
        amount INTEGER NOT NULL CHECK(amount > 0),
        category TEXT NOT NULL,
        day_of_month INTEGER NOT NULL CHECK(day_of_month BETWEEN 1 AND 28),
        active INTEGER NOT NULL DEFAULT 1,
        last_created_month TEXT DEFAULT '',
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()

def valid_month(value):
    return bool(re.fullmatch(r"\d{4}-\d{2}", value or ""))

def valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False

def parse_amount(value):
    """Accept 300000, 300.000, 1.000.000, or formatted currency text."""
    if value is None:
        raise ValueError
    if isinstance(value, (int, float)):
        amount = int(value)
    else:
        digits = re.sub(r"\D", "", str(value))
        if not digits:
            raise ValueError
        amount = int(digits)
    if amount <= 0:
        raise ValueError
    return amount

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def current_user():
    if "user_id" not in session:
        return None
    conn = db()
    user = conn.execute("SELECT id,name,email FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return user

def month_now():
    return date.today().strftime("%Y-%m")

def month_bounds(month):
    return month + "-01", month + "-31"

def process_recurring(user_id):
    month = month_now()
    conn = db()
    rows = conn.execute(
        "SELECT * FROM recurring WHERE user_id=? AND active=1 AND (last_created_month IS NULL OR last_created_month<>?)",
        (user_id, month)
    ).fetchall()
    today = date.today().day
    for r in rows:
        if today >= r["day_of_month"]:
            txdate = f"{month}-{r['day_of_month']:02d}"
            conn.execute("""INSERT INTO transactions
                (user_id,kind,name,amount,category,note,transaction_date,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (user_id,r["kind"],r["name"],r["amount"],r["category"],
                 "Transaksi berulang", txdate, datetime.now().isoformat()))
            conn.execute("UPDATE recurring SET last_created_month=? WHERE id=?", (month, r["id"]))
    conn.commit()
    conn.close()

@app.route("/")
def index():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))

@app.route("/health")
def health():
    return {"status": "ok"}, 200

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not name or not email or len(password) < 6:
            flash("Isi semua data. Password minimal 6 karakter.", "error")
            return render_template("register.html")
        conn = db()
        try:
            conn.execute("INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                         (name,email,generate_password_hash(password),datetime.now().isoformat()))
            conn.commit()
            flash("Akun berhasil dibuat. Silakan masuk.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email sudah digunakan di CashFlow V4.", "error")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Email atau password salah.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    process_recurring(session["user_id"])
    return render_template("dashboard.html", user=current_user(), month=month_now())

@app.route("/api/summary")
@login_required
def summary():
    user_id = session["user_id"]
    month = request.args.get("month", month_now())
    if not valid_month(month):
        return jsonify({"error":"Bulan tidak valid."}),400
    start,end = month_bounds(month)
    conn = db()
    totals = conn.execute("""
        SELECT
        COALESCE(SUM(CASE WHEN kind='income' THEN amount ELSE 0 END),0) income,
        COALESCE(SUM(CASE WHEN kind='expense' THEN amount ELSE 0 END),0) expense
        FROM transactions WHERE user_id=? AND transaction_date BETWEEN ? AND ?
    """,(user_id,start,end)).fetchone()
    all_totals = conn.execute("""
        SELECT
        COALESCE(SUM(CASE WHEN kind='income' THEN amount ELSE 0 END),0) income,
        COALESCE(SUM(CASE WHEN kind='expense' THEN amount ELSE 0 END),0) expense
        FROM transactions WHERE user_id=?
    """,(user_id,)).fetchone()
    budget = conn.execute("SELECT amount FROM budgets WHERE user_id=? AND month=?", (user_id,month)).fetchone()
    categories = conn.execute("""
        SELECT category, SUM(amount) total FROM transactions
        WHERE user_id=? AND kind='expense' AND transaction_date BETWEEN ? AND ?
        GROUP BY category ORDER BY total DESC
    """,(user_id,start,end)).fetchall()
    conn.close()
    return jsonify({
        "income": totals["income"], "expense": totals["expense"],
        "balance": all_totals["income"]-all_totals["expense"],
        "month_balance": totals["income"]-totals["expense"],
        "budget": budget["amount"] if budget else 0,
        "budget_left": (budget["amount"]-totals["expense"]) if budget else 0,
        "categories": [{"category":r["category"],"total":r["total"]} for r in categories]
    })

@app.route("/api/transactions")
@login_required
def transactions():
    user_id=session["user_id"]; month=request.args.get("month",month_now())
    if not valid_month(month): return jsonify({"error":"Bulan tidak valid."}),400
    start,end=month_bounds(month)
    conn=db()
    rows=conn.execute("""SELECT * FROM transactions
        WHERE user_id=? AND transaction_date BETWEEN ? AND ?
        ORDER BY transaction_date DESC,id DESC""",(user_id,start,end)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/transactions", methods=["POST"])
@login_required
def add_transaction():
    data=request.get_json(silent=True) or {}
    try:
        kind=data["kind"]; name=data["name"].strip(); amount=parse_amount(data["amount"])
        category=data.get("category","Lainnya").strip() or "Lainnya"
        note=data.get("note","").strip()
        txdate=data.get("transaction_date") or date.today().isoformat()
        if kind not in ("income","expense") or not name or not valid_date(txdate): raise ValueError
        conn=db()
        conn.execute("""INSERT INTO transactions
            (user_id,kind,name,amount,category,note,transaction_date,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (session["user_id"],kind,name,amount,category,note,txdate,datetime.now().isoformat()))
        conn.commit(); conn.close()
        return jsonify({"ok":True})
    except (KeyError,ValueError):
        return jsonify({"ok":False,"error":"Data transaksi tidak valid."}),400

@app.route("/api/transactions/<int:tx_id>", methods=["PUT"])
@login_required
def edit_transaction(tx_id):
    data=request.get_json(silent=True) or {}
    conn=db()
    owner=conn.execute("SELECT id FROM transactions WHERE id=? AND user_id=?", (tx_id,session["user_id"])).fetchone()
    if not owner:
        conn.close(); return jsonify({"ok":False,"error":"Transaksi tidak ditemukan."}),404
    try:
        kind=data["kind"]; name=data["name"].strip(); amount=parse_amount(data["amount"])
        category=data.get("category","Lainnya").strip() or "Lainnya"
        note=data.get("note","").strip(); txdate=data.get("transaction_date")
        if kind not in ("income","expense") or not name or not valid_date(txdate): raise ValueError
        conn.execute("""UPDATE transactions SET kind=?,name=?,amount=?,category=?,note=?,transaction_date=?
                        WHERE id=? AND user_id=?""",
                     (kind,name,amount,category,note,txdate,tx_id,session["user_id"]))
        conn.commit(); conn.close()
        return jsonify({"ok":True})
    except (KeyError,ValueError):
        conn.close(); return jsonify({"ok":False,"error":"Data transaksi tidak valid."}),400

@app.route("/api/transactions/<int:tx_id>", methods=["DELETE"])
@login_required
def delete_transaction(tx_id):
    conn=db(); conn.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tx_id,session["user_id"])); conn.commit(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/budget", methods=["POST"])
@login_required
def set_budget():
    data=request.get_json(silent=True) or {}; month=data.get("month",month_now())
    try:
        amount=parse_amount(data.get("amount",0))
    except ValueError:
        return jsonify({"ok":False,"error":"Nominal budget tidak valid."}),400
    if not valid_month(month): return jsonify({"ok":False,"error":"Bulan tidak valid."}),400
    conn=db()
    conn.execute("""INSERT INTO budgets(user_id,month,amount) VALUES(?,?,?)
                    ON CONFLICT(user_id,month) DO UPDATE SET amount=excluded.amount""",
                 (session["user_id"],month,amount))
    conn.commit(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/category-budget", methods=["POST"])
@login_required
def set_category_budget():
    data=request.get_json(silent=True) or {}
    try:
        month=data.get("month",month_now()); category=data["category"].strip(); amount=parse_amount(data["amount"])
    except (KeyError,ValueError):
        return jsonify({"ok":False,"error":"Nominal budget kategori tidak valid."}),400
    if not valid_month(month) or not category: return jsonify({"ok":False,"error":"Data tidak valid."}),400
    conn=db()
    conn.execute("""INSERT INTO category_budgets(user_id,month,category,amount) VALUES(?,?,?,?)
                    ON CONFLICT(user_id,month,category) DO UPDATE SET amount=excluded.amount""",
                 (session["user_id"],month,category,amount))
    conn.commit(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/category-budgets")
@login_required
def category_budgets():
    month=request.args.get("month",month_now())
    conn=db()
    rows=conn.execute("SELECT category,amount FROM category_budgets WHERE user_id=? AND month=? ORDER BY category",
                      (session["user_id"],month)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/goals")
@login_required
def goals():
    conn=db(); rows=conn.execute("SELECT * FROM goals WHERE user_id=? ORDER BY id DESC",(session["user_id"],)).fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/goals", methods=["POST"])
@login_required
def add_goal():
    data=request.get_json(silent=True) or {}
    try:
        name=data["name"].strip(); target=parse_amount(data["target"]); saved=max(0,parse_amount(data.get("saved",0)) if data.get("saved",0) not in ("",None,0) else 0); deadline=data.get("deadline","")
        if not name or (deadline and not valid_date(deadline)): raise ValueError
    except (KeyError,ValueError):
        return jsonify({"ok":False,"error":"Data target tidak valid."}),400
    conn=db()
    conn.execute("INSERT INTO goals(user_id,name,target,saved,deadline,created_at) VALUES(?,?,?,?,?,?)",
                 (session["user_id"],name,target,saved,deadline,datetime.now().isoformat()))
    conn.commit(); conn.close(); return jsonify({"ok":True})

@app.route("/api/goals/<int:goal_id>", methods=["PUT"])
@login_required
def update_goal(goal_id):
    data=request.get_json(silent=True) or {}; conn=db()
    if not conn.execute("SELECT id FROM goals WHERE id=? AND user_id=?",(goal_id,session["user_id"])).fetchone():
        conn.close(); return jsonify({"ok":False}),404
    try:
        saved=max(0,parse_amount(data.get("saved",0)) if data.get("saved",0) not in ("",None,0) else 0)
        name=data["name"].strip(); target=parse_amount(data["target"]); deadline=data.get("deadline","")
        if not name or (deadline and not valid_date(deadline)): raise ValueError
    except (KeyError,ValueError):
        conn.close(); return jsonify({"ok":False}),400
    conn.execute("UPDATE goals SET name=?,target=?,saved=?,deadline=? WHERE id=? AND user_id=?",
                 (name,target,saved,deadline,goal_id,session["user_id"]))
    conn.commit(); conn.close(); return jsonify({"ok":True})

@app.route("/api/goals/<int:goal_id>", methods=["DELETE"])
@login_required
def delete_goal(goal_id):
    conn=db(); conn.execute("DELETE FROM goals WHERE id=? AND user_id=?",(goal_id,session["user_id"])); conn.commit(); conn.close(); return jsonify({"ok":True})

@app.route("/api/recurring")
@login_required
def recurring():
    conn=db(); rows=conn.execute("SELECT * FROM recurring WHERE user_id=? ORDER BY active DESC,id DESC",(session["user_id"],)).fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/recurring", methods=["POST"])
@login_required
def add_recurring():
    data=request.get_json(silent=True) or {}
    try:
        kind=data["kind"]; name=data["name"].strip(); amount=parse_amount(data["amount"]); category=data.get("category","Lainnya").strip(); day=int(data["day_of_month"])
        if kind not in ("income","expense") or not name or not category or not 1<=day<=28: raise ValueError
    except (KeyError,ValueError):
        return jsonify({"ok":False,"error":"Data transaksi berulang tidak valid."}),400
    conn=db()
    conn.execute("""INSERT INTO recurring(user_id,kind,name,amount,category,day_of_month)
                    VALUES(?,?,?,?,?,?)""",(session["user_id"],kind,name,amount,category,day))
    conn.commit(); conn.close(); return jsonify({"ok":True})

@app.route("/api/recurring/<int:item_id>", methods=["DELETE"])
@login_required
def delete_recurring(item_id):
    conn=db(); conn.execute("DELETE FROM recurring WHERE id=? AND user_id=?",(item_id,session["user_id"])); conn.commit(); conn.close(); return jsonify({"ok":True})

@app.route("/export.csv")
@login_required
def export_csv():
    month=request.args.get("month",month_now()); start,end=month_bounds(month)
    conn=db(); rows=conn.execute("""SELECT transaction_date,kind,name,amount,category,note
        FROM transactions WHERE user_id=? AND transaction_date BETWEEN ? AND ? ORDER BY transaction_date,id""",
        (session["user_id"],start,end)).fetchall(); conn.close()
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["Tanggal","Jenis","Nama","Jumlah","Kategori","Catatan"])
    for r in rows: writer.writerow(list(r))
    mem=io.BytesIO(output.getvalue().encode("utf-8-sig")); mem.seek(0)
    return send_file(mem,as_attachment=True,download_name=f"cashflow-{month}.csv",mimetype="text/csv")

# Pastikan tabel tersedia baik saat dijalankan lokal maupun lewat Gunicorn.
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
