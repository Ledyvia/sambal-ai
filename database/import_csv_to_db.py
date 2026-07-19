"""
Import Indonesian_Food_Recipes.csv ke database MySQL (XAMPP).

Cara pakai:
1. Nyalakan XAMPP, start Apache + MySQL
2. Jalankan schema.sql dulu (lewat phpMyAdmin, atau: mysql -u root -p < database/schema.sql)
3. Taruh file Indonesian_Food_Recipes.csv di folder yang sama dengan script ini,
   atau ubah CSV_PATH di bawah
4. Jalankan: python database/import_csv_to_db.py
"""
import os
import sys
import pandas as pd
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "Indonesian_Food_Recipes.csv")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "sambal_ai"),
}


def main():
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: file tidak ditemukan di {CSV_PATH}")
        print("Taruh Indonesian_Food_Recipes.csv di root folder project, atau ubah CSV_PATH di script ini.")
        sys.exit(1)

    print("Membaca CSV...")
    df = pd.read_csv(CSV_PATH).fillna("")
    print(f"Jumlah baris: {len(df)}")

    print("Konek ke MySQL...")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    print("Mengosongkan tabel recipes (kalau sudah ada data)...")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    cursor.execute("TRUNCATE TABLE favorites")
    cursor.execute("TRUNCATE TABLE meal_plans")
    cursor.execute("TRUNCATE TABLE recipes")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()

    insert_sql = """
        INSERT INTO recipes
        (title, ingredients, steps, loves, url, category, title_cleaned,
         total_ingredients, ingredients_cleaned, total_steps)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    print("Import data (mungkin makan waktu beberapa menit)...")
    batch = []
    batch_size = 500
    total_inserted = 0

    for _, row in df.iterrows():
        batch.append((
            str(row.get("Title", "")),
            str(row.get("Ingredients", "")),
            str(row.get("Steps", "")),
            int(row.get("Loves", 0) or 0),
            str(row.get("URL", "")),
            str(row.get("Category", "")),
            str(row.get("Title Cleaned", "")),
            int(row.get("Total Ingredients", 0) or 0),
            str(row.get("Ingredients Cleaned", "")),
            int(row.get("Total Steps", 0) or 0),
        ))
        if len(batch) >= batch_size:
            cursor.executemany(insert_sql, batch)
            conn.commit()
            total_inserted += len(batch)
            print(f"  {total_inserted} baris ter-import...")
            batch = []

    if batch:
        cursor.executemany(insert_sql, batch)
        conn.commit()
        total_inserted += len(batch)

    print(f"Selesai! Total {total_inserted} resep ter-import ke database.")
    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
