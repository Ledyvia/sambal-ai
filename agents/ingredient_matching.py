"""Ingredient Matching Agent (ROADMAP #2b, #7) — bandingin bahan yang user PUNYA
vs bahan yang DIBUTUHKAN resep pilihan. Murni set difference, tanpa LLM."""


def find_missing(user_bahan: list[str], recipe_ingredients_text: str) -> list[str]:
    if not user_bahan:
        return []
    recipe_text = str(recipe_ingredients_text).lower()
    missing = [b for b in user_bahan if b.lower() not in recipe_text]
    return missing
