import logging
from pathlib import Path

from .art import CANVAS_SIZE, DEFAULT_IMAGE_FORMAT, generate_art
from .metadata import TitleMetadata, get_metadata

logger = logging.getLogger(__name__)


def run_pipeline(
    title: str,
    year: int | None = None,
    kinopoisk_id: int | None = None,
    output_dir: str | Path = "output",
    size: tuple[int, int] = CANVAS_SIZE,
    image_format: str = DEFAULT_IMAGE_FORMAT,
) -> tuple[TitleMetadata, Path]:
    """Fetch metadata for a title and generate a poster for it."""
    metadata = get_metadata(title, year=year, kinopoisk_id=kinopoisk_id)
    logger.info(
        "Metadata resolved via %s: %s (%s)",
        metadata.source,
        metadata.display_title,
        metadata.year,
    )

    image_path = generate_art(metadata, output_dir=output_dir, size=size, image_format=image_format)
    return metadata, image_path
