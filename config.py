"""Konfigurasi terpusat — dibaca sekali dari environment variables."""
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
MODEL_NAME = "gemini-3.5-flash"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-ganti-ini")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "MYSQLHOST"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "sambal_ai"),
}

STOPWORDS_ID = {
    "aku", "kamu", "saya", "dia", "kita", "kami", "mereka", "punya", "ada", "dan",
    "atau", "yang", "ini", "itu", "di", "ke", "dari", "untuk", "dengan", "juga",
    "enak", "enaknya", "dimasak", "masak", "gimana", "apa", "apaya", "apakah",
    "dong", "sih", "ya", "nya", "bisa", "mau", "ingin", "tolong", "kasih", "rekomendasi",
    "resep", "resepnya", "cara", "bikin", "membuat", "buat",
}

SYNONYM_MAP = {
    "sapi": ["daging sapi", "has sapi", "sandung lamur", "sengkel", "iga sapi"],
    "santan": ["santan kelapa", "santan instan", "kara"],
    "cabai": ["cabe", "cabai rawit", "cabai merah", "cabai hijau", "lombok"],
    "ayam": ["daging ayam", "ayam kampung", "ayam broiler", "ayam potong"],
    "udang": ["udang segar", "udang windu", "udang vaname"],
    "minyak": ["minyak goreng", "minyak sayur"],
    "kecap": ["kecap manis", "kecap asin"],
    "bawang": ["bawang merah", "bawang putih", "bawang bombay"],
}

CATEGORIES = ["ayam", "sapi", "ikan", "udang", "tempe", "tahu", "telur", "kambing"]
DAYS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
MEAL_TYPES = ["Sarapan", "Makan Siang", "Makan Malam"]

INSTANT_GROCERY_APPS = ["Astro", "Sayurbox", "Segari"]

# ---------- Meal Planner AI ----------
# Asumsi porsi dasar tiap resep di dataset (tidak ada kolom porsi eksplisit di
# data, jadi ini estimasi kasar buat skala shopping list — ditandai jelas ke
# user sebagai perkiraan, bukan angka pasti).
DEFAULT_PORSI_PER_RESEP = 4
MEAL_PLAN_MAX_HARI = 7

BLOG_POSTS = [
    {
        "slug": "bumbu-dasar-masakan-indonesia",
        "title": "5 Bumbu Dasar yang Wajib Ada di Dapur Indonesia",
        "category": "Tips Dasar",
        "excerpt": "Kenalan sama bumbu dasar merah, kuning, putih, dan oranye — kunci rasa masakan Nusantara.",
        "content": (
            "Masakan Indonesia punya empat bumbu dasar yang jadi fondasi ribuan resep: "
            "bumbu merah (cabai merah, bawang, tomat) untuk masakan pedas segar, bumbu kuning "
            "(kunyit, kemiri, bawang) untuk soto dan gulai, bumbu putih (bawang putih, kemiri, "
            "ketumbar) untuk opor dan sayur bening, serta bumbu oranye (campuran merah-kuning) "
            "untuk rendang dan semur.\n\n"
            "Kalau kamu simpan keempat bumbu ini dalam bentuk pasta di freezer, masak sehari-hari "
            "jadi jauh lebih cepat — tinggal tumis dan tambah bahan utama."
        ),
    },
    {
        "slug": "cara-simpan-bahan-segar",
        "title": "Cara Menyimpan Sayur & Daging Biar Awet Lebih Lama",
        "category": "Penyimpanan",
        "excerpt": "Trik simpan bahan biar nggak cepat busuk, hemat belanja mingguan.",
        "content": (
            "Sayur berdaun (kangkung, bayam) sebaiknya dibungkus tisu sebelum masuk kulkas, "
            "biar kelembapan berlebih terserap dan daun nggak layu. Daging dan ayam paling "
            "aman dibagi jadi porsi sekali masak sebelum dibekukan, jadi nggak perlu thawing "
            "berulang yang bikin tekstur rusak.\n\n"
            "Bumbu basah seperti bawang giling atau cabai giling bisa disimpan di wadah kedap "
            "udara dan tahan sekitar seminggu di kulkas, atau dibekukan dalam cetakan es batu "
            "untuk pemakaian per porsi kecil."
        ),
    },
    {
        "slug": "masak-cepat-anak-kos",
        "title": "Ide Masak Cepat 15 Menit buat Anak Kos",
        "category": "Praktis",
        "excerpt": "Nggak punya banyak waktu? Ini resep-resep yang cocok buat jadwal padat kuliah.",
        "content": (
            "Telur dadar bumbu, tumis tahu-tempe kecap, dan mi goreng sayur adalah tiga menu "
            "yang bisa selesai di bawah 15 menit dengan bahan yang gampang dicari di warung "
            "dekat kos. Kuncinya: siapkan bumbu dasar dari akhir pekan, jadi hari kerja tinggal "
            "eksekusi.\n\n"
            "Coba fitur chat AI di SAMBAL.AI dan ketik bahan yang kamu punya — sistem bakal "
            "carikan resep yang paling cocok dari database, termasuk yang cepat dan simpel."
        ),
    },
    {
        "slug": "kenali-kategori-masakan",
        "title": "Kenalan Sama 8 Kategori Masakan di SAMBAL.AI",
        "category": "Panduan",
        "excerpt": "Ayam, sapi, ikan, udang, tempe, tahu, telur, kambing — mana favoritmu?",
        "content": (
            "Dataset SAMBAL.AI mengelompokkan resep ke dalam 8 kategori bahan utama: ayam, "
            "sapi, ikan, udang, tempe, tahu, telur, dan kambing. Tiap kategori punya karakter "
            "masak yang beda — misalnya kambing lebih cocok dimasak lama (gulai, tongseng) "
            "buat melunakkan tekstur, sementara udang dan ikan lebih pas dimasak cepat biar "
            "nggak alot.\n\n"
            "Coba jelajahi tiap kategori di halaman Menu, atau pakai Rencana Menu Mingguan "
            "buat variasiin kategori tiap harinya."
        ),
    },
]

FAQS = [
    ("Apakah SAMBAL.AI gratis dipakai?", "Iya, sepenuhnya gratis. Kamu cuma perlu bikin akun buat pakai fitur chat AI dan menyimpan favorit."),
    ("Dari mana data resepnya?", "Semua resep berasal dari dataset Indonesian Food Recipes, dengan lebih dari 14.000 resep asli Indonesia."),
    ("Kenapa saya harus login buat chat AI?", "Login membantu kami menjaga kualitas layanan dan memungkinkan kamu menyimpan riwayat favorit serta rencana menu."),
    ("Bagaimana cara kerja rekomendasi AI-nya?", "Ada beberapa agen AI yang bekerja berurutan & paralel: menganalisis kebutuhanmu, mencari kandidat resep, mengecek nutrisi/budget, memilih rekomendasi terbaik, mengecek bahan yang kurang, mencari substitusi, video tutorial, dan link belanja."),
]
