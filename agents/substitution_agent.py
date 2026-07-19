"""Substitution Agent (ROADMAP #2b) — saranin bahan pengganti buat yang kurang."""
import json

from config import MODEL_NAME

PROMPT = """Kamu adalah ahli substitusi bahan masakan Indonesia.
Untuk tiap bahan di bawah ini, berikan alternatif yang umum ditemukan di dapur
Indonesia, beserta catatan singkat (rasio takaran kalau beda).
Balas HANYA JSON: {{"substitutions": [{{"bahan_asli": "...", "pengganti": "...", "catatan": "..."}}]}}
Kalau memang tidak ada pengganti yang masuk akal untuk suatu bahan, boleh dilewati (tidak usah dipaksakan).

Bahan yang tidak tersedia: {missing_ingredients}
Konteks resep: {recipe_title}
"""


def suggest(missing_ingredients: list[str], recipe_title: str, client, max_retries: int = 2) -> list[dict]:
    if not missing_ingredients:
        return []

    prompt = PROMPT.format(
        missing_ingredients=", ".join(missing_ingredients),
        recipe_title=recipe_title,
    )
    for _ in range(max_retries):
        try:
            from google.genai import types
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            data = json.loads(resp.text)
            return data.get("substitutions", [])
        except Exception:
            continue
    return []
