import logging

import requests

logger = logging.getLogger(__name__)

MYMEMORY_URL = "https://api.mymemory.translated.net/get"
REQUEST_TIMEOUT = 15


def translate_to_russian(text: str) -> str | None:
    """Best-effort machine translation via the free MyMemory API (no key required).

    Only used as a last resort for overlaying a Russian title on a real poster
    that has no official Russian title in our metadata — this is a machine
    translation, not an authoritative localized title.
    """
    if not text:
        return None

    try:
        response = requests.get(
            MYMEMORY_URL,
            params={"q": text, "langpair": "en|ru"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("Translation request failed for %r: %s", text, exc)
        return None

    translated = (payload.get("responseData") or {}).get("translatedText")
    if not translated or translated.strip().lower() == text.strip().lower():
        return None
    return translated.strip()
