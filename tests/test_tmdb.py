"""Offline tests for the TMDb client (mocked HTTP, no network calls)."""
import unittest
from unittest.mock import MagicMock, patch

from covergen.tmdb import fetch_poster_urls

SEARCH_PAYLOAD = {"results": [{"id": 42, "title": "Test Movie"}]}
IMAGES_PAYLOAD = {
    "posters": [
        {"file_path": "/en-low.jpg", "iso_639_1": "en", "vote_average": 3},
        {"file_path": "/en-high.jpg", "iso_639_1": "en", "vote_average": 8},
        {"file_path": "/ru.jpg", "iso_639_1": "ru", "vote_average": 5},
    ]
}


class FetchPosterUrlsTests(unittest.TestCase):
    def test_returns_empty_without_api_key(self):
        with patch("covergen.tmdb.get_tmdb_api_key", return_value=None):
            self.assertEqual(fetch_poster_urls("Test Movie"), [])

    def test_returns_empty_when_no_search_results(self):
        response = MagicMock(status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = {"results": []}

        with patch("covergen.tmdb.get_tmdb_api_key", return_value="key"), patch(
            "covergen.tmdb.requests.get", return_value=response
        ):
            self.assertEqual(fetch_poster_urls("Unknown Movie"), [])

    def test_orders_by_language_priority_then_vote(self):
        search_response = MagicMock(status_code=200)
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = SEARCH_PAYLOAD

        images_response = MagicMock(status_code=200)
        images_response.raise_for_status.return_value = None
        images_response.json.return_value = IMAGES_PAYLOAD

        with patch("covergen.tmdb.get_tmdb_api_key", return_value="key"), patch(
            "covergen.tmdb.requests.get", side_effect=[search_response, images_response]
        ):
            urls = fetch_poster_urls("Test Movie", language_priority=("ru", "en"))

        self.assertEqual(
            urls,
            [
                "https://image.tmdb.org/t/p/original/ru.jpg",
                "https://image.tmdb.org/t/p/original/en-high.jpg",
                "https://image.tmdb.org/t/p/original/en-low.jpg",
            ],
        )

    def test_respects_limit(self):
        search_response = MagicMock(status_code=200)
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = SEARCH_PAYLOAD

        images_response = MagicMock(status_code=200)
        images_response.raise_for_status.return_value = None
        images_response.json.return_value = IMAGES_PAYLOAD

        with patch("covergen.tmdb.get_tmdb_api_key", return_value="key"), patch(
            "covergen.tmdb.requests.get", side_effect=[search_response, images_response]
        ):
            urls = fetch_poster_urls("Test Movie", limit=1)

        self.assertEqual(len(urls), 1)


if __name__ == "__main__":
    unittest.main()
