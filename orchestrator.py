"""Orchestrator (ROADMAP #7) — menjalankan pipeline multi-agent.

Desain paralelisasi memakai `concurrent.futures.ThreadPoolExecutor`, BUKAN
asyncio. Alasannya: Flask di sini jalan sebagai WSGI sync app (bukan ASGI),
jadi memaksa asyncio.run() di dalam route sync itu valid tapi menambah
kompleksitas tanpa manfaat nyata untuk skala tugas ini. ThreadPoolExecutor
memberi paralelisme I/O-bound yang sama (agent-agent yang saling menunggu
network/DB) dengan kode yang jauh lebih mudah dibaca & di-debug.

Ada 2 pipeline terpisah:
1. run_pipeline()          — chat 1 resep (kasih tau enaknya masak apa dari bahan)
2. run_meal_plan_pipeline() — Meal Planner AI (rencana menu N hari + shopping list)

Dua-duanya SEKARANG cuma pakai 1 dataset: tabel `recipes` (dataset utama).
Dataset "Resep Sehat" (extended_recipes) dan "Diet Explorer" (diet_recipes)
sudah dihapus dari project ini."""
from concurrent.futures import ThreadPoolExecutor
import json

from agents import (
    ingredient_analyzer,
    recipe_finder,
    nutrition_agent,
    budget_agent,
    decision_maker,
    ingredient_matching,
    substitution_agent,
    video_agent,
    shopping_agent,
    scoring,
    aggregator,
    meal_plan_analyzer,
    meal_plan_selector,
    weekly_shopping_agent,
    weekly_aggregator,
)
from services.db import (
    load_all_recipes, get_user_preferences,
    get_recipe_candidate_pool, save_meal_plan_week, save_meal_plan_settings,
    save_meal_plan_shopping_list,
)
from config import DAYS, MEAL_TYPES, MEAL_PLAN_MAX_HARI, CATEGORIES


def run_pipeline(user_input: str, client, user_id: int | None = None,
                  lat: float | None = None, lng: float | None = None) -> dict:
    """Return dict berisi 'reply' (teks final) dan 'meta' (data mentah tiap
    tahap, buat debugging/logging kalau perlu)."""

    if not client:
        return {
            "reply": "GEMINI_API_KEY belum diisi di file .env — isi dulu sebelum pakai chat.",
            "meta": {},
        }

    # ---------- Fase 1: sekuensial ----------
    analysis = ingredient_analyzer.analyze(user_input, client)

    if analysis.get("_fallback"):
        # Gemini gagal total (mis. 429 kuota habis). Daripada lanjut dengan data
        # bahan yang kosong/ngaco (yang bikin rekomendasi & link belanja jadi asal),
        # berhenti di sini dan kasih tahu user apa adanya.
        return {
            "reply": (
                "Maaf, sistem AI lagi sibuk/kuota harian tercapai jadi belum bisa "
                "menganalisis permintaanmu dengan akurat. Coba lagi dalam beberapa "
                "menit ya."
            ),
            "meta": {"analysis": analysis},
        }

    if analysis.get("intent") == "pertanyaan_umum" and not analysis.get("bahan") and not analysis.get("keywords"):
        return {"reply": "Maaf, data tidak ditemukan dalam database.", "meta": {"analysis": analysis}}

    df = load_all_recipes()
    user_prefs = get_user_preferences(user_id) if user_id else None

    # ---------- Fase 2: PARALEL ----------
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_candidates = executor.submit(recipe_finder.find, df, analysis, 8, user_prefs)
        future_nutrition = executor.submit(nutrition_agent.get_context, analysis, None)
        future_budget = executor.submit(budget_agent.get_weight, analysis)

        candidates = future_candidates.result()
        nutrition_context = future_nutrition.result()
        budget_weight = future_budget.result()

    if candidates.empty:
        return {"reply": "Maaf, data tidak ditemukan dalam database.", "meta": {"analysis": analysis}}

    # ---------- Fase 3: sekuensial ----------
    decision_text = decision_maker.decide(user_input, analysis, candidates, client, nutrition_context)

    # Recipe utama buat fitur turunan (video/matching/scoring) = kandidat skor tertinggi
    primary_recipe = candidates.iloc[0].to_dict()

    # ---------- Fase 4: sekuensial ----------
    missing_ingredients = ingredient_matching.find_missing(
        analysis.get("bahan", []), primary_recipe.get("ingredients", "")
    )

    # ---------- Fase 5: PARALEL ----------
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_substitution = executor.submit(
            substitution_agent.suggest, missing_ingredients, primary_recipe.get("title", ""), client
        )
        future_video = executor.submit(video_agent.find, primary_recipe.get("title", ""))
        future_shopping = executor.submit(
            shopping_agent.suggest, missing_ingredients, analysis.get("urgency", "sekarang"), lat, lng
        )

        substitutions = future_substitution.result()
        tutorial_video = future_video.result()
        shopping_suggestions = future_shopping.result()

    # ---------- Fase 6: sekuensial ----------
    scores = scoring.calculate(primary_recipe, analysis, nutrition_context, budget_weight)
    final_reply = aggregator.build_final_reply(
        decision_text, scores, missing_ingredients, substitutions, shopping_suggestions, tutorial_video
    )

    return {
        "reply": final_reply,
        "meta": {
            "analysis": analysis,
            "primary_recipe_id": primary_recipe.get("id"),
            "scores": scores,
            "missing_ingredients": missing_ingredients,
            "tutorial_video": tutorial_video,
        },
    }


def run_meal_plan_pipeline(
    message: str,
    client,
    user_id: int,
    jumlah_hari_form: int = 7,
    jumlah_orang_form: int = 4,
    lat: float | None = None,
    lng: float | None = None,
    wilayah: str = "jawa",
) -> dict:
    """Pipeline terpisah buat fitur Meal Planner AI (chat mingguan). Beda dari
    run_pipeline() di atas: outputnya bukan 1 resep, tapi rencana menu N hari x
    3 jenis makan + shopping list gabungan seminggu (LENGKAP DENGAN JUMLAH/BERAT
    tiap bahan, diparse dari data ingredients asli), disimpan ke DB biar muncul
    di halaman planner. Cuma butuh maksimal 2x panggilan Gemini per generate
    (1x baca chat + 1x milih semua slot sekaligus), TIDAK peduli berapa
    hari/slot yang diminta — sisanya (shopping list, jumlah bahan) dihitung
    murni Python dari data asli, bukan LLM.

    Kandidat resep dari tabel `recipes` (dataset utama, SATU-SATUNYA dataset
    di project ini) — variasi menu antar hari berdasarkan kategori bahan utama
    (ayam/sapi/ikan/dst), BUKAN klaim gizi/kalori (dataset ini gak punya data itu)."""

    if not client:
        return {
            "reply": "GEMINI_API_KEY belum diisi di file .env — isi dulu sebelum pakai fitur ini.",
            "meta": {},
        }

    # ---------- Fase 1: analisis pesan (opsional, hemat kuota kalau kosong) ----------
    if message and message.strip():
        analysis = meal_plan_analyzer.analyze(message, client)
        if analysis.get("_fallback"):
            return {
                "reply": (
                    "Maaf, sistem AI lagi sibuk atau kuota API harian tercapai, jadi "
                    "belum bisa membaca pesanmu dengan akurat. Coba lagi dalam beberapa "
                    "menit ya, atau langsung generate pakai setelan jumlah hari/orang di form."
                ),
                "meta": {"analysis": analysis},
            }
    else:
        analysis = {"bahan_dipunya": [], "jumlah_hari_override": None, "jumlah_orang_override": None,
                    "preferensi": {"hemat": False, "sehat": False}}

    jumlah_hari = analysis.get("jumlah_hari_override") or jumlah_hari_form or 7
    jumlah_hari = max(1, min(int(jumlah_hari), MEAL_PLAN_MAX_HARI))

    jumlah_orang = analysis.get("jumlah_orang_override") or jumlah_orang_form or 4
    jumlah_orang = max(1, min(int(jumlah_orang), 20))

    days = DAYS[:jumlah_hari]
    meal_types = MEAL_TYPES

    # ---------- Fase 2: ambil kandidat dari dataset utama ----------
    candidates = get_recipe_candidate_pool(CATEGORIES, per_category=12)
    if not candidates:
        return {"reply": "Maaf, data tidak ditemukan dalam database.", "meta": {"analysis": analysis}}

    # ---------- Fase 3: 1x panggilan Gemini, pilih SEMUA slot sekaligus ----------
    plan = meal_plan_selector.select_week(
        candidates, days, meal_types,
        analysis.get("bahan_dipunya", []), analysis.get("preferensi", {}),
        client,
    )
    if not plan:
        return {
            "reply": (
                "Maaf, sistem AI lagi sibuk atau kuota API harian tercapai, jadi belum "
                "bisa menyusun rencana menu minggu ini. Coba lagi dalam beberapa menit ya."
            ),
            "meta": {"analysis": analysis},
        }

    candidates_by_id = {c["id"]: c for c in candidates}
    for p in plan:
        c = candidates_by_id.get(p["recipe_id"], {})
        p["category"] = c.get("category")

    # ---------- Fase 4: shopping list gabungan LENGKAP DENGAN JUMLAH/BERAT ----------
    # Murni Python — jumlah (kg/gram/butir/dst) diparse dari teks ingredients asli
    # tiap resep, dijumlahin, diskalain sesuai jumlah orang. Bukan karangan LLM.
    selected_recipes_full = [
        {"title": p["title"], "ingredients": candidates_by_id[p["recipe_id"]].get("ingredients", "")}
        for p in plan if p["recipe_id"] in candidates_by_id
    ]
    shopping_result = weekly_shopping_agent.build_weekly_shopping_list(
        selected_recipes_full, analysis.get("bahan_dipunya", []), jumlah_orang, client=client,
        lat=lat, lng=lng, wilayah=wilayah,
    )

    # ---------- Fase 5: rangkai balasan final (video tutorial ditempel di sini) ----------
    final_reply = weekly_aggregator.build_weekly_reply(
        days, meal_types, plan, shopping_result, jumlah_orang,
    )

    # ---------- Simpan ke DB biar muncul di halaman planner tanpa perlu chat ulang ----------
    save_error = None
    if user_id:
        print(f"[meal-plan-ai] mulai simpan ke DB buat user_id={user_id}, {len(plan)} slot...")
        try:
            save_meal_plan_settings(user_id, jumlah_hari, jumlah_orang, wilayah)
            save_meal_plan_week(user_id, plan)
            save_meal_plan_shopping_list(
                user_id, json.dumps(shopping_result, ensure_ascii=False),
                final_reply,
            )
            print(f"[meal-plan-ai] BERHASIL simpan ke DB buat user_id={user_id}")
        except Exception as e:
            # print() dipakai (bukan logging module) biar PASTI muncul di terminal,
            # gak tergantung konfigurasi logging Flask yang mungkin beda-beda.
            import traceback
            print(f"[meal-plan-ai] GAGAL simpan ke DB buat user_id={user_id}: {e}")
            traceback.print_exc()
            # Dulu error ini cuma keliatan di terminal server — di layar user
            # kelihatannya "berhasil" (chat & kartu belanja tetap tampil dari
            # hasil AJAX), padahal DB-nya kosong. Baru ketauan belakangan pas
            # klik "Export PDF" dan muncul "Belum ada daftar belanja" yang
            # membingungkan. Sekarang errornya ikut dikirim ke frontend.
            save_error = str(e)
    else:
        print("[meal-plan-ai] user_id kosong/None — proses simpan ke DB DILEWATI SAMA SEKALI")

    return {
        "reply": final_reply,
        "meta": {
            "analysis": analysis,
            "plan": plan,
            "shopping_result": shopping_result,
            "jumlah_hari": jumlah_hari,
            "jumlah_orang": jumlah_orang,
            "save_error": save_error,
        },
    }