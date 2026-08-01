import logging
from dataclasses import dataclass, field

import requests

from .config import get_kinopoisk_api_key, get_omdb_api_key

logger = logging.getLogger(__name__)

KINOPOISK_BASE_URL = "https://api.poiskkino.dev/v1.4"
OMDB_BASE_URL = "https://www.omdbapi.com/"

REQUEST_TIMEOUT = 15


class MetadataNotFoundError(Exception):
    """Raised when neither Kinopoisk nor OMDb has data for the requested title."""


@dataclass
class TitleMetadata:
    title_ru: str | None
    title_original: str | None
    year: int | None
    genres: list[str] = field(default_factory=list)
    poster_url: str | None = None
    description: str | None = None
    source: str = ""
    kinopoisk_id: int | None = None
    imdb_id: str | None = None

    @property
    def display_title(self) -> str:
        return self.title_original or self.title_ru or "Untitled"


def get_metadata(
    title: str,
    year: int | None = None,
    kinopoisk_id: int | None = None,
) -> TitleMetadata:
    """Fetch title metadata, trying Kinopoisk first and falling back to OMDb."""
    metadata = _fetch_from_kinopoisk(title, year, kinopoisk_id)
    if metadata is not None:
        return metadata

    logger.info("Kinopoisk had no match for %r, falling back to OMDb", title)
    metadata = _fetch_from_omdb(title, year)
    if metadata is not None:
        return metadata

    raise MetadataNotFoundError(
        f"Could not find metadata for title={title!r} year={year!r} "
        f"kinopoisk_id={kinopoisk_id!r} in Kinopoisk or OMDb"
    )


def _fetch_from_kinopoisk(
    title: str,
    year: int | None,
    kinopoisk_id: int | None,
) -> TitleMetadata | None:
    api_key = get_kinopoisk_api_key()
    if not api_key:
        logger.warning("KINOPOISK_API_KEY is not set, skipping Kinopoisk")
        return None

    headers = {"X-API-KEY": api_key, "accept": "application/json"}

    try:
        if kinopoisk_id is not None:
            response = requests.get(
                f"{KINOPOISK_BASE_URL}/movie/{kinopoisk_id}",
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            doc = response.json()
        else:
            response = requests.get(
                f"{KINOPOISK_BASE_URL}/movie/search",
                headers=headers,
                params={"query": title, "page": 1, "limit": 10},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            docs = response.json().get("docs", [])
            doc = _pick_best_match(docs, year)
    except requests.RequestException as exc:
        body = getattr(exc.response, "text", None)
        logger.warning("Kinopoisk request failed: %s | response body: %s", exc, body)
        return None

    if not doc:
        return None

    return _parse_kinopoisk_doc(doc)


def fetch_kinopoisk_poster_gallery(kinopoisk_id: int | None, limit: int = 6) -> list[str]:
    """Best-effort list of additional poster image URLs for a Kinopoisk movie id.

    The main movie record's poster.url is just one representative image — Kinopoisk
    hosts several poster variants per title (some with the Russian title baked in,
    some textless key art), reachable only via this separate gallery endpoint.
    Never raises: returns [] if unavailable.
    """
    api_key = get_kinopoisk_api_key()
    if not api_key or not kinopoisk_id:
        return []

    headers = {"X-API-KEY": api_key, "accept": "application/json"}
    try:
        response = requests.get(
            f"{KINOPOISK_BASE_URL}/image",
            headers=headers,
            params={"movieId": kinopoisk_id, "type": "cover", "page": 1, "limit": limit},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        docs = response.json().get("docs", [])
    except requests.RequestException as exc:
        body = getattr(exc.response, "text", None)
        logger.warning("Kinopoisk poster gallery request failed: %s | response body: %s", exc, body)
        return []

    return [doc["url"] for doc in docs if doc.get("url")]


def _pick_best_match(docs: list[dict], year: int | None) -> dict | None:
    if not docs:
        return None
    if year is not None:
        for doc in docs:
            if doc.get("year") == year:
                return doc
    return docs[0]


def _parse_kinopoisk_doc(doc: dict) -> TitleMetadata:
    genres = [g["name"] for g in doc.get("genres", []) if g.get("name")]
    poster = doc.get("poster") or {}
    description = doc.get("description") or doc.get("shortDescription")
    external_id = doc.get("externalId") or {}

    return TitleMetadata(
        title_ru=doc.get("name"),
        title_original=doc.get("alternativeName") or doc.get("enName"),
        year=doc.get("year"),
        genres=genres,
        poster_url=poster.get("url"),
        description=description,
        source="kinopoisk",
        kinopoisk_id=doc.get("id"),
        imdb_id=external_id.get("imdb"),
    )


def _fetch_from_omdb(title: str, year: int | None) -> TitleMetadata | None:
    api_key = get_omdb_api_key()
    if not api_key:
        logger.warning("OMDB_API_KEY is not set, skipping OMDb")
        return None

    params = {"apikey": api_key, "t": title, "plot": "full"}
    if year is not None:
        params["y"] = year

    try:
        response = requests.get(OMDB_BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("OMDb request failed: %s", exc)
        return None

    if payload.get("Response") != "True":
        logger.info("OMDb returned no match: %s", payload.get("Error"))
        return None

    return _parse_omdb_payload(payload)


def _parse_omdb_payload(payload: dict) -> TitleMetadata:
    genres = [g.strip() for g in payload.get("Genre", "").split(",") if g.strip()]
    year_raw = payload.get("Year", "")
    year = None
    if year_raw:
        digits = "".join(ch for ch in year_raw if ch.isdigit())[:4]
        year = int(digits) if digits else None

    poster_url = payload.get("Poster")
    if poster_url in (None, "N/A"):
        poster_url = None

    return TitleMetadata(
        title_ru=None,
        title_original=payload.get("Title"),
        year=year,
        genres=genres,
        poster_url=poster_url,
        description=payload.get("Plot"),
        source="omdb",
        imdb_id=payload.get("imdbID"),
    )
