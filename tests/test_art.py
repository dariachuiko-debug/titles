"""Offline tests for image sizing/title-overlay logic (no network calls)."""
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from covergen.art import (
    CANVAS_SIZE,
    _draw_title,
    _fit_to_canvas,
    _gather_candidate_urls,
    _pick_accent_color,
    fetch_poster,
    poster_title,
)
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

    def test_vertical_bias_keeps_bottom_of_portrait_source(self):
        # Top half red, bottom half blue — a title near the bottom should survive
        # a bottom-biased crop even though the source is much taller than our canvas.
        image = Image.new("RGB", (600, 1800))
        pixels = image.load()
        for x in range(600):
            for y in range(1800):
                pixels[x, y] = (255, 0, 0) if y < 900 else (0, 0, 255)

        centered = _fit_to_canvas(image, CANVAS_SIZE, vertical_bias=0.5)
        bottom_biased = _fit_to_canvas(image, CANVAS_SIZE, vertical_bias=1.0)

        # A bottom-biased crop should contain strictly more blue (bottom) pixels
        # than a centered crop of the same source.
        def blue_fraction(img):
            colors = img.getcolors(maxcolors=img.width * img.height)
            blue = sum(count for count, color in colors if color == (0, 0, 255))
            return blue / (img.width * img.height)

        self.assertGreater(blue_fraction(bottom_biased), blue_fraction(centered))


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


class GatherCandidateUrlsTests(unittest.TestCase):
    def test_orders_and_dedups_across_sources(self):
        metadata = TitleMetadata(
            title_ru="Тестовый фильм",
            title_original="Test Movie",
            year=2020,
            source="kinopoisk",
            poster_url="https://kinopoisk.example/main.jpg",
            kinopoisk_id=123,
            imdb_id="tt1234567",
        )

        with patch(
            "covergen.art.fetch_kinopoisk_poster_gallery", return_value=["https://kinopoisk.example/gallery1.jpg"]
        ), patch(
            "covergen.art.fetch_tmdb_poster_urls",
            side_effect=[["https://tmdb.example/ru.jpg"], ["https://tmdb.example/en.jpg"]],
        ) as mock_tmdb, patch(
            "covergen.art.fetch_fanart_poster_urls",
            # duplicate of the kinopoisk poster_url, should be deduped
            return_value=["https://kinopoisk.example/main.jpg"],
        ):
            urls = _gather_candidate_urls(metadata)

        self.assertEqual(
            urls,
            [
                "https://kinopoisk.example/gallery1.jpg",
                "https://tmdb.example/ru.jpg",
                "https://kinopoisk.example/main.jpg",
                "https://tmdb.example/en.jpg",
            ],
        )
        self.assertEqual(mock_tmdb.call_args_list[0].kwargs["language_priority"], ("ru",))
        self.assertEqual(mock_tmdb.call_args_list[1].kwargs["language_priority"], ("en",))

    def test_omits_kinopoisk_poster_url_when_source_is_omdb(self):
        # OMDb's poster_url isn't Kinopoisk's own asset, so it only belongs in the
        # final English-fallback slot, not alongside the ru-priority sources.
        metadata = TitleMetadata(
            title_ru=None,
            title_original="Test Movie",
            year=2020,
            source="omdb",
            poster_url="https://omdb.example/poster.jpg",
        )

        with patch("covergen.art.fetch_kinopoisk_poster_gallery", return_value=[]), patch(
            "covergen.art.fetch_tmdb_poster_urls", return_value=[]
        ), patch("covergen.art.fetch_fanart_poster_urls", return_value=[]):
            urls = _gather_candidate_urls(metadata)

        self.assertEqual(urls, ["https://omdb.example/poster.jpg"])


class FetchPosterTests(unittest.TestCase):
    @staticmethod
    def _fake_poster_bytes(size=(600, 900)) -> bytes:
        buf = BytesIO()
        Image.new("RGB", size, "green").save(buf, format="JPEG")
        return buf.getvalue()

    def test_uses_first_candidate_with_detected_text_untouched(self):
        metadata = TitleMetadata(
            title_ru="Тестовый фильм", title_original="Test Movie", year=2020, source="kinopoisk"
        )
        response = MagicMock(content=self._fake_poster_bytes())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "covergen.art._gather_candidate_urls", return_value=["https://example.com/candidate1.jpg"]
        ), patch("covergen.art.requests.get", return_value=response) as mock_get, patch(
            "covergen.art.has_visible_text", return_value=True
        ), patch("covergen.art._draw_title") as mock_draw:
            result = fetch_poster(metadata, output_dir=tmp_dir)
            self.assertTrue(result.path.exists())

        mock_get.assert_called_once()
        mock_draw.assert_not_called()
        self.assertTrue(result.is_original_art)
        self.assertTrue(result.title_is_official)

    def test_skips_textless_candidates_until_one_has_text(self):
        metadata = TitleMetadata(
            title_ru="Тестовый фильм", title_original="Test Movie", year=2020, source="kinopoisk"
        )
        response = MagicMock(content=self._fake_poster_bytes())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "covergen.art._gather_candidate_urls",
            return_value=["https://example.com/textless.jpg", "https://example.com/with-text.jpg"],
        ), patch("covergen.art.requests.get", return_value=response) as mock_get, patch(
            "covergen.art.has_visible_text", side_effect=[False, True]
        ):
            result = fetch_poster(metadata, output_dir=tmp_dir)

        self.assertEqual(mock_get.call_count, 2)
        self.assertTrue(result.title_is_official)

    def test_overlays_own_title_on_best_resolution_candidate_when_none_have_text(self):
        metadata = TitleMetadata(
            title_ru=None, title_original="Test Movie", year=2020, source="omdb"
        )
        small = MagicMock(content=self._fake_poster_bytes((400, 600)))
        small.raise_for_status.return_value = None
        large = MagicMock(content=self._fake_poster_bytes((1600, 2400)))
        large.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "covergen.art._gather_candidate_urls",
            return_value=["https://example.com/small.jpg", "https://example.com/large.jpg"],
        ), patch("covergen.art.requests.get", side_effect=[small, large]), patch(
            "covergen.art.has_visible_text", return_value=False
        ), patch("covergen.art.translate_to_russian", return_value="Тестовый фильм"):
            result = fetch_poster(metadata, output_dir=tmp_dir)

        self.assertTrue(result.is_original_art)
        self.assertFalse(result.title_is_official)

    def test_falls_back_to_ai_art_when_no_candidate_downloads(self):
        metadata = TitleMetadata(
            title_ru=None, title_original="Test Movie", year=2020, source="omdb"
        )

        with patch("covergen.art._gather_candidate_urls", return_value=[]), patch(
            "covergen.art.generate_art", return_value=Path("/tmp/fake-poster.jpg")
        ) as mock_generate:
            result = fetch_poster(metadata, output_dir="ignored")

        mock_generate.assert_called_once()
        self.assertFalse(result.is_original_art)
        self.assertFalse(result.title_is_official)

    def test_falls_back_to_ai_art_when_all_downloads_fail(self):
        metadata = TitleMetadata(
            title_ru="Тестовый фильм", title_original="Test Movie", year=2020, source="kinopoisk"
        )

        with patch(
            "covergen.art._gather_candidate_urls", return_value=["https://example.com/broken.jpg"]
        ), patch("covergen.art.requests.get", side_effect=OSError("boom")), patch(
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
