import os
import sqlite3
from flask import Flask, render_template, request

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservations.db")

SALLES = [
    {"nom": "G 11", "etage": "ground floor"},
    {"nom": "G 12", "etage": "ground floor"},
    {"nom": "G 13", "etage": "ground floor"},

    {"nom": "L1 04", "etage": "first floor"},
    {"nom": "L1 05", "etage": "first floor"},
    {"nom": "L1 08", "etage": "first floor"},
    {"nom": "L1 18", "etage": "first floor"},
    {"nom": "L1 19", "etage": "first floor"},
    {"nom": "L1 20", "etage": "first floor"},
    {"nom": "L1 21", "etage": "first floor"},
    {"nom": "L1 22", "etage": "first floor"},
    {"nom": "L1 26", "etage": "first floor"},

    {"nom": "L2 08", "etage": "second floor"},
    {"nom": "L2 09", "etage": "second floor"},
    {"nom": "L2 10", "etage": "second floor"},
    {"nom": "L2 11", "etage": "second floor"},
    {"nom": "L2 14", "etage": "second floor"},
    {"nom": "L2 28", "etage": "second floor"},
    {"nom": "L2 29", "etage": "second floor"},
    {"nom": "L2 30", "etage": "second floor"},
    {"nom": "L2 31", "etage": "second floor"},
    {"nom": "L2 32", "etage": "second floor"},
    {"nom": "L2 33", "etage": "second floor"},
    {"nom": "L2 34", "etage": "second floor"},
    {"nom": "L2 35", "etage": "second floor"},

    {"nom": "L3 08", "etage": "third floor"},
    {"nom": "L3 09", "etage": "third floor"},
    {"nom": "L3 10", "etage": "third floor"},
    {"nom": "L3 11", "etage": "third floor"},
    {"nom": "L3 13", "etage": "third floor"},
    {"nom": "L3 27", "etage": "third floor"},
    {"nom": "L3 28", "etage": "third floor"},
    {"nom": "L3 29", "etage": "third floor"},
    {"nom": "L3 30", "etage": "third floor"},
    {"nom": "L3 31", "etage": "third floor"},
    {"nom": "L3 32", "etage": "third floor"},
    {"nom": "L3 33", "etage": "third floor"},
    {"nom": "L3 34", "etage": "third floor"},

    {"nom": "L4 08", "etage": "fourth floor"},
    {"nom": "L4 09", "etage": "fourth floor"},
    {"nom": "L4 10", "etage": "fourth floor"},
    {"nom": "L4 11", "etage": "fourth floor"},
    {"nom": "L4 14", "etage": "fourth floor"},
    {"nom": "L4 29", "etage": "fourth floor"},
    {"nom": "L4 30", "etage": "fourth floor"},
    {"nom": "L4 31", "etage": "fourth floor"},
    {"nom": "L4 32", "etage": "fourth floor"},
    {"nom": "L4 33", "etage": "fourth floor"},
    {"nom": "L4 34", "etage": "fourth floor"},
    {"nom": "L4 35", "etage": "fourth floor"},
    {"nom": "L4 36", "etage": "fourth floor"},
]


def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            salle TEXT,
            etage TEXT,
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


init_db()


@app.route("/", methods=["GET", "POST"])
def index():
    conn = get_db()
    cur = conn.cursor()

    salles_filtrees = SALLES
    erreur = None

    if request.method == "POST":
        action = request.form.get("action")

        # 🔴 DELETE
        if action == "delete":
            selected_id = request.form.get("selected_id")
            if selected_id:
                cur.execute("DELETE FROM reservations WHERE id=?", (selected_id,))
                conn.commit()

        # 🔵 DISPONIBILITÉ
        elif action == "dispo":
            debut = request.form.get("debut")
            fin = request.form.get("fin")
            periode = request.form.get("periode")

            salles_filtrees = []

            for s in SALLES:
                cur.execute("""
                    SELECT * FROM reservations
                    WHERE salle=? AND periode=?
                    AND (date_debut <= ? AND date_fin >= ?)
                """, (s["nom"], periode, fin, debut))

                if not cur.fetchone():
                    salles_filtrees.append(s)

        # 🟢 RESERVER
        elif action == "reserver":
            salle = request.form.get("salle")
            debut = request.form.get("debut")
            fin = request.form.get("fin")
            periode = request.form.get("periode")

            cur.execute("""
                SELECT * FROM reservations
                WHERE salle=? AND periode=?
                AND (date_debut <= ? AND date_fin >= ?)
            """, (salle, periode, fin, debut))

            if cur.fetchone():
                erreur = "❌ Salle déjà réservée"
            else:
                cur.execute("""
                    INSERT INTO reservations
                    (type, salle, etage, genre, periode, date_debut, date_fin, titre, organisateur)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    request.form.get("type"),
                    salle,
                    request.form.get("etage"),
                    request.form.get("genre"),
                    periode,
                    debut,
                    fin,
                    request.form.get("titre"),
                    request.form.get("organisateur")
                ))
                conn.commit()

    cur.execute("SELECT * FROM reservations ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()

    return render_template("index.html", data=data, salles=salles_filtrees, erreur=erreur)


if __name__ == "__main__":
    app.run(debug=True)
