"""Text-to-Speech synthesis with graceful engine degradation.

Tries engines in order: chatterbox -> piper -> gTTS -> espeak.
The first available engine is used transparently.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Ordered list of engines to attempt
_ENGINE_PRIORITY = ("chatterbox", "piper", "gtts", "espeak")


class Synthesizer:
    """Text-to-Speech engine with automatic fallback.

    On construction, ``engine="auto"`` (default) probes available
    backends and selects the best one.  You can force a specific
    engine by passing its name.

    Supported engines:
        * ``chatterbox`` — ChatterboxTTS (GPU-accelerated, high quality)
        * ``piper`` — Piper TTS (fast, offline, CPU-friendly)
        * ``gtts`` — Google TTS via ``gTTS`` (requires internet)
        * ``espeak`` — eSpeak NG (always available on Linux)

    Args:
        engine: Engine name or ``"auto"`` for automatic selection.
    """

    def __init__(self, engine: str = "auto") -> None:
        self._requested_engine = engine.lower()
        self._active_engine: str | None = None

        if self._requested_engine != "auto":
            if self._requested_engine not in _ENGINE_PRIORITY:
                raise ValueError(
                    f"Unknown TTS engine '{engine}'. "
                    f"Choose from: {', '.join(_ENGINE_PRIORITY)} or 'auto'."
                )
            self._active_engine = self._requested_engine
            logger.info("TTS engine forced to: %s", self._active_engine)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        output_path: str | None = None,
    ) -> str:
        """Convert text to speech and save as an audio file.

        Args:
            text: The text to speak.
            output_path: Destination path for the audio file.  If None,
                a temporary WAV/MP3 file is created.

        Returns:
            Absolute path to the generated audio file.

        Raises:
            RuntimeError: If no TTS engine is available.
        """
        if not text or not text.strip():
            raise ValueError("Cannot synthesize empty text.")

        engines_to_try: tuple[str, ...]
        if self._active_engine:
            engines_to_try = (self._active_engine,)
        else:
            engines_to_try = _ENGINE_PRIORITY

        last_error: Exception | None = None

        for engine in engines_to_try:
            try:
                method = {
                    "chatterbox": self._try_chatterbox,
                    "piper": self._try_piper,
                    "gtts": self._try_gtts,
                    "espeak": self._try_espeak,
                }[engine]
                result_path = method(text, output_path)
                self._active_engine = engine
                logger.info("TTS synthesis OK via '%s': %s", engine, result_path)
                return result_path
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.debug(
                    "TTS engine '%s' unavailable: %s", engine, exc
                )
                continue

        raise RuntimeError(
            "No TTS engine available. Install at least one of: "
            "chatterbox-tts, piper-tts, gTTS, or espeak-ng. "
            f"Last error: {last_error}"
        )

    # ------------------------------------------------------------------
    # Engine implementations
    # ------------------------------------------------------------------

    def _try_chatterbox(
        self, text: str, output_path: str | None
    ) -> str:
        """Synthesize using ChatterboxTTS (high-quality, GPU-preferred).

        Raises ImportError if the library is not installed.
        """
        try:
            import torch
            from chatterbox.tts import ChatterboxTTS
        except ImportError as exc:
            raise RuntimeError(
                "chatterbox-tts is not installed."
            ) from exc

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = ChatterboxTTS.from_pretrained(device=device)

        wav = model.generate(text)

        path = self._resolve_output_path(output_path, suffix=".wav")
        import torchaudio

        torchaudio.save(path, wav, model.sr)
        return path

    def _try_piper(
        self, text: str, output_path: str | None
    ) -> str:
        """Synthesize using piper-tts CLI.

        Requires the ``piper`` binary to be installed and at least one
        voice model downloaded.
        """
        piper_bin = shutil.which("piper")
        if piper_bin is None:
            raise RuntimeError("piper binary not found in PATH.")

        path = self._resolve_output_path(output_path, suffix=".wav")

        result = subprocess.run(
            [
                piper_bin,
                "--output_file", path,
            ],
            input=text,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"piper failed (rc={result.returncode}): {result.stderr}"
            )
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError("piper produced no output.")
        return path

    def _try_gtts(
        self, text: str, output_path: str | None
    ) -> str:
        """Synthesize using Google TTS (gTTS). Requires internet.

        Raises ImportError if gTTS is not installed.
        """
        try:
            from gtts import gTTS
        except ImportError as exc:
            raise RuntimeError("gTTS is not installed.") from exc

        path = self._resolve_output_path(output_path, suffix=".mp3")

        tts = gTTS(text=text, lang="es")
        tts.save(path)

        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError("gTTS produced no output.")
        return path

    def _try_espeak(
        self, text: str, output_path: str | None
    ) -> str:
        """Synthesize using espeak-ng (always available on Linux).

        Falls back to ``espeak`` if ``espeak-ng`` is not found.
        """
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if binary is None:
            raise RuntimeError(
                "Neither espeak-ng nor espeak found in PATH."
            )

        path = self._resolve_output_path(output_path, suffix=".wav")

        result = subprocess.run(
            [
                binary,
                "-v", "es",  # Spanish voice
                "-w", path,
                text,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"espeak failed (rc={result.returncode}): {result.stderr}"
            )
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError("espeak produced no output.")
        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_output_path(
        output_path: str | None, *, suffix: str
    ) -> str:
        """Return an absolute output path, creating a tempfile if needed."""
        if output_path is not None:
            output_path = os.path.abspath(output_path)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            return output_path

        fd, path = tempfile.mkstemp(suffix=suffix, prefix="tts_")
        os.close(fd)
        return path
