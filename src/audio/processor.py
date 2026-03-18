"""Audio format conversion using pydub and ffmpeg."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from pydub import AudioSegment
    _PYDUB_OK = True
except ImportError:
    AudioSegment = None  # type: ignore[assignment]
    _PYDUB_OK = False

logger = logging.getLogger(__name__)

WHISPER_SAMPLE_RATE = 16000
WHISPER_CHANNELS = 1


def ensure_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def convert_ogg_to_wav(
    input_path: str,
    output_path: str | None = None,
) -> str:
    """Convert OGG/Opus to WAV 16kHz mono for Whisper."""
    input_path = os.path.abspath(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not ensure_ffmpeg():
        raise RuntimeError(
            "ffmpeg is not installed. Install it with: "
            "winget install ffmpeg (Windows), brew install ffmpeg (macOS), "
            "or sudo apt install ffmpeg (Linux)"
        )

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="audio_")
        os.close(fd)
    else:
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not _PYDUB_OK:
        raise RuntimeError(
            "pydub is not available (Python 3.13+: install pyaudioop). "
            "Run: pip install pyaudioop"
        )

    try:
        audio = AudioSegment.from_file(input_path, format="ogg")
        audio = audio.set_frame_rate(WHISPER_SAMPLE_RATE).set_channels(
            WHISPER_CHANNELS
        )
        audio.export(output_path, format="wav")
        logger.debug(
            "Converted OGG -> WAV: %s -> %s (%.1fs)",
            input_path,
            output_path,
            len(audio) / 1000.0,
        )
        return output_path
    except Exception:
        if os.path.isfile(output_path):
            try:
                os.unlink(output_path)
            except OSError:
                pass
        raise


def convert_wav_to_ogg(
    input_path: str,
    output_path: str | None = None,
) -> str:
    """Convert WAV to OGG/Opus for voice note sending."""
    input_path = os.path.abspath(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not ensure_ffmpeg():
        raise RuntimeError(
            "ffmpeg is not installed. Install it with: "
            "winget install ffmpeg (Windows), brew install ffmpeg (macOS), "
            "or sudo apt install ffmpeg (Linux)"
        )

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".ogg", prefix="audio_")
        os.close(fd)
    else:
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not _PYDUB_OK:
        raise RuntimeError(
            "pydub is not available (Python 3.13+: install pyaudioop). "
            "Run: pip install pyaudioop"
        )

    try:
        audio = AudioSegment.from_file(input_path)
        audio.export(output_path, format="ogg", codec="libopus")
        logger.debug(
            "Converted WAV -> OGG: %s -> %s (%.1fs)",
            input_path,
            output_path,
            len(audio) / 1000.0,
        )
        return output_path
    except Exception:
        if os.path.isfile(output_path):
            try:
                os.unlink(output_path)
            except OSError:
                pass
        raise


def get_audio_duration(path: str) -> float:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Audio file not found: {path}")

    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError):
            pass

    if not _PYDUB_OK:
        raise RuntimeError("pydub not available and ffprobe failed. Install pyaudioop.")
    audio = AudioSegment.from_file(path)
    return len(audio) / 1000.0
