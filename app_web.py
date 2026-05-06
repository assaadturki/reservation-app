import os
import hashlib
import json
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
from flask import Flask, request, redirect, send_file, session, jsonify, flash, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret_key_in_production")

# ─── In-memory online users tracker ──────────────────────────────────────────
# {username: {"last_seen": datetime, "login_time": datetime, "ip": str}}
ONLINE_USERS = {}
ONLINE_TIMEOUT = 300  # 5 min inactivity = considered offline
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret_key_in_production")

# ─── DATABASE: PostgreSQL (Render) ou SQLite (local) ──────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL:
    # Render fournit postgres:// mais psycopg2 veut postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    import psycopg2
    import psycopg2.extras
    PG = True
else:
    import sqlite3
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH  = os.path.join(BASE_DIR, "reservations.db")
    PG = False


def get_conn():
    if PG:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        return sqlite3.connect(DB_PATH)


def qmark(sql):
    """Convert SQLite ? placeholders to PostgreSQL %s."""
    if PG:
        return sql.replace("?", "%s")
    return sql


def fetchall(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(qmark(sql), params)
    return cur.fetchall()


def fetchone(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(qmark(sql), params)
    return cur.fetchone()


def execute(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(qmark(sql), params)


def _bootstrap_db():
    conn = get_conn()
    if PG:
        execute(conn, """CREATE TABLE IF NOT EXISTS reservations (
            id SERIAL PRIMARY KEY,
            course_code TEXT,
            type TEXT, etage TEXT, salle TEXT, genre TEXT, periode TEXT,
            date_debut TEXT, date_fin TEXT, titre TEXT, organisateur TEXT,
            level TEXT, competance TEXT, method TEXT, registred INTEGER DEFAULT 0, status TEXT,
            created_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()
        # Migrations — each in its own try/except + rollback
        for col, defval in [
            ("course_code", "TEXT"),
            ("level",       "TEXT"),
            ("competance",  "TEXT"),
            ("method",      "TEXT"),
            ("registred",   "INTEGER DEFAULT 0"),
            ("status",      "TEXT"),
        ]:
            try:
                execute(conn, f"ALTER TABLE reservations ADD COLUMN {col} {defval}")
                conn.commit()
            except Exception:
                conn.rollback()
        execute(conn, """CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            role TEXT DEFAULT 'user', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()
        execute(conn, """CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            "user" TEXT, message TEXT, is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()
        execute(conn, """CREATE TABLE IF NOT EXISTS user_sessions (
            id SERIAL PRIMARY KEY,
            username TEXT, login_at TEXT, logout_at TEXT,
            duration_seconds INTEGER DEFAULT 0, ip TEXT)""")
        conn.commit()
        row = fetchone(conn, "SELECT COUNT(*) FROM users WHERE username=%s", ("admin",))
        if row[0] == 0:
            execute(conn, "INSERT INTO users (username,password,role) VALUES (%s,%s,%s)",
                    ("admin", hashlib.sha256(b"admin123").hexdigest(), "admin"))
        conn.commit()
    else:
        execute(conn, """CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT,
            type TEXT, etage TEXT, salle TEXT, genre TEXT, periode TEXT,
            date_debut TEXT, date_fin TEXT, titre TEXT, organisateur TEXT,
            level TEXT, competance TEXT, method TEXT, registred INTEGER DEFAULT 0, status TEXT,
            created_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        for col, defval in [
            ("course_code", "TEXT"),
            ("level",       "TEXT"),
            ("competance",  "TEXT"),
            ("method",      "TEXT"),
            ("registred",   "INTEGER DEFAULT 0"),
            ("status",      "TEXT"),
        ]:
            try:
                execute(conn, f"ALTER TABLE reservations ADD COLUMN {col} {defval}")
            except Exception:
                pass
        execute(conn, """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            role TEXT DEFAULT 'user', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        execute(conn, """CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT, message TEXT, is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        execute(conn, """CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, login_at TEXT, logout_at TEXT,
            duration_seconds INTEGER DEFAULT 0, ip TEXT)""")
        row = fetchone(conn, "SELECT COUNT(*) FROM users WHERE username=?", ("admin",))
        if row[0] == 0:
            execute(conn, "INSERT INTO users (username,password,role) VALUES (?,?,?)",
                    ("admin", hashlib.sha256(b"admin123").hexdigest(), "admin"))
        conn.commit()
    conn.close()

_bootstrap_db()

SALLES = [
    {"nom": "G 11", "etage": "الأرضي", "type": "قاعة"},
    {"nom": "G 12", "etage": "الأرضي", "type": "قاعة"},
    {"nom": "G 13", "etage": "الأرضي", "type": "قاعة"},
    {"nom": "L1 04", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 05", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 08", "etage": "الأول", "type": "مختبر"},
    {"nom": "L1 18", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 19", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 20", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 21", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 22", "etage": "الأول", "type": "مختبر"},
    {"nom": "L1 26", "etage": "الأول", "type": "قاعة"},
    {"nom": "L2 08", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 09", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 10", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 11", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 14", "etage": "الثاني", "type": "مختبر"},
    {"nom": "L2 28", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 29", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 30", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 31", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 32", "etage": "الثاني", "type": "مختبر"},
    {"nom": "L2 33", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 34", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 35", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L3 08", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 09", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 10", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 11", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 13", "etage": "الثالث", "type": "مختبر"},
    {"nom": "L3 27", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 28", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 29", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 30", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 31", "etage": "الثالث", "type": "مختبر"},
    {"nom": "L3 32", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 33", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 34", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L4 08", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 09", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 10", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 11", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 14", "etage": "الرابع", "type": "مختبر"},
    {"nom": "L4 29", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 30", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 31", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 32", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 33", "etage": "الرابع", "type": "مختبر"},
    {"nom": "L4 34", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 35", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 36", "etage": "الرابع", "type": "قاعة"},
]

# ─────────────────────────────────────────────────────────────────────────────
#  TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

LOGIN_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>تسجيل الدخول</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3e;--accent:#4f6ef7;--accent2:#7c3aed;--text:#e2e8f0;--muted:#64748b}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;overflow:hidden}
.orbs{position:fixed;inset:0;pointer-events:none}
.orb{position:absolute;border-radius:50%;filter:blur(80px);opacity:.15}
.o1{width:400px;height:400px;background:var(--accent);top:-100px;right:-100px;animation:f1 8s ease-in-out infinite}
.o2{width:300px;height:300px;background:var(--accent2);bottom:-80px;left:-80px;animation:f2 10s ease-in-out infinite}
@keyframes f1{0%,100%{transform:translate(0,0)}50%{transform:translate(-30px,30px)}}
@keyframes f2{0%,100%{transform:translate(0,0)}50%{transform:translate(20px,-20px)}}
.card{position:relative;z-index:1;background:var(--card);border:1px solid var(--border);border-radius:20px;padding:48px 40px;width:420px;box-shadow:0 25px 60px rgba(0,0,0,.5);animation:up .5s ease}
@keyframes up{from{opacity:0;transform:translateY(30px)}to{opacity:1;transform:translateY(0)}}
.logo{text-align:center;margin-bottom:32px}
.logo-icon{width:64px;height:64px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:16px;display:inline-flex;align-items:center;justify-content:center;font-size:28px;margin-bottom:12px;box-shadow:0 8px 24px rgba(79,110,247,.3)}
.logo h1{font-size:22px;font-weight:700}.logo p{color:var(--muted);font-size:13px;margin-top:4px}
.field{margin-bottom:20px}.field label{display:block;font-size:14px;font-weight:600;margin-bottom:8px}
.field input{width:100%;background:var(--bg);border:1.5px solid var(--border);border-radius:10px;color:var(--text);font-family:'Cairo',sans-serif;font-size:15px;padding:12px 16px;transition:border-color .2s,box-shadow .2s;outline:none}
.field input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(79,110,247,.15)}
.btn{width:100%;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border:none;border-radius:10px;font-family:'Cairo',sans-serif;font-size:16px;font-weight:700;padding:14px;cursor:pointer;transition:opacity .2s,transform .1s;margin-top:8px}
.btn:hover{opacity:.9;transform:translateY(-1px)}
.flash{padding:12px 16px;border-radius:10px;font-size:14px;margin-bottom:20px;font-weight:600}
.flash.error{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);color:#f87171}
.flash.success{background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.3);color:#4ade80}
</style></head><body>
<div class="orbs"><div class="orb o1"></div><div class="orb o2"></div></div>
<div class="card">
  <div class="logo"><div class="logo-icon">🏛️</div><h1>حجز القاعات</h1><p>نظام إدارة حجز القاعات الجامعية</p></div>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
  {% endwith %}
  <form method="POST">
    <div class="field"><label>اسم المستخدم</label><input type="text" name="username" placeholder="أدخل اسم المستخدم" required autofocus></div>
    <div class="field"><label>كلمة المرور</label><input type="password" name="password" placeholder="أدخل كلمة المرور" required></div>
    <button type="submit" class="btn">تسجيل الدخول</button>
  </form>
</div><!-- Gantt Tooltip -->
<div id="gantt-tip" style="display:none;position:fixed;z-index:9999;background:#fefefe;color:#1a2e28;border:1.5px solid #a8c8c0;border-radius:10px;padding:14px 16px;min-width:220px;max-width:280px;font-family:'Cairo',sans-serif;font-size:12px;line-height:1.8;box-shadow:0 6px 20px rgba(0,0,0,.15);pointer-events:auto;direction:rtl;"></div>

</body></html>"""

REGISTER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>إدارة المستخدمين</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#e8f0ee;--sidebar:#c8ddd8;--topbar:#5a8a7a;--accent:#3d7a6a;--accent2:#2d6a5a;--text:#1a2e28;--muted:#5a7a72;--border:#a8c8c0;--white:#fff;--red:#c0392b;--green:#27ae60}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;direction:rtl;padding:0}
.topbar{background:var(--topbar);color:#fff;padding:0 16px;display:flex;align-items:center;gap:12px;height:44px;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.topbar h1{font-size:15px;font-weight:900;flex:1}
a.back{background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:6px;padding:5px 14px;font-family:'Cairo',sans-serif;font-size:12px;text-decoration:none}
a.back:hover{background:rgba(255,255,255,.3)}
.main{padding:20px;max-width:1000px;margin:0 auto}
.flash{padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:14px;font-weight:600}
.flash.error{background:#fdecea;border:1px solid #e57373;color:#c0392b}
.flash.success{background:#e8f5e9;border:1px solid #81c784;color:#2e7d32}
.grid{display:grid;grid-template-columns:320px 1fr;gap:20px;align-items:start}
.card{background:var(--white);border:1.5px solid var(--border);border-radius:12px;padding:20px}
.card h2{font-size:14px;font-weight:900;color:var(--accent2);margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid var(--border)}
.field{margin-bottom:12px}
.field label{display:block;font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px}
.field input,.field select{width:100%;background:var(--bg);border:1.5px solid var(--border);border-radius:7px;color:var(--text);font-family:'Cairo',sans-serif;font-size:13px;padding:8px 11px;outline:none;height:36px}
.field input:focus,.field select:focus{border-color:var(--accent)}
.field select option{background:var(--white)}
.btn-primary{background:var(--green);color:#fff;border:none;border-radius:7px;font-family:'Cairo',sans-serif;font-size:13px;font-weight:700;padding:10px;cursor:pointer;width:100%;margin-top:4px}
.btn-primary:hover{background:#219a52}
.btn-danger{background:#fdecea;color:var(--red);border:1px solid #e57373;border-radius:6px;font-family:'Cairo',sans-serif;font-size:11px;font-weight:700;padding:5px 12px;cursor:pointer}
.btn-danger:hover{background:#fbbcba}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{background:var(--topbar);color:#fff;font-weight:700;text-align:right;padding:9px 12px;font-size:11px;letter-spacing:.3px}
thead th:first-child{text-align:center}
tbody tr:nth-child(even){background:#f0f7f5}
tbody td{padding:10px 12px;border-bottom:1px solid var(--border)}
tbody tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:700}
.badge-admin{background:rgba(61,122,106,.15);color:var(--accent2);border:1px solid rgba(61,122,106,.3)}
.badge-user{background:rgba(90,122,114,.1);color:var(--muted);border:1px solid var(--border)}
</style></head><body>
<div class="topbar">
  <a href="/" class="back">← رجوع</a>
  <h1>👥 إدارة المستخدمين</h1>
</div>
<div class="main">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat,msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
  {% endwith %}
  <div class="grid">
    <div class="card">
      <h2>➕ إنشاء مستخدم جديد</h2>
      <form method="POST" action="/register">
        <div class="field"><label>اسم المستخدم</label><input type="text" name="username" placeholder="username" required></div>
        <div class="field"><label>كلمة المرور</label><input type="password" name="password" placeholder="••••••••" required></div>
        <div class="field"><label>الصلاحية</label>
          <select name="role">
            <option value="user">مستخدم عادي</option>
            <option value="admin">مسؤول</option>
          </select>
        </div>
        <button type="submit" class="btn-primary">✔ إنشاء المستخدم</button>
      </form>
    </div>
    <div class="card">
      <h2>📋 قائمة المستخدمين ({{ users|length }})</h2>
      <table>
        <thead><tr><th>#</th><th>اسم المستخدم</th><th>الصلاحية</th><th>الإجراء</th></tr></thead>
        <tbody>
        {% for u in users %}
        <tr>
          <td style="text-align:center;color:var(--muted);font-size:11px;">{{ u[0] }}</td>
          <td><strong>{{ u[1] }}</strong></td>
          <td><span class="badge {% if u[2]=='admin' %}badge-admin{% else %}badge-user{% endif %}">{{ 'مسؤول' if u[2]=='admin' else 'مستخدم' }}</span></td>
          <td>{% if u[1] != 'admin' %}
            <form method="POST" action="/delete_user" style="display:inline;" onsubmit="return confirm('حذف المستخدم {{ u[1] }}؟')">
              <input type="hidden" name="id" value="{{ u[0] }}">
              <button type="submit" class="btn-danger">حذف</button>
            </form>
          {% else %}<span style="color:var(--muted);font-size:11px;">محمي</span>{% endif %}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div></body></html>"""

DASHBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>لوحة التحكم</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#e8f0ee;--topbar:#5a8a7a;--accent:#3d7a6a;--accent2:#2d6a5a;--text:#1a2e28;--muted:#5a7a72;--border:#a8c8c0;--white:#fff;--green:#27ae60;--red:#c0392b;--blue:#2471a3;--orange:#e67e22}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);direction:rtl}
.topbar{background:var(--topbar);color:#fff;padding:0 16px;display:flex;align-items:center;gap:10px;height:44px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.topbar h1{font-size:14px;font-weight:900;flex:1}
a.tbtn{color:#fff;border:1px solid rgba(255,255,255,.3);border-radius:6px;padding:4px 12px;font-family:'Cairo',sans-serif;font-size:11px;text-decoration:none;font-weight:700}
a.tbtn:hover{background:rgba(255,255,255,.2)}
.main{padding:16px;max-width:1400px;margin:0 auto}
.filter-bar{background:var(--white);border:1.5px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:16px;display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap}
.filter-bar label{font-size:10px;font-weight:700;color:var(--muted);display:block;margin-bottom:3px;text-transform:uppercase}
.filter-bar input{background:var(--bg);border:1.5px solid var(--border);border-radius:6px;padding:5px 8px;font-family:'Cairo',sans-serif;font-size:12px;height:32px;outline:none}
.filter-bar input:focus{border-color:var(--accent)}
.fbtn{background:var(--topbar);color:#fff;border:none;border-radius:6px;padding:0 16px;height:32px;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;cursor:pointer}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:16px}
.kpi{background:var(--white);border:1.5px solid var(--border);border-radius:10px;padding:16px;text-align:center;position:relative;overflow:hidden}
.kpi::before{content:'';position:absolute;top:0;right:0;left:0;height:4px}
.kpi.green::before{background:var(--green)}.kpi.blue::before{background:var(--blue)}
.kpi.red::before{background:var(--red)}.kpi.orange::before{background:var(--orange)}
.kpi.teal::before{background:var(--topbar)}
.kpi-val{font-size:32px;font-weight:900;color:var(--accent2);line-height:1}
.kpi-label{font-size:11px;color:var(--muted);margin-top:5px;font-weight:600}
.dash-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.dash-grid.three{grid-template-columns:1fr 1fr 1fr}
@media(max-width:900px){.dash-grid,.dash-grid.three{grid-template-columns:1fr}}
.card{background:var(--white);border:1.5px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:0}
.card-header{background:var(--topbar);padding:10px 14px;color:#fff;font-size:13px;font-weight:900;display:flex;align-items:center;gap:8px}
.card-body{padding:14px}
.bar-row{display:flex;align-items:center;gap:8px;margin-bottom:7px;font-size:12px}
.bar-label{min-width:80px;text-align:right;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px}
.bar-track{flex:1;background:#e8f0ee;border-radius:4px;height:20px}
.bar-fill{height:100%;border-radius:4px;display:flex;align-items:center;padding-right:6px;justify-content:flex-end;min-width:24px}
.bar-val{font-size:10px;font-weight:700;color:#fff}
.donut-row{display:flex;align-items:center;gap:10px;margin-bottom:10px;font-size:12px}
.dot{width:14px;height:14px;border-radius:50%;flex-shrink:0}
.donut-label{flex:1;font-weight:600}
.donut-pct{font-weight:700;color:var(--accent2)}
.online-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;padding:14px}
.user-card{border:1.5px solid var(--border);border-radius:8px;padding:10px 12px}
.user-card.active{border-color:var(--green);background:#f0faf4}
.user-card.idle{border-color:var(--orange);background:#fef8f0}
.user-name{font-size:13px;font-weight:900;color:var(--accent2)}
.user-meta{font-size:10px;color:var(--muted);margin-top:3px;line-height:1.6}
.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:4px}
.status-dot.active{background:var(--green)}.status-dot.idle{background:var(--orange)}
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{background:var(--topbar);color:#fff;padding:8px 10px;text-align:center;font-size:11px}
tbody td{padding:8px 10px;text-align:center;border-bottom:1px solid var(--border)}
tbody tr:nth-child(even){background:#f5faf8}
</style></head>
<body>
<div class="topbar">
  <a href="/" class="tbtn">← رجوع</a>
  <h1>📊 لوحة التحكم — إحصائيات النظام</h1>
  <a href="/report" class="tbtn">👥 تقرير المستخدمين</a>
</div>
<div class="main">
  <form method="GET" class="filter-bar">
    <div><label>من تاريخ</label><input type="date" name="f_debut" value="{{ f_debut }}"></div>
    <div><label>إلى تاريخ</label><input type="date" name="f_fin"   value="{{ f_fin }}"></div>
    <button type="submit" class="fbtn">🔍 تطبيق</button>
    <a href="/dashboard" class="tbtn" style="height:32px;display:inline-flex;align-items:center;background:var(--topbar);">✕ مسح</a>
  </form>

  <div class="kpi-grid">
    <div class="kpi green"><div class="kpi-val">{{ total }}</div><div class="kpi-label">إجمالي الحجوزات</div></div>
    <div class="kpi blue"><div class="kpi-val">{{ salle_count }}</div><div class="kpi-label">حجوزات قاعات</div></div>
    <div class="kpi red"><div class="kpi-val">{{ lab_count }}</div><div class="kpi-label">حجوزات مختبرات</div></div>
    <div class="kpi orange"><div class="kpi-val">{{ by_etage|length }}</div><div class="kpi-label">طوابق نشطة</div></div>
    <div class="kpi teal"><div class="kpi-val">{{ by_org|length }}</div><div class="kpi-label">منظمون مختلفون</div></div>
    <div class="kpi green"><div class="kpi-val" id="kpi-online">—</div><div class="kpi-label">متصلون الآن</div></div>
  </div>

  <div class="dash-grid">
    <div class="card"><div class="card-header">🏢 الحجوزات حسب الطابق</div><div class="card-body">
      {% set max_e = namespace(v=1) %}{% for r in by_etage %}{% if r[1]>max_e.v %}{% set max_e.v=r[1] %}{% endif %}{% endfor %}
      {% for row in by_etage %}{% set pct=(row[1]/max_e.v*100)|round|int %}
      <div class="bar-row"><span class="bar-label">{{ row[0] or '—' }}</span>
        <div class="bar-track"><div class="bar-fill" style="width:{{ pct }}%;background:var(--accent)"><span class="bar-val">{{ row[1] }}</span></div></div>
      </div>{% endfor %}
    </div></div>

    <div class="card"><div class="card-header">🏆 أكثر القاعات استخداماً</div><div class="card-body">
      {% set max_s = namespace(v=1) %}{% if by_salle %}{% set max_s.v=by_salle[0][1] %}{% endif %}
      {% for row in by_salle %}{% set pct=(row[1]/max_s.v*100)|round|int %}
      {% set col=['#c0392b','#c0392b','#c0392b','#2471a3','#2471a3','#2471a3','#3d7a6a','#3d7a6a','#3d7a6a','#3d7a6a','#3d7a6a','#3d7a6a','#3d7a6a','#3d7a6a','#3d7a6a'] %}
      <div class="bar-row"><span class="bar-label">{{ row[0] }}</span>
        <div class="bar-track"><div class="bar-fill" style="width:{{ pct }}%;background:{{ col[loop.index0] }}"><span class="bar-val">{{ row[1] }}</span></div></div>
      </div>{% endfor %}
    </div></div>
  </div>

  <div class="dash-grid three">
    <div class="card"><div class="card-header">👥 حسب الجنس</div><div class="card-body">
      {% set tot_g=namespace(v=1) %}{% for r in by_genre %}{% set tot_g.v=tot_g.v+r[1] %}{% endfor %}
      {% set cg=['#2980b9','#e67e22','#8e44ad'] %}
      {% for row in by_genre %}<div class="donut-row">
        <span class="dot" style="background:{{ cg[loop.index0%3] }}"></span>
        <span class="donut-label">{{ row[0] }}</span>
        <span class="donut-pct">{{ row[1] }} <small style="color:var(--muted)">({{ (row[1]/tot_g.v*100)|round(1) }}%)</small></span>
      </div>{% endfor %}
    </div></div>

    <div class="card"><div class="card-header">⏰ حسب الفترة</div><div class="card-body">
      {% set tot_p=namespace(v=1) %}{% for r in by_periode %}{% set tot_p.v=tot_p.v+r[1] %}{% endfor %}
      {% for row in by_periode %}<div class="donut-row">
        <span class="dot" style="background:{% if row[0]=='صباحي' %}#27ae60{% else %}#8e44ad{% endif %}"></span>
        <span class="donut-label">{{ row[0] }}</span>
        <span class="donut-pct">{{ row[1] }} <small style="color:var(--muted)">({{ (row[1]/tot_p.v*100)|round(1) }}%)</small></span>
      </div>{% endfor %}
    </div></div>

    <div class="card"><div class="card-header">🏛️ قاعة vs مختبر</div><div class="card-body">
      {% set tot_t=namespace(v=1) %}{% for r in by_type %}{% set tot_t.v=tot_t.v+r[1] %}{% endfor %}
      {% for row in by_type %}<div class="donut-row">
        <span class="dot" style="background:{% if row[0]=='قاعة' %}#3d7a6a{% else %}#c0392b{% endif %}"></span>
        <span class="donut-label">{{ row[0] }}</span>
        <span class="donut-pct">{{ row[1] }} <small style="color:var(--muted)">({{ (row[1]/tot_t.v*100)|round(1) }}%)</small></span>
      </div>{% endfor %}
    </div></div>
  </div>

  <div class="dash-grid">
    <div class="card"><div class="card-header">📅 التوزيع الشهري</div><div class="card-body">
      {% set max_m=namespace(v=1) %}{% for r in by_month %}{% if r[1]>max_m.v %}{% set max_m.v=r[1] %}{% endif %}{% endfor %}
      {% for row in by_month|reverse %}{% set pct=(row[1]/max_m.v*100)|round|int %}
      <div class="bar-row"><span class="bar-label">{{ row[0] }}</span>
        <div class="bar-track"><div class="bar-fill" style="width:{{ pct }}%;background:var(--blue)"><span class="bar-val">{{ row[1] }}</span></div></div>
      </div>{% endfor %}
    </div></div>

    <div class="card"><div class="card-header">🏢 أكثر المنظمين نشاطاً</div><div class="card-body">
      {% set max_o=namespace(v=1) %}{% if by_org %}{% set max_o.v=by_org[0][1] %}{% endif %}
      {% for row in by_org %}{% set pct=(row[1]/max_o.v*100)|round|int %}
      <div class="bar-row"><span class="bar-label" title="{{ row[0] }}">{{ row[0][:18] }}</span>
        <div class="bar-track"><div class="bar-fill" style="width:{{ pct }}%;background:var(--orange)"><span class="bar-val">{{ row[1] }}</span></div></div>
      </div>{% endfor %}
    </div></div>
  </div>

  <!-- Online users -->
  <div class="card" style="margin-bottom:14px;">
    <div class="card-header">🟢 المستخدمون المتصلون الآن
      <span id="online-count" style="background:rgba(255,255,255,.25);padding:1px 10px;border-radius:10px;font-size:11px;margin-right:8px;">—</span>
      <button onclick="loadOnline()" style="background:rgba(255,255,255,.2);border:none;color:#fff;border-radius:4px;padding:2px 8px;cursor:pointer;font-family:'Cairo',sans-serif;font-size:11px;">🔄</button>
    </div>
    <div id="online-grid" class="online-grid">
      <div style="padding:20px;text-align:center;color:var(--muted);grid-column:1/-1;">جاري التحميل...</div>
    </div>
  </div>

  <!-- Session stats -->
  <div class="card">
    <div class="card-header">⏱️ إحصائيات جلسات المستخدمين</div>
    <table><thead><tr>
      <th>المستخدم</th><th>عدد الجلسات</th><th>إجمالي وقت النشاط</th><th>متوسط الجلسة</th><th>آخر دخول</th>
    </tr></thead><tbody>
    {% for r in session_stats %}
    <tr>
      <td><strong style="color:var(--accent2)">{{ r[0] }}</strong></td>
      <td>{{ r[1] }}</td>
      <td>{% set h=(r[2]//3600)|int %}{% set m=((r[2]%3600)//60)|int %}{{ h }}س {{ m }}د</td>
      <td>{% if r[3] %}{{ (r[3]//60)|int }}د{% else %}—{% endif %}</td>
      <td style="font-size:11px;color:var(--muted)">{{ r[4] or '—' }}</td>
    </tr>
    {% else %}
    <tr><td colspan="5" style="text-align:center;color:var(--muted);padding:20px;">لا توجد بيانات جلسات بعد</td></tr>
    {% endfor %}
    </tbody></table>
  </div>
</div>

<script>
async function loadOnline(){
  try{
    let data=await(await fetch('/api/online_users')).json();
    document.getElementById('online-count').textContent=data.length+' متصل';
    let kpi=document.getElementById('kpi-online');
    if(kpi) kpi.textContent=data.length;
    let grid=document.getElementById('online-grid');
    if(!data.length){grid.innerHTML='<div style="padding:20px;text-align:center;color:var(--muted);grid-column:1/-1;">لا يوجد مستخدمون متصلون حالياً</div>';return;}
    grid.innerHTML=data.map(u=>`
      <div class="user-card ${u.status==='نشط'?'active':'idle'}">
        <div class="user-name"><span class="status-dot ${u.status==='نشط'?'active':'idle'}"></span>${u.username}</div>
        <div class="user-meta">🕐 دخل: ${u.login_time}</div>
        <div class="user-meta">👁️ آخر نشاط: ${u.last_seen}</div>
        <div class="user-meta">⏱️ مدة: ${u.active_minutes} دقيقة</div>
        <div class="user-meta">🌐 ${u.ip}</div>
        <div class="user-meta" style="font-weight:700;color:${u.status==='نشط'?'#27ae60':'#e67e22'}">${u.status}</div>
      </div>`).join('');
  }catch(e){console.error(e);}
}
loadOnline();
setInterval(loadOnline,30000);
</script>
</body></html>"""

PROFILE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>الملف الشخصي</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#e8f0ee;--topbar:#5a8a7a;--accent:#3d7a6a;--accent2:#2d6a5a;--text:#1a2e28;--muted:#5a7a72;--border:#a8c8c0;--white:#fff;--green:#27ae60;--red:#c0392b}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;direction:rtl}
.topbar{background:var(--topbar);color:#fff;padding:0 16px;display:flex;align-items:center;gap:12px;height:44px;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.topbar h1{font-size:15px;font-weight:900;flex:1}
a.back{background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:6px;padding:5px 14px;font-family:'Cairo',sans-serif;font-size:12px;text-decoration:none}
.main{padding:24px;max-width:600px;margin:0 auto}
.flash{padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:14px;font-weight:600}
.flash.error{background:#fdecea;border:1px solid #e57373;color:var(--red)}
.flash.success{background:#e8f5e9;border:1px solid #81c784;color:#2e7d32}
.card{background:var(--white);border:1.5px solid var(--border);border-radius:12px;padding:24px;margin-bottom:20px}
.card h2{font-size:15px;font-weight:900;color:var(--accent2);margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid var(--border)}
.field{margin-bottom:14px}
.field label{display:block;font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px}
.field input{width:100%;background:var(--bg);border:1.5px solid var(--border);border-radius:7px;color:var(--text);font-family:'Cairo',sans-serif;font-size:13px;padding:9px 12px;outline:none;height:38px}
.field input:focus{border-color:var(--accent)}
.btn-primary{background:var(--green);color:#fff;border:none;border-radius:7px;font-family:'Cairo',sans-serif;font-size:13px;font-weight:700;padding:10px;cursor:pointer;width:100%;margin-top:4px}
.btn-primary:hover{background:#219a52}
.stat-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.stat-box{background:var(--topbar);border-radius:8px;padding:14px;text-align:center;color:#fff}
.stat-val{font-size:28px;font-weight:900}
.stat-label{font-size:11px;opacity:.85;margin-top:4px}
</style></head><body>
<div class="topbar"><a href="/" class="back">← رجوع</a><h1>👤 الملف الشخصي</h1></div>
<div class="main">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat,msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
  {% endwith %}
  <div class="card">
    <h2>📊 إحصائياتي</h2>
    <div class="stat-row">
      <div class="stat-box"><div class="stat-val">{{ total_added }}</div><div class="stat-label">حجز أضفته</div></div>
      <div class="stat-box" style="background:var(--accent2);"><div class="stat-val">{{ 'مسؤول' if role=='admin' else 'مستخدم' }}</div><div class="stat-label">{{ user }}</div></div>
    </div>
  </div>
  <div class="card">
    <h2>🔒 تغيير كلمة المرور</h2>
    <form method="POST" action="/profile">
      <div class="field"><label>كلمة المرور الحالية</label><input type="password" name="old_password" required placeholder="••••••••"></div>
      <div class="field"><label>كلمة المرور الجديدة</label><input type="password" name="new_password" required placeholder="6 أحرف على الأقل"></div>
      <div class="field"><label>تأكيد كلمة المرور الجديدة</label><input type="password" name="confirm_password" required placeholder="••••••••"></div>
      <button type="submit" class="btn-primary">✔ حفظ كلمة المرور الجديدة</button>
    </form>
  </div>
</div></body></html>"""

REPORT_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>تقرير النشاط</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#e8f0ee;--topbar:#5a8a7a;--accent:#3d7a6a;--accent2:#2d6a5a;--text:#1a2e28;--muted:#5a7a72;--border:#a8c8c0;--white:#fff;--thead:#5a8a7a}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;direction:rtl}
.topbar{background:var(--topbar);color:#fff;padding:0 16px;display:flex;align-items:center;gap:12px;height:44px;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.topbar h1{font-size:15px;font-weight:900;flex:1}
a.back{background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:6px;padding:5px 14px;font-family:'Cairo',sans-serif;font-size:12px;text-decoration:none}
a.export-btn{background:#27ae60;border:none;color:#fff;border-radius:6px;padding:5px 14px;font-family:'Cairo',sans-serif;font-size:12px;text-decoration:none;font-weight:700}
.main{padding:20px;max-width:1200px;margin:0 auto}
.card{background:var(--white);border:1.5px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:20px}
.card-header{background:var(--topbar);padding:12px 18px;color:#fff;font-size:14px;font-weight:900}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{background:var(--thead);color:#fff;padding:9px 12px;text-align:center;font-size:11px;letter-spacing:.3px;border-left:1px solid rgba(255,255,255,.1)}
thead th:last-child{border-left:none}
tbody tr:nth-child(even){background:#f0f7f5}
tbody td{padding:9px 12px;text-align:center;border-bottom:1px solid var(--border)}
tbody tr:last-child td{border-bottom:none}
.bar{height:16px;background:var(--accent);border-radius:3px;display:inline-block;min-width:4px;transition:width .3s}
.user-tag{background:var(--accent);color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700}
</style></head><body>
<div class="topbar">
  <a href="/" class="back">← رجوع</a>
  <h1>📊 تقرير النشاط — نظام الحجز</h1>
  <a href="/report/export" class="export-btn">📥 تصدير Excel</a>
  <a href="/admin/clean_empty_salle" class="export-btn" style="background:#c0392b;margin-right:8px;"
     onclick="return confirm('حذف كل السجلات بدون قاعة؟')">🗑️ حذف السجلات الفارغة</a>
  <a href="/admin/fix_etage_type" class="export-btn" style="background:#2471a3;margin-right:8px;">🔧 إصلاح الطابق/النوع</a>
</div>
<div class="main">
  <div class="card">
    <div class="card-header">👥 ملخص النشاط حسب المستخدم</div>
    <table>
      <thead><tr>
        <th>المستخدم</th><th>الإجمالي</th><th>رجال</th><th>نساء</th><th>مختلط</th>
        <th>صباحي</th><th>مسائي</th><th>أول حجز</th><th>آخر حجز</th><th>نسبة</th>
      </tr></thead>
      <tbody>
      {% set grand_total = users_stats|sum(attribute=1) %}
      {% for u in users_stats %}
      {% set pct = (u[1] / grand_total * 100)|round(1) if grand_total else 0 %}
      <tr>
        <td><span class="user-tag">{{ u[0] or '—' }}</span></td>
        <td><strong>{{ u[1] }}</strong></td>
        <td>{{ u[2] }}</td><td>{{ u[3] }}</td><td>{{ u[4] }}</td>
        <td>{{ u[5] }}</td><td>{{ u[6] }}</td>
        <td style="font-size:11px;color:var(--muted);">{{ u[7] or '—' }}</td>
        <td style="font-size:11px;color:var(--muted);">{{ u[8] or '—' }}</td>
        <td>
          <div style="display:flex;align-items:center;gap:6px;">
            <div class="bar" style="width:{{ [pct*2,100]|min }}px;"></div>
            <span style="font-size:11px;">{{ pct }}%</span>
          </div>
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>

  <div class="card">
    <div class="card-header">🕐 آخر 50 حجز مضافة</div>
    <table>
      <thead><tr>
        <th>المستخدم</th><th>ID</th><th>رقم الدورة</th><th>العنوان</th>
        <th>القاعة</th><th>البداية</th><th>تاريخ الإضافة</th>
      </tr></thead>
      <tbody>
      {% for r in recent %}
      <tr>
        <td><span class="user-tag">{{ r[0] or '—' }}</span></td>
        <td style="color:var(--muted);font-size:11px;">{{ r[1] }}</td>
        <td><strong>{{ r[2] or '—' }}</strong></td>
        <td>{{ r[3] or '—' }}</td>
        <td><strong>{{ r[4] or '—' }}</strong></td>
        <td>{{ r[5] or '—' }}</td>
        <td style="font-size:11px;color:var(--muted);">{{ r[6] or '—' }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</div></body></html>"""

INDEX_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>حجز القاعات</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#e8f0ee;--sidebar:#c8ddd8;--topbar:#5a8a7a;--topbar2:#4a7a6a;
  --accent:#3d7a6a;--accent2:#2d6a5a;--red:#c0392b;--green:#27ae60;
  --text:#1a2e28;--muted:#5a7a72;--border:#a8c8c0;--white:#ffffff;
  --row-even:#f0f7f5;--row-hover:#d8ede8;--row-sel:#ffd5d0;
  --thead:#5a8a7a;--chip-bg:#3d7a6a;
}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;direction:rtl;overflow-x:hidden}

/* ── TOPBAR ── */
.topbar{background:var(--topbar);color:#fff;padding:0 14px;display:flex;align-items:center;gap:10px;height:44px;position:fixed;top:0;left:0;right:0;z-index:200;box-shadow:0 2px 8px rgba(0,0,0,.2)}
.brand{font-size:16px;font-weight:900;white-space:nowrap;color:#fff;letter-spacing:.5px}
.topbar-center{display:flex;gap:4px;margin:0 auto}
.tab{background:rgba(255,255,255,.15);border:none;color:#fff;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;padding:5px 14px;border-radius:6px;cursor:pointer;transition:all .2s;text-decoration:none;display:inline-block;white-space:nowrap}
.tab:hover{background:rgba(255,255,255,.25)}
.tab.active{background:var(--white);color:var(--accent2);font-weight:900}
.topbar-right{display:flex;align-items:center;gap:6px}
.notif-btn{position:relative;background:rgba(255,255,255,.2);border:none;color:#fff;border-radius:6px;width:32px;height:32px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:16px;transition:background .2s}
.notif-btn:hover{background:rgba(255,255,255,.3)}
.notif-badge{position:absolute;top:-3px;left:-3px;background:var(--red);color:#fff;border-radius:8px;font-size:9px;font-weight:700;padding:1px 4px;display:none}
.user-chip{display:flex;align-items:center;gap:5px;background:rgba(255,255,255,.2);border-radius:6px;padding:4px 10px;font-size:12px;font-weight:700;color:#fff;white-space:nowrap}
.role-badge{font-size:9px;padding:1px 5px;border-radius:4px;font-weight:700;background:rgba(255,255,255,.3)}
a.logout{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:6px;padding:4px 10px;font-family:'Cairo',sans-serif;font-size:11px;text-decoration:none;transition:all .2s;white-space:nowrap}
a.logout:hover{background:rgba(255,255,255,.25)}

/* ── LAYOUT ── */
.layout{display:flex;padding-top:44px;min-height:100vh}

/* ── SIDEBAR ── */
.sidebar{position:fixed;top:44px;right:0;bottom:0;width:260px;background:var(--sidebar);border-left:2px solid var(--border);overflow-y:auto;z-index:150;transition:transform .3s ease;display:flex;flex-direction:column}
.sidebar.collapsed{transform:translateX(100%)}
.sidebar-inner{padding:12px;flex:1}

/* ── SIDEBAR ── */
.sidebar{position:fixed;top:44px;right:0;bottom:0;width:300px;background:var(--sidebar);border-left:2px solid var(--border);overflow-y:auto;z-index:150;transition:transform .3s ease;display:flex;flex-direction:column}
.sidebar.collapsed{transform:translateX(100%)}
.sidebar-inner{padding:12px;flex:1}

/* STATS */
.stats-row{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:12px}
.stat{background:var(--topbar);border-radius:8px;padding:8px 4px;text-align:center;color:#fff}
.stat-val{font-size:18px;font-weight:900;line-height:1}
.stat-label{font-size:9px;opacity:.85;margin-top:2px}

/* SECTION TITLE */
.sec-title{font-size:13px;font-weight:900;color:var(--accent2);margin-bottom:8px;display:flex;align-items:center;gap:6px;border-bottom:2px solid var(--border);padding-bottom:6px}

/* FIELDS */
.field{margin-bottom:8px}
.field label{display:block;font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:3px}
.field input,.field select{width:100%;background:var(--white);border:1.5px solid var(--border);border-radius:6px;color:var(--text);font-family:'Cairo',sans-serif;font-size:12px;padding:6px 9px;outline:none;height:32px;transition:border-color .2s}
.field input[type="date"]{font-size:11px;padding:4px 6px}
.field input:focus,.field select:focus{border-color:var(--accent)}
.field select option{background:var(--white)}

/* SALLE GRID */
.salle-grid-label{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;display:block}
.salle-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:5px;margin-bottom:10px;max-height:160px;overflow-y:auto;padding:2px}
.salle-btn{background:var(--white);border:1.5px solid var(--border);border-radius:6px;padding:5px 2px;font-family:'Cairo',sans-serif;font-size:11px;font-weight:700;cursor:pointer;transition:all .15s;color:var(--text);text-align:center}
.salle-btn:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.salle-btn.active{background:var(--accent);color:#fff;border-color:var(--accent2);box-shadow:0 0 0 2px rgba(61,122,106,.3)}
.salle-btn.reserved{background:#ddd;color:#999;border-color:#ccc;cursor:not-allowed}
.salle-btn.conflict{background:#fdecea;color:#c0392b;border-color:#e57373;}

/* CONFLICT */
.conflict-box{display:none;background:#fdecea;border:1.5px solid #e57373;border-radius:6px;padding:7px 9px;color:#c0392b;font-size:11px;font-weight:600;margin-bottom:8px}
.conflict-box.show{display:block}

/* BUTTONS */
.btn{border:none;border-radius:6px;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;padding:7px 14px;cursor:pointer;transition:all .2s;display:inline-flex;align-items:center;gap:4px;text-decoration:none;white-space:nowrap;justify-content:center}
.btn-save{background:var(--green);color:#fff;width:100%;padding:9px;font-size:13px}
.btn-save:hover{background:#219a52}.btn-save:disabled{opacity:.4;cursor:not-allowed}
.btn-reset{background:#888;color:#fff;width:100%;padding:7px;font-size:12px;margin-top:5px}
.btn-reset:hover{background:#666}
.btn-del{background:var(--red);color:#fff;padding:5px 12px;font-size:11px}
.btn-del:hover{background:#a93226}
.btn-green{background:var(--green);color:#fff;width:100%;padding:8px;margin-bottom:6px}
.btn-green:hover{background:#219a52}
.btn-import{background:var(--topbar);color:#fff;width:100%;padding:8px}
.btn-import:hover{background:var(--accent2)}
.btn-edit{background:var(--accent);color:#fff;width:100%;padding:9px;font-size:13px;display:none}
.btn-edit:hover{background:var(--accent2)}
.btn-cancel{background:#888;color:#fff;width:100%;padding:7px;font-size:12px;margin-top:5px;display:none}

/* FLASH */
.flash{padding:8px 12px;border-radius:6px;font-size:12px;font-weight:600;margin-bottom:8px}
.flash.error{background:#fdecea;border:1px solid #e57373;color:#c0392b}
.flash.success{background:#e8f5e9;border:1px solid #81c784;color:#2e7d32}

/* ── CONTENT ── */
.content{flex:1;margin-right:300px;transition:margin-right .3s ease;min-width:0;padding:10px 12px;overflow-x:auto}
.content.full{margin-right:0}

/* ── SEARCH BAR ── */
.search-bar{background:var(--white);border:1.5px solid var(--border);border-radius:8px;padding:8px 12px;margin-bottom:8px;display:flex;gap:6px;align-items:flex-end;flex-wrap:wrap}
.search-bar input,.search-bar select{background:var(--bg);border:1.5px solid var(--border);border-radius:6px;color:var(--text);font-family:'Cairo',sans-serif;font-size:12px;padding:5px 8px;outline:none;height:32px}
.search-bar input:focus,.search-bar select:focus{border-color:var(--accent)}
.sf{display:flex;flex-direction:column;gap:3px}
.sf label{font-size:9px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.btn-search{background:var(--topbar);color:#fff;border:none;border-radius:6px;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;padding:0 14px;height:32px;cursor:pointer}
.btn-clear{background:#888;color:#fff;border:none;border-radius:6px;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;padding:0 12px;height:32px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}

/* ── TABLE ── */
.table-wrap{background:var(--white);border:1.5px solid var(--border);border-radius:8px;overflow:hidden}
.table-header{background:var(--topbar);padding:10px 16px;display:flex;align-items:center;gap:10px}
.table-header h2{font-size:14px;font-weight:900;color:#fff;flex:1}
.count-badge{background:rgba(255,255,255,.25);color:#fff;border-radius:12px;padding:2px 10px;font-size:11px;font-weight:700}
/* Scrollable table body */
.table-scroll{max-height:calc(100vh - 180px);overflow-y:auto;position:relative}
.table-scroll::-webkit-scrollbar{width:8px}
.table-scroll::-webkit-scrollbar-track{background:#e8f0ee}
.table-scroll::-webkit-scrollbar-thumb{background:var(--topbar);border-radius:4px}
.table-scroll::-webkit-scrollbar-thumb:hover{background:var(--accent2)}
table{width:100%;border-collapse:collapse;font-size:12px}
/* Sticky header */
thead{position:sticky;top:0;z-index:10}
thead th{background:var(--thead);color:#fff;font-weight:700;text-align:center;padding:8px 10px;white-space:nowrap;font-size:11px;letter-spacing:.3px;border-left:1px solid rgba(255,255,255,.1);user-select:none}
thead th.sortable{cursor:pointer}
thead th.sortable:hover{background:var(--accent2)}
thead th .sort-icon{display:inline-block;margin-right:4px;opacity:.5;font-size:10px}
thead th.sort-asc .sort-icon{opacity:1;content:'▲'}
thead th.sort-desc .sort-icon{opacity:1}
thead th:last-child{border-left:none}
tbody tr{cursor:pointer;transition:background .12s}
tbody tr:nth-child(even){background:var(--row-even)}
tbody tr:nth-child(odd){background:var(--white)}
tbody tr:hover{background:var(--row-hover)}
tbody tr.selected-row{background:var(--row-sel)!important}
tbody td{padding:8px 10px;text-align:center;border-bottom:1px solid var(--border);border-left:1px solid var(--border)}
tbody td:last-child{border-left:none}
.chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;color:#fff}
.chip-q{background:#3d7a6a}.chip-lab{background:#c0392b}
.chip-m{background:#2980b9;color:#fff}.chip-f{background:#e67e22;color:#fff}.chip-mix{background:#8e44ad;color:#fff}
.chip-s{background:#27ae60;color:#fff}.chip-e{background:#8e44ad;color:#fff}

/* NOTIF DRAWER */
.notif-drawer{position:fixed;top:44px;left:0;bottom:0;width:320px;background:var(--white);border-right:2px solid var(--border);z-index:999;transform:translateX(-100%);transition:transform .3s ease;display:flex;flex-direction:column}
.notif-drawer.open{transform:translateX(0)}
.notif-drawer-header{padding:14px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;background:var(--topbar);color:#fff}
.notif-drawer-header h2{font-size:14px;font-weight:700}
.notif-close{background:none;border:none;color:#fff;font-size:18px;cursor:pointer}
.notif-list{flex:1;overflow-y:auto;padding:10px}
.notif-item{padding:10px 12px;border-radius:6px;background:var(--row-even);border:1px solid var(--border);margin-bottom:6px;font-size:12px;line-height:1.6}
.notif-item.unread{border-color:var(--accent);background:#e8f5f2}
.notif-time{font-size:10px;color:var(--muted);margin-top:3px}
.notif-mark-btn{margin:10px;background:var(--bg);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:7px;font-family:'Cairo',sans-serif;font-size:12px;cursor:pointer;width:calc(100% - 20px)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:998;display:none}.overlay.show{display:block}

/* CALENDAR */
#calendar-container{background:var(--white);border:1.5px solid var(--border);border-radius:8px;padding:16px}
.fc{--fc-border-color:var(--border);--fc-today-bg-color:rgba(61,122,106,.1)}
.fc .fc-toolbar-title{font-family:'Cairo',sans-serif;font-size:16px;color:var(--text)}
.fc .fc-button{background:var(--topbar)!important;border-color:var(--accent2)!important;color:#fff!important;font-family:'Cairo',sans-serif!important}
.fc .fc-button:hover{background:var(--accent2)!important}
.fc .fc-event{border-radius:4px;border:none!important;font-size:11px;font-family:'Cairo',sans-serif}

.empty-state{padding:40px;text-align:center;color:var(--muted)}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

/* IMPORT ROW */
.import-row{display:flex;flex-direction:column;gap:6px}
.file-input{font-size:11px;color:var(--muted);width:100%}
</style></head><body>

<nav class="topbar">
  <div class="brand">🏛️ حجز القاعات</div>
  <div class="topbar-center">
    <button class="tab active" onclick="switchTab('reservations',this)">الحجوزات</button>
    <button class="tab" onclick="switchTab('calendar',this)">التقويم</button>
    {% if role == 'admin' %}<a href="/register" class="tab">المستخدمون</a>{% endif %}
  </div>
  <div class="topbar-right">
    <button class="notif-btn" onclick="openNotifDrawer()">🔔<span class="notif-badge" id="notif-badge">0</span></button>
    <div class="user-chip">
      <span>{{ user }}</span>
      <span class="role-badge">{{ 'مسؤول' if role=='admin' else 'مستخدم' }}</span>
    </div>
    <a href="/profile" class="logout">👤 ملفي</a>
    {% if role == 'admin' %}<a href="/dashboard" class="logout">📊 لوحة</a>{% endif %}
    {% if role == 'admin' %}<a href="/report" class="logout">📋 تقرير</a>{% endif %}
    <a href="/logout" class="logout">خروج</a>
  </div>
</nav>

<!-- SIDEBAR -->
<div class="sidebar" id="sidebar">
  <div class="sidebar-inner">

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for cat,msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
    {% endwith %}

    <!-- Stats -->
    <div class="stats-row">
      <div class="stat"><div class="stat-val">{{ total_count }}</div><div class="stat-label">الإجمالي</div></div>
      <div class="stat"><div class="stat-val">{{ occupied_today }}</div><div class="stat-label">اليوم</div></div>
      <div class="stat"><div class="stat-val">{{ upcoming_count }}</div><div class="stat-label">الأسبوع</div></div>
    </div>

    <!-- FORM -->
    <div class="sec-title">➕ حجز جديد</div>
    <input type="hidden" id="edit-id" value="">

    <div class="field"><label>رقم الدورة</label><input id="f-course-code" placeholder="مثال: 202501" maxlength="20" style="letter-spacing:1px;"></div>
    <div class="field"><label>العنوان</label><input id="f-titre" placeholder="عنوان الحجز"></div>
    <div class="field"><label>المنظم</label><input id="f-organisateur" placeholder="اسم المنظم"></div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
      <div class="field"><label>نوع النشاط</label>
        <select id="f-level">
          <option value="">—</option>
          <option value="دورة تدريبية">دورة تدريبية</option>
          <option value="ورشة تدريبية">ورشة تدريبية</option>
          <option value="اجتماع">اجتماع</option>
          <option value="لقاء">لقاء</option>
          <option value="ملتقى">ملتقى</option>
          <option value="مؤتمر">مؤتمر</option>
          <option value="أخرى" id="level-other-opt">أخرى...</option>
        </select>
        <input type="text" id="f-level-custom" placeholder="نوع النشاط المخصص" style="display:none;margin-top:4px;"></div>
      <div class="field"><label>الكفاءة</label>
        <select id="f-competance">
          <option value="">—</option>
          <option value="سلوكية">سلوكية</option>
          <option value="قيادية">قيادية</option>
          <option value="فنية">فنية</option>
          <option value="تطويري">تطويري</option>
        </select></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
      <div class="field"><label>الأسلوب</label>
        <select id="f-method">
          <option value="">—</option>
          <option value="نظامي">نظامي</option>
          <option value="عن بعد">عن بعد</option>
          <option value="تطبيقي">تطبيقي</option>
        </select></div>
      <div class="field"><label>الحالة</label>
        <select id="f-status">
          <option value="">—</option>
          <option value="ملغى">ملغى</option>
          <option value="نشط">نشط</option>
          <option value="بالتنفيذ">بالتنفيذ</option>
          <option value="منتهي">منتهي</option>
        </select></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
      <div class="field"><label>الطابق</label>
        <select id="f-etage" onchange="renderSalleGrid()">
          <option value="">اختر</option>
          <option value="الأرضي">الأرضي</option><option value="الأول">الأول</option>
          <option value="الثاني">الثاني</option><option value="الثالث">الثالث</option>
          <option value="الرابع">الرابع</option>
        </select></div>
      <div class="field"><label>النوع</label>
        <select id="f-type" onchange="renderSalleGrid()">
          <option value="">الكل</option><option value="قاعة">قاعة</option><option value="مختبر">مختبر</option>
        </select></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
      <div class="field"><label>الجنس</label>
        <select id="f-genre" onchange="filterSallesByGenre()">
          <option value="">اختر</option><option value="رجال">رجال</option><option value="نساء">نساء</option><option value="مختلط">مختلط</option>
        </select></div>
      <div class="field"><label>الفترة</label>
        <select id="f-periode" onchange="checkConflict()">
          <option value="">اختر</option><option value="صباحي">صباحي</option><option value="مسائي">مسائي</option>
        </select></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
      <div class="field"><label>البداية</label><input type="date" id="f-debut" onchange="checkConflict()"></div>
      <div class="field"><label>النهاية</label><input type="date" id="f-fin" onchange="checkConflict()"></div>
    </div>

    <!-- Salle grid -->
    <span class="salle-grid-label">القاعة
      <span id="salle-selected-label" style="color:var(--accent);font-weight:900;"></span>
      <button type="button" id="btn-clear-salle" onclick="clearSalle()" title="إلغاء تحديد القاعة"
        style="display:none;background:none;border:none;color:#c0392b;cursor:pointer;font-size:13px;margin-right:4px;">✕ إلغاء القاعة</button>
    </span>
    <input type="hidden" id="f-salle" value="">
    <div class="salle-grid" id="salle-grid">
      <span style="color:var(--muted);font-size:11px;grid-column:1/-1;text-align:center;padding:12px;">اختر الطابق أولاً</span>
    </div>

    <div class="conflict-box" id="conflict-box">⚠️ <span id="conflict-text"></span></div>

    <button class="btn btn-save" id="btn-save" onclick="submitForm()">💾 حفظ الحجز</button>
    <button class="btn btn-edit" id="btn-edit" onclick="addToBatch()" style="display:none;">➕ إضافة للدفعة</button>
    <button class="btn btn-reset" onclick="resetForm()">↺ إعادة تعيين</button>
    <button class="btn btn-cancel" id="btn-cancel" onclick="resetForm()" style="display:none;">✕ إلغاء</button>

    <!-- BATCH PANEL -->
    <div id="batch-panel" style="display:none;margin-top:12px;padding:10px;background:rgba(39,174,96,.1);border:1.5px solid #27ae60;border-radius:8px;">
      <div style="font-size:12px;font-weight:700;color:#1e8449;margin-bottom:6px;">
        📦 دفعة معلقة: <span id="batch-count">0</span> تعديل
      </div>
      <div id="batch-list" style="font-size:11px;color:var(--muted);max-height:100px;overflow-y:auto;margin-bottom:8px;line-height:1.8;"></div>
      <button onclick="saveBatch()" style="background:#27ae60;color:#fff;border:none;border-radius:6px;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;padding:8px;width:100%;cursor:pointer;margin-bottom:4px;">✅ حفظ الكل دفعة واحدة</button>
      <button onclick="clearBatch()" style="background:#888;color:#fff;border:none;border-radius:6px;font-family:'Cairo',sans-serif;font-size:12px;padding:6px;width:100%;cursor:pointer;">🗑️ إلغاء الدفعة</button>
    </div>

    <!-- SWAP PANEL -->
    <div style="margin-top:10px;padding:10px;background:rgba(36,113,163,.08);border:1.5px solid #2471a3;border-radius:8px;">
      <div style="font-size:12px;font-weight:700;color:#1a5276;margin-bottom:6px;">🔄 تبادل القاعات</div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:6px;">اختر حجزين من نفس التاريخ لتبادل قاعتيهما</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
        <div><label style="font-size:10px;color:var(--muted);">رقم الدورة 1</label>
          <input type="text" id="swap-id1" placeholder="مثال: 16035" style="width:100%;border:1.5px solid var(--border);border-radius:5px;padding:4px 6px;font-size:12px;background:var(--white);">
        </div>
        <div><label style="font-size:10px;color:var(--muted);">رقم الدورة 2</label>
          <input type="text" id="swap-id2" placeholder="مثال: 16036" style="width:100%;border:1.5px solid var(--border);border-radius:5px;padding:4px 6px;font-size:12px;background:var(--white);">
        </div>
      </div>
      <button onclick="swapSalles()" style="background:#2471a3;color:#fff;border:none;border-radius:6px;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;padding:7px;width:100%;cursor:pointer;">🔄 تبادل القاعتين</button>
      <div id="swap-result" style="margin-top:6px;font-size:11px;display:none;"></div>
    </div>

    <!-- Hidden forms -->
    <form method="POST" action="/" id="form-save" style="display:none">
      <input type="hidden" name="_qs" id="h-qs">
      <input type="hidden" name="course_code" id="h-course-code">
      <input type="hidden" name="titre" id="h-titre">
      <input type="hidden" name="organisateur" id="h-organisateur">
      <input type="hidden" name="etage" id="h-etage">
      <input type="hidden" name="type" id="h-type">
      <input type="hidden" name="genre" id="h-genre">
      <input type="hidden" name="periode" id="h-periode">
      <input type="hidden" name="debut" id="h-debut">
      <input type="hidden" name="fin" id="h-fin">
      <input type="hidden" name="salle" id="h-salle">
      <input type="hidden" name="level" id="h-level">
      <input type="hidden" name="competance" id="h-competance">
      <input type="hidden" name="method" id="h-method">
      <input type="hidden" name="registred" id="h-registred">
      <input type="hidden" name="status" id="h-status">
    </form>
    <form method="POST" action="/update" id="form-edit" style="display:none">
      <input type="hidden" name="_qs" id="he-qs">
      <input type="hidden" name="id" id="he-id">
      <input type="hidden" name="course_code" id="he-course-code">
      <input type="hidden" name="titre" id="he-titre">
      <input type="hidden" name="organisateur" id="he-organisateur">
      <input type="hidden" name="etage" id="he-etage">
      <input type="hidden" name="type" id="he-type">
      <input type="hidden" name="genre" id="he-genre">
      <input type="hidden" name="periode" id="he-periode">
      <input type="hidden" name="debut" id="he-debut">
      <input type="hidden" name="fin" id="he-fin">
      <input type="hidden" name="salle" id="he-salle">
      <input type="hidden" name="level" id="he-level">
      <input type="hidden" name="competance" id="he-competance">
      <input type="hidden" name="method" id="he-method">
      <input type="hidden" name="registred" id="he-registred">
      <input type="hidden" name="status" id="he-status">
    </form>

    <div style="margin-top:10px;padding-top:10px;border-top:1.5px solid var(--border);">
      <a href="/export" class="btn btn-green">📥 تصدير إكسل</a>
      <div class="import-row">
        <form action="/import" method="POST" enctype="multipart/form-data">
          <input type="file" name="file" accept=".xlsx,.xls" class="file-input">
          <button type="submit" class="btn btn-import" style="margin-top:5px;">📤 استيراد إكسل</button>
        </form>
      </div>
    </div>

  </div>
</div>

<!-- MAIN CONTENT -->
<div class="layout">
  <div class="content" id="content">

    <!-- RESERVATIONS PANEL -->
    <div id="panel-reservations" style="display:block;">

      <form method="GET" class="search-bar">
        <div class="sf" style="flex:1;min-width:140px;"><label>بحث</label><input type="text" name="search" placeholder="رقم الدورة، عنوان، قاعة..." value="{{ search }}" style="width:100%;"></div>
        <div class="sf"><label>رقم الدورة</label><input type="text" name="dore_f" placeholder="رقم الدورة" value="{{ request.args.get('dore_f','') }}" style="width:110px;"></div>
        <div class="sf"><label>الطابق</label><select name="f_etage">
          <option value="">الكل</option>
          <option value="الأرضي" {% if f_etage=='الأرضي' %}selected{% endif %}>الأرضي</option>
          <option value="الأول" {% if f_etage=='الأول' %}selected{% endif %}>الأول</option>
          <option value="الثاني" {% if f_etage=='الثاني' %}selected{% endif %}>الثاني</option>
          <option value="الثالث" {% if f_etage=='الثالث' %}selected{% endif %}>الثالث</option>
          <option value="الرابع" {% if f_etage=='الرابع' %}selected{% endif %}>الرابع</option>
        </select></div>
        <div class="sf"><label>النوع</label><select name="f_type">
          <option value="">الكل</option><option value="قاعة" {% if f_type=='قاعة' %}selected{% endif %}>قاعة</option>
          <option value="مختبر" {% if f_type=='مختبر' %}selected{% endif %}>مختبر</option>
        </select></div>
        <div class="sf"><label>الجنس</label><select name="f_genre">
          <option value="">الكل</option><option value="رجال" {% if f_genre=='رجال' %}selected{% endif %}>رجال</option>
          <option value="نساء" {% if f_genre=='نساء' %}selected{% endif %}>نساء</option>
          <option value="مختلط" {% if f_genre=='مختلط' %}selected{% endif %}>مختلط</option>
        </select></div>
        <div class="sf"><label>الفترة</label><select name="f_periode">
          <option value="">الكل</option><option value="صباحي" {% if f_periode=='صباحي' %}selected{% endif %}>صباحي</option>
          <option value="مسائي" {% if f_periode=='مسائي' %}selected{% endif %}>مسائي</option>
        </select></div>
        <div class="sf"><label>من</label><input type="date" name="f_debut" value="{{ f_debut }}"></div>
        <div class="sf"><label>إلى</label><input type="date" name="f_fin" value="{{ f_fin }}"></div>
        <button type="submit" class="btn-search">بحث</button>
        <a href="/" class="btn-clear">مسح</a>
      </form>

      <div class="table-wrap">
        <div class="table-header">
          <h2>قائمة الحجوزات</h2>
          <span class="count-badge" id="row-count">{{ data|length }} حجز</span>
          <button type="button" class="btn btn-del" onclick="deleteSelected()">حذف المحدد</button>
        </div>
        {% if data %}
        <div class="table-scroll">
        <table id="table"><thead><tr>
          <th><input type="checkbox" id="select-all" onchange="toggleAll(this)"></th>
          <th class="sortable" onclick="sortTable(1)"><span class="sort-icon" id="si-1">⇅</span>ID</th>
          <th class="sortable" onclick="sortTable(2)"><span class="sort-icon" id="si-2">⇅</span>رقم الدورة</th>
          <th class="sortable" onclick="sortTable(3)"><span class="sort-icon" id="si-3">⇅</span>النوع</th>
          <th class="sortable" onclick="sortTable(4)" style="min-width:70px;"><span class="sort-icon" id="si-4">⇅</span>الطابق</th>
          <th class="sortable" onclick="sortTable(5)" style="min-width:70px;"><span class="sort-icon" id="si-5">⇅</span>القاعة</th>
          <th class="sortable" onclick="sortTable(6)"><span class="sort-icon" id="si-6">⇅</span>الجنس</th>
          <th class="sortable" onclick="sortTable(7)"><span class="sort-icon" id="si-7">⇅</span>الفترة</th>
          <th class="sortable" onclick="sortTable(8)"><span class="sort-icon" id="si-8">⇅</span>البداية</th>
          <th class="sortable" onclick="sortTable(9)"><span class="sort-icon" id="si-9">⇅</span>النهاية</th>
          <th class="sortable" onclick="sortTable(10)"><span class="sort-icon" id="si-10">⇅</span>العنوان</th>
          <th class="sortable" onclick="sortTable(11)"><span class="sort-icon" id="si-11">⇅</span>المنظم</th>
          <th class="sortable" onclick="sortTable(12)"><span class="sort-icon" id="si-12">⇅</span>نوع النشاط</th>
          <th class="sortable" onclick="sortTable(13)"><span class="sort-icon" id="si-13">⇅</span>الكفاءة</th>
          <th class="sortable" onclick="sortTable(14)"><span class="sort-icon" id="si-14">⇅</span>الأسلوب</th>
          <th class="sortable" onclick="sortTable(15)"><span class="sort-icon" id="si-15">⇅</span>الحالة</th>
        </tr></thead><tbody id="tbody">
        {% for r in data %}
        <tr onclick="fillForm({{ r[0] }})" data-id="{{ r[0] }}"
            data-course-code="{{ r[1]|e }}"
            data-type="{{ r[2]|e }}"
            data-etage="{{ r[3]|e }}"
            data-salle="{{ r[4]|e }}"
            data-genre="{{ r[5]|e }}"
            data-periode="{{ r[6]|e }}"
            data-debut="{{ r[7]|e }}"
            data-fin="{{ r[8]|e }}"
            data-titre="{{ r[9]|e }}"
            data-organisateur="{{ r[10]|e }}"
            data-level="{{ r[11]|e if r[11] else '' }}"
            data-competance="{{ r[12]|e if r[12] else '' }}"
            data-method="{{ r[13]|e if r[13] else '' }}"
            data-status="{{ r[15]|e if r[15] else '' }}"
            data-created-by="{{ r[16]|e if r[16] else '' }}">
          <td onclick="event.stopPropagation()">
            <input type="checkbox" class="row-check" value="{{ r[0] }}"
              {% if role != 'admin' and (not r[16] or r[16] != user) %}disabled title="لا يمكنك حذف هذا الحجز"{% endif %}>
          </td>
          <td style="color:var(--muted);font-size:11px;">{{ r[0] }}</td>
          <td><strong>{{ r[1] }}</strong></td>
          <td><span class="chip {% if r[2]=='قاعة' %}chip-q{% else %}chip-lab{% endif %}">{{ r[2] }}</span></td>
          <td style="font-size:11px;color:var(--muted);white-space:nowrap;">{{ r[3] }}</td>
          <td style="white-space:nowrap;">
            <strong style="color:var(--accent2);">{{ r[4] }}</strong>
            {% if r[4] and (role=='admin' or r[16]==user) %}
            <button onclick="event.stopPropagation();clearSalleFromRow({{ r[0] }},this)" title="إلغاء القاعة"
              style="background:none;border:none;color:#c0392b;cursor:pointer;font-size:11px;margin-right:2px;">✕</button>
            {% endif %}
          </td>
          <td><span class="chip {% if r[5]=='رجال' %}chip-m{% elif r[5]=='مختلط' %}chip-mix{% else %}chip-f{% endif %}">{{ r[5] }}</span></td>
          <td><span class="chip {% if r[6]=='صباحي' %}chip-s{% else %}chip-e{% endif %}">{{ r[6] }}</span></td>
          <td>{{ r[7] }}</td><td>{{ r[8] }}</td><td>{{ r[9] }}</td>
          <td style="color:var(--muted);">{{ r[10] }}</td>
          <td style="font-size:11px;">{{ r[11] or '' }}</td>
          <td style="font-size:11px;">{{ r[12] or '' }}</td>
          <td style="font-size:11px;">{{ r[13] or '' }}</td>
          <td style="font-size:11px;">
            {% if r[15] %}
            <span class="chip {% if r[15]=='ملغى' %}chip-lab{% elif r[15]=='نشط' %}chip-s{% elif r[15]=='بالتنفيذ' %}chip-mix{% else %}chip-m{% endif %}">{{ r[15] }}</span>
            {% endif %}
          </td>
        </tr>
        {% endfor %}
        </tbody></table>
        </div><!-- /table-scroll -->
        {% else %}<div class="empty-state">📭 لا توجد حجوزات مطابقة</div>{% endif %}
      </div>
    </div>

    <!-- CALENDAR PANEL -->
    <div id="panel-calendar" style="display:none;">
      <div id="gantt-root"></div>
    </div>

  </div>
</div>

<!-- NOTIF DRAWER -->
<div class="overlay" id="overlay" onclick="closeNotifDrawer()"></div>
<div class="notif-drawer" id="notif-drawer">
  <div class="notif-drawer-header"><h2>🔔 الإشعارات</h2><button class="notif-close" onclick="closeNotifDrawer()">✕</button></div>
  <button class="notif-mark-btn" onclick="markAllRead()">تعليم الكل كمقروء</button>
  <div class="notif-list" id="notif-list"></div>
</div>

<script>
// ══════════════════════════════════════════════════════════════════
//  GANTT CHART — Salles vs Jours ouvrables (Dim→Jeu, sans Ven/Sam)
// ══════════════════════════════════════════════════════════════════

const GANTT_SALLES = {{ salles|tojson }};
let ganttEvents   = [];
let ganttYear     = new Date().getFullYear();
let ganttMonth    = new Date().getMonth(); // 0-based
let ganttView     = 'month'; // 'month' | 'week' | 'list'
let ganttFloor    = '';
let ganttPeriode  = ''; // '' | 'صباحي' | 'مسائي'
let ganttInited   = false;

// ── helpers ───────────────────────────────────────────────────────
// JS getDay(): 0=Sun,1=Mon,2=Tue,3=Wed,4=Thu,5=Fri,6=Sat
// Working days: Sun(0) Mon(1) Tue(2) Wed(3) Thu(4)  — Fri(5) Sat(6) = weekend
function isWorkday(d){ const w=d.getDay(); return w!==5 && w!==6; }
function isWeekend(d){ const w=d.getDay(); return w===5 || w===6; }

function dateStr(d){
  // Use local date to avoid UTC offset shifting the day
  let y=d.getFullYear(), m=String(d.getMonth()+1).padStart(2,'0'), dd=String(d.getDate()).padStart(2,'0');
  return `${y}-${m}-${dd}`;
}
function parseDate(s){
  // Parse as local date (NOT UTC) to avoid off-by-one
  const [y,m,dd]=s.split('-');
  return new Date(+y, +m-1, +dd);
}

function allDaysInRange(start, end){
  let days=[], d=new Date(start.getFullYear(), start.getMonth(), start.getDate());
  let e=new Date(end.getFullYear(), end.getMonth(), end.getDate());
  while(d<=e){ days.push(dateStr(d)); d.setDate(d.getDate()+1); }
  return days;
}

function workdaysInRange(start, end){
  let days=[], d=new Date(start.getFullYear(), start.getMonth(), start.getDate());
  let e=new Date(end.getFullYear(), end.getMonth(), end.getDate());
  while(d<=e){
    let w=d.getDay(); // 0=Sun,1=Mon,2=Tue,3=Wed,4=Thu,5=Fri,6=Sat
    if(w!==5 && w!==6) days.push(dateStr(d)); // exclude only Fri+Sat
    d.setDate(d.getDate()+1);
  }
  return days;
}

function getViewDays(){
  if(ganttView==='month'){
    let start=new Date(ganttYear, ganttMonth, 1);
    let end  =new Date(ganttYear, ganttMonth+1, 0);
    return allDaysInRange(start, end);
  } else {
    let now=new Date(ganttYear, ganttMonth, 1);
    while(now.getDay()!==0) now.setDate(now.getDate()+1);
    let end=new Date(now.getFullYear(), now.getMonth(), now.getDate()+6);
    return allDaysInRange(now, end);
  }
}

function monthName(m){
  return ['يناير','فبراير','مارس','أبريل','مايو','يونيو',
          'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'][m];
}

// ── colors: red=occupied, green=free ─────────────────────────────
const COLOR_OCC  = {bg:'#c0392b', border:'#922b21'}; // occupied
const COLOR_FREE = {bg:'transparent', border:'transparent'}; // free cell

// ── tooltip ───────────────────────────────────────────────────────
function showTooltipMulti(e, evList){
  let tip = document.getElementById('gantt-tip');
  let html = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
    <strong style="font-size:12px;color:#1a2e28;">${evList[0]?.salle||''}</strong>
    <button onclick="hideTooltip();activeTooltipId=null;" style="background:none;border:none;cursor:pointer;font-size:16px;color:#888;">✕</button>
  </div>`;

  evList.forEach((ev, i)=>{
    if(i>0) html += `<hr style="border:none;border-top:1px solid #e0e0e0;margin:8px 0;">`;
    html += `<div style="display:grid;grid-template-columns:auto 1fr;gap:2px 10px;font-size:12px;color:#333;">
      <span style="color:#888;">رقم الدورة</span><span><b>${ev.course_code||'—'}</b></span>
      <span style="color:#888;">العنوان</span><span>${ev.titre||'—'}</span>
      <span style="color:#888;">المنظم</span><span>${ev.organisateur||'—'}</span>
      <span style="color:#888;">الجنس</span><span>${ev.genre}</span>
      <span style="color:#888;">الفترة</span><span><b>${ev.periode}</b></span>
      <span style="color:#888;">من</span><span>${ev.date_debut} → ${ev.date_fin}</span>
    </div>`;
  });

  tip.innerHTML = html;
  tip.style.display = 'block';
  positionTip(e);
}

function showTooltip(e, ev){
  showTooltipMulti(e, [ev]);
}
function positionTip(e){
  let tip=document.getElementById('gantt-tip');
  let x=e.clientX+12, y=e.clientY+12;
  if(x+260>window.innerWidth) x=e.clientX-270;
  if(y+200>window.innerHeight) y=e.clientY-210;
  tip.style.left=x+'px'; tip.style.top=y+'px';
}
function hideTooltip(){ document.getElementById('gantt-tip').style.display='none'; }

// ── colors ────────────────────────────────────────────────────────
function barColor(genre, periode){
  if(genre==='نساء') return {bg:'#c0392b'};
  if(genre==='مختلط') return {bg:'#8e44ad'};
  if(periode==='مسائي') return {bg:'#2471a3'};
  return {bg:'#1e8449'};
}

// ── MAIN RENDER ───────────────────────────────────────────────────
function renderGantt(){
  let days = getViewDays();
  if(!days.length){ document.getElementById('gantt-root').innerHTML='<p style="padding:20px;color:var(--muted)">لا توجد أيام في هذه الفترة</p>'; return; }

  let daySet = new Set(days);

  // Filter salles by floor
  let salles = ganttFloor ? GANTT_SALLES.filter(s=>s.etage===ganttFloor) : GANTT_SALLES;

  // Filter events by periode if selected
  let filteredEvents = ganttPeriode
    ? ganttEvents.filter(ev=>ev.periode===ganttPeriode)
    : ganttEvents;

  // Build event map: salle → { dayStr → [events] }  (array to detect double bookings)
  let evMap = {};
  for(let ev of filteredEvents){
    if(!ev.date_debut || !ev.date_fin) continue;
    let start=parseDate(ev.date_debut), end=parseDate(ev.date_fin);
    for(let ds of workdaysInRange(start, end)){
      if(!daySet.has(ds)) continue;
      if(!evMap[ev.salle]) evMap[ev.salle]={};
      if(!evMap[ev.salle][ds]) evMap[ev.salle][ds]=[];
      evMap[ev.salle][ds].push(ev);
    }
  }

  let periodLabel = ganttView==='month'
    ? `شهر ${monthName(ganttMonth)} ${ganttYear}`
    : `أسبوع ${days[0]} ← ${days[days.length-1]}`;

  let revDays = [...days].reverse();
  let CELL=32, LABEL=80;

  const dowMap={0:'أح',1:'إث',2:'ثل',3:'أر',4:'خم',5:'ج',6:'س'};

  let html = `
  <div style="background:var(--white);border:1.5px solid var(--border);border-radius:8px;overflow:hidden;font-family:'Cairo',sans-serif;">

    <!-- Toolbar -->
    <div style="background:var(--topbar);padding:10px 16px;display:flex;align-items:center;gap:8px;color:#fff;flex-wrap:wrap;">
      <button onclick="ganttNav(-1)" style="background:rgba(255,255,255,.2);border:none;color:#fff;border-radius:6px;padding:4px 12px;cursor:pointer;font-family:'Cairo',sans-serif;font-size:13px;">◀</button>
      <span style="font-weight:900;font-size:15px;flex:1;text-align:center;">${periodLabel}</span>
      <button onclick="ganttNav(1)"  style="background:rgba(255,255,255,.2);border:none;color:#fff;border-radius:6px;padding:4px 12px;cursor:pointer;font-family:'Cairo',sans-serif;font-size:13px;">▶</button>

      <button onclick="setGanttView('list')"  style="background:${ganttView==='list' ?'#fff':'rgba(255,255,255,.2)'};color:${ganttView==='list' ?'var(--accent2)':'#fff'};border:none;border-radius:6px;padding:4px 12px;cursor:pointer;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;">list</button>
      <button onclick="setGanttView('week')"  style="background:${ganttView==='week' ?'#fff':'rgba(255,255,255,.2)'};color:${ganttView==='week' ?'var(--accent2)':'#fff'};border:none;border-radius:6px;padding:4px 12px;cursor:pointer;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;">week</button>
      <button onclick="setGanttView('month')" style="background:${ganttView==='month'?'#fff':'rgba(255,255,255,.2)'};color:${ganttView==='month'?'var(--accent2)':'#fff'};border:none;border-radius:6px;padding:4px 12px;cursor:pointer;font-family:'Cairo',sans-serif;font-size:12px;font-weight:700;">month</button>

      <select onchange="ganttFloor=this.value;renderGantt()" style="background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:6px;padding:4px 8px;font-family:'Cairo',sans-serif;font-size:12px;">
        <option value="" style="color:#000" ${!ganttFloor?'selected':''}>كل الطوابق</option>
        <option value="الأرضي" style="color:#000" ${ganttFloor==='الأرضي'?'selected':''}>الأرضي</option>
        <option value="الأول"  style="color:#000" ${ganttFloor==='الأول' ?'selected':''}>الأول</option>
        <option value="الثاني" style="color:#000" ${ganttFloor==='الثاني'?'selected':''}>الثاني</option>
        <option value="الثالث" style="color:#000" ${ganttFloor==='الثالث'?'selected':''}>الثالث</option>
        <option value="الرابع" style="color:#000" ${ganttFloor==='الرابع'?'selected':''}>الرابع</option>
      </select>

      <select onchange="ganttPeriode=this.value;renderGantt()" style="background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);color:#fff;border-radius:6px;padding:4px 8px;font-family:'Cairo',sans-serif;font-size:12px;">
        <option value=""       style="color:#000" ${!ganttPeriode?'selected':''}>الكل (ص+م)</option>
        <option value="صباحي"  style="color:#000" ${ganttPeriode==='صباحي'?'selected':''}>صباحي فقط</option>
        <option value="مسائي"  style="color:#000" ${ganttPeriode==='مسائي'?'selected':''}>مسائي فقط</option>
      </select>
    </div>

    ${ganttView==='list' ? renderGanttList(filteredEvents) : `
    <!-- Grid -->
    <div style="overflow-x:auto;overflow-y:auto;max-height:calc(100vh - 160px);">
    <table style="border-collapse:collapse;font-size:11px;direction:rtl;">
      <thead style="position:sticky;top:0;z-index:3;">
        <tr>
          <th style="position:sticky;right:0;background:var(--thead);color:#fff;padding:6px 10px;text-align:center;min-width:${LABEL}px;z-index:4;border-left:1px solid rgba(255,255,255,.1);">القاعة</th>
          ${revDays.map(d=>{
            let dt=parseDate(d);
            let day=dt.getDate();
            let dow=dowMap[dt.getDay()]||'';
            let isToday = d===dateStr(new Date());
            let isWE = isWeekend(dt);
            let thBg = isToday ? '#1a5c4a' : isWE ? '#8a8078' : 'var(--thead)';
            return `<th style="background:${thBg};color:${isWE?'#ddd':'#fff'};padding:4px 2px;text-align:center;min-width:${CELL}px;max-width:${CELL}px;border-left:1px solid rgba(255,255,255,.1);">
              <div style="font-size:9px;opacity:.85;">${dow}</div>
              <div style="font-weight:900;font-size:11px;">${day}</div>
            </th>`;
          }).join('')}
        </tr>
      </thead>
      <tbody>
        ${salles.map((s,si)=>{
          let sEv = evMap[s.nom] || {};
          let rowBg = si%2===0 ? 'var(--row-even)' : 'var(--white)';
          return `<tr>
            <td style="position:sticky;right:0;background:${rowBg};font-weight:700;padding:4px 8px;text-align:center;border-bottom:1px solid var(--border);border-left:1px solid var(--border);z-index:1;font-size:11px;white-space:nowrap;">${s.nom}</td>
            ${revDays.map(d=>{
              let dt=parseDate(d);
              let isWE=isWeekend(dt);
              let isToday=d===dateStr(new Date());
              let ev=sEv[d];

              if(isWE){
                // Show salle name in grey weekend column for easy reading
                let isFirstOrLast = (revDays.indexOf(d)===0 || revDays.indexOf(d)===revDays.length-1);
                return `<td style="background:repeating-linear-gradient(45deg,#ccc9c5,#ccc9c5 2px,#dedad6 2px,#dedad6 8px);border-bottom:1px solid var(--border);border-left:1px solid rgba(168,200,192,.3);padding:3px 2px;">
                  <div style="height:20px;display:flex;align-items:center;justify-content:center;font-size:9px;color:#aaa;font-weight:600;">${s.nom}</div>
                </td>`;
              }
              let cellBg = isToday ? 'rgba(45,106,90,.06)' : rowBg;
              let evList = sEv[d] || [];
              if(evList.length > 0){
                let hasMatin = evList.some(e=>e.periode==='صباحي');
                let hasSoir  = evList.some(e=>e.periode==='مسائي');
                let firstEv  = evList[0];
                let evIds    = evList.map(e=>e.id).join(',');

                // 9 distinct user colors — same user always gets same color
                const USER_COLORS = [
                  {base:'#1a3a5c', light:'#5b9bd5', dark:'#0f2240'},  // bleu
                  {base:'#7d2e1e', light:'#e05a40', dark:'#4a1a10'},  // rouge
                  {base:'#1e5e3a', light:'#4caf80', dark:'#0f3020'},  // vert
                  {base:'#5a2d82', light:'#a06cc0', dark:'#3a1a58'},  // violet
                  {base:'#7a5200', light:'#e8a020', dark:'#503600'},  // orange
                  {base:'#1a5c5c', light:'#40b0b0', dark:'#0f3a3a'},  // teal
                  {base:'#7a2060', light:'#d060a0', dark:'#501040'},  // rose
                  {base:'#4a4a00', light:'#a8a820', dark:'#2e2e00'},  // olive
                  {base:'#3a1a00', light:'#a06030', dark:'#201000'},  // brun
                ];

                // Build user→color index from ganttEvents
                let userList = [...new Set(ganttEvents.map(e=>e.created_by||e.organisateur||'').filter(Boolean))];
                let creator = firstEv.created_by || firstEv.organisateur || '';
                let idx = userList.indexOf(creator) % USER_COLORS.length;
                if(idx < 0) idx = 0;
                let uc = USER_COLORS[idx];

                let color, border;
                if(hasMatin && hasSoir){ color=uc.dark;  border=uc.dark; }
                else if(hasSoir)       { color=uc.base;  border=uc.dark; }
                else                   { color=uc.light; border=uc.base; }

                return `<td style="background:${cellBg};border-bottom:1px solid var(--border);border-left:1px solid rgba(168,200,192,.3);padding:3px 2px;">
                  <div style="background:${color};border:1.5px solid ${border};border-radius:4px;height:20px;cursor:pointer;"
                    data-ev-ids="${evIds}"
                    onclick="ganttClick(event,this)">
                  </div>
                </td>`;
              }
              return `<td style="background:${cellBg};border-bottom:1px solid var(--border);border-left:1px solid rgba(168,200,192,.3);padding:3px 2px;">
                <div style="background:#a8d5cb;border-radius:4px;height:20px;opacity:.35;"></div>
              </td>`;
            }).join('')}
          </tr>`;
        }).join('')}
      </tbody>
    </table>
    </div>

    <div style="padding:8px 14px;display:flex;gap:14px;flex-wrap:wrap;font-size:11px;border-top:1px solid var(--border);background:var(--bg);align-items:center;" id="gantt-legend">
      <strong style="color:var(--muted)">الكثافة:</strong>
      <span><span style="display:inline-block;width:14px;height:14px;background:#aaa;border-radius:3px;vertical-align:middle;margin-left:4px;opacity:.6;"></span>صباحي (فاتح)</span>
      <span><span style="display:inline-block;width:14px;height:14px;background:#666;border-radius:3px;vertical-align:middle;margin-left:4px;"></span>مسائي</span>
      <span><span style="display:inline-block;width:14px;height:14px;background:#222;border-radius:3px;vertical-align:middle;margin-left:4px;"></span>ص+م (داكن)</span>
      <span style="border-right:1px solid var(--border);padding-right:10px;"></span>
      <span id="gantt-user-legend"></span>
      <span><span style="display:inline-block;width:14px;height:14px;background:#a8d5cb;opacity:.4;border-radius:3px;vertical-align:middle;margin-left:4px;"></span>متاح</span>
      <span><span style="display:inline-block;width:14px;height:14px;background:repeating-linear-gradient(45deg,#ccc,#ccc 2px,#ddd 2px,#ddd 8px);border-radius:3px;vertical-align:middle;margin-left:4px;"></span>عطلة</span>
    </div>
    `}
  </div>`;

  document.getElementById('gantt-root').innerHTML = html;

  // Build user legend AFTER innerHTML is set (avoids </script> inside template literal)
  const UC=[
    {base:'#1a3a5c'},{base:'#7d2e1e'},{base:'#1e5e3a'},{base:'#5a2d82'},
    {base:'#7a5200'},{base:'#1a5c5c'},{base:'#7a2060'},{base:'#4a4a00'},{base:'#3a1a00'}
  ];
  let users=[...new Set(ganttEvents.map(e=>e.created_by||'').filter(Boolean))];
  let leg=document.getElementById('gantt-user-legend');
  if(leg) leg.innerHTML=users.slice(0,9).map((u,i)=>
    `<span style="margin-left:8px;"><span style="display:inline-block;width:14px;height:14px;background:${UC[i%9].base};border-radius:3px;vertical-align:middle;margin-left:4px;"></span>${u}</span>`
  ).join('');
}

function renderGanttList(events){
  if(!events.length) return '<div style="padding:20px;text-align:center;color:var(--muted)">لا توجد حجوزات</div>';
  // Filter by current month
  let filtered = events.filter(ev=>{
    if(!ev.date_debut) return false;
    let d=parseDate(ev.date_debut);
    return d.getFullYear()===ganttYear && d.getMonth()===ganttMonth;
  }).sort((a,b)=>a.date_debut>b.date_debut?1:-1);

  return `<div style="overflow-y:auto;max-height:calc(100vh - 200px);">
    <table style="width:100%;border-collapse:collapse;font-size:12px;direction:rtl;">
      <thead><tr style="background:var(--thead);color:#fff;">
        <th style="padding:8px 12px;text-align:right;">رقم الدورة</th>
        <th style="padding:8px 12px;text-align:right;">العنوان</th>
        <th style="padding:8px 12px;">القاعة</th>
        <th style="padding:8px 12px;">الجنس</th>
        <th style="padding:8px 12px;">الفترة</th>
        <th style="padding:8px 12px;">البداية</th>
        <th style="padding:8px 12px;">النهاية</th>
        <th style="padding:8px 12px;">المنظم</th>
      </tr></thead>
      <tbody>
      ${filtered.map((ev,i)=>{
        let c=barColor(ev.genre,ev.periode);
        return `<tr style="background:${i%2===0?'var(--row-even)':'var(--white)'}">
          <td style="padding:7px 12px;font-weight:700;color:var(--accent2);">${ev.course_code||'—'}</td>
          <td style="padding:7px 12px;">${ev.titre||'—'}</td>
          <td style="padding:7px 12px;text-align:center;"><strong>${ev.salle}</strong></td>
          <td style="padding:7px 12px;text-align:center;"><span style="background:${c.bg};color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;">${ev.genre}</span></td>
          <td style="padding:7px 12px;text-align:center;">${ev.periode}</td>
          <td style="padding:7px 12px;text-align:center;">${ev.date_debut}</td>
          <td style="padding:7px 12px;text-align:center;">${ev.date_fin}</td>
          <td style="padding:7px 12px;color:var(--muted);">${ev.organisateur||'—'}</td>
        </tr>`;
      }).join('')}
      </tbody>
    </table>
  </div>`;
}

let activeTooltipId = null;

function ganttClick(e, el){
  e.stopPropagation();
  let ids = el.dataset.evIds.split(',').map(Number);
  let evList = ids.map(id=>ganttEvents.find(x=>x.id===id)).filter(Boolean);
  if(!evList.length) return;
  let firstId = ids[0];
  if(activeTooltipId === firstId){
    hideTooltip(); activeTooltipId=null; return;
  }
  activeTooltipId = firstId;
  showTooltipMulti(e, evList);
}

function ganttHover(e, evId){
  let ev = ganttEvents.find(x=>x.id===evId);
  if(ev) showTooltip(e, ev);
}

// Click anywhere else to close tooltip
document.addEventListener('click', function(e){
  let tip = document.getElementById('gantt-tip');
  if(tip && !tip.contains(e.target)){
    hideTooltip();
    activeTooltipId = null;
  }
});

function ganttNav(dir){
  if(ganttView==='month'){
    ganttMonth += dir;
    if(ganttMonth>11){ ganttMonth=0; ganttYear++; }
    if(ganttMonth<0) { ganttMonth=11; ganttYear--; }
  } else {
    // Move by 1 week (5 workdays)
    let days=getViewDays();
    let pivot = dir>0 ? parseDate(days[days.length-1]) : parseDate(days[0]);
    pivot.setDate(pivot.getDate() + dir*7);
    ganttMonth=pivot.getMonth(); ganttYear=pivot.getFullYear();
  }
  renderGantt();
}

function setGanttView(v){ ganttView=v; renderGantt(); }

// ── TAB SWITCHING ─────────────────────────────────────────────────
let calendarInit=false;
function switchTab(tab,btn){
  document.getElementById('panel-reservations').style.display = tab==='reservations'?'block':'none';
  document.getElementById('panel-calendar').style.display     = tab==='calendar'?'block':'none';
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');

  let content = document.getElementById('content');
  let sidebar  = document.getElementById('sidebar');

  if(tab==='calendar'){
    if(sidebar) sidebar.style.transform='translateX(100%)';
    if(content) content.style.marginRight='0';
    fetch('/calendar_events').then(r=>r.json()).then(data=>{
      ganttEvents=data;
      renderGantt();
    });
  } else {
    if(sidebar) sidebar.style.transform='';
    if(content) content.style.marginRight='';
  }
}
</script>
<script>
// ── DATA ──────────────────────────────────────────────────────────
const SALLES = {{ salles|tojson }};
// Salles autorisées par genre
const SALLES_MIX    = new Set(['G 11','G 12','G 13','L1 04','L1 05','L1 08','L1 18','L1 19','L1 20','L1 21','L1 22','L1 26','L2 08','L2 09','L2 10','L2 11','L2 14','L2 28','L2 29','L2 30','L2 31','L2 32','L2 33','L2 34','L2 35']);
const SALLES_FEMALE = new Set(['L3 08','L3 09','L3 10','L3 11','L3 13','L3 27','L3 28','L3 29','L3 30','L3 31','L3 32','L3 33','L3 34','L4 08','L4 09','L4 10','L4 11','L4 14','L4 29','L4 30','L4 31','L4 32','L4 33','L4 34','L4 35','L4 36']);

let currentEditId = null;
let currentEditSalle = '';
let selectedSalle = '';

// ── GENRE → SALLE FILTER ─────────────────────────────────────────
function filterSallesByGenre(){
  let genre = document.getElementById('f-genre').value;
  // Auto-suggest etage based on genre
  let etageEl = document.getElementById('f-etage');
  if(genre === 'مختلط' && !etageEl.value){
    etageEl.value = 'الأرضي';
  } else if(genre === 'نساء' && !etageEl.value){
    etageEl.value = 'الثالث';
  }
  renderSalleGrid(selectedSalle || '');
}

// ── LIVE AUTO-REFRESH ─────────────────────────────────────────────
let lastCount = {{ data|length }};
let liveRefreshActive = true;

async function checkForUpdates(){
  if(!liveRefreshActive) return;
  try {
    let r = await fetch('/live_count');
    let d = await r.json();
    if(d.count !== lastCount){
      lastCount = d.count;
      // Show subtle notification bar instead of full reload
      showLiveAlert(d.count);
    }
  } catch(e){}
}

function showLiveAlert(newCount){
  let bar = document.getElementById('live-alert');
  if(!bar){
    bar = document.createElement('div');
    bar.id = 'live-alert';
    bar.style.cssText = 'position:fixed;top:44px;left:0;right:260px;background:#2e7d32;color:#fff;text-align:center;padding:8px;font-family:Cairo,sans-serif;font-size:13px;font-weight:700;z-index:190;cursor:pointer;transition:all .3s';
    bar.onclick = () => window.location.reload();
    document.body.appendChild(bar);
  }
  bar.textContent = `🔄 تم تحديث البيانات (${newCount} حجز) — انقر للتحديث`;
  bar.style.display = 'block';
}

setInterval(checkForUpdates, 8000); // check every 8 seconds

// ── SALLE GRID ────────────────────────────────────────────────────
function renderSalleGrid(preselect){
  let etage = document.getElementById('f-etage').value;
  let type  = document.getElementById('f-type').value;
  let genre = document.getElementById('f-genre').value;
  let grid  = document.getElementById('salle-grid');
  selectedSalle = preselect || '';
  document.getElementById('f-salle').value = selectedSalle;
  document.getElementById('salle-selected-label').textContent = selectedSalle ? '— '+selectedSalle : '';

  if(!etage){ grid.innerHTML='<span style="color:var(--muted);font-size:11px;grid-column:1/-1;text-align:center;padding:12px;">اختر الطابق أولاً</span>'; return; }

  let filtered = SALLES.filter(s=>{
    if(s.etage !== etage) return false;
    if(type && s.type !== type) return false;
    // Genre restrictions
    if(genre === 'مختلط'){
      // Mix only in ground floor and 1st floor (occasionally 2nd)
      if(s.etage === 'الثالث' || s.etage === 'الرابع') return false;
    }
    if(genre === 'رجال'){
      // Males not in strict female floors
      if(s.etage === 'الثالث' || s.etage === 'الرابع') return false;
    }
    return true;
  });

  if(!filtered.length){ grid.innerHTML='<span style="color:var(--muted);font-size:11px;grid-column:1/-1;text-align:center;padding:10px;">لا توجد قاعات متاحة لهذا الجنس في هذا الطابق</span>'; return; }

  grid.innerHTML = filtered.map(s=>{
    let isActive = s.nom === selectedSalle;
    return `<button type="button" class="salle-btn ${isActive?'active':''}"
      onclick="selectSalle('${s.nom}')">
      ${s.nom}
    </button>`;
  }).join('');
}

function selectSalle(nom){
  selectedSalle = nom;
  document.getElementById('f-salle').value = nom;
  document.getElementById('salle-selected-label').textContent = '— '+nom;
  document.getElementById('btn-clear-salle').style.display = nom ? 'inline' : 'none';
  document.querySelectorAll('.salle-btn').forEach(b=>b.classList.toggle('active', b.textContent.trim()===nom));
  checkConflict();
}

// ── CONFLICT CHECK ─────────────────────────────────────────────────
let ct=null;
function checkConflict(){clearTimeout(ct);ct=setTimeout(_check,350);}
async function _check(){
  let salle   = document.getElementById('f-salle').value;
  let debut   = document.getElementById('f-debut').value;
  let fin     = document.getElementById('f-fin').value;
  let periode = document.getElementById('f-periode').value;
  let box = document.getElementById('conflict-box');
  let saveBtn = document.getElementById('btn-save');
  let editBtn = document.getElementById('btn-edit');
  if(!salle||!debut||!fin||!periode){
    box.classList.remove('show');
    // Reset all buttons to normal
    document.querySelectorAll('.salle-btn').forEach(b=>b.classList.remove('conflict'));
    return;
  }
  let params = new URLSearchParams({salle,debut,fin,periode});
  if(currentEditId) params.append('exclude_id', currentEditId);
  try{
    let d = await (await fetch('/check_conflict?'+params)).json();
    if(d.conflict){
      box.classList.add('show');
      document.getElementById('conflict-text').textContent=d.detail;
      if(saveBtn) saveBtn.disabled=true;
      if(editBtn) editBtn.disabled=true;
      // Mark the conflicting salle button red
      document.querySelectorAll('.salle-btn').forEach(b=>{
        b.classList.toggle('conflict', b.textContent.trim()===salle);
      });
    } else {
      box.classList.remove('show');
      if(saveBtn) saveBtn.disabled=false;
      if(editBtn) editBtn.disabled=false;
      document.querySelectorAll('.salle-btn').forEach(b=>b.classList.remove('conflict'));
    }
  }catch(e){}
}

// ── BATCH EDIT ────────────────────────────────────────────────────
let batchRows = []; // [{id, course_code, salle, ...}, ...]

function addToBatch(){
  if(!validate()) return;

  // Get etage from dropdown; fallback to original row's data-etage
  let etageVal = document.getElementById('f-etage').value;
  if(!etageVal && currentEditId){
    let origRow = document.querySelector(`#table tbody tr[data-id="${currentEditId}"]`);
    if(origRow) etageVal = origRow.dataset.etage || '';
  }

  let row = {
    id:           currentEditId,
    course_code:  document.getElementById('f-course-code').value,
    titre:        document.getElementById('f-titre').value,
    organisateur: document.getElementById('f-organisateur').value,
    etage:        etageVal,
    type:         document.getElementById('f-type').value,
    genre:        document.getElementById('f-genre').value,
    periode:      document.getElementById('f-periode').value,
    debut:        document.getElementById('f-debut').value,
    fin:          document.getElementById('f-fin').value,
    salle:        document.getElementById('f-salle').value,
  };

  // Replace if same ID already in batch
  let idx = batchRows.findIndex(r=>r.id===row.id);
  if(idx>=0) batchRows[idx]=row; else batchRows.push(row);

  // Mark row in table as pending
  let tr = document.querySelector(`#table tbody tr[data-id="${row.id}"]`);
  if(tr){ tr.style.outline='2px solid #27ae60'; tr.style.outlineOffset='-2px'; }

  updateBatchUI();
  resetForm();
}

function updateBatchUI(){
  let panel = document.getElementById('batch-panel');
  let countEl = document.getElementById('batch-count');
  let listEl  = document.getElementById('batch-list');
  if(!batchRows.length){ panel.style.display='none'; return; }
  panel.style.display = 'block';
  countEl.textContent = batchRows.length;
  listEl.innerHTML = batchRows.map(r=>
    `<div style="border-bottom:1px solid rgba(0,0,0,.08);padding:2px 0;">
      <b style="color:var(--accent2);">${r.course_code||'#'+r.id}</b>
      — ${r.salle||'بدون قاعة'}
      — ${r.periode}
      <span onclick="removeBatchRow(${r.id})" style="color:#c0392b;cursor:pointer;margin-right:4px;">✕</span>
    </div>`
  ).join('');
}

function removeBatchRow(id){
  batchRows = batchRows.filter(r=>r.id!==id);
  let tr = document.querySelector(`#table tbody tr[data-id="${id}"]`);
  if(tr){ tr.style.outline=''; }
  updateBatchUI();
}

async function saveBatch(){
  if(!batchRows.length) return;
  let btn = event.target;
  btn.disabled = true;
  btn.textContent = '⏳ جاري الحفظ...';

  try {
    let res = await fetch('/batch_update', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({rows: batchRows})
    });
    let data = await res.json();

    if(data.ok){
      let msg = `✅ تم حفظ ${data.saved} تعديل`;
      if(data.errors.length) msg += `\n⚠️ ${data.errors.join('\n')}`;

      // Update rows in table visually
      batchRows.forEach(row=>{
        let tr = document.querySelector(`#table tbody tr[data-id="${row.id}"]`);
        if(!tr) return;
        tr.style.outline = '';
        // Update displayed cells
        tr.dataset.salle   = row.salle;
        tr.dataset.etage   = row.etage;
        tr.dataset.periode = row.periode;
        if(tr.children[4]) tr.children[4].innerHTML = `<strong>${row.salle}</strong>`;
        if(tr.children[7]) tr.children[7].textContent = row.debut;
        if(tr.children[8]) tr.children[8].textContent = row.fin;
      });

      clearBatch();
      alert(msg);
    } else {
      alert('خطأ: ' + (data.error||''));
    }
  } catch(e){
    alert('خطأ في الاتصال');
  } finally {
    btn.disabled = false;
    btn.textContent = '✅ حفظ الكل دفعة واحدة';
  }
}

function clearBatch(){
  batchRows.forEach(r=>{
    let tr=document.querySelector(`#table tbody tr[data-id="${r.id}"]`);
    if(tr) tr.style.outline='';
  });
  batchRows=[];
  updateBatchUI();
}

// ── SUBMIT SINGLE SAVE ────────────────────────────────────────────
function submitForm(){
  if(!validate()) return;
  syncHidden('h');
  document.getElementById('form-save').submit();
}
function submitEdit(){
  if(!validate()) return;
  syncHidden('he');
  document.getElementById('he-id').value = currentEditId;
  document.getElementById('form-edit').submit();
}
function syncHidden(p){
  let qs = window.location.search.replace(/^\?/,'');
  document.getElementById(p+'-qs').value          = qs;
  document.getElementById(p+'-course-code').value = document.getElementById('f-course-code').value;
  document.getElementById(p+'-titre').value        = document.getElementById('f-titre').value;
  document.getElementById(p+'-organisateur').value = document.getElementById('f-organisateur').value;
  document.getElementById(p+'-etage').value        = document.getElementById('f-etage').value;
  document.getElementById(p+'-type').value         = document.getElementById('f-type').value;
  document.getElementById(p+'-genre').value        = document.getElementById('f-genre').value;
  document.getElementById(p+'-periode').value      = document.getElementById('f-periode').value;
  document.getElementById(p+'-debut').value        = document.getElementById('f-debut').value;
  document.getElementById(p+'-fin').value          = document.getElementById('f-fin').value;
  document.getElementById(p+'-salle').value        = document.getElementById('f-salle').value;
  let levelVal = document.getElementById('f-level').value;
  if(levelVal === 'أخرى') levelVal = document.getElementById('f-level-custom').value || 'أخرى';
  document.getElementById(p+'-level').value        = levelVal;
  document.getElementById(p+'-competance').value   = document.getElementById('f-competance').value;
  document.getElementById(p+'-method').value       = document.getElementById('f-method').value;
  document.getElementById(p+'-registred').value    = document.getElementById('f-registred')?.value || 0;
  document.getElementById(p+'-status').value       = document.getElementById('f-status').value;
}
function validate(){
  let fields = [['f-titre','العنوان'],['f-organisateur','المنظم'],['f-genre','الجنس'],['f-periode','الفترة'],['f-debut','البداية'],['f-fin','النهاية']];
  for(let [id,lbl] of fields){
    if(!document.getElementById(id).value){alert('يرجى إدخال: '+lbl);return false;}
  }
  if(!document.getElementById('f-salle').value){alert('يرجى اختيار القاعة');return false;}
  return true;
}

// ── FILL FORM FROM ROW (EDIT MODE) ────────────────────────────────
function fillForm(id){
  let row = document.querySelector(`#table tbody tr[data-id="${id}"]`);
  if(!row) return;

  let courseCode   = row.dataset.courseCode   || '';
  let titre        = row.dataset.titre        || '';
  let organisateur = row.dataset.organisateur || '';
  let type         = row.dataset.type         || '';
  let etage        = row.dataset.etage        || '';
  let salle        = row.dataset.salle        || '';
  let genre        = row.dataset.genre        || '';
  let periode      = row.dataset.periode      || '';
  let debut        = row.dataset.debut        || '';
  let fin          = row.dataset.fin          || '';

  currentEditId    = id;
  currentEditSalle = salle;
  selectedSalle    = salle;

  document.getElementById('f-course-code').value  = courseCode;
  document.getElementById('f-titre').value         = titre;
  document.getElementById('f-organisateur').value  = organisateur;
  document.getElementById('f-etage').value         = etage;
  document.getElementById('f-type').value          = type;
  document.getElementById('f-genre').value         = genre;
  document.getElementById('f-periode').value       = periode;
  document.getElementById('f-debut').value         = debut;
  document.getElementById('f-fin').value           = fin;
  document.getElementById('f-salle').value         = salle;
  if(salle) document.getElementById('btn-clear-salle').style.display='inline';
  else document.getElementById('btn-clear-salle').style.display='none';

  // Handle activity type (level)
  let levelVal = row.dataset.level || '';
  let levelSel = document.getElementById('f-level');
  let opts = Array.from(levelSel.options).map(o=>o.value);
  if(opts.includes(levelVal)){
    levelSel.value = levelVal;
    document.getElementById('f-level-custom').style.display='none';
  } else if(levelVal){
    levelSel.value = 'أخرى';
    document.getElementById('f-level-custom').style.display='block';
    document.getElementById('f-level-custom').value = levelVal;
  } else {
    levelSel.value = '';
    document.getElementById('f-level-custom').style.display='none';
  }
  document.getElementById('f-competance').value    = row.dataset.competance || '';
  document.getElementById('f-method').value        = row.dataset.method     || '';
  document.getElementById('f-status').value        = row.dataset.status     || '';

  renderSalleGrid(salle);

  // Switch to edit mode buttons
  document.getElementById('btn-save').style.display  = 'none';
  document.getElementById('btn-edit').style.display  = 'flex';
  document.getElementById('btn-cancel').style.display= 'flex';
  document.getElementById('conflict-box').classList.remove('show');

  // Highlight row, scroll into view
  document.querySelectorAll('#table tbody tr').forEach(r=>r.classList.remove('selected-row'));
  row.classList.add('selected-row');
  row.scrollIntoView({block:'nearest', behavior:'smooth'});

  // Scroll sidebar to top
  document.querySelector('.sidebar').scrollTop = 0;
  checkConflict();
}

// ── RESET ─────────────────────────────────────────────────────────
function resetForm(){
  currentEditId = null; currentEditSalle = ''; selectedSalle = '';
  ['f-course-code','f-titre','f-organisateur','f-debut','f-fin'].forEach(id=>document.getElementById(id).value='');
  ['f-etage','f-type','f-genre','f-periode'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('f-salle').value='';
  document.getElementById('salle-selected-label').textContent='';
  renderSalleGrid();
  document.getElementById('conflict-box').classList.remove('show');
  document.getElementById('btn-save').style.display='flex';
  document.getElementById('btn-save').disabled=false;
  document.getElementById('btn-edit').style.display='none';
  document.getElementById('btn-cancel').style.display='none';
  document.querySelectorAll('#table tbody tr').forEach(r=>r.classList.remove('selected-row'));
}

// ── SWAP SALLES ───────────────────────────────────────────────────
async function swapSalles(){
  let cc1 = document.getElementById('swap-id1').value.trim();
  let cc2 = document.getElementById('swap-id2').value.trim();
  let res = document.getElementById('swap-result');
  if(!cc1 || !cc2){ res.style.display='block';res.style.color='#c0392b';res.textContent='يرجى إدخال رقمي الدورة';return;}
  if(cc1===cc2){ res.style.display='block';res.style.color='#c0392b';res.textContent='رقما الدورة متطابقان';return;}
  try{
    let r = await (await fetch('/swap_salles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cc1,cc2})})).json();
    res.style.display='block';
    res.style.color = r.ok ? '#27ae60' : '#c0392b';
    res.textContent = r.ok ? r.msg : '⚠️ '+r.error;
    if(r.ok){ document.getElementById('swap-id1').value=''; document.getElementById('swap-id2').value=''; }
  }catch(e){res.style.display='block';res.style.color='#c0392b';res.textContent='خطأ في الاتصال';}
}

// ── CLEAR SALLE ───────────────────────────────────────────────────
function clearSalle(){
  selectedSalle='';
  document.getElementById('f-salle').value='';
  document.getElementById('salle-selected-label').textContent='';
  document.getElementById('btn-clear-salle').style.display='none';
  document.querySelectorAll('.salle-btn').forEach(b=>b.classList.remove('active'));
  checkConflict();
}

// ── إلغاء تحديد القاعة من صف الجدول ─────────────────────────────
async function clearSalleFromRow(id, btn){
  if(!confirm('إلغاء تحديد القاعة لهذا الحجز؟')) return;
  let r = await (await fetch('/clear_salle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})})).json();
  if(r.ok){
    let tr = document.querySelector(`#table tbody tr[data-id="${id}"]`);
    if(tr){ tr.dataset.salle=''; tr.children[5].innerHTML='<strong style="color:var(--muted)">—</strong>'; tr.children[4].textContent=''; }
    btn.parentElement.querySelector('strong').style.color='var(--muted)';
  } else alert(r.error);
}

// ── CUSTOM LEVEL ──────────────────────────────────────────────────
document.getElementById('f-level')?.addEventListener('change', function(){
  let custom = document.getElementById('f-level-custom');
  if(this.value==='أخرى'){ custom.style.display='block'; custom.focus(); }
  else { custom.style.display='none'; }
});

// ── SORT TABLE ────────────────────────────────────────────────────
let sortCol = -1, sortAsc = true;
function sortTable(col){
  let tbody = document.getElementById('tbody');
  if(!tbody) return;
  let rows = Array.from(tbody.querySelectorAll('tr'));
  if(sortCol === col){ sortAsc = !sortAsc; }
  else { sortCol = col; sortAsc = true; }
  for(let i=1;i<=15;i++){
    let si = document.getElementById('si-'+i);
    if(si) si.textContent = (i===col) ? (sortAsc?'▲':'▼') : '⇅';
  }
  rows.sort((a,b)=>{
    let av = a.children[col]?.innerText?.trim() || '';
    let bv = b.children[col]?.innerText?.trim() || '';
    if(col===1){ return sortAsc ? (+av-(+bv)) : (+bv-(+av)); }
    return sortAsc ? av.localeCompare(bv,'ar') : bv.localeCompare(av,'ar');
  });
  rows.forEach(r => tbody.appendChild(r));
}

// ── TABLE SELECTION & DELETE ──────────────────────────────────────
function toggleAll(m){document.querySelectorAll('.row-check').forEach(cb=>{cb.checked=m.checked;});}
async function deleteSelected(){
  let sel=[...document.querySelectorAll('.row-check:checked')];
  if(!sel.length){alert('اختر عناصر للحذف');return;}
  if(!confirm('حذف '+sel.length+' عنصر؟'))return;
  await Promise.all(sel.map(el=>fetch('/delete',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'id='+el.value}).then(()=>el.closest('tr').remove())));
}

// ── TABS (defined in gantt script block above, stub here) ─────────
function initCalendar(){} // no-op: gantt replaces FullCalendar

// ── NOTIFICATIONS ─────────────────────────────────────────────────
async function loadNotifications(){
  try{
    let d=await(await fetch('/notifications')).json();
    let badge=document.getElementById('notif-badge');
    badge.textContent=d.unread;badge.style.display=d.unread>0?'block':'none';
    let list=document.getElementById('notif-list');
    list.innerHTML=d.notifications.length?d.notifications.map(n=>`<div class="notif-item ${n.is_read?'':'unread'}">${n.message}<div class="notif-time">${n.created_at}</div></div>`).join(''):'<p style="color:var(--muted);text-align:center;padding:16px;font-size:12px;">لا توجد إشعارات</p>';
  }catch(e){}
}
function openNotifDrawer(){document.getElementById('notif-drawer').classList.add('open');document.getElementById('overlay').classList.add('show');loadNotifications();}
function closeNotifDrawer(){document.getElementById('notif-drawer').classList.remove('open');document.getElementById('overlay').classList.remove('show');}
async function markAllRead(){await fetch('/notifications/read',{method:'POST'});document.getElementById('notif-badge').style.display='none';loadNotifications();}
setInterval(loadNotifications,30000);loadNotifications();

// ── HEARTBEAT (keep online status) ───────────────────────────────
setInterval(()=>fetch('/heartbeat',{method:'POST'}), 60000);
fetch('/heartbeat',{method:'POST'}); // immediate on load
</script>
</body></html>"""

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def init_db():
    _bootstrap_db()

def add_notification(user, message):
    conn = get_conn()
    execute(conn, "INSERT INTO notifications (\"user\",message) VALUES (?,?)", (user, message))
    conn.commit()
    conn.close()

def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if "user" not in session: return redirect("/login")
        return f(*a, **kw)
    return dec

def admin_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if "user" not in session: return redirect("/login")
        if session.get("role") != "admin":
            flash("غير مصرح لك بهذه العملية", "error"); return redirect("/")
        return f(*a, **kw)
    return dec

# ─────────────────────────────────────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        conn = get_conn()
        row = fetchone(conn, "SELECT username,role FROM users WHERE username=? AND password=?",
                       (u, hash_password(p)))
        conn.close()
        if row:
            session["user"] = row[0]
            session["role"] = row[1]
            session["login_time"] = datetime.now().isoformat()
            # Track online
            ONLINE_USERS[row[0]] = {
                "last_seen": datetime.now(),
                "login_time": datetime.now(),
                "ip": request.remote_addr or "—"
            }
            # Log session to DB
            conn2 = get_conn()
            execute(conn2, "INSERT INTO user_sessions (username, login_at, ip) VALUES (?,?,?)",
                    (row[0], datetime.now().isoformat(), request.remote_addr or ""))
            conn2.commit(); conn2.close()
            return redirect("/")
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    u = session.get("user")
    login_time_str = session.get("login_time")
    if u and login_time_str:
        try:
            login_dt = datetime.fromisoformat(login_time_str)
            duration = int((datetime.now() - login_dt).total_seconds())
            conn = get_conn()
            # Update last open session
            execute(conn, """UPDATE user_sessions SET logout_at=?, duration_seconds=?
                WHERE username=? AND logout_at IS NULL
                ORDER BY id DESC LIMIT 1""",
                (datetime.now().isoformat(), duration, u))
            conn.commit(); conn.close()
        except Exception:
            pass
        ONLINE_USERS.pop(u, None)
    session.clear()
    return redirect("/login")

@app.route("/register", methods=["GET", "POST"])
@admin_required
def register():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        r = request.form.get("role", "user")
        if not u or not p:
            flash("يرجى ملء جميع الحقول", "error"); return redirect("/register")
        conn = get_conn()
        try:
            execute(conn, "INSERT INTO users (username,password,role) VALUES (?,?,?)",
                    (u, hash_password(p), r))
            conn.commit(); flash(f"تم إنشاء المستخدم {u} بنجاح", "success")
        except Exception:
            conn.rollback(); flash("اسم المستخدم موجود مسبقاً", "error")
        finally:
            conn.close()
        return redirect("/register")
    conn = get_conn()
    users = fetchall(conn, "SELECT id,username,role,created_at FROM users ORDER BY id DESC")
    conn.close()
    return render_template_string(REGISTER_TEMPLATE, users=users)

@app.route("/delete_user", methods=["POST"])
@admin_required
def delete_user():
    conn = get_conn()
    execute(conn, "DELETE FROM users WHERE id=? AND username!='admin'",
            (request.form.get("id"),))
    conn.commit(); conn.close(); return redirect("/register")

@app.route("/check_conflict")
@login_required
def check_conflict():
    salle      = request.args.get("salle", "")
    debut      = request.args.get("debut", "")
    fin        = request.args.get("fin", "")
    periode    = request.args.get("periode", "")
    exclude_id = request.args.get("exclude_id", None)
    if not salle or not debut or not fin or not periode:
        return jsonify({"conflict": False})
    conn = get_conn()
    if exclude_id:
        row = fetchone(conn, """SELECT titre,organisateur,date_debut,date_fin FROM reservations
                          WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=? AND id!=?""",
                       (salle, periode, fin, debut, exclude_id))
    else:
        row = fetchone(conn, """SELECT titre,organisateur,date_debut,date_fin FROM reservations
                          WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=?""",
                       (salle, periode, fin, debut))
    conn.close()
    if row:
        return jsonify({"conflict": True,
                        "detail": f"القاعة محجوزة: «{row[0]}» بواسطة {row[1]} من {row[2]} إلى {row[3]}"})
    return jsonify({"conflict": False})

@app.route("/notifications")
@login_required
def get_notifications():
    conn = get_conn()
    rows = fetchall(conn,
        "SELECT id,message,is_read,created_at FROM notifications WHERE \"user\"=? ORDER BY id DESC LIMIT 20",
        (session["user"],))
    conn.close()
    notifs = [{"id": r[0], "message": r[1], "is_read": r[2], "created_at": r[3]} for r in rows]
    return jsonify({"notifications": notifs, "unread": sum(1 for n in notifs if not n["is_read"])})

@app.route("/notifications/read", methods=["POST"])
@login_required
def mark_read():
    conn = get_conn()
    execute(conn, "UPDATE notifications SET is_read=1 WHERE \"user\"=?", (session["user"],))
    conn.commit(); conn.close(); return jsonify({"ok": True})

@app.route("/calendar_events")
@login_required
def calendar_events():
    conn = get_conn()
    rows = fetchall(conn, """SELECT id, course_code, titre, salle, date_debut, date_fin,
                                    genre, periode, organisateur, type, etage, created_by
                             FROM reservations ORDER BY salle, date_debut""")
    conn.close()
    events = []
    for r in rows:
        events.append({
            "id": r[0], "course_code": r[1], "titre": r[2], "salle": r[3],
            "date_debut": r[4], "date_fin": r[5],
            "genre": r[6], "periode": r[7], "organisateur": r[8],
            "type": r[9], "etage": r[10], "created_by": r[11] or ""
        })
    return jsonify(events)

SALLE_TO_ETAGE = {}
SALLE_TO_TYPE  = {}
for s in SALLES:
    SALLE_TO_ETAGE[s["nom"]] = s["etage"]
    SALLE_TO_TYPE[s["nom"]]  = s["type"]

# ── Auto-fix migration: correct etage+type for ALL existing rows ──
def _fix_etage_type_all():
    try:
        conn = get_conn()
        rows = fetchall(conn, "SELECT id, salle, etage, type FROM reservations")
        fixed = 0
        for r in rows:
            id_, salle, etage, rtype = r[0], r[1] or "", r[2] or "", r[3] or ""

            # Case 1: salle is correct, just fix etage/type
            if salle and salle in SALLE_TO_ETAGE:
                ce = SALLE_TO_ETAGE[salle]
                ct = SALLE_TO_TYPE[salle]
                if ce != etage or ct != rtype:
                    execute(conn, "UPDATE reservations SET etage=?, type=? WHERE id=?",
                            (ce, ct, id_))
                    fixed += 1

            # Case 2: salle is empty but etage contains the salle name (old bug)
            elif not salle and etage in SALLE_TO_ETAGE:
                ce = SALLE_TO_ETAGE[etage]
                ct = SALLE_TO_TYPE[etage]
                execute(conn, "UPDATE reservations SET salle=?, etage=?, type=? WHERE id=?",
                        (etage, ce, ct, id_))
                fixed += 1

        if fixed:
            conn.commit()
            print(f"Migration: fixed {fixed} rows")
        conn.close()
    except Exception as e:
        print(f"Migration warning: {e}")

_fix_etage_type_all()

@app.route("/swap_salles", methods=["POST"])
@login_required
def swap_salles():
    data = request.get_json()
    cc1, cc2 = str(data.get("cc1","")).strip(), str(data.get("cc2","")).strip()
    if not cc1 or not cc2 or cc1 == cc2:
        return jsonify({"ok": False, "error": "يرجى إدخال رقمي دورة مختلفين"})
    conn = get_conn()
    r1 = fetchone(conn, "SELECT id,salle,etage,type,date_debut,date_fin FROM reservations WHERE course_code=?", (cc1,))
    r2 = fetchone(conn, "SELECT id,salle,etage,type,date_debut,date_fin FROM reservations WHERE course_code=?", (cc2,))
    if not r1:
        conn.close(); return jsonify({"ok": False, "error": f"رقم الدورة {cc1} غير موجود"})
    if not r2:
        conn.close(); return jsonify({"ok": False, "error": f"رقم الدورة {cc2} غير موجود"})
    execute(conn, "UPDATE reservations SET salle=?, etage=?, type=? WHERE id=?", (r2[1],r2[2],r2[3],r1[0]))
    execute(conn, "UPDATE reservations SET salle=?, etage=?, type=? WHERE id=?", (r1[1],r1[2],r1[3],r2[0]))
    conn.commit(); conn.close()
    add_notification(session["user"], f"تم تبادل القاعتين: {cc1}({r1[1]}) ↔ {cc2}({r2[1]})")
    return jsonify({"ok": True, "msg": f"✅ {cc1} ← {r2[1]}  |  {cc2} ← {r1[1]}"})

@app.route("/clear_salle", methods=["POST"])
@login_required
def clear_salle():
    id_ = request.get_json().get("id")
    conn = get_conn()
    row = fetchone(conn, "SELECT salle, created_by FROM reservations WHERE id=?", (id_,))
    if not row:
        conn.close(); return jsonify({"ok": False, "error": "الحجز غير موجود"})
    if session["role"] != "admin" and row[1] != session["user"]:
        conn.close(); return jsonify({"ok": False, "error": "غير مصرح"})
    execute(conn, "UPDATE reservations SET salle='', etage='', type='' WHERE id=?", (id_,))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "old_salle": row[0]})

@app.route("/batch_update", methods=["POST"])
@login_required
def batch_update():
    """Update multiple reservations in one request."""
    import json
    data = request.get_json()
    if not data or "rows" not in data:
        return jsonify({"ok": False, "error": "no data"}), 400

    conn = get_conn()
    saved = 0
    errors = []

    for row in data["rows"]:
        id_          = row.get("id")
        course_code  = str(row.get("course_code", "")).strip()
        salle        = str(row.get("salle", "")).strip()
        etage        = SALLE_TO_ETAGE.get(salle, str(row.get("etage", "")).strip())
        type_        = SALLE_TO_TYPE.get(salle,  str(row.get("type",  "")).strip())
        debut        = str(row.get("debut", "")).strip()
        fin          = str(row.get("fin", "")).strip()
        periode      = str(row.get("periode", "")).strip()
        titre        = str(row.get("titre", "")).strip()
        organisateur = str(row.get("organisateur", "")).strip()
        genre        = str(row.get("genre", "")).strip()
        level        = str(row.get("level", "")).strip()
        competance   = str(row.get("competance", "")).strip()
        method       = str(row.get("method", "")).strip()
        registred    = int(row.get("registred", 0) or 0)
        status       = str(row.get("status", "")).strip()

        # Get original to compare
        orig = fetchone(conn, "SELECT salle,periode,date_debut,date_fin FROM reservations WHERE id=?", (id_,))
        if not orig:
            errors.append(f"#{id_} غير موجود")
            continue

        # Check conflict only if salle/dates/periode changed
        if salle != orig[0] or periode != orig[1] or debut != orig[2] or fin != orig[3]:
            conflict = fetchone(conn, """SELECT id FROM reservations
                WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=? AND id!=?""",
                (salle, periode, fin, debut, id_))
            if conflict:
                errors.append(f"#{id_} تعارض: {salle} محجوزة")
                continue

        execute(conn, """UPDATE reservations SET
            course_code=?, type=?, etage=?, salle=?, genre=?, periode=?,
            date_debut=?, date_fin=?, titre=?, organisateur=?,
            level=?, competance=?, method=?, registred=?, status=?
            WHERE id=?""",
            (course_code, type_, etage, salle, genre, periode,
             debut, fin, titre, organisateur,
             level, competance, method, registred, status, id_))
        saved += 1

    conn.commit()
    conn.close()

    if saved:
        add_notification(session["user"], f"تم تعديل {saved} حجز دفعة واحدة")

    return jsonify({"ok": True, "saved": saved, "errors": errors})

@app.route("/report/export")
@admin_required
def report_export():
    import io
    conn = get_conn()
    rows = fetchall(conn, """
        SELECT created_by, COUNT(*) as total,
               SUM(CASE WHEN genre='رجال' THEN 1 ELSE 0 END),
               SUM(CASE WHEN genre='نساء' THEN 1 ELSE 0 END),
               SUM(CASE WHEN genre='مختلط' THEN 1 ELSE 0 END),
               SUM(CASE WHEN periode='صباحي' THEN 1 ELSE 0 END),
               SUM(CASE WHEN periode='مسائي' THEN 1 ELSE 0 END),
               MIN(date_debut), MAX(date_fin)
        FROM reservations WHERE created_by IS NOT NULL
        GROUP BY created_by ORDER BY total DESC
    """)
    conn.close()
    cols = ["المستخدم","الإجمالي","رجال","نساء","مختلط","صباحي","مسائي","أول حجز","آخر حجز"]
    df = pd.DataFrame(rows, columns=cols)
    buf = io.BytesIO(); df.to_excel(buf, index=False); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="rapport_activite.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        old_pw   = request.form.get("old_password", "")
        new_pw   = request.form.get("new_password", "")
        confirm  = request.form.get("confirm_password", "")
        if not old_pw or not new_pw or not confirm:
            flash("يرجى ملء جميع الحقول", "error")
            return redirect("/profile")
        if new_pw != confirm:
            flash("كلمة المرور الجديدة غير متطابقة", "error")
            return redirect("/profile")
        if len(new_pw) < 6:
            flash("كلمة المرور يجب أن تكون 6 أحرف على الأقل", "error")
            return redirect("/profile")
        conn = get_conn()
        row = fetchone(conn, "SELECT id FROM users WHERE username=? AND password=?",
                       (session["user"], hash_password(old_pw)))
        if not row:
            conn.close()
            flash("كلمة المرور الحالية غير صحيحة", "error")
            return redirect("/profile")
        execute(conn, "UPDATE users SET password=? WHERE username=?",
                (hash_password(new_pw), session["user"]))
        conn.commit(); conn.close()
        flash("✅ تم تغيير كلمة المرور بنجاح", "success")
        return redirect("/profile")

    conn = get_conn()
    stats = fetchone(conn, "SELECT COUNT(*) FROM reservations WHERE created_by=?", (session["user"],))
    conn.close()
    return render_template_string(PROFILE_TEMPLATE,
        user=session["user"], role=session["role"],
        total_added=stats[0] if stats else 0)


@app.route("/dashboard")
@admin_required
def dashboard():
    conn = get_conn()
    f_debut = request.args.get("f_debut", "")
    f_fin   = request.args.get("f_fin", "")

    where = "WHERE 1=1"
    params = []
    if f_debut: where += " AND date_debut>=?"; params.append(f_debut)
    if f_fin:   where += " AND date_fin<=?";   params.append(f_fin)

    # Global stats
    total = fetchone(conn, f"SELECT COUNT(*) FROM reservations {where}", params)[0]

    # By etage
    by_etage = fetchall(conn, f"""SELECT etage, COUNT(*) FROM reservations {where}
        AND etage!='' GROUP BY etage ORDER BY etage""", params)

    # By salle (top 15)
    by_salle = fetchall(conn, f"""SELECT salle, COUNT(*) as n FROM reservations {where}
        AND salle!='' GROUP BY salle ORDER BY n DESC LIMIT 15""", params)

    # By type (قاعة/مختبر)
    by_type = fetchall(conn, f"""SELECT type, COUNT(*) FROM reservations {where}
        AND type!='' GROUP BY type""", params)

    # By genre
    by_genre = fetchall(conn, f"""SELECT genre, COUNT(*) FROM reservations {where}
        AND genre!='' GROUP BY genre""", params)

    # By periode
    by_periode = fetchall(conn, f"""SELECT periode, COUNT(*) FROM reservations {where}
        AND periode!='' GROUP BY periode""", params)

    # By month (last 12 months)
    by_month = fetchall(conn, f"""SELECT SUBSTR(date_debut,1,7) as m, COUNT(*)
        FROM reservations {where} AND date_debut!=''
        GROUP BY m ORDER BY m DESC LIMIT 12""", params)

    # Occupancy rate per salle (days occupied / total workdays in range)
    # Top organisateurs
    by_org = fetchall(conn, f"""SELECT organisateur, COUNT(*) as n FROM reservations {where}
        AND organisateur!='' GROUP BY organisateur ORDER BY n DESC LIMIT 10""", params)

    # Lab vs Salle stats
    lab_count  = fetchone(conn, f"SELECT COUNT(*) FROM reservations {where} AND type='مختبر'", params)[0]
    salle_count= fetchone(conn, f"SELECT COUNT(*) FROM reservations {where} AND type='قاعة'", params)[0]

    # Session stats per user
    session_stats = fetchall(conn, """
        SELECT username, COUNT(*) as sessions,
               SUM(duration_seconds) as total_sec,
               AVG(duration_seconds) as avg_sec,
               MAX(login_at) as last_login
        FROM user_sessions WHERE duration_seconds > 0
        GROUP BY username ORDER BY total_sec DESC""")

    conn.close()
    return render_template_string(DASHBOARD_TEMPLATE,
        total=total, by_etage=by_etage, by_salle=by_salle,
        by_type=by_type, by_genre=by_genre, by_periode=by_periode,
        by_month=by_month, by_org=by_org, lab_count=lab_count,
        salle_count=salle_count, session_stats=session_stats,
        f_debut=f_debut, f_fin=f_fin,
        user=session["user"], role=session["role"])

@app.route("/report")
@admin_required
def report():
    conn = get_conn()
    # Activity per user
    users_stats = fetchall(conn, """
        SELECT created_by,
               COUNT(*) as total,
               SUM(CASE WHEN genre='رجال' THEN 1 ELSE 0 END) as men,
               SUM(CASE WHEN genre='نساء' THEN 1 ELSE 0 END) as women,
               SUM(CASE WHEN genre='مختلط' THEN 1 ELSE 0 END) as mixed,
               SUM(CASE WHEN periode='صباحي' THEN 1 ELSE 0 END) as morning,
               SUM(CASE WHEN periode='مسائي' THEN 1 ELSE 0 END) as evening,
               MIN(date_debut) as first_date,
               MAX(date_fin) as last_date
        FROM reservations
        WHERE created_by IS NOT NULL AND created_by != ''
        GROUP BY created_by
        ORDER BY total DESC
    """)
    # Recent activity per user (last 10 actions)
    recent = fetchall(conn, """
        SELECT created_by, id, course_code, titre, salle, date_debut, created_at
        FROM reservations
        ORDER BY created_at DESC
        LIMIT 50
    """)
    conn.close()
    return render_template_string(REPORT_TEMPLATE,
        users_stats=users_stats, recent=recent,
        user=session["user"], role=session["role"])


@app.route("/admin/clean_empty_salle")
@admin_required
def clean_empty_salle():
    conn = get_conn()
    # Count first
    count = fetchone(conn, "SELECT COUNT(*) FROM reservations WHERE salle IS NULL OR salle = ''")[0]
    # Delete rows with no salle
    execute(conn, "DELETE FROM reservations WHERE salle IS NULL OR salle = ''")
    conn.commit()
    conn.close()
    flash(f"✅ تم حذف {count} سجل بدون قاعة", "success")
    return redirect("/")

@app.route("/admin/fix_etage_type")
@admin_required
def fix_etage_type():
    """One-time migration: fix etage and type for all existing reservations based on salle name."""
    conn = get_conn()
    rows = fetchall(conn, "SELECT id, salle FROM reservations")
    fixed = 0
    for r in rows:
        id_, salle = r[0], r[1]
        if not salle:
            continue
        correct_etage = SALLE_TO_ETAGE.get(salle)
        correct_type  = SALLE_TO_TYPE.get(salle)
        if correct_etage and correct_type:
            execute(conn, "UPDATE reservations SET etage=?, type=? WHERE id=?",
                    (correct_etage, correct_type, id_))
            fixed += 1
    conn.commit()
    conn.close()
    flash(f"✅ تم إصلاح {fixed} سجل — الطابق والنوع تم تصحيحهما", "success")
    return redirect("/")

@app.route("/heartbeat", methods=["POST"])
@login_required
def heartbeat():
    u = session.get("user")
    if u:
        if u not in ONLINE_USERS:
            ONLINE_USERS[u] = {"login_time": datetime.now(), "ip": request.remote_addr or "—"}
        ONLINE_USERS[u]["last_seen"] = datetime.now()
    return jsonify({"ok": True})

@app.route("/api/online_users")
@admin_required
def online_users_api():
    now = datetime.now()
    result = []
    for uname, info in list(ONLINE_USERS.items()):
        last = info.get("last_seen", now)
        inactive = (now - last).total_seconds()
        if inactive > ONLINE_TIMEOUT:
            continue  # expired
        login_t = info.get("login_time", last)
        active_sec = int((now - login_t).total_seconds())
        result.append({
            "username": uname,
            "ip": info.get("ip", "—"),
            "login_time": login_t.strftime("%H:%M:%S"),
            "last_seen": last.strftime("%H:%M:%S"),
            "active_minutes": active_sec // 60,
            "inactive_seconds": int(inactive),
            "status": "نشط" if inactive < 60 else "خامل"
        })
    return jsonify(result)

@app.route("/live_count")
@login_required
def live_count():
    conn = get_conn()
    count = fetchone(conn, "SELECT COUNT(*) FROM reservations")[0]
    conn.close()
    return jsonify({"count": count})

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    init_db()
    conn = get_conn()
    if request.method == "POST":
        salle        = request.form.get("salle", "").strip()
        debut        = request.form.get("debut", "")
        fin          = request.form.get("fin", "")
        periode      = request.form.get("periode", "")
        course_code  = request.form.get("course_code", "").strip()
        # Always derive etage from salle name — never trust form etage field
        etage = SALLE_TO_ETAGE.get(salle, request.form.get("etage", "").strip())
        type_ = SALLE_TO_TYPE.get(salle, request.form.get("type", "").strip())
        conflict = fetchone(conn, """SELECT id FROM reservations
            WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=?""",
            (salle, periode, fin, debut))
        if conflict:
            flash("⚠️ تعارض في الحجز: القاعة محجوزة في هذه الفترة", "error")
            conn.close(); return redirect("/")
        execute(conn, """INSERT INTO reservations
            (course_code,type,etage,salle,genre,periode,date_debut,date_fin,titre,organisateur,
             level,competance,method,registred,status,created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            course_code, type_, etage, salle,
            request.form.get("genre"), periode, debut, fin,
            request.form.get("titre"), request.form.get("organisateur"),
            request.form.get("level",""), request.form.get("competance",""),
            request.form.get("method",""), int(request.form.get("registred",0) or 0),
            request.form.get("status",""), session["user"]))
        conn.commit()
        titre = request.form.get("titre", "")
        users = fetchall(conn, "SELECT username FROM users")
        conn.close()
        for u in users:
            add_notification(u[0], f"حجز جديد: «{titre}» في {salle} من {debut} إلى {fin}")
        # Preserve filters after save
        qs = request.form.get("_qs", "")
        return redirect("/?" + qs if qs else "/")

    search    = request.args.get("search", "")
    f_etage   = request.args.get("f_etage", "")
    f_type    = request.args.get("f_type", "")
    f_genre   = request.args.get("f_genre", "")
    f_periode = request.args.get("f_periode", "")
    f_debut   = request.args.get("f_debut", "")
    f_fin     = request.args.get("f_fin", "")
    dore_f    = request.args.get("dore_f", "")

    # r[0]=id r[1]=course_code r[2]=type r[3]=etage r[4]=salle r[5]=genre r[6]=periode
    # r[7]=date_debut r[8]=date_fin r[9]=titre r[10]=organisateur
    # r[11]=level r[12]=competance r[13]=method r[14]=registred r[15]=status r[16]=created_by
    q = """SELECT id, course_code, type, etage, salle, genre, periode,
                  date_debut, date_fin, titre, organisateur,
                  level, competance, method, registred, status, created_by
           FROM reservations WHERE 1=1"""
    params = []
    if search:    q += " AND (titre LIKE ? OR organisateur LIKE ? OR salle LIKE ? OR course_code LIKE ? OR CAST(id AS TEXT) LIKE ?)"; params += [f"%{search}%"] * 5
    if dore_f:    q += " AND course_code LIKE ?"; params.append(f"%{dore_f}%")
    if f_etage:   q += " AND etage=?";    params.append(f_etage)
    if f_type:    q += " AND type=?";     params.append(f_type)
    if f_genre:   q += " AND genre=?";    params.append(f_genre)
    if f_periode: q += " AND periode=?";  params.append(f_periode)
    if f_debut:   q += " AND date_debut>=?"; params.append(f_debut)
    if f_fin:     q += " AND date_fin<=?";   params.append(f_fin)
    q += " ORDER BY date_debut DESC"

    data = fetchall(conn, q, params)
    today     = datetime.now().strftime("%Y-%m-%d")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    upcoming_count = fetchone(conn, "SELECT COUNT(*) FROM reservations WHERE date_debut BETWEEN ? AND ?",
                              (today, next_week))[0]
    total_count    = fetchone(conn, "SELECT COUNT(*) FROM reservations")[0]
    occupied_today = fetchone(conn, "SELECT COUNT(DISTINCT salle) FROM reservations WHERE date_debut<=? AND date_fin>=?",
                              (today, today))[0]
    conn.close()

    return render_template_string(INDEX_TEMPLATE,
        data=data, salles=SALLES, user=session["user"], role=session["role"],
        search=search, f_etage=f_etage, f_type=f_type, f_genre=f_genre,
        f_periode=f_periode, f_debut=f_debut, f_fin=f_fin,
        upcoming_count=upcoming_count, total_count=total_count, occupied_today=occupied_today)

@app.route("/export")
@login_required
def export_excel():
    import io
    conn = get_conn()
    rows = fetchall(conn, """SELECT id, course_code, type, etage, salle, genre, periode,
                                    date_debut, date_fin, titre, organisateur,
                                    level, competance, method, registred, status, created_by
                             FROM reservations ORDER BY id""")
    conn.close()
    cols = ["id","course code","type","etage","salle","genre","periode",
            "date_debut","date_fin","titre","organisateur",
            "Level","competance","method","registred","status","created_by"]
    df = pd.DataFrame(rows, columns=cols)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="reservations.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/import", methods=["POST"])
@login_required
def import_excel():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("يرجى اختيار ملف Excel", "error"); return redirect("/")
    try:
        df = pd.read_excel(file, engine="openpyxl")
    except Exception as e:
        flash(f"خطأ في قراءة الملف: {str(e)}", "error"); return redirect("/")

    # Normalize column names
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    conn = get_conn()
    imported = 0
    skipped  = 0

    for _, row in df.iterrows():
        def g(*cols):
            for col in cols:
                v = str(row.get(col, "")).strip()
                if v and v not in ("nan", "None", "NaT"):
                    return v
            return ""

        course_code  = g("course_code", "course code")
        salle       = g("salle")
        etage       = SALLE_TO_ETAGE.get(salle, g("etage"))
        type_       = SALLE_TO_TYPE.get(salle,  g("type"))
        genre       = g("genre")
        periode     = g("periode")
        date_debut  = g("date_debut")[:10] if g("date_debut") else ""
        date_fin    = g("date_fin")[:10]   if g("date_fin")   else ""
        titre       = g("titre")
        organisateur = g("organisateur")
        level       = g("level")
        competance  = g("competance")
        method      = g("method")
        registred   = int(g("registred") or 0)
        status      = g("status")
        created_by  = g("created_by") or session["user"]

        if not titre and not organisateur and not salle:
            skipped += 1
            continue

        try:
            execute(conn, """INSERT INTO reservations
                (course_code,type,etage,salle,genre,periode,date_debut,date_fin,titre,organisateur,
                 level,competance,method,registred,status,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (course_code, type_, etage, salle, genre, periode,
                 date_debut, date_fin, titre, organisateur,
                 level, competance, method, registred, status, created_by))
            imported += 1
        except Exception:
            skipped += 1
            continue

    conn.commit(); conn.close()
    flash(f"✅ تم استيراد {imported} حجز بنجاح" + (f" ({skipped} سطر تم تجاهله)" if skipped else ""), "success")
    return redirect("/")

@app.route("/update", methods=["POST"])
@login_required
def update():
    id_          = request.form.get("id")
    course_code  = request.form.get("course_code", "").strip()
    salle        = request.form.get("salle", "").strip()
    etage        = SALLE_TO_ETAGE.get(salle, request.form.get("etage", "").strip())
    type_        = SALLE_TO_TYPE.get(salle,  request.form.get("type",  "").strip())
    debut        = request.form.get("debut", "").strip()
    fin          = request.form.get("fin", "").strip()
    periode      = request.form.get("periode", "").strip()
    titre        = request.form.get("titre", "").strip()
    organisateur = request.form.get("organisateur", "").strip()
    genre        = request.form.get("genre", "").strip()
    level        = request.form.get("level", "").strip()
    competance   = request.form.get("competance", "").strip()
    method       = request.form.get("method", "").strip()
    registred    = int(request.form.get("registred", 0) or 0)
    status       = request.form.get("status", "").strip()
    conn = get_conn()
    orig = fetchone(conn, "SELECT salle,periode,date_debut,date_fin FROM reservations WHERE id=?", (id_,))
    if not orig:
        flash("الحجز غير موجود", "error"); conn.close(); return redirect("/")
    if salle != orig[0] or periode != orig[1] or debut != orig[2] or fin != orig[3]:
        conflict = fetchone(conn, """SELECT id FROM reservations
            WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=? AND id!=?""",
            (salle, periode, fin, debut, id_))
        if conflict:
            flash("⚠️ تعارض في الحجز: القاعة محجوزة في هذه الفترة", "error")
            conn.close(); return redirect("/")
    execute(conn, """UPDATE reservations SET
        course_code=?, type=?, etage=?, salle=?, genre=?, periode=?,
        date_debut=?, date_fin=?, titre=?, organisateur=?,
        level=?, competance=?, method=?, registred=?, status=?
        WHERE id=?""",
        (course_code, type_, etage, salle, genre, periode, debut, fin, titre, organisateur,
         level, competance, method, registred, status, id_))
    if not orig:
        flash("الحجز غير موجود", "error"); conn.close(); return redirect("/")
    if salle != orig[0] or periode != orig[1] or debut != orig[2] or fin != orig[3]:
        conflict = fetchone(conn, """SELECT id FROM reservations
            WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=? AND id!=?""",
            (salle, periode, fin, debut, id_))
        if conflict:
            flash("⚠️ تعارض في الحجز: القاعة محجوزة في هذه الفترة", "error")
            conn.close(); return redirect("/")
    execute(conn, """UPDATE reservations SET
        course_code=?, type=?, etage=?, salle=?, genre=?, periode=?,
        date_debut=?, date_fin=?, titre=?, organisateur=?
        WHERE id=?""",
        (course_code, type_, etage, salle, genre, periode, debut, fin, titre, organisateur, id_))
    conn.commit()
    conn.close()
    add_notification(session["user"], f"تم تعديل الحجز #{id_} [{course_code}]: «{titre}»")
    flash("✅ تم تعديل الحجز بنجاح", "success")
    qs = request.form.get("_qs", "")
    return redirect("/?" + qs if qs else "/")

@app.route("/delete", methods=["POST"])
@login_required
def delete():
    id_ = request.form.get("id")
    conn = get_conn()
    row = fetchone(conn, "SELECT titre,salle,created_by FROM reservations WHERE id=?", (id_,))
    if row and (session["role"] == "admin" or row[2] == session["user"]):
        execute(conn, "DELETE FROM reservations WHERE id=?", (id_,))
        conn.commit()
        conn.close()
        add_notification(session["user"], f"تم حذف الحجز: «{row[0]}» في {row[1]}")
    else:
        conn.close()
    return jsonify({"ok": True})

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
