@app.route("/import", methods=["POST"])
def import_excel():
    file = request.files.get("file")
    if not file or file.filename == "":
        return "لم يتم اختيار ملف"

    try:
        import pandas as pd

        df = pd.read_excel(file)

        # 🔧 توحيد أسماء الأعمدة (إزالة فراغات + lowercase)
        df.columns = [str(c).strip().lower() for c in df.columns]

        # 🔁 خريطة أعمدة عربي/إنجليزي → أسماء DB
        col_map = {
            # English
            "type": "type",
            "etage": "etage",
            "salle": "salle",
            "genre": "genre",
            "periode": "periode",
            "date_debut": "date_debut",
            "date_fin": "date_fin",
            "titre": "titre",
            "organisateur": "organisateur",

            # Arabic
            "النوع": "type",
            "الطابق": "etage",
            "القاعة": "salle",
            "الجنس": "genre",
            "الفترة": "periode",
            "تاريخ البدء": "date_debut",
            "تاريخ البداية": "date_debut",
            "تاريخ النهاية": "date_fin",
            "العنوان": "titre",
            "عنوان الدورة / البرنامج": "titre",
            "المنظم": "organisateur",
            "الإدارة / الجهة المنظمة": "organisateur",
        }

        # 🧱 أعمدة DB النهائية
        target_cols = ["type","etage","salle","genre","periode","date_debut","date_fin","titre","organisateur"]

        # 🔄 إعادة تسمية الأعمدة حسب الخريطة
        renamed = {}
        for c in df.columns:
            if c in col_map:
                renamed[c] = col_map[c]
        df = df.rename(columns=renamed)

        # ➕ إضافة الأعمدة الناقصة بقيم فارغة
        for col in target_cols:
            if col not in df.columns:
                df[col] = ""

        # 🗓️ تحويل التواريخ إلى نص YYYY-MM-DD
        for col in ["date_debut", "date_fin"]:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")
            df[col] = df[col].fillna("")

        # 🧼 تحويل NaN إلى نص فارغ
        df = df.fillna("")

        conn = get_db()
        cur = conn.cursor()

        # 🚀 إدخال البيانات
        for _, row in df.iterrows():
            cur.execute("""
                INSERT INTO reservations
                (type, etage, salle, genre, periode, date_debut, date_fin, titre, organisateur)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(row["type"]),
                str(row["etage"]),
                str(row["salle"]),
                str(row["genre"]),
                str(row["periode"]),
                str(row["date_debut"]),
                str(row["date_fin"]),
                str(row["titre"]),
                str(row["organisateur"]),
            ))

        conn.commit()
        conn.close()

    except Exception as e:
        return f"خطأ في الاستيراد: {e}"

    return redirect("/")
