import logging
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fal_client
import requests
from PIL import Image, ImageDraw, ImageFont

from .config import get_fal_api_key
from .metadata import TitleMetadata

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "fal-ai/flux/dev"
REQUEST_TIMEOUT = 60

CANVAS_SIZE = (1280, 768)
DEFAULT_IMAGE_FORMAT = "jpeg"
SUPPORTED_IMAGE_FORMATS = {"jpeg", "jpg", "png"}

FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
TITLE_MIN_FONT_SIZE = 22
TITLE_MAX_LINES = 2


@dataclass
class PosterResult:
    path: Path
    is_original: bool
    """True: real official poster art (from Kinopoisk/OMDb poster_url), fit to size only.
    False: no official poster was found; this is Fal.ai-generated placeholder art — it is
    NOT a real frame or official artwork, just an AI approximation, since a text-to-image
    model has no access to actual film footage."""


def poster_title(metadata: TitleMetadata) -> str:
    """The title text overlaid on AI-generated placeholder art: Russian when available, else original."""
    return metadata.title_ru or metadata.title_original or ""


def fetch_poster(
    metadata: TitleMetadata,
    output_dir: str | Path = "output",
    model: str = DEFAULT_MODEL,
    size: tuple[int, int] = CANVAS_SIZE,
    image_format: str = DEFAULT_IMAGE_FORMAT,
) -> PosterResult:
    """Get a poster image for the title: the real official poster when one exists,
    otherwise an AI-generated placeholder as a last resort."""
    if metadata.poster_url:
        try:
            raw_bytes = _download_bytes(metadata.poster_url)
            image = Image.open(BytesIO(raw_bytes)).convert("RGB")
            image = _fit_to_canvas(image, size)
            path = _save_image(image, metadata, output_dir, image_format)
            logger.info("Using original poster art (%s) from %s", metadata.poster_url, metadata.source)
            return PosterResult(path=path, is_original=True)
        except (requests.RequestException, OSError) as exc:
            logger.warning("Failed to fetch original poster %s: %s — falling back to AI art", metadata.poster_url, exc)

    logger.warning(
        "No original poster available for %r — generating AI placeholder art. "
        "This is NOT real film footage/artwork, only an AI approximation.",
        metadata.display_title,
    )
    path = generate_art(metadata, output_dir=output_dir, model=model, size=size, image_format=image_format)
    return PosterResult(path=path, is_original=False)


def build_prompt(metadata: TitleMetadata) -> str:
    genres = ", ".join(metadata.genres) if metadata.genres else "cinematic drama"
    description = (metadata.description or "").strip()

    prompt = (
        f'Movie poster artwork for "{metadata.display_title}", genre: {genres}. '
        f"{description} "
        "Cinematic composition, dramatic lighting, highly detailed, professional "
        "movie poster art. The title is added separately afterward, so the image "
        "itself must contain no text, no letters, no titles, no logos, no watermarks."
    )
    return re.sub(r"\s+", " ", prompt).strip()


def generate_art(
    metadata: TitleMetadata,
    output_dir: str | Path = "output",
    model: str = DEFAULT_MODEL,
    size: tuple[int, int] = CANVAS_SIZE,
    image_format: str = DEFAULT_IMAGE_FORMAT,
) -> Path:
    """Generate poster art via Fal.ai, overlay the (Russian) title, and save it locally."""
    image_format = image_format.lower()
    if image_format not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError(f"Unsupported image_format: {image_format!r}, expected one of {SUPPORTED_IMAGE_FORMATS}")

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
            "image_size": {"width": size[0], "height": size[1]},
            "num_images": 1,
        },
    )

    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"Fal.ai returned no images: {result}")

    raw_bytes = _download_bytes(images[0]["url"])
    image = Image.open(BytesIO(raw_bytes)).convert("RGB")
    image = _fit_to_canvas(image, size)
    image = _draw_title(image, poster_title(metadata))

    return _save_image(image, metadata, output_dir, image_format)


def _download_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.content


def _fit_to_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize+center-crop (cover fit) so the image exactly matches the target size."""
    target_w, target_h = size
    src_w, src_h = image.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        new_h = target_h
        new_w = round(new_h * src_ratio)
    else:
        new_w = target_w
        new_h = round(new_w / src_ratio)

    image = image.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return image.crop((left, top, left + target_w, top + target_h))


def _wrap_title(draw: ImageDraw.ImageDraw, title: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if draw.textbbox((0, 0), title, font=font)[2] <= max_width:
        return [title]

    words = title.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_title(image: Image.Image, title: str) -> Image.Image:
    """Overlay the poster title in a fixed, consistent font over a darkened bottom band."""
    if not title:
        return image

    image = image.convert("RGBA")
    width, height = image.size
    margin = round(width * 0.06)
    max_text_width = width - 2 * margin
    band_height = round(height * 0.28)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    band_draw = ImageDraw.Draw(overlay)
    for y in range(band_height):
        alpha = round(200 * (y / band_height))
        band_draw.line([(0, height - band_height + y), (width, height - band_height + y)], fill=(0, 0, 0, alpha))
    image = Image.alpha_composite(image, overlay)
    draw = ImageDraw.Draw(image)

    font_size = round(height * 0.1)
    font = ImageFont.truetype(str(FONT_PATH), font_size)
    lines = [title]
    while font_size > TITLE_MIN_FONT_SIZE:
        font = ImageFont.truetype(str(FONT_PATH), font_size)
        lines = _wrap_title(draw, title, font, max_text_width)
        fits = len(lines) <= TITLE_MAX_LINES and all(
            draw.textbbox((0, 0), line, font=font)[2] <= max_text_width for line in lines
        )
        if fits:
            break
        font_size -= 2

    line_gap = round(font_size * 0.25)
    line_boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_heights = [box[3] - box[1] for box in line_boxes]
    total_text_height = sum(line_heights) + line_gap * (len(lines) - 1)
    y = height - margin - total_text_height

    for line, box, line_height in zip(lines, line_boxes, line_heights):
        line_width = box[2] - box[0]
        x = (width - line_width) / 2 - box[0]
        draw.text((x + 3, y - box[1] + 3), line, font=font, fill=(0, 0, 0, 170))
        draw.text((x, y - box[1]), line, font=font, fill=(255, 255, 255, 255))
        y += line_height + line_gap

    return image.convert("RGB")


def _save_image(image: Image.Image, metadata: TitleMetadata, output_dir: str | Path, image_format: str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fmt = "jpeg" if image_format in ("jpeg", "jpg") else "png"
    extension = "jpg" if fmt == "jpeg" else "png"
    filename = _slugify(metadata.display_title, metadata.year) + f".{extension}"
    path = output_dir / filename

    save_kwargs = {"quality": 92, "optimize": True} if fmt == "jpeg" else {"optimize": True}
    image.save(path, format=fmt.upper(), **save_kwargs)
    logger.info("Saved poster to %s (%dx%d, %s)", path, image.width, image.height, fmt.upper())
    return path


def _slugify(title: str, year: int | None) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title).strip("-").lower() or "untitled"
    return f"{slug}-{year}" if year else slug
