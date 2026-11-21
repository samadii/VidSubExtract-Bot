# Video Subtitle Extractor Bot

A Telegram bot that extracts hard-coded (burned-in) subtitles from videos and exports them as an SRT file using FFmpeg and Tesseract OCR.

## Improvements in this branch

- Extracts sampled frames with **one FFmpeg process**, instead of launching FFmpeg separately for every frame.
- Uses a configurable sampling interval (default: 500 ms / 2 frames per second).
- Reuses a thread-local Tesseract OCR engine between frames, avoiding repeated engine initialization and allowing native OCR work to run without holding Python's GIL.
- Uses prebuilt `tesserocr` wheels that bundle Tesseract and Leptonica on supported platforms; no separate Tesseract executable installation is needed there.
- Downloads the selected Tesseract language data automatically when missing.
- Normalizes OCR output and compares nearby samples using text similarity, reducing duplicate subtitle cues.
- Builds subtitle start/end times from sampled frame timestamps.
- Uses a separate temporary workspace for each chat, so simultaneous users do not overwrite each other's files.
- Adds /cancel support and automatic cleanup of temporary files.
- Adds tests for subtitle grouping and SRT formatting.

OCR accuracy still depends on subtitle size, contrast, font, language data, and video quality. This bot extracts hard-coded subtitles; it does not extract selectable subtitle tracks embedded in a video container.

## Requirements

- Python 3.10+
- FFmpeg (including ffprobe)
- A platform/Python combination supported by a prebuilt `tesserocr` wheel

Install Python dependencies:

```bash
pip install -r requirements.txt
```

The `tesserocr` wheel bundles the Tesseract engine and its native runtime dependencies for supported Linux, macOS, and 64-bit Windows builds. If pip cannot find a compatible wheel, installation may attempt a source build that requires Tesseract and Leptonica development libraries.

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
| `SUBTITLE_LANG` | No | `fas` | Tesseract language code, for example `eng` or `fas` |
| `OCR_INTERVAL_MS` | No | `500` | Time between sampled frames in milliseconds; minimum 100 |
| `USE_CROP` | No | disabled | Set to `1` to focus OCR on the lower subtitle region |
| `TESSDATA_DIR` | No | `./tessdata` | Directory used for Tesseract language data |

The required Tesseract language file is downloaded automatically on first run. Language data is still required even though the OCR engine is bundled in the wheel.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Deployment

The repository includes a Procfile and Heroku app configuration. Make sure the deployment environment has FFmpeg (including ffprobe) installed.

## Source

Original project: https://github.com/samadii/VidSubExtract-Bot
