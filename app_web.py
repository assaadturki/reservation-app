import os
import sqlite3
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservations.db")


# 🔥 SALLES (tu peux compléter toute ta liste ici)
SALLES = [
    {"type": "class", "nom": "G 11", "etage": "ground floor", "default": "mix", "matin": "male", "soir": "male"},
    {"type": "class", "nom": "G 12", "etage": "ground floor", "default": "mix", "matin": "female", "soir": "male"},
    {"type": "class", "nom": "G 13", "etage": "ground floor", "default": "mix", "matin": "female", "soir": "male"},
    {"type": "class", "nom": "L1 04", "etage": "first floor", "default": "mix", "matin": "female", "soir": "male"},
    {"type": "class", "nom": "L1 05", "etage": "first floor", "default": "mix", "matin": "female", "soir": "male"},
    {"type": "Lab", "nom": "L1 08", "etage": "first floor", "default": "mix", "matin": "female", "soir": "male"},
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
            salle TEXT,
            etage TEXT,
            section TEXT,
            titre TEXT,
            organisateur TEXT,
            date_debut TEXT,
            date_fin TEXT,
            periode TEXT
        )
    """)
    conn.commit()
    conn.close()


@app.route("/", methods=["GET", "POST"])
def index():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        type_ = request.form.get("type")
        salle = request.form.get("salle")
        etage = request.form.get("etage")
        section = request.form.get("section")
        titre = request.form.get("titre")
        organisateur = request.form.get("organisateur")
        debut = request.form.get("debut")
        fin = request.form.get("fin")
        periode = request.form.get("periode")

        cur.execute("""
            INSERT INTO reservations
            (type, salle, etage, section, titre, organisateur, date_debut, date_fin, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (type_, salle, etage, section, titre, organisateur, debut, fin, periode))

        conn.commit()

    cur.execute("SELECT * FROM reservations ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()

    return render_template("index.html", data=data, salles=SALLES)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
