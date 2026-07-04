"""LLM provider tests (Phase 11).

Cover the Gemini request/response translation (pure, no network) and the
environment-based provider selection (offline-first). The live Gemini call is
verified separately against the real API.

Runs under pytest OR standalone (`python agent/tests/test_provider.py`).
"""

import os
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import pytest  # noqa: F401
except ImportError:
    pytest = None

from agent.core import (  # noqa: E402
    GeminiProvider, GroqProvider, LocalQwenProvider, FallbackProvider, LLMProvider,
    get_default_provider,
)


class _StubProvider(LLMProvider):
    """Returns a canned string, or raises, to drive FallbackProvider tests."""

    def __init__(self, name, reply=None, error=None):
        self.name = name
        self._reply = reply
        self._error = error
        self.calls = 0

    def complete(self, messages, *, max_tokens=512, temperature=0.2):
        self.calls += 1
        if self._error:
            raise self._error
        return self._reply


# ── request translation ──────────────────────────────────────────────────────
def test_to_gemini_request_maps_roles_and_system():
    msgs = [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "again"},
    ]
    req = GeminiProvider._to_gemini_request(msgs, max_tokens=256, temperature=0.1)
    # system → systemInstruction (not in contents)
    assert req["systemInstruction"]["parts"][0]["text"] == "You are an agent."
    roles = [c["role"] for c in req["contents"]]
    assert roles == ["user", "model", "user"]          # assistant → model
    assert req["contents"][0]["parts"][0]["text"] == "hi"
    assert req["generationConfig"] == {"maxOutputTokens": 256, "temperature": 0.1}


def test_to_gemini_request_multiple_system_messages_joined():
    msgs = [
        {"role": "system", "content": "A"},
        {"role": "system", "content": "B"},
        {"role": "user", "content": "q"},
    ]
    req = GeminiProvider._to_gemini_request(msgs, 128, 0.0)
    assert req["systemInstruction"]["parts"][0]["text"] == "A\n\nB"


def test_to_gemini_request_no_system():
    req = GeminiProvider._to_gemini_request([{"role": "user", "content": "q"}], 64, 0.2)
    assert "systemInstruction" not in req
    assert req["contents"] == [{"role": "user", "parts": [{"text": "q"}]}]


# ── response parsing ─────────────────────────────────────────────────────────
def test_text_from_response_happy_path():
    data = {"candidates": [{"content": {"parts": [{"text": "hello "}, {"text": "world"}]}}]}
    assert GeminiProvider._text_from_response(data) == "hello world"


def test_text_from_response_empty_or_malformed():
    assert GeminiProvider._text_from_response({}) == ""
    assert GeminiProvider._text_from_response({"candidates": []}) == ""
    assert GeminiProvider._text_from_response({"candidates": [{}]}) == ""
    assert GeminiProvider._text_from_response(None) == ""


def test_gemini_provider_requires_key():
    try:
        GeminiProvider(api_key="")
    except ValueError:
        pass
    else:
        raise AssertionError("empty api_key must raise")
    p = GeminiProvider(api_key="k", model="gemini-2.0-flash")
    assert p.name == "gemini:gemini-2.0-flash"


# ── Groq (OpenAI-compatible) ─────────────────────────────────────────────────
def test_groq_request_passes_roles_through():
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"}]
    req = GroqProvider._to_request(msgs, "llama-3.3-70b-versatile", 256, 0.1)
    assert req["model"] == "llama-3.3-70b-versatile"
    assert [m["role"] for m in req["messages"]] == ["system", "user", "assistant"]
    assert req["messages"][1]["content"] == "u"
    assert req["max_tokens"] == 256 and req["temperature"] == 0.1


def test_groq_text_from_response():
    assert GroqProvider._text_from_response(
        {"choices": [{"message": {"content": "  hi there "}}]}) == "hi there"
    assert GroqProvider._text_from_response({}) == ""
    assert GroqProvider._text_from_response({"choices": []}) == ""
    assert GroqProvider._text_from_response(None) == ""


def test_groq_requires_key_and_name():
    try:
        GroqProvider(api_key="")
    except ValueError:
        pass
    else:
        raise AssertionError("empty api_key must raise")
    assert GroqProvider("k", "m").name == "groq:m"


# ── env-based selection (offline-first) ──────────────────────────────────────
def _with_env(**kv):
    """Set/clear env vars, returning a restore callable."""
    old = {k: os.environ.get(k) for k in kv}

    def restore():
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return restore


def _kinds(p):
    return [type(x).__name__ for x in p.providers]


def test_selection_no_key_is_local():
    restore = _with_env(GROQ_API_KEY=None, GEMINI_API_KEY=None, AGENT_LLM_PROVIDER=None)
    try:
        assert isinstance(get_default_provider(), LocalQwenProvider)
    finally:
        restore()


def test_selection_auto_priority_groq_then_gemini_then_local():
    restore = _with_env(GROQ_API_KEY="gk", GEMINI_API_KEY="mk", AGENT_LLM_PROVIDER="auto",
                        GROQ_MODEL="llama-3.3-70b-versatile", GEMINI_MODEL="gemini-2.0-flash")
    try:
        p = get_default_provider()
        assert isinstance(p, FallbackProvider)
        assert _kinds(p) == ["GroqProvider", "GeminiProvider", "LocalQwenProvider"]
        assert p.name == "groq:llama-3.3-70b-versatile"   # most-preferred reported first
    finally:
        restore()


def test_selection_only_gemini_key():
    restore = _with_env(GROQ_API_KEY=None, GEMINI_API_KEY="mk", AGENT_LLM_PROVIDER="auto")
    try:
        assert _kinds(get_default_provider()) == ["GeminiProvider", "LocalQwenProvider"]
    finally:
        restore()


def test_selection_only_groq_key():
    restore = _with_env(GROQ_API_KEY="gk", GEMINI_API_KEY=None, AGENT_LLM_PROVIDER="auto")
    try:
        assert _kinds(get_default_provider()) == ["GroqProvider", "LocalQwenProvider"]
    finally:
        restore()


def test_selection_explicit_local_overrides_keys():
    restore = _with_env(GROQ_API_KEY="gk", GEMINI_API_KEY="mk", AGENT_LLM_PROVIDER="local")
    try:
        assert isinstance(get_default_provider(), LocalQwenProvider)
    finally:
        restore()


def test_selection_explicit_gemini_excludes_groq():
    restore = _with_env(GROQ_API_KEY="gk", GEMINI_API_KEY="mk", AGENT_LLM_PROVIDER="gemini")
    try:
        assert _kinds(get_default_provider()) == ["GeminiProvider", "LocalQwenProvider"]
    finally:
        restore()


def test_selection_explicit_groq():
    restore = _with_env(GROQ_API_KEY="gk", GEMINI_API_KEY="mk", AGENT_LLM_PROVIDER="groq")
    try:
        assert _kinds(get_default_provider()) == ["GroqProvider", "LocalQwenProvider"]
    finally:
        restore()


# ── FallbackProvider robustness ──────────────────────────────────────────────
def test_fallback_uses_primary_when_ok():
    primary = _StubProvider("gemini:x", reply="from-primary")
    fb = _StubProvider("local", reply="from-local")
    p = FallbackProvider([primary, fb])
    assert p.complete([{"role": "user", "content": "q"}]) == "from-primary"
    assert p.name == "gemini:x" and fb.calls == 0


def test_fallback_degrades_on_primary_error_and_sticks():
    primary = _StubProvider("gemini:x", error=RuntimeError("Gemini API 429"))
    fb = _StubProvider("local", reply="from-local")
    p = FallbackProvider([primary, fb])
    # 1st call: primary raises → degrade to fallback
    assert p.complete([{"role": "user", "content": "q"}]) == "from-local"
    assert "local" in p.name and "fallback from gemini:x" in p.name
    # 2nd call: stays degraded, primary not retried
    assert p.complete([{"role": "user", "content": "q2"}]) == "from-local"
    assert primary.calls == 1 and fb.calls == 2


if __name__ == "__main__":
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}")
        except Exception:
            failed += 1; print(f"FAIL  {name}"); traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
