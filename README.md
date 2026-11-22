# Video Subtitle Extractor Bot

A Telegram bot that extracts hard-coded (burned-in) subtitles from videos and exports them as an SRT file using FFmpeg with Tesseract OCR and optional Google Lens OCR.

## Included

- Extracts sampled frames with **one FFmpeg process**, instead of launching FFmpeg separately for every frame.
- Uses a configurable sampling interval (default: 500 ms / 2 frames per second).
- Reuses a thread-local Tesseract OCR engine between frames, avoiding repeated engine initialization and allowing native OCR work to run without holding Python's GIL.
- Uses prebuilt `tesserocr` wheels that bundle Tesseract and Leptonica on supported platforms; no separate Tesseract executable installation is needed there.
- Downloads the selected Tesseract language data automatically when missing.
- Compares consecutive sampled frames with a lightweight SSIM implementation and skips OCR only for virtually identical frames, reusing the previous reading so subtitle timing remains continuous.
- Uses Tesseract's page-level confidence to prefer the strongest OCR reading when multiple similar readings belong to the same subtitle cue. Google Lens readings are also supported as an optional alternative engine.
- Can automatically download and install the selected Google Lens CLI at startup; its binary and the small 7-Zip Python helper are installed only when that engine is selected.
- Normalizes OCR output and compares nearby samples using text similarity, reducing duplicate subtitle cues.
- Builds subtitle start/end times from sampled frame timestamps.
- Uses a separate temporary workspace for each chat, so simultaneous users do not overwrite each other's files.
- Adds /cancel support and automatic cleanup of temporary files.
- Adds tests for subtitle grouping and SRT formatting.

OCR accuracy still depends on subtitle size, contrast, font, language data, and video quality. This bot extracts hard-coded subtitles; it does not extract selectable subtitle tracks embedded in a video container.

## Requirements

- Python 3.10+
- A platform supported by `static-ffmpeg` (it downloads FFmpeg and ffprobe automatically on first startup)
- A platform/Python combination supported by a prebuilt `tesserocr` wheel when using Tesseract
- if deploying is on Linux, requires glibc 2.35+ when using Google Lens.

Install Python dependencies:

```bash
pip install -r requirements.txt
```

The `tesserocr` wheel bundles the Tesseract engine and its native runtime dependencies for supported Linux, macOS, and 64-bit Windows builds. If pip cannot find a compatible wheel, installation may attempt a source build that requires Tesseract and Leptonica development libraries.

`static-ffmpeg` downloads the matching FFmpeg 8.0 and ffprobe binaries on the first bot startup, then adds their directory to `PATH`. You do not need to install FFmpeg separately.
Run locally:

```bash
python main.py
```

## Environment variables

| Variable | Required | Default | Description |
|---|---:|---|---|
| `BOT_TOKEN` | Yes | — | Telegram bot token from @BotFather |
| `API_ID` | Yes | — | Telegram API ID from my.telegram.org |
| `API_HASH` | Yes | — | Telegram API hash from my.telegram.org |
| `OCR_ENGINE` | No | `google_lens` | OCR engine: `tesseract` or `google_lens` |
| `SUBTITLE_LANG` | No | `fas` | Language code for the selected OCR engine. Tesseract codes are converted to BCP-47 for Google Lens (for example `fas` → `fa`, `eng` → `en`). |
| `OCR_INTERVAL_MS` | No | `500` | Time between sampled frames in milliseconds; minimum 100 |\n| `FRAME_SSIM_THRESHOLD` | No | `0.997` | Similarity threshold (0.0–1.0) for skipping OCR on virtually identical consecutive frames; set to `1.0` to disable |
| `USE_CROP` | No | disabled | Set to `1` to focus OCR on the lower subtitle region |
| `TESSDATA_DIR` | No | `./tessdata` | Directory used for Tesseract language data |

The Tesseract language file is downloaded automatically when Tesseract is selected. It is not downloaded when Google Lens is selected.

### Selecting OCR ENGINE

Google Lens is selected by default. To use Tesseract instead, set `OCR_ENGINE=tesseract` in the deployment environment and restart the bot. At startup, the bot downloads the latest Chrome-Lens-OCR release, verifies its SHA-256 digest when GitHub provides one, extracts it, and checks that the CLI executable is present before accepting Telegram messages. The small `py7zip` helper is installed on demand only if it is not already available. The Google Lens binary is cached under `plugins/google_lens` and the downloaded archive under `.plugin_cache`.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Source

Original project: https://github.com/samadii/VidSubExtract-Bot
