-- Migration FINAL buat fitur Meal Planner AI + penyederhanaan ke 1 dataset aja.
-- Jalankan SETELAH schema.sql utama. Aman dijalankan berkali-kali (idempotent)
-- dan aman juga kalau sebelumnya kamu udah pernah jalanin versi migration yang
-- lama (yang masih pakai extended_recipes) — script ini otomatis beresin itu.

USE sambal_ai;

-- Simpan preferensi jumlah hari & jumlah anggota keluarga per user, dipakai
-- sebagai default form di halaman Meal Planner (bisa dioverride via chat).
CREATE TABLE IF NOT EXISTS meal_plan_settings (
    user_id      INT PRIMARY KEY,
    jumlah_hari  TINYINT NOT NULL DEFAULT 7,
    jumlah_orang TINYINT NOT NULL DEFAULT 4,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Simpan hasil hitung shopping list mingguan terakhir per user (lengkap sama
-- jumlah/berat tiap bahan), biar bisa ditampilkan lagi tanpa perlu chat ulang
-- tiap buka halaman.
CREATE TABLE IF NOT EXISTS meal_plan_shopping_list (
    user_id      INT PRIMARY KEY,
    shopping_json TEXT NOT NULL,
    catatan_gizi  TEXT,
    generated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- Beres-beres: hapus 2 dataset yang gak dipakai lagi ----------
-- Project ini SEKARANG cuma pakai 1 dataset (tabel recipes / Indonesian_Food_Recipes.csv).
-- Dataset "Resep Sehat" (extended_recipes) dan "Diet Explorer" (diet_recipes)
-- sudah tidak dipakai — dihapus total, termasuk tabel meal_plan_ai_slots versi
-- lama yang FK ke extended_recipes (kalau kamu sempat jalanin migration versi
-- sebelumnya). Urutan DROP penting: child dulu (meal_plan_ai_slots) baru parent
-- (extended_recipes), biar gak kena error foreign key.
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS meal_plan_ai_slots;
DROP TABLE IF EXISTS extended_recipes;
DROP TABLE IF EXISTS diet_recipes;
SET FOREIGN_KEY_CHECKS = 1;

-- Rencana menu mingguan dari Meal Planner AI, sekarang nunjuk ke `recipes`
-- (dataset utama) — SATU-SATUNYA dataset di project ini. Terpisah dari tabel
-- meal_plans (grid manual) biar generate AI gak nimpa slot yang dipilih manual.
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
) ENGINE=InnoDB;
