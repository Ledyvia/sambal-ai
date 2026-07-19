"""Meal Plan Selector — pilih resep buat SELURUH slot minggu ini (hari x jenis
makan) dalam SATU kali panggilan Gemini, bukan satu panggilan per slot.
Alasan: kuota Gemini gratis kecil (20 request/hari) — kalau tiap slot manggil
LLM sendiri, 1x generate plan seminggu penuh (7 hari x 3 jenis makan = 21 slot)
bisa langsung ngabisin seluruh kuota harian dalam sekali klik.

Kandidat resep dari tabel recipes (dataset utama) — dataset ini TIDAK punya
data gizi/kalori/skor kesehatan, jadi kriteria variasinya murni dari kategori
bahan utama (ayam/sapi/ikan/dst), BUKAN klaim "gizi seimbang"."""
import json
import math

from config import MODEL_NAME

PROMPT_TEMPLATE = """Kamu adalah Meal Plan Selector, bagian dari sistem AI perencana menu
masakan Indonesia mingguan.

ATURAN KETAT:
- Pilih HANYA dari daftar kandidat resep di bawah (JANGAN mengarang resep di luar daftar).
- Isi SEMUA slot yang diminta: {jumlah_hari} hari x jenis makan {meal_types}.
- Prioritas pemilihan (dalam urutan penting):
  1. BUDGET: category "sapi", "kambing", dan "udang" harganya jauh lebih mahal per
     porsi dibanding "ayam"/"ikan"/"tahu"/"tempe"/"telur" (bisa 2-4x lipat). Supaya
     total belanja mingguan gak bengkak gak masuk akal, GABUNGAN ketiga category
     mahal ini ("sapi"+"kambing"+"udang") MAKSIMAL muncul di ~1/4 dari total slot
     minggu ini (mis. buat 7 hari x 3 makan = 21 slot, maksimal ~5 slot dari
     ketiganya digabung) — SISANYA prioritaskan "ayam"/"ikan"/"tahu"/"tempe"/"telur"
     yang jauh lebih hemat buat menu sehari-hari. Kalau preferensi "hemat" true,
     perketat lagi jadi maksimal ~1/8 dari total slot (atau seminimal mungkin).
  2. Variasi kategori bahan utama (category) antar hari — usahakan JANGAN pakai
     category yang sama 2 hari berturut-turut kalau kandidatnya memungkinkan
     (biar gak bosen makan itu-itu terus, misal ayam terus-terusan) — TAPI aturan
     variasi ini TUNDUK ke aturan budget #1 di atas, jangan sampai demi variasi
     malah masukin sapi/kambing/udang berkali-kali dalam 1 minggu.
  3. EFISIENSI BAHAN: kalau ada beberapa kandidat yang cocok, PILIH yang
     ingredients-nya banyak overlap dengan bahan yang sudah dipunya user ATAU
     dengan resep lain yang sudah kamu pilih di hari lain — supaya belanja mingguan
     lebih hemat (bahan yang dibeli kepakai di beberapa resep sekaligus, bukan cuma 1x).
- Kalau preferensi "hemat" true, prioritaskan resep dengan total_ingredients lebih sedikit.

Bahan yang sudah dipunya user (pertimbangkan buat prioritas #3): {bahan_dipunya}
Preferensi user: {preferensi}

Kandidat resep (JSON, dari database asli — id dan title HARUS persis sama seperti ini):
{candidates_json}

Balas HANYA JSON dengan struktur:
{{
  "pilihan": [
    {{"hari": "Senin", "jenis_makan": "Sarapan", "recipe_id": 123, "alasan_singkat": "..."}},
    ...
  ]
}}
alasan_singkat maksimal 1 kalimat pendek bahasa Indonesia.
"""


def _trim(text, limit=250):
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "..."


# Category yang harganya jauh lebih mahal per porsi (2-4x lipat) dibanding
# ayam/ikan/tahu/tempe/telur — lihat services/price_estimator.py buat acuan
# harga per kg-nya.
EXPENSIVE_CATEGORIES = {"sapi", "kambing", "udang"}


def _cap_expensive_categories(cleaned: list[dict], candidates_by_id: dict, preferensi: dict) -> list[dict]:
    """Safety net KALAU LLM ngeyel gak nurutin aturan budget di prompt (bisa
    kejadian, terutama pas kuota gratisan lagi dipakein model yang kurang
    presisi) — batasin PAKSA jumlah slot kategori mahal (sapi/kambing/udang)
    SETELAH hasil balik dari Gemini, murni Python & deterministik. Ini yang
    bikin total belanja mingguan gak bisa kebablasan mahal cuma gara-gara LLM
    ngotot ngejar variasi kategori tanpa mikirin harga."""
    total_slots = len(cleaned)
    if total_slots == 0:
        return cleaned

    divisor = 8 if preferensi.get("hemat") else 4
    max_allowed = max(1, math.ceil(total_slots / divisor))

    cheap_candidates = [c for c in candidates_by_id.values() if c.get("category") not in EXPENSIVE_CATEGORIES]
    if not cheap_candidates:
        return cleaned  # gak ada kandidat murah buat gantiin, biarin apa adanya

    expensive_count = 0
    cheap_cursor = 0
    result = []
    for slot in cleaned:
        category = candidates_by_id.get(slot["recipe_id"], {}).get("category")
        if category in EXPENSIVE_CATEGORIES:
            expensive_count += 1
            if expensive_count > max_allowed:
                # Ganti slot ini ke kandidat murah (round-robin biar tetap bervariasi,
                # bukan cuma 1 resep hemat yang dipakai berulang-ulang).
                replacement = cheap_candidates[cheap_cursor % len(cheap_candidates)]
                cheap_cursor += 1
                slot = {
                    **slot,
                    "recipe_id": replacement["id"],
                    "title": replacement["title"],
                    "alasan_singkat": "Diganti otomatis ke bahan yang lebih hemat biar total belanja mingguan gak bengkak.",
                }
        result.append(slot)
    return result


def select_week(
    candidates: list[dict],
    days: list[str],
    meal_types: list[str],
    bahan_dipunya: list[str],
    preferensi: dict,
    client,
    max_retries: int = 2,
) -> list[dict]:
    if not candidates:
        return []

    candidates_json = json.dumps(
        [
            {
                "id": c["id"],
                "title": c["title"],
                "category": c.get("category"),
                "total_ingredients": c.get("total_ingredients"),
                "ingredients": _trim(c.get("ingredients")),
            }
            for c in candidates
        ],
        ensure_ascii=False,
    )

    prompt = PROMPT_TEMPLATE.format(
        jumlah_hari=len(days),
        meal_types=", ".join(meal_types),
        bahan_dipunya=", ".join(bahan_dipunya) if bahan_dipunya else "(tidak ada)",
        preferensi=json.dumps(preferensi, ensure_ascii=False),
        candidates_json=candidates_json,
    )

    valid_ids = {c["id"] for c in candidates}
    valid_titles_by_id = {c["id"]: c["title"] for c in candidates}
    candidates_by_id = {c["id"]: c for c in candidates}

    for _ in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            data = json.loads(resp.text)
            pilihan = data.get("pilihan", [])

            # Validasi keras: buang pilihan yang recipe_id-nya gak ada di kandidat asli
            # (jaga-jaga LLM halusinasi id). Ini yang bikin hasilnya bisa dipercaya.
            cleaned = []
            for p in pilihan:
                rid = p.get("recipe_id")
                if rid in valid_ids and p.get("hari") in days and p.get("jenis_makan") in meal_types:
                    cleaned.append({
                        "day_of_week": p["hari"],
                        "meal_type": p["jenis_makan"],
                        "recipe_id": rid,
                        "title": valid_titles_by_id[rid],
                        "alasan_singkat": p.get("alasan_singkat", ""),
                    })
            if cleaned:
                return _cap_expensive_categories(cleaned, candidates_by_id, preferensi)
        except Exception:
            continue

    return []