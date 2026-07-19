"""Server-side versi dari linkify() + classifyLink() di static/js/meal-planner-ai.js
dan chat.js.

BUG YANG DIPERBAIKI: link video tutorial/maps/marketplace di balasan bot cuma
berwarna & bisa diklik kalau baru saja digenerate lewat AJAX (JS yang linkify).
Begitu halaman di-reload — meal_planner.html render ulang `ai_last_reply` dan
riwayat_chat.html render `item.reply` LANGSUNG dari Jinja sebagai teks polos
({{ ai_last_reply }}) tanpa pernah melewati proses linkify apapun. Hasilnya:
URL tampil sebagai teks mentah, tidak berwarna, tidak bisa diklik.

Modul ini dipakai sebagai Jinja filter (didaftarkan di app.py) supaya SEMUA
tempat yang menampilkan balasan bot — baik yang baru di-generate (JS) maupun
yang di-render ulang dari DB (Jinja) — pakai logika linkify yang identik.
"""
import re
from markupsafe import Markup, escape

_URL_RE = re.compile(r"(https?://[^\s]+)")


def classify_link(url: str) -> str:
    if re.search(r"youtube\.com|youtu\.be", url, re.IGNORECASE):
        return "link-video"
    if re.search(r"google\.[a-z.]+/maps", url, re.IGNORECASE):
        return "link-maps"
    return "link-marketplace"


def linkify_html(text: str) -> Markup:
    """Escape teks lalu bungkus tiap URL jadi <a> dengan class warna yang sama
    persis dengan versi JS (link-video / link-maps / link-marketplace), biar
    tampilan konsisten baik saat baru digenerate maupun setelah reload halaman."""
    if text is None:
        return Markup("")
    escaped = str(escape(str(text)))

    def _wrap(match: "re.Match") -> str:
        url = match.group(1)
        cls = classify_link(url)
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="{cls}">{url}</a>'

    return Markup(_URL_RE.sub(_wrap, escaped))
