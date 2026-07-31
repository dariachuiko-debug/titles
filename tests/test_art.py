"""Offline tests for image sizing/title-overlay logic (no network calls)."""
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from covergen.art import CANVAS_SIZE, _draw_title, _fit_to_canvas, fetch_poster, poster_title
from covergen.metadata import TitleMetadata


class PosterTitleTests(unittest.TestCase):
    def test_prefers_russian_title(self):
        metadata = TitleMetadata(title_ru="Стражи Галактики", title_original="Guardians", year=2017, source="kinopoisk")
        self.assertEqual(poster_title(metadata), "Стражи Галактики")

    def test_falls_back_to_original_title(self):
        metadata = TitleMetadata(title_ru=None, title_original="Guardians of the Galaxy Vol. 2", year=2017, source="omdb")
        self.assertEqual(poster_title(metadata), "Guardians of the Galaxy Vol. 2")


class FitToCanvasTests(unittest.TestCase):
    def test_wide_source_crops_to_exact_size(self):
        image = Image.new("RGB", (2000, 1000), "red")
        fitted = _fit_to_canvas(image, CANVAS_SIZE)
        self.assertEqual(fitted.size, CANVAS_SIZE)

    def test_tall_source_crops_to_exact_size(self):
        image = Image.new("RGB", (900, 1600), "blue")
        fitted = _fit_to_canvas(image, CANVAS_SIZE)
        self.assertEqual(fitted.size, CANVAS_SIZE)


class DrawTitleTests(unittest.TestCase):
    def test_overlay_preserves_canvas_size(self):
        image = Image.new("RGB", CANVAS_SIZE, "black")
        result = _draw_title(image, "Стражи Галактики. Часть 2")
        self.assertEqual(result.size, CANVAS_SIZE)
        self.assertEqual(result.mode, "RGB")

    def test_empty_title_is_noop(self):
        image = Image.new("RGB", CANVAS_SIZE, "black")
        result = _draw_title(image, "")
        self.assertIs(result, image)

    def test_long_title_wraps_without_error(self):
        image = Image.new("RGB", CANVAS_SIZE, "black")
        long_title = "Очень длинное название фильма, которое точно не влезет в одну строку постера"
        result = _draw_title(image, long_title)
        self.assertEqual(result.size, CANVAS_SIZE)


class FetchPosterTests(unittest.TestCase):
    @staticmethod
    def _fake_poster_bytes() -> bytes:
        buf = BytesIO()
        Image.new("RGB", (600, 900), "green").save(buf, format="JPEG")
        return buf.getvalue()

    def test_uses_real_poster_when_available(self):
        metadata = TitleMetadata(
            title_ru="Тестовый фильм",
            title_original="Test Movie",
            year=2020,
            source="kinopoisk",
            poster_url="https://example.com/poster.jpg",
        )
        response = MagicMock(content=self._fake_poster_bytes())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch("covergen.art.requests.get", return_value=response):
            result = fetch_poster(metadata, output_dir=tmp_dir)
            self.assertTrue(result.is_original)
            self.assertTrue(result.path.exists())

    def test_falls_back_to_ai_art_when_no_poster_url(self):
        metadata = TitleMetadata(
            title_ru=None,
            title_original="Test Movie",
            year=2020,
            source="omdb",
            poster_url=None,
        )

        with patch("covergen.art.generate_art", return_value=Path("/tmp/fake-poster.jpg")) as mock_generate:
            result = fetch_poster(metadata, output_dir="ignored")

        mock_generate.assert_called_once()
        self.assertFalse(result.is_original)

    def test_falls_back_to_ai_art_when_download_fails(self):
        metadata = TitleMetadata(
            title_ru="Тестовый фильм",
            title_original="Test Movie",
            year=2020,
            source="kinopoisk",
            poster_url="https://example.com/broken.jpg",
        )

        with patch("covergen.art.requests.get", side_effect=OSError("boom")), patch(
            "covergen.art.generate_art", return_value=Path("/tmp/fake-poster.jpg")
        ) as mock_generate:
            result = fetch_poster(metadata, output_dir="ignored")

        mock_generate.assert_called_once()
        self.assertFalse(result.is_original)


if __name__ == "__main__":
    unittest.main()
