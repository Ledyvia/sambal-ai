"""Agent 2 — Recipe Finder. Cari kandidat resep dari cache pandas (tanpa LLM).
Diperluas (ROADMAP #2a, #6.a, #6.e): synonym expansion, boost sesuai preferensi
(hemat/cepat) dan preferensi historis user (favorit sebelumnya)."""
import json as json_lib

import pandas as pd

from config import SYNONYM_MAP


def expand_terms(terms: list[str]) -> list[str]:
    expanded = set(terms)
    for t in terms:
        for canonical, variants in SYNONYM_MAP.items():
            if t == canonical or t in variants:
                expanded.update(variants + [canonical])
    return list(expanded)


def find(df: pd.DataFrame, analysis: dict, top_n: int = 8, user_prefs: dict | None = None) -> pd.DataFrame:
    terms = [t.strip().lower() for t in (analysis.get("bahan", []) + analysis.get("keywords", [])) if t and t.strip()]
    terms = list(dict.fromkeys(terms))
    terms = expand_terms(terms)
    if not terms:
        return df.iloc[0:0]

    haystack = (
        df["title_cleaned"].astype(str) + " " +
        df["ingredients_cleaned"].astype(str) + " " +
        df["category"].astype(str)
    ).str.lower()

    scores = haystack.map(lambda text: sum(1 for t in terms if t in text))
    candidates = df.assign(_score=scores)
    candidates = candidates[candidates["_score"] > 0].copy()

    preferensi = analysis.get("preferensi", {}) or {}

    # Boost "hemat" -> resep dengan bahan lebih sedikit diutamakan
    if preferensi.get("hemat"):
        max_ing = candidates["total_ingredients"].replace(0, 1).max() or 1
        candidates["_score"] += (1 - candidates["total_ingredients"] / max_ing) * 2

    # Boost "cepat" -> resep dengan langkah lebih sedikit diutamakan
    if preferensi.get("cepat"):
        max_steps = candidates["total_steps"].replace(0, 1).max() or 1
        candidates["_score"] += (1 - candidates["total_steps"] / max_steps) * 2

    # Boost berdasarkan kategori yang pernah difavoritkan user (user preference memory, #6.e)
    if user_prefs and user_prefs.get("suka_kategori"):
        try:
            suka = json_lib.loads(user_prefs["suka_kategori"]) if isinstance(user_prefs["suka_kategori"], str) else user_prefs["suka_kategori"]
            candidates["_score"] += candidates["category"].map(lambda c: suka.get(c, 0) * 0.5)
        except Exception:
            pass

    candidates = candidates.sort_values(["_score", "loves"], ascending=[False, False])
    return candidates.head(top_n)
