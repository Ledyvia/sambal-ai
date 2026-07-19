"""Nutrition Agent (ROADMAP #5, #7) — dataset diet terpisah (All_Diets.csv) sudah
DIHAPUS dari project ini (per keputusan pakai 1 dataset utama aja). Fungsi ini
sengaja dibiarkan ada (bukan dihapus total dari pipeline) supaya orchestrator,
decision_maker, dan scoring gak perlu diubah sama sekali — semuanya sudah
didesain buat handle nutrition_context = None dengan baik (fitur nutrisi jadi
netral/nonaktif, bukan error)."""


def get_context(analysis: dict, diet_df=None) -> dict | None:
    return None
