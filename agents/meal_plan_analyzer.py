"""Meal Plan Analyzer — baca pesan chat user di halaman Meal Planner AI.
Beda dari ingredient_analyzer.py biasa: fokusnya bukan nyari 1 resep, tapi
nangkep (1) bahan yang SUDAH dipunya user di rumah (buat dikurangi dari
shopping list mingguan), dan (2) override jumlah hari/orang kalau disebut
di kalimat (form tetap jadi default kalau user gak nyebut apa-apa)."""
import json

from config import MODEL_NAME

PROMPT = """Kamu adalah asisten yang membaca pesan user di fitur Meal Planner AI
(perencana menu masakan Indonesia untuk 1 minggu).

Tugasmu HANYA mengekstrak data terstruktur dari kalimat user, BUKAN membuat resep.

Kembalikan JSON dengan struktur:
{{
  "bahan_dipunya": ["daftar bahan yang user bilang SUDAH ada di rumah/kulkas, lowercase, tanpa jumlah/satuan"],
  "jumlah_hari_override": null atau angka (HANYA isi kalau user secara eksplisit sebut jumlah hari, mis. "buat 5 hari"),
  "jumlah_orang_override": null atau angka (HANYA isi kalau user secara eksplisit sebut jumlah orang/anggota keluarga),
  "preferensi": {{
    "hemat": true/false,
    "sehat": true/false
  }}
}}

Kalau user cuma bilang "aku punya telur sama kecap" tanpa nyebut hari/orang, jumlah_hari_override
dan jumlah_orang_override HARUS null (jangan menebak).

Pesan user: "{message}"
"""


def analyze(message: str, client, max_retries: int = 2) -> dict:
    prompt = PROMPT.format(message=message)
    for _ in range(max_retries):
        try:
            from google.genai import types
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            data = json.loads(resp.text)
            data.setdefault("bahan_dipunya", [])
            data.setdefault("jumlah_hari_override", None)
            data.setdefault("jumlah_orang_override", None)
            data.setdefault("preferensi", {"hemat": False, "sehat": False})
            return data
        except Exception:
            continue

    # Gemini gagal total — JANGAN menebak bahan dari regex kata mentah (lihat
    # perbaikan ingredient_analyzer.py sebelumnya, alasan sama persis: data
    # tebakan bikin shopping list jadi ngaco). Tandai fallback secara eksplisit.
    return {
        "bahan_dipunya": [],
        "jumlah_hari_override": None,
        "jumlah_orang_override": None,
        "preferensi": {"hemat": False, "sehat": False},
        "_fallback": True,
    }
