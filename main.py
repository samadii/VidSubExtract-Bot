from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from display_progress import progress_for_pyrogram
from subtitle_extractor import SubtitleCollector, extract_frames, read_subtitle, write_srt


BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
LANG = os.environ.get("SUBTITLE_LANG", "fas").strip() or "fas"
USE_CROP = os.environ.get("USE_CROP", "").strip().lower() in {"1", "true", "yes", "on"}
OCR_INTERVAL_MS = max(100, int(os.environ.get("OCR_INTERVAL_MS", "500")))
TESSDATA_DIR = Path(os.environ.get("TESSDATA_DIR", str(Path(__file__).parent / "tessdata")))

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise RuntimeError("BOT_TOKEN, API_ID and API_HASH environment variables are required.")

Bot = Client(
    "VidSubExtract-Bot",
    bot_token=BOT_TOKEN,
    api_id=int(API_ID),
    api_hash=API_HASH,
)

START_TEXT = (
    "Hi {mention}!\n"
    "I can extract hard-coded subtitles from videos and create an SRT file.\n\n"
    "Send me a video to get started.\n"
    "Use /cancel to stop an active extraction."
)
START_BUTTONS = InlineKeyboardMarkup(
    [[InlineKeyboardButton("Source Code", url="https://github.com/Soebb/VidSubExtract-Bot")]]
)

# Each chat gets its own workspace and cancellation event.
ACTIVE_JOBS: dict[int, asyncio.Event] = {}


def ensure_tessdata() -> None:
    TESSDATA_DIR.mkdir(parents=True, exist_ok=True)
    traineddata = TESSDATA_DIR / f"{LANG}.traineddata"
    if traineddata.exists() and traineddata.stat().st_size > 0:
        return

    url = f"https://github.com/tesseract-ocr/tessdata/raw/main/{LANG}.traineddata"
    response = requests.get(url, timeout=60, headers={"User-Agent": "VidSubExtract-Bot"})
    response.raise_for_status()
    if not response.content:
        raise RuntimeError(f"Tesseract language data for '{LANG}' is empty.")
    traineddata.write_bytes(response.content)


def get_video_duration(video_path: str) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe was not found. Install FFmpeg and make sure it is in PATH.")

    process = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,duration",
            "-of", "json", video_path,
        ],
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "Could not read video duration.")

    try:
        import json
        metadata = json.loads(process.stdout)
        raw_duration = metadata.get("format", {}).get("duration")
        if not raw_duration:
            raw_duration = next(
                stream.get("duration")
                for stream in metadata.get("streams", [])
                if stream.get("codec_type") == "video" and stream.get("duration")
            )
        duration = float(raw_duration)
    except (ValueError, KeyError, StopIteration, TypeError) as error:
        raise RuntimeError("Could not determine the video duration.") from error

    if duration <= 0:
        raise RuntimeError("The video has an invalid duration.")
    return duration


def display_name(message) -> str:
    media = message.video or message.document
    original = getattr(media, "file_name", None)
    stem = Path(original).stem if original else f"video_{message.id}"
    return re.sub(r"[^\w.-]+", "_", stem).strip("._") or f"video_{message.id}"


@Bot.on_message(filters.command("start"))
async def start(_, message):
    mention = message.from_user.mention if message.from_user else "there"
    await message.reply_text(
        START_TEXT.format(mention=mention),
        reply_markup=START_BUTTONS,
        disable_web_page_preview=True,
    )


@Bot.on_message(filters.command("cancel") & filters.private)
async def cancel(_, message):
    event = ACTIVE_JOBS.get(message.chat.id)
    if event:
        event.set()
        await message.reply_text("Cancellation requested. The current step will stop shortly.")
    else:
        await message.reply_text("There is no active extraction to cancel.")


@Bot.on_message(filters.private & (filters.video | filters.document))
async def extract_video(client, message):
    if message.document and not (message.document.mime_type or "").startswith("video/"):
        return

    chat_id = message.chat.id
    if chat_id in ACTIVE_JOBS:
        await message.reply_text("An extraction is already running in this chat. Send /cancel first.")
        return

    job_cancel = asyncio.Event()
    ACTIVE_JOBS[chat_id] = job_cancel
    status = await message.reply_text("Downloading video…")
    work_dir = None

    try:
        work_dir = tempfile.mkdtemp(prefix=f"vidsub_{chat_id}_")
        video_path = await client.download_media(
            message,
            file_name=str(Path(work_dir) / "input_video"),
            progress=progress_for_pyrogram,
            progress_args=("Downloading…", status, time.time()),
        )
        if not video_path:
            raise RuntimeError("Telegram did not return a downloaded video file.")

        if job_cancel.is_set():
            await status.edit_text("Extraction cancelled.")
            return

        await status.edit_text("Preparing OCR language data…")
        await asyncio.to_thread(ensure_tessdata)

        duration = await asyncio.to_thread(get_video_duration, video_path)
        duration_ms = int(duration * 1000)
        frames_dir = Path(work_dir) / "frames"

        await status.edit_text("Extracting frames with FFmpeg…")
        frames = await asyncio.to_thread(
            extract_frames, video_path, str(frames_dir), OCR_INTERVAL_MS
        )
        if not frames:
            raise RuntimeError("FFmpeg did not produce any frames.")

        collector = SubtitleCollector(OCR_INTERVAL_MS)
        total = len(frames)
        last_update = 0.0

        for index, frame_path in enumerate(frames):
            if job_cancel.is_set():
                await status.edit_text("Extraction cancelled.")
                return

            timestamp_ms = index * OCR_INTERVAL_MS
            text = await asyncio.to_thread(
                read_subtitle, frame_path, LANG, USE_CROP, str(TESSDATA_DIR)
            )
            collector.add(timestamp_ms, text)

            now = time.monotonic()
            if now - last_update >= 5 or index + 1 == total:
                percentage = (index + 1) * 100 / total
                try:
                    await status.edit_text(
                        f"Recognizing subtitles… {percentage:.1f}% "
                        f"({index + 1}/{total} frames)"
                    )
                except Exception:
                    pass
                last_update = now

        if job_cancel.is_set():
            await status.edit_text("Extraction cancelled.")
            return

        cues = collector.close(duration_ms)
        if not cues:
            await status.edit_text("No readable subtitles were detected in this video.")
            return

        output_path = Path(work_dir) / f"{display_name(message)}.srt"
        write_srt(cues, output_path)

        await client.send_document(
            chat_id=chat_id,
            document=str(output_path),
            file_name=f"{display_name(message)}.srt",
            caption=f"Subtitle extraction completed. Found {len(cues)} subtitle cues.",
        )
        await status.delete()

    except Exception as error:
        try:
            await status.edit_text(f"Extraction failed: {error}")
        except Exception:
            await message.reply_text(f"Extraction failed: {error}")
    finally:
        ACTIVE_JOBS.pop(chat_id, None)
        if work_dir and Path(work_dir).exists():
            shutil.rmtree(work_dir, ignore_errors=True)


Bot.run()
