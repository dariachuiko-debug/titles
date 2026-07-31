import logging

import requests

from .config import get_fanart_api_key

logger = logging.getLogger(__name__)

FANART_BASE_URL = "https://webservice.fanart.tv/v3/movies"
REQUEST_TIMEOUT = 15


def fetch_poster(imdb_id: str | None, preferred_language: str = "ru") -> tuple[str | None, bool]:
    """Look up a real poster on fanart.tv by IMDb id.

    Returns (url, is_preferred_language). Never raises: returns (None, False) if
    FANART_API_KEY is unset, imdb_id is missing, or fanart.tv has nothing for it —
    callers should treat this as optional.
    """
    api_key = get_fanart_api_key()
    if not api_key or not imdb_id:
        return None, False

    try:
        response = requests.get(f"{FANART_BASE_URL}/{imdb_id}", params={"api_key": api_key}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 404:
            return None, False
        response.raise_for_status()
        posters = response.json().get("movieposter", [])
    except requests.RequestException as exc:
        logger.warning("fanart.tv lookup failed for %s: %s", imdb_id, exc)
        return None, False

    if not posters:
        return None, False

    def likes(poster: dict) -> int:
        try:
            return int(poster.get("likes", 0))
        except (TypeError, ValueError):
            return 0

    localized = [p for p in posters if p.get("lang") == preferred_language]
    if localized:
        localized.sort(key=likes, reverse=True)
        return localized[0]["url"], True

    posters_sorted = sorted(posters, key=likes, reverse=True)
    return posters_sorted[0]["url"], False
