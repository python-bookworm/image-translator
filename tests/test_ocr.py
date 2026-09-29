import unittest
from types import SimpleNamespace

from app.services.ocr import _result_payload


class OcrResultTests(unittest.TestCase):
    def test_extracts_new_paddle_result_payload(self) -> None:
        payload = {"rec_texts": ["hello"], "rec_scores": [0.9]}
        self.assertEqual(_result_payload(SimpleNamespace(res=payload)), payload)

    def test_accepts_dictionary_payload(self) -> None:
        payload = {"rec_texts": ["hello"]}
        self.assertEqual(_result_payload(payload), payload)


if __name__ == "__main__":
    unittest.main()
