"""Multi-model LLM abstraction with fallback chain.

Supports:
- Claude Code CLI (primary, existing)
- OpenAI API (GPT-4o, GPT-4o-mini, etc.)
- Ollama (local models: llama3, mistral, etc.)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

log = structlog.get_logger("assistant.core.llm_bridge")


class LLMBackend:
    """Abstract base for LLM backends."""

    name: str = "base"

    async def ask(self, prompt: str, system_prompt: str = "", timeout: int = 120) -> str:
        raise NotImplementedError

    async def is_available(self) -> bool:
        raise NotImplementedError


class OpenAIBackend(LLMBackend):
    """OpenAI API backend (GPT-4o, GPT-4o-mini, etc.)."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    async def ask(self, prompt: str, system_prompt: str = "", timeout: int = 120) -> str:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: pip install openai")

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
        )

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=4096,
                ),
                timeout=timeout,
            )
            content = response.choices[0].message.content or ""
            log.debug("openai_backend.response", model=self._model, length=len(content))
            return content
        except asyncio.TimeoutError:
            raise RuntimeError(f"OpenAI timeout after {timeout}s")
        except Exception as exc:
            raise RuntimeError(f"OpenAI error: {exc}") from exc

    async def is_available(self) -> bool:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
            models = await asyncio.wait_for(client.models.list(), timeout=10)
            return True
        except Exception:
            return False


class OllamaBackend(LLMBackend):
    """Ollama local model backend."""

    name = "ollama"

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def ask(self, prompt: str, system_prompt: str = "", timeout: int = 120) -> str:
        import aiohttp

        url = f"{self._base_url}/api/chat"
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise RuntimeError(f"Ollama HTTP {resp.status}: {body[:200]}")
                    data = await resp.json()
                    content = data.get("message", {}).get("content", "")
                    log.debug("ollama_backend.response", model=self._model, length=len(content))
                    return content
        except asyncio.TimeoutError:
            raise RuntimeError(f"Ollama timeout after {timeout}s")
        except ImportError:
            # Fallback to urllib if aiohttp not available
            return await self._ask_urllib(prompt, system_prompt, timeout)

    async def _ask_urllib(self, prompt: str, system_prompt: str, timeout: int) -> str:
        """Fallback using urllib (no aiohttp needed)."""
        import urllib.request

        url = f"{self._base_url}/api/chat"
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "stream": False,
        }).encode()

        def _do_request() -> str:
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "")

        return await asyncio.to_thread(_do_request)

    async def is_available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                available = any(self._model in m for m in models)
                log.debug("ollama_backend.check", models=models[:5], target=self._model, available=available)
                return available
        except Exception:
            return False


class LLMBridge:
    """Multi-model bridge with automatic fallback chain.

    Primary: Claude Code CLI (handled externally by ClaudeBridge)
    Fallback chain: OpenAI → Ollama
    """

    def __init__(self) -> None:
        self._backends: list[LLMBackend] = []
        self._available_cache: dict[str, bool] = {}

    def add_backend(self, backend: LLMBackend) -> None:
        """Add a backend to the fallback chain."""
        self._backends.append(backend)
        log.info("llm_bridge.backend_added", name=backend.name)

    async def check_backends(self) -> dict[str, bool]:
        """Check availability of all backends."""
        results: dict[str, bool] = {}
        for backend in self._backends:
            try:
                results[backend.name] = await backend.is_available()
            except Exception:
                results[backend.name] = False
        self._available_cache = results
        log.info("llm_bridge.backends_checked", results=results)
        return results

    async def ask_fallback(self, prompt: str, system_prompt: str = "", timeout: int = 120) -> str:
        """Ask using the fallback chain. Tries each backend until one succeeds."""
        errors: list[str] = []

        for backend in self._backends:
            try:
                cached = self._available_cache.get(backend.name)
                if cached is False:
                    continue

                result = await backend.ask(prompt, system_prompt, timeout)
                if result:
                    log.info("llm_bridge.fallback_success", backend=backend.name)
                    return result
            except Exception as exc:
                error_msg = f"{backend.name}: {exc}"
                errors.append(error_msg)
                log.warning("llm_bridge.backend_failed", backend=backend.name, error=str(exc))
                self._available_cache[backend.name] = False
                continue

        error_detail = "; ".join(errors) if errors else "no backends configured"
        raise RuntimeError(f"All LLM backends failed: {error_detail}")

    @property
    def backends(self) -> list[str]:
        return [b.name for b in self._backends]

    @property
    def available_backends(self) -> list[str]:
        return [name for name, ok in self._available_cache.items() if ok]
