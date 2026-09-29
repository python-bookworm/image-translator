import unittest

from app.languages import to_nllb


class LanguageTests(unittest.TestCase):
    def test_known_language_maps_to_nllb(self) -> None:
        self.assertEqual(to_nllb("zh"), "zho_Hans")
        self.assertEqual(to_nllb("km"), "khm_Khmr")

    def test_unknown_language_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported language"):
            to_nllb("not-a-language")


if __name__ == "__main__":
    unittest.main()
