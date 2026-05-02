import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, send_file

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reservations.db")


# ✅ LISTE COMPLETE DES SALLES
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


@app.route("/", methods=["GET", "POST"])
def index():
    init_db()
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")
        id_ = request.form.get("id")

        if action == "update" and id_:
            cur.execute("""
                UPDATE reservations SET
                type=?, etage=?, salle=?, genre=?, periode=?,
                date_debut=?, date_fin=?, titre=?, organisateur=?
                WHERE id=?
            """, (
                request.form.get("type"),
                request.form.get("etage"),
                request.form.get("salle"),
                request.form.get("genre"),
                request.form.get("periode"),
                request.form.get("debut"),
                request.form.get("fin"),
                request.form.get("titre"),
                request.form.get("organisateur"),
                id_
            ))
        else:
            cur.execute("""
                INSERT INTO reservations
                (type, etage, salle, genre, periode, date_debut, date_fin, titre, organisateur)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.form.get("type"),
                request.form.get("etage"),
                request.form.get("salle"),
                request.form.get("genre"),
                request.form.get("periode"),
                request.form.get("debut"),
                request.form.get("fin"),
                request.form.get("titre"),
                request.form.get("organisateur"),
            ))

        conn.commit()
        conn.close()
        return redirect("/")

    cur.execute("SELECT * FROM reservations ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()

    return render_template("index.html", data=data, salles=SALLES)


@app.route("/delete", methods=["POST"])
def delete():
    id_ = request.form.get("id")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM reservations WHERE id=?", (id_,))
    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/export")
def export_excel():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM reservations", conn)
    conn.close()

    file = "export.xlsx"
    df.to_excel(file, index=False)

    return send_file(file, as_attachment=True)


@app.route("/import", methods=["POST"])
def import_excel():
    file = request.files.get("file")

    if not file:
        return "لم يتم اختيار ملف"

    try:
        import pandas as pd

        df = pd.read_excel(file)

        conn = get_db()
        cur = conn.cursor()

        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO reservations
                (type, etage, salle, genre, periode, date_debut, date_fin, titre, organisateur)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("type", ""),
                row.get("etage", ""),
                row.get("salle", ""),
                row.get("genre", ""),
                row.get("periode", ""),
                str(row.get("date_debut", "")),
                str(row.get("date_fin", "")),
                row.get("titre", ""),
                row.get("organisateur", "")
            ))

        conn.commit()
        conn.close()

    except Exception as e:
        return f"خطأ في الاستيراد: {e}"

    return redirect("/")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
