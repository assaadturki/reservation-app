import os
import hashlib
from functools import wraps
from datetime import datetime, timedelta

import pandas as pd
from flask import Flask, request, redirect, send_file, session, jsonify, flash, render_template_string

app = Flask(__name__)
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
            created_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()
        # Migration: add course_code if missing — must commit/rollback between DDL statements in PG
        try:
            execute(conn, "ALTER TABLE reservations ADD COLUMN course_code TEXT")
            conn.commit()
        except Exception:
            conn.rollback()  # CRITICAL: reset failed transaction before continuing
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
            created_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        try:
            execute(conn, "ALTER TABLE reservations ADD COLUMN course_code TEXT")
        except Exception:
            pass  # SQLite doesn't need rollback for this
        execute(conn, """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            role TEXT DEFAULT 'user', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        execute(conn, """CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT, message TEXT, is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
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
    <span class="salle-grid-label">القاعة <span id="salle-selected-label" style="color:var(--accent);font-weight:900;"></span></span>
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
          <th class="sortable" onclick="sortTable(4)"><span class="sort-icon" id="si-4">⇅</span>الطابق</th>
          <th class="sortable" onclick="sortTable(5)"><span class="sort-icon" id="si-5">⇅</span>القاعة</th>
          <th class="sortable" onclick="sortTable(6)"><span class="sort-icon" id="si-6">⇅</span>الجنس</th>
          <th class="sortable" onclick="sortTable(7)"><span class="sort-icon" id="si-7">⇅</span>الفترة</th>
          <th class="sortable" onclick="sortTable(8)"><span class="sort-icon" id="si-8">⇅</span>البداية</th>
          <th class="sortable" onclick="sortTable(9)"><span class="sort-icon" id="si-9">⇅</span>النهاية</th>
          <th class="sortable" onclick="sortTable(10)"><span class="sort-icon" id="si-10">⇅</span>العنوان</th>
          <th class="sortable" onclick="sortTable(11)"><span class="sort-icon" id="si-11">⇅</span>المنظم</th>
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
            data-organisateur="{{ r[10]|e }}">
          <td onclick="event.stopPropagation()"><input type="checkbox" class="row-check" value="{{ r[0] }}"></td>
          <td style="color:var(--muted);font-size:11px;">{{ r[0] }}</td>
          <td><strong>{{ r[1] }}</strong></td>
          <td><span class="chip {% if r[2]=='قاعة' %}chip-q{% else %}chip-lab{% endif %}">{{ r[2] }}</span></td>
          <td>{{ r[3] }}</td>
          <td><strong>{{ r[4] }}</strong></td>
          <td><span class="chip {% if r[5]=='رجال' %}chip-m{% elif r[5]=='مختلط' %}chip-mix{% else %}chip-f{% endif %}">{{ r[5] }}</span></td>
          <td><span class="chip {% if r[6]=='صباحي' %}chip-s{% else %}chip-e{% endif %}">{{ r[6] }}</span></td>
          <td>{{ r[7] }}</td><td>{{ r[8] }}</td><td>{{ r[9] }}</td>
          <td style="color:var(--muted);">{{ r[10] }}</td>
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
  tip.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <strong style="font-size:13px;color:#1a2e28;">${ev.salle}</strong>
      <button onclick="hideTooltip();activeTooltipId=null;" style="background:none;border:none;cursor:pointer;font-size:16px;color:#888;line-height:1;">✕</button>
    </div>
    <div style="display:grid;grid-template-columns:auto 1fr;gap:3px 10px;font-size:12px;color:#333;">
      <span style="color:#888;">رقم الدورة</span><span><b>${ev.course_code||'—'}</b></span>
      <span style="color:#888;">العنوان</span><span>${ev.titre||'—'}</span>
      <span style="color:#888;">المنظم</span><span>${ev.organisateur||'—'}</span>
      <span style="color:#888;">القاعة</span><span>${ev.salle} — ${ev.etage}</span>
      <span style="color:#888;">الجنس</span><span>${ev.genre}</span>
      <span style="color:#888;">الفترة</span><span>${ev.periode}</span>
      <span style="color:#888;">من</span><span>${ev.date_debut}</span>
      <span style="color:#888;">إلى</span><span>${ev.date_fin}</span>
    </div>
  `;
  tip.style.display = 'block';
  positionTip(e);
}
function positionTip(e){
  let tip=document.getElementById('gantt-tip');
  let x=e.clientX+12, y=e.clientY+12;
  if(x+260>window.innerWidth) x=e.clientX-270;
  if(y+200>window.innerHeight) y=e.clientY-210;
  tip.style.left=x+'px'; tip.style.top=y+'px';
}
function hideTooltip(){ document.getElementById('gantt-tip').style.display='none'; }

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
                // Purple if booked both matin AND soir
                let hasMatin = evList.some(e=>e.periode==='صباحي');
                let hasSoir  = evList.some(e=>e.periode==='مسائي');
                let color = (hasMatin && hasSoir) ? '#8e44ad' : '#c0392b';
                let border= (hasMatin && hasSoir) ? '#6c3483' : '#922b21';
                let firstEv = evList[0];
                return `<td style="background:${cellBg};border-bottom:1px solid var(--border);border-left:1px solid rgba(168,200,192,.3);padding:3px 2px;">
                  <div style="background:${color};border:1.5px solid ${border};border-radius:4px;height:20px;cursor:pointer;"
                    onclick="ganttClick(event,${firstEv.id},${JSON.stringify(evList).replace(/"/g,'&quot;')})">
                  </div>
                </td>`;
              }
              return `<td style="background:${cellBg};border-bottom:1px solid var(--border);border-left:1px solid rgba(168,200,192,.3);padding:3px 2px;">
                <div style="background:#27ae60;border:1.5px solid #1e8449;border-radius:4px;height:20px;opacity:.2;"></div>
              </td>`;
            }).join('')}
          </tr>`;
        }).join('')}
      </tbody>
    </table>
    </div>

    <div style="padding:7px 14px;display:flex;gap:16px;flex-wrap:wrap;font-size:11px;border-top:1px solid var(--border);background:var(--bg);align-items:center;">
      <span><span style="display:inline-block;width:14px;height:14px;background:#c0392b;border-radius:3px;vertical-align:middle;margin-left:4px;"></span>مشغول</span>
      <span><span style="display:inline-block;width:14px;height:14px;background:#8e44ad;border-radius:3px;vertical-align:middle;margin-left:4px;"></span>مشغول (ص+م)</span>
      <span><span style="display:inline-block;width:14px;height:14px;background:#27ae60;opacity:.4;border-radius:3px;vertical-align:middle;margin-left:4px;"></span>متاح</span>
      <span><span style="display:inline-block;width:14px;height:14px;background:repeating-linear-gradient(45deg,#ccc,#ccc 2px,#ddd 2px,#ddd 8px);border-radius:3px;vertical-align:middle;margin-left:4px;"></span>عطلة (ج/س)</span>
      ${ganttPeriode ? `<span style="background:rgba(255,255,255,.3);padding:2px 10px;border-radius:10px;font-weight:700;">الفترة: ${ganttPeriode}</span>` : ''}
    </div>
    `}
  </div>`;

  document.getElementById('gantt-root').innerHTML = html;
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

function ganttClick(e, evId, evListJson){
  e.stopPropagation();
  // Parse event list (may be multiple if double-booked)
  let evList = evListJson ? evListJson : [ganttEvents.find(x=>x.id===evId)].filter(Boolean);
  if(typeof evListJson === 'string'){
    try{ evList = JSON.parse(evListJson); }catch(err){ evList = [ganttEvents.find(x=>x.id===evId)].filter(Boolean); }
  }
  if(activeTooltipId === evId){
    hideTooltip(); return;
  }
  activeTooltipId = evId;
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
    // Hide sidebar, expand content for full-width gantt
    if(sidebar) sidebar.classList.add('collapsed');
    if(content) content.classList.remove('with-sidebar');
    if(!calendarInit){
      calendarInit=true;
    }
    fetch('/calendar_events').then(r=>r.json()).then(data=>{
      ganttEvents=data;
      renderGantt();
    });
  } else {
    // Restore sidebar for reservations view
    if(sidebar) sidebar.classList.remove('collapsed');
    if(content) content.classList.add('with-sidebar');
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
}
function validate(){
  let fields = [['f-titre','العنوان'],['f-organisateur','المنظم'],['f-etage','الطابق'],['f-genre','الجنس'],['f-periode','الفترة'],['f-debut','البداية'],['f-fin','النهاية']];
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

// ── SORT TABLE ────────────────────────────────────────────────────
let sortCol = -1, sortAsc = true;
function sortTable(col){
  let tbody = document.getElementById('tbody');
  if(!tbody) return;
  let rows = Array.from(tbody.querySelectorAll('tr'));
  if(sortCol === col){ sortAsc = !sortAsc; }
  else { sortCol = col; sortAsc = true; }
  for(let i=1;i<=11;i++){
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
            session["user"] = row[0]; session["role"] = row[1]; return redirect("/")
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    session.clear(); return redirect("/login")

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
                                    genre, periode, organisateur, type, etage
                             FROM reservations ORDER BY salle, date_debut""")
    conn.close()
    events = []
    for r in rows:
        events.append({
            "id": r[0], "course_code": r[1], "titre": r[2], "salle": r[3],
            "date_debut": r[4], "date_fin": r[5],
            "genre": r[6], "periode": r[7], "organisateur": r[8],
            "type": r[9], "etage": r[10]
        })
    return jsonify(events)

SALLE_TO_ETAGE = {}
for s in SALLES:
    SALLE_TO_ETAGE[s["nom"]] = s["etage"]

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
        debut        = str(row.get("debut", "")).strip()
        fin          = str(row.get("fin", "")).strip()
        periode      = str(row.get("periode", "")).strip()
        titre        = str(row.get("titre", "")).strip()
        organisateur = str(row.get("organisateur", "")).strip()
        type_        = str(row.get("type", "")).strip()
        genre        = str(row.get("genre", "")).strip()

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
            date_debut=?, date_fin=?, titre=?, organisateur=?
            WHERE id=?""",
            (course_code, type_, etage, salle, genre, periode,
             debut, fin, titre, organisateur, id_))
        saved += 1

    conn.commit()
    conn.close()

    if saved:
        add_notification(session["user"], f"تم تعديل {saved} حجز دفعة واحدة")

    return jsonify({"ok": True, "saved": saved, "errors": errors})

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
        salle        = request.form.get("salle", "")
        debut        = request.form.get("debut", "")
        fin          = request.form.get("fin", "")
        periode      = request.form.get("periode", "")
        course_code  = request.form.get("course_code", "").strip()
        conflict = fetchone(conn, """SELECT id FROM reservations
            WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=?""",
            (salle, periode, fin, debut))
        if conflict:
            flash("⚠️ تعارض في الحجز: القاعة محجوزة في هذه الفترة", "error")
            conn.close(); return redirect("/")
        execute(conn, """INSERT INTO reservations
            (course_code,type,etage,salle,genre,periode,date_debut,date_fin,titre,organisateur,created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
            course_code,
            request.form.get("type"), request.form.get("etage"), salle,
            request.form.get("genre"), periode, debut, fin,
            request.form.get("titre"), request.form.get("organisateur"), session["user"]))
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

    # Explicit columns: id, course_code, type, etage, salle, genre, periode, date_debut, date_fin, titre, organisateur
    q = """SELECT id, course_code, type, etage, salle, genre, periode,
                  date_debut, date_fin, titre, organisateur
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
                                    date_debut, date_fin, titre, organisateur, created_by
                             FROM reservations ORDER BY id""")
    conn.close()
    cols = ["id", "course code", "type", "etage", "salle", "genre", "periode",
            "date_debut", "date_fin", "titre", "organisateur", "created_by"]
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
        type_       = g("type")
        etage       = g("etage")
        salle       = g("salle")
        genre       = g("genre")
        periode     = g("periode")
        date_debut  = g("date_debut")[:10] if g("date_debut") else ""
        date_fin    = g("date_fin")[:10]   if g("date_fin")   else ""
        titre       = g("titre")
        organisateur = g("organisateur")
        created_by  = g("created_by") or session["user"]

        # Skip completely empty rows
        if not titre and not organisateur and not salle:
            skipped += 1
            continue

        try:
            execute(conn, """INSERT INTO reservations
                (course_code,type,etage,salle,genre,periode,date_debut,date_fin,titre,organisateur,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (course_code, type_, etage, salle, genre, periode,
                 date_debut, date_fin, titre, organisateur, created_by))
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
    debut        = request.form.get("debut", "").strip()
    fin          = request.form.get("fin", "").strip()
    periode      = request.form.get("periode", "").strip()
    titre        = request.form.get("titre", "").strip()
    organisateur = request.form.get("organisateur", "").strip()
    type_        = request.form.get("type", "").strip()
    genre        = request.form.get("genre", "").strip()
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
