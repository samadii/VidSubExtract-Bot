from __future__ import annotations

import re
import subprocess
import threading
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageChops, ImageOps, ImageStat
from tesserocr import PyTessBaseAPI, PSM


# A separate Tesseract API instance per executor thread. Reusing it avoids
# initializing the OCR engine for every sampled frame without sharing the
# non-thread-safe API object between threads.
_OCR_LOCAL = threading.local()


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
    return re.sub(r"\s+", " ", value).strip()


def _prepare_ocr_image(source: Image.Image, crop: bool) -> Image.Image:
    image = source.convert("RGB")
    if crop:
        width, height = image.size
        image = image.crop((width // 10, (height * 2) // 3, width * 9 // 10, height))

    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image)
    return image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)


def _comparison_image(image_path: str | Path, crop: bool) -> Image.Image:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
    if crop:
        width, height = image.size
        image = image.crop((width // 10, (height * 2) // 3, width * 9 // 10, height))
    return ImageOps.grayscale(image).resize((96, 54), Image.Resampling.BILINEAR)


def structural_similarity(first_path: str | Path, second_path: str | Path, crop: bool = False) -> float:
    """Return a lightweight SSIM score (0..1) for consecutive sampled frames."""
    first = _comparison_image(first_path, crop)
    second = _comparison_image(second_path, crop)
    mean_a = ImageStat.Stat(first).mean[0] / 255.0
    mean_b = ImageStat.Stat(second).mean[0] / 255.0
    var_a = ImageStat.Stat(first).stddev[0] ** 2 / (255.0 ** 2)
    var_b = ImageStat.Stat(second).stddev[0] ** 2 / (255.0 ** 2)
    product_mean = ImageStat.Stat(ImageChops.multiply(first, second)).mean[0] / 255.0
    covariance = product_mean - mean_a * mean_b

    c1 = 0.01 ** 2
    c2 = 0.03 ** 2
    numerator = (2 * mean_a * mean_b + c1) * (2 * covariance + c2)
    denominator = (mean_a ** 2 + mean_b ** 2 + c1) * (var_a + var_b + c2)
    if denominator == 0:
        return 1.0 if first.tobytes() == second.tobytes() else 0.0
    return max(-1.0, min(1.0, numerator / denominator))


def _is_same_subtitle(first: str, second: str) -> bool:
    if first == second:
        return True
    if not first or not second:
        return False

    ratio = SequenceMatcher(None, first, second).ratio()
    first_words, second_words = set(first.split()), set(second.split())
    union = first_words | second_words
    overlap = len(first_words & second_words) / len(union) if union else 0

    threshold = 0.82 if min(len(first), len(second)) < 12 else 0.72
    return ratio >= threshold or (bool(union) and overlap >= 0.72)


def _get_ocr_api(language: str, tessdata_dir: str | None):
    cache_key = (language, str(Path(tessdata_dir).resolve()) if tessdata_dir else None)
    cached_key = getattr(_OCR_LOCAL, "cache_key", None)
    api = getattr(_OCR_LOCAL, "api", None)

    if api is None or cached_key != cache_key:
        if api is not None:
            api.End()
        api = PyTessBaseAPI(
            path=cache_key[1],
            lang=language,
            psm=PSM.SINGLE_BLOCK,
        )
        _OCR_LOCAL.api = api
        _OCR_LOCAL.cache_key = cache_key

    return api


def read_subtitle_result(
    image_path: str | Path,
    language: str,
    crop: bool = False,
    tessdata_dir: str | None = None,
) -> tuple[str, float]:
    """Return normalized OCR text and Tesseract's page-level confidence (0..100)."""
    with Image.open(image_path) as source:
        image = _prepare_ocr_image(source, crop)

    api = _get_ocr_api(language, tessdata_dir)
    api.SetImage(image)
    text = normalize_text(api.GetUTF8Text())
    try:
        confidence = float(api.MeanTextConf())
    except (AttributeError, TypeError, ValueError):
        confidence = 0.0
    return text, max(0.0, min(100.0, confidence))


def read_subtitle(
    image_path: str | Path,
    language: str,
    crop: bool = False,
    tessdata_dir: str | None = None,
) -> str:
    """Backward-compatible text-only OCR helper."""
    return read_subtitle_result(image_path, language, crop, tessdata_dir)[0]


class SubtitleCollector:
    """Merge consecutive OCR samples and retain the strongest reading per cue."""

    def __init__(self, sample_interval_ms: int):
        self.sample_interval_ms = sample_interval_ms
        self.cues: list[tuple[int, int, str]] = []
        self.current_text = ""
        self.current_confidence = -1.0
        self.current_start: int | None = None
        self.last_seen = 0
        self.pending_empty: int | None = None

    def add(self, timestamp_ms: int, text: str, confidence: float = 0.0) -> None:
        text = normalize_text(text)

        if not text or len(text) < 2:
            if self.current_text and self.pending_empty is None:
                self.pending_empty = timestamp_ms
            elif self.current_text and self.pending_empty is not None:
                self._finish(self.pending_empty)
            return

        if not self.current_text:
            self._start(timestamp_ms, text, confidence)
            return

        if _is_same_subtitle(self.current_text, text):
            self.last_seen = timestamp_ms
            self.pending_empty = None
            # Prefer the reading with the higher OCR confidence. On a tie,
            # prefer the more complete text rather than blindly taking the
            # latest frame.
            if confidence > self.current_confidence or (
                confidence == self.current_confidence and len(text) > len(self.current_text)
            ):
                self.current_text = text
                self.current_confidence = confidence
            return

        end_ms = self.pending_empty if self.pending_empty is not None else timestamp_ms
        self._finish(end_ms)
        self._start(timestamp_ms, text, confidence)

    def _start(self, timestamp_ms: int, text: str, confidence: float = 0.0) -> None:
        self.current_text = text
        self.current_confidence = confidence
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
        self.current_confidence = -1.0
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
