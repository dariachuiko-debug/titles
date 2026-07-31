import colorsys
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fal_client
import requests
from PIL import Image, ImageDraw, ImageFont

from .config import get_fal_api_key
from .fanart import fetch_poster as fetch_fanart_poster
from .metadata import TitleMetadata
from .tmdb import fetch_localized_poster_url
from .translate import translate_to_russian

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "fal-ai/flux/dev"
REQUEST_TIMEOUT = 60

CANVAS_SIZE = (1280, 768)
DEFAULT_IMAGE_FORMAT = "jpeg"
SUPPORTED_IMAGE_FORMATS = {"jpeg", "jpg", "png"}

FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
TITLE_MIN_FONT_SIZE = 22
TITLE_MAX_LINES = 2
DEFAULT_TITLE_COLOR = (255, 255, 255)


@dataclass
class PosterResult:
    path: Path
    is_original_art: bool
    """True: the underlying image is real (official poster/key art from Kinopoisk,
    OMDb, or TMDb). False: no official artwork was found anywhere, so this is
    Fal.ai-generated placeholder art — NOT a real frame, since a text-to-image
    model has no access to actual film footage."""
    title_is_official: bool
    """True: the title text visible on the image is the studio's own (either
    baked into a real, already-localized poster, or the image had no title we
    touched). False: we overlaid a title ourselves (machine-translated and/or
    on AI-generated art) — font and exact color are our best-effort approximation,
    not the franchise's real typography."""


def poster_title(metadata: TitleMetadata) -> str:
    """The title text to overlay on placeholder/untranslated art: Russian when
    available, else a best-effort machine translation of the original, else the
    original title untranslated."""
    if metadata.title_ru:
        return metadata.title_ru
    translated = translate_to_russian(metadata.title_original or "")
    return translated or metadata.title_original or ""


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


def fetch_poster(
    metadata: TitleMetadata,
    output_dir: str | Path = "output",
    model: str = DEFAULT_MODEL,
    size: tuple[int, int] = CANVAS_SIZE,
    image_format: str = DEFAULT_IMAGE_FORMAT,
) -> PosterResult:
    """Get a poster image for the title, preferring real official artwork over AI art.

    Kinopoisk's own poster CDN URLs cap out around 600x900 — noticeably softer once
    upscaled to our wider 1280x768 canvas — so TMDb/fanart.tv (which serve full
    original-resolution scans) are tried first for a Russian-localized poster, and
    Kinopoisk/OMDb's own poster_url is only a resolution fallback, not the primary pick:

    1. A real, Russian-localized poster from TMDb, if TMDB_API_KEY is configured.
    2. A real, Russian-localized poster from fanart.tv (by IMDb id), if FANART_API_KEY
       is configured.
    3. Kinopoisk/OMDb poster_url when we also have a confirmed Russian title — smaller,
       but still real and already carries the studio's own Russian typography.
    4. The real poster we do have (possibly English-only, from Kinopoisk/OMDb), with a
       best-effort translated Russian title overlaid in a fixed font and a color
       sampled from that same image.
    5. A real poster from fanart.tv in any language, same best-effort overlay.
    6. Last resort: Fal.ai-generated placeholder art (never real), with the same
       best-effort title overlay.
    """
    tmdb_url = fetch_localized_poster_url(metadata.display_title, metadata.year, language="ru")
    if tmdb_url:
        result = _try_real_poster(tmdb_url, metadata, output_dir, size, image_format, title_is_official=True)
        if result:
            return result

    fanart_url, fanart_is_ru = fetch_fanart_poster(metadata.imdb_id, preferred_language="ru")
    if fanart_url and fanart_is_ru:
        result = _try_real_poster(fanart_url, metadata, output_dir, size, image_format, title_is_official=True)
        if result:
            return result

    if metadata.poster_url and metadata.title_ru:
        result = _try_real_poster(metadata.poster_url, metadata, output_dir, size, image_format, title_is_official=True)
        if result:
            return result

    if metadata.poster_url:
        result = _try_real_poster(
            metadata.poster_url, metadata, output_dir, size, image_format, title_is_official=False, overlay_title=True
        )
        if result:
            return result

    if fanart_url:
        result = _try_real_poster(
            fanart_url, metadata, output_dir, size, image_format, title_is_official=False, overlay_title=True
        )
        if result:
            return result

    logger.warning(
        "No official poster available anywhere for %r — generating AI placeholder art. "
        "This is NOT real film footage/artwork, only an AI approximation.",
        metadata.display_title,
    )
    path = generate_art(metadata, output_dir=output_dir, model=model, size=size, image_format=image_format)
    return PosterResult(path=path, is_original_art=False, title_is_official=False)


def _try_real_poster(
    url: str,
    metadata: TitleMetadata,
    output_dir: str | Path,
    size: tuple[int, int],
    image_format: str,
    title_is_official: bool,
    overlay_title: bool = False,
) -> PosterResult | None:
    try:
        raw_bytes = _download_bytes(url)
        image = Image.open(BytesIO(raw_bytes)).convert("RGB")
    except (requests.RequestException, OSError) as exc:
        logger.warning("Failed to fetch poster %s: %s", url, exc)
        return None

    image = _fit_to_canvas(image, size)
    if overlay_title:
        color = _pick_accent_color(image)
        image = _draw_title(image, poster_title(metadata), color=color)

    path = _save_image(image, metadata, output_dir, image_format)
    logger.info("Using real poster art from %s (title_is_official=%s)", url, title_is_official)
    return PosterResult(path=path, is_original_art=True, title_is_official=title_is_official)


def generate_art(
    metadata: TitleMetadata,
    output_dir: str | Path = "output",
    model: str = DEFAULT_MODEL,
    size: tuple[int, int] = CANVAS_SIZE,
    image_format: str = DEFAULT_IMAGE_FORMAT,
) -> Path:
    """Generate placeholder poster art via Fal.ai and overlay the title. Not a real image —
    only used by fetch_poster() when no official artwork exists anywhere."""
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
    image = _draw_title(image, poster_title(metadata), color=DEFAULT_TITLE_COLOR)

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


def _pick_accent_color(image: Image.Image, fallback: tuple[int, int, int] = DEFAULT_TITLE_COLOR) -> tuple[int, int, int]:
    """Sample a vivid, high-contrast color from the poster itself, so an overlaid
    title at least echoes that specific poster's real palette instead of always
    being plain white. This is a heuristic, not an extraction of any official
    trademark color code."""
    small = image.resize((80, 80))
    quantized = small.quantize(colors=8, method=Image.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = sorted(quantized.getcolors() or [], reverse=True)

    best_hue: float | None = None
    best_sat: float | None = None
    best_score = -1.0
    for _count, idx in counts:
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s < 0.35 or v < 0.45:
            continue
        score = s * v
        if score > best_score:
            best_score = score
            best_hue, best_sat = h, s

    if best_hue is None:
        return fallback

    # The title always sits over a near-black gradient band, so force enough
    # brightness for the sampled hue to stay legible instead of blending into it.
    r, g, b = colorsys.hsv_to_rgb(best_hue, min(best_sat, 0.75), 0.95)
    return (round(r * 255), round(g * 255), round(b * 255))


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


def _draw_title(image: Image.Image, title: str, color: tuple[int, int, int] = DEFAULT_TITLE_COLOR) -> Image.Image:
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

    fill = (*color, 255)
    shadow = (0, 0, 0, 170)
    for line, box, line_height in zip(lines, line_boxes, line_heights):
        line_width = box[2] - box[0]
        x = (width - line_width) / 2 - box[0]
        draw.text((x + 3, y - box[1] + 3), line, font=font, fill=shadow)
        draw.text((x, y - box[1]), line, font=font, fill=fill)
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
