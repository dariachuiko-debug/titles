"""Offline tests for the fanart.tv client (mocked HTTP, no network calls)."""
import unittest
from unittest.mock import MagicMock, patch

from covergen.fanart import fetch_poster

POSTERS_PAYLOAD = {
    "movieposter": [
        {"id": "1", "url": "https://fanart.example/en-low.jpg", "lang": "en", "likes": "3"},
        {"id": "2", "url": "https://fanart.example/en-high.jpg", "lang": "en", "likes": "10"},
        {"id": "3", "url": "https://fanart.example/ru.jpg", "lang": "ru", "likes": "5"},
    ]
}


class FetchPosterTests(unittest.TestCase):
    def test_returns_none_without_api_key(self):
        with patch("covergen.fanart.get_fanart_api_key", return_value=None):
            url, is_ru = fetch_poster("tt1234567")
        self.assertIsNone(url)
        self.assertFalse(is_ru)

    def test_returns_none_without_imdb_id(self):
        with patch("covergen.fanart.get_fanart_api_key", return_value="key"):
            url, is_ru = fetch_poster(None)
        self.assertIsNone(url)
        self.assertFalse(is_ru)

    def test_prefers_preferred_language_poster(self):
        response = MagicMock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = POSTERS_PAYLOAD

        with patch("covergen.fanart.get_fanart_api_key", return_value="key"), patch(
            "covergen.fanart.requests.get", return_value=response
        ):
            url, is_ru = fetch_poster("tt1234567", preferred_language="ru")

        self.assertEqual(url, "https://fanart.example/ru.jpg")
        self.assertTrue(is_ru)

    def test_falls_back_to_most_liked_poster_when_no_preferred_language(self):
        payload = {"movieposter": [p for p in POSTERS_PAYLOAD["movieposter"] if p["lang"] != "ru"]}
        response = MagicMock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = payload

        with patch("covergen.fanart.get_fanart_api_key", return_value="key"), patch(
            "covergen.fanart.requests.get", return_value=response
        ):
            url, is_ru = fetch_poster("tt1234567", preferred_language="ru")

        self.assertEqual(url, "https://fanart.example/en-high.jpg")
        self.assertFalse(is_ru)

    def test_returns_none_on_404(self):
        response = MagicMock(status_code=404)

        with patch("covergen.fanart.get_fanart_api_key", return_value="key"), patch(
            "covergen.fanart.requests.get", return_value=response
        ):
            url, is_ru = fetch_poster("tt0000000")

        self.assertIsNone(url)
        self.assertFalse(is_ru)


if __name__ == "__main__":
    unittest.main()
