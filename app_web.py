import os
import sqlite3
from flask import Flask, render_template, request, redirect, send_file, jsonify
import pandas as pd
from datetime import datetime

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservations.db")

SALLES = [
    "G 11","G 12","G 13",
    "L1 04","L1 05","L1 08","L1 18","L1 19","L1 20","L1 21","L1 22","L1 26",
    "L2 08","L2 09","L2 10","L2 11","L2 14","L2 28","L2 29","L2 30","L2 31","L2 32","L2 33","L2 34","L2 35",
    "L3 08","L3 09","L3 10","L3 11","L3 13","L3 27","L3 28","L3 29","L3 30","L3 31","L3 32","L3 33","L3 34",
    "L4 08","L4 09","L4 10","L4 11","L4 14","L4 29","L4 30","L4 31","L4 32","L4 33","L4 34","L4 35","L4 36"
]

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
        organisateur TEXT
    )
    """)
    conn.commit()
    conn.close()

def normalize_date(x):
    if pd.isna(x):
        return None
    if isinstance(x, (datetime, )):
        return x.strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(x, dayfirst=False, errors='coerce').strftime("%Y-%m-%d")
    except:
        return None

@app.route("/", methods=["GET", "POST"])
def index():
    init_db()
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        id_ = request.form.get("id")
        action = request.form.get("action")

        payload = (
            request.form.get("type"),
            request.form.get("etage"),
            request.form.get("salle"),
            request.form.get("genre"),
            request.form.get("periode"),
            request.form.get("debut"),
            request.form.get("fin"),
            request.form.get("titre"),
            request.form.get("organisateur"),
        )

        if action == "update" and id_:
            cur.execute("""
                UPDATE reservations
                SET type=?, etage=?, salle=?, genre=?, periode=?,
                    date_debut=?, date_fin=?, titre=?, organisateur=?
                WHERE id=?
            """, payload + (id_,))
        else:
            cur.execute("""
                INSERT INTO reservations
                (type, etage, salle, genre, periode, date_debut, date_fin, titre, organisateur)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, payload)

        conn.commit()
        return redirect("/")

    # --- Filters (optional)
    filters = []
    params = []

    f_type = request.args.get("type")
    f_etage = request.args.get("etage")
    f_genre = request.args.get("genre")
    f_periode = request.args.get("periode")
    f_debut = request.args.get("debut")
    f_fin = request.args.get("fin")

    if f_type:
        filters.append("type=?"); params.append(f_type)
    if f_etage:
        filters.append("etage=?"); params.append(f_etage)
    if f_genre:
        filters.append("genre=?"); params.append(f_genre)
    if f_periode:
        filters.append("periode=?"); params.append(f_periode)
    if f_debut:
        filters.append("date_debut>=?"); params.append(f_debut)
    if f_fin:
        filters.append("date_fin<=?"); params.append(f_fin)

    sql = "SELECT * FROM reservations"
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    sql += " ORDER BY id DESC"

    cur.execute(sql, params)
    data = cur.fetchall()
    conn.close()

    return render_template("index.html", data=data, salles=SALLES)

@app.route("/delete", methods=["POST"])
def delete():
    ids = request.form.getlist("ids[]")
    if not ids:
        return redirect("/")
    conn = get_db()
    cur = conn.cursor()
    cur.executemany("DELETE FROM reservations WHERE id=?", [(i,) for i in ids])
    conn.commit()
    conn.close()
    return redirect("/")

# --- Export Excel
@app.route("/export")
def export_excel():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM reservations", conn)
    conn.close()
    path = os.path.join(BASE_DIR, "export.xlsx")
    df.to_excel(path, index=False)
    return send_file(path, as_attachment=True)

# --- Import Excel
@app.route("/import", methods=["POST"])
def import_excel():
    file = request.files.get("file")
    if not file:
        return redirect("/")

    df = pd.read_excel(file)

    conn = get_db()
    cur = conn.cursor()

    for _, row in df.iterrows():
        cur.execute("""
        INSERT INTO reservations
        (type, etage, salle, genre, periode, date_debut, date_fin, titre, organisateur)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get("type"),
            row.get("etage"),
            row.get("salle"),
            row.get("genre"),
            row.get("periode"),
            normalize_date(row.get("date_debut")),
            normalize_date(row.get("date_fin")),
            row.get("titre"),
            row.get("organisateur"),
        ))

    conn.commit()
    conn.close()
    return redirect("/")

# --- Availability (for coloring)
@app.route("/disponibilite", methods=["POST"])
def dispo():
    debut = request.json.get("debut")
    fin = request.json.get("fin")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT salle FROM reservations
        WHERE date_debut <= ? AND date_fin >= ?
    """, (fin, debut))
    occupees = [r[0] for r in cur.fetchall()]
    conn.close()
    return jsonify({"occupees": occupees})

# --- Assign salle to selected row
@app.route("/assign", methods=["POST"])
def assign():
    id_ = request.json.get("id")
    salle = request.json.get("salle")
    if not id_:
        return "no id", 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE reservations SET salle=? WHERE id=?", (salle, id_))
    conn.commit()
    conn.close()
    return "ok"

if __name__ == "__main__":
    app.run(debug=True)
