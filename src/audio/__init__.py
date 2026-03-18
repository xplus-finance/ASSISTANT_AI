"""Audio processing: format conversion, speech-to-text, text-to-speech."""

try:
    from src.audio.processor import (
        convert_ogg_to_wav,
        convert_wav_to_ogg,
        ensure_ffmpeg,
        get_audio_duration,
    )
except Exception:  # pydub/audioop missing on Python 3.13+
    convert_ogg_to_wav = None  # type: ignore[assignment]
    convert_wav_to_ogg = None  # type: ignore[assignment]
    ensure_ffmpeg = None  # type: ignore[assignment]
    get_audio_duration = None  # type: ignore[assignment]

try:
    from src.audio.synthesizer import Synthesizer
except Exception:
    Synthesizer = None  # type: ignore[assignment]

try:
    from src.audio.transcriber import Transcriber, TranscriptionResult
except Exception:
    Transcriber = None  # type: ignore[assignment]
    TranscriptionResult = None  # type: ignore[assignment]

__all__ = [
    "convert_ogg_to_wav",
    "convert_wav_to_ogg",
    "ensure_ffmpeg",
    "get_audio_duration",
    "Synthesizer",
    "Transcriber",
    "TranscriptionResult",
]
