"""LLM provider abstraction for the Agent Core — *Model Independence*.

The Agent Core depends ONLY on this interface, never on a concrete model
(SmartDocs-Agent/CLAUDE.md → Model Independence). Providers shipped:

* ``LocalQwenProvider`` — offline-first default; reuses the already-loaded shared
  Qwen via ``services.ai_rewrite_service.run_local_messages`` (B1 pattern).
* ``GeminiProvider``    — Google Gemini REST API.
* ``GroqProvider``      — Groq OpenAI-compatible chat API (fast cloud inference).
* ``OpenAICompatibleProvider`` — any OpenAI-compatible ``/v1/chat/completions``
  server (vLLM, llama.cpp server, LM Studio, …) via ``OPENAI_COMPATIBLE_*``.

All speak the SAME neutral ``complete(messages) -> str`` contract, so the Agent
Core's model-neutral JSON tool protocol works unchanged with any of them — no
provider-specific branching leaks into the loop. ``FallbackProvider`` chains
several together (priority order) so a rate-limited / unreachable cloud provider
transparently degrades to the next one, ending at the always-available local model.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, List

logger = logging.getLogger(__name__)

Message = Dict[str, str]  # {"role": "...", "content": "..."}

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class LLMProvider(ABC):
    name: str = "provider"

    @abstractmethod
    def complete(self, messages: List[Message], *, max_tokens: int = 512,
                 temperature: float = 0.2) -> str:
        """Return the model's text completion for a chat-style message list."""
        raise NotImplementedError


class LocalQwenProvider(LLMProvider):
    """Local Qwen via the existing shared generation path (offline-first)."""

    name = "local-qwen"

    def __init__(self) -> None:
        self.last_engine: str | None = None

    def complete(self, messages: List[Message], *, max_tokens: int = 512,
                 temperature: float = 0.2) -> str:
        from services import ai_rewrite_service  # lazy: avoids importing torch at import time

        text, engine = ai_rewrite_service.run_local_messages(
            list(messages),
            max_new_tokens=max_tokens,
            max_input_tokens=4096,          # roomy: tool specs + observations
            temperature=temperature,
            do_sample=temperature > 0,
        )
        self.last_engine = engine
        return text or ""


class GeminiProvider(LLMProvider):
    """Google Gemini via the REST API (``generativelanguage.googleapis.com``)."""

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL,
                 timeout: int = 60) -> None:
        if not api_key:
            raise ValueError("GeminiProvider requires an api_key")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.name = f"gemini:{model}"

    @staticmethod
    def _to_gemini_request(messages: List[Message], max_tokens: int,
                           temperature: float) -> dict:
        """Neutral messages → Gemini generateContent body (system→systemInstruction,
        assistant→model)."""
        system_parts: List[str] = []
        contents: List[dict] = []
        for m in messages:
            role = m.get("role")
            text = m.get("content") or ""
            if role == "system":
                if text:
                    system_parts.append(text)
            else:
                g_role = "model" if role == "assistant" else "user"
                contents.append({"role": g_role, "parts": [{"text": text}]})
        req: dict = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if system_parts:
            req["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        return req

    @staticmethod
    def _text_from_response(data: dict) -> str:
        try:
            cands = (data or {}).get("candidates") or []
            if not cands:
                return ""
            parts = (cands[0].get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in parts).strip()
        except Exception:
            return ""

    def complete(self, messages: List[Message], *, max_tokens: int = 512,
                 temperature: float = 0.2) -> str:
        import requests  # lazy: keep `import agent` free of the http stack

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent")
        body = self._to_gemini_request(list(messages), max_tokens, temperature)
        resp = requests.post(
            url,
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json=body, timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API {resp.status_code}: {resp.text[:300]}")
        return self._text_from_response(resp.json())


class GroqProvider(LLMProvider):
    """Groq via the OpenAI-compatible Chat Completions API (``api.groq.com``).

    Groq accepts the neutral role-tagged messages directly (system/user/assistant),
    so no translation is needed — only auth + response extraction.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_GROQ_MODEL,
                 timeout: int = 60) -> None:
        if not api_key:
            raise ValueError("GroqProvider requires an api_key")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.name = f"groq:{model}"

    @staticmethod
    def _to_request(messages: List[Message], model: str, max_tokens: int,
                    temperature: float) -> dict:
        """Neutral messages → OpenAI/Groq chat body (roles pass through)."""
        return {
            "model": model,
            "messages": [{"role": m.get("role") or "user",
                          "content": m.get("content") or ""} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

    @staticmethod
    def _text_from_response(data: dict) -> str:
        try:
            choices = (data or {}).get("choices") or []
            if not choices:
                return ""
            return ((choices[0].get("message") or {}).get("content") or "").strip()
        except Exception:
            return ""

    def complete(self, messages: List[Message], *, max_tokens: int = 512,
                 temperature: float = 0.2) -> str:
        import requests  # lazy

        body = self._to_request(list(messages), self.model, max_tokens, temperature)
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=body, timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:300]}")
        return self._text_from_response(resp.json())


class OpenAICompatibleProvider(LLMProvider):
    """Any OpenAI-compatible ``/v1/chat/completions`` endpoint (vLLM, llama.cpp
    server, LM Studio, a remote Mac running mlx, …).

    Configured via ``OPENAI_COMPATIBLE_BASE_URL`` / ``OPENAI_COMPATIBLE_MODEL``
    / ``OPENAI_COMPATIBLE_API_KEY`` (key optional — many local servers need
    none). The request/response shape is identical to Groq's (both speak the
    OpenAI chat API), so the payload helpers are shared.
    """

    def __init__(self, base_url: str, model: str, api_key: str = "",
                 timeout: int = 120) -> None:
        if not base_url or not model:
            raise ValueError("OpenAICompatibleProvider requires base_url and model")
        base = base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            self.url = base
        elif base.endswith("/v1"):
            self.url = base + "/chat/completions"
        else:
            self.url = base + "/v1/chat/completions"
        self.api_key = api_key or ""
        self.model = model
        self.timeout = timeout
        self.name = f"openai-compatible:{model}"

    def complete(self, messages: List[Message], *, max_tokens: int = 512,
                 temperature: float = 0.2) -> str:
        import requests  # lazy

        body = GroqProvider._to_request(list(messages), self.model, max_tokens,
                                        temperature)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = requests.post(self.url, headers=headers, json=body,
                             timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenAI-compatible API {resp.status_code}: {resp.text[:300]}")
        return GroqProvider._text_from_response(resp.json())


class FallbackProvider(LLMProvider):
    """Try an ordered list of providers; on failure, fall through to the next.

    Robustness (Phase 11/12): a rate-limited (429), unauthorized, or unreachable
    cloud provider must not break the agent — the run transparently continues on
    the next provider, ending at the always-available local model. Once a provider
    succeeds after earlier ones failed, this instance sticks to it for the rest of
    its life (one request), so failed providers are not retried every step.
    ``name`` reflects the provider that actually produced the last completion.
    """

    def __init__(self, providers: List[LLMProvider]) -> None:
        self.providers = [p for p in providers if p is not None]
        if not self.providers:
            raise ValueError("FallbackProvider requires at least one provider")
        self._preferred = getattr(self.providers[0], "name", "provider")
        self.name = self._preferred
        self._start = 0

    def complete(self, messages: List[Message], *, max_tokens: int = 512,
                 temperature: float = 0.2) -> str:
        last_err = None
        for i in range(self._start, len(self.providers)):
            p = self.providers[i]
            try:
                out = p.complete(messages, max_tokens=max_tokens, temperature=temperature)
                pname = getattr(p, "name", "provider")
                self.name = pname if i == 0 else f"{pname} (fallback from {self._preferred})"
                if i > self._start:
                    self._start = i      # stick: skip providers that just failed
                return out
            except Exception as exc:  # noqa: BLE001 — degrade on any provider error
                last_err = exc
                logger.warning("[Provider] %s failed (%s); trying next",
                               getattr(p, "name", "?"), str(exc)[:160])
                continue
        raise last_err or RuntimeError("All providers failed")


def get_default_provider() -> LLMProvider:
    """Build the provider chain from the environment, offline-first.

    Priority (``AGENT_LLM_PROVIDER=auto``, the default): **Groq → Gemini →
    OpenAI-compatible endpoint (if configured) → local Qwen** — each cloud
    provider is included only if its key is set, and the local model is always
    the final fallback. ``AGENT_LLM_PROVIDER=local`` forces local; ``groq`` /
    ``gemini`` / ``openai_compatible`` pin that one provider (still
    local-backed).

    Cross-platform note: ``LLM_PROVIDER=openai_compatible`` (the platform-wide
    provider switch in config.py) promotes the configured OpenAI-compatible
    endpoint to the FRONT of the chain, so a Windows/Linux install without a
    usable local model can run the agent against vLLM / llama.cpp / LM Studio.
    """
    choice = (os.environ.get("AGENT_LLM_PROVIDER") or "auto").strip().lower()
    if choice == "local":
        return LocalQwenProvider()

    groq_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    gem_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    chain: List[LLMProvider] = []

    if groq_key and choice in ("auto", "groq"):
        try:
            chain.append(GroqProvider(groq_key,
                         (os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL).strip()))
        except Exception:
            pass
    if gem_key and choice in ("auto", "gemini"):
        try:
            chain.append(GeminiProvider(gem_key,
                         (os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()))
        except Exception:
            pass

    oc_url = (os.environ.get("OPENAI_COMPATIBLE_BASE_URL") or "").strip()
    oc_model = (os.environ.get("OPENAI_COMPATIBLE_MODEL") or "").strip()
    oc_key = (os.environ.get("OPENAI_COMPATIBLE_API_KEY") or "").strip()
    llm_provider = (os.environ.get("LLM_PROVIDER") or "local_hf").strip().lower()
    if oc_url and oc_model and choice in ("auto", "openai_compatible"):
        try:
            oc = OpenAICompatibleProvider(oc_url, oc_model, oc_key)
            if llm_provider == "openai_compatible" or choice == "openai_compatible":
                chain.insert(0, oc)     # explicit platform/agent choice → first
            else:
                chain.append(oc)        # auto → after the cloud keys, before local
        except Exception:
            pass

    chain.append(LocalQwenProvider())   # always the final, offline fallback
    return chain[0] if len(chain) == 1 else FallbackProvider(chain)
