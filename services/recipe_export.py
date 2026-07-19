"""services/recipe_export.py
Dua fitur PDF baru:
1. generate_recipe_pdf() — download 1 resep (dari halaman detail resep di Menu).
2. generate_meal_plan_pdf() — download SEMUA resep di rencana menu mingguan
   (Senin-Minggu), lengkap dengan bahan & langkah tiap resep, bukan cuma
   daftar belanjanya doang (itu udah ada di shopping_export.py).

Sama-sama pakai reportlab (konsisten sama shopping_export.py yang udah ada),
biar nggak nambah dependency baru.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

DAY_ORDER = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
MEAL_TYPE_ORDER = ["Sarapan", "Makan Siang", "Makan Malam"]


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Heading1"], fontSize=18, spaceAfter=4),
        "day_heading": ParagraphStyle("DayHeading", parent=base["Heading1"], fontSize=15,
                                       textColor=colors.HexColor("#C0392B"), spaceBefore=6, spaceAfter=8),
        "recipe_title": ParagraphStyle("RecipeTitle", parent=base["Heading2"], fontSize=13, spaceBefore=10, spaceAfter=2),
        "meal_label": ParagraphStyle("MealLabel", parent=base["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=2),
        "sub": ParagraphStyle("Sub", parent=base["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=12),
        "section_heading": ParagraphStyle("SectionHeading", parent=base["Normal"], fontSize=10.5,
                                           fontName="Helvetica-Bold", textColor=colors.HexColor("#4C6444"),
                                           spaceBefore=6, spaceAfter=4),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=9.5, leading=14),
        "footer": ParagraphStyle("Footer", parent=base["Normal"], fontSize=8, textColor=colors.grey),
        "cell": ParagraphStyle("Cell", parent=base["Normal"], fontSize=8.5, leading=11),
        "cell_header": ParagraphStyle("CellHeader", parent=base["Normal"], fontSize=9, fontName="Helvetica-Bold",
                                       textColor=colors.white, leading=11),
        "cell_category": ParagraphStyle("CellCategory", parent=base["Normal"], fontSize=7, textColor=colors.grey, leading=9),
    }


def _ingredients_flowables(ingredients_text: str, styles: dict) -> list:
    lines = [l.strip() for l in str(ingredients_text or "").split("--") if l.strip()]
    if not lines:
        return [Paragraph("(bahan tidak tercatat)", styles["body"])]
    bullet_text = "<br/>".join(f"&bull;&nbsp;&nbsp;{line}" for line in lines)
    return [Paragraph(bullet_text, styles["body"])]


def _steps_flowables(steps_text: str, styles: dict) -> list:
    lines = [l.strip() for l in str(steps_text or "").split("--") if l.strip()]
    if not lines:
        return [Paragraph("(langkah tidak tercatat)", styles["body"])]
    numbered_text = "<br/><br/>".join(f"{i}. {line}" for i, line in enumerate(lines, start=1))
    return [Paragraph(numbered_text, styles["body"])]


def _recipe_flowables(recipe: dict, styles: dict, heading_style_key: str = "recipe_title") -> list:
    """recipe perlu key: title, category (opsional), ingredients, steps."""
    elements = []
    title = recipe.get("title", "Resep")
    category = recipe.get("category")
    heading_text = title + (f" <font size=9 color='#888888'>({category})</font>" if category else "")
    elements.append(Paragraph(heading_text, styles[heading_style_key]))
    elements.append(Paragraph("Bahan", styles["section_heading"]))
    elements.extend(_ingredients_flowables(recipe.get("ingredients", ""), styles))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("Langkah", styles["section_heading"]))
    elements.extend(_steps_flowables(recipe.get("steps", ""), styles))
    return elements


def generate_recipe_pdf(recipe: dict) -> bytes:
    """recipe: dict dari row dataset (title, category, ingredients, steps, url opsional)."""
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.8 * cm, bottomMargin=1.5 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )

    elements = [Paragraph(recipe.get("title", "Resep"), styles["title"])]
    if recipe.get("category"):
        elements.append(Paragraph(f"Kategori: {recipe['category']}", styles["sub"]))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("Bahan", styles["section_heading"]))
    elements.extend(_ingredients_flowables(recipe.get("ingredients", ""), styles))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Langkah", styles["section_heading"]))
    elements.extend(_steps_flowables(recipe.get("steps", ""), styles))

    if recipe.get("url"):
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f'Sumber asli: <link href="{recipe["url"]}" color="blue">{recipe["url"]}</link>', styles["footer"]))

    elements.append(Spacer(1, 16))
    elements.append(Paragraph("Diunduh dari SAMBAL.AI.", styles["footer"]))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_meal_plan_pdf(plan_rows: list[dict], recipes_by_id: dict, jumlah_orang: int | None = None) -> bytes:
    """plan_rows: hasil get_meal_plan_week() -> [{day_of_week, meal_type, recipe_id, title, category}, ...]
    recipes_by_id: {recipe_id: {title, category, ingredients, steps, ...}} — buat ambil bahan & langkah
    lengkap (plan_rows sendiri cuma punya title/category, gak ada ingredients/steps).
    Return: bytes PDF, 1 hari = 1 halaman baru, tiap resep di hari itu lengkap bahan+langkahnya."""
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.8 * cm, bottomMargin=1.5 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )

    by_day = {day: {} for day in DAY_ORDER}
    for row in plan_rows:
        day = row.get("day_of_week")
        meal = row.get("meal_type")
        if day in by_day:
            by_day[day][meal] = row

    elements = [Paragraph("Rencana Menu Mingguan — SAMBAL.AI", styles["title"])]
    sub_text = "Resep lengkap (bahan & langkah) untuk semua menu Senin-Minggu."
    if jumlah_orang:
        sub_text += f" Dihitung untuk {jumlah_orang} orang."
    elements.append(Paragraph(sub_text, styles["sub"]))

    any_content = False
    for day in DAY_ORDER:
        meals = by_day.get(day, {})
        if not any(meals.values()) and not meals:
            continue
        day_has_content = False
        day_elements = [Paragraph(day, styles["day_heading"])]
        for meal_type in ("Sarapan", "Makan Siang", "Makan Malam"):
            row = meals.get(meal_type)
            if not row:
                continue
            recipe = recipes_by_id.get(row.get("recipe_id"))
            if not recipe:
                continue
            day_has_content = True
            day_elements.append(Paragraph(meal_type, styles["meal_label"]))
            day_elements.extend(_recipe_flowables(recipe, styles))
            day_elements.append(Spacer(1, 8))
        if day_has_content:
            any_content = True
            if elements and len(elements) > 2:
                elements.append(PageBreak())
            elements.extend(day_elements)

    if not any_content:
        elements.append(Paragraph("Belum ada rencana menu yang tersimpan.", styles["body"]))

    elements.append(Spacer(1, 16))
    elements.append(Paragraph("Diunduh dari SAMBAL.AI.", styles["footer"]))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_menu_table_pdf(plan_rows: list[dict], jumlah_hari: int, jumlah_orang: int | None = None) -> bytes:
    """Versi TABEL doang (kayak grid yang keliatan di layar) — cuma judul
    resep + kategori, TANPA bahan & langkah masak. Beda sama
    generate_meal_plan_pdf() di atas yang isinya resep lengkap.

    jumlah_hari dipakai buat motong tabelnya cuma sepanjang hari yang BENERAN
    di-generate (mis. kalau user generate 2 hari doang, tabelnya cuma 2 kolom
    hari, bukan 7 kolom dengan 5 kolom kosong)."""
    styles = _styles()
    days = DAY_ORDER[:max(1, min(jumlah_hari or 7, 7))]

    by_day = {day: {} for day in days}
    for row in plan_rows:
        day = row.get("day_of_week")
        meal = row.get("meal_type")
        if day in by_day:
            by_day[day][meal] = row

    buffer = io.BytesIO()
    # Landscape biar kolom harinya muat, apalagi kalau generate full 7 hari.
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )

    elements = [Paragraph("Menu Rencana Makan — SAMBAL.AI", styles["title"])]
    sub_text = f"Menu untuk {len(days)} hari ({days[0]}\u2013{days[-1]})."
    if jumlah_orang:
        sub_text += f" Dihitung untuk {jumlah_orang} orang."
    elements.append(Paragraph(sub_text, styles["sub"]))
    elements.append(Spacer(1, 6))

    header_row = [Paragraph("Waktu Makan", styles["cell_header"])] + [Paragraph(d, styles["cell_header"]) for d in days]
    table_data = [header_row]
    for meal_type in MEAL_TYPE_ORDER:
        row_cells = [Paragraph(meal_type, styles["cell_header"])]
        for day in days:
            slot = by_day.get(day, {}).get(meal_type)
            if slot and slot.get("title"):
                cell_text = slot["title"]
                if slot.get("category"):
                    cell_text += f"<br/><font color='#888888' size=7>({slot['category']})</font>"
                row_cells.append(Paragraph(cell_text, styles["cell"]))
            else:
                row_cells.append(Paragraph("\u2014", styles["cell"]))
        table_data.append(row_cells)

    usable_width = landscape(A4)[0] - 3 * cm
    label_col_width = 3.2 * cm
    day_col_width = (usable_width - label_col_width) / len(days)
    col_widths = [label_col_width] + [day_col_width] * len(days)

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C0392B")),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#4C6444")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (1, 1), (-1, -1), [colors.white, colors.HexColor("#FFF3DD")]),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)

    elements.append(Spacer(1, 14))
    elements.append(Paragraph(
        "Tabel ini cuma daftar menunya \u2014 buat bahan & langkah masak lengkap, download \"Download Resep\".",
        styles["footer"],
    ))
    elements.append(Paragraph("Diunduh dari SAMBAL.AI.", styles["footer"]))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes