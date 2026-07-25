import mysql.connector
import pandas as pd
from sqlalchemy import create_engine
import os

# DEBUG Railway ENV
print("MYSQLHOST =", os.getenv("MYSQLHOST"))
print("MYSQLPORT =", os.getenv("MYSQLPORT"))
print("MYSQLUSER =", os.getenv("MYSQLUSER"))
print("MYSQLDATABASE =", os.getenv("MYSQLDATABASE"))

port = int(os.getenv("MYSQLPORT") or 3306)

_engine = create_engine(
    f"mysql+mysqlconnector://{os.getenv('MYSQLUSER')}:{os.getenv('MYSQLPASSWORD')}"
    f"@{os.getenv('MYSQLHOST')}:{port}/{os.getenv('MYSQLDATABASE')}"
)


def get_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQLHOST"),
        user=os.getenv("MYSQLUSER"),
        password=os.getenv("MYSQLPASSWORD"),
        database=os.getenv("MYSQLDATABASE"),
        port=int(os.getenv("MYSQLPORT") or 3306),
    )


def ensure_meal_plan_tables():
    """Safety net dipanggil sekali pas app start (lihat app.py). Sama persis
    dengan CREATE TABLE di database/schema_meal_plan_ai.sql, tapi dijalankan
    otomatis dari kode — supaya generate rencana menu tidak pernah gagal
    nyimpen ke DB hanya gara-gara migration SQL-nya lupa/belum dijalankan
    manual. Aman dipanggil berkali-kali (IF NOT EXISTS)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meal_plan_settings (
            user_id      INT PRIMARY KEY,
            jumlah_hari  TINYINT NOT NULL DEFAULT 7,
            jumlah_orang TINYINT NOT NULL DEFAULT 4,
            wilayah      VARCHAR(20) NOT NULL DEFAULT 'jawa',
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    """)
    # Buat instalasi LAMA yang tabelnya udah kebuat sebelum kolom 'wilayah' ada
    # (dipakai buat pengali kasar estimasi harga Jawa/Luar Jawa) — ADD COLUMN
    # gak seaman MODIFY COLUMN buat dijalanin berkali-kali (beberapa versi
    # MySQL/MariaDB gak dukung "ADD COLUMN IF NOT EXISTS"), jadi dibungkus
    # try/except: kalau kolomnya udah ada, errornya ditangkep & dilewatin aja.
    try:
        cur.execute("ALTER TABLE meal_plan_settings ADD COLUMN wilayah VARCHAR(20) NOT NULL DEFAULT 'jawa'")
    except mysql.connector.Error:
        pass
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meal_plan_shopping_list (
            user_id       INT PRIMARY KEY,
            shopping_json MEDIUMTEXT NOT NULL,
            catatan_gizi  MEDIUMTEXT,
            generated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    """)
    # BUG YANG DIPERBAIKI: kolom ini sebelumnya TEXT (batas 65.535 byte).
    # Rencana menu 7 hari x 3 kali makan = 21 resep, dan JSON daftar belanjanya
    # (nama bahan + url marketplace + url maps + catatan + daftar resep per
    # bahan) gampang lewat 64KB. XAMPP defaultnya TIDAK strict mode, jadi MySQL
    # DIAM-DIAM MEMOTONG data yang kepanjangan alih-alih error saat INSERT —
    # hasilnya JSON yang tersimpan jadi rusak/terpotong. Baris di bawah ini
    # naikin kapasitasnya ke MEDIUMTEXT (16MB) DAN memperbaiki tabel yang
    # sudah kadung dibuat dengan tipe TEXT lama (ALTER aman dijalankan
    # berkali-kali, MySQL skip kalau tipenya udah benar).
    cur.execute("ALTER TABLE meal_plan_shopping_list MODIFY COLUMN shopping_json MEDIUMTEXT NOT NULL")
    cur.execute("ALTER TABLE meal_plan_shopping_list MODIFY COLUMN catatan_gizi MEDIUMTEXT")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meal_plan_ai_slots (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            day_of_week VARCHAR(10) NOT NULL,
            meal_type VARCHAR(15) NOT NULL,
            recipe_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_ai_slot (user_id, day_of_week, meal_type),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
        ) ENGINE=InnoDB
    """)
    conn.commit()
    cur.close()
    conn.close()


def load_all_recipes() -> pd.DataFrame:
    """Load seluruh tabel recipes ke pandas DataFrame, dicache di memori proses."""
    global _recipes_cache
    if _recipes_cache is not None:
        return _recipes_cache
    df = pd.read_sql("SELECT * FROM recipes", _engine)
    df = df.fillna("")
    _recipes_cache = df
    return df


def get_user_preferences(user_id: int) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM user_preferences WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def bump_preference_category(user_id: int, category: str):
    """Dipanggil tiap kali user nge-favoritkan resep — nambah counter kategori
    di JSON suka_kategori, dipakai buat context-aware recommendation (section 6.a/6.e)."""
    import json as json_lib

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM user_preferences WHERE user_id = %s", (user_id,))
    row = cur.fetchone()

    if row:
        suka = json_lib.loads(row["suka_kategori"] or "{}")
        suka[category] = suka.get(category, 0) + 1
        cur.execute(
            "UPDATE user_preferences SET suka_kategori = %s WHERE user_id = %s",
            (json_lib.dumps(suka), user_id),
        )
    else:
        suka = {category: 1}
        cur.execute(
            "INSERT INTO user_preferences (user_id, suka_kategori) VALUES (%s, %s)",
            (user_id, json_lib.dumps(suka)),
        )
    conn.commit()
    cur.close()
    conn.close()


# ---------- Meal Planner AI ----------

def get_meal_plan_settings(user_id: int) -> dict:
    """Ambil setting jumlah hari & orang & wilayah. Kalau belum pernah diset,
    balikin default."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT jumlah_hari, jumlah_orang, wilayah FROM meal_plan_settings WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        row.setdefault("wilayah", "jawa")
        return row
    return {"jumlah_hari": 7, "jumlah_orang": 4, "wilayah": "jawa"}


def save_meal_plan_settings(user_id: int, jumlah_hari: int, jumlah_orang: int, wilayah: str = "jawa"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO meal_plan_settings (user_id, jumlah_hari, jumlah_orang, wilayah)
           VALUES (%s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE jumlah_hari = VALUES(jumlah_hari), jumlah_orang = VALUES(jumlah_orang), wilayah = VALUES(wilayah)""",
        (user_id, jumlah_hari, jumlah_orang, wilayah),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_recipe_candidate_pool(categories: list[str], per_category: int = 12) -> list[dict]:
    """Ambil kandidat resep dari tabel recipes (dataset utama), diversifikasi per
    kategori (ayam/sapi/ikan/dst) biar variasi menu seminggu gak monoton di 1
    kategori. Diurutkan dari yang paling banyak di-loves (proxy popularitas —
    dataset ini gak punya skor kesehatan/gizi, jadi ini bukan klaim "paling sehat")."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    rows = []
    for cat in categories:
        cur.execute(
            """SELECT id, title, category, ingredients, total_ingredients
               FROM recipes
               WHERE category = %s
               ORDER BY loves DESC
               LIMIT %s""",
            (cat, per_category),
        )
        rows.extend(cur.fetchall())
    cur.close()
    conn.close()
    return rows


def save_meal_plan_week(user_id: int, assignments: list[dict]):
    """assignments: list of {day_of_week, meal_type, recipe_id}. Disimpan TERPISAH
    dari tabel meal_plans (grid manual yang sudah ada duluan), biar generate AI
    gak nimpa slot yang udah dipilih manual sama user."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM meal_plan_ai_slots WHERE user_id = %s", (user_id,))
    for a in assignments:
        cur.execute(
            """INSERT INTO meal_plan_ai_slots (user_id, day_of_week, meal_type, recipe_id)
               VALUES (%s, %s, %s, %s)""",
            (user_id, a["day_of_week"], a["meal_type"], a["recipe_id"]),
        )
    conn.commit()
    cur.close()
    conn.close()


def get_meal_plan_week(user_id: int) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """SELECT s.day_of_week, s.meal_type, r.id AS recipe_id, r.title, r.category
           FROM meal_plan_ai_slots s
           JOIN recipes r ON r.id = s.recipe_id
           WHERE s.user_id = %s""",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_meal_plan_last_reply(user_id: int) -> str | None:
    """Ambil teks balasan chat TERAKHIR yang berhasil di-generate, buat ditampilin
    lagi pas user buka ulang halaman /rencana-menu (biar chat gak keliatan
    'ilang' padahal cuma belum di-render ulang)."""
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT catatan_gizi FROM meal_plan_shopping_list WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["catatan_gizi"] if row else None


def clear_meal_plan_ai(user_id: int):
    """Dipanggil dari tombol 'Bersihin Chat' — hapus rencana menu AI & daftar
    belanja yang tersimpan. Setting jumlah hari/orang SENGAJA gak ikut dihapus
    (biar gak perlu diisi ulang tiap mau generate baru)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM meal_plan_ai_slots WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM meal_plan_shopping_list WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


def get_meal_plan_shopping_list_saved(user_id: int) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT shopping_json FROM meal_plan_shopping_list WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    import json as json_lib
    try:
        data = json_lib.loads(row["shopping_json"])
    except Exception as e:
        # Dulu exception ini ditelan diam-diam (langsung `return None`), jadi
        # kelihatannya sama persis kayak "user belum pernah generate rencana
        # menu" padahal datanya ADA tapi rusak/terpotong (lihat komentar di
        # ensure_meal_plan_tables soal MEDIUMTEXT). Sekarang errornya diprint
        # biar akar masalah kelihatan jelas di terminal, bukan cuma "KOSONG/None".
        print(f"[get_meal_plan_shopping_list_saved] user_id={user_id}: shopping_json di DB gagal di-parse ({e}). "
              f"Panjang data tersimpan: {len(row['shopping_json'])} karakter — kalau ini kelihatan 'kepotong', "
              f"kemungkinan besar sebelum fix MEDIUMTEXT datanya kena truncate MySQL. Generate ulang rencana menu.")
        return None

    # Backward-compat: kalau data ini tersimpan dari SEBELUM fitur harga/gramasi
    # ditambahkan, field-nya belum ada sama sekali di JSON lama. Isi default di
    # sini (bukan cuma di template) supaya SEMUA konsumen data ini (halaman
    # rencana menu, export PDF, dst) sama-sama aman dari data lama yang belum
    # lengkap, bukan cuma nge-tempel `| default(...)` di satu tempat doang.
    for item in data.get("shopping_list", []) or []:
        item.setdefault("harga_estimasi", 0)
        item.setdefault("harga_kasar", True)
        item.setdefault("jumlah", "secukupnya")
        item.setdefault("dipakai_di", 1)
        item.setdefault("resep", [])
    data.setdefault("total_harga_estimasi", sum(i.get("harga_estimasi", 0) for i in data.get("shopping_list", []) or []))

    return data


def save_meal_plan_shopping_list(user_id: int, shopping_json: str, catatan_gizi: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO meal_plan_shopping_list (user_id, shopping_json, catatan_gizi)
           VALUES (%s, %s, %s)
           ON DUPLICATE KEY UPDATE shopping_json = VALUES(shopping_json), catatan_gizi = VALUES(catatan_gizi)""",
        (user_id, shopping_json, catatan_gizi),
    )
    conn.commit()
    cur.close()
    conn.close()
