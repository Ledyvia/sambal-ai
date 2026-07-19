"""Shopping Agent (ROADMAP #4) — urgency-aware, cuma proses bahan yang KURANG.
Update: terima lat/lng (GPS browser user, opsional) biar link Maps 'toko
terdekat' beneran dihitung dari lokasi asli, bukan pencarian generik."""
from services.shopping_links import build_shopping_list_with_links


def suggest(
    missing_ingredients: list[str],
    urgency: str = "sekarang",
    lat: float | None = None,
    lng: float | None = None,
) -> list[dict]:
    if not missing_ingredients:
        return []
    return build_shopping_list_with_links(missing_ingredients, urgency, lat, lng)