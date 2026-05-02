import os
import sqlite3
from flask import Flask, render_template, request, redirect, jsonify

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

@app.route("/")
def index():
    init_db()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reservations ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()
    return render_template("index.html", data=data, salles=SALLES)

# 🔥 API: récupérer salles occupées selon dates
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

# 🔥 attribution salle
@app.route("/assign", methods=["POST"])
def assign():
    id_ = request.json.get("id")
    salle = request.json.get("salle")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE reservations SET salle=? WHERE id=?", (salle, id_))
    conn.commit()
    conn.close()

    return "ok"

if __name__ == "__main__":
    app.run(debug=True)
