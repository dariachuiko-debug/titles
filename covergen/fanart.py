import logging

import requests

from .config import get_fanart_api_key

logger = logging.getLogger(__name__)

FANART_BASE_URL = "https://webservice.fanart.tv/v3/movies"
REQUEST_TIMEOUT = 15


def fetch_poster_urls(imdb_id: str | None, preferred_language: str = "ru") -> list[str]:
    """Best-effort list of real fanart.tv poster URLs for an IMDb id, preferred-language
    posters first (each group sorted by community likes).

    Returns [] (never raises) if FANART_API_KEY is unset, imdb_id is missing, or
    fanart.tv has nothing for it — callers should treat this as optional.
    """
    api_key = get_fanart_api_key()
    if not api_key or not imdb_id:
        return []

    try:
        response = requests.get(f"{FANART_BASE_URL}/{imdb_id}", params={"api_key": api_key}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        posters = response.json().get("movieposter", [])
    except requests.RequestException as exc:
        logger.warning("fanart.tv lookup failed for %s: %s", imdb_id, exc)
        return []

    if not posters:
        return []

    def likes(poster: dict) -> int:
        try:
            return int(poster.get("likes", 0))
        except (TypeError, ValueError):
            return 0

    localized = sorted((p for p in posters if p.get("lang") == preferred_language), key=likes, reverse=True)
    other = sorted((p for p in posters if p.get("lang") != preferred_language), key=likes, reverse=True)
    return [p["url"] for p in (*localized, *other) if p.get("url")]
