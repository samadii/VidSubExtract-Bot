import tempfile
import unittest
from pathlib import Path

from subtitle_extractor import (
    SubtitleCollector,
    format_timestamp,
    normalize_text,
    write_srt,
)


class SubtitleExtractorTests(unittest.TestCase):
    def test_normalize_text_collapses_whitespace(self):
        self.assertEqual(normalize_text("  Hello\n  world  "), "Hello world")

    def test_consecutive_samples_merge_into_one_cue(self):
        collector = SubtitleCollector(500)
        collector.add(0, "Hello world")
        collector.add(500, "Hello world!")
        collector.add(1000, "Hello world")
        cues = collector.close(1500)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0][0], 0)
        self.assertEqual(cues[0][1], 1500)

    def test_different_text_starts_new_cue(self):
        collector = SubtitleCollector(500)
        collector.add(0, "First subtitle")
        collector.add(500, "First subtitle")
        collector.add(1000, "Second subtitle")
        cues = collector.close(1500)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0][2], "First subtitle")
        self.assertEqual(cues[1][2], "Second subtitle")

    def test_single_empty_sample_closes_previous_cue(self):
        collector = SubtitleCollector(500)
        collector.add(0, "Visible subtitle")
        collector.add(500, "")
        cues = collector.close(1500)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0][1], 500)

    def test_empty_sample_is_used_as_boundary_before_new_subtitle(self):
        collector = SubtitleCollector(500)
        collector.add(0, "First subtitle")
        collector.add(500, "")
        collector.add(1000, "Second subtitle")
        cues = collector.close(1500)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0][1], 500)
        self.assertEqual(cues[1][0], 1000)

    def test_timestamp_format(self):
        self.assertEqual(format_timestamp(3_726_045), "01:02:06,045")

    def test_srt_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "captions.srt"
            count = write_srt([(0, 1500, "Hello")], output)
            self.assertEqual(count, 1)
            content = output.read_text(encoding="utf-8-sig")
            self.assertIn("00:00:00,000 --> 00:00:01,500", content)
            self.assertIn("Hello", content)


if __name__ == "__main__":
    unittest.main()
