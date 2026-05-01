import os
import sqlite3
from flask import Flask, render_template, request

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservations.db")


# 🔥 SALLES
SALLES = [
    {"type": "class", "nom": "G 11", "etage": "ground floor", "default": "mix", "matin": "male", "soir": "male"},
    {"type": "class", "nom": "G 12", "etage": "ground floor", "default": "mix", "matin": "female", "soir": "male"},
    {"type": "class", "nom": "G 13", "etage": "ground floor", "default": "mix", "matin": "female", "soir": "male"},
    {"type": "class", "nom": "L1 04", "etage": "first floor", "default": "mix", "matin": "female", "soir": "male"},
    {"type": "class", "nom": "L1 05", "etage": "first floor", "default": "mix", "matin": "female", "soir": "male"},
    {"type": "Lab", "nom": "L1 08", "etage": "first floor", "default": "mix", "matin": "female", "soir": "male"},
]


# 🔧 Connexion DB (fix Render)
def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# 🔧 Création table
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


# 🔥 IMPORTANT : exécuté au démarrage (Render OK)
init_db()


# 🟢 ROUTE PRINCIPALE
@app.route("/", methods=["GET", "POST"])
def index():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        try:
            cur.execute("""
                INSERT INTO reservations
                (type, salle, etage, section, titre, organisateur, date_debut, date_fin, periode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.form.get("type"),
                request.form.get("salle"),
                request.form.get("etage"),
                request.form.get("section"),
                request.form.get("titre"),
                request.form.get("organisateur"),
                request.form.get("debut"),
                request.form.get("fin"),
                request.form.get("periode")
            ))
            conn.commit()
        except Exception as e:
            print("ERREUR DB:", e)

    cur.execute("SELECT * FROM reservations ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()

    return render_template("index.html", data=data, salles=SALLES)


# 🔧 lancement local seulement
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
