"""Offline smoke tests exercising parsing/prompt logic without hitting real APIs."""
import unittest
from unittest.mock import MagicMock, patch

from covergen.art import build_prompt
from covergen.metadata import TitleMetadata, _parse_kinopoisk_doc, _parse_omdb_payload, get_metadata

KINOPOISK_DOC = {
    "id": 462,
    "name": "Стражи Галактики. Часть 2",
    "alternativeName": "Guardians of the Galaxy Vol. 2",
    "year": 2017,
    "genres": [{"name": "фантастика"}, {"name": "боевик"}],
    "poster": {"url": "https://example.com/poster.jpg"},
    "description": "Продолжение приключений команды Стражей Галактики.",
}

OMDB_PAYLOAD = {
    "Response": "True",
    "Title": "Guardians of the Galaxy Vol. 2",
    "Year": "2017",
    "Genre": "Action, Adventure, Comedy",
    "Poster": "https://example.com/omdb-poster.jpg",
    "Plot": "The Guardians struggle to keep together as a team.",
    "imdbID": "tt3896198",
}


class ParsingTests(unittest.TestCase):
    def test_parse_kinopoisk_doc(self):
        metadata = _parse_kinopoisk_doc(KINOPOISK_DOC)
        self.assertEqual(metadata.title_ru, "Стражи Галактики. Часть 2")
        self.assertEqual(metadata.title_original, "Guardians of the Galaxy Vol. 2")
        self.assertEqual(metadata.year, 2017)
        self.assertIn("фантастика", metadata.genres)
        self.assertEqual(metadata.source, "kinopoisk")
        self.assertEqual(metadata.kinopoisk_id, 462)

    def test_parse_omdb_payload(self):
        metadata = _parse_omdb_payload(OMDB_PAYLOAD)
        self.assertEqual(metadata.title_original, "Guardians of the Galaxy Vol. 2")
        self.assertEqual(metadata.year, 2017)
        self.assertEqual(metadata.genres, ["Action", "Adventure", "Comedy"])
        self.assertEqual(metadata.source, "omdb")
        self.assertEqual(metadata.imdb_id, "tt3896198")

    def test_get_metadata_falls_back_to_omdb_when_kinopoisk_empty(self):
        kinopoisk_response = MagicMock(status_code=200)
        kinopoisk_response.raise_for_status.return_value = None
        kinopoisk_response.json.return_value = {"docs": []}

        omdb_response = MagicMock(status_code=200)
        omdb_response.raise_for_status.return_value = None
        omdb_response.json.return_value = OMDB_PAYLOAD

        with patch("covergen.metadata.get_kinopoisk_api_key", return_value="k"), patch(
            "covergen.metadata.get_omdb_api_key", return_value="o"
        ), patch(
            "covergen.metadata.requests.get",
            side_effect=[kinopoisk_response, omdb_response],
        ):
            metadata = get_metadata("Guardians of the Galaxy Vol. 2", year=2017)

        self.assertEqual(metadata.source, "omdb")

    def test_build_prompt_includes_genre_and_title(self):
        metadata = TitleMetadata(
            title_ru="Стражи Галактики. Часть 2",
            title_original="Guardians of the Galaxy Vol. 2",
            year=2017,
            genres=["sci-fi", "action"],
            description="A team of misfit heroes defends the galaxy.",
            source="kinopoisk",
        )
        prompt = build_prompt(metadata)
        self.assertIn("Guardians of the Galaxy Vol. 2", prompt)
        self.assertIn("sci-fi, action", prompt)
        self.assertIn("no text", prompt)


if __name__ == "__main__":
    unittest.main()
