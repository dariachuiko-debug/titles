"""Offline tests for image sizing/title-overlay logic (no network calls)."""
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from covergen.art import CANVAS_SIZE, _draw_title, _fit_to_canvas, _pick_accent_color, fetch_poster, poster_title
from covergen.metadata import TitleMetadata


class PosterTitleTests(unittest.TestCase):
    def test_prefers_russian_title(self):
        metadata = TitleMetadata(title_ru="Стражи Галактики", title_original="Guardians", year=2017, source="kinopoisk")
        self.assertEqual(poster_title(metadata), "Стражи Галактики")

    def test_uses_translation_when_available(self):
        metadata = TitleMetadata(title_ru=None, title_original="Guardians of the Galaxy Vol. 2", year=2017, source="omdb")
        with patch("covergen.art.translate_to_russian", return_value="Стражи Галактики. Часть 2"):
            self.assertEqual(poster_title(metadata), "Стражи Галактики. Часть 2")

    def test_falls_back_to_original_title_when_translation_unavailable(self):
        metadata = TitleMetadata(title_ru=None, title_original="Guardians of the Galaxy Vol. 2", year=2017, source="omdb")
        with patch("covergen.art.translate_to_russian", return_value=None):
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

    def test_uses_real_poster_as_is_when_russian_title_confirmed(self):
        """Step 1: Kinopoisk poster_url + confirmed title_ru -> used untouched."""
        metadata = TitleMetadata(
            title_ru="Тестовый фильм",
            title_original="Test Movie",
            year=2020,
            source="kinopoisk",
            poster_url="https://example.com/poster.jpg",
        )
        response = MagicMock(content=self._fake_poster_bytes())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "covergen.art.requests.get", return_value=response
        ) as mock_get, patch("covergen.art.fetch_localized_poster_url") as mock_tmdb:
            result = fetch_poster(metadata, output_dir=tmp_dir)
            self.assertTrue(result.is_original_art)
            self.assertTrue(result.title_is_official)
            self.assertTrue(result.path.exists())

        mock_tmdb.assert_not_called()
        mock_get.assert_called_once()

    def test_uses_tmdb_localized_poster_when_no_confirmed_russian_title(self):
        """Step 2: no title_ru, but TMDb has a real ru-localized poster -> used untouched."""
        metadata = TitleMetadata(
            title_ru=None,
            title_original="Test Movie",
            year=2020,
            source="omdb",
            poster_url="https://example.com/english-poster.jpg",
        )
        response = MagicMock(content=self._fake_poster_bytes())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "covergen.art.requests.get", return_value=response
        ), patch(
            "covergen.art.fetch_localized_poster_url", return_value="https://tmdb.example/ru-poster.jpg"
        ) as mock_tmdb, patch("covergen.art.fetch_fanart_poster", return_value=(None, False)):
            result = fetch_poster(metadata, output_dir=tmp_dir)

        mock_tmdb.assert_called_once()
        self.assertTrue(result.is_original_art)
        self.assertTrue(result.title_is_official)

    def test_uses_fanart_ru_poster_when_no_kinopoisk_or_tmdb_match(self):
        """Step 3: no title_ru, TMDb has nothing, but fanart.tv has a ru poster -> used untouched."""
        metadata = TitleMetadata(
            title_ru=None,
            title_original="Test Movie",
            year=2020,
            source="omdb",
            poster_url="https://example.com/english-poster.jpg",
            imdb_id="tt1234567",
        )
        response = MagicMock(content=self._fake_poster_bytes())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "covergen.art.requests.get", return_value=response
        ), patch("covergen.art.fetch_localized_poster_url", return_value=None), patch(
            "covergen.art.fetch_fanart_poster", return_value=("https://fanart.example/ru-poster.jpg", True)
        ) as mock_fanart:
            result = fetch_poster(metadata, output_dir=tmp_dir)

        mock_fanart.assert_called_once_with("tt1234567", preferred_language="ru")
        self.assertTrue(result.is_original_art)
        self.assertTrue(result.title_is_official)

    def test_overlays_translated_title_on_real_poster_as_last_resort_before_ai(self):
        """Step 4: real poster exists but only in English, no TMDb/fanart ru version -> overlay our translation."""
        metadata = TitleMetadata(
            title_ru=None,
            title_original="Test Movie",
            year=2020,
            source="omdb",
            poster_url="https://example.com/english-poster.jpg",
        )
        response = MagicMock(content=self._fake_poster_bytes())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "covergen.art.requests.get", return_value=response
        ), patch("covergen.art.fetch_localized_poster_url", return_value=None), patch(
            "covergen.art.fetch_fanart_poster", return_value=(None, False)
        ), patch("covergen.art.translate_to_russian", return_value="Тестовый фильм"):
            result = fetch_poster(metadata, output_dir=tmp_dir)

        self.assertTrue(result.is_original_art)
        self.assertFalse(result.title_is_official)

    def test_uses_fanart_any_language_poster_before_giving_up_to_ai(self):
        """Step 5: no metadata.poster_url at all, but fanart.tv has a poster in some other language."""
        metadata = TitleMetadata(
            title_ru=None,
            title_original="Test Movie",
            year=2020,
            source="omdb",
            poster_url=None,
            imdb_id="tt1234567",
        )
        response = MagicMock(content=self._fake_poster_bytes())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "covergen.art.requests.get", return_value=response
        ), patch("covergen.art.fetch_localized_poster_url", return_value=None), patch(
            "covergen.art.fetch_fanart_poster", return_value=("https://fanart.example/en-poster.jpg", False)
        ), patch("covergen.art.translate_to_russian", return_value="Тестовый фильм"), patch(
            "covergen.art.generate_art"
        ) as mock_generate:
            result = fetch_poster(metadata, output_dir=tmp_dir)

        mock_generate.assert_not_called()
        self.assertTrue(result.is_original_art)
        self.assertFalse(result.title_is_official)

    def test_falls_back_to_ai_art_when_no_poster_anywhere(self):
        """Step 6: nothing real found anywhere -> AI placeholder, clearly flagged as not original."""
        metadata = TitleMetadata(
            title_ru=None,
            title_original="Test Movie",
            year=2020,
            source="omdb",
            poster_url=None,
        )

        with patch("covergen.art.fetch_localized_poster_url", return_value=None), patch(
            "covergen.art.fetch_fanart_poster", return_value=(None, False)
        ), patch("covergen.art.generate_art", return_value=Path("/tmp/fake-poster.jpg")) as mock_generate:
            result = fetch_poster(metadata, output_dir="ignored")

        mock_generate.assert_called_once()
        self.assertFalse(result.is_original_art)
        self.assertFalse(result.title_is_official)

    def test_falls_back_to_ai_art_when_all_real_downloads_fail(self):
        metadata = TitleMetadata(
            title_ru="Тестовый фильм",
            title_original="Test Movie",
            year=2020,
            source="kinopoisk",
            poster_url="https://example.com/broken.jpg",
        )

        with patch("covergen.art.requests.get", side_effect=OSError("boom")), patch(
            "covergen.art.fetch_localized_poster_url", return_value=None
        ), patch("covergen.art.fetch_fanart_poster", return_value=(None, False)), patch(
            "covergen.art.generate_art", return_value=Path("/tmp/fake-poster.jpg")
        ) as mock_generate:
            result = fetch_poster(metadata, output_dir="ignored")

        mock_generate.assert_called_once()
        self.assertFalse(result.is_original_art)


class AccentColorTests(unittest.TestCase):
    def test_picks_a_vivid_color_from_the_image(self):
        image = Image.new("RGB", (200, 200), (220, 30, 30))
        color = _pick_accent_color(image)
        self.assertEqual(len(color), 3)
        self.assertTrue(all(0 <= c <= 255 for c in color))

    def test_falls_back_to_default_for_flat_grey_image(self):
        image = Image.new("RGB", (200, 200), (128, 128, 128))
        color = _pick_accent_color(image)
        self.assertEqual(color, (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
