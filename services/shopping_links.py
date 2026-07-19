"""Generate link belanja bahan — urgency-aware (lihat ROADMAP_ADVANCED.md #4).

Update: link Google Maps sekarang bisa berbasis LOKASI ASLI user (dari GPS
browser, lihat static/js/chat.js & static/js/meal-planner-ai.js) — bukan cuma
pencarian generik "beli X terdekat" tanpa titik acuan. Kalau lat/lng nggak ada
(user nolak izin lokasi / browser nggak support), fallback ke pencarian generik
dengan "Yogyakarta" sebagai region default (karena project ini emang buat
mahasiswa di Jogja)."""
import re
from urllib.parse import quote

from config import INSTANT_GROCERY_APPS

PRODUCT_NAME_MAP = {
    "ayam": "ayam segar",
    "telur": "telur ayam",
    "santan": "santan kara",
    "minyak": "minyak goreng",
}

DEFAULT_REGION = "Yogyakarta"


def to_product_query(ingredient: str) -> str:
    return PRODUCT_NAME_MAP.get(ingredient.lower(), ingredient)


def extract_shopping_list(ingredients_text: str) -> list[str]:
    """Parse teks bahan (format: '1 kg ayam--2 buah tomat--...') jadi list bersih."""
    raw_items = re.split(r"--|\n", ingredients_text)
    cleaned = []
    for item in raw_items:
        item = item.strip()
        item = re.sub(
            r"^[\d/.,]+\s*(kg|gram|gr|ml|liter|l|sdm|sdt|buah|butir|siung|lembar|batang)?\s*",
            "", item, flags=re.IGNORECASE,
        )
        if item:
            cleaned.append(item)
    return cleaned


def generate_superindo_link(ingredient_name: str) -> str:
    # Dulu ini nge-link ke halaman toko spesifik "superindo-indonesia-raya" di
    # Tokopedia — tapi toko itu nggak beneran ada (slug-nya ditebak, bukan
    # diverifikasi), jadi selalu 404 apapun yang dicari. Ganti ke pencarian
    # SELURUH Tokopedia yang pasti selalu ada hasilnya buat bahan masakan umum.
    query = quote(to_product_query(ingredient_name))
    return f"https://www.tokopedia.com/search?st=product&q={query}"


def generate_maps_link(ingredient_name: str, lat: float | None = None, lng: float | None = None) -> str:
    """PENTING: query-nya SENGAJA nggak nyebut nama bahan (mis. 'merica' atau
    'saori saos tiram'). Google Maps itu nyari TEMPAT/BISNIS berdasarkan nama,
    bukan nyari produk di dalam toko — jadi kalau query-nya 'beli merica
    terdekat', Maps entah nggak nemu apa-apa (nama bahan terlalu spesifik buat
    dicocokkan ke nama tempat), atau malah nyasar ke tempat yang namanya
    kebetulan mirip (mis. 'saos tiram' nyangkut ke warung seafood). Jadi
    query-nya selalu 'supermarket & toko sembako terdekat' — itu KATEGORI
    tempat yang beneran dikenali Maps, hasilnya konsisten toko kelontong/
    minimarket/supermarket asli, nama bahan spesifiknya ditaruh di teks
    'catatan' aja (lihat build_shopping_suggestion), bukan di URL Maps.

    Kalau ada lat/lng (dari GPS browser user), Maps bakal nyari 'terdekat'
    beneran dari titik itu. Kalau nggak ada, fallback ke pencarian generik yang
    di-scope ke Yogyakarta (region utama pengguna project ini)."""
    if lat is not None and lng is not None:
        query = quote("supermarket & toko sembako terdekat")
        # Format "@lat,lng,zoom" di path Maps bikin hasil pencarian dipusatkan
        # di titik itu, jadi "terdekat" dihitung dari lokasi user asli.
        return f"https://www.google.com/maps/search/{query}/@{lat},{lng},15z"

    query = quote(f"supermarket & toko sembako terdekat {DEFAULT_REGION}")
    return f"https://www.google.com/maps/search/{query}"


def build_shopping_suggestion(
    ingredient_name: str,
    urgency: str = "sekarang",
    lat: float | None = None,
    lng: float | None = None,
) -> dict:
    """urgency: 'sekarang' (butuh masak hari ini) atau 'nanti' (restock biasa)."""
    marketplace_url = generate_superindo_link(ingredient_name)
    maps_url = generate_maps_link(ingredient_name, lat, lng)
    location_note = "" if lat is not None else " (izin lokasi belum aktif, hasil di-scope ke Yogyakarta)"

    if urgency == "sekarang":
        return {
            "bahan": ingredient_name,
            "prioritas": "toko_fisik",
            "marketplace_url": marketplace_url,
            "maps_url": maps_url,
            "catatan": (
                f"Cek toko/minimarket terdekat dulu buat '{ingredient_name}'{location_note}. "
                f"Kalau areamu dijangkau, aplikasi grocery instan "
                f"({', '.join(INSTANT_GROCERY_APPS)}) juga bisa jadi opsi (antar 15-45 menit)."
            ),
        }
    return {
        "bahan": ingredient_name,
        "prioritas": "marketplace",
        "marketplace_url": marketplace_url,
        "maps_url": maps_url,
        "catatan": "Buat stok bahan ke depan, bisa cek harga & promo di marketplace.",
    }


def build_shopping_list_with_links(
    missing_ingredients: list[str],
    urgency: str = "sekarang",
    lat: float | None = None,
    lng: float | None = None,
) -> list[dict]:
    return [build_shopping_suggestion(item, urgency, lat, lng) for item in missing_ingredients]