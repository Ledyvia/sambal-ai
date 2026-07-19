"""Unit Converter — normalisasi SEMUA satuan (siung, buah, sdm, butir, dst) jadi
gram, biar daftar belanja nunjukin SATU angka berat yang jelas per bahan
(mis. "250 g" atau "1.2 kg"), bukan campuran "3 siung + 2 buah + 1 sdm" yang
susah dibayangin beratnya pas belanja beneran.

INI SEMUA ESTIMASI, bukan takaran presisi — dataset resep nggak pernah nulis
berat asli tiap bahan, cuma satuan dapur biasa (siung, butir, dst). Makanya ada
2 lapis tabel konversi:
1. INGREDIENT_UNIT_OVERRIDES — kombinasi (kata kunci di nama bahan + satuan)
   yang punya estimasi lebih akurat, mis. "telur" + "butir" = 60g (rata-rata
   berat 1 butir telur ayam), beda sama "bawang putih" + "siung" = 5g.
2. UNIT_TO_GRAM — fallback generik per satuan kalau kombinasi bahan+satuannya
   nggak ada di override (dipakai buat bahan yang jarang/nggak dikenal).
"""


def keyword_in_name(keyword: str, name_lower: str) -> bool:
    """Cek apakah 'keyword' (sudah lowercase) ada di 'name_lower' (sudah
    lowercase juga). Dipisah jadi fungsi sendiri (bukan cuma 'in' langsung)
    biar konsisten dipakai di semua modul (unit_converter.py & price_estimator.py)
    dan gampang diupgrade ke pencocokan yang lebih pintar (mis. word-boundary)
    nanti kalau perlu, tanpa harus ubah tiap tempat yang makai."""
    return keyword in name_lower


# Fallback generik: rata-rata berat 1 satuan itu, TANPA memandang bahannya apa.
# Dipakai kalau kombinasi (bahan, satuan) nggak ada di INGREDIENT_UNIT_OVERRIDES.
UNIT_TO_GRAM: dict[str, float] = {
    "kg": 1000, "gram": 1, "gr": 1, "g": 1,
    "ml": 1, "liter": 1000, "ltr": 1000, "l": 1000,
    "sdm": 15, "sdt": 5,
    "buah": 100, "bh": 100,
    "butir": 55, "btr": 55,
    "siung": 5,
    "lembar": 2, "lbr": 2,
    "batang": 15, "btg": 15,
    "ekor": 250,
    "papan": 250,
    "ruas": 15,
    "bungkus": 200, "bks": 200,
    "potong": 70, "ptg": 70,
    "iris": 5,
    "genggam": 25,
    "ikat": 100,
    "biji": 8,   # mirip 'butir'/'buah' generik — biasanya nempel di bahan kecil (cabai, dst)
    "cup": 130,  # ukuran cup dapur ~240ml, digenapin buat bahan kering kayak tepung
    "ons": 100,  # 1 ons pasar tradisional Indonesia = 100 gram
    "jari": 10,  # keterangan panjang buat jahe/kunyit/lengkuas, mirip 'ruas'
    "cm": 5,     # satuan panjang informal (jahe/serai/kunyit "5 cm"), estimasi kasar per cm
    "btng": 15,  # singkatan 'batang' versi lain
    "lmbr": 2,   # singkatan 'lembar' versi lain
}

# (kata kunci yang dicari di nama bahan [lowercase], satuan) -> gram per 1 satuan.
# Dicek LEBIH DULU sebelum fallback ke UNIT_TO_GRAM, karena satuan "buah"/"butir"/
# dst beratnya beda jauh tergantung bahannya (1 buah tomat != 1 buah kelapa).
INGREDIENT_UNIT_OVERRIDES: list[tuple[str, str, float]] = [
    ("telur", "butir", 60), ("telur", "btr", 60), ("telur", "buah", 60),
    ("kelapa", "buah", 600), ("kelapa", "butir", 600),
    ("jeruk nipis", "buah", 30), ("jeruk limau", "buah", 15),
    ("tomat", "buah", 90),
    ("cabai", "buah", 8), ("cabe", "buah", 8),
    ("cabai", "biji", 8), ("cabe", "biji", 8),
    ("bawang merah", "siung", 8), ("bawang merah", "buah", 8),
    ("bawang putih", "siung", 5),
    ("bawang bombay", "buah", 150),
    ("kentang", "buah", 120),
    ("wortel", "buah", 80),
    ("mentimun", "buah", 100), ("timun", "buah", 100),
    ("terong", "buah", 100),
    ("jagung", "buah", 200),
    ("pisang", "buah", 100),
    ("tahu", "buah", 100), ("tahu", "potong", 100), ("tahu", "ptg", 100),
    ("tempe", "papan", 250), ("tempe", "potong", 40), ("tempe", "ptg", 40),
    ("ikan", "ekor", 300),
    ("ayam", "ekor", 900), ("ayam", "potong", 150), ("ayam", "ptg", 150),
    ("cumi", "ekor", 80),
    ("udang", "ekor", 15),
    ("daun jeruk", "lembar", 0.3), ("daun jeruk", "lbr", 0.3),
    ("daun salam", "lembar", 0.3), ("daun salam", "lbr", 0.3),
    ("daun pisang", "lembar", 20), ("daun pisang", "lbr", 20),
    ("serai", "batang", 15), ("serai", "btg", 15),
    ("kunyit", "ruas", 10), ("jahe", "ruas", 10), ("lengkuas", "ruas", 15),
    ("kemiri", "butir", 4), ("kemiri", "btr", 4),
    # Bumbu bubuk yang RINGAN (bukan padat kayak garam/gula) — 1 sdm/sdt-nya
    # jauh lebih ringan dari default generik (15g/5g), yang kalau dipakai
    # apa adanya bikin totalnya kehitung ratusan gram cuma dari beberapa
    # resep (mis. '1 sdm merica' x 6 resep jadi kayak butuh setengah kilo).
    ("merica", "sdm", 6), ("merica", "sdt", 2),
    ("lada", "sdm", 6), ("lada", "sdt", 2),
    ("ketumbar", "sdm", 6), ("ketumbar", "sdt", 2),
]


def convert_to_gram(name: str, qty: float, unit: str) -> float | None:
    """qty & unit dari 1 baris bahan (mis. qty=3, unit='siung'). Return total
    gram, atau None kalau satuannya nggak dikenal sama sekali (mis. 'secukupnya'
    yang emang nggak ada angkanya — itu ditangani terpisah, lihat
    estimate_secukupnya_gram di bawah)."""
    if qty is None or not unit:
        return None
    name_lower = name.lower()
    unit_lower = unit.lower()
    for keyword, u, gram_per_unit in INGREDIENT_UNIT_OVERRIDES:
        if keyword_in_name(keyword, name_lower) and u == unit_lower:
            return qty * gram_per_unit
    if unit_lower in UNIT_TO_GRAM:
        return qty * UNIT_TO_GRAM[unit_lower]
    return None


# Buat bahan yang ditulis "secukupnya"/"sesuai selera" (nggak ada angkanya sama
# sekali di resep) — dikasih estimasi kasar per PEMAKAIAN (per resep), supaya
# daftar belanja tetap kasih perkiraan berat, bukan cuma "jumlah gak jelas".
SECUKUPNYA_GRAM_PER_PAKAI: list[tuple[str, float]] = [
    ("minyak", 15), ("garam", 3), ("gula", 5), ("air", 100),
    ("penyedap", 3), ("kaldu", 5), ("merica", 2), ("lada", 2),
    ("kecap", 10), ("saus", 10), ("santan", 50), ("tepung", 15),
]
SECUKUPNYA_GRAM_DEFAULT = 10  # fallback generik buat bumbu/bahan lain yg gak ke-listed


def estimate_secukupnya_gram(name: str) -> float:
    name_lower = name.lower()
    for keyword, gram in SECUKUPNYA_GRAM_PER_PAKAI:
        if keyword_in_name(keyword, name_lower):
            return gram
    return SECUKUPNYA_GRAM_DEFAULT


def format_gram(total_gram: float) -> str:
    """250 -> '250 g', 1450 -> '1.45 kg'. Dibulatin ke angka yang masuk akal
    buat belanja (nggak perlu presisi desimal panjang)."""
    if total_gram >= 1000:
        kg = round(total_gram / 1000, 2)
        return f"{kg:g} kg"
    return f"{round(total_gram)} g"


# Bahan CAIR ditampilkan pakai ml/liter, bukan gram/kg — orang Indonesia lebih
# kebayang "minyak 1/2 liter" daripada "minyak 450 gram", walau secara berat
# angkanya kurang lebih sama (asumsi massa jenis ~1 g/ml, cukup akurat buat
# perkiraan belanja).
LIQUID_KEYWORDS = ("minyak", "santan", "kecap", "susu", "air", "saus", "cuka", "sirup", "kaldu cair")


def is_liquid(name: str) -> bool:
    name_lower = name.lower()
    return any(keyword_in_name(keyword, name_lower) for keyword in LIQUID_KEYWORDS)


def format_volume(total_ml: float) -> str:
    """350 -> '350 ml', 1200 -> '1.2 liter'."""
    if total_ml >= 1000:
        liter = round(total_ml / 1000, 2)
        return f"{liter:g} liter"
    return f"{round(total_ml)} ml"


def format_quantity(name: str, total_gram: float) -> str:
    """Router: pilih format ml/liter buat bahan cair, g/kg buat sisanya.
    total_gram diperlakukan setara ml (asumsi massa jenis ~1) kalau cair."""
    if is_liquid(name):
        return format_volume(total_gram)
    return format_gram(total_gram)


# ---------- Pembulatan ke ukuran kemasan yang BENERAN dijual di pasaran ----------
# Kenapa ini penting: hasil hitungan murni (mis. "175 ml kecap") itu SECARA
# MATEMATIS benar, tapi nggak ada produk kecap yang dijual persis 175ml di
# toko manapun — orang beli 1 botol ukuran TERDEKAT yang tersedia (mis. 220ml
# atau 135ml x2). Tabel di bawah ini nyimpen ukuran kemasan umum yang BENERAN
# ada di rak minimarket/warung Indonesia, supaya rekomendasi belanjanya bisa
# langsung dibeli, bukan angka teoritis yang nggak match produk manapun.
#
# Format: (kata kunci di nama bahan, [daftar ukuran kemasan yang tersedia, ml/gram])
PACKAGE_SIZES_ML: list[tuple[str, list[int]]] = [
    ("kecap manis", [135, 220, 275, 600, 620]),
    ("kecap asin", [135, 220, 600]),
    ("kecap", [135, 220, 600]),
    ("minyak goreng", [500, 900, 1000, 2000, 5000]),
    ("minyak", [500, 900, 1000, 2000]),
    ("santan", [65, 200, 400, 1000]),
    ("saus tiram", [135, 250, 480]),
    ("saus sambal", [140, 275, 340, 550]),
    ("saus tomat", [140, 275, 340]),
    ("saus", [135, 250, 340]),
    ("susu", [200, 250, 500, 1000]),
    ("cuka", [140, 620]),
    ("sirup", [460, 620]),
]
PACKAGE_SIZES_GRAM: list[tuple[str, list[int]]] = [
    ("garam", [250, 500, 1000]),
    ("gula merah", [250, 500]),
    ("gula pasir", [250, 500, 1000]),
    ("gula", [250, 500, 1000]),
    ("tepung terigu", [250, 500, 1000]),
    ("tepung beras", [250, 500, 1000]),
    ("tepung", [250, 500, 1000]),
    ("beras", [1000, 5000, 10000]),
    ("mentega", [200, 227]),
    ("margarin", [200, 250]),
    ("keju", [165, 170, 200]),
    ("kopi bubuk", [65, 165, 200]),
    ("terasi", [50, 100]),
    ("penyedap", [11, 50]),
    ("kaldu bubuk", [11, 50]),
    ("kaldu jamur", [11, 50]),
    ("kaldu", [11, 50]),
    # Bumbu bubuk/kering yang beneran dijual di warung/minimarket dalam SACHET
    # kecil (8-50g), BUKAN ditimbang bebas kayak sayur segar di pasar. Tanpa
    # ini, totalnya bisa kehitung ratusan gram (mis. "427 g merica") padahal
    # gak ada yang belanja merica bubuk sebanyak itu buat kebutuhan seminggu.
    ("merica", [8, 20, 45, 100]),
    ("lada", [8, 20, 45, 100]),
    ("ketumbar", [8, 20, 45]),
    ("jinten", [8, 20]),
    ("pala bubuk", [8, 20]),
    ("kunyit bubuk", [8, 20]),
    ("cabai bubuk", [8, 25, 50]),
    ("bawang putih bubuk", [8, 25, 50]),
    ("bawang merah bubuk", [8, 25, 50]),
    ("kayu manis bubuk", [8, 20]),
]


def _find_package_sizes(name: str, table: list[tuple[str, list[int]]]) -> list[int] | None:
    name_lower = name.lower()
    matches = [(kw, sizes) for kw, sizes in table if keyword_in_name(kw, name_lower)]
    if not matches:
        return None
    _, sizes = max(matches, key=lambda m: len(m[0]))  # kata kunci terpanjang menang
    return sizes


def round_to_market_package(name: str, total: float) -> tuple[str, float] | None:
    """Return (teks kayak '1 kemasan kecap manis 220 ml', jumlah_beli_actual)
    kalau bahan ini punya ukuran kemasan standar yang dikenal. jumlah_beli_actual
    dipakai buat estimasi HARGA — kita bayar buat 1 botol 220ml penuh, bukan
    cuma 175ml yang kepake, jadi harga harus ngikutin jumlah yang DIBELI.
    Return None kalau bahan ini bukan produk kemasan (mis. sayur/daging segar
    yang dijual per berat di pasar, bukan per kemasan tetap)."""
    sizes = _find_package_sizes(name, PACKAGE_SIZES_ML if is_liquid(name) else PACKAGE_SIZES_GRAM)
    if not sizes:
        return None
    unit_label = "ml" if is_liquid(name) else "g"
    sizes = sorted(sizes)
    for size in sizes:
        if total <= size:
            return f"1 kemasan {size} {unit_label} (kebutuhan ~{round(total)} {unit_label})", float(size)
    # Kebutuhan lebih besar dari kemasan terbesar yang ada -> beli beberapa kemasan terbesar
    largest = sizes[-1]
    count = -(-round(total) // largest)  # ceiling division
    return f"{count} kemasan {largest} {unit_label} (kebutuhan ~{round(total)} {unit_label})", float(count * largest)


def format_market_quantity(name: str, total_gram: float) -> tuple[str, float]:
    """Versi 'siap beli' dari format_quantity — kalau bahannya punya ukuran
    kemasan standar (lihat PACKAGE_SIZES_ML/GRAM), dibulatin ke situ (harga
    nanti dihitung dari jumlah yang DIBELI, bukan cuma yang KEPAKE). Kalau
    nggak (bahan segar: sayur/daging/bumbu basah yang dijual per berat di
    pasar, bukan per kemasan tetap), tetap pakai angka gram/ml/liter biasa
    dan jumlah beli = jumlah kebutuhan (pasar tradisional bisa jual longgar
    per berat, jadi nggak perlu dibulatin ke kemasan tetap).
    Return: (teks_ditampilkan, jumlah_dibeli_buat_hitung_harga)"""
    package_result = round_to_market_package(name, total_gram)
    if package_result:
        return package_result
    return format_quantity(name, total_gram), total_gram