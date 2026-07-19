"""Weekly Shopping Agent — gabungin bahan dari semua resep terpilih seminggu.
JUMLAHNYA (kg/gram/butir/dst) diparse dari teks ingredients asli tiap resep,
dijumlahin per bahan, diskalain sesuai jumlah orang — ini SEMUA murni Python,
angka gak pernah dikarang LLM.

Nama bahan yang berantakan/duplikat (dataset penuh singkatan & instruksi masak
nempel, mis. 'bw putih, geprek cincang') dibersihin & digabung pakai
shopping_cleaner.py (1x panggilan Gemini buat SEMUA nama sekaligus) — supaya
daftar belanja beneran minimal, gak keliatan banyak item padahal bahan yang
sama. Kalau Gemini gagal/gak dikasih, fallback ke nama mentah apa adanya
(tetap tampil, cuma kurang rapi — TIDAK hilang)."""
import re
from collections import defaultdict

from services.shopping_links import build_shopping_suggestion
from services.price_estimator import estimate_price, PRICE_DISCLAIMER, DEFAULT_WILAYAH
from agents.shopping_cleaner import clean_and_group
from agents.unit_converter import convert_to_gram, estimate_secukupnya_gram, format_market_quantity
from config import DEFAULT_PORSI_PER_RESEP

# Unit lengkap + singkatan umum yang dipakai di dataset (bh=buah, lbr=lembar, dst)
UNIT_LIST = (
    "kg|gram|gr|g|ml|liter|ltr|l|sdm|sdt|buah|bh|butir|btr|siung|lembar|lbr|lmbr|"
    "batang|btg|btng|ekor|papan|ruas|bungkus|bks|potong|ptg|iris|genggam|ikat|"
    "biji|cup|ons|jari|cm"
)
QTY_UNIT_RE = re.compile(rf"^([\d/.,\-–]+)\s*({UNIT_LIST})?\s+(.+)$", re.IGNORECASE)
NON_QTY_MARKERS = ("secukupnya", "secukup nya", "sesuai selera", "seperlunya", "sejumput")

# Frasa yang KADANG nyelip di antara baris-baris bahan di dataset tapi
# sebenernya instruksi masak ATAU label section (mis. "bumbu halus", "bahan
# isian"), bukan nama bahan sama sekali. _is_section_header cuma nangkep baris
# bersimbol/berakhiran ':', jadi kalimat/label kayak gini perlu denylist
# eksplisit biar gak ke-itung sebagai "bahan belanja" seharga Rp500.
NON_INGREDIENT_PHRASES = {
    "campur jd satu", "campur jadi satu", "campur rata", "aduk rata",
    "aduk hingga rata", "aduk sampai rata",
    "bumbu halus", "bumbu yang dihaluskan", "bumbu yg dihaluskan",
    "bahan isian", "bahan pelengkap", "bahan tambahan", "pelengkap",
}

# Kata/frasa CARA OLAH yang sering nempel di belakang nama bahan dataset,
# dipisah koma (mis. "bawang merah, iris-iris" / "cabai, cincang halus").
# Dipakai buat DETERMINISTIC dedup (murni Python, regex — SELALU jalan,
# nggak bergantung Gemini nyala/nggak) sebelum grouping key dihitung. Ini
# yang bikin "bawang merah" dan "bawang merah iris-iris" ketangkep sebagai
# bahan yang SAMA walau client=None / API key belum diisi.
PREP_INSTRUCTION_RE = re.compile(
    r"[,./]?\s*("
    r"iris.*|cincang.*|geprek.*|memarkan.*|haluskan.*|hancurkan.*|"
    r"potong.*|serut.*|parut.*|belah.*|rajang.*|digoreng.*|"
    r"tumbuk.*|ulek.*|sangrai.*|cuci\s*bersih|sisihkan|buang\s*biji|buang\s*kulit|"
    r"kocok.*|"
    r"untuk\s*taburan|utk\s*taburan|untuk\s*olesan|opsional|"
    # 'udang ukuran besar/sedang/jumbo' atau 'pindang tongkol uk. sedang' ->
    # cuma keterangan UKURAN, bukan jenis bahan yang beda — dulu ini bikin
    # 'udang' & 'udang ukuran' keitung 2 bahan terpisah, shrimp-nya kebeli
    # dobel di daftar belanja.
    r"ukuran\s*(besar|sedang|kecil|jumbo|super)?|\buk\.?\s*(besar|sedang|kecil|jumbo|super)?|"
    # keterangan ukuran/kondisi lepas yang nempel di belakang (bukan bagian
    # nama bahan): 'cabai merah besar', 'cabai kecil', 'wortel import',
    # 'jengkol tua' — semua ini tetap bahan yang SAMA cuma beda deskripsi.
    r"besar|kecil|sedang|jumbo|import|tua|muda|"
    # sisa instruksi yang KEPOTONG di tengah kata pas scraping dataset (mis.
    # 'bawang putih yang sudah di' — harusnya '...dihaluskan' tapi kepotong).
    # 'di' bare di posisi akhir HAMPIR SELALU sisa kata kerja yang kepotong,
    # bukan bagian nama bahan.
    r"yang\s*sudah\s*di|di|"
    r"secukupnya|sesuai\s*selera|seperlunya"
    r")\s*$",
    re.IGNORECASE,
)


# Bahan yang punya beberapa VARIAN kata di tengah/belakang nama tapi tetap
# bahan yang SAMA (bukan cuma di akhir string kayak PREP_INSTRUCTION_RE di
# atas) — mis. 'tahu putih bandung' / 'tahu petak' / 'tahu putih' semuanya
# tetap tahu biasa buat keperluan belanja.
COLLAPSE_VARIANT_RE = re.compile(
    r"\btahu\s+(putih|petak|bandung|kuning|coklat)(\s+(putih|petak|bandung|kuning|coklat))*\b",
    re.IGNORECASE,
)

# Kata unit/keterangan yang NYASAR jadi awalan nama bahan — biasanya karena
# angka/kuantitasnya kepisah/ilang pas scraping dataset (mis. raw text aslinya
# '2 cm jahe' tapi yang ke-parse cuma 'cm jahe' doang, jadi 'cm' dikira nama).
LEADING_STRAY_UNIT_RE = re.compile(
    r"^(cm|jari|ruas|ons|ptg|potong|buah|lembar|lbr|lmbr|biji|siung|batang|btg|btng|bonggol)\s+",
    re.IGNORECASE,
)


def _split_joined_alternatives(name: str) -> str:
    """Dataset kadang nggabungin 2 penyebutan jadi 1 baris pakai '&'/'/'/'*'
    (mis. 'garam&kaldu jamur', 'kecap asin jepang/kikkoman/shoyu', 'tahu putih
    bandung *hancurkan'). Kita gak punya cara aman buat misahin JUMLAH per
    bagian, jadi diambil bagian PERTAMA aja sebagai nama representatif —
    lebih baik daripada nampilin 1 baris belanja dengan nama gabungan yang
    aneh/gak bisa di-'Cari' ke marketplace."""
    name = name.split("*")[0].strip()
    name = name.split("&")[0].strip()
    if "/" in name:
        first = name.split("/")[0].strip()
        # Cuma dianggap 'daftar alternatif nama bahan' kalau bagian pertamanya
        # beneran teks (bukan sisa notasi angka kayak '-/+ 110gr').
        if len(first) >= 2 and not re.match(r"^[\d/eE.,\-–+\s]+$", first):
            name = first
    return name


def _strip_prep_instructions(name: str) -> str:
    """'bawang merah, iris-iris' -> 'bawang merah'. Dijalankan berulang kali
    karena kadang ada lebih dari 1 instruksi nempel (mis. ', cincang, untuk
    taburan')."""
    cleaned = re.sub(r"\([^)]*\)", "", name)  # buang catatan dalam kurung
    cleaned = _split_joined_alternatives(cleaned)
    # 'minyak goreng untuk menumis dan menggoreng' -> 'minyak goreng' — apapun
    # setelah 'untuk'/'utk' hampir selalu keterangan tujuan, bukan nama bahan.
    cleaned = re.split(r"\b(?:untuk|utk)\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = PREP_INSTRUCTION_RE.sub("", cleaned).strip()
        cleaned = LEADING_STRAY_UNIT_RE.sub("", cleaned).strip()
    # Bagian sebelum koma PERTAMA yang tersisa dianggap nama inti bahan —
    # sisa apapun setelah koma di dataset ini nyaris selalu instruksi masak,
    # bukan bagian dari nama bahannya.
    core = cleaned.split(",")[0].strip()
    core = core if core else cleaned.strip()
    core = COLLAPSE_VARIANT_RE.sub("tahu", core).strip()
    # Bersihin sisa simbol/emoji nyempil di ujung (mis. label section 'bumbu
    # halus👇' dari dataset) — biar bisa ke-cocokin ke NON_INGREDIENT_PHRASES.
    core = re.sub(r"[^\w\s]+$", "", core).strip()
    return core if core else name.strip()


# Varian ejaan bahan yang SAMA tapi ditulis beda-beda di dataset (bukan
# masalah instruksi masak lagi, ini masalah ejaan) — kalau nggak dinormalisasi
# di sini, "bawang bombay" dan "bawang bombai" dianggap 2 bahan beda padahal
# sama. Ini jalan MURNI PYTHON (dict lookup), gak bergantung Gemini nyala/nggak.
# Varian ejaan bahan yang SAMA tapi ditulis beda-beda di dataset (bukan
# masalah instruksi masak lagi, ini masalah ejaan) — kalau nggak dinormalisasi
# di sini, "bawang bombay" dan "bawang bombai" (atau "cabe merah giling" vs
# "cabai merah giling") dianggap 2 bahan beda padahal sama. Regex \b (word
# boundary) dipakai biar cocok di manapun posisinya dalam nama, bukan cuma
# kalau nama itu PERSIS sama dengan kata kuncinya. Jalan MURNI PYTHON, gak
# bergantung Gemini nyala/nggak.
SPELLING_SYNONYM_PATTERNS: list[tuple[str, str]] = [
    (r"\bbawang bombai\b", "bawang bombay"),
    (r"\bbombai\b", "bombay"),
    (r"\bcabe\b", "cabai"),
    (r"\bsaos\b", "saus"),
    (r"\bsereh\b", "serai"),
    (r"\bjeruk limo\b", "jeruk limau"),
    (r"\bjeruk purut\b", "daun jeruk"),
    (r"\bgula pasir\b", "gula"),
    (r"\bgaram dapur\b", "garam"),
    (r"\bterasi udang\b", "terasi"),
    (r"\bkunir\b", "kunyit"),
    (r"\blombok\b", "cabai"),
    (r"\bbrambang\b", "bawang merah"),
    (r"\bbw putih\b", "bawang putih"),
    (r"\bbw merah\b", "bawang merah"),
    # 'tahu bandung' cuma varian tahu (tekstur beda dikit), bukan bahan lain —
    # kalau gak digabung, tahu kebeli 2x sendiri-sendiri padahal fungsinya sama.
    (r"\btahu bandung\b", "tahu"),
    # Minyak sayur/minyak generik nyaris selalu dimaksudkan sebagai minyak
    # goreng biasa di resep rumahan — digabung jadi SATU biar gak kebeli
    # botol minyak terpisah-pisah buat hal yang sama. 'minyak kelapa' SENGAJA
    # gak digabung (produk beda, kadang emang dipilih khusus).
    (r"\bminyak sayur\b", "minyak goreng"),
    (r"\bminyak\b(?!\s*(goreng|kelapa))", "minyak goreng"),
    # 'Saori' itu MEREK saus tiram (produk dagang), bukan bahan yang beda —
    # kalau gak digabung, saus tiram kebeli 2x sendiri-sendiri (1 disebut
    # nama merek, 1 disebut nama generiknya) padahal fungsinya sama persis.
    (r"\bsaori\b", "saus tiram"),
    # 'Lada' dan 'merica' itu KATA LAIN buat bahan yang SAMA PERSIS (bukan 2
    # jenis rempah beda) — tanpa ini, bisa muncul sampai 4 entri terpisah:
    # merica, merica bubuk, lada, lada bubuk, padahal belanjanya cuma 1 hal.
    (r"\blada\b", "merica"),
    (r"\bmerica bubuk\b", "merica"),
    (r"\bketumbar bubuk\b", "ketumbar"),
    # Royco/Masako itu MEREK penyedap rasa/kaldu bubuk (produk dagang), bukan
    # bahan tersendiri.
    (r"\broyco\b", "kaldu bubuk"),
    (r"\bmasako\b", "kaldu bubuk"),
    # Ejaan 'kriting' (typo umum) vs 'keriting', dan urutan kata yang kebalik
    # ('cabai keriting merah' vs 'cabai merah keriting') — disamain ke 1 bentuk.
    (r"\bkriting\b", "keriting"),
    (r"\bcabai keriting merah\b", "cabai merah keriting"),
    # 'kecap asin jepang/kikkoman/shoyu' — abis _split_joined_alternatives
    # ambil bagian pertama ('kecap asin jepang'), sebutan merek/asal negaranya
    # gak signifikan buat belanja, tetap kecap asin biasa.
    (r"\bkecap asin jepang\b", "kecap asin"),
]


def _apply_spelling_synonym(name: str) -> str:
    result = name
    for pattern, replacement in SPELLING_SYNONYM_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def _normalize(name: str) -> str:
    stripped = _strip_prep_instructions(name).strip().lower()
    return _apply_spelling_synonym(stripped)


def _parse_qty(raw: str) -> float | None:
    raw = raw.strip().replace(",", ".")
    try:
        if "/" in raw:
            num, denom = raw.split("/")
            return float(num) / float(denom)
        if "-" in raw or "–" in raw:
            # Rentang kayak "3-4" — ambil batas atas (lebih aman buat belanja
            # daripada kurang), bukan angka pasti dari resep.
            parts = re.split(r"[-–]", raw)
            nums = [float(p) for p in parts if p.strip()]
            return max(nums) if nums else None
        return float(raw)
    except (ValueError, ZeroDivisionError):
        return None


def _is_section_header(line: str) -> bool:
    """Dataset kadang punya baris penanda sub-bagian di tengah daftar bahan,
    mis. '@@ bumbu halus ::' (nandain kelompok "bumbu halus" berikut, bukan
    bahan beneran). Baris kayak gini gak punya huruf biasa di awalnya (cuma
    simbol) atau diakhiri '::' — dibuang sebelum diparse jadi item belanja."""
    stripped = line.strip()
    if stripped.endswith("::") or stripped.endswith(":"):
        return True
    # Baris yang mulai dengan simbol non-alfanumerik berulang (@@, **, ==, --, dst)
    if re.match(r"^[^a-zA-Z0-9]{2,}", stripped):
        return True
    return False


def _parse_ingredient_line(line: str) -> dict:
    """'3 siung bawang putih, geprek cincang' -> {"name": "bawang putih, geprek
    cincang", "qty": 3.0, "unit": "siung"}. Nama masih bisa nempel instruksi
    masak di sini — itu baru dibersihin di tahap _strip_prep_instructions()
    (dipanggil dari _normalize)."""
    line = line.strip()
    lower = line.lower()
    for marker in NON_QTY_MARKERS:
        if lower.startswith(marker):
            # PENTING: marker-nya ('secukupnya', dst) dibuang dari name juga —
            # dulu nama tetap 'secukupnya Garam' utuh, jadi nggak pernah
            # ke-gabung sama 'Garam' dari resep lain yang nulis pakai takaran
            # pasti (mis. '1 sdt garam'), padahal bahannya SAMA.
            name = line[len(marker):].strip(" ,")
            return {"name": name or line, "qty": None, "unit": None}
    match = QTY_UNIT_RE.match(line)
    if not match:
        return {"name": line, "qty": None, "unit": None}
    qty_raw, unit, name = match.groups()
    return {"name": name.strip(), "qty": _parse_qty(qty_raw), "unit": (unit or "").lower().strip() or None}


# Bahan yang SELALU dianggap ada di rumah, jadi TIDAK PERNAH muncul di daftar
# belanja meskipun dipakai di resep — orang nggak "belanja" air putih. Daftar
# ini sengaja pendek & spesifik (bukan nebak-nebak bumbu dapur mana yang PASTI
# selalu ada), gampang ditambah lagi kalau mau (mis. garam/gula) tinggal
# tambahin ke list ini.
SELALU_ADA_DI_RUMAH = ("air",)


def _selalu_ada_di_rumah(bahan_key: str) -> bool:
    bk = _normalize(bahan_key)
    return any(bk == item or bk.startswith(item + " ") for item in SELALU_ADA_DI_RUMAH)


def _summarize_jumlah(name: str, entries: list[dict], faktor_porsi: float) -> tuple[str, float, float]:
    """Convert SEMUA entry (apapun satuan aslinya: siung/buah/sdm/dst) jadi
    SATU total gram, biar daftar belanja nunjukin angka berat yang jelas
    (mis. '350 g' atau '1.2 kg') — bukan campuran satuan yang susah
    dibayangin beratnya pas belanja beneran (dulu: '3 siung + 2 buah').

    Entry yang satuannya nggak kekonversi (termasuk 'secukupnya') TETAP
    dihitung pakai estimasi kasar dari estimate_secukupnya_gram — supaya
    SEMUA bahan punya angka berat, nggak ada lagi yang 'jumlah gak jelas,
    cek pas belanja'.

    Return: (teks_ditampilkan, total_gram_kebutuhan, jumlah_gram_dibeli).
    jumlah_gram_dibeli dipakai buat hitung harga — kalau bahannya produk
    kemasan (kecap/minyak/dll), ini dibulatin ke ukuran kemasan terdekat yang
    BENERAN dijual (mis. butuh 175ml kecap -> beli 1 botol 220ml -> harga
    dihitung buat 220ml, bukan 175ml, karena itu yang beneran dibayar)."""
    total_gram = 0.0
    for e in entries:
        gram = None
        if e["qty"] is not None and e["unit"]:
            gram = convert_to_gram(name, e["qty"], e["unit"])
        if gram is None:
            gram = estimate_secukupnya_gram(name)
        total_gram += gram
    total_gram *= faktor_porsi
    display_text, beli_gram = format_market_quantity(name, total_gram)
    return display_text, total_gram, beli_gram


def build_weekly_shopping_list(
    selected_recipes: list[dict],
    bahan_dipunya: list[str],
    jumlah_orang: int,
    client=None,
    urgency: str = "sekarang",
    lat: float | None = None,
    lng: float | None = None,
    wilayah: str = DEFAULT_WILAYAH,
) -> dict:
    """selected_recipes: list of {title, ingredients} (full ingredients text asli).
    client: kalau diisi, nama bahan dibersihin & digabung 1x panggilan Gemini
    buat semua bahan sekaligus (opsional — kalau None/gagal, tetap jalan pakai
    nama mentah apa adanya)."""

    # ---------- Tahap 1: parse & agregasi mentah (murni Python) ----------
    usage_entries = defaultdict(list)   # raw_name -> list of {"qty","unit"}
    usage_recipes = defaultdict(list)   # raw_name -> list of judul resep

    for r in selected_recipes:
        raw_items = re.split(r"--|\n", r.get("ingredients", ""))
        seen_in_this_recipe = set()
        for raw in raw_items:
            raw = raw.strip()
            if not raw or _is_section_header(raw):
                continue
            parsed = _parse_ingredient_line(raw)
            key = _normalize(parsed["name"])
            if not key or key in seen_in_this_recipe or key in NON_INGREDIENT_PHRASES:
                continue
            seen_in_this_recipe.add(key)
            usage_entries[key].append({"qty": parsed["qty"], "unit": parsed["unit"]})
            usage_recipes[key].append(r.get("title", ""))

    # ---------- Tahap 2: bersihin & gabungin nama yang sama (1x panggilan Gemini) ----------
    raw_keys = list(usage_entries.keys())
    name_map = clean_and_group(raw_keys, client) if client else {}

    grouped_entries = defaultdict(list)   # nama_bersih -> gabungan entries dari semua raw_name serupa
    grouped_recipes = defaultdict(list)
    for raw_key in raw_keys:
        clean_name = name_map.get(raw_key, raw_key)  # fallback ke nama mentah kalau gak ada di mapping
        grouped_entries[clean_name].extend(usage_entries[raw_key])
        grouped_recipes[clean_name].extend(usage_recipes[raw_key])

    # ---------- Tahap 3: filter yang udah dipunya user & susun hasil akhir ----------
    bahan_dipunya_norm = [_normalize(b) for b in bahan_dipunya]

    def sudah_dipunya(bahan_key: str) -> bool:
        bk = _normalize(bahan_key)
        return any(b in bk or bk in b for b in bahan_dipunya_norm)

    missing = [k for k in grouped_entries if not sudah_dipunya(k) and not _selalu_ada_di_rumah(k)]
    missing.sort(key=lambda k: len(grouped_entries[k]), reverse=True)

    faktor_porsi = round(jumlah_orang / DEFAULT_PORSI_PER_RESEP, 2) if jumlah_orang else 1.0

    shopping_list = []
    total_harga_estimasi = 0
    for key in missing:
        suggestion = build_shopping_suggestion(key, urgency, lat, lng)
        suggestion["dipakai_di"] = len(grouped_entries[key])
        suggestion["resep"] = list(dict.fromkeys(grouped_recipes[key]))
        jumlah_str, total_gram, beli_gram = _summarize_jumlah(key, grouped_entries[key], faktor_porsi)
        suggestion["jumlah"] = jumlah_str
        harga, harga_kasar = estimate_price(key, beli_gram, wilayah)
        suggestion["harga_estimasi"] = harga
        suggestion["harga_kasar"] = harga_kasar  # True = bahan gak ketemu di tabel referensi, harga generik
        total_harga_estimasi += harga
        shopping_list.append(suggestion)

    catatan_porsi = (
        f"Asumsi tiap resep di dataset untuk sekitar {DEFAULT_PORSI_PER_RESEP} porsi. "
        f"Jumlah di atas sudah dikalikan ~{faktor_porsi}x buat {jumlah_orang} orang — "
        f"tapi ini tetap perkiraan (resep di dataset kadang gak konsisten nulis satuan), "
        f"jadi sesuaikan lagi pas belanja beneran."
    ) if jumlah_orang and jumlah_orang != DEFAULT_PORSI_PER_RESEP else None

    return {
        "shopping_list": shopping_list,
        "total_bahan_kurang": len(shopping_list),
        "total_bahan_terpakai": len(grouped_entries),
        "faktor_porsi": faktor_porsi,
        "total_harga_estimasi": total_harga_estimasi,
        "harga_disclaimer": PRICE_DISCLAIMER,
        "wilayah": wilayah,
        "catatan_porsi": catatan_porsi,
    }