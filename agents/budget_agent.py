"""Budget Agent (ROADMAP #7) — sinyal ringan buat scoring, murni dari preferensi
user (tidak butuh LLM, tidak butuh data harga real yang memang tidak tersedia)."""


def get_weight(analysis: dict) -> dict:
    preferensi = analysis.get("preferensi", {}) or {}
    return {
        "budget_mode": bool(preferensi.get("hemat")),
        "catatan": (
            "Mode hemat aktif — resep dengan bahan lebih sedikit diprioritaskan."
            if preferensi.get("hemat")
            else "Mode standar — tidak ada prioritas khusus soal budget."
        ),
    }
