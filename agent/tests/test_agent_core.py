"""Agent Core orchestration tests (Phase 3).

These verify the loop mechanics deterministically with a scripted FakeProvider —
no model loading. Tool execution goes through a real ToolRegistry with stub
tools, so the registry/tool contract is exercised end to end.

Runs under pytest (`pytest agent/tests/`) OR standalone
(`python agent/tests/test_agent_core.py`).
"""

import contextlib
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import pytest  # noqa: F401
except ImportError:
    pytest = None

from agent.core import AgentCore, AgentResult, LLMProvider  # noqa: E402
from agent.tools import Tool, ToolRegistry, ToolResult  # noqa: E402


# ── test doubles ────────────────────────────────────────────────────────────────
class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []  # list of role-sequences, one per complete()

    def complete(self, messages, *, max_tokens=512, temperature=0.2):
        self.calls.append([m["role"] for m in messages])
        return self.responses.pop(0) if self.responses else '{"final": "(exhausted)"}'


class EchoTool(Tool):
    name = "echo"
    description = "Echo the args back."
    parameters = {"type": "object", "properties": {"x": {"type": "integer"}}}

    def run(self, **kwargs):
        return ToolResult.success({"echo": kwargs})


class CaptureTool(Tool):
    """A tool whose name is set per-instance, capturing the kwargs it received."""
    description = "capture"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, name):
        self.name = name
        self.last_kwargs = None

    def run(self, **kwargs):
        self.last_kwargs = kwargs
        return ToolResult.success({"ok": True})


def _registry(*tools):
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


# ── tests ───────────────────────────────────────────────────────────────────────
def test_direct_final_answer():
    core = AgentCore(registry=_registry(EchoTool()),
                     provider=FakeProvider(['{"final": "hello"}']), max_steps=3)
    res = core.run("hi")
    assert isinstance(res, AgentResult)
    assert res.answer == "hello" and res.completed
    assert res.tool_calls() == []
    assert res.provider == "fake"


def test_tool_then_final():
    fp = FakeProvider(['{"tool": "echo", "arguments": {"x": 7}}', '{"final": "done"}'])
    core = AgentCore(registry=_registry(EchoTool()), provider=fp, max_steps=3)
    res = core.run("do it")
    assert res.tool_calls() == ["echo"]
    assert res.answer == "done" and res.completed
    tool_step = [s for s in res.steps if s.kind == "tool"][0]
    assert tool_step.observation["ok"] is True
    assert tool_step.observation["data"]["echo"] == {"x": 7}


def test_plain_text_is_treated_as_final():
    core = AgentCore(registry=_registry(EchoTool()),
                     provider=FakeProvider(["I think the answer is 42."]), max_steps=2)
    res = core.run("q")
    assert res.answer == "I think the answer is 42." and res.completed
    assert res.tool_calls() == []


def test_json_in_code_fence_is_parsed():
    core = AgentCore(registry=_registry(EchoTool()),
                     provider=FakeProvider(['```json\n{"final": "x"}\n```']), max_steps=2)
    res = core.run("q")
    assert res.answer == "x"


def test_json_with_braces_inside_string_value():
    core = AgentCore(registry=_registry(EchoTool()),
                     provider=FakeProvider(['Sure: {"final": "has {braces} inside"}']),
                     max_steps=2)
    res = core.run("q")
    assert res.answer == "has {braces} inside"


def test_unknown_tool_becomes_failure_observation_then_recovers():
    fp = FakeProvider(['{"tool": "nope", "arguments": {}}', '{"final": "recovered"}'])
    core = AgentCore(registry=_registry(EchoTool()), provider=fp, max_steps=3)
    res = core.run("q")
    obs = [s for s in res.steps if s.kind == "tool"][0].observation
    assert obs["ok"] is False and "Unknown tool" in obs["error"]
    assert res.answer == "recovered"


def test_tenancy_injected_for_chat_tool_only():
    chat = CaptureTool("chat")
    fp = FakeProvider(['{"tool": "chat", "arguments": {"query": "hi"}}', '{"final": "ok"}'])
    core = AgentCore(registry=_registry(chat), provider=fp, max_steps=3)
    core.run("ask", allowed_file_ids={"a", "b"})
    assert chat.last_kwargs.get("allowed_file_ids") == {"a", "b"}
    assert chat.last_kwargs.get("query") == "hi"


def test_tenancy_not_injected_for_non_tenancy_tool():
    cap = CaptureTool("echo")  # not in tenancy_tools
    fp = FakeProvider(['{"tool": "echo", "arguments": {"x": 1}}', '{"final": "ok"}'])
    core = AgentCore(registry=_registry(cap), provider=fp, max_steps=3)
    core.run("q", allowed_file_ids={"a"})
    assert "allowed_file_ids" not in cap.last_kwargs


def test_tenancy_not_injected_when_none():
    chat = CaptureTool("chat")
    fp = FakeProvider(['{"tool": "chat", "arguments": {"query": "hi"}}', '{"final": "ok"}'])
    core = AgentCore(registry=_registry(chat), provider=fp, max_steps=3)
    core.run("ask")  # no allowed_file_ids
    assert "allowed_file_ids" not in chat.last_kwargs


def test_max_steps_then_synthesis_marks_incomplete():
    fp = FakeProvider([
        '{"tool": "echo", "arguments": {}}',
        '{"tool": "echo", "arguments": {}}',
        "final synthesized answer",  # synthesis pass (plain text)
    ])
    core = AgentCore(registry=_registry(EchoTool()), provider=fp, max_steps=2)
    res = core.run("q")
    assert res.completed is False
    assert res.answer == "final synthesized answer"
    assert len(res.tool_calls()) == 2


def test_result_to_dict_shape():
    fp = FakeProvider(['{"tool": "echo", "arguments": {"x": 1}}', '{"final": "ok"}'])
    core = AgentCore(registry=_registry(EchoTool()), provider=fp, max_steps=3)
    d = core.run("q").to_dict()
    assert d["answer"] == "ok" and d["completed"] is True
    assert d["tool_calls"] == ["echo"]
    assert d["steps"][0]["tool"] == "echo"


# ── standalone runner (used when pytest is unavailable) ──────────────────────────
if __name__ == "__main__":
    import traceback

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
