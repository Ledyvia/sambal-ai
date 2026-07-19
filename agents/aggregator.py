"""Aggregator Agent (ROADMAP #4.6, #7) — gabungin hasil semua agent (Decision Maker,
Substitution, Video, Shopping, Scoring) jadi satu teks final. Bagian kualitatif
(analisis/rekomendasi) ditulis LLM; bagian kuantitatif (skor, link) ditempel
deterministik di Python — supaya nggak ada angka/link yang dikarang LLM."""

from agents.scoring import format_score_block


def build_final_reply(
    decision_text: str,
    scores: dict,
    missing_ingredients: list[str],
    substitutions: list[dict],
    shopping_suggestions: list[dict],
    tutorial_video: dict | None,
) -> str:
    parts = [decision_text]

    if tutorial_video:
        parts.append(
            "\n\n[Tutorial Video]\n"
            f"{tutorial_video['title']} — {tutorial_video['channel']}\n"
            f"{tutorial_video['url']}"
        )

    if missing_ingredients:
        block = "\n\n[Bahan yang Mungkin Kurang]\n"
        block += ", ".join(missing_ingredients)

        if substitutions:
            block += "\n\nSaran pengganti:\n"
            for s in substitutions:
                block += f"- {s.get('bahan_asli', '')} → {s.get('pengganti', '')} ({s.get('catatan', '')})\n"

        if shopping_suggestions:
            block += "\nCari bahan:\n"
            for s in shopping_suggestions:
                block += f"- {s['bahan']}: marketplace → {s['marketplace_url']} | toko terdekat → {s['maps_url']}\n"

        parts.append(block)

    parts.append(format_score_block(scores))

    return "".join(parts)