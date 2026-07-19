"""Weekly Aggregator — gabungin hasil Meal Plan Selector + Weekly Shopping Agent
+ Video Agent jadi satu balasan teks final. Sama seperti aggregator.py yang lama:
bagian kuantitatif (skor, link, daftar bahan) ditempel deterministik di Python,
bukan dikarang LLM."""
from concurrent.futures import ThreadPoolExecutor

from agents.video_agent import find as find_video


def build_weekly_reply(
    days: list[str],
    meal_types: list[str],
    plan: list[dict],  # {day_of_week, meal_type, title, category, alasan_singkat}
    shopping_result: dict,
    jumlah_orang: int,
    include_video: bool = True,
) -> str:
    parts = [f"[Rencana Menu {len(days)} Hari — untuk {jumlah_orang} orang]\n"]

    plan_by_slot = {(p["day_of_week"], p["meal_type"]): p for p in plan}

    # Cari SEMUA video tutorial BARENGAN (paralel), bukan satu-satu berurutan.
    # Ini yang paling makan waktu kalau sekuensial — bisa sampai 21 kali panggilan
    # HTTP ke YouTube API buat rencana 7 hari x 3 jenis makan.
    videos_by_title = {}
    if include_video:
        titles = list({slot["title"] for slot in plan_by_slot.values()})
        with ThreadPoolExecutor(max_workers=min(len(titles), 10) or 1) as executor:
            results = executor.map(find_video, titles)
            videos_by_title = dict(zip(titles, results))

    for day in days:
        parts.append(f"\n{day}:")
        for meal in meal_types:
            slot = plan_by_slot.get((day, meal))
            if not slot:
                parts.append(f"  - {meal}: (belum ada rekomendasi cocok)")
                continue
            line = f"  - {meal}: {slot['title']}"
            if slot.get("category"):
                line += f" [{slot['category']}]"
            parts.append(line)
            if slot.get("alasan_singkat"):
                parts.append(f"    ↳ {slot['alasan_singkat']}")
            if include_video:
                video = videos_by_title.get(slot["title"])
                if video:
                    parts.append(f"    🎥 {video['url']}")
            parts.append("")

    parts.append("\n\n[Daftar Belanja Mingguan]")
    shopping_list = shopping_result["shopping_list"]
    if not shopping_list:
        parts.append("Semua bahan yang dibutuhkan sudah kamu punya. Mantap, gak perlu belanja!")
    else:
        parts.append(
            f"Total {shopping_result['total_bahan_kurang']} bahan perlu dibeli "
            f"(dari {shopping_result['total_bahan_terpakai']} total bahan yang dipakai minggu ini). "
            f"Rinciannya (nama, jumlah, link cari) ada di kartu \"Daftar Belanja Minggu Ini\" "
            f"di bawah chat ini ⬇️"
        )
        if shopping_result.get("catatan_porsi"):
            parts.append(shopping_result["catatan_porsi"])

    parts.append(
        "\n\n[Catatan]\n"
        "Variasi menu di atas dipilih berdasarkan kategori bahan utama (biar gak "
        "itu-itu terus tiap hari) dan efisiensi bahan belanja. Dataset ini gak "
        "menyimpan data kalori/gizi per resep, jadi sistem gak menampilkan angka "
        "gizi apapun — kalau butuh info gizi presisi, sebaiknya konsultasi ke "
        "sumber terpercaya lain."
    )

    return "\n".join(parts)