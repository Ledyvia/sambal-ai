"""Recipe Scoring System (ROADMAP #6.b, #6.c) — dihitung deterministik di Python,
BUKAN diminta LLM mengarang angka. Ini yang bikin Explainable AI-nya bisa
dipercaya: angkanya selalu bisa ditelusuri balik ke data asli."""


def calculate(primary_recipe: dict, analysis: dict, nutrition_context: dict | None, budget_weight: dict) -> dict:
    scores = {}

    # 1. Kecocokan bahan (0-40) — dari _score Agent 2, dinormalisasi kasar
    raw_score = float(primary_recipe.get("_score", 0))
    scores["kecocokan_bahan"] = round(min(raw_score * 8, 40), 1)

    # 2. Nutrisi (0-30)
    if analysis.get("preferensi", {}).get("sehat"):
        scores["nutrisi"] = 25 if nutrition_context else 15
    else:
        scores["nutrisi"] = 20  # netral, tidak relevan buat user ini

    # 3. Budget/simplicity (0-30) — makin sedikit bahan, makin tinggi (proxy kesederhanaan)
    total_bahan = max(int(primary_recipe.get("total_ingredients", 10) or 10), 1)
    base_budget = max(30 - total_bahan, 5)
    if budget_weight.get("budget_mode"):
        base_budget = min(base_budget + 10, 30)
    scores["budget"] = round(base_budget, 1)

    scores["total"] = round(sum(v for k, v in scores.items() if k != "total"), 1)
    return scores


def format_score_block(scores: dict) -> str:
    return (
        "\n\n[Skor Kecocokan]\n"
        f"- Kecocokan bahan: {scores['kecocokan_bahan']}/40\n"
        f"- Nutrisi: {scores['nutrisi']}/30\n"
        f"- Budget/simplicity: {scores['budget']}/30\n"
        f"- Total: {scores['total']}/100"
    )
