"""Speech-to-Text via faster-whisper with lazy model loading."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

VALID_MODEL_SIZES = ("tiny", "base", "small", "medium", "large-v3")


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    duration: float
    confidence: float


class Transcriber:


    def __init__(self, model_size: str = "medium", device: str = "auto") -> None:
        if model_size not in VALID_MODEL_SIZES:
            raise ValueError(
                f"Invalid model_size '{model_size}'. "
                f"Choose from: {', '.join(VALID_MODEL_SIZES)}"
            )
        self._model_size = model_size
        self._requested_device = device
        self._model = None
        self._resolved_device: str | None = None

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        audio_path = os.path.abspath(audio_path)
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        self._ensure_model()
        logger.info("Transcribing %s with model=%s device=%s", audio_path, self._model_size, self._resolved_device)
        segments, info = self._model.transcribe(audio_path, beam_size=5, language=None, vad_filter=True)
        texts: list[str] = []
        log_probs: list[float] = []
        for segment in segments:
            texts.append(segment.text.strip())
            log_probs.append(segment.avg_logprob)
        full_text = " ".join(texts)
        avg_logprob = sum(log_probs) / len(log_probs) if log_probs else -1.0
        import math
        confidence = round(min(max(math.exp(avg_logprob), 0.0), 1.0), 4)
        result = TranscriptionResult(text=full_text, language=info.language, duration=round(info.duration, 2), confidence=confidence)
        logger.info("Transcription complete: lang=%s dur=%.1fs conf=%.2f len=%d", result.language, result.duration, result.confidence, len(result.text))
        return result

    def _resolve_device(self) -> str:
        if self._requested_device != "auto":
            return self._requested_device
        try:
            import torch
            if torch.cuda.is_available():
                logger.info("CUDA available \u2014 using GPU acceleration.")
                return "cuda"
        except ImportError:
            pass
        logger.info("CUDA not available \u2014 falling back to CPU.")
        return "cpu"

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is not installed. Install it with:\n  pip install faster-whisper") from exc
        self._resolved_device = self._resolve_device()
        compute_type = "float16" if self._resolved_device == "cuda" else "int8"
        logger.info("Loading Whisper model '%s' on %s (compute=%s). This may download ~1 GB on first run...", self._model_size, self._resolved_device, compute_type)
        self._model = WhisperModel(self._model_size, device=self._resolved_device, compute_type=compute_type)
        logger.info("Whisper model loaded successfully.")
