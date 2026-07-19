-- Jalankan lewat phpMyAdmin (XAMPP) atau `mysql -u root -p < schema.sql`

CREATE DATABASE IF NOT EXISTS sambal_ai
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE sambal_ai;

CREATE TABLE IF NOT EXISTS recipes (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    title               VARCHAR(255) NOT NULL,
    ingredients         TEXT,
    steps               TEXT,
    loves               INT DEFAULT 0,
    url                 VARCHAR(500),
    category            VARCHAR(50),
    title_cleaned       VARCHAR(255),
    total_ingredients   INT DEFAULT 0,
    ingredients_cleaned TEXT,
    total_steps         INT DEFAULT 0,
    FULLTEXT KEY ft_search (title, ingredients_cleaned, category)
) ENGINE=InnoDB;

CREATE INDEX idx_category ON recipes (category);
CREATE INDEX idx_loves ON recipes (loves DESC);

-- ---------- Users (untuk login/register) ----------
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50) NOT NULL UNIQUE,
    email         VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------- Favorit resep per user ----------
CREATE TABLE IF NOT EXISTS favorites (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    recipe_id  INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_favorite (user_id, recipe_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- Rencana menu mingguan (meal planner) ----------
CREATE TABLE IF NOT EXISTS meal_plans (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    day_of_week  VARCHAR(10) NOT NULL,   -- Senin, Selasa, ...
    meal_type    VARCHAR(15) NOT NULL,   -- Sarapan, Makan Siang, Makan Malam
    recipe_id  INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_slot (user_id, day_of_week, meal_type),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- Pesan dari halaman Kontak/Bantuan ----------
CREATE TABLE IF NOT EXISTS contact_messages (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    email      VARCHAR(150) NOT NULL,
    message    TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ---------- Riwayat percakapan chat AI ----------
CREATE TABLE IF NOT EXISTS chat_history (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    message    TEXT NOT NULL,
    reply      TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- Dataset diet (terpisah dari recipes Indonesia, lihat ROADMAP_ADVANCED.md) ----------
CREATE TABLE IF NOT EXISTS diet_recipes (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    diet_type     VARCHAR(30) NOT NULL,
    recipe_name   VARCHAR(255) NOT NULL,
    cuisine_type  VARCHAR(50),
    protein_g     DECIMAL(6,2) DEFAULT 0,
    carbs_g       DECIMAL(6,2) DEFAULT 0,
    fat_g         DECIMAL(6,2) DEFAULT 0,
    calories_kcal DECIMAL(8,2) GENERATED ALWAYS AS (protein_g*4 + carbs_g*4 + fat_g*9) STORED,
    INDEX idx_diet_type (diet_type)
) ENGINE=InnoDB;

-- ---------- Extended Recipes: dataset kedua (recipes_extended.csv) ----------
-- Beda dari diet_recipes (All_Diets.csv) yang cuma punya nama + makro tanpa cara masak.
-- Dataset ini PUNYA ingredients & directions asli, jadi bisa ditampilkan sebagai resep
-- lengkap (bukan cuma daftar nama), plus flag diet yang lebih akurat per resep
-- (vegan/vegetarian/halal/kosher/gluten-free/dairy-free/nut-free) dan skor kesehatan.
CREATE TABLE IF NOT EXISTS extended_recipes (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    title               VARCHAR(500) NOT NULL,
    category            VARCHAR(120),
    subcategory         VARCHAR(120),
    description         TEXT,
    ingredients         TEXT,               -- satu bahan per baris
    directions          TEXT,               -- langkah bernomor "1. ... \n2. ..."
    num_ingredients     INT DEFAULT 0,
    num_steps           INT DEFAULT 0,
    ingredient_text     TEXT,               -- versi plain lowercase, buat search
    cuisine_list        VARCHAR(500),       -- comma-joined
    course_list         VARCHAR(255),
    primary_taste       VARCHAR(30),
    secondary_taste     VARCHAR(30),
    cook_speed          VARCHAR(20),        -- fast | medium | slow
    est_prep_time_min   INT DEFAULT 0,
    est_cook_time_min   INT DEFAULT 0,
    difficulty          VARCHAR(20),        -- easy | medium | hard
    is_vegan            TINYINT(1) DEFAULT 0,
    is_vegetarian       TINYINT(1) DEFAULT 0,
    is_halal            TINYINT(1) DEFAULT 0,
    is_kosher           TINYINT(1) DEFAULT 0,
    is_nut_free         TINYINT(1) DEFAULT 0,
    is_dairy_free       TINYINT(1) DEFAULT 0,
    is_gluten_free      TINYINT(1) DEFAULT 0,
    healthiness_score   INT DEFAULT 0,
    health_level        VARCHAR(20),        -- healthy | moderate | unhealthy
    main_ingredient     VARCHAR(30),        -- red_meat | poultry | seafood | plant | egg_dairy | unknown
    INDEX idx_ext_category (category),
    INDEX idx_ext_health_level (health_level),
    INDEX idx_ext_is_vegan (is_vegan),
    INDEX idx_ext_is_vegetarian (is_vegetarian),
    INDEX idx_ext_is_gluten_free (is_gluten_free),
    INDEX idx_ext_main_ingredient (main_ingredient),
    FULLTEXT KEY ft_ext_search (title, ingredient_text, category)
) ENGINE=InnoDB;

-- ---------- User Preference Memory (ROADMAP #6.e) ----------
CREATE TABLE IF NOT EXISTS user_preferences (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL UNIQUE,
    suka_kategori JSON,
    diet_type     VARCHAR(30),
    budget_mode   BOOLEAN DEFAULT FALSE,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------- Feedback Loop (ROADMAP #6.f) ----------
CREATE TABLE IF NOT EXISTS chat_feedback (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    chat_history_id  INT NOT NULL,
    rating           TINYINT NOT NULL,   -- 1 = tidak membantu, 5 = sangat membantu (dipakai biner: 1 atau 5)
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_history_id) REFERENCES chat_history(id) ON DELETE CASCADE
) ENGINE=InnoDB;
