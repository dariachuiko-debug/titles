import logging
from pathlib import Path

from .art import CANVAS_SIZE, DEFAULT_IMAGE_FORMAT, PosterResult, fetch_poster
from .metadata import TitleMetadata, get_metadata

logger = logging.getLogger(__name__)


def run_pipeline(
    title: str,
    year: int | None = None,
    kinopoisk_id: int | None = None,
    output_dir: str | Path = "output",
    size: tuple[int, int] = CANVAS_SIZE,
    image_format: str = DEFAULT_IMAGE_FORMAT,
) -> tuple[TitleMetadata, PosterResult]:
    """Fetch metadata for a title and get a poster for it (original art, or an AI fallback)."""
    metadata = get_metadata(title, year=year, kinopoisk_id=kinopoisk_id)
    logger.info(
        "Metadata resolved via %s: %s (%s)",
        metadata.source,
        metadata.display_title,
        metadata.year,
    )

    poster = fetch_poster(metadata, output_dir=output_dir, size=size, image_format=image_format)
    return metadata, poster
