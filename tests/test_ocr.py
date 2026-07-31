"""Functional tests for OCR-based text detection (real Tesseract, no mocks/network)."""
import unittest

from PIL import Image, ImageDraw, ImageFont

from covergen.art import FONT_PATH
from covergen.ocr import has_visible_text


class HasVisibleTextTests(unittest.TestCase):
    def test_detects_real_rendered_text(self):
        image = Image.new("RGB", (800, 400), (20, 20, 20))
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(FONT_PATH), 64)
        draw.text((60, 150), "Стражи Галактики", font=font, fill=(255, 255, 255))
        self.assertTrue(has_visible_text(image))

    def test_blank_image_has_no_text(self):
        image = Image.new("RGB", (800, 400), (30, 30, 30))
        self.assertFalse(has_visible_text(image))

    def test_flat_color_photo_like_noise_has_no_text(self):
        image = Image.new("RGB", (800, 400))
        pixels = image.load()
        for x in range(800):
            for y in range(400):
                pixels[x, y] = ((x * 7) % 256, (y * 13) % 256, ((x + y) * 5) % 256)
        self.assertFalse(has_visible_text(image))


if __name__ == "__main__":
    unittest.main()
