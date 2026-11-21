import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

import subtitle_extractor
from subtitle_extractor import (
    SubtitleCollector,
    format_timestamp,
    normalize_text,
    read_subtitle,
    write_srt,
)


class SubtitleExtractorTests(unittest.TestCase):
    def tearDown(self):
        api = getattr(subtitle_extractor._OCR_LOCAL, "api", None)
        if api is not None:
            api.End()
        subtitle_extractor._OCR_LOCAL.__dict__.clear()

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

    def test_collector_prefers_higher_confidence_reading(self):
        collector = SubtitleCollector(500)
        collector.add(0, "سلام مایک", 45)
        collector.add(500, "سلام مایک!", 91)
        collector.add(1000, "سلام مایک", 62)
        cues = collector.close(1500)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0][2], "سلام مایک!")

    def test_structural_similarity_for_identical_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.png"
            second = Path(directory) / "second.png"
            Image.new("RGB", (120, 80), "white").save(first)
            Image.new("RGB", (120, 80), "white").save(second)
            self.assertAlmostEqual(structural_similarity(first, second), 1.0, places=5)

    def test_structural_similarity_detects_different_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.png"
            second = Path(directory) / "second.png"
            Image.new("RGB", (120, 80), "white").save(first)
            Image.new("RGB", (120, 80), "black").save(second)
            self.assertLess(structural_similarity(first, second), 0.5)

    def test_ocr_engine_is_reused_for_frames(self):
        fake_api = Mock()
        fake_api.GetUTF8Text.return_value = "Recognized text"
        fake_api.MeanTextConf.return_value = 87

        with tempfile.TemporaryDirectory() as directory:
            frame = Path(directory) / "frame.png"
            Image.new("RGB", (20, 10), "white").save(frame)

            with patch("subtitle_extractor.PyTessBaseAPI", return_value=fake_api) as factory:
                first = read_subtitle(frame, "fas", tessdata_dir=directory)
                second = read_subtitle(frame, "fas", tessdata_dir=directory)

        self.assertEqual(first, "Recognized text")
        self.assertEqual(second, "Recognized text")
        factory.assert_called_once()
        self.assertEqual(fake_api.SetImage.call_count, 2)


if __name__ == "__main__":
    unittest.main()
