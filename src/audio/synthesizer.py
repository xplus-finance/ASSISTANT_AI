"""Text-to-Speech with engine fallback: chatterbox -> piper -> gTTS -> espeak."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_ENGINE_PRIORITY = ("chatterbox", "piper", "gtts", "espeak")

_PITCH_MAP = {
    "low": -4,       # Masculine / grave
    "very_low": -6,
    "normal": 0,
    "high": 3,       # Feminine
    "very_high": 5,
}


class Synthesizer:


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

        self._pitch: str = "low"      # Default: masculine/grave
        self._speed: float = 1.78     # Default: fast, user preference
        self._language: str = "es"

    def set_voice_params(
        self,
        pitch: str | None = None,
        speed: float | None = None,
        language: str | None = None,
    ) -> None:
        if pitch is not None:
            if pitch not in _PITCH_MAP:
                logger.warning("Unknown pitch '%s', using 'normal'", pitch)
                pitch = "normal"
            self._pitch = pitch
        if speed is not None:
            self._speed = max(0.5, min(2.0, speed))
        if language is not None:
            self._language = language
        logger.info(
            "Voice params updated: pitch=%s speed=%.2f lang=%s",
            self._pitch, self._speed, self._language,
        )

    def synthesize(self, text: str, output_path: str | None = None) -> str:
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

                result_path = self._apply_voice_effects(result_path)

                return result_path
            except Exception as exc:
                last_error = exc
                logger.debug("TTS engine '%s' unavailable: %s", engine, exc)
                continue
        raise RuntimeError(
            "No TTS engine available. Install at least one of: "
            "chatterbox-tts, piper-tts, gTTS, or espeak-ng. "
            f"Last error: {last_error}"
        )

    def _apply_voice_effects(self, audio_path: str) -> str:
        pitch_semitones = _PITCH_MAP.get(self._pitch, 0)
        speed = self._speed

        if pitch_semitones == 0 and abs(speed - 1.0) < 0.05:
            return audio_path

        try:
            ffmpeg_bin = shutil.which("ffmpeg")
            ffprobe_bin = shutil.which("ffprobe")
            if not ffmpeg_bin:
                logger.warning("ffmpeg not available, skipping voice effects")
                return audio_path

            source_rate = 44100
            if ffprobe_bin:
                probe = subprocess.run(
                    [ffprobe_bin, "-v", "error", "-select_streams", "a:0",
                     "-show_entries", "stream=sample_rate",
                     "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                    capture_output=True, text=True, timeout=10,
                )
                if probe.returncode == 0 and probe.stdout.strip().isdigit():
                    source_rate = int(probe.stdout.strip())

            suffix = Path(audio_path).suffix or ".wav"
            fd, out_path = tempfile.mkstemp(suffix=suffix, prefix="tts_fx_")
            os.close(fd)

            filters = []

            if abs(speed - 1.0) >= 0.05:
                tempo = max(0.5, min(2.0, speed))
                filters.append(f"atempo={tempo:.3f}")

            if pitch_semitones != 0:
                pitch_factor = 2 ** (pitch_semitones / 12.0)
                new_rate = int(source_rate * pitch_factor)
                filters.append(f"asetrate={new_rate}")
                filters.append(f"aresample={source_rate}")

            if not filters:
                return audio_path

            filter_str = ",".join(filters)
            cmd = [
                ffmpeg_bin, "-y", "-i", audio_path,
                "-af", filter_str,
                out_path,
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )

            if result.returncode != 0:
                logger.warning("ffmpeg voice effects failed: %s", result.stderr[:200])
                return audio_path

            try:
                os.unlink(audio_path)
            except OSError:
                pass

            logger.info(
                "Voice effects applied: pitch=%s (%+d st) speed=%.2f source_rate=%d",
                self._pitch, pitch_semitones, speed, source_rate,
            )
            return out_path

        except Exception as exc:
            logger.warning("Failed to apply voice effects: %s", exc)
            return audio_path

    def _try_chatterbox(self, text: str, output_path: str | None) -> str:
        try:
            import torch
            from chatterbox.tts import ChatterboxTTS
        except ImportError as exc:
            raise RuntimeError("chatterbox-tts is not installed.") from exc
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = ChatterboxTTS.from_pretrained(device=device)
        wav = model.generate(text)
        path = self._resolve_output_path(output_path, suffix=".wav")
        import torchaudio
        torchaudio.save(path, wav, model.sr)
        return path

    def _try_piper(self, text: str, output_path: str | None) -> str:
        piper_bin = shutil.which("piper")
        if piper_bin is None:
            raise RuntimeError("piper binary not found in PATH.")
        path = self._resolve_output_path(output_path, suffix=".wav")
        result = subprocess.run(
            [piper_bin, "--output_file", path],
            input=text, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"piper failed (rc={result.returncode}): {result.stderr}")
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError("piper produced no output.")
        return path

    def _try_gtts(self, text: str, output_path: str | None) -> str:
        try:
            from gtts import gTTS
        except ImportError as exc:
            raise RuntimeError("gTTS is not installed.") from exc
        path = self._resolve_output_path(output_path, suffix=".mp3")
        tts = gTTS(text=text, lang=self._language)
        tts.save(path)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError("gTTS produced no output.")
        return path

    def _try_espeak(self, text: str, output_path: str | None) -> str:
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if binary is None:
            raise RuntimeError("Neither espeak-ng nor espeak found in PATH.")
        path = self._resolve_output_path(output_path, suffix=".wav")

        args = [binary]
        voice = f"{self._language}+m3" if self._pitch in ("low", "very_low") else self._language
        args.extend(["-v", voice])
        wpm = int(175 * self._speed)
        args.extend(["-s", str(wpm)])
        pitch_val = 50 + (_PITCH_MAP.get(self._pitch, 0) * 5)
        pitch_val = max(0, min(99, pitch_val))
        args.extend(["-p", str(pitch_val)])
        args.extend(["-w", path, text])

        result = subprocess.run(
            args, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"espeak failed (rc={result.returncode}): {result.stderr}")
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError("espeak produced no output.")
        return path

    @staticmethod
    def _resolve_output_path(output_path: str | None, *, suffix: str) -> str:
        if output_path is not None:
            output_path = os.path.abspath(output_path)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            return output_path
        fd, path = tempfile.mkstemp(suffix=suffix, prefix="tts_")
        os.close(fd)
        return path
