"""Langfuse tracing tests.

No network and no Langfuse account: the handler is stubbed, so what is under test is the
contract this codebase depends on — that tracing is inert without credentials, that it never
raises into an agent run, and that a config built at the top of the graph reaches the LLM calls
the sub-agents make several frames down.
"""
import sys
from typing import Annotated, TypedDict

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.runnables.config import ensure_config
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from src.agent import tracing


class StubHandler(BaseCallbackHandler):
    """Stands in for langfuse.langchain.CallbackHandler — identity is all the tests check."""


class _ProbeState(TypedDict):
    messages: Annotated[list, add_messages]


@pytest.fixture(autouse=True)
def clean_tracing_state(monkeypatch):
    """Tracing caches its handler process-wide; reset around every test."""
    for name in (
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_TRACING_ENABLED",
        "LANGFUSE_VERIFY_SSL",
    ):
        monkeypatch.delenv(name, raising=False)
    tracing.reset()
    yield
    tracing.reset()


@pytest.fixture
def stub_handler(monkeypatch):
    """Pin a known handler so trace_config() behaves as if Langfuse were configured."""
    handler = StubHandler()
    monkeypatch.setattr(tracing, "_handler", handler)
    monkeypatch.setattr(tracing, "_resolved", True)
    return handler


# -- enablement ------------------------------------------------------------


def test_disabled_without_credentials():
    assert tracing.tracing_enabled() is False


def test_enabled_with_both_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    assert tracing.tracing_enabled() is True


def test_one_key_alone_is_not_enough(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")

    assert tracing.tracing_enabled() is False


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no", "off"])
def test_explicit_disable_overrides_present_keys(monkeypatch, value):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", value)

    assert tracing.tracing_enabled() is False


def test_host_falls_back_to_legacy_variable(monkeypatch):
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setenv("LANGFUSE_HOST", "https://langfuse.internal")

    assert tracing.langfuse_host() == "https://langfuse.internal"


def test_base_url_wins_over_legacy_variable(monkeypatch):
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://primary.example")
    monkeypatch.setenv("LANGFUSE_HOST", "https://legacy.example")

    assert tracing.langfuse_host() == "https://primary.example"


# -- degradation -----------------------------------------------------------


def test_no_credentials_yields_a_config_without_callbacks():
    config = tracing.trace_config("run", session_id="s1", tags=["a"])

    assert config == {}


def test_disabled_tracing_preserves_the_base_config():
    base = {"recursion_limit": 42, "callbacks": ["existing"]}

    config = tracing.trace_config("run", base=base)

    assert config == base
    assert config is not base, "base must not be mutated in place"


def test_missing_package_degrades_instead_of_raising(monkeypatch):
    """Tracing is optional; a missing import must not take an incident triage down with it."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "langfuse", None)  # forces ImportError on import

    assert tracing.get_handler() is None
    assert tracing.trace_config("run") == {}


def test_client_construction_failure_degrades(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    import langfuse

    def explode(**_kwargs):
        raise RuntimeError("host unreachable")

    monkeypatch.setattr(langfuse, "Langfuse", explode)

    assert tracing.get_handler() is None


def test_flush_is_safe_when_tracing_never_resolved():
    tracing.flush()  # must not raise


def test_handler_is_resolved_once(monkeypatch):
    calls = []
    monkeypatch.setattr(tracing, "_build_handler", lambda: calls.append(1) or "handler")

    assert tracing.get_handler() == "handler"
    assert tracing.get_handler() == "handler"
    assert len(calls) == 1


# -- config shape ----------------------------------------------------------


def test_trace_attributes_travel_as_langfuse_metadata_keys(stub_handler):
    config = tracing.trace_config(
        "sre-alert:PaymentHighErrorRate",
        session_id="fingerprint-1",
        user_id="oncall",
        tags=["incimin-webhook", "critical"],
        metadata={"service": "paymentservice"},
    )

    assert config["callbacks"] == [stub_handler]
    assert config["run_name"] == "sre-alert:PaymentHighErrorRate"
    assert config["metadata"] == {
        "service": "paymentservice",
        "langfuse_trace_name": "sre-alert:PaymentHighErrorRate",
        "langfuse_session_id": "fingerprint-1",
        "langfuse_user_id": "oncall",
        "langfuse_tags": ["incimin-webhook", "critical"],
    }


def test_optional_attributes_are_omitted_when_absent(stub_handler):
    config = tracing.trace_config("run")

    assert config["metadata"] == {"langfuse_trace_name": "run"}


def test_existing_callbacks_are_kept(stub_handler):
    """A caller's own callbacks (LangSmith, say) must survive; tracing appends, never replaces."""
    other = StubHandler()

    config = tracing.trace_config("run", base={"callbacks": [other]})

    assert config["callbacks"] == [other, stub_handler]


def test_a_bare_callback_is_normalised_to_a_list(stub_handler):
    other = StubHandler()

    config = tracing.trace_config("run", base={"callbacks": other})

    assert config["callbacks"] == [other, stub_handler]


def test_blank_and_duplicate_tags_are_dropped(stub_handler):
    """Callers build tag lists from optional alert fields, so None must not become "None"."""
    config = tracing.trace_config(
        "run", tags=["incimin-webhook", None, "", "  ", "incimin-webhook", "critical"]
    )

    assert config["metadata"]["langfuse_tags"] == ["incimin-webhook", "critical"]


def test_all_blank_tags_omit_the_key_entirely(stub_handler):
    config = tracing.trace_config("run", tags=[None, ""])

    assert "langfuse_tags" not in config["metadata"]


# -- propagation to sub-agents ---------------------------------------------


def test_callbacks_reach_llm_calls_made_inside_a_tool(stub_handler):
    """The telemetry and knowledge sub-agents call `build_llm().invoke(...)` inside a tool with
    no config of their own. They inherit the handler through LangChain's config contextvar —
    this pins that behaviour, since losing it would silently empty out half of every trace.
    """
    seen = {}

    @tool
    def probe_tool(query: str) -> str:
        """Records the config a nested call would see."""
        seen["callbacks"] = ensure_config().get("callbacks")
        return "ok"

    def emit_tool_call(_state):
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "probe_tool", "args": {"query": "x"}, "id": "call-1"}],
                )
            ]
        }

    # Driven through a compiled graph rather than a bare ToolNode, because it is the compiled
    # graph that establishes the run context the sub-agents actually execute inside.
    workflow = StateGraph(_ProbeState)
    workflow.add_node("emit", emit_tool_call)
    workflow.add_node("tools", ToolNode([probe_tool]))
    workflow.set_entry_point("emit")
    workflow.add_edge("emit", "tools")
    workflow.add_edge("tools", END)

    workflow.compile().invoke({"messages": []}, config=tracing.trace_config("run"))

    callbacks = seen["callbacks"]
    handlers = getattr(callbacks, "handlers", callbacks)
    assert stub_handler in handlers
