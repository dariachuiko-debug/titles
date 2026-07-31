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
from .fanart import fetch_poster_urls as fetch_fanart_poster_urls
from .metadata import TitleMetadata, fetch_kinopoisk_poster_gallery
from .ocr import has_visible_text
from .tmdb import fetch_poster_urls as fetch_tmdb_poster_urls
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
TEXT_CROP_VERTICAL_BIAS = 0.85
"""Titles on portrait posters usually sit in the bottom third. When we know (via OCR)
that a candidate image has real text, bias the crop toward the bottom instead of the
default center-crop, so fitting a portrait source to our wider canvas doesn't cut the
title off."""


@dataclass
class PosterResult:
    path: Path
    is_original_art: bool
    """True: the underlying image is real (official poster/key art from Kinopoisk,
    TMDb, fanart.tv, or OMDb). False: no official artwork was found anywhere, so
    this is Fal.ai-generated placeholder art — NOT a real frame, since a
    text-to-image model has no access to actual film footage."""
    title_is_official: bool
    """True: the visible title text was confirmed (via OCR) to already be baked into
    the real poster we used — the studio's own typography, untouched by us. False:
    we overlaid a title ourselves (machine-translated and/or on AI-generated art) —
    font and exact color are our best-effort approximation."""


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
    """Get a poster image for the title, preferring a real poster that already has
    a legible title baked in, over drawing our own text on top of anything:

    1. Gather real-poster candidates from every source we have — Kinopoisk's full
       image gallery (not just the one poster on the movie record, which is often
       textless key art), TMDb, fanart.tv, and the plain poster_url from metadata —
       Russian-tagged sources first, then English.
    2. Download each in turn and check it with local OCR (Tesseract, no external
       API). The first one with confidently-detected real text wins, used as-is.
    3. If nothing anywhere has legible text, fall back to the highest-resolution
       candidate we downloaded, with our own translated title overlaid (fixed font,
       accent color sampled from that image).
    4. Only if no real image was found at all: Fal.ai-generated placeholder art
       (never real), same overlay treatment. Flagged via PosterResult.is_original_art.
    """
    candidate_urls = _gather_candidate_urls(metadata)

    best_source: tuple[int, Image.Image] | None = None  # (pixel area, raw image)
    for url in candidate_urls:
        raw_image = _try_download_image(url)
        if raw_image is None:
            continue

        area = raw_image.width * raw_image.height
        if best_source is None or area > best_source[0]:
            best_source = (area, raw_image)

        if has_visible_text(raw_image):
            image = _fit_to_canvas(raw_image, size, vertical_bias=TEXT_CROP_VERTICAL_BIAS)
            path = _save_image(image, metadata, output_dir, image_format)
            logger.info("Using real poster with detected text from %s", url)
            return PosterResult(path=path, is_original_art=True, title_is_official=True)

    if best_source is not None:
        _, raw_image = best_source
        image = _fit_to_canvas(raw_image, size)
        color = _pick_accent_color(image)
        image = _draw_title(image, poster_title(metadata), color=color)
        path = _save_image(image, metadata, output_dir, image_format)
        logger.info("No real poster had detectable text; overlaid our own title instead")
        return PosterResult(path=path, is_original_art=True, title_is_official=False)

    logger.warning(
        "No official poster available anywhere for %r — generating AI placeholder art. "
        "This is NOT real film footage/artwork, only an AI approximation.",
        metadata.display_title,
    )
    path = generate_art(metadata, output_dir=output_dir, model=model, size=size, image_format=image_format)
    return PosterResult(path=path, is_original_art=False, title_is_official=False)


def _gather_candidate_urls(metadata: TitleMetadata) -> list[str]:
    """Real-poster URLs in priority order: Russian-market sources first, then
    English-language ones. Order within a source matters less than source order,
    since fetch_poster() stops at the first one with confirmed visible text."""
    urls: list[str] = []

    urls.extend(fetch_kinopoisk_poster_gallery(metadata.kinopoisk_id))
    urls.extend(fetch_tmdb_poster_urls(metadata.display_title, metadata.year, language_priority=("ru",)))
    urls.extend(fetch_fanart_poster_urls(metadata.imdb_id, preferred_language="ru"))
    if metadata.poster_url and metadata.source == "kinopoisk":
        urls.append(metadata.poster_url)

    urls.extend(fetch_tmdb_poster_urls(metadata.display_title, metadata.year, language_priority=("en",)))
    if metadata.poster_url and metadata.poster_url not in urls:
        urls.append(metadata.poster_url)

    seen: set[str] = set()
    deduped = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _try_download_image(url: str) -> Image.Image | None:
    try:
        raw_bytes = _download_bytes(url)
        return Image.open(BytesIO(raw_bytes)).convert("RGB")
    except (requests.RequestException, OSError) as exc:
        logger.warning("Failed to fetch candidate poster %s: %s", url, exc)
        return None


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


def _fit_to_canvas(image: Image.Image, size: tuple[int, int], vertical_bias: float = 0.5) -> Image.Image:
    """Resize+crop (cover fit) so the image exactly matches the target size.

    vertical_bias controls where the crop window sits when a portrait source has to
    lose height to fill our wider canvas: 0.5 is a center crop (best for character
    compositions), closer to 1.0 keeps more of the bottom (where poster titles
    usually sit) at the cost of the top.
    """
    target_w, target_h = size
    src_w, src_h = image.size
    src_ratio = src_w / src_h
    target_ratio = target_w / target_h

    if src_ratio > target_ratio:
        new_h = target_h
        new_w = round(new_h * src_ratio)
        image = image.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        return image.crop((left, 0, left + target_w, target_h))

    new_w = target_w
    new_h = round(new_w / src_ratio)
    image = image.resize((new_w, new_h), Image.LANCZOS)
    excess = new_h - target_h
    top = max(0, min(round(excess * vertical_bias), excess))
    return image.crop((0, top, target_w, top + target_h))


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
