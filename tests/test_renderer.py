import unittest

from PIL import Image, ImageDraw, ImageFont

from app.services.renderer import _wrap


class RendererTests(unittest.TestCase):
    def test_wrap_preserves_all_characters(self) -> None:
        image = Image.new("RGB", (100, 100), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        lines = _wrap(draw, "translated text", font, 30)
        self.assertEqual("".join(lines), "translated text")
        self.assertGreater(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
