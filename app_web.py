import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, send_file, session, jsonify, flash
from functools import wraps
from datetime import datetime, timedelta
import hashlib

app = Flask(__name__)
app.secret_key = "change_this_secret_key_in_production"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservations.db")

SALLES = [
    {"nom": "G 11", "etage": "ground floor", "type": "Class"},
    {"nom": "G 12", "etage": "ground floor", "type": "Class"},
    {"nom": "G 13", "etage": "ground floor", "type": "Lab"},

    {"nom": "L1 04", "etage": "first floor", "type": "Class"},
    {"nom": "L1 05", "etage": "first floor", "type": "Class"},
    {"nom": "L1 08", "etage": "first floor", "type": "Lab"},
    {"nom": "L1 18", "etage": "first floor", "type": "Class"},
    {"nom": "L1 19", "etage": "first floor", "type": "Class"},
    {"nom": "L1 20", "etage": "first floor", "type": "Class"},
    {"nom": "L1 21", "etage": "first floor", "type": "Class"},
    {"nom": "L1 22", "etage": "first floor", "type": "Class"},
    {"nom": "L1 26", "etage": "first floor", "type": "Lab"},

    {"nom": "L2 08", "etage": "second floor", "type": "Lab"},
    {"nom": "L2 09", "etage": "second floor", "type": "Class"},
    {"nom": "L2 10", "etage": "second floor", "type": "Class"},
    {"nom": "L2 11", "etage": "second floor", "type": "Class"},
    {"nom": "L2 14", "etage": "second floor", "type": "Class"},
    {"nom": "L2 28", "etage": "second floor", "type": "Class"},
    {"nom": "L2 29", "etage": "second floor", "type": "Class"},
    {"nom": "L2 30", "etage": "second floor", "type": "Class"},
    {"nom": "L2 31", "etage": "second floor", "type": "Class"},
    {"nom": "L2 32", "etage": "second floor", "type": "Class"},
    {"nom": "L2 33", "etage": "second floor", "type": "Class"},
    {"nom": "L2 34", "etage": "second floor", "type": "Class"},
    {"nom": "L2 35", "etage": "second floor", "type": "Class"},

    {"nom": "L3 08", "etage": "third floor", "type": "Lab"},
    {"nom": "L3 09", "etage": "third floor", "type": "Class"},
    {"nom": "L3 10", "etage": "third floor", "type": "Class"},
    {"nom": "L3 11", "etage": "third floor", "type": "Class"},
    {"nom": "L3 13", "etage": "third floor", "type": "Class"},
    {"nom": "L3 27", "etage": "third floor", "type": "Class"},
    {"nom": "L3 28", "etage": "third floor", "type": "Class"},
    {"nom": "L3 29", "etage": "third floor", "type": "Class"},
    {"nom": "L3 30", "etage": "third floor", "type": "Class"},
    {"nom": "L3 31", "etage": "third floor", "type": "Class"},
    {"nom": "L3 32", "etage": "third floor", "type": "Class"},
    {"nom": "L3 33", "etage": "third floor", "type": "Class"},
    {"nom": "L3 34", "etage": "third floor", "type": "Class"},

    {"nom": "L4 08", "etage": "fourth floor", "type": "Lab"},
    {"nom": "L4 09", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 10", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 11", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 14", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 29", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 30", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 31", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 32", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 33", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 34", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 35", "etage": "fourth floor", "type": "Class"},
    {"nom": "L4 36", "etage": "fourth floor", "type": "Class"},
]


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def get_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        etage TEXT,
        salle TEXT,
        genre TEXT,
        periode TEXT,
        date_debut TEXT,
        date_fin TEXT,
        titre TEXT,
        organisateur TEXT,
        created_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Create default admin if not exists
    cur.execute("SELECT COUNT(*) FROM users WHERE username='admin'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", hash_password("admin123"), "admin")
        )

    conn.commit()
    conn.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        if session.get("role") != "admin":
            flash("غير مصرح لك بهذه العملية", "error")
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


def add_notification(user, message):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO notifications (user, message) VALUES (?, ?)",
        (user, message)
    )
    conn.commit()
    conn.close()


# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT username, role FROM users WHERE username=? AND password=?",
            (username, hash_password(password))
        )
        user = cur.fetchone()
        conn.close()
        if user:
            session["user"] = user[0]
            session["role"] = user[1]
            return redirect("/")
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
@admin_required
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        if not username or not password:
            flash("يرجى ملء جميع الحقول", "error")
            return redirect("/register")
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role)
            )
            conn.commit()
            flash(f"تم إنشاء المستخدم {username} بنجاح", "success")
        except sqlite3.IntegrityError:
            flash("اسم المستخدم موجود مسبقاً", "error")
        finally:
            conn.close()
        return redirect("/register")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id DESC")
    users = cur.fetchall()
    conn.close()
    return render_template("register.html", users=users)


@app.route("/delete_user", methods=["POST"])
@admin_required
def delete_user():
    user_id = request.form.get("id")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id=? AND username != 'admin'", (user_id,))
    conn.commit()
    conn.close()
    return redirect("/register")


# ─── CONFLICT CHECK API ───────────────────────────────────────────────────────

@app.route("/check_conflict")
@login_required
def check_conflict():
    salle = request.args.get("salle", "")
    debut = request.args.get("debut", "")
    fin = request.args.get("fin", "")
    periode = request.args.get("periode", "")
    exclude_id = request.args.get("exclude_id", None)

    if not salle or not debut or not fin:
        return jsonify({"conflict": False})

    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT id, titre, organisateur, date_debut, date_fin, periode
        FROM reservations
        WHERE salle = ?
          AND periode = ?
          AND date_debut <= ?
          AND date_fin >= ?
    """
    params = [salle, periode, fin, debut]

    if exclude_id:
        query += " AND id != ?"
        params.append(exclude_id)

    cur.execute(query, params)
    conflicts = cur.fetchall()
    conn.close()

    if conflicts:
        c = conflicts[0]
        return jsonify({
            "conflict": True,
            "detail": f"القاعة محجوزة: «{c[1]}» بواسطة {c[2]} من {c[3]} إلى {c[4]}"
        })

    return jsonify({"conflict": False})


# ─── NOTIFICATIONS API ────────────────────────────────────────────────────────

@app.route("/notifications")
@login_required
def get_notifications():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, message, is_read, created_at FROM notifications WHERE user=? ORDER BY id DESC LIMIT 20",
        (session["user"],)
    )
    notifs = [{"id": r[0], "message": r[1], "is_read": r[2], "created_at": r[3]} for r in cur.fetchall()]
    unread = sum(1 for n in notifs if not n["is_read"])
    conn.close()
    return jsonify({"notifications": notifs, "unread": unread})


@app.route("/notifications/read", methods=["POST"])
@login_required
def mark_read():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET is_read=1 WHERE user=?", (session["user"],))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ─── CALENDAR API ─────────────────────────────────────────────────────────────

@app.route("/calendar_events")
@login_required
def calendar_events():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, titre, salle, date_debut, date_fin, genre, periode, organisateur FROM reservations")
    rows = cur.fetchall()
    conn.close()

    colors = {"Matin": "#2563eb", "Soir": "#7c3aed"}
    events = []
    for r in rows:
        events.append({
            "id": r[0],
            "title": f"{r[1]} — {r[2]}",
            "start": r[3],
            "end": r[4],
            "color": colors.get(r[6], "#059669"),
            "extendedProps": {
                "salle": r[2],
                "organisateur": r[7],
                "periode": r[6],
                "genre": r[5],
            }
        })
    return jsonify(events)


# ─── MAIN ROUTE ───────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    init_db()
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        salle = request.form.get("salle", "")
        debut = request.form.get("debut", "")
        fin = request.form.get("fin", "")
        periode = request.form.get("periode", "")

        # Server-side conflict check
        cur.execute("""
            SELECT id FROM reservations
            WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=?
        """, (salle, periode, fin, debut))
        if cur.fetchone():
            flash("⚠️ تعارض في الحجز: القاعة محجوزة في هذه الفترة والتواريخ", "error")
            conn.close()
            return redirect("/")

        cur.execute("""
            INSERT INTO reservations
            (type, etage, salle, genre, periode, date_debut, date_fin, titre, organisateur, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("type"),
            request.form.get("etage"),
            salle,
            request.form.get("genre"),
            periode,
            debut,
            fin,
            request.form.get("titre"),
            request.form.get("organisateur"),
            session["user"],
        ))
        conn.commit()

        # Notify all users
        cur.execute("SELECT username FROM users")
        all_users = [r[0] for r in cur.fetchall()]
        for u in all_users:
            add_notification(u, f"حجز جديد: «{request.form.get('titre')}» في {salle} من {debut} إلى {fin}")

        conn.close()
        return redirect("/")

    # Filters
    search = request.args.get("search", "")
    f_etage = request.args.get("f_etage", "")
    f_type = request.args.get("f_type", "")
    f_genre = request.args.get("f_genre", "")
    f_periode = request.args.get("f_periode", "")
    f_debut = request.args.get("f_debut", "")
    f_fin = request.args.get("f_fin", "")

    query = "SELECT * FROM reservations WHERE 1=1"
    params = []

    if search:
        query += " AND (titre LIKE ? OR organisateur LIKE ? OR salle LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if f_etage:
        query += " AND etage=?"
        params.append(f_etage)
    if f_type:
        query += " AND type=?"
        params.append(f_type)
    if f_genre:
        query += " AND genre=?"
        params.append(f_genre)
    if f_periode:
        query += " AND periode=?"
        params.append(f_periode)
    if f_debut:
        query += " AND date_debut >= ?"
        params.append(f_debut)
    if f_fin:
        query += " AND date_fin <= ?"
        params.append(f_fin)

    query += " ORDER BY date_debut DESC"
    cur.execute(query, params)
    data = cur.fetchall()

    # Upcoming reservations (next 7 days)
    today = datetime.now().strftime("%Y-%m-%d")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    cur.execute(
        "SELECT COUNT(*) FROM reservations WHERE date_debut BETWEEN ? AND ?",
        (today, next_week)
    )
    upcoming_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM reservations")
    total_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT salle) FROM reservations WHERE date_debut <= ? AND date_fin >= ?", (today, today))
    occupied_today = cur.fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        data=data,
        salles=SALLES,
        user=session["user"],
        role=session["role"],
        search=search,
        f_etage=f_etage,
        f_type=f_type,
        f_genre=f_genre,
        f_periode=f_periode,
        f_debut=f_debut,
        f_fin=f_fin,
        upcoming_count=upcoming_count,
        total_count=total_count,
        occupied_today=occupied_today,
    )


# ─── EXPORT / IMPORT ─────────────────────────────────────────────────────────

@app.route("/export")
@login_required
def export_excel():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM reservations", conn)
    conn.close()
    file_path = os.path.join(BASE_DIR, "export.xlsx")
    df.to_excel(file_path, index=False)
    return send_file(file_path, as_attachment=True)


@app.route("/import", methods=["POST"])
@login_required
def import_excel():
    file = request.files.get("file")
    if not file:
        return "No file", 400

    df = pd.read_excel(file)
    conn = get_db()
    cur = conn.cursor()

    for _, row in df.iterrows():
        cur.execute("""
            INSERT INTO reservations
            (type, etage, salle, genre, periode, date_debut, date_fin, titre, organisateur, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(row.get("type", "")),
            str(row.get("etage", "")),
            str(row.get("salle", "")),
            str(row.get("genre", "")),
            str(row.get("periode", "")),
            str(row.get("date_debut", ""))[:10],
            str(row.get("date_fin", ""))[:10],
            str(row.get("titre", "")),
            str(row.get("organisateur", "")),
            session["user"],
        ))

    conn.commit()
    conn.close()
    return redirect("/")


@app.route("/delete", methods=["POST"])
@login_required
def delete():
    id_ = request.form.get("id")
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT titre, salle, created_by FROM reservations WHERE id=?", (id_,))
    row = cur.fetchone()

    if row and (session["role"] == "admin" or row[2] == session["user"]):
        cur.execute("DELETE FROM reservations WHERE id=?", (id_,))
        conn.commit()
        add_notification(session["user"], f"تم حذف الحجز: «{row[0]}» في {row[1]}")

    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
