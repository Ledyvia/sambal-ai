"""Smart Cooking Timeline (ROADMAP #6.d) — estimasi waktu per langkah masak
pakai heuristik kata kunci. Murni parsing teks, tidak butuh LLM."""
import re


def parse(steps_text: str) -> list[dict]:
    steps = re.split(r"\d+\)", str(steps_text))
    timeline = []
    cumulative = 0
    for step in steps:
        step = step.strip()
        if not step:
            continue
        duration = 5  # default 5 menit buat langkah aktif biasa
        match = re.search(r"(\d+)\s*menit", step, re.IGNORECASE)
        if match:
            duration = int(match.group(1))
        elif re.search(r"marinasi|diamkan|rendam", step, re.IGNORECASE):
            duration = 30
        elif re.search(r"rebus|kukus|panggang|goreng", step, re.IGNORECASE):
            duration = 15
        cumulative += duration
        timeline.append({"step": step, "durasi_menit": duration, "waktu_kumulatif": cumulative})
    return timeline
