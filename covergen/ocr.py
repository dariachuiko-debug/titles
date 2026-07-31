import logging

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 75.0
MIN_CONFIDENT_WORDS = 1


def has_visible_text(image: Image.Image) -> bool:
    """Best-effort check for legible text baked into a real poster image, so we can
    prefer a real poster that already has a title over a textless one.

    Uses local OCR (Tesseract) — no external API, no key needed. Deliberately
    conservative: busy poster backgrounds (smoke, light streaks, fur) routinely get
    misread as short symbol/punctuation "words" by OCR, so only alphabetic tokens of
    at least 2 characters at high confidence count as a real text detection.
    """
    try:
        data = pytesseract.image_to_data(
            image, lang="rus+eng", config="--psm 11", output_type=pytesseract.Output.DICT
        )
    except Exception as exc:  # pytesseract/tesseract missing or failed on this image
        logger.warning("OCR text detection unavailable: %s", exc)
        return False

    confident_words = 0
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        word = text.strip()
        if not word.isalpha() or len(word) < 2:
            continue
        try:
            confidence = float(conf)
        except (TypeError, ValueError):
            continue
        if confidence >= MIN_CONFIDENCE:
            confident_words += 1

    return confident_words >= MIN_CONFIDENT_WORDS
