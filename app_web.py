import os
import sqlite3
import hashlib
from functools import wraps
from datetime import datetime, timedelta

import pandas as pd
from flask import Flask, request, redirect, send_file, session, jsonify, flash, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change_this_secret_key_in_production")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservations.db")

# Init DB immediately at import time so tables exist before any request
def _bootstrap_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT, etage TEXT, salle TEXT, genre TEXT, periode TEXT,
        date_debut TEXT, date_fin TEXT, titre TEXT, organisateur TEXT,
        created_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        role TEXT DEFAULT 'user', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT, message TEXT, is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("SELECT COUNT(*) FROM users WHERE username='admin'")
    if c.fetchone()[0] == 0:
        import hashlib
        c.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
                  ("admin", hashlib.sha256(b"admin123").hexdigest(), "admin"))
    conn.commit()
    conn.close()

_bootstrap_db()

SALLES = [
    {"nom": "G 11", "etage": "الأرضي", "type": "قاعة"},
    {"nom": "G 12", "etage": "الأرضي", "type": "قاعة"},
    {"nom": "G 13", "etage": "الأرضي", "type": "مختبر"},
    {"nom": "L1 04", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 05", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 08", "etage": "الأول", "type": "مختبر"},
    {"nom": "L1 18", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 19", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 20", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 21", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 22", "etage": "الأول", "type": "قاعة"},
    {"nom": "L1 26", "etage": "الأول", "type": "مختبر"},
    {"nom": "L2 08", "etage": "الثاني", "type": "مختبر"},
    {"nom": "L2 09", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 10", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 11", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 14", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 28", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 29", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 30", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 31", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 32", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 33", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 34", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L2 35", "etage": "الثاني", "type": "قاعة"},
    {"nom": "L3 08", "etage": "الثالث", "type": "مختبر"},
    {"nom": "L3 09", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 10", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 11", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 13", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 27", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 28", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 29", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 30", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 31", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 32", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 33", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L3 34", "etage": "الثالث", "type": "قاعة"},
    {"nom": "L4 08", "etage": "الرابع", "type": "مختبر"},
    {"nom": "L4 09", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 10", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 11", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 14", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 29", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 30", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 31", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 32", "etage": "الرابع", "type": "قاعة"},
    {"nom": "L4 33", "etage": "الرابع", "type": "قاعة"},
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
</div></body></html>"""

REGISTER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>إدارة المستخدمين</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1117;--card:#1a1d27;--border:#2a2d3e;--accent:#4f6ef7;--accent2:#7c3aed;--text:#e2e8f0;--muted:#64748b}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:24px}
.topbar{display:flex;align-items:center;gap:16px;margin-bottom:32px;background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px 24px}
.topbar h1{font-size:20px;font-weight:700;flex:1}
a.back{background:var(--border);color:var(--text);border:none;border-radius:8px;padding:8px 16px;font-family:'Cairo',sans-serif;font-size:14px;text-decoration:none}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:28px}
.card h2{font-size:17px;font-weight:700;margin-bottom:20px}
.field{margin-bottom:16px}.field label{display:block;font-size:13px;font-weight:600;margin-bottom:6px;color:var(--muted)}
.field input,.field select{width:100%;background:var(--bg);border:1.5px solid var(--border);border-radius:8px;color:var(--text);font-family:'Cairo',sans-serif;font-size:14px;padding:10px 14px;outline:none}
.field input:focus,.field select:focus{border-color:var(--accent)}
.field select option{background:var(--card)}
.btn{border:none;border-radius:8px;font-family:'Cairo',sans-serif;font-size:14px;font-weight:700;padding:10px 20px;cursor:pointer;transition:opacity .2s}
.btn-primary{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;width:100%;padding:12px;font-size:15px}
.btn-danger{background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3);padding:6px 14px;font-size:13px}
.btn:hover{opacity:.85}
.flash{padding:10px 16px;border-radius:8px;font-size:14px;margin-bottom:16px;font-weight:600}
.flash.error{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);color:#f87171}
.flash.success{background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.3);color:#4ade80}
table{width:100%;border-collapse:collapse;font-size:14px}
th{color:var(--muted);font-weight:600;text-align:right;padding:10px 12px;border-bottom:1px solid var(--border)}
td{padding:12px;border-bottom:1px solid rgba(42,45,62,.5)}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700}
.badge-admin{background:rgba(79,110,247,.15);color:#818cf8;border:1px solid rgba(79,110,247,.3)}
.badge-user{background:rgba(100,116,139,.15);color:#94a3b8;border:1px solid rgba(100,116,139,.3)}
</style></head><body>
<div class="topbar"><a href="/" class="back">← رجوع</a><h1>👥 إدارة المستخدمين</h1></div>
{% with messages = get_flashed_messages(with_categories=true) %}{% for cat,msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}{% endwith %}
<div class="grid">
  <div class="card"><h2>➕ إنشاء مستخدم جديد</h2>
    <form method="POST" action="/register">
      <div class="field"><label>اسم المستخدم</label><input type="text" name="username" required></div>
      <div class="field"><label>كلمة المرور</label><input type="password" name="password" required></div>
      <div class="field"><label>الصلاحية</label>
        <select name="role"><option value="user">مستخدم عادي</option><option value="admin">مسؤول</option></select>
      </div>
      <button type="submit" class="btn btn-primary">إنشاء المستخدم</button>
    </form>
  </div>
  <div class="card"><h2>📋 قائمة المستخدمين</h2>
    <table><tr><th>المستخدم</th><th>الصلاحية</th><th>الإجراء</th></tr>
    {% for u in users %}<tr>
      <td>{{ u[1] }}</td>
      <td><span class="badge {% if u[2]=='admin' %}badge-admin{% else %}badge-user{% endif %}">{{ 'مسؤول' if u[2]=='admin' else 'مستخدم' }}</span></td>
      <td>{% if u[1] != 'admin' %}<form method="POST" action="/delete_user" style="display:inline;" onsubmit="return confirm('حذف؟')">
        <input type="hidden" name="id" value="{{ u[0] }}"><button type="submit" class="btn btn-danger">حذف</button></form>{% endif %}</td>
    </tr>{% endfor %}</table>
  </div>
</div></body></html>"""

INDEX_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>حجز القاعات</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.css" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1117;--card:#1a1d27;--card2:#1e2130;--border:#2a2d3e;--accent:#4f6ef7;--accent2:#7c3aed;--green:#10b981;--red:#ef4444;--text:#e2e8f0;--muted:#64748b}
body{font-family:'Cairo',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;direction:rtl}
.topbar{background:var(--card);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;gap:16px;height:64px;position:sticky;top:0;z-index:100}
.brand{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:900}
.brand-icon{width:36px;height:36px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px}
.tabs{display:flex;gap:4px;margin:0 auto}
.tab{background:none;border:none;color:var(--muted);font-family:'Cairo',sans-serif;font-size:14px;font-weight:600;padding:8px 18px;border-radius:8px;cursor:pointer;transition:all .2s;text-decoration:none;display:inline-block}
.tab:hover{background:var(--border);color:var(--text)}.tab.active{background:var(--accent);color:#fff}
.actions{display:flex;align-items:center;gap:12px}
.notif-btn{position:relative;background:var(--card2);border:1px solid var(--border);color:var(--text);border-radius:10px;width:40px;height:40px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:18px;transition:background .2s}
.notif-btn:hover{background:var(--border)}
.notif-badge{position:absolute;top:-4px;left:-4px;background:var(--red);color:#fff;border-radius:10px;font-size:11px;font-weight:700;padding:1px 6px;display:none}
.user-chip{display:flex;align-items:center;gap:8px;background:var(--card2);border:1px solid var(--border);border-radius:10px;padding:6px 14px;font-size:14px;font-weight:600}
.role-badge{font-size:11px;padding:2px 8px;border-radius:6px;font-weight:700}
.role-admin{background:rgba(79,110,247,.2);color:#818cf8}.role-user{background:rgba(100,116,139,.2);color:#94a3b8}
a.logout{background:none;border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:7px 14px;font-family:'Cairo',sans-serif;font-size:13px;text-decoration:none;transition:all .2s}
a.logout:hover{border-color:var(--accent);color:var(--accent)}
.main{padding:24px;max-width:1600px;margin:0 auto}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:20px 24px;display:flex;align-items:center;gap:16px;transition:border-color .2s}
.stat:hover{border-color:var(--accent)}.stat-icon{font-size:28px}.stat-val{font-size:28px;font-weight:900;line-height:1}.stat-label{font-size:13px;color:var(--muted);margin-top:2px}
.flash{padding:12px 18px;border-radius:10px;font-size:14px;font-weight:600;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.flash.error{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#f87171}
.flash.success{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.3);color:#4ade80}
.panel{display:none}.panel.active{display:block}
.form-card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:28px;margin-bottom:24px}
.form-card h2{font-size:17px;font-weight:700;margin-bottom:20px}
.form-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}
.field{display:flex;flex-direction:column;gap:6px}
.field label{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.field input,.field select{background:var(--bg);border:1.5px solid var(--border);border-radius:9px;color:var(--text);font-family:'Cairo',sans-serif;font-size:14px;padding:10px 13px;transition:border-color .2s,box-shadow .2s;outline:none;height:42px}
.field input:focus,.field select:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(79,110,247,.12)}
.field select option{background:var(--card)}
.salle-wrapper{position:relative}
.salle-box{position:absolute;top:calc(100% + 4px);right:0;left:0;background:var(--card2);border:1.5px solid var(--accent);border-radius:10px;max-height:200px;overflow-y:auto;z-index:50;box-shadow:0 8px 24px rgba(0,0,0,.4);display:none}
.salle-box.open{display:block}
.salle-item{padding:9px 13px;font-size:13px;cursor:pointer;transition:background .15s;border-bottom:1px solid var(--border)}
.salle-item:last-child{border-bottom:none}.salle-item:hover{background:var(--border)}.salle-item.selected{background:var(--accent);color:#fff}
.conflict-msg{display:none;padding:10px 14px;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.35);border-radius:9px;color:#f87171;font-size:13px;font-weight:600;margin-top:12px;grid-column:1/-1}
.conflict-msg.visible{display:flex;align-items:center;gap:8px}
.form-actions{display:flex;gap:12px;margin-top:20px;align-items:center;flex-wrap:wrap}
.btn{border:none;border-radius:9px;font-family:'Cairo',sans-serif;font-size:14px;font-weight:700;padding:11px 22px;cursor:pointer;transition:all .2s;display:inline-flex;align-items:center;gap:6px;text-decoration:none}
.btn-primary{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff}.btn-primary:hover{opacity:.88;transform:translateY(-1px)}.btn-primary:disabled{opacity:.4;cursor:not-allowed;transform:none}
.btn-danger{background:rgba(239,68,68,.12);color:#f87171;border:1px solid rgba(239,68,68,.3)}.btn-danger:hover{background:rgba(239,68,68,.2)}
.btn-secondary{background:var(--card2);color:var(--text);border:1px solid var(--border)}.btn-secondary:hover{border-color:var(--accent);color:var(--accent)}
.btn-green{background:rgba(16,185,129,.12);color:#34d399;border:1px solid rgba(16,185,129,.3)}.btn-green:hover{background:rgba(16,185,129,.2)}
.search-bar{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px 20px;margin-bottom:16px;display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}
.search-bar input,.search-bar select{background:var(--bg);border:1.5px solid var(--border);border-radius:9px;color:var(--text);font-family:'Cairo',sans-serif;font-size:14px;padding:9px 13px;outline:none;height:40px}
.search-bar input:focus,.search-bar select:focus{border-color:var(--accent)}
.sf{display:flex;flex-direction:column;gap:5px}.sf label{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.table-card{background:var(--card);border:1px solid var(--border);border-radius:16px;overflow:hidden}
.table-header{padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}
.table-header h2{font-size:16px;font-weight:700;flex:1}
.count-badge{background:var(--border);color:var(--muted);border-radius:20px;padding:3px 12px;font-size:13px;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:14px}
thead th{background:var(--card2);color:var(--muted);font-weight:700;text-align:center;padding:12px 14px;border-bottom:1px solid var(--border);white-space:nowrap;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
tbody td{padding:13px 14px;text-align:center;border-bottom:1px solid rgba(42,45,62,.5)}
tbody tr{transition:background .15s;cursor:pointer}tbody tr:hover{background:rgba(79,110,247,.05)}
tbody tr.selected-row{background:rgba(239,68,68,.08)}tbody tr:last-child td{border-bottom:none}
.chip{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700}
.chip-matin{background:rgba(37,99,235,.15);color:#60a5fa}.chip-soir{background:rgba(124,58,237,.15);color:#a78bfa}
.chip-male{background:rgba(16,185,129,.15);color:#34d399}.chip-female{background:rgba(245,158,11,.15);color:#fbbf24}
.chip-class{background:rgba(79,110,247,.15);color:#818cf8}.chip-lab{background:rgba(239,68,68,.15);color:#f87171}
#calendar-container{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:24px}
.fc{--fc-border-color:var(--border);--fc-page-bg-color:transparent;--fc-today-bg-color:rgba(79,110,247,.08)}
.fc .fc-toolbar-title{font-family:'Cairo',sans-serif;font-size:18px;color:var(--text)}
.fc .fc-button{background:var(--card2)!important;border:1px solid var(--border)!important;color:var(--text)!important;font-family:'Cairo',sans-serif!important}
.fc .fc-button:hover{background:var(--border)!important}
.fc .fc-button-primary:not(:disabled).fc-button-active{background:var(--accent)!important;border-color:var(--accent)!important}
.fc th{color:var(--muted);font-size:12px}.fc .fc-col-header-cell-cushion,.fc .fc-daygrid-day-number{color:var(--muted)}
.fc .fc-event{border-radius:6px;border:none!important;padding:2px 6px;font-size:12px;font-family:'Cairo',sans-serif}
.notif-drawer{position:fixed;top:0;left:0;bottom:0;width:360px;background:var(--card);border-left:1px solid var(--border);z-index:999;transform:translateX(-100%);transition:transform .3s ease;display:flex;flex-direction:column}
.notif-drawer.open{transform:translateX(0)}
.notif-drawer-header{padding:20px 20px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.notif-drawer-header h2{font-size:17px;font-weight:700}
.notif-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer}
.notif-list{flex:1;overflow-y:auto;padding:12px}
.notif-item{padding:12px 14px;border-radius:10px;background:var(--card2);border:1px solid var(--border);margin-bottom:8px;font-size:13px;line-height:1.6}
.notif-item.unread{border-color:rgba(79,110,247,.4);background:rgba(79,110,247,.06)}
.notif-time{font-size:11px;color:var(--muted);margin-top:4px}
.notif-mark-btn{margin:12px;background:var(--card2);border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:8px;font-family:'Cairo',sans-serif;font-size:13px;cursor:pointer;width:calc(100% - 24px)}
.notif-mark-btn:hover{border-color:var(--accent);color:var(--accent)}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:998;display:none}.overlay.show{display:block}
.empty-state{padding:48px;text-align:center;color:var(--muted)}.empty-state .icon{font-size:48px;margin-bottom:12px}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style></head><body>

<nav class="topbar">
  <div class="brand"><div class="brand-icon">🏛️</div><span>حجز القاعات</span></div>
  <div class="tabs">
    <button class="tab active" onclick="switchTab('reservations',this)">📋 الحجوزات</button>
    <button class="tab" onclick="switchTab('calendar',this)">📅 التقويم</button>
    {% if role == 'admin' %}<a href="/register" class="tab">👥 المستخدمون</a>{% endif %}
  </div>
  <div class="actions">
    <button class="notif-btn" onclick="openNotifDrawer()">🔔<span class="notif-badge" id="notif-badge">0</span></button>
    <div class="user-chip">
      <span>{{ user }}</span>
      <span class="role-badge {% if role=='admin' %}role-admin{% else %}role-user{% endif %}">{{ 'مسؤول' if role=='admin' else 'مستخدم' }}</span>
    </div>
    <a href="/logout" class="logout">خروج ↩</a>
  </div>
</nav>

<div class="main">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat,msg in messages %}<div class="flash {{ cat }}">{{ msg }}</div>{% endfor %}
  {% endwith %}

  <div class="stats">
    <div class="stat"><div class="stat-icon">📊</div><div><div class="stat-val">{{ total_count }}</div><div class="stat-label">إجمالي الحجوزات</div></div></div>
    <div class="stat"><div class="stat-icon">🏢</div><div><div class="stat-val">{{ occupied_today }}</div><div class="stat-label">قاعة مشغولة اليوم</div></div></div>
    <div class="stat"><div class="stat-icon">📅</div><div><div class="stat-val">{{ upcoming_count }}</div><div class="stat-label">حجوزات الأسبوع القادم</div></div></div>
  </div>

  <div id="panel-reservations" class="panel active">
    <div class="form-card"><h2>➕ حجز جديد</h2>
      <form method="POST" id="reservation-form">
        <div class="form-grid">
          <div class="field"><label>العنوان</label><input name="titre" placeholder="عنوان الحجز" required></div>
          <div class="field"><label>المنظم</label><input name="organisateur" placeholder="اسم المنظم" required></div>
          <div class="field"><label>الطابق</label>
            <select name="etage" id="etage" onchange="chargerSalles()">
              <option value="">اختر الطابق</option>
              <option value="الأرضي">الأرضي</option><option value="الأول">الأول</option>
              <option value="الثاني">الثاني</option><option value="الثالث">الثالث</option>
              <option value="الرابع">الرابع</option>
            </select></div>
          <div class="field"><label>النوع</label>
            <select name="type" id="type" onchange="chargerSalles()">
              <option value="">كل الأنواع</option><option value="قاعة">قاعة</option><option value="مختبر">مختبر</option>
            </select></div>
          <div class="field"><label>الجنس</label>
            <select name="genre">
              <option value="">اختر</option><option value="رجال">رجال</option><option value="نساء">نساء</option>
            </select></div>
          <div class="field"><label>الفترة</label>
            <select name="periode" id="periode" onchange="checkConflict()">
              <option value="">اختر</option><option value="صباحي">صباحي</option><option value="مسائي">مسائي</option>
            </select></div>
          <div class="field"><label>تاريخ البداية</label><input type="date" name="debut" id="debut" onchange="checkConflict()" required></div>
          <div class="field"><label>تاريخ النهاية</label><input type="date" name="fin" id="fin" onchange="checkConflict()" required></div>
          <div class="field salle-wrapper">
            <label>القاعة</label>
            <input name="salle" id="salle_input" placeholder="اختر القاعة..." readonly required onclick="toggleSalleBox()" style="cursor:pointer;">
            <div class="salle-box" id="salles">
              {% for s in salles %}
              <div class="salle-item" data-etage="{{ s.etage }}" data-type="{{ s.type }}" data-nom="{{ s.nom }}" onclick="selectSalle(this)">
                {{ s.nom }} <small style="color:var(--muted);font-size:11px;margin-right:6px;">{{ s.type }}</small>
              </div>
              {% endfor %}
            </div>
          </div>
          <div class="conflict-msg" id="conflict-msg">⚠️ <span id="conflict-text">تعارض في الحجز</span></div>
        </div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary" id="save-btn">💾 حفظ الحجز</button>
          <button type="button" class="btn btn-secondary" onclick="resetForm()">↺ إعادة تعيين</button>
        </div>
      </form>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:16px;padding-top:16px;border-top:1px solid var(--border);">
        <a href="/export" class="btn btn-green">📥 تصدير Excel</a>
        <form action="/import" method="POST" enctype="multipart/form-data" style="display:inline-flex;align-items:center;gap:8px;">
          <input type="file" name="file" accept=".xlsx,.xls" style="font-size:13px;color:var(--muted);">
          <button type="submit" class="btn btn-secondary">📤 استيراد</button>
        </form>
      </div>
    </div>

    <form method="GET" class="search-bar">
      <div class="sf" style="flex:1;min-width:180px;"><label>بحث</label><input type="text" name="search" placeholder="عنوان، منظم، قاعة..." value="{{ search }}" style="width:100%;"></div>
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
      </select></div>
      <div class="sf"><label>الفترة</label><select name="f_periode">
        <option value="">الكل</option><option value="صباحي" {% if f_periode=='صباحي' %}selected{% endif %}>صباحي</option>
        <option value="مسائي" {% if f_periode=='مسائي' %}selected{% endif %}>مسائي</option>
      </select></div>
      <div class="sf"><label>من</label><input type="date" name="f_debut" value="{{ f_debut }}"></div>
      <div class="sf"><label>إلى</label><input type="date" name="f_fin" value="{{ f_fin }}"></div>
      <button type="submit" class="btn btn-primary" style="height:40px;padding:0 16px;">🔍 بحث</button>
      <a href="/" class="btn btn-secondary" style="height:40px;padding:0 14px;">✕ مسح</a>
    </form>

    <div class="table-card">
      <div class="table-header">
        <h2>قائمة الحجوزات</h2>
        <span class="count-badge">{{ data|length }} حجز</span>
        <button type="button" class="btn btn-danger" onclick="deleteSelected()" style="margin-right:8px;">🗑️ حذف المحدد</button>
      </div>
      {% if data %}
      <table id="table"><thead><tr>
        <th><input type="checkbox" id="select-all" onchange="toggleAll(this)"></th>
        <th>#</th><th>النوع</th><th>الطابق</th><th>القاعة</th><th>الجنس</th><th>الفترة</th><th>البداية</th><th>النهاية</th><th>العنوان</th><th>المنظم</th>
      </tr></thead><tbody>
      {% for r in data %}
      <tr onclick="selectRow(this)">
        <td onclick="event.stopPropagation()"><input type="checkbox" class="row-check" value="{{ r[0] }}"></td>
        <td>{{ r[0] }}</td>
        <td><span class="chip {% if r[1]=='قاعة' %}chip-class{% else %}chip-lab{% endif %}">{{ r[1] }}</span></td>
        <td style="font-size:12px;color:var(--muted);">{{ r[2] }}</td>
        <td><strong>{{ r[3] }}</strong></td>
        <td><span class="chip {% if r[4]=='رجال' %}chip-male{% else %}chip-female{% endif %}">{{ r[4] }}</span></td>
        <td><span class="chip {% if r[5]=='صباحي' %}chip-matin{% else %}chip-soir{% endif %}">{{ r[5] }}</span></td>
        <td>{{ r[6] }}</td><td>{{ r[7] }}</td><td>{{ r[8] }}</td>
        <td style="color:var(--muted);">{{ r[9] }}</td>
      </tr>
      {% endfor %}
      </tbody></table>
      {% else %}<div class="empty-state"><div class="icon">📭</div><p>لا توجد حجوزات مطابقة</p></div>{% endif %}
    </div>
  </div>

  <div id="panel-calendar" class="panel">
    <div id="calendar-container"><div id="calendar"></div></div>
  </div>
</div>

<div class="overlay" id="overlay" onclick="closeNotifDrawer()"></div>
<div class="notif-drawer" id="notif-drawer">
  <div class="notif-drawer-header"><h2>🔔 الإشعارات</h2><button class="notif-close" onclick="closeNotifDrawer()">✕</button></div>
  <button class="notif-mark-btn" onclick="markAllRead()">تعليم الكل كمقروء</button>
  <div class="notif-list" id="notif-list"><p style="color:var(--muted);text-align:center;padding:20px;font-size:13px;">جاري التحميل...</p></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js"></script>
<script>
let calendarInit=false;
function switchTab(tab,btn){
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
  document.getElementById('panel-'+tab).classList.add('active');
  btn.classList.add('active');
  if(tab==='calendar'&&!calendarInit){initCalendar();calendarInit=true;}
}
function chargerSalles(){
  let etage=document.getElementById('etage').value,type=document.getElementById('type').value;
  document.querySelectorAll('.salle-item').forEach(s=>{
    let show=true;
    if(etage&&s.dataset.etage!==etage)show=false;
    if(type&&s.dataset.type!==type)show=false;
    s.style.display=show?'':'none';
  });
}
function toggleSalleBox(){let b=document.getElementById('salles');b.classList.toggle('open');if(b.classList.contains('open'))chargerSalles();}
function selectSalle(el){
  document.querySelectorAll('.salle-item').forEach(s=>s.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('salle_input').value=el.dataset.nom;
  document.getElementById('salles').classList.remove('open');
  checkConflict();
}
document.addEventListener('click',e=>{
  let box=document.getElementById('salles'),inp=document.getElementById('salle_input');
  if(box&&!box.contains(e.target)&&e.target!==inp)box.classList.remove('open');
});
let ct=null;
function checkConflict(){clearTimeout(ct);ct=setTimeout(_check,400);}
async function _check(){
  let salle=document.getElementById('salle_input').value,
      debut=document.getElementById('debut').value,
      fin=document.getElementById('fin').value,
      periode=document.getElementById('periode').value,
      msg=document.getElementById('conflict-msg'),btn=document.getElementById('save-btn');
  if(!salle||!debut||!fin||!periode){msg.classList.remove('visible');btn.disabled=false;return;}
  try{
    let r=await fetch('/check_conflict?'+new URLSearchParams({salle,debut,fin,periode}));
    let d=await r.json();
    if(d.conflict){msg.classList.add('visible');document.getElementById('conflict-text').textContent=d.detail;btn.disabled=true;}
    else{msg.classList.remove('visible');btn.disabled=false;}
  }catch(e){}
}
function selectRow(row){row.classList.toggle('selected-row');let cb=row.querySelector('.row-check');cb.checked=!cb.checked;}
function toggleAll(m){document.querySelectorAll('.row-check').forEach(cb=>{cb.checked=m.checked;cb.closest('tr').classList.toggle('selected-row',m.checked);});}
async function deleteSelected(){
  let sel=[...document.querySelectorAll('.row-check:checked')];
  if(!sel.length){alert('اختر عناصر للحذف');return;}
  if(!confirm('هل تريد حذف '+sel.length+' عنصر؟'))return;
  await Promise.all(sel.map(el=>fetch('/delete',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'id='+el.value}).then(()=>el.closest('tr').remove())));
}
function resetForm(){
  document.getElementById('reservation-form').reset();
  document.getElementById('salle_input').value='';
  document.querySelectorAll('.salle-item').forEach(s=>s.classList.remove('selected'));
  document.getElementById('conflict-msg').classList.remove('visible');
  document.getElementById('save-btn').disabled=false;
}
async function loadNotifications(){
  try{
    let r=await fetch('/notifications'),d=await r.json();
    let badge=document.getElementById('notif-badge');
    badge.textContent=d.unread;badge.style.display=d.unread>0?'block':'none';
    let list=document.getElementById('notif-list');
    if(!d.notifications.length){list.innerHTML='<p style="color:var(--muted);text-align:center;padding:20px;font-size:13px;">لا توجد إشعارات</p>';return;}
    list.innerHTML=d.notifications.map(n=>`<div class="notif-item ${n.is_read?'':'unread'}">${n.message}<div class="notif-time">${n.created_at}</div></div>`).join('');
  }catch(e){}
}
function openNotifDrawer(){document.getElementById('notif-drawer').classList.add('open');document.getElementById('overlay').classList.add('show');loadNotifications();}
function closeNotifDrawer(){document.getElementById('notif-drawer').classList.remove('open');document.getElementById('overlay').classList.remove('show');}
async function markAllRead(){await fetch('/notifications/read',{method:'POST'});document.getElementById('notif-badge').style.display='none';loadNotifications();}
setInterval(loadNotifications,30000);loadNotifications();
function initCalendar(){
  new FullCalendar.Calendar(document.getElementById('calendar'),{
    initialView:'dayGridMonth',direction:'rtl',
    headerToolbar:{start:'prev,next today',center:'title',end:'dayGridMonth,timeGridWeek,listWeek'},
    events:'/calendar_events',
    eventClick:function(info){
      let p=info.event.extendedProps;
      alert('📅 '+info.event.title+'\n\n🏢 القاعة: '+p.salle+'\n👤 المنظم: '+p.organisateur+'\n⏰ الفترة: '+p.periode);
    },height:'auto'
  }).render();
}
</script>
</body></html>"""

# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT, etage TEXT, salle TEXT, genre TEXT, periode TEXT,
        date_debut TEXT, date_fin TEXT, titre TEXT, organisateur TEXT,
        created_by TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        role TEXT DEFAULT 'user', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT, message TEXT, is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("SELECT COUNT(*) FROM users WHERE username='admin'")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)",
                  ("admin", hash_password("admin123"), "admin"))
    conn.commit(); conn.close()

def add_notification(user, message):
    conn = get_conn()
    conn.execute("INSERT INTO notifications (user,message) VALUES (?,?)", (user, message))
    conn.commit(); conn.close()

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
        row = conn.execute("SELECT username,role FROM users WHERE username=? AND password=?",
                           (u, hash_password(p))).fetchone()
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
            conn.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)", (u, hash_password(p), r))
            conn.commit(); flash(f"تم إنشاء المستخدم {u} بنجاح", "success")
        except sqlite3.IntegrityError:
            flash("اسم المستخدم موجود مسبقاً", "error")
        finally:
            conn.close()
        return redirect("/register")
    conn = get_conn()
    users = conn.execute("SELECT id,username,role,created_at FROM users ORDER BY id DESC").fetchall()
    conn.close()
    return render_template_string(REGISTER_TEMPLATE, users=users)

@app.route("/delete_user", methods=["POST"])
@admin_required
def delete_user():
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE id=? AND username!='admin'", (request.form.get("id"),))
    conn.commit(); conn.close(); return redirect("/register")

@app.route("/check_conflict")
@login_required
def check_conflict():
    salle = request.args.get("salle", "")
    debut = request.args.get("debut", "")
    fin   = request.args.get("fin", "")
    periode = request.args.get("periode", "")
    if not salle or not debut or not fin:
        return jsonify({"conflict": False})
    conn = get_conn()
    row = conn.execute("""SELECT titre,organisateur,date_debut,date_fin FROM reservations
                          WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=?""",
                       (salle, periode, fin, debut)).fetchone()
    conn.close()
    if row:
        return jsonify({"conflict": True,
                        "detail": f"القاعة محجوزة: «{row[0]}» بواسطة {row[1]} من {row[2]} إلى {row[3]}"})
    return jsonify({"conflict": False})

@app.route("/notifications")
@login_required
def get_notifications():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id,message,is_read,created_at FROM notifications WHERE user=? ORDER BY id DESC LIMIT 20",
        (session["user"],)).fetchall()
    conn.close()
    notifs = [{"id": r[0], "message": r[1], "is_read": r[2], "created_at": r[3]} for r in rows]
    return jsonify({"notifications": notifs, "unread": sum(1 for n in notifs if not n["is_read"])})

@app.route("/notifications/read", methods=["POST"])
@login_required
def mark_read():
    conn = get_conn()
    conn.execute("UPDATE notifications SET is_read=1 WHERE user=?", (session["user"],))
    conn.commit(); conn.close(); return jsonify({"ok": True})

@app.route("/calendar_events")
@login_required
def calendar_events():
    conn = get_conn()
    rows = conn.execute("SELECT id,titre,salle,date_debut,date_fin,genre,periode,organisateur FROM reservations").fetchall()
    conn.close()
    colors = {"صباحي": "#2563eb", "مسائي": "#7c3aed"}
    return jsonify([{
        "id": r[0], "title": f"{r[1]} — {r[2]}", "start": r[3], "end": r[4],
        "color": colors.get(r[6], "#059669"),
        "extendedProps": {"salle": r[2], "organisateur": r[7], "periode": r[6], "genre": r[5]}
    } for r in rows])

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    init_db()
    conn = get_conn()
    if request.method == "POST":
        salle   = request.form.get("salle", "")
        debut   = request.form.get("debut", "")
        fin     = request.form.get("fin", "")
        periode = request.form.get("periode", "")
        conflict = conn.execute("""SELECT id FROM reservations
            WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=?""",
            (salle, periode, fin, debut)).fetchone()
        if conflict:
            flash("⚠️ تعارض في الحجز: القاعة محجوزة في هذه الفترة", "error")
            conn.close(); return redirect("/")
        conn.execute("""INSERT INTO reservations
            (type,etage,salle,genre,periode,date_debut,date_fin,titre,organisateur,created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (
            request.form.get("type"), request.form.get("etage"), salle,
            request.form.get("genre"), periode, debut, fin,
            request.form.get("titre"), request.form.get("organisateur"), session["user"]))
        conn.commit()
        titre = request.form.get("titre", "")
        users = conn.execute("SELECT username FROM users").fetchall()
        for u in users:
            add_notification(u[0], f"حجز جديد: «{titre}» في {salle} من {debut} إلى {fin}")
        conn.close(); return redirect("/")

    search    = request.args.get("search", "")
    f_etage   = request.args.get("f_etage", "")
    f_type    = request.args.get("f_type", "")
    f_genre   = request.args.get("f_genre", "")
    f_periode = request.args.get("f_periode", "")
    f_debut   = request.args.get("f_debut", "")
    f_fin     = request.args.get("f_fin", "")

    q = "SELECT * FROM reservations WHERE 1=1"; params = []
    if search:    q += " AND (titre LIKE ? OR organisateur LIKE ? OR salle LIKE ?)"; params += [f"%{search}%"] * 3
    if f_etage:   q += " AND etage=?";    params.append(f_etage)
    if f_type:    q += " AND type=?";     params.append(f_type)
    if f_genre:   q += " AND genre=?";    params.append(f_genre)
    if f_periode: q += " AND periode=?";  params.append(f_periode)
    if f_debut:   q += " AND date_debut>=?"; params.append(f_debut)
    if f_fin:     q += " AND date_fin<=?";   params.append(f_fin)
    q += " ORDER BY date_debut DESC"

    data = conn.execute(q, params).fetchall()
    today     = datetime.now().strftime("%Y-%m-%d")
    next_week = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    upcoming_count = conn.execute("SELECT COUNT(*) FROM reservations WHERE date_debut BETWEEN ? AND ?", (today, next_week)).fetchone()[0]
    total_count    = conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
    occupied_today = conn.execute("SELECT COUNT(DISTINCT salle) FROM reservations WHERE date_debut<=? AND date_fin>=?", (today, today)).fetchone()[0]
    conn.close()

    return render_template_string(INDEX_TEMPLATE,
        data=data, salles=SALLES, user=session["user"], role=session["role"],
        search=search, f_etage=f_etage, f_type=f_type, f_genre=f_genre,
        f_periode=f_periode, f_debut=f_debut, f_fin=f_fin,
        upcoming_count=upcoming_count, total_count=total_count, occupied_today=occupied_today)

@app.route("/export")
@login_required
def export_excel():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM reservations", conn); conn.close()
    path = os.path.join(BASE_DIR, "export.xlsx")
    df.to_excel(path, index=False)
    return send_file(path, as_attachment=True)

@app.route("/import", methods=["POST"])
@login_required
def import_excel():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("يرجى اختيار ملف Excel", "error")
        return redirect("/")
    try:
        df = pd.read_excel(file, engine="openpyxl")
    except Exception as e:
        flash(f"خطأ في قراءة الملف: {str(e)}", "error")
        return redirect("/")

    # Normalize column names: strip spaces, lowercase
    df.columns = [str(c).strip().lower() for c in df.columns]

    conn = get_conn()
    imported = 0
    for _, row in df.iterrows():
        def g(col, alt=None):
            for k in ([col] + ([alt] if alt else [])):
                if k in row and str(row[k]).strip() not in ("", "nan", "None"):
                    return str(row[k]).strip()
            return ""
        try:
            conn.execute("""INSERT INTO reservations
                (type,etage,salle,genre,periode,date_debut,date_fin,titre,organisateur,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                g("type"), g("etage"), g("salle"), g("genre"), g("periode"),
                g("date_debut")[:10] if g("date_debut") else "",
                g("date_fin")[:10]   if g("date_fin")   else "",
                g("titre"), g("organisateur"), session["user"]))
            imported += 1
        except Exception:
            continue
    conn.commit(); conn.close()
    flash(f"تم استيراد {imported} حجز بنجاح", "success")
    return redirect("/")

@app.route("/delete", methods=["POST"])
@login_required
def delete():
    id_ = request.form.get("id")
    conn = get_conn()
    row = conn.execute("SELECT titre,salle,created_by FROM reservations WHERE id=?", (id_,)).fetchone()
    if row and (session["role"] == "admin" or row[2] == session["user"]):
        conn.execute("DELETE FROM reservations WHERE id=?", (id_,))
        conn.commit()
        add_notification(session["user"], f"تم حذف الحجز: «{row[0]}» في {row[1]}")
    conn.close(); return jsonify({"ok": True})

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
