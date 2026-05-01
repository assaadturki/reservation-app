from flask import Flask, render_template, request, redirect
import sqlite3
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservations.db")

def get_db():
    return sqlite3.connect(DB_PATH)

# créer table si absente
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

init_db()

# ================= PAGE PRINCIPALE =================
@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()

    date = request.args.get("date")

    if date:
        cur.execute("""
        SELECT * FROM reservations
        WHERE date_debut <= ? AND date_fin >= ?
        """, (date, date))
    else:
        cur.execute("SELECT * FROM reservations")

    data = cur.fetchall()
    conn.close()

    return render_template("index.html", data=data)

# ================= AJOUT =================
@app.route("/add", methods=["POST"])
def add():
    form = request.form

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO reservations 
    (type, salle, etage, section, titre, organisateur, date_debut, date_fin, periode)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        form["type"],
        form["salle"],
        form["etage"],
        form["section"],
        form["titre"],
        form["organisateur"],
        form["date_debut"],
        form["date_fin"],
        form["periode"]
    ))

    conn.commit()
    conn.close()

    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)