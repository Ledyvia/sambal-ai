"""Agent 1 — Ingredient Analyzer. Baca kalimat user, ubah jadi data terstruktur.
Diperluas (ROADMAP #6.a): deteksi urgency & preferensi (hemat/cepat/sehat/porsi)."""
import json
import re

from config import STOPWORDS_ID, MODEL_NAME

ANALYZER_PROMPT = """Kamu adalah Ingredient Analyzer, bagian dari sistem multi-agent rekomendasi resep masakan Indonesia.
Tugasmu HANYA menganalisis input user, BUKAN menjawab pertanyaan resep.

Analisis input user berikut dan kembalikan JSON dengan struktur:
{
  "ringkasan": "ringkasan singkat kebutuhan/tujuan user dalam 1 kalimat bahasa Indonesia",
  "bahan": ["daftar bahan yang disebut user, lowercase, tanpa embel-embel jumlah/satuan"],
  "keywords": ["daftar kata kunci pencarian tambahan, misal nama masakan, kategori (ayam/sapi/ikan/tempe/tahu/udang/telur/kambing), rasa, atau teknik masak yang disebut/tersirat"],
  "intent": "salah satu dari: cari_berdasarkan_bahan | resep_spesifik | pertanyaan_umum",
  "urgency": "salah satu dari: sekarang | nanti (sekarang = mau masak hari ini/mendesak, nanti = rencana/stok ke depan; default sekarang kalau tidak jelas)",
  "preferensi": {
    "hemat": true/false,
    "cepat": true/false,
    "sehat": true/false,
    "porsi": null atau angka jumlah orang
  }
}

Input user: "{user_input}"
"""


def analyze(user_input: str, client, max_retries: int = 2) -> dict:
    prompt = ANALYZER_PROMPT.replace("{user_input}", user_input)
    last_err = None
    for _ in range(max_retries):
        try:
            from google.genai import types
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            data = json.loads(resp.text)
            data.setdefault("bahan", [])
            data.setdefault("keywords", [])
            data.setdefault("ringkasan", user_input)
            data.setdefault("intent", "cari_berdasarkan_bahan")
            data.setdefault("urgency", "sekarang")
            data.setdefault("preferensi", {"hemat": False, "cepat": False, "sehat": False, "porsi": None})
            return data
        except Exception as e:
            last_err = e
            continue

    # Gemini gagal total setelah retry (mis. kuota habis/429). JANGAN nebak "bahan"
    # dari regex kata mentah — itu bikin missing_ingredients & link Maps jadi ngaco
    # (bisa nyasar ke kata yang bukan bahan sama sekali). Tandai fallback secara
    # eksplisit dan biarkan orchestrator berhenti dengan pesan yang jujur ke user.
    return {
        "ringkasan": user_input,
        "bahan": [],
        "keywords": [],
        "intent": "pertanyaan_umum",
        "urgency": "sekarang",
        "preferensi": {"hemat": False, "cepat": False, "sehat": False, "porsi": None},
        "_fallback": True,
        "_error": str(last_err) if last_err else None,
    }
