import logging

import requests

from .config import get_tmdb_api_key

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"
REQUEST_TIMEOUT = 15
DEFAULT_LANGUAGE_PRIORITY = ("ru", "en")


def fetch_poster_urls(
    title: str,
    year: int | None = None,
    language_priority: tuple[str, ...] = DEFAULT_LANGUAGE_PRIORITY,
    limit: int = 6,
) -> list[str]:
    """Best-effort list of real TMDb poster URLs for a title, ordered by language
    priority (Russian first by default) and then by TMDb's own vote score.

    Returns [] (never raises) if TMDB_API_KEY is unset, the title isn't found, or
    TMDb has nothing for it — callers should treat this as optional.
    """
    api_key = get_tmdb_api_key()
    if not api_key:
        return []

    try:
        search_params = {"api_key": api_key, "query": title}
        if year is not None:
            search_params["year"] = year
        response = requests.get(f"{TMDB_BASE_URL}/search/movie", params=search_params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        results = response.json().get("results", [])
    except requests.RequestException as exc:
        logger.warning("TMDb search failed for %r: %s", title, exc)
        return []

    if not results:
        return []
    movie_id = results[0]["id"]

    try:
        response = requests.get(
            f"{TMDB_BASE_URL}/movie/{movie_id}/images",
            params={"api_key": api_key, "include_image_language": ",".join(language_priority)},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        posters = response.json().get("posters", [])
    except requests.RequestException as exc:
        logger.warning("TMDb images lookup failed for movie_id=%s: %s", movie_id, exc)
        return []

    def sort_key(poster: dict) -> tuple[int, float]:
        lang = poster.get("iso_639_1")
        priority = language_priority.index(lang) if lang in language_priority else len(language_priority)
        return (priority, -poster.get("vote_average", 0))

    posters.sort(key=sort_key)
    return [TMDB_IMAGE_BASE_URL + poster["file_path"] for poster in posters[:limit] if poster.get("file_path")]
