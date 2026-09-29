import unittest

from app.services.translator import parse_source_language_response, parse_translation_response


class TranslationResponseTests(unittest.TestCase):
    def test_parses_detected_turkish_source_language(self) -> None:
        response = '{"source_language":"tr","translations":[{"id":0,"text":"你好"}]}'

        self.assertEqual(parse_source_language_response(response), "tr")

    def test_rejects_auto_as_detected_source_language(self) -> None:
        response = '{"source_language":"auto","translations":[]}'

        with self.assertRaisesRegex(ValueError, "unsupported source language"):
            parse_source_language_response(response)

    def test_rejects_unknown_detected_source_language(self) -> None:
        response = '{"source_language":"xx","translations":[]}'

        with self.assertRaisesRegex(ValueError, "unsupported source language"):
            parse_source_language_response(response)

    def test_parses_markdown_wrapped_json_and_restores_id_order(self) -> None:
        response = """Result:\n```json
        {"translations":[{"id":1,"text":"世界"},{"id":0,"text":"你好"}]}
        ```"""

        self.assertEqual(parse_translation_response(response, 2), ["你好", "世界"])

    def test_rejects_missing_translation(self) -> None:
        response = '{"translations":[{"id":0,"text":"你好"}]}'

        with self.assertRaisesRegex(ValueError, "missing=\[1\]"):
            parse_translation_response(response, 2)

    def test_rejects_duplicate_id(self) -> None:
        response = (
            '{"translations":['
            '{"id":0,"text":"你好"},{"id":0,"text":"重复"}'
            "]}"
        )

        with self.assertRaisesRegex(ValueError, "duplicate translation id 0"):
            parse_translation_response(response, 2)


if __name__ == "__main__":
    unittest.main()
