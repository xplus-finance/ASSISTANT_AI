"""Speech-to-Text transcription using faster-whisper.

Provides a lazy-loading Transcriber that auto-detects CPU/GPU
and downloads models on first use.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

VALID_MODEL_SIZES = ("tiny", "base", "small", "medium", "large-v3")


@dataclass(frozen=True)
class TranscriptionResult:
    """Result of a speech-to-text transcription."""

    text: str
    language: str
    duration: float  # audio duration in seconds
    confidence: float  # average log-probability (0.0–1.0 scale)


class Transcriber:
    """Speech-to-Text engine backed by faster-whisper.

    The underlying CTranslate2 model is loaded lazily on first
    ``transcribe()`` call, so construction is cheap.

    Args:
        model_size: Whisper model variant. One of
            ``tiny``, ``base``, ``small``, ``medium``, ``large-v3``.
        device: ``"cpu"``, ``"cuda"``, or ``"auto"`` (default).
            When ``"auto"``, CUDA is used if available.
    """

    def __init__(
        self,
        model_size: str = "medium",
        device: str = "auto",
    ) -> None:
        if model_size not in VALID_MODEL_SIZES:
            raise ValueError(
                f"Invalid model_size '{model_size}'. "
                f"Choose from: {', '.join(VALID_MODEL_SIZES)}"
            )
        self._model_size = model_size
        self._requested_device = device
        self._model = None  # lazy loaded
        self._resolved_device: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe an audio file to text.

        The audio should ideally be 16 kHz mono WAV (use
        ``audio.processor.convert_ogg_to_wav`` first for voice notes).

        Args:
            audio_path: Path to the audio file.

        Returns:
            A ``TranscriptionResult`` with text, detected language,
            audio duration, and average confidence score.

        Raises:
            FileNotFoundError: If the audio file does not exist.
            RuntimeError: If faster-whisper is not installed.
        """
        audio_path = os.path.abspath(audio_path)
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self._ensure_model()

        logger.info(
            "Transcribing %s with model=%s device=%s",
            audio_path,
            self._model_size,
            self._resolved_device,
        )

        segments, info = self._model.transcribe(
            audio_path,
            beam_size=5,
            language=None,  # auto-detect
            vad_filter=True,
        )

        # Materialise segments to collect text and confidence scores
        texts: list[str] = []
        log_probs: list[float] = []
        for segment in segments:
            texts.append(segment.text.strip())
            log_probs.append(segment.avg_logprob)

        full_text = " ".join(texts)

        # Convert average log-probability to a 0–1 confidence heuristic.
        # Log-probs are negative; closer to 0 → higher confidence.
        avg_logprob = (
            sum(log_probs) / len(log_probs) if log_probs else -1.0
        )
        # Clamp to [0, 1] — a logprob of 0 maps to 1.0, -1 maps to ~0.37
        import math

        confidence = round(min(max(math.exp(avg_logprob), 0.0), 1.0), 4)

        result = TranscriptionResult(
            text=full_text,
            language=info.language,
            duration=round(info.duration, 2),
            confidence=confidence,
        )
        logger.info(
            "Transcription complete: lang=%s dur=%.1fs conf=%.2f len=%d",
            result.language,
            result.duration,
            result.confidence,
            len(result.text),
        )
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_device(self) -> str:
        """Determine the compute device to use."""
        if self._requested_device != "auto":
            return self._requested_device

        try:
            import torch

            if torch.cuda.is_available():
                logger.info("CUDA available — using GPU acceleration.")
                return "cuda"
        except ImportError:
            pass

        logger.info("CUDA not available — falling back to CPU.")
        return "cpu"

    def _ensure_model(self) -> None:
        """Load the faster-whisper model if not already loaded.

        Downloads the model from Hugging Face on first invocation.

        Raises:
            RuntimeError: If faster-whisper is not installed.
        """
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Install it with:\n"
                "  pip install faster-whisper"
            ) from exc

        self._resolved_device = self._resolve_device()
        compute_type = "float16" if self._resolved_device == "cuda" else "int8"

        logger.info(
            "Loading Whisper model '%s' on %s (compute=%s). "
            "This may download ~1 GB on first run...",
            self._model_size,
            self._resolved_device,
            compute_type,
        )

        self._model = WhisperModel(
            self._model_size,
            device=self._resolved_device,
            compute_type=compute_type,
        )
        logger.info("Whisper model loaded successfully.")
