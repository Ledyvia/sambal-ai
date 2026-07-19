"""
services/shopping_export.py
Export daftar belanja mingguan (hasil Meal Planner AI) jadi file PDF yang bisa
di-download & dibawa pas belanja — bukan Excel, PDF dipilih karena langsung bisa
dibuka/diprint dari HP tanpa aplikasi tambahan.

Setiap bahan dikasih keterangan HARI dipakainya (bukan cuma "dipakai di 2 resep"
kayak di halaman web) — dicari dengan mencocokkan judul resep di shopping_list
(field 'resep') ke jadwal meal plan (day_of_week + meal_type per resep).
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT

DAY_ORDER = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _build_title_to_days_map(meal_plan_rows: list[dict]) -> dict:
    """meal_plan_rows: list of {day_of_week, meal_type, title, ...}
    -> {judul_resep_lowercase: ["Senin (Sarapan)", "Rabu (Makan Malam)", ...]}
    Urutan hari diurutkan Senin->Minggu, bukan urutan random dari DB."""
    by_title = {}
    for row in meal_plan_rows:
        key = (row.get("title") or "").strip().lower()
        if not key:
            continue
        label = f"{row['day_of_week']} ({row['meal_type']})"
        by_title.setdefault(key, []).append((row["day_of_week"], label))

    result = {}
    for key, entries in by_title.items():
        entries.sort(key=lambda e: DAY_ORDER.index(e[0]) if e[0] in DAY_ORDER else 99)
        result[key] = [label for _, label in entries]
    return result


def _days_for_item(item: dict, title_to_days: dict) -> str:
    """Gabungin keterangan hari dari semua resep yang pakai bahan ini."""
    labels = []
    for title in item.get("resep", []):
        labels.extend(title_to_days.get((title or "").strip().lower(), []))
    # dedupe tapi tetap jaga urutan
    seen = set()
    unique_labels = []
    for l in labels:
        if l not in seen:
            seen.add(l)
            unique_labels.append(l)
    return ", ".join(unique_labels) if unique_labels else "-"


def generate_shopping_list_pdf(shopping_result: dict, meal_plan_rows: list[dict], jumlah_orang: int | None = None) -> bytes:
    """shopping_result: dict dari weekly_shopping_agent.build_weekly_shopping_list()
    (atau hasil get_meal_plan_shopping_list_saved()) — punya key 'shopping_list'.
    meal_plan_rows: hasil get_meal_plan_week() — dipakai buat cari keterangan hari.
    Return: bytes isi file PDF (langsung dikirim via Flask, gak perlu simpan ke disk)."""

    title_to_days = _build_title_to_days_map(meal_plan_rows)
    items = shopping_result.get("shopping_list", [])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle("Heading", parent=styles["Heading1"], fontSize=16, spaceAfter=4)
    sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=12)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=9.5, leading=13)
    cell_bold_style = ParagraphStyle("CellBold", parent=cell_style, fontName="Helvetica-Bold")

    elements = []
    elements.append(Paragraph("Daftar Belanja Mingguan — SAMBAL.AI", heading_style))
    sub_text = "Bahan yang masih kurang buat rencana menu minggu ini."
    if jumlah_orang:
        sub_text += f" Dihitung untuk {jumlah_orang} orang."
    elements.append(Paragraph(sub_text, sub_style))

    if shopping_result.get("catatan_porsi"):
        elements.append(Paragraph(f"<i>{shopping_result['catatan_porsi']}</i>", sub_style))

    if not items:
        elements.append(Paragraph("Semua bahan yang dibutuhkan minggu ini udah kamu punya. Gak perlu belanja!", cell_style))
    else:
        table_data = [[
            Paragraph("✓", cell_bold_style),
            Paragraph("Bahan", cell_bold_style),
            Paragraph("Jumlah", cell_bold_style),
            Paragraph("Harga Estimasi", cell_bold_style),
            Paragraph("Dipakai Hari Apa", cell_bold_style),
            Paragraph("Toko", cell_bold_style),
        ]]
        for item in items:
            maps_url = item.get("maps_url")
            toko_cell = Paragraph(f'<link href="{maps_url}" color="blue">Peta</link>', cell_style) if maps_url else Paragraph("-", cell_style)
            harga = item.get("harga_estimasi")
            harga_text = f"Rp{harga:,.0f}".replace(",", ".") if harga else "-"
            if item.get("harga_kasar"):
                harga_text += " *"  # tanda perkiraan kasar (bahan gak ketemu di tabel referensi harga)
            table_data.append([
                Paragraph("☐", cell_style),
                Paragraph(item.get("bahan", "-"), cell_style),
                Paragraph(item.get("jumlah") or "cek pas belanja", cell_style),
                Paragraph(harga_text, cell_style),
                Paragraph(_days_for_item(item, title_to_days), cell_style),
                toko_cell,
            ])

        table = Table(table_data, colWidths=[0.8 * cm, 4 * cm, 3 * cm, 2.4 * cm, 4.3 * cm, 1.5 * cm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C0392B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBF3E7")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)

        total_harga = shopping_result.get("total_harga_estimasi")
        if total_harga:
            total_text = f"Total estimasi belanja: Rp{total_harga:,.0f}".replace(",", ".")
            elements.append(Spacer(1, 8))
            elements.append(Paragraph(total_text, cell_bold_style))
            elements.append(Paragraph(
                "* harga perkiraan kasar, bahan ini belum ada di tabel referensi harga kami.",
                ParagraphStyle("PriceNote", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
            ))

    elements.append(Spacer(1, 16))
    elements.append(Paragraph(
        "Dibuat otomatis oleh SAMBAL.AI dari rencana menu mingguan kamu. "
        "Kuantitas hasil parsing dari resep asli — sesuaikan lagi pas belanja beneran.",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey),
    ))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes