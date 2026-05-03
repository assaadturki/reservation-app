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

INDEX_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>حجز القاعات</title>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.css" rel="stylesheet">
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
.content{flex:1;margin-right:260px;transition:margin-right .3s ease;min-width:0;padding:10px 12px;overflow-x:auto}
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
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{background:var(--thead);color:#fff;font-weight:700;text-align:center;padding:8px 10px;white-space:nowrap;font-size:11px;letter-spacing:.3px;border-left:1px solid rgba(255,255,255,.1)}
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
.chip-m{background:#2980b9}.chip-f{background:#e67e22}
.chip-s{background:#27ae60}.chip-e{background:#8e44ad}

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
        <select id="f-genre">
          <option value="">اختر</option><option value="رجال">رجال</option><option value="نساء">نساء</option>
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
    <button class="btn btn-edit" id="btn-edit" onclick="submitEdit()">✏️ تعديل الحجز</button>
    <button class="btn btn-reset" onclick="resetForm()">↺ إعادة تعيين</button>
    <button class="btn btn-cancel" id="btn-cancel" onclick="resetForm()">✕ إلغاء التعديل</button>

    <!-- Hidden forms -->
    <form method="POST" action="/" id="form-save" style="display:none">
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
      <input type="hidden" name="id" id="he-id">
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
        <div class="sf" style="flex:1;min-width:140px;"><label>بحث</label><input type="text" name="search" placeholder="عنوان، منظم، قاعة..." value="{{ search }}" style="width:100%;"></div>
        <div class="sf"><label>العنوان</label><input type="text" name="titre_f" placeholder="العنوان" value="{{ request.args.get('titre_f','') }}" style="width:100px;"></div>
        <div class="sf"><label>المنظم</label><input type="text" name="org_f" placeholder="المنظم" value="{{ request.args.get('org_f','') }}" style="width:100px;"></div>
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
        <button type="submit" class="btn-search">بحث</button>
        <a href="/" class="btn-clear">مسح</a>
      </form>

      <div class="table-wrap">
        <div class="table-header">
          <h2>قائمة الحجوزات</h2>
          <span class="count-badge">{{ data|length }} حجز</span>
          <button type="button" class="btn btn-del" onclick="deleteSelected()">حذف المحدد</button>
        </div>
        {% if data %}
        <table id="table"><thead><tr>
          <th><input type="checkbox" id="select-all" onchange="toggleAll(this)"></th>
          <th>#</th><th>النوع</th><th>الطابق</th><th>القاعة</th><th>الجنس</th><th>الفترة</th>
          <th>البداية</th><th>النهاية</th><th>العنوان</th><th>المنظم</th>
        </tr></thead><tbody>
        {% for r in data %}
        <tr onclick="fillForm({{ r[0] }},'{{ r[1] }}','{{ r[2] }}','{{ r[3] }}','{{ r[4] }}','{{ r[5] }}','{{ r[6] }}','{{ r[7] }}','{{ r[8] }}','{{ r[9] }}')" data-id="{{ r[0] }}">
          <td onclick="event.stopPropagation()"><input type="checkbox" class="row-check" value="{{ r[0] }}"></td>
          <td>{{ r[0] }}</td>
          <td><span class="chip {% if r[1]=='قاعة' %}chip-q{% else %}chip-lab{% endif %}">{{ r[1] }}</span></td>
          <td>{{ r[2] }}</td>
          <td><strong>{{ r[3] }}</strong></td>
          <td><span class="chip {% if r[4]=='رجال' %}chip-m{% else %}chip-f{% endif %}">{{ r[4] }}</span></td>
          <td><span class="chip {% if r[5]=='صباحي' %}chip-s{% else %}chip-e{% endif %}">{{ r[5] }}</span></td>
          <td>{{ r[6] }}</td><td>{{ r[7] }}</td><td>{{ r[8] }}</td>
          <td style="color:var(--muted);">{{ r[9] }}</td>
        </tr>
        {% endfor %}
        </tbody></table>
        {% else %}<div class="empty-state">📭 لا توجد حجوزات مطابقة</div>{% endif %}
      </div>
    </div>

    <!-- CALENDAR PANEL -->
    <div id="panel-calendar" style="display:none;">
      <div id="calendar-container"><div id="calendar"></div></div>
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

<script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js"></script>
<script>
// ── DATA ──────────────────────────────────────────────────────────
const SALLES = {{ salles|tojson }};
let currentEditId = null;
let currentEditSalle = '';
let selectedSalle = '';

// ── SALLE GRID ────────────────────────────────────────────────────
function renderSalleGrid(preselect){
  let etage = document.getElementById('f-etage').value;
  let type  = document.getElementById('f-type').value;
  let grid  = document.getElementById('salle-grid');
  selectedSalle = preselect || '';
  document.getElementById('f-salle').value = selectedSalle;
  document.getElementById('salle-selected-label').textContent = selectedSalle ? '— '+selectedSalle : '';

  if(!etage){ grid.innerHTML='<span style="color:var(--muted);font-size:11px;grid-column:1/-1;text-align:center;padding:12px;">اختر الطابق أولاً</span>'; return; }

  let filtered = SALLES.filter(s=> s.etage===etage && (!type || s.type===type));

  if(!filtered.length){ grid.innerHTML='<span style="color:var(--muted);font-size:11px;grid-column:1/-1;text-align:center;padding:10px;">لا توجد قاعات</span>'; return; }

  // All buttons active — conflict is checked via API when dates+periode are set
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

// ── SUBMIT SAVE ───────────────────────────────────────────────────
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
function fillForm(id,type,etage,salle,genre,periode,debut,fin,titre,organisateur){
  currentEditId    = id;
  currentEditSalle = salle;   // remember which salle this record already owns
  selectedSalle    = salle;
  document.getElementById('f-organisateur').value = organisateur;
  document.getElementById('f-etage').value        = etage;
  document.getElementById('f-type').value         = type;
  document.getElementById('f-genre').value        = genre;
  document.getElementById('f-periode').value      = periode;
  document.getElementById('f-debut').value        = debut;
  document.getElementById('f-fin').value          = fin;
  document.getElementById('f-salle').value        = salle;
  selectedSalle = salle;

  renderSalleGrid(salle);

  // Switch buttons to edit mode
  document.getElementById('btn-save').style.display='none';
  document.getElementById('btn-edit').style.display='flex';
  document.getElementById('btn-cancel').style.display='flex';
  document.getElementById('conflict-box').classList.remove('show');

  // Highlight row
  document.querySelectorAll('#table tbody tr').forEach(r=>r.classList.remove('selected-row'));
  let row = document.querySelector(`#table tbody tr[data-id="${id}"]`);
  if(row){row.classList.add('selected-row'); row.scrollIntoView({block:'nearest',behavior:'smooth'});}

  // Scroll sidebar to top
  document.querySelector('.sidebar').scrollTop=0;
  checkConflict();
}

// ── RESET ─────────────────────────────────────────────────────────
function resetForm(){
  currentEditId = null; currentEditSalle = ''; selectedSalle = '';
  ['f-titre','f-organisateur','f-debut','f-fin'].forEach(id=>document.getElementById(id).value='');
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

// ── TABLE SELECTION & DELETE ──────────────────────────────────────
function toggleAll(m){document.querySelectorAll('.row-check').forEach(cb=>{cb.checked=m.checked;});}
async function deleteSelected(){
  let sel=[...document.querySelectorAll('.row-check:checked')];
  if(!sel.length){alert('اختر عناصر للحذف');return;}
  if(!confirm('حذف '+sel.length+' عنصر؟'))return;
  await Promise.all(sel.map(el=>fetch('/delete',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'id='+el.value}).then(()=>el.closest('tr').remove())));
}

// ── TABS ──────────────────────────────────────────────────────────
let calendarInit=false;
function switchTab(tab,btn){
  document.getElementById('panel-reservations').style.display = tab==='reservations'?'block':'none';
  document.getElementById('panel-calendar').style.display     = tab==='calendar'?'block':'none';
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if(tab==='calendar'&&!calendarInit){initCalendar();calendarInit=true;}
}

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

// ── CALENDAR ─────────────────────────────────────────────────────
function initCalendar(){
  new FullCalendar.Calendar(document.getElementById('calendar'),{
    initialView:'dayGridMonth',direction:'rtl',
    headerToolbar:{start:'prev,next today',center:'title',end:'dayGridMonth,timeGridWeek,listWeek'},
    events:'/calendar_events',
    eventClick:function(info){
      let p=info.event.extendedProps;
      alert('📅 '+info.event.title+'\n🏢 '+p.salle+'\n👤 '+p.organisateur+'\n⏰ '+p.periode);
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

@app.route("/update", methods=["POST"])
@login_required
def update():
    id_     = request.form.get("id")
    salle   = request.form.get("salle", "")
    debut   = request.form.get("debut", "")
    fin     = request.form.get("fin", "")
    periode = request.form.get("periode", "")
    conn = get_conn()
    # conflict check excluding current record
    conflict = conn.execute("""SELECT id FROM reservations
        WHERE salle=? AND periode=? AND date_debut<=? AND date_fin>=? AND id!=?""",
        (salle, periode, fin, debut, id_)).fetchone()
    if conflict:
        flash("⚠️ تعارض في الحجز: القاعة محجوزة في هذه الفترة", "error")
        conn.close(); return redirect("/")
    conn.execute("""UPDATE reservations SET
        type=?, etage=?, salle=?, genre=?, periode=?,
        date_debut=?, date_fin=?, titre=?, organisateur=?
        WHERE id=?""", (
        request.form.get("type"), request.form.get("etage"), salle,
        request.form.get("genre"), periode, debut, fin,
        request.form.get("titre"), request.form.get("organisateur"), id_))
    conn.commit()
    add_notification(session["user"], f"تم تعديل الحجز #{id_}: «{request.form.get('titre')}»")
    conn.close()
    flash("✅ تم تعديل الحجز بنجاح", "success")
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
