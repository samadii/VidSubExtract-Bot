import unittest

from ocr_engines import parse_google_lens_output, tesseract_to_bcp47


class GoogleLensOutputTests(unittest.TestCase):
    def test_tesseract_language_codes_are_converted_to_bcp47(self):
        self.assertEqual(tesseract_to_bcp47("fas"), "fa")
        self.assertEqual(tesseract_to_bcp47("eng"), "en")
        self.assertEqual(tesseract_to_bcp47("chi_sim"), "zh-Hans")

    def test_existing_bcp47_tags_are_preserved(self):
        self.assertEqual(tesseract_to_bcp47("pt-BR"), "pt-BR")
        self.assertEqual(tesseract_to_bcp47("fa"), "fa")

    def test_unknown_three_letter_language_code_is_preserved(self):
        self.assertEqual(tesseract_to_bcp47("abc"), "abc")

    def test_parse_word_json_and_preserve_separators(self):
        output = (
            '{"file":"frame.jpg","words":['
            '{"text":"Hello","separator":" "},'
            '{"text":"world","separator":"!"}]}'
        )
        self.assertEqual(parse_google_lens_output(output), "Hello world!")

    def test_parse_empty_or_invalid_output(self):
        self.assertEqual(parse_google_lens_output(""), "")
        self.assertEqual(parse_google_lens_output("not json"), "")
        self.assertEqual(parse_google_lens_output('{"words":[]}'), "")

    def test_parse_plain_text_field(self):
        self.assertEqual(
            parse_google_lens_output('{"ocr_text":"  سلام\\nدنیا  "}'),
            "سلام دنیا",
        )


if __name__ == "__main__":
    unittest.main()
