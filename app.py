import math
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types

import config
from services.db import (
    get_connection, load_all_recipes, bump_preference_category,
    get_meal_plan_settings, save_meal_plan_settings, get_meal_plan_week,
    get_meal_plan_shopping_list_saved, get_meal_plan_last_reply, clear_meal_plan_ai,
)
from agents import video_agent, cooking_timeline
from orchestrator import run_pipeline, run_meal_plan_pipeline
from services.shopping_export import generate_shopping_list_pdf
from services.recipe_export import generate_recipe_pdf, generate_meal_plan_pdf, generate_menu_table_pdf
from services.linkify import linkify_html
from services.db import ensure_meal_plan_tables

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.jinja_env.filters["linkify"] = linkify_html

# Bikin tabel-tabel Meal Planner AI otomatis kalau belum ada (idempotent —
# CREATE TABLE IF NOT EXISTS). Ini jaring pengaman: kalau migration
# database/schema_meal_plan_ai.sql belum/lupa dijalankan manual, generate
# rencana menu tetap akan GAGAL diam-diam nyimpen ke DB (exception ketangkep
# & cuma diprint ke terminal, lihat orchestrator.py) — bikin tombol "Export
# PDF" selalu bilang "Belum ada daftar belanja" walau di layar keliatan ada.
try:
    ensure_meal_plan_tables()
except Exception as e:
    print(f"[startup] Gagal memastikan tabel Meal Planner AI ada: {e}")

client = None
if config.GEMINI_API_KEY:
    client = genai.Client(api_key=config.GEMINI_API_KEY, http_options=types.HttpOptions(timeout=60_000))


# ---------- Auth helpers ----------
def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Login dulu buat akses fitur ini ya.")
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_user():
    return {
        "current_username": session.get("username"),
        "is_logged_in": bool(session.get("user_id")),
    }


# ---------- Landing & Menu ----------
@app.route("/")
def landing():
    df = load_all_recipes()
    return render_template("landing.html", total=len(df))


@app.route("/menu")
@login_required
def menu():
    df = load_all_recipes()
    featured = df.sort_values("loves", ascending=False).head(12).to_dict(orient="records")
    return render_template("menu.html", categories=config.CATEGORIES, recipes=featured, total=len(df))


@app.route("/api/recipes")
@login_required
def api_recipes():
    df = load_all_recipes()
    category = request.args.get("category", "").strip().lower()
    search = request.args.get("search", "").strip().lower()
    page = max(int(request.args.get("page", 1)), 1)
    per_page = 12

    filtered = df
    if category:
        filtered = filtered[filtered["category"].str.lower() == category]
    if search:
        filtered = filtered[
            filtered["title"].str.lower().str.contains(search, na=False) |
            filtered["ingredients_cleaned"].str.lower().str.contains(search, na=False)
        ]

    filtered = filtered.sort_values("loves", ascending=False)
    total = len(filtered)
    start = (page - 1) * per_page
    page_items = filtered.iloc[start:start + per_page]

    return jsonify({
        "recipes": page_items[["id", "title", "category", "loves", "total_ingredients"]].to_dict(orient="records"),
        "page": page,
        "total_pages": max(math.ceil(total / per_page), 1),
        "total": total,
    })


@app.route("/resep/<int:recipe_id>")
@login_required
def recipe_detail(recipe_id):
    df = load_all_recipes()
    row = df[df["id"] == recipe_id]
    if row.empty:
        return "Resep tidak ditemukan", 404
    recipe = row.iloc[0].to_dict()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM favorites WHERE user_id = %s AND recipe_id = %s",
        (session["user_id"], recipe_id),
    )
    is_favorited = cur.fetchone() is not None
    cur.close()
    conn.close()

    # ---------- Resep serupa: kategori sama + kemiripan bahan ----------
    same_category = df[(df["category"] == recipe["category"]) & (df["id"] != recipe_id)].copy()
    current_words = set(str(recipe["ingredients_cleaned"]).lower().split())

    def overlap_score(text):
        words = set(str(text).lower().split())
        return len(words & current_words)

    same_category["_overlap"] = same_category["ingredients_cleaned"].map(overlap_score)
    similar = same_category.sort_values(["_overlap", "loves"], ascending=[False, False]).head(4)
    similar_recipes = similar[["id", "title", "category", "loves", "total_ingredients"]].to_dict(orient="records")

    # ---------- Fitur tambahan (ROADMAP #3, #6.d): tutorial video & cooking timeline ----------
    tutorial = video_agent.find(recipe["title"])
    timeline = cooking_timeline.parse(recipe["steps"])

    return render_template(
        "recipe_detail.html",
        recipe=recipe,
        is_favorited=is_favorited,
        similar_recipes=similar_recipes,
        tutorial=tutorial,
        timeline=timeline,
    )


@app.route("/resep/<int:recipe_id>/export-pdf")
@login_required
def export_recipe_pdf(recipe_id):
    df = load_all_recipes()
    row = df[df["id"] == recipe_id]
    if row.empty:
        return "Resep tidak ditemukan", 404
    recipe = row.iloc[0].to_dict()

    pdf_bytes = generate_recipe_pdf(recipe)
    safe_title = "".join(c if c.isalnum() or c in " -" else "" for c in recipe.get("title", "resep")).strip().replace(" ", "-").lower()
    filename = f"resep-{safe_title or recipe_id}-sambal-ai.pdf"

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------- Auth routes ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Semua kolom wajib diisi.")
            return render_template("register.html")
        if len(password) < 6:
            flash("Password minimal 6 karakter.")
            return render_template("register.html")

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if cur.fetchone():
            flash("Username atau email sudah dipakai.")
            cur.close()
            conn.close()
            return render_template("register.html")

        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, password_hash),
        )
        conn.commit()
        cur.close()
        conn.close()

        flash("Akun berhasil dibuat, silakan login.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, username))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Username/email atau password salah.")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        flash(f"Selamat datang, {user['username']}!")

        next_url = request.args.get("next") or url_for("landing")
        return redirect(next_url)

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Kamu sudah logout.")
    return redirect(url_for("landing"))


# ---------- Favorites (+ User Preference Memory, ROADMAP #6.e) ----------
@app.route("/favorit")
@login_required
def favorit():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT r.* FROM recipes r
        INNER JOIN favorites f ON f.recipe_id = r.id
        WHERE f.user_id = %s
        ORDER BY f.created_at DESC
    """, (session["user_id"],))
    recipes = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("favorit.html", recipes=recipes)


@app.route("/api/favorit/<int:recipe_id>", methods=["POST"])
@login_required
def toggle_favorite(recipe_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM favorites WHERE user_id = %s AND recipe_id = %s",
        (session["user_id"], recipe_id),
    )
    existing = cur.fetchone()

    if existing:
        cur.execute("DELETE FROM favorites WHERE id = %s", (existing[0],))
        favorited = False
    else:
        cur.execute(
            "INSERT INTO favorites (user_id, recipe_id) VALUES (%s, %s)",
            (session["user_id"], recipe_id),
        )
        favorited = True

    conn.commit()
    cur.close()
    conn.close()

    # User Preference Memory: update counter kategori tiap kali di-favoritkan
    if favorited:
        cur2 = get_connection().cursor()
        cur2.execute("SELECT category FROM recipes WHERE id = %s", (recipe_id,))
        row = cur2.fetchone()
        cur2.close()
        if row:
            bump_preference_category(session["user_id"], row[0])

    return jsonify({"favorited": favorited})


# ---------- Chat AI (multi-agent pipeline, butuh login) ----------
@app.route("/api/chat", methods=["POST"])
def api_chat():
    if not session.get("user_id"):
        return jsonify({"reply": "__LOGIN_REQUIRED__"}), 401
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    lat = data.get("lat")
    lng = data.get("lng")

    try:
        result = run_pipeline(message, client, user_id=session["user_id"], lat=lat, lng=lng)
        reply = result["reply"]
    except Exception as e:
        # Kalau pipeline crash (exception tak terduga di salah satu agent),
        # jangan biarkan Flask balikin 500 HTML mentah — frontend cuma bisa
        # baca JSON, kalau bodynya HTML maka fetch/res.json() di chat.js gagal
        # parse dan user cuma lihat "gagal terhubung ke server" yang menyesatkan.
        app.logger.exception("Pipeline /api/chat gagal: %s", e)
        return jsonify({
            "reply": "Maaf, terjadi kendala di server saat memproses permintaanmu. Coba lagi sebentar ya."
        }), 200

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO chat_history (user_id, message, reply) VALUES (%s, %s, %s)",
            (session["user_id"], message, reply),
        )
        conn.commit()
        chat_history_id = cur.lastrowid
        cur.close()
        conn.close()
    except Exception as e:
        # Reply dari AI tetap berhasil didapat, jadi tetap kirim ke user meski
        # gagal disimpan ke riwayat chat (mis. DB lagi down/timeout).
        app.logger.exception("Gagal simpan chat_history: %s", e)
        return jsonify({"reply": reply, "chat_history_id": None})

    return jsonify({"reply": reply, "chat_history_id": chat_history_id})


@app.route("/api/chat/feedback", methods=["POST"])
@login_required
def chat_feedback():
    data = request.get_json(silent=True) or {}
    chat_history_id = data.get("chat_history_id")
    rating = data.get("rating")  # 1 (nggak membantu) atau 5 (membantu)

    if not chat_history_id or rating not in (1, 5):
        return jsonify({"error": "Data tidak valid"}), 400

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_feedback (chat_history_id, rating) VALUES (%s, %s)",
        (chat_history_id, rating),
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/chat/history")
def api_chat_history():
    if not session.get("user_id"):
        return jsonify({"history": []})
    limit = int(request.args.get("limit", 20))
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, message, reply, created_at FROM chat_history WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (session["user_id"], limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    rows.reverse()
    for r in rows:
        r["created_at"] = r["created_at"].strftime("%d %b %Y, %H:%M")
    return jsonify({"history": rows})


@app.route("/riwayat-chat")
@login_required
def riwayat_chat():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT message, reply, created_at FROM chat_history WHERE user_id = %s ORDER BY created_at DESC",
        (session["user_id"],),
    )
    history = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("riwayat_chat.html", history=history)


# ---------- Meal Planner ----------
@app.route("/rencana-menu")
@login_required
def meal_planner():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT mp.day_of_week, mp.meal_type, r.id AS recipe_id, r.title, r.category
        FROM meal_plans mp
        INNER JOIN recipes r ON r.id = mp.recipe_id
        WHERE mp.user_id = %s
    """, (session["user_id"],))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    plan = {day: {meal: None for meal in config.MEAL_TYPES} for day in config.DAYS}
    for row in rows:
        if row["day_of_week"] in plan and row["meal_type"] in plan[row["day_of_week"]]:
            plan[row["day_of_week"]][row["meal_type"]] = row

    # Data buat panel Meal Planner AI (terpisah dari grid manual di atas)
    ai_settings = get_meal_plan_settings(session["user_id"])
    ai_rows = get_meal_plan_week(session["user_id"])
    ai_plan = {day: {meal: None for meal in config.MEAL_TYPES} for day in config.DAYS}
    for row in ai_rows:
        if row["day_of_week"] in ai_plan and row["meal_type"] in ai_plan[row["day_of_week"]]:
            ai_plan[row["day_of_week"]][row["meal_type"]] = row
    ai_has_content = len(ai_rows) > 0
    ai_shopping_list = get_meal_plan_shopping_list_saved(session["user_id"])
    ai_last_reply = get_meal_plan_last_reply(session["user_id"])

    return render_template(
        "meal_planner.html", days=config.DAYS, meal_types=config.MEAL_TYPES, plan=plan,
        ai_settings=ai_settings, ai_plan=ai_plan, ai_has_content=ai_has_content,
        ai_shopping_list=ai_shopping_list, ai_last_reply=ai_last_reply,
    )


@app.route("/api/meal-plan-ai/clear", methods=["POST"])
@login_required
def api_meal_plan_ai_clear():
    clear_meal_plan_ai(session["user_id"])
    return jsonify({"ok": True})


@app.route("/rencana-menu/export-belanja")
@login_required
def export_shopping_list_pdf():
    print(f"[export-pdf] user_id={session['user_id']} minta export PDF")
    shopping_result = get_meal_plan_shopping_list_saved(session["user_id"])
    print(f"[export-pdf] hasil query DB: {'ADA data' if shopping_result else 'KOSONG/None'}")
    if not shopping_result:
        flash("Belum ada daftar belanja buat di-export — generate rencana menu dulu ya.")
        return redirect(url_for("meal_planner"))

    meal_plan_rows = get_meal_plan_week(session["user_id"])
    ai_settings = get_meal_plan_settings(session["user_id"])
    pdf_bytes = generate_shopping_list_pdf(
        shopping_result, meal_plan_rows, jumlah_orang=ai_settings.get("jumlah_orang"),
    )

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=daftar-belanja-sambal-ai.pdf"},
    )


@app.route("/rencana-menu/export-resep")
@login_required
def export_meal_plan_pdf():
    ai_rows = get_meal_plan_week(session["user_id"])
    if not ai_rows:
        flash("Belum ada rencana menu buat di-export — generate rencana menu dulu ya.")
        return redirect(url_for("meal_planner"))

    recipe_ids = {row["recipe_id"] for row in ai_rows}
    df = load_all_recipes()
    recipes_by_id = {
        rid: df[df["id"] == rid].iloc[0].to_dict()
        for rid in recipe_ids if not df[df["id"] == rid].empty
    }

    ai_settings = get_meal_plan_settings(session["user_id"])
    pdf_bytes = generate_meal_plan_pdf(ai_rows, recipes_by_id, jumlah_orang=ai_settings.get("jumlah_orang"))

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=rencana-menu-seminggu-sambal-ai.pdf"},
    )


@app.route("/rencana-menu/export-menu")
@login_required
def export_menu_table_pdf():
    ai_rows = get_meal_plan_week(session["user_id"])
    if not ai_rows:
        flash("Belum ada rencana menu buat di-export — generate rencana menu dulu ya.")
        return redirect(url_for("meal_planner"))

    ai_settings = get_meal_plan_settings(session["user_id"])
    pdf_bytes = generate_menu_table_pdf(
        ai_rows, jumlah_hari=ai_settings.get("jumlah_hari", 7), jumlah_orang=ai_settings.get("jumlah_orang"),
    )

    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=menu-rencana-makan-sambal-ai.pdf"},
    )


@app.route("/api/meal-plan-ai/generate", methods=["POST"])
@login_required
def api_meal_plan_ai_generate():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    jumlah_hari_form = data.get("jumlah_hari", 7)
    jumlah_orang_form = data.get("jumlah_orang", 4)
    wilayah_form = data.get("wilayah", "jawa")
    lat = data.get("lat")
    lng = data.get("lng")

    try:
        jumlah_hari_form = int(jumlah_hari_form)
        jumlah_orang_form = int(jumlah_orang_form)
    except (TypeError, ValueError):
        jumlah_hari_form, jumlah_orang_form = 7, 4

    if wilayah_form not in ("jawa", "luar_jawa"):
        wilayah_form = "jawa"

    try:
        result = run_meal_plan_pipeline(
            message, client, user_id=session["user_id"],
            jumlah_hari_form=jumlah_hari_form, jumlah_orang_form=jumlah_orang_form,
            lat=lat, lng=lng, wilayah=wilayah_form,
        )
    except Exception as e:
        app.logger.exception("Pipeline /api/meal-plan-ai/generate gagal: %s", e)
        return jsonify({
            "reply": "Maaf, terjadi kendala di server saat menyusun rencana menu. Coba lagi sebentar ya."
        }), 200

    return jsonify(result)


@app.route("/api/recipes/search")
@login_required
def api_recipes_search():
    q = request.args.get("q", "").strip().lower()
    df = load_all_recipes()
    if not q:
        results = df.sort_values("loves", ascending=False).head(8)
    else:
        results = df[df["title"].str.lower().str.contains(q, na=False)].head(8)
    return jsonify(results[["id", "title", "category"]].to_dict(orient="records"))


@app.route("/api/meal-plan", methods=["POST"])
@login_required
def set_meal_plan():
    data = request.get_json(silent=True) or {}
    day = data.get("day")
    meal_type = data.get("meal_type")
    recipe_id = data.get("recipe_id")

    if day not in config.DAYS or meal_type not in config.MEAL_TYPES or not recipe_id:
        return jsonify({"error": "Data tidak valid"}), 400

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO meal_plans (user_id, day_of_week, meal_type, recipe_id)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE recipe_id = VALUES(recipe_id)
    """, (session["user_id"], day, meal_type, recipe_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/meal-plan", methods=["DELETE"])
@login_required
def delete_meal_plan():
    data = request.get_json(silent=True) or {}
    day = data.get("day")
    meal_type = data.get("meal_type")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM meal_plans WHERE user_id = %s AND day_of_week = %s AND meal_type = %s",
        (session["user_id"], day, meal_type),
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


# ---------- Halaman informasi ----------
@app.route("/tentang")
def about():
    return render_template("about.html")


@app.route("/kontak", methods=["GET", "POST"])
def kontak():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash("Semua kolom wajib diisi.")
            return render_template("kontak.html", faqs=config.FAQS)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO contact_messages (name, email, message) VALUES (%s, %s, %s)",
            (name, email, message),
        )
        conn.commit()
        cur.close()
        conn.close()

        flash("Pesan kamu berhasil terkirim, terima kasih!")
        return redirect(url_for("kontak"))

    return render_template("kontak.html", faqs=config.FAQS)


@app.route("/blog")
def blog():
    return render_template("blog.html", posts=config.BLOG_POSTS)


@app.route("/blog/<slug>")
def blog_detail(slug):
    post = next((p for p in config.BLOG_POSTS if p["slug"] == slug), None)
    if not post:
        return "Artikel tidak ditemukan", 404
    return render_template("blog_detail.html", post=post)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
