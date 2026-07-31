"""Offline tests for image sizing/title-overlay logic (no network calls)."""
import unittest

from PIL import Image

from covergen.art import CANVAS_SIZE, _draw_title, _fit_to_canvas, poster_title
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


if __name__ == "__main__":
    unittest.main()
