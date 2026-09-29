import unittest

import cv2
import numpy as np

from app.config import Settings
from app.pipeline import ImageTranslationPipeline


class PipelineDecodeTests(unittest.TestCase):
    def test_decode_accepts_valid_image_without_loading_models(self) -> None:
        pipeline = object.__new__(ImageTranslationPipeline)
        pipeline._settings = Settings(max_image_pixels=100)
        source = np.zeros((5, 5, 3), dtype=np.uint8)
        success, encoded = cv2.imencode(".png", source)

        self.assertTrue(success)
        decoded = pipeline._decode(encoded.tobytes())
        self.assertEqual(decoded.shape, (5, 5, 3))

    def test_decode_rejects_invalid_image_without_loading_models(self) -> None:
        pipeline = object.__new__(ImageTranslationPipeline)
        pipeline._settings = Settings()

        with self.assertRaisesRegex(ValueError, "invalid image"):
            pipeline._decode(b"not-an-image")


if __name__ == "__main__":
    unittest.main()
