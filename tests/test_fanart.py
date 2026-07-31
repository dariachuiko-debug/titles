"""Offline tests for the fanart.tv client (mocked HTTP, no network calls)."""
import unittest
from unittest.mock import MagicMock, patch

from covergen.fanart import fetch_poster_urls

POSTERS_PAYLOAD = {
    "movieposter": [
        {"id": "1", "url": "https://fanart.example/en-low.jpg", "lang": "en", "likes": "3"},
        {"id": "2", "url": "https://fanart.example/en-high.jpg", "lang": "en", "likes": "10"},
        {"id": "3", "url": "https://fanart.example/ru.jpg", "lang": "ru", "likes": "5"},
    ]
}


class FetchPosterUrlsTests(unittest.TestCase):
    def test_returns_empty_without_api_key(self):
        with patch("covergen.fanart.get_fanart_api_key", return_value=None):
            self.assertEqual(fetch_poster_urls("tt1234567"), [])

    def test_returns_empty_without_imdb_id(self):
        with patch("covergen.fanart.get_fanart_api_key", return_value="key"):
            self.assertEqual(fetch_poster_urls(None), [])

    def test_preferred_language_posters_come_first_by_likes(self):
        response = MagicMock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = POSTERS_PAYLOAD

        with patch("covergen.fanart.get_fanart_api_key", return_value="key"), patch(
            "covergen.fanart.requests.get", return_value=response
        ):
            urls = fetch_poster_urls("tt1234567", preferred_language="ru")

        self.assertEqual(
            urls,
            [
                "https://fanart.example/ru.jpg",
                "https://fanart.example/en-high.jpg",
                "https://fanart.example/en-low.jpg",
            ],
        )

    def test_returns_empty_on_404(self):
        response = MagicMock(status_code=404)

        with patch("covergen.fanart.get_fanart_api_key", return_value="key"), patch(
            "covergen.fanart.requests.get", return_value=response
        ):
            self.assertEqual(fetch_poster_urls("tt0000000"), [])


if __name__ == "__main__":
    unittest.main()
