import logging

import requests

from .config import get_tmdb_api_key

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"
REQUEST_TIMEOUT = 15


def fetch_localized_poster_url(title: str, year: int | None = None, language: str = "ru") -> str | None:
    """Best-effort lookup of a real, official TMDb poster localized in the given language.

    Returns None (never raises) if TMDB_API_KEY is unset, the title isn't found, or no
    poster tagged with that language exists — callers should treat this as optional.
    """
    api_key = get_tmdb_api_key()
    if not api_key:
        return None

    try:
        search_params = {"api_key": api_key, "query": title}
        if year is not None:
            search_params["year"] = year
        response = requests.get(f"{TMDB_BASE_URL}/search/movie", params=search_params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        results = response.json().get("results", [])
    except requests.RequestException as exc:
        logger.warning("TMDb search failed for %r: %s", title, exc)
        return None

    if not results:
        return None
    movie_id = results[0]["id"]

    try:
        response = requests.get(
            f"{TMDB_BASE_URL}/movie/{movie_id}/images",
            params={"api_key": api_key, "include_image_language": language},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        posters = response.json().get("posters", [])
    except requests.RequestException as exc:
        logger.warning("TMDb images lookup failed for movie_id=%s: %s", movie_id, exc)
        return None

    localized = [p for p in posters if p.get("iso_639_1") == language]
    if not localized:
        return None
    localized.sort(key=lambda p: p.get("vote_average", 0), reverse=True)
    return TMDB_IMAGE_BASE_URL + localized[0]["file_path"]
