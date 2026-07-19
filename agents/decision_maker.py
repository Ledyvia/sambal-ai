"""Agent 3 — Decision Maker. Pilih 2-3 resep terbaik dari kandidat, susun jawaban.
Diperluas (ROADMAP #5): bisa menerima konteks nutrisi opsional dari Nutrition Agent."""
import json

import pandas as pd

from config import MODEL_NAME

DECISION_PROMPT_TEMPLATE = """Kamu adalah Decision Maker, bagian dari sistem multi-agent rekomendasi resep masakan Indonesia.

ATURAN KETAT:
- Semua jawaban HARUS berdasarkan data kandidat resep di bawah ini. JANGAN mengarang bahan/langkah di luar data.
- Pilih maksimal 2-3 resep TERBAIK dari kandidat yang paling sesuai dengan permintaan user.
- Gunakan PERSIS format output berikut (bahasa Indonesia):

[Analisis]
(tulis ringkas hasil analisis kebutuhan user)

[Rekomendasi] Nama Masakan:
- (nama resep 1)
- (nama resep 2)
- (nama resep 3, jika ada)

[Detail Resep]
Nama Masakan: (nama resep)
Bahan:
- (daftar bahan, satu per baris, ambil dari data asli kandidat)
Langkah:
1. (langkah pertama)
2. (langkah kedua)
3. dst

(ulangi blok [Detail Resep] di atas untuk tiap resep yang direkomendasikan)

[Penjelasan]
- (alasan kenapa resep-resep ini dipilih, dan kesesuaiannya dengan permintaan user)

Permintaan user: "{user_input}"

Hasil analisis kebutuhan user: {analysis}
{nutrition_note}
Kandidat resep (JSON, dari database asli):
{candidates_json}
"""


def _trim(text, limit=600):
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."


def decide(user_input: str, analysis: dict, candidates: pd.DataFrame, client,
           nutrition_context: dict | None = None, max_retries: int = 2) -> str:
    if candidates.empty:
        return "Maaf, data tidak ditemukan dalam database."

    records = [
        {
            "Title": row["title"],
            "Ingredients": _trim(row["ingredients"]),
            "Steps": _trim(row["steps"], limit=1000),
            "Category": row["category"],
            "URL": row["url"],
        }
        for _, row in candidates.iterrows()
    ]

    nutrition_note = f"\nKonteks nutrisi tambahan (opsional, referensi umum): {nutrition_context['catatan']}\n" if nutrition_context else ""

    prompt = DECISION_PROMPT_TEMPLATE.format(
        user_input=user_input,
        analysis=json.dumps(analysis, ensure_ascii=False),
        nutrition_note=nutrition_note,
        candidates_json=json.dumps(records, ensure_ascii=False, indent=2),
    )

    last_err = None
    for _ in range(max_retries):
        try:
            resp = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            return resp.text.strip()
        except Exception as e:
            last_err = e
            continue
    # Jangan bocorkan raw exception (bisa berisi detail teknis/internal) ke chat
    # user. Log detailnya di server, tapi balas dengan pesan yang jelas & manusiawi.
    print(f"[decision_maker] Gemini gagal setelah {max_retries}x retry: {last_err}")
    return (
        "Maaf, sistem AI lagi sibuk atau kuota API harian sudah tercapai, jadi "
        "belum bisa menyusun rekomendasi resep saat ini. Coba lagi dalam beberapa "
        "menit ya."
    )
