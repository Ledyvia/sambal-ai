"""Integrasi YouTube Data API v3 — cari video tutorial masak (lihat ROADMAP_ADVANCED.md #3)."""
import requests

from config import YOUTUBE_API_KEY

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


def find_tutorial_video(recipe_title: str) -> dict | None:
    """Cari 1 video tutorial paling relevan. Return None kalau API key kosong,
    request gagal, atau tidak ada hasil — supaya sistem tetap jalan tanpa fitur ini."""
    if not YOUTUBE_API_KEY:
        return None

    params = {
        "part": "snippet",
        "q": f"cara masak {recipe_title}",
        "type": "video",
        "maxResults": 1,
        "relevanceLanguage": "id",
        "key": YOUTUBE_API_KEY,
    }
    try:
        resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=8)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    except Exception:
        return None

    if not items:
        return None

    video = items[0]
    video_id = video["id"]["videoId"]
    snippet = video["snippet"]
    return {
        "title": snippet["title"],
        "channel": snippet["channelTitle"],
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": snippet["thumbnails"]["medium"]["url"],
    }
