"""Price Estimator — kasih ESTIMASI kasar biaya belanja mingguan.

PENTING, ini harus jujur dari awal: harga di sini BUKAN data real-time dari
toko/marketplace manapun (nggak ada API harga yang dipanggil). Ini tabel
referensi statis, disusun dari kisaran harga umum bahan pokok & bumbu dapur
di pasar tradisional/supermarket Indonesia. Tujuannya cuma kasih GAMBARAN
KASAR "kira-kira segini lho budget belanja minggu ini", BUKAN angka final
yang bisa dipegang persis — harga asli beda-beda tergantung kota, musim,
promo, dan toko yang dipilih.

Karena itu, setiap kali angka ini ditampilkan ke user (chat reply, kartu
belanja, PDF), HARUS selalu disertai PRICE_DISCLAIMER supaya jelas ini
estimasi, bukan harga pasti.
"""
from agents.unit_converter import keyword_in_name

PRICE_DISCLAIMER = (
    "Estimasi harga di bawah ini dihitung dari tabel referensi harga umum bahan "
    "dapur Indonesia (BUKAN data real-time dari toko/marketplace manapun), "
    "disesuaikan pakai pengali kasar per wilayah (Jawa / Luar Jawa) — bukan "
    "harga per kota yang presisi. Harga asli tetap bisa beda tergantung kota, "
    "musim, dan toko. Anggap ini gambaran kasar buat nyiapin budget, bukan "
    "angka pasti."
)

# Pengali KASAR per wilayah — MANUAL/STATIS, bukan hasil lookup lokasi otomatis
# atau data live dari toko manapun. Alasan cuma 2 kategori (bukan per kota):
# Tokopedia/marketplace sendiri nggak punya "harga per kota" yang bersih (harga
# ditentukan per PENJUAL, beda kota cuma beda ongkir) — jadi cari harga presisi
# per kota itu nggak benar-benar ada datanya buat dijadikan acuan. Angka di
# bawah cuma menangkap pola umum: harga bahan pokok & bumbu dapur di luar Jawa
# cenderung lebih tinggi karena biaya distribusi/logistik lebih jauh.
REGIONAL_MULTIPLIER: dict[str, float] = {
    "jawa": 1.0,
    "luar_jawa": 1.2,
}
DEFAULT_WILAYAH = "jawa"

# Rp per 1 kg (atau per 1 liter buat cairan, diperlakukan setara 1kg buat
# kesederhanaan hitung). Disusun dari kisaran harga umum pasar tradisional/
# supermarket Indonesia — angka BULAT & KASAR secara sengaja, bukan pura-pura
# presisi padahal sebenarnya cuma tebakan.
HARGA_PER_KG: list[tuple[str, int]] = [
    ("daging sapi", 130000), ("daging kambing", 140000), ("kambing", 140000),
    ("ayam", 38000), ("bebek", 55000),
    ("udang", 75000), ("cumi", 60000), ("ikan", 35000), ("kepiting", 90000),
    ("telur", 28000),
    ("bawang merah", 40000), ("bawang putih", 35000), ("bawang bombay", 25000),
    ("cabai rawit", 65000), ("cabai merah", 45000), ("cabai hijau", 40000), ("cabai", 45000),
    ("tomat", 12000), ("kentang", 15000), ("wortel", 12000),
    ("kol", 8000), ("kubis", 8000), ("sawi", 10000), ("bayam", 10000), ("kangkung", 8000),
    ("buncis", 14000), ("terong", 10000), ("mentimun", 8000), ("timun", 8000),
    ("jagung", 8000), ("tempe", 12000), ("tahu", 10000),
    ("santan", 20000), ("kelapa", 13000),
    ("minyak goreng", 18000), ("minyak", 18000),
    ("gula merah", 22000), ("gula", 16000), ("garam", 8000),
    ("kecap manis", 20000), ("kecap asin", 20000), ("kecap", 20000),
    ("saus tiram", 35000), ("saus", 25000), ("terasi", 45000),
    ("merica", 90000), ("lada", 90000), ("ketumbar", 40000),
    ("kunyit", 20000), ("jahe", 25000), ("lengkuas", 15000), ("serai", 15000),
    ("daun jeruk", 30000), ("daun salam", 20000), ("daun pisang", 8000),
    ("kemiri", 45000), ("jeruk nipis", 20000),
    ("tepung terigu", 12000), ("tepung beras", 14000), ("tepung", 13000),
    ("mie", 15000), ("susu", 20000), ("keju", 90000), ("mentega", 30000), ("margarin", 28000),
    ("daun bawang", 15000), ("seledri", 15000),
]

# Kalau nama bahan sama sekali gak cocok kata kunci manapun di atas — tetap
# dikasih angka (bukan disembunyikan), tapi pakai harga generik yang ditandai
# jelas sebagai tebakan kasar di UI (lihat "harga_kasar" flag pada tiap item).
HARGA_PER_KG_DEFAULT = 25000


def estimate_price(name: str, total_gram: float, wilayah: str = DEFAULT_WILAYAH) -> tuple[int, bool]:
    """Return (estimasi_rupiah, is_default_fallback). is_default_fallback=True
    kalau bahan gak ketemu di tabel referensi (pakai harga generik) — dipakai
    caller buat kasih tanda "~" tambahan di UI biar user tau ini extra kasar.
    wilayah: "jawa" (default, pengali 1.0) atau "luar_jawa" (pengali 1.2) —
    lihat REGIONAL_MULTIPLIER di atas soal kenapa cuma 2 kategori kasar."""
    if total_gram is None or total_gram <= 0:
        return 0, True
    multiplier = REGIONAL_MULTIPLIER.get(wilayah, 1.0)
    name_lower = name.lower()
    # Cocokkan kata kunci TERPANJANG dulu, biar "bawang merah" gak ketiban
    # aturan generik "bawang" (yang kebetulan gak ada di tabel ini, tapi jaga2
    # kalau nanti ditambah).
    matches = [(kw, harga) for kw, harga in HARGA_PER_KG if keyword_in_name(kw, name_lower)]
    if matches:
        _, harga_per_kg = max(matches, key=lambda m: len(m[0]))
        rupiah = (total_gram / 1000) * harga_per_kg * multiplier
        return _round_rupiah(rupiah), False
    rupiah = (total_gram / 1000) * HARGA_PER_KG_DEFAULT * multiplier
    return _round_rupiah(rupiah), True


def _round_rupiah(value: float) -> int:
    """Dibulatin ke kelipatan 500 terdekat — angka belanja beneran emang
    jarang presisi sampai satuan Rupiah."""
    return max(500, round(value / 500) * 500)