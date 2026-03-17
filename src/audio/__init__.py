"""Audio processing: format conversion, speech-to-text, text-to-speech."""

from src.audio.processor import (
    convert_ogg_to_wav,
    convert_wav_to_ogg,
    ensure_ffmpeg,
    get_audio_duration,
)
from src.audio.synthesizer import Synthesizer
from src.audio.transcriber import Transcriber, TranscriptionResult

__all__ = [
    "convert_ogg_to_wav",
    "convert_wav_to_ogg",
    "ensure_ffmpeg",
    "get_audio_duration",
    "Synthesizer",
    "Transcriber",
    "TranscriptionResult",
]
