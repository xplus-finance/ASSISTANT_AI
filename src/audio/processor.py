"""Audio format conversion utilities using pydub and ffmpeg.

Handles OGG/Opus <-> WAV conversion required for Whisper STT
and voice note sending across messaging channels.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Whisper expects 16kHz mono WAV
WHISPER_SAMPLE_RATE = 16000
WHISPER_CHANNELS = 1


def ensure_ffmpeg() -> bool:
    """Check if ffmpeg is installed and accessible.

    Returns:
        True if ffmpeg is available, False otherwise.
    """
    return shutil.which("ffmpeg") is not None


def convert_ogg_to_wav(
    input_path: str,
    output_path: str | None = None,
) -> str:
    """Convert OGG/Opus audio to WAV 16kHz mono (Whisper-compatible).

    Args:
        input_path: Path to the input OGG/Opus file.
        output_path: Path for the output WAV file. If None, a temporary
            file is created in the system temp directory.

    Returns:
        Absolute path to the generated WAV file.

    Raises:
        FileNotFoundError: If the input file does not exist.
        RuntimeError: If ffmpeg is not installed.
        Exception: If pydub/ffmpeg conversion fails.
    """
    input_path = os.path.abspath(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not ensure_ffmpeg():
        raise RuntimeError(
            "ffmpeg is not installed. Install it with: "
            "sudo apt install ffmpeg"
        )

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".wav", prefix="audio_")
        os.close(fd)
    else:
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

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
        # Clean up partial output on failure
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
    """Convert WAV audio to OGG/Opus (for sending voice notes).

    Args:
        input_path: Path to the input WAV file.
        output_path: Path for the output OGG file. If None, a temporary
            file is created in the system temp directory.

    Returns:
        Absolute path to the generated OGG file.

    Raises:
        FileNotFoundError: If the input file does not exist.
        RuntimeError: If ffmpeg is not installed.
        Exception: If pydub/ffmpeg conversion fails.
    """
    input_path = os.path.abspath(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not ensure_ffmpeg():
        raise RuntimeError(
            "ffmpeg is not installed. Install it with: "
            "sudo apt install ffmpeg"
        )

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".ogg", prefix="audio_")
        os.close(fd)
    else:
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        # Auto-detect input format (works with WAV, MP3, etc.)
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
    """Return the duration of an audio file in seconds.

    Uses ffprobe for accuracy when available, falls back to pydub.

    Args:
        path: Path to the audio file.

    Returns:
        Duration in seconds as a float.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Audio file not found: {path}")

    # Try ffprobe first — more accurate and doesn't load the whole file
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

    # Fallback to pydub
    audio = AudioSegment.from_file(path)
    return len(audio) / 1000.0
