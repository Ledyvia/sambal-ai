"""Video Agent (ROADMAP #3) — wrapper tipis di atas services/youtube_service.py."""
from services.youtube_service import find_tutorial_video


def find(recipe_title: str) -> dict | None:
    return find_tutorial_video(recipe_title)
