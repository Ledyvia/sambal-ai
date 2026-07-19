# SAMBAL.AI — Multi-Agent Recipe Recommender + Login + Meal Planner AI

Website resep masakan Indonesia dengan sistem **multi-agent AI** (analisis kebutuhan →
cari resep → cek nutrisi/budget → putuskan rekomendasi → cek bahan kurang → substitusi →
video tutorial → link belanja → skor & penjelasan), landing page, login/register, meal
planner mingguan (manual + AI), favorit, riwayat chat. Satu dataset resep Indonesia
(`Indonesian_Food_Recipes.csv`) dipakai buat SEMUA fitur.
Backend Flask + MySQL (XAMPP), dijalankan lokal lewat VS Code.

> Baca `ROADMAP_ADVANCED.md` untuk penjelasan arsitektur & desain teknis lengkap
> (kenapa paralel pakai `ThreadPoolExecutor`, kenapa Superindo/GrabMart nggak bisa
> API langsung, perbandingan RAG vs fine-tuning, dll).

## Halaman yang Tersedia

| Halaman | Route | Keterangan |
|---|---|---|
| Landing / Beranda | `/` | Opening page — hero, fitur, teaser terkunci (belum login) |
| Menu | `/menu` | Jelajahi semua resep — filter kategori, search (butuh login) |
| Detail Resep | `/resep/<id>` | Bahan, langkah, tutorial video, cooking timeline, resep serupa, favorit |
| Login / Daftar | `/login`, `/register` | Auth |
| Favorit | `/favorit` | Resep tersimpan (butuh login) |
| Rencana Menu | `/rencana-menu` | Meal planner mingguan — grid manual + Meal Planner AI (chat, generate otomatis + shopping list) (butuh login) |
| Riwayat Chat | `/riwayat-chat` | Histori percakapan AI (butuh login) |
| Blog, Tentang, Kontak | `/blog`, `/tentang`, `/kontak` | Konten pendukung |
| Chat AI | tombol 🍲 di semua halaman | Multi-agent pipeline, butuh login |

## Arsitektur Multi-Agent

```
Fase 1 (sekuensial)   : Ingredient Analyzer  (paham maksud user, urgency, preferensi)
Fase 2 (PARALEL)      : Recipe Finder | Nutrition Agent | Budget Agent
Fase 3 (sekuensial)   : Decision Maker        (pilih & susun 2-3 rekomendasi)
Fase 4 (sekuensial)   : Ingredient Matching   (cek bahan yang kurang)
Fase 5 (PARALEL)      : Substitution Agent | Video Agent | Shopping Agent
Fase 6 (sekuensial)   : Scoring + Aggregator  (gabung semua jadi 1 jawaban + skor)
```

Paralelisasi pakai `concurrent.futures.ThreadPoolExecutor` (bukan asyncio) — lebih
simpel & robust untuk Flask sync app. Detail alasan ada di `ROADMAP_ADVANCED.md` §7.

## Struktur Folder

```
sambal-ai/
├── app.py                       # Flask app — HANYA routes, tipis
├── config.py                    # Semua konstanta & konfigurasi
├── orchestrator.py               # Orkestrasi pipeline (sekuensial + paralel)
├── agents/
│   ├── ingredient_analyzer.py    # Agent 1
│   ├── recipe_finder.py          # Agent 2 (+ synonym expansion, preference boost)
│   ├── nutrition_agent.py        # nonaktif (dataset diet sudah dihapus, return None)
│   ├── budget_agent.py           # BARU — sinyal hemat/tidak
│   ├── decision_maker.py         # Agent 3
│   ├── ingredient_matching.py     # BARU — cek bahan kurang
│   ├── substitution_agent.py     # BARU — saran pengganti bahan
│   ├── video_agent.py            # BARU — tutorial YouTube
│   ├── shopping_agent.py         # BARU — link belanja urgency-aware
│   ├── scoring.py                # BARU — skor deterministik (explainable AI)
│   ├── aggregator.py             # BARU — gabung semua jadi 1 jawaban
│   ├── cooking_timeline.py       # BARU — estimasi waktu per langkah masak
│   ├── meal_plan_analyzer.py     # Meal Planner AI — baca bahan dipunya + override hari/orang
│   ├── meal_plan_selector.py     # Meal Planner AI — pilih resep 1 minggu (1x panggilan Gemini)
│   ├── weekly_shopping_agent.py  # Meal Planner AI — gabung shopping list + jumlah/berat (murni Python)
│   └── weekly_aggregator.py      # Meal Planner AI — rangkai balasan final
├── services/
│   ├── db.py                     # Koneksi MySQL + cache pandas + user preferences
│   ├── youtube_service.py        # Panggilan YouTube Data API v3
│   └── shopping_links.py         # Generator link Tokopedia
├── database/
│   ├── schema.sql                 # Tabel utama (recipes, users, favorites, meal_plans,
│   │                                contact_messages, chat_history, user_preferences,
│   │                                chat_feedback)
│   ├── schema_meal_plan_ai.sql    # Tabel tambahan buat Meal Planner AI
│   └── import_csv_to_db.py        # Import Indonesian_Food_Recipes.csv
├── requirements.txt
├── .env.example                   # copy jadi .env
├── Indonesian_Food_Recipes.csv
├── templates/, static/            # UI (Jinja2 + CSS custom + vanilla JS)
└── ROADMAP_ADVANCED.md            # Dokumentasi desain & keputusan teknis
```

## 1. Setup XAMPP (Database)

1. Install & buka **XAMPP Control Panel**
2. Start service **Apache** dan **MySQL**
3. Buka phpMyAdmin di `http://localhost/phpmyadmin`
4. Buka tab **SQL**, paste **seluruh isi** `database/schema.sql`, klik **Go**
   (membuat tabel: `recipes`, `users`, `favorites`, `meal_plans`, `contact_messages`,
   `chat_history`, `user_preferences`, `chat_feedback`)
5. Paste juga **seluruh isi** `database/schema_meal_plan_ai.sql`, klik **Go**
   (membuat tabel tambahan buat fitur Meal Planner AI)

## 2. Setup Python Environment

Buka folder `sambal-ai` di VS Code, buka terminal (`` Ctrl+` ``):

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Konfigurasi .env

```powershell
copy .env.example .env
```

Buka file `.env`, isi:
- `GEMINI_API_KEY` — wajib, dari https://aistudio.google.com/apikey
- `SECRET_KEY` — isi teks acak bebas
- `YOUTUBE_API_KEY` — **opsional**. Kalau diisi, fitur tutorial video aktif. Kalau
  dikosongkan, sistem tetap jalan normal, cuma section video-nya nggak muncul.
  Cara dapetin: [Google Cloud Console](https://console.cloud.google.com/) → New
  Project → aktifkan "YouTube Data API v3" → Credentials → Create API Key.
- Konfigurasi DB biasanya default XAMPP udah pas, nggak perlu diubah

## 4. Import Dataset

```powershell
python database/import_csv_to_db.py
```

Import 14.945 resep Indonesia dari `Indonesian_Food_Recipes.csv` (taruh filenya
di root project, sejajar `app.py`, sebelum jalanin) ke tabel `recipes` — SATU-SATUNYA
dataset yang dipakai di seluruh project ini (chat AI, menu browsing, dan Meal
Planner AI semuanya baca dari tabel yang sama).

## 5. Jalankan

```powershell
python app.py
```

Buka **http://localhost:5000**

## Fitur Intelligence yang Sudah Aktif

- **Context-aware**: chat mendeteksi `urgency` (mendesak/nanti) dan `preferensi`
  (hemat/cepat/sehat/porsi) dari kalimat bebas, memengaruhi ranking resep & saran belanja
- **Explainable scoring**: tiap jawaban chat disertai blok `[Skor Kecocokan]` dengan
  angka yang dihitung deterministik di Python (bukan dikarang LLM)
- **User preference memory**: kategori yang sering difavoritkan otomatis nambah bobot
  di rekomendasi berikutnya (tabel `user_preferences`)
- **Feedback loop**: tombol 👍/👎 di tiap balasan chat, tersimpan ke `chat_feedback`
- **Ingredient matching + substitusi + shopping**: kalau ada bahan yang kamu sebut tapi
  nggak ada di resep pilihan, otomatis muncul saran pengganti + link cari bahan
  (toko fisik via Maps kalau mendesak, marketplace kalau buat stok)
- **Tutorial video**: muncul di halaman detail resep DAN di jawaban chat (kalau
  `YOUTUBE_API_KEY` diisi)
- **Cooking timeline**: estimasi waktu tiap langkah masak, muncul di halaman detail resep

## Troubleshooting

**"Access denied for user 'root'"** — cek `DB_PASSWORD` di `.env`, default kosong di XAMPP.

**"Can't connect to MySQL server"** — pastikan MySQL di XAMPP Control Panel statusnya hijau.

**Chat minta login padahal udah login** — cek `SECRET_KEY` di `.env` sudah terisi, restart `python app.py`.

**Chat balas soal "GEMINI_API_KEY belum diisi"** — isi `.env`, restart server.

**Video tutorial nggak pernah muncul** — cek `YOUTUBE_API_KEY` terisi & valid, dan
kuota harian (100 pencarian gratis/hari) belum habis. Kalau kosong, ini memang
fitur opsional yang sengaja nonaktif tanpa key.

**`ModuleNotFoundError` pas run `app.py`** — pastikan venv aktif (`(venv)` muncul di
prompt) dan `pip install -r requirements.txt` sudah selesai tanpa error.

**Import CSV gagal di tengah** — jalankan ulang `python database/import_csv_to_db.py`,
otomatis `TRUNCATE` tabel `recipes` dulu sebelum import ulang, aman diulang.

**Error `Cannot truncate a table referenced in a foreign key constraint`** — sudah
ditangani di `import_csv_to_db.py` (matiin FK check sementara saat truncate), pastikan
kamu pakai file yang ada di zip ini, bukan versi lama.