# SAMBAL.AI — Roadmap Pengembangan Lanjutan
### Dari Sequential 3-Agent ke Parallel Multi-Agent Intelligence System

Dokumen ini adalah panduan implementasi berbasis kode `app.py` yang sudah ada (568 baris, Flask + MySQL + Gemini 2.5 Flash). Semua rekomendasi bersifat **incremental** — memodifikasi/menambah, bukan membangun ulang.

---

## 1. Review & Refactor Kode

### 1.1 Struktur Saat Ini (Kondisi Aktual)

```
app.py  (satu file, ~700 baris)
├── Config (DB_CONFIG, GEMINI_API_KEY, client)
├── Data statis (STOPWORDS_ID, CATEGORIES, BLOG_POSTS, FAQS)
├── Auth helpers (login_required, inject_user)
├── DB helpers (get_connection, load_all_recipes)
├── Agent 1: agent_ingredient_analyzer()
├── Agent 2: agent_recipe_finder()
├── Agent 3: agent_decision_maker()
├── Orchestrator: run_pipeline()
└── 20+ route functions (landing, menu, auth, favorit, meal planner, chat, dst)
```

### 1.2 Masalah Modularitas & Scalability

| Masalah | Dampak | Prioritas |
|---|---|---|
| Semua kode di 1 file (`app.py`) | Sulit di-test terpisah, merge conflict kalau kerja tim, sulit nambah agent baru tanpa file makin panjang | Tinggi |
| Agent function langsung manggil `client.models.generate_content` | Nggak ada abstraction layer — kalau mau ganti model/nambah retry policy, harus edit tiap fungsi | Tinggi |
| `load_all_recipes()` pakai module-level global `_df_cache` | Nggak thread-safe kalau nanti pindah ke multi-worker (Gunicorn dengan >1 worker bakal punya cache terpisah per-proses, potensi inconsistent) | Sedang |
| Tidak ada layer "orchestrator" yang bisa jalanin agent secara paralel | `run_pipeline()` murni sekuensial — nggak ada tempat buat nambah agent yang jalan bareng | Tinggi (blocker buat req #7) |
| Prompt (string literal panjang) nempel di kode | Sulit di-versioning/di-tuning terpisah dari logic | Rendah |

### 1.3 Struktur Baru yang Diusulkan

```
sambal-ai/
├── app.py                      # HANYA routes + Flask setup (tipis)
├── config.py                   # Semua konfigurasi (DB, API keys, konstanta)
├── agents/
│   ├── __init__.py
│   ├── base.py                  # BaseAgent class (abstraksi umum)
│   ├── ingredient_analyzer.py   # Agent 1 (existing, dipindah)
│   ├── recipe_finder.py         # Agent 2 (existing, dipindah)
│   ├── decision_maker.py        # Agent 3 (existing, dipindah)
│   ├── substitution_agent.py    # BARU
│   ├── nutrition_agent.py       # BARU
│   ├── budget_agent.py          # BARU
│   ├── video_agent.py           # BARU
│   ├── shopping_agent.py        # BARU
│   └── aggregator.py            # BARU — gabungin hasil semua agent
├── orchestrator.py              # Orkestrasi async/paralel
├── services/
│   ├── db.py                     # get_connection(), load_all_recipes()
│   ├── youtube_service.py        # BARU
│   └── shopping_links.py         # BARU
├── prompts/
│   └── *.txt atau *.py           # Prompt template terpisah dari logic
└── templates/, static/           # tidak berubah
```

**Kenapa struktur ini penting buat jawaban ke dosen:** ini yang bikin "bisa dikembangkan ke multi-agent" jadi nyata secara arsitektur, bukan cuma klaim — tiap agent adalah unit independen (class/module) yang bisa di-test sendiri, dipanggil sendiri, dan **dipanggil paralel** lewat orchestrator.

### 1.4 Contoh Refactor: `BaseAgent` Abstraction

```python
# agents/base.py
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    """Kontrak umum semua agent — memudahkan orchestrator memanggil
    agent apapun dengan cara seragam (penting buat paralelisasi)."""

    name: str = "base_agent"

    def __init__(self, client, model_name: str = "gemini-2.5-flash"):
        self.client = client
        self.model_name = model_name

    @abstractmethod
    async def run(self, context: dict) -> dict:
        """context: state yang mengalir antar agent.
        return: dict hasil, akan di-merge ke context oleh orchestrator."""
        ...

    async def _call_llm(self, prompt: str, json_mode: bool = False):
        # Wrapper terpusat: retry, timeout, logging — sekali definisikan,
        # dipakai semua agent turunan.
        import asyncio
        from google.genai import types
        config = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=self.model_name, contents=prompt, config=config
            ),
        )
```

Setiap agent existing (`agent_ingredient_analyzer`, dst) tinggal dibungkus jadi class yang extends `BaseAgent`, isi method `run()` pakai logic yang udah ada — **tidak perlu nulis ulang logic-nya**, cuma dipindah lokasi & dibungkus interface seragam.

---

## 2. Ingredient-Based Recommendation & Substitusi Bahan

### 2.a Ingredient-Based Recommendation (sudah ada, ini peningkatannya)

Kode `agent_recipe_finder()` yang ada sekarang pakai **exact substring match**. Peningkatan konkret:

```python
# agents/recipe_finder.py — versi upgrade
SYNONYM_MAP = {
    "sapi": ["daging sapi", "has sapi", "sandung lamur", "sengkel"],
    "santan": ["santan kelapa", "santan instan", "kara"],
    "cabai": ["cabe", "cabai rawit", "cabai merah", "lombok"],
    # ... bisa terus ditambah, atau nanti diganti embedding-based
}

def expand_terms(terms: list[str]) -> list[str]:
    expanded = set(terms)
    for t in terms:
        for canonical, variants in SYNONYM_MAP.items():
            if t == canonical or t in variants:
                expanded.update(variants + [canonical])
    return list(expanded)
```
Ini dipanggil sebelum scoring di `agent_recipe_finder()` — perbaikan kecil tapi langsung nambah recall (nangkep "cabe" walau user nulis "cabai").

### 2.b Substitusi Bahan — Agent Baru

```python
# agents/substitution_agent.py
class SubstitutionAgent(BaseAgent):
    name = "substitution_agent"

    PROMPT = """Kamu adalah ahli substitusi bahan masakan Indonesia.
Untuk tiap bahan yang TIDAK TERSEDIA di bawah ini, berikan alternatif yang
umum ditemukan di dapur Indonesia, beserta rasio takaran kalau beda.
Balas HANYA JSON: {{"substitutions": [{{"bahan_asli": "...", "pengganti": "...", "catatan": "..."}}]}}

Bahan yang tidak tersedia: {missing_ingredients}
Konteks resep: {recipe_title}
"""

    async def run(self, context: dict) -> dict:
        missing = context.get("missing_ingredients", [])
        if not missing:
            return {"substitutions": []}
        prompt = self.PROMPT.format(
            missing_ingredients=", ".join(missing),
            recipe_title=context.get("recipe_title", ""),
        )
        resp = await self._call_llm(prompt, json_mode=True)
        import json
        return json.loads(resp.text)
```

**Cara nentuin `missing_ingredients`:** bandingin `bahan` dari Agent 1 (yang user PUNYA) vs bahan yang disebut di kolom `ingredients` resep pilihan (dari Agent 3) — set difference sederhana, nggak butuh LLM buat ini:

```python
def find_missing_ingredients(user_bahan: list[str], recipe_ingredients_text: str) -> list[str]:
    recipe_words = set(recipe_ingredients_text.lower().split())
    return [b for b in user_bahan if b.lower() not in recipe_words]
```

---

## 3. Integrasi Video Tutorial (YouTube Data API v3)

### 3.1 Setup
1. Buka [Google Cloud Console](https://console.cloud.google.com/) → New Project
2. Aktifkan **"YouTube Data API v3"**
3. Buat API Key (Credentials → Create Credentials → API Key)
4. Kuota gratis: 10.000 unit/hari, `search.list` = 100 unit → **~100 pencarian gratis/hari**

### 3.2 Implementasi

```python
# services/youtube_service.py
import requests

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

def find_tutorial_video(recipe_title: str) -> dict | None:
    if not YOUTUBE_API_KEY:
        return None
    params = {
        "part": "snippet",
        "q": f"cara masak {recipe_title}",
        "type": "video",
        "maxResults": 1,
        "relevanceLanguage": "id",
        "key": YOUTUBE_API_KEY,
    }
    resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return None
    video = items[0]
    video_id = video["id"]["videoId"]
    return {
        "title": video["snippet"]["title"],
        "channel": video["snippet"]["channelTitle"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": video["snippet"]["thumbnails"]["medium"]["url"],
    }
```

### 3.3 Agent Wrapper (buat orchestration paralel)

```python
# agents/video_agent.py
class VideoAgent(BaseAgent):
    name = "video_agent"

    async def run(self, context: dict) -> dict:
        import asyncio
        from services.youtube_service import find_tutorial_video
        recipe_title = context.get("recipe_title", "")
        loop = asyncio.get_event_loop()
        # requests itu blocking, jalanin di executor biar nggak nge-block event loop
        video = await loop.run_in_executor(None, find_tutorial_video, recipe_title)
        return {"tutorial_video": video}
```

### 3.4 Integrasi ke Route yang Sudah Ada

Di `recipe_detail()` (route existing), tambah panggilan ini setelah `recipe` di-load:
```python
from services.youtube_service import find_tutorial_video
tutorial = find_tutorial_video(recipe["title"])
return render_template("recipe_detail.html", recipe=recipe, ..., tutorial=tutorial)
```
Lalu di `recipe_detail.html`, tambah blok kondisional nampilin thumbnail + link kalau `tutorial` ada.

---

## 4. Smart Shopping — Superindo (Direvisi: Urgency-Aware)

### 4.1 Realitas Teknis (Penting Buat Transparansi ke Dosen)

Superindo **tidak punya API publik maupun website search resmi** — belanja online cuma lewat app "My Super Indo" yang tertutup. **Tapi Superindo punya toko resmi terverifikasi di Tokopedia** (`tokopedia.com/superindo-indonesia-raya`), yang punya fitur search-within-shop. Ini jadi jalan yang **jujur dan beneran jalan**, bukan reka-reka.

### 4.2 Masalah yang Ditemukan & Diperbaiki

**Masalah:** Tokopedia/marketplace itu e-commerce biasa — pengiriman antar kota, bisa 1-3 hari. Kalau user "lagi masak, kurang bahan hari ini", ngarahin ke Tokopedia itu **nggak masuk akal** — bahan baru sampai pas masakan udah keburu basi ditinggal nunggu.

**Solusinya:** bedain dua kebutuhan yang beda konteks waktu:

| Situasi | Solusi Prioritas | Kenapa |
|---|---|---|
| **"Kurang bahan, mau masak SEKARANG"** | **Google Maps** → toko/minimarket/warung fisik terdekat | Bisa dijangkau jalan kaki/motor 5-15 menit, langsung lanjut masak |
| **"Mau restock buat minggu depan"** | Tokopedia/Superindo/marketplace | Nggak buru-buru, bisa bandingin harga, oke nunggu 1-2 hari |

Aplikasi grocery instan (Astro, Sayurbox, Segari — antar 15-45 menit) sebenarnya lebih pas buat kasus mendesak dibanding marketplace biasa, tapi karena nggak ada URL search resmi yang bisa dipastikan formatnya, pendekatan paling jujur adalah **merekomendasikan nama aplikasinya** (bukan link langsung yang berisiko broken), biar user cari sendiri di app yang sudah terinstall.

### 4.3 Implementasi — Urgency-Aware Shopping

```python
# services/shopping_links.py
import re
from urllib.parse import quote

SUPERINDO_TOKOPEDIA_SLUG = "superindo-indonesia-raya"

def extract_shopping_list(ingredients_text: str) -> list[str]:
    """Parse teks bahan (format: '1 kg ayam--2 buah tomat--...') jadi list bersih."""
    raw_items = re.split(r"--|\n", ingredients_text)
    cleaned = []
    for item in raw_items:
        item = item.strip()
        item = re.sub(r"^[\d/.,]+\s*(kg|gram|gr|ml|liter|l|sdm|sdt|buah|butir|siung|lembar|batang)?\s*", "", item, flags=re.IGNORECASE)
        if item:
            cleaned.append(item)
    return cleaned


def generate_superindo_link(ingredient_name: str) -> str:
    query = quote(ingredient_name)
    return f"https://www.tokopedia.com/{SUPERINDO_TOKOPEDIA_SLUG}/search?q={query}"


def generate_maps_link(ingredient_name: str) -> str:
    query = quote(f"beli {ingredient_name} terdekat")
    return f"https://www.google.com/maps/search/{query}"


INSTANT_GROCERY_APPS = ["Astro", "Sayurbox", "Segari"]


def build_shopping_suggestion(ingredient_name: str, urgency: str = "sekarang") -> dict:
    """
    urgency: "sekarang" (butuh masak hari ini/mendesak) atau "nanti" (restock biasa)
    """
    maps_url = generate_maps_link(ingredient_name)

    if urgency == "sekarang":
        return {
            "bahan": ingredient_name,
            "prioritas": "toko_fisik",
            "maps_url": maps_url,
            "marketplace_url": None,  # sengaja nggak diprioritaskan, nunggu 1-3 hari nggak relevan
            "catatan": (
                f"Cek toko/minimarket terdekat dulu buat '{ingredient_name}'. "
                f"Kalau areamu dijangkau, aplikasi grocery instan ({', '.join(INSTANT_GROCERY_APPS)}) "
                "juga bisa jadi opsi (antar 15-45 menit)."
            ),
        }
    return {
        "bahan": ingredient_name,
        "prioritas": "marketplace",
        "maps_url": maps_url,
        "marketplace_url": generate_superindo_link(ingredient_name),
        "catatan": "Buat stok bahan ke depan, bisa cek harga & promo di marketplace.",
    }


def build_shopping_list_with_links(ingredients_text: str, urgency: str = "sekarang") -> list[dict]:
    items = extract_shopping_list(ingredients_text)
    return [build_shopping_suggestion(item, urgency) for item in items]
```

### 4.4 Deteksi Urgency Otomatis (Perluasan Agent 1)

Tambahkan field di `ANALYZER_PROMPT` (Ingredient Analyzer) yang sudah ada:

```python
# Tambahan di skema JSON Agent 1:
"urgency": "salah satu dari: sekarang | nanti"
# "sekarang" kalau user bilang "lagi masak", "sekarang mau bikin", "kurang nih pas masak"
# "nanti" kalau user bilang "mau belanja bulanan", "buat stok", "rencana minggu depan"
```

Field ini mengalir dari Agent 1 → dipakai langsung oleh Shopping Agent, tanpa perlu logic tambahan di tempat lain.

### 4.5 Agent Wrapper

```python
# agents/shopping_agent.py
class ShoppingAgent(BaseAgent):
    name = "shopping_agent"

    async def run(self, context: dict) -> dict:
        from services.shopping_links import build_shopping_list_with_links
        missing = context.get("missing_ingredients", [])
        if not missing:
            return {"shopping_suggestions": []}
        ingredients_text = "--".join(missing)
        urgency = context.get("urgency", "sekarang")
        shopping_list = build_shopping_list_with_links(ingredients_text, urgency)
        return {"shopping_suggestions": shopping_list}
```

**Catatan:** Shopping Agent sekarang cuma jalan buat `missing_ingredients` (hasil Ingredient Matching Agent), bukan buat SEMUA bahan resep — nggak ada gunanya nyaranin beli bahan yang user udah punya.

### 4.6 Integrasi Final: Video + Substitusi + Shopping Digabung

Setelah Video Agent (section 3), Substitution Agent (section 2.b), dan Shopping Agent (di atas) masing-masing selesai jalan **paralel**, Aggregator Agent menggabungkan semuanya jadi satu response:

```python
# agents/aggregator.py
class AggregatorAgent(BaseAgent):
    name = "aggregator_agent"

    async def run(self, context: dict) -> dict:
        return {
            "final_response": {
                "resep": {
                    "title": context["recipe_title"],
                    "bahan": context["recipe_ingredients"],
                    "langkah": context["recipe_steps"],
                },
                "tutorial_video": context.get("tutorial_video"),
                # dari Video Agent: {"title", "channel", "url", "thumbnail"}

                "bahan_kurang": context.get("missing_ingredients", []),
                "substitusi": context.get("substitutions", []),
                # dari Substitution Agent: [{"bahan_asli", "pengganti", "catatan"}]

                "belanja": context.get("shopping_suggestions", []),
                # dari Shopping Agent (urgency-aware): [{"bahan", "prioritas", "maps_url", "marketplace_url", "catatan"}]

                "skor": context.get("recipe_score"),
                # dari Recipe Scoring System (section 6.b)
            }
        }
```

**Urutan tampilan di UI (halaman detail resep), mengikuti urutan logis proses masak:**

```
[Detail Resep — bahan & langkah]
        ↓
[▶️ Tonton Tutorial]                     <- Video Agent
        ↓
[⚠️ Bahan yang Kurang: santan, daun jeruk]
   → Pengganti: santan bisa pakai susu cair + minyak    <- Substitution Agent
   → Daun jeruk: 📍 Cek toko terdekat [Google Maps]      <- Shopping Agent (urgency=sekarang)
        ↓
[Skor Kecocokan: 82/100 — kenapa direkomendasikan]       <- Recipe Scoring + Explainable AI
```

Video dan Shopping tetap dua section yang **independen secara proses** (jalan paralel, nggak saling nunggu), tapi **tampil bersamaan** di halaman yang sama karena keduanya sama-sama menunggu hasil dari Ingredient Matching Agent (resep final + daftar bahan kurang) sebelum ditampilkan.

---

## 5. Dataset Masakan Diet

### 5.1 Dataset yang Kamu Upload — Analisis

```
Kolom: Diet_type, Recipe_name, Cuisine_type, Protein(g), Carbs(g), Fat(g), Extraction_day, Extraction_time
Jumlah: 7.806 baris
Diet_type: paleo, vegan, keto, mediterranean, dash
Cuisine_type: american, mexican, chinese, south east asian, dst (BUKAN Indonesia)
```

**Catatan penting:** dataset ini TIDAK punya kolom `ingredients` dan resepnya sama sekali beda dari 14.945 resep Indonesia yang sudah ada. **Tidak bisa** di-join langsung by title/ID. Kalori juga belum ada, tapi bisa dihitung: `kalori ≈ (protein × 4) + (carbs × 4) + (fat × 9)`.

### 5.2 Struktur Tabel yang Diusulkan

```sql
CREATE TABLE IF NOT EXISTS diet_recipes (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    diet_type     VARCHAR(30) NOT NULL,      -- paleo, vegan, keto, mediterranean, dash
    recipe_name   VARCHAR(255) NOT NULL,
    cuisine_type  VARCHAR(50),
    protein_g     DECIMAL(6,2) DEFAULT 0,
    carbs_g       DECIMAL(6,2) DEFAULT 0,
    fat_g         DECIMAL(6,2) DEFAULT 0,
    calories_kcal DECIMAL(8,2) GENERATED ALWAYS AS (protein_g*4 + carbs_g*4 + fat_g*9) STORED,
    INDEX idx_diet_type (diet_type)
) ENGINE=InnoDB;
```

### 5.3 Contoh Data (5 baris dari dataset asli)

| diet_type | recipe_name | cuisine_type | protein_g | carbs_g | fat_g | calories_kcal (dihitung) |
|---|---|---|---|---|---|---|
| paleo | Bone Broth From 'Nom Nom Paleo' | american | 5.22 | 1.29 | 3.20 | ~55.8 |
| paleo | Paleo Effect Asian-Glazed Pork Sides | south east asian | 181.55 | 28.62 | 146.14 | ~2159.6 |
| keto | (contoh dari dataset kamu) | ... | ... | ... | ... | ... |
| vegan | (contoh dari dataset kamu) | ... | ... | ... | ... | ... |
| mediterranean | (contoh dari dataset kamu) | ... | ... | ... | ... | ... |

### 5.4 Cara Integrasi — Karena Datanya Terpisah dari Resep Indonesia

**Bukan** merge ke tabel `recipes` (beda semesta data). Pendekatan yang jujur dan tetap berguna:

**Opsi A — Fitur "Diet Explorer" Terpisah** (paling simpel, direkomendasikan)
- Halaman baru `/diet` — browsing 7.806 resep diet, filter by `diet_type`, sort by kalori/protein
- Independen dari sistem 3-agent utama, murni pandas filter (sama kayak `/menu`)

**Opsi B — Sebagai Referensi Kontekstual buat Agent 1**
- Kalau user bilang "aku lagi diet keto", Agent 1 deteksi intent tambahan `diet_preference: "keto"`
- Sistem kasih insight nutrisi umum dari `diet_recipes` (rata-rata makro tipe keto) sebagai **konteks edukatif**, BUKAN klaim bahwa resep Indonesia yang direkomendasikan itu "resep keto asli" (karena kita nggak punya data nutrisi buat 14.945 resep Indonesia)

### 5.5 Perbandingan Pendekatan: RAG vs Fine-Tuning vs Hybrid

| Aspek | RAG (Retrieval) | Fine-Tuning | Hybrid |
|---|---|---|---|
| **Cara kerja** | Query dataset saat runtime, hasil dikasih ke LLM sebagai konteks | Model dilatih ulang pakai dataset diet | Kombinasi: retrieval buat data faktual + LLM buat reasoning |
| **Biaya** | Rendah — cuma query DB | Tinggi — butuh GPU, waktu, dataset besar & bersih | Sedang |
| **Update data** | Instan — tinggal update tabel | Harus re-train ulang tiap ada data baru | Instan (bagian retrieval-nya) |
| **Akurasi faktual** | Tinggi — data selalu dari sumber asli, nggak ada hallucinasi | Rawan lupa/halusinasi kalau model overfitting atau dataset kurang besar | Tinggi |
| **Kompleksitas implementasi** | Rendah-sedang (sudah ada polanya di Agent 2 & 3) | Tinggi — butuh infrastruktur ML training | Sedang |
| **Cocok untuk skala tugas mahasiswa?** | ✅ Ya, paling realistis | ❌ Butuh resource di luar jangkauan tugas kuliah biasa | ✅ Ya, dan paling "advanced" secara konsep |

**Rekomendasi:** pakai **Hybrid** — retrieval buat ambil fakta nutrisi dari `diet_recipes` (persis kayak Agent 2 sekarang), lalu LLM (Agent 3 gaya) yang menjelaskan & mengaitkan ke kebutuhan user. Ini **sebenarnya pola yang SUDAH kamu pakai** di 3-agent existing (RAG sederhana) — tinggal diperluas ke sumber data kedua. Fine-tuning **tidak disarankan** untuk scope tugas kuliah karena butuh infrastruktur training yang di luar kebutuhan real project ini.

---

## 6. Fitur Lanjutan (Intelligence)

### 6.a Context-Aware Recommendation

Perluas skema Agent 1 buat nangkep intent gaya hidup:

```python
ANALYZER_PROMPT_V2 = """... (prompt existing) ...
Tambahkan juga field:
"preferensi": {{
    "hemat": true/false,       // user sebut "murah", "hemat", "budget"
    "cepat": true/false,       // user sebut "cepat", "buru-buru", "praktis"
    "sehat": true/false,       // user sebut "sehat", "diet", "kalori"
    "porsi": angka atau null   // kalau user sebut jumlah orang
}}
"""
```
Field `preferensi` ini lalu dipakai buat **bobot ulang scoring** di Recipe Finder (misal kalau `hemat=true`, boost resep dengan `total_ingredients` sedikit).

### 6.b Recipe Scoring System

```python
def calculate_recipe_score(recipe: dict, analysis: dict, user_preferensi: dict) -> dict:
    """Scoring transparan — tiap komponen bisa dijelasin (mendukung Explainable AI di 6.c)"""
    scores = {}

    # 1. Kecocokan bahan (0-40 poin)
    scores["kecocokan_bahan"] = min(recipe.get("_score", 0) * 10, 40)

    # 2. Nutrisi (0-30 poin) — kalau ada data diet_recipes yang relevan
    if user_preferensi.get("sehat"):
        scores["nutrisi"] = 30 if recipe.get("is_healthy_flag") else 15
    else:
        scores["nutrisi"] = 20  # netral

    # 3. Budget/simplicity (0-30 poin) — proxy pakai jumlah bahan (makin dikit makin murah/simpel)
    total_bahan = recipe.get("total_ingredients", 10)
    scores["budget"] = max(30 - total_bahan, 5)

    scores["total"] = sum(scores.values())
    return scores
```

### 6.c Explainable AI

Modifikasi prompt Agent 3 (Decision Maker) — tambahkan instruksi eksplisit buat mencantumkan skor:

```python
DECISION_PROMPT_ADDITION = """
Selain format yang sudah ada, tambahkan section:
[Skor Kecocokan]
- Kecocokan bahan: {kecocokan_bahan}/40 — karena ...
- Nutrisi: {nutrisi}/30 — karena ...
- Budget/simplicity: {budget}/30 — karena ...
- Total: {total}/100
"""
```
Ini yang jadi jawaban ke kritik dosen soal "black box" — user (dan dosen) bisa lihat **kenapa** resep itu direkomendasikan, bukan cuma hasil akhir.

### 6.d Smart Cooking Timeline

```python
def parse_cooking_timeline(steps_text: str) -> list[dict]:
    """Estimasi waktu per langkah pakai heuristik kata kunci + LLM buat kasus ambigu."""
    import re
    steps = re.split(r"\d+\)", steps_text)
    timeline = []
    cumulative = 0
    for step in steps:
        step = step.strip()
        if not step:
            continue
        # heuristik durasi dari kata kunci umum
        duration = 5  # default 5 menit
        if re.search(r"rebus|masak.*\d+\s*menit", step, re.IGNORECASE):
            match = re.search(r"(\d+)\s*menit", step)
            duration = int(match.group(1)) if match else 15
        elif re.search(r"marinasi|diamkan", step, re.IGNORECASE):
            duration = 30
        cumulative += duration
        timeline.append({"step": step, "durasi_menit": duration, "waktu_kumulatif": cumulative})
    return timeline
```
Ditampilkan di UI sebagai progress bar/timeline di halaman detail resep.

### 6.e User Preference Memory

```sql
CREATE TABLE IF NOT EXISTS user_preferences (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL UNIQUE,
    suka_kategori JSON,      -- ["ayam", "tempe"] — diupdate dari histori favorit
    diet_type    VARCHAR(30),
    budget_mode  BOOLEAN DEFAULT FALSE,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;
```
Diupdate otomatis tiap kali user nge-favoritkan resep (trigger sederhana di route `toggle_favorite` yang sudah ada — tambah increment counter kategori di JSON).

### 6.f Feedback Loop

```sql
CREATE TABLE IF NOT EXISTS chat_feedback (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    chat_history_id INT NOT NULL,
    rating       TINYINT,           -- 1 (nggak membantu) - 5 (sangat membantu)
    comment      TEXT,
    FOREIGN KEY (chat_history_id) REFERENCES chat_history(id) ON DELETE CASCADE
) ENGINE=InnoDB;
```
UI: tombol 👍/👎 di tiap balasan chat (mengacu ke `chat_history.id` yang sudah ada). Datanya dipakai buat analisis kualitatif (bukan re-training model — itu di luar scope realistis tugas kuliah), misalnya laporan "X% rekomendasi dirating positif" sebagai bagian evaluasi sistem di laporan akhir.

---

## 7. Arsitektur Multi-Agent Paralel

### 7.1 Diagram Alur

```
                              ┌─────────────────────┐
                              │   Planner Agent      │  <- decide agent mana yg perlu dipanggil
                              │  (analisis intent)    │     berdasar Agent 1 (existing)
                              └──────────┬───────────┘
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 │                       │                       │
                 ▼                       ▼                       ▼
        ┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐
        │  Recipe Agent   │    │  Nutrition Agent  │    │  Budget Agent     │
        │ (existing Ag.2) │    │  (query diet_recipes)   │ (hitung simplicity)│
        └────────┬────────┘    └─────────┬─────────┘    └─────────┬─────────┘
                 │                       │                        │
                 └───────────────────────┼────────────────────────┘
                                         ▼
                              ┌─────────────────────┐
                              │  Ingredient Matching  │  <- cross-check bahan user
                              │       Agent           │     vs resep terpilih
                              └──────────┬───────────┘
                                         │
                       ┌─────────────────┼─────────────────┐
                       ▼                 ▼                 ▼
              ┌───────────────┐ ┌────────────────┐ ┌────────────────┐
              │ Substitution   │ │  Video Agent   │ │ Shopping Agent  │
              │    Agent       │ │ (YouTube API)  │ │  (Superindo)    │
              └───────┬───────┘ └───────┬────────┘ └────────┬────────┘
                      │                 │                    │
                      └─────────────────┼────────────────────┘
                                       ▼
                            ┌─────────────────────┐
                            │  Aggregator Agent    │  <- gabung semua hasil,
                            │  (= Decision Maker    │     format final + skor
                            │   yang diperluas)     │     + explanation
                            └─────────────────────┘
```

**Yang jalan paralel (nggak saling butuh hasil satu sama lain):**
- `Recipe Agent`, `Nutrition Agent`, `Budget Agent` — bisa jalan bareng setelah Planner selesai
- `Substitution Agent`, `Video Agent`, `Shopping Agent` — bisa jalan bareng setelah resep final dipilih (mereka independen satu sama lain)

**Yang tetap sekuensial (data dependency, nggak bisa dihindari):**
- Planner harus selesai dulu sebelum Recipe/Nutrition/Budget jalan
- Ingredient Matching butuh resep final dulu (dari Recipe Agent), baru bisa jalan
- Aggregator harus nunggu SEMUA agent lain selesai

### 7.2 Implementasi Orchestrator (asyncio)

```python
# orchestrator.py
import asyncio

class Orchestrator:
    def __init__(self, agents: dict):
        self.agents = agents  # {"recipe": RecipeAgent(), "nutrition": NutritionAgent(), ...}

    async def run_parallel_phase(self, agent_names: list[str], context: dict) -> dict:
        """Jalankan beberapa agent BARENGAN, gabung hasilnya ke context."""
        tasks = [self.agents[name].run(context) for name in agent_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(agent_names, results):
            if isinstance(result, Exception):
                context[f"{name}_error"] = str(result)
            else:
                context.update(result)
        return context

    async def run_pipeline(self, user_input: str) -> dict:
        context = {"user_input": user_input}

        # Fase 1: sekuensial (planner butuh jalan duluan)
        context.update(await self.agents["planner"].run(context))

        # Fase 2: PARALEL — recipe, nutrition, budget nggak saling butuh
        context = await self.run_parallel_phase(["recipe", "nutrition", "budget"], context)

        # Fase 3: sekuensial (butuh resep final dari fase 2)
        context.update(await self.agents["ingredient_matching"].run(context))

        # Fase 4: PARALEL — substitution, video, shopping independen
        context = await self.run_parallel_phase(["substitution", "video", "shopping"], context)

        # Fase 5: aggregate semuanya
        context.update(await self.agents["aggregator"].run(context))

        return context
```

### 7.3 Integrasi ke Flask (existing `/api/chat`)

Flask sync itu nggak native support `async def` di route biasa. Cara paling praktis tanpa migrasi besar-besaran ke FastAPI/Quart:

```python
# app.py — modifikasi route /api/chat yang sudah ada
import asyncio
from orchestrator import Orchestrator

orchestrator = Orchestrator(agents={...})  # inisialisasi sekali di startup

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if not session.get("user_id"):
        return jsonify({"reply": "__LOGIN_REQUIRED__"}), 401
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    # Flask sync -> jalanin event loop async secara terisolasi per-request
    result = asyncio.run(orchestrator.run_pipeline(message))

    # ... simpan ke chat_history seperti sekarang ...
    return jsonify({"reply": result.get("final_answer")})
```

**Catatan realistis:** `asyncio.run()` di dalam route Flask sync itu valid dan gampang, tapi kalau mau *benar-benar* scalable (banyak concurrent user), pertimbangan jangka panjang adalah migrasi ke **FastAPI** (native async) atau **Flask + Quart**. Untuk scope tugas kuliah, pendekatan `asyncio.run()` di atas **sudah cukup dan legitimate** buat mendemonstrasikan paralelisasi.

---

## 8. Implementasi Teknis — Ringkasan Prioritas

Supaya nggak overwhelmed, urutan implementasi yang disarankan (dari yang paling murah/cepat ke paling kompleks):

| Urutan | Fitur | Effort | Dependency |
|---|---|---|---|
| 1 | Diet Explorer (`/diet` page dari `All_Diets.csv`) | Rendah | Tidak ada — bisa langsung |
| 2 | Video Agent (YouTube API) | Rendah | Butuh API key YouTube |
| 3 | Shopping Agent (link Superindo/Maps) | Rendah | Tidak ada |
| 4 | Substitution Agent | Sedang | Butuh Agent 1 & 3 existing |
| 5 | Recipe Scoring + Explainable AI | Sedang | Modifikasi prompt Agent 3 |
| 6 | Refactor ke struktur folder `agents/` | Sedang | Tidak ada, tapi effort "beres-beres" |
| 7 | User Preference Memory + Feedback Loop | Sedang | Tabel baru |
| 8 | Orchestrator async penuh (paralel beneran) | Tinggi | Semua agent di atas harus ada dulu |

---

## 9. Kesimpulan untuk Presentasi/Laporan

**Klaim yang BISA kamu buat dengan jujur setelah semua ini diimplementasi:**
- ✅ "Sistem menggunakan lebih dari 3 agent dengan pembagian tanggung jawab spesifik"
- ✅ "Sebagian agent (Recipe, Nutrition, Budget) berjalan paralel menggunakan asyncio"
- ✅ "Sistem terintegrasi dengan API eksternal asli (YouTube Data API v3)"
- ✅ "Sistem memiliki explainable scoring, bukan black-box recommendation"
- ✅ "Sistem punya user preference memory dan feedback loop untuk continuous improvement"
- ✅ "Shopping Agent bersifat urgency-aware — membedakan kebutuhan mendesak (toko fisik terdekat via Maps) vs restock biasa (marketplace), bukan asal redirect ke e-commerce yang makan waktu kirim"

**Klaim yang HARUS dihindari (supaya nggak kena tanya balik yang nggak bisa dijawab):**
- ❌ "Terintegrasi API resmi Superindo/GrabMart" (nggak ada API publiknya — jelasin pakai pendekatan link/deep-link)
- ❌ "Rekomendasi diet berbasis resep Indonesia yang sama" (dataset diet & dataset Indonesia itu terpisah, jangan diklaim tergabung)
- ❌ "Model di-fine-tune" kalau sebenarnya cuma prompt engineering + RAG (dua hal berbeda secara teknis)
