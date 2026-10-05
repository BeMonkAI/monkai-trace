"""Per-agent model and token attribution in MonkAIRunHooks.

Fakes the agents/contexts the SDK passes to the hooks; only the upload client
(``hooks.client.upload_records_batch``) is mocked.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from monkai_trace.integrations.openai_agents import MonkAIRunHooks, _model_id

TRIAGE_INSTRUCTIONS = "Route the customer to the right specialist."
SPECIALIST_INSTRUCTIONS = "You are the billing specialist. Answer billing questions."


def _hooks():
    hooks = MonkAIRunHooks(tracer_token="tk_test", namespace="ns", batch_size=100)
    hooks.uploaded = []

    def upload(records):  # the hook clears its buffer after upload, so copy now
        hooks.uploaded.extend(r.model_dump(by_alias=True) for r in records)
        return {"total_inserted": len(records)}

    hooks.client.upload_records_batch = Mock(side_effect=upload)
    hooks.set_user_id("user-1")
    return hooks


def _agent(name, model, instructions):
    return SimpleNamespace(name=name, model=model, instructions=instructions)


def _usage(inp, out):
    return SimpleNamespace(input_tokens=inp, output_tokens=out, requests=1)


def _response(inp, out):
    return SimpleNamespace(usage=_usage(inp, out), output=[])


async def _flush(hooks):
    await hooks.flush()
    hooks.client.upload_records_batch.assert_called_once()
    return hooks.uploaded


class _LitellmModel:
    """Stand-in for agents.extensions.models.litellm_model.LitellmModel (litellm is optional)."""

    __module__ = "agents.extensions.models.litellm_model"

    def __init__(self, model):
        self.model = model


# ---------------------------------------------------------------- characterization


@pytest.mark.asyncio
async def test_single_agent_turn_record_is_unchanged():
    """Pin the record a turn without handoff produces (same as before per-agent attribution)."""
    hooks = _hooks()
    agent = _agent("Support", "gpt-4o", SPECIALIST_INSTRUCTIONS)
    ctx = SimpleNamespace(usage=_usage(120, 30))

    hooks.set_user_input("Where is my invoice?")
    await hooks.on_agent_start(ctx, agent)
    await hooks.on_llm_start(ctx, agent, SPECIALIST_INSTRUCTIONS, [])
    await hooks.on_llm_end(ctx, agent, _response(120, 30))
    await hooks.on_agent_end(ctx, agent, "It was emailed yesterday.")

    [record] = await _flush(hooks)
    process = len(SPECIALIST_INSTRUCTIONS) // 4
    assert record["agent"] == "Support"
    assert record["model"] == "gpt-4o"
    assert record["session_id"] == hooks._current_session
    assert record["input_tokens"] == 120
    assert record["output_tokens"] == 30
    assert record["process_tokens"] == process
    assert record["memory_tokens"] == 0
    assert record["total_tokens"] == 150 + process
    assert record["transfers"] is None
    assert [(m["role"], m["content"], m["sender"]) for m in record["msg"]] == [
        ("user", "Where is my invoice?", "user"),
        ("assistant", "It was emailed yesterday.", "Support"),
    ]


# ---------------------------------------------------------------- model id


def test_model_id_string_passthrough():
    assert _model_id("gpt-4o") == "gpt-4o"
    assert _model_id("litellm/anthropic/claude-sonnet-4-5") == "litellm/anthropic/claude-sonnet-4-5"


def test_model_id_from_openai_model_object():
    from agents import OpenAIChatCompletionsModel, OpenAIResponsesModel
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key="sk-fake", base_url="http://localhost:1")
    assert _model_id(OpenAIChatCompletionsModel(model="gpt-4o", openai_client=client)) == "gpt-4o"
    assert _model_id(OpenAIResponsesModel(model="gpt-5-mini", openai_client=client)) == "gpt-5-mini"


def test_model_id_strips_litellm_provider_prefix():
    assert _model_id(_LitellmModel("anthropic/claude-sonnet-4-5")) == "claude-sonnet-4-5"
    assert _model_id(_LitellmModel("openrouter/openai/gpt-4o")) == "gpt-4o"
    assert _model_id(_LitellmModel("gpt-4o")) == "gpt-4o"


def test_model_id_real_litellm_model():
    pytest.importorskip("litellm")
    from agents.extensions.models.litellm_model import LitellmModel

    assert _model_id(LitellmModel(model="anthropic/claude-sonnet-4-5")) == "claude-sonnet-4-5"


def test_model_id_unknown_object_is_none_not_repr():
    assert _model_id(None) is None
    assert _model_id(object()) is None
    assert _model_id(Mock()) is None


@pytest.mark.asyncio
async def test_record_model_is_clean_id_for_model_object():
    hooks = _hooks()
    agent = _agent("Support", _LitellmModel("anthropic/claude-sonnet-4-5"), "x")
    ctx = SimpleNamespace(usage=_usage(1, 1))
    hooks.set_user_input("hi")
    await hooks.on_agent_start(ctx, agent)
    await hooks.on_agent_end(ctx, agent, "hello")
    [record] = await _flush(hooks)
    assert record["model"] == "claude-sonnet-4-5"


# ---------------------------------------------------------------- handoffs


async def _handoff_turn(hooks, with_llm_end=True):
    triage = _agent("Triage", "gpt-4o-mini", TRIAGE_INSTRUCTIONS)
    specialist = _agent(
        "Billing", _LitellmModel("anthropic/claude-sonnet-4-5"), SPECIALIST_INSTRUCTIONS
    )
    ctx = SimpleNamespace(usage=_usage(0, 0))

    hooks.set_user_input("Why was I charged twice?")
    await hooks.on_agent_start(ctx, triage)
    await hooks.on_llm_start(ctx, triage, TRIAGE_INSTRUCTIONS, [])
    ctx.usage = _usage(100, 5)  # the SDK adds to context.usage before on_llm_end
    if with_llm_end:
        await hooks.on_llm_end(ctx, triage, _response(100, 5))
    await hooks.on_handoff(ctx, triage, specialist)
    await hooks.on_agent_start(ctx, specialist)
    await hooks.on_llm_start(ctx, specialist, SPECIALIST_INSTRUCTIONS, [])
    ctx.usage = _usage(300, 55)
    if with_llm_end:
        await hooks.on_llm_end(ctx, specialist, _response(200, 50))
    await hooks.on_agent_end(ctx, specialist, "You were refunded.")


@pytest.mark.asyncio
async def test_handoff_turn_emits_one_record_per_agent():
    hooks = _hooks()
    await _handoff_turn(hooks)
    triage, billing = await _flush(hooks)

    assert triage["agent"] == "Triage"
    assert triage["model"] == "gpt-4o-mini"
    assert (triage["input_tokens"], triage["output_tokens"]) == (100, 5)
    assert triage["process_tokens"] == len(TRIAGE_INSTRUCTIONS) // 4
    assert triage["total_tokens"] == 105 + len(TRIAGE_INSTRUCTIONS) // 4

    assert billing["agent"] == "Billing"
    assert billing["model"] == "claude-sonnet-4-5"
    assert (billing["input_tokens"], billing["output_tokens"]) == (200, 50)
    assert billing["process_tokens"] == len(SPECIALIST_INSTRUCTIONS) // 4

    # Tokens add up to the run's cumulative usage: nothing lost, nothing double counted.
    assert triage["input_tokens"] + billing["input_tokens"] == 300
    assert triage["output_tokens"] + billing["output_tokens"] == 55
    assert triage["session_id"] == billing["session_id"] == hooks._current_session


@pytest.mark.asyncio
async def test_handoff_final_record_keeps_full_msg_and_transfers():
    hooks = _hooks()
    await _handoff_turn(hooks)
    _, billing = await _flush(hooks)

    assert [m["role"] for m in billing["msg"]] == ["user", "tool", "assistant"]
    assert billing["msg"][0]["content"] == "Why was I charged twice?"
    assert billing["msg"][-1]["content"] == "You were refunded."
    assert [(t["from"], t["to"]) for t in billing["transfers"]] == [("Triage", "Billing")]


@pytest.mark.asyncio
async def test_intermediate_record_is_not_a_user_turn():
    """Hub derives human_prompt from the first role=user message; intermediate has none."""
    hooks = _hooks()
    await _handoff_turn(hooks)
    triage, _ = await _flush(hooks)

    [msg] = triage["msg"]
    assert msg["role"] == "assistant"
    assert msg["sender"] == "Triage"
    assert msg["content"] == "Transferindo conversa para Billing"
    # The handoff timestamp keeps the msg unique so the Hub's 60s content dedup
    # (session_id + msg) never drops a later turn's identical handoff.
    assert msg["tool_calls"][0]["arguments"]["timestamp"]
    assert triage["transfers"] is None


@pytest.mark.asyncio
async def test_handoff_without_llm_end_falls_back_to_single_cumulative_record():
    """SDKs that never call on_llm_end keep the previous behavior."""
    hooks = _hooks()
    await _handoff_turn(hooks, with_llm_end=False)
    [record] = await _flush(hooks)
    assert record["agent"] == "Billing"
    assert (record["input_tokens"], record["output_tokens"]) == (300, 55)


@pytest.mark.asyncio
async def test_per_agent_usage_resets_between_turns():
    hooks = _hooks()
    await _handoff_turn(hooks)
    agent = _agent("Billing", "gpt-4o", "x")
    ctx = SimpleNamespace(usage=_usage(7, 3))
    hooks.set_user_input("thanks")
    await hooks.on_agent_start(ctx, agent)
    await hooks.on_llm_end(ctx, agent, _response(7, 3))
    await hooks.on_agent_end(ctx, agent, "bye")

    records = await _flush(hooks)
    assert len(records) == 3
    assert (records[-1]["input_tokens"], records[-1]["output_tokens"]) == (7, 3)


@pytest.mark.asyncio
async def test_metadata_goes_on_every_record_of_the_turn():
    hooks = _hooks()
    hooks.set_metadata({"label": "teste.21", "variant": "A"})
    await _handoff_turn(hooks)
    records = await _flush(hooks)

    assert len(records) == 2  # triage handoff record + final record
    assert all(r["metadata"] == {"label": "teste.21", "variant": "A"} for r in records)


@pytest.mark.asyncio
async def test_metadata_cleared_with_none_and_absent_by_default():
    hooks = _hooks()
    hooks.set_metadata({"label": "teste.21"})
    hooks.set_metadata(None)
    await _handoff_turn(hooks)
    records = await _flush(hooks)

    assert all(r["metadata"] is None for r in records)


@pytest.mark.asyncio
async def test_wire_format_omits_metadata_unless_set():
    wire = {}
    for name, meta in (("without", None), ("with", {"label": "teste.21", "variant": "A"})):
        hooks = _hooks()
        hooks.client.upload_records_batch = Mock(
            side_effect=lambda records: wire.setdefault(name, [r.to_api_format() for r in records])
            and {"total_inserted": len(records)}
        )
        if meta:
            hooks.set_metadata(meta)
        await _handoff_turn(hooks)
        await hooks.flush()

    assert wire["without"] and all("metadata" not in r for r in wire["without"])
    assert wire["with"] and all(r["metadata"] == {"label": "teste.21", "variant": "A"} for r in wire["with"])
