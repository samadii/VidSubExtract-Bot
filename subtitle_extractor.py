from __future__ import annotations

import math
import os
import re
import subprocess
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageOps
import pytesseract


def extract_frames(video_path: str, output_dir: str, interval_ms: int = 500) -> list[Path]:
    """Extract sampled frames with one FFmpeg process instead of one process per frame."""
    if interval_ms < 100:
        raise ValueError("OCR_INTERVAL_MS must be at least 100 milliseconds.")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    pattern = output / "frame_%06d.jpg"
    fps = 1000 / interval_ms

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video_path),
        "-vf", f"fps={fps:.8f}",
        "-q:v", "3",
        str(pattern),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFmpeg could not extract video frames.")

    return sorted(output.glob("frame_*.jpg"))


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\x0c", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _is_same_subtitle(first: str, second: str) -> bool:
    if first == second:
        return True
    if not first or not second:
        return False

    ratio = SequenceMatcher(None, first, second).ratio()
    first_words, second_words = set(first.split()), set(second.split())
    union = first_words | second_words
    overlap = len(first_words & second_words) / len(union) if union else 0

    # Short captions need a stricter match to avoid merging unrelated dialogue.
    threshold = 0.82 if min(len(first), len(second)) < 12 else 0.72
    return ratio >= threshold or (len(union) > 0 and overlap >= 0.72)


def read_subtitle(
    image_path: str | Path,
    language: str,
    crop: bool = False,
    tessdata_dir: str | None = None,
) -> str:
    """OCR one frame, applying lightweight preprocessing for better recognition."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")

        if crop:
            width, height = image.size
            image = image.crop((width // 10, (height * 2) // 3, width * 9 // 10, height))

        image = ImageOps.grayscale(image)
        image = ImageOps.autocontrast(image)
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)

        config = "--oem 3 --psm 6"
        if tessdata_dir:
            config += f' --tessdata-dir "{tessdata_dir}"'

        recognized = pytesseract.image_to_string(image, lang=language, config=config)

    return normalize_text(recognized)


class SubtitleCollector:
    """Merge consecutive OCR samples into subtitle cues."""

    def __init__(self, sample_interval_ms: int):
        self.sample_interval_ms = sample_interval_ms
        self.cues: list[tuple[int, int, str]] = []
        self.current_text = ""
        self.current_start: int | None = None
        self.last_seen = 0
        self.pending_empty: int | None = None

    def add(self, timestamp_ms: int, text: str) -> None:
        text = normalize_text(text)

        if not text or len(text) < 2:
            if self.current_text and self.pending_empty is None:
                self.pending_empty = timestamp_ms
            elif self.current_text and self.pending_empty is not None:
                self._finish(self.pending_empty)
            return

        if not self.current_text:
            self._start(timestamp_ms, text)
            return

        if _is_same_subtitle(self.current_text, text):
            self.last_seen = timestamp_ms
            self.pending_empty = None
            # Keep the clearest/most complete OCR variant for the cue.
            if len(text) > len(self.current_text):
                self.current_text = text
            return

        self._finish(timestamp_ms)
        self._start(timestamp_ms, text)

    def _start(self, timestamp_ms: int, text: str) -> None:
        self.current_text = text
        self.current_start = timestamp_ms
        self.last_seen = timestamp_ms
        self.pending_empty = None

    def _finish(self, end_ms: int) -> None:
        if self.current_start is not None and self.current_text:
            start = self.current_start
            end = max(start + self.sample_interval_ms, end_ms)
            if end > start:
                self.cues.append((start, end, self.current_text))
        self.current_text = ""
        self.current_start = None
        self.pending_empty = None

    def close(self, duration_ms: int) -> list[tuple[int, int, str]]:
        if self.current_text:
            end = self.pending_empty if self.pending_empty is not None else min(
                duration_ms, self.last_seen + self.sample_interval_ms
            )
            self._finish(max(end, self.current_start + self.sample_interval_ms))
        return self.cues


def format_timestamp(milliseconds: int) -> str:
    milliseconds = max(0, int(milliseconds))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def write_srt(cues: list[tuple[int, int, str]], output_path: str | Path) -> int:
    with open(output_path, "w", encoding="utf-8-sig", newline="\n") as output:
        for index, (start, end, text) in enumerate(cues, start=1):
            output.write(
                f"{index}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n\n"
            )
    return len(cues)
