"""Shopping Cleaner — bersihin nama bahan mentah dari dataset (banyak singkatan:
'bw'=bawang, 'bh'=buah, 'lbr'=lembar, dan nempel instruksi masak kayak 'geprek
cincang'/'iris serong') dan GABUNGIN bahan yang sebenernya sama tapi ditulis
beda-beda di tiap resep (mis. 'bawang putih' vs 'bw putih, cincang halus').

PENTING: agent ini CUMA ngasih nama bersih + pengelompokan (tugas linguistik,
cocok buat LLM). Angka/jumlah TETAP dihitung Python dari data asli (lihat
weekly_shopping_agent.py) — LLM gak pernah diminta ngarang angka."""
import json

from config import MODEL_NAME


def clean_and_group(raw_names: list[str], client, max_retries: int = 2) -> dict:
    """raw_names: list nama bahan mentah (apa adanya dari parsing dataset).
    Return: {raw_name: nama_bersih}. Nama bersih yang SAMA artinya beberapa raw_name
    beneran digabung jadi 1 (biar shopping list gak keliatan banyak padahal bahan
    yang sama). Kalau gagal, return {} — caller fallback ke nama mentah apa adanya
    (tetap tampil, cuma kurang rapi, BUKAN hilang)."""
    if not raw_names:
        return {}

    prompt = f"""Kamu bantu beresin daftar belanja mingguan. Berikut daftar nama bahan
MENTAH dari database resep (sering ada singkatan & nempel instruksi masak):

{json.dumps(raw_names, ensure_ascii=False)}

Tugasmu:
1. Bersihin tiap nama: buang instruksi masak yang nempel (mis. ", geprek cincang",
   ", iris serong", ", utk taburan", ", cincang halus", "kocok lepas", "kocok dulu")
   dan catatan tambahan dalam kurung (mis. "(opsional)", "(bisa diganti ...)") — itu
   CARA OLAH/catatan, bukan bagian nama bahan. Kembangin singkatan umum (bw=bawang,
   bh=buah, lbr=lembar, btr=butir, bks=bungkus, ptg=potong, sdm=sendok makan,
   sdt=sendok teh).
2. GABUNGIN raw_name yang beda tulisan tapi bahan yang SAMA jadi 1 nama_bersih yang
   sama persis. Ini termasuk (tapi tidak terbatas ke):
   - Typo/singkatan: "bw putih, cincang halus" & "bawang putih" → "bawang putih"
   - Kualifikasi yang gak signifikan buat belanja: "telur ayam" & "telur 2 butir" &
     "telur" → semua jadi "telur" (jenis/jumlah gak bikin beda produk yang dibeli)
   - Merek vs nama generik: "royco"/"masako" → "kaldu bubuk", "saori" → "saus tiram"
   - Ejaan ganda: "cabai keriting" & "cabai kriting" (typo) → satu bentuk yang sama
   Ini penting BANGET — daftar belanja yang gak digabung bikin user bingung/beli
   dobel padahal cuma 1 bahan. Kalau ragu apakah 2 nama itu bahan yang sama, anggap
   SAMA kalau intinya (jenis bahan pokoknya) identik.
3. JANGAN gabungin bahan yang beda (mis. "bawang putih" dan "bawang merah" TETAP
   dipisah, itu bahan berbeda; "minyak goreng" dan "minyak wijen" juga TETAP dipisah).

JANGAN hilangkan raw_name manapun dari output — SETIAP raw_name di input HARUS
punya pasangan di output, walaupun cuma 1 kata.

Balas HANYA JSON array, urutan bebas, struktur:
[{{"raw_name": "<persis sama seperti input>", "nama_bersih": "<hasil bersih>"}}]
"""
    for _ in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            data = json.loads(resp.text)
            mapping = {}
            valid_raw = set(raw_names)
            for item in data:
                raw = item.get("raw_name")
                clean = item.get("nama_bersih")
                if raw in valid_raw and clean:
                    mapping[raw] = clean
            # Minimal separuh raw_name berhasil dipetakan baru dianggap sukses —
            # kalau kurang dari itu kemungkinan output-nya rusak/gak lengkap.
            if len(mapping) >= max(1, len(raw_names) // 2):
                return mapping
        except Exception as e:
            print(f"[shopping_cleaner] Gemini gagal ({e}), fallback ke nama mentah + pembersihan regex saja.")
            continue
    print("[shopping_cleaner] Semua percobaan gagal/hasil gak lengkap — pakai fallback nama mentah + pembersihan regex saja.")
    return {}