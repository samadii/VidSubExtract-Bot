import unittest

from ocr_engines import parse_google_lens_output


class GoogleLensOutputTests(unittest.TestCase):
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
            parse_google_lens_output('{"ocr_text":"  سلام\nدنیا  "}'),
            "سلام دنیا",
        )


if __name__ == "__main__":
    unittest.main()
