import logging
import re
from pathlib import Path

import fal_client
import requests

from .config import get_fal_api_key
from .metadata import TitleMetadata

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "fal-ai/flux/dev"
REQUEST_TIMEOUT = 60


def build_prompt(metadata: TitleMetadata) -> str:
    genres = ", ".join(metadata.genres) if metadata.genres else "cinematic drama"
    description = (metadata.description or "").strip()

    prompt = (
        f'Movie poster artwork for "{metadata.display_title}", genre: {genres}. '
        f"{description} "
        "Cinematic composition, dramatic lighting, highly detailed, "
        "professional movie poster art, no text, no logos, no watermarks."
    )
    return re.sub(r"\s+", " ", prompt).strip()


def generate_art(
    metadata: TitleMetadata,
    output_dir: str | Path = "output",
    model: str = DEFAULT_MODEL,
) -> Path:
    """Generate a poster image via Fal.ai and save it locally. Returns the file path."""
    api_key = get_fal_api_key()
    if not api_key:
        raise RuntimeError("FAL_API_KEY is not set")

    client = fal_client.SyncClient(key=api_key)
    prompt = build_prompt(metadata)
    logger.info("Fal.ai prompt: %s", prompt)

    result = client.subscribe(
        model,
        arguments={
            "prompt": prompt,
            "image_size": "portrait_4_3",
            "num_images": 1,
        },
    )

    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"Fal.ai returned no images: {result}")

    image_url = images[0]["url"]
    return _download_image(image_url, metadata, output_dir)


def _download_image(url: str, metadata: TitleMetadata, output_dir: str | Path) -> Path:
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(url).suffix or ".png"
    filename = _slugify(metadata.display_title, metadata.year) + suffix
    path = output_dir / filename
    path.write_bytes(response.content)
    logger.info("Saved poster to %s", path)
    return path


def _slugify(title: str, year: int | None) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower() or "untitled"
    return f"{slug}-{year}" if year else slug
