from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

GITHUB_RELEASE_API = "https://api.github.com/repos/timminator/Chrome-Lens-OCR/releases/latest"
PY7ZIP_WHEEL = (
    "https://github.com/aliasfoxkde/py7zip/releases/download/v0.8.0/"
    "py7zip-0.8.0-py3-none-any.whl"
)
PLUGIN_DIR = Path(__file__).parent / "plugins" / "google_lens"
CACHE_DIR = Path(__file__).parent / ".plugin_cache"
ASSET_PREFIX = "Chrome-Lens-OCR-"
USER_AGENT = "VidSubExtract-Bot"


def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_file(url: str, destination: Path, expected_size: int, expected_digest: str | None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            downloaded = 0
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)

        if downloaded != expected_size:
            raise RuntimeError(
                f"Google Lens download is incomplete: {downloaded}/{expected_size} bytes."
            )

        if expected_digest and expected_digest.startswith("sha256:"):
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if digest.lower() != expected_digest.split(":", 1)[1].lower():
                raise RuntimeError("Google Lens archive failed its SHA-256 integrity check.")

        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _get_py7zip():
    try:
        module = importlib.import_module("py7zip")
    except ImportError:
        print("Installing the small py7zip helper required to unpack Google Lens…", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", PY7ZIP_WHEEL],
            check=True,
        )
        importlib.invalidate_caches()
        module = importlib.import_module("py7zip")

    if not hasattr(module, "Py7zip"):
        raise RuntimeError(
            "The installed py7zip package does not expose Py7zip(). "
            "The pinned 0.8.0 wheel is required to extract the Google Lens archive."
        )
    return module.Py7zip()


def _find_executable() -> Path | None:
    if not PLUGIN_DIR.exists():
        return None

    candidates = [
        path for path in PLUGIN_DIR.rglob("*")
        if path.is_file() and path.name.lower() in {"chrome-lens.bin", "chrome-lens"}
    ]
    if not candidates:
        return None

    executable = candidates[0]
    if platform.system() != "Windows":
        executable.chmod(executable.stat().st_mode | 0o111)
    return executable


def prepare_google_lens() -> Path:
    """Download, extract, and verify the latest Linux Google Lens CLI."""
    existing = _find_executable()
    if existing:
        print(f"[ready] Google Lens CLI: {existing}", flush=True)
        return existing

    print("Preparing optional Google Lens OCR engine…", flush=True)
    release = _request_json(GITHUB_RELEASE_API)
    system = platform.system()

    if system != "Linux":
        raise RuntimeError(
            f"Google Lens prebuilt CLI is currently supported only on Linux, not {system}."
        )
    suffix = "-Linux.7z"

    assets = release.get("assets", [])
    asset = next(
        (
            item for item in assets
            if item.get("name", "").startswith(ASSET_PREFIX)
            and item.get("name", "").endswith(suffix)
        ),
        None,
    )
    if not asset:
        raise RuntimeError(
            f"No Google Lens CLI archive was found for {system} in release "
            f"{release.get('tag_name', 'latest')}."
        )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive = CACHE_DIR / asset["name"]
    if not archive.exists() or archive.stat().st_size != int(asset["size"]):
        print(
            f"[download] Google Lens CLI {release.get('tag_name', '')} "
            f"({int(asset['size']) / (1024 * 1024):.1f} MB)…",
            flush=True,
        )
        _download_file(
            asset["browser_download_url"],
            archive,
            int(asset["size"]),
            asset.get("digest"),
        )

    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    print("[extract] Google Lens CLI…", flush=True)
    extractor = _get_py7zip()
    extractor.decompress(str(archive), str(PLUGIN_DIR))

    executable = _find_executable()
    if not executable:
        raise RuntimeError(
            "Google Lens archive was extracted, but chrome-lens.bin/chrome-lens "
            "could not be found."
        )

    print(f"[ready] Google Lens CLI installed: {executable}", flush=True)
    return executable


def parse_google_lens_output(output: str) -> str:
    """Extract recognized words from the JSON format emitted by VideOCR's Lens CLI."""
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        words = data.get("words")
        if isinstance(words, list):
            parts = []
            for item in words:
                if not isinstance(item, dict):
                    continue
                word = str(item.get("text") or "")
                separator = str(item.get("separator") or "")
                parts.append(word + separator)
            text = "".join(parts).strip()
            if text:
                return " ".join(text.split())

        text = data.get("ocr_text")
        if isinstance(text, str) and text.strip():
            return " ".join(text.split())

    return ""


def read_google_lens_subtitle(
    image_path: str | Path,
    language: str = "fa",
    crop: bool = False,
) -> tuple[str, float]:
    """Run Google Lens OCR on one sampled frame and return text plus a compatible score."""
    executable = _find_executable()
    if not executable:
        raise RuntimeError("Google Lens CLI is not installed. Select OCR_ENGINE=google_lens at startup.")

    source_path = Path(image_path)
    lens_image = source_path
    temporary_image: Path | None = None

    try:
        if crop:
            with Image.open(source_path) as source:
                image = source.convert("RGB")
                width, height = image.size
                image = image.crop((width // 10, (height * 2) // 3, width * 9 // 10, height))
                temporary_image = source_path.with_name(source_path.stem + ".google_lens.jpg")
                image.save(temporary_image, format="JPEG", quality=95)
                lens_image = temporary_image

        command = [
            str(executable),
            str(lens_image),
            language,
            "--get-coords",
            "--oneline",
            "-q",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=90,
            cwd=str(executable.parent),
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                f"Google Lens OCR failed (exit {result.returncode}): "
                f"{details[-1200:] or 'no error output'}"
            )

        recognized = parse_google_lens_output(result.stdout)
        if not recognized and result.stdout.strip() and not result.stdout.lstrip().startswith("{"):
            # Some CLI builds print plain text instead of the structured JSON form.
            recognized = " ".join(result.stdout.split())

        return recognized, 100.0 if recognized else 0.0
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Google Lens OCR timed out while processing a frame.") from error
    finally:
        if temporary_image and temporary_image.exists():
            temporary_image.unlink()
