"""'No user message captured' WARNING is not raised by the agent receiving a handoff (#69)."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from monkai_trace.integrations.openai_agents import MonkAIRunHooks

WARNING_TEXT = "No user message captured"


def _hooks():
    hooks = MonkAIRunHooks(tracer_token="tk_test", namespace="ns", batch_size=100)
    hooks.uploaded = []

    def upload(records):
        hooks.uploaded.extend(hooks.client._serialize_record(r) for r in records)
        return {"total_inserted": len(records), "total_records": len(records), "failures": []}

    hooks.client.upload_records_batch = Mock(side_effect=upload)
    hooks.set_user_id("user-1")
    return hooks


def _ctx():
    # No input/messages/context attributes: the hooks only have set_user_input to go on
    return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=5, requests=1))


def _agent(name):
    return SimpleNamespace(name=name, model="gpt-4o", instructions="Help.")


def _warnings(caplog):
    return [
        r for r in caplog.records if r.levelno == logging.WARNING and WARNING_TEXT in r.getMessage()
    ]


@pytest.mark.asyncio
async def test_handoff_does_not_warn_and_keeps_user_message(caplog):
    hooks = _hooks()
    triage, support = _agent("Triage"), _agent("Support")
    ctx = _ctx()

    hooks.set_user_input("Quero trocar meu plano")
    with caplog.at_level(logging.WARNING, logger="monkai_trace.integrations.openai_agents"):
        await hooks.on_agent_start(ctx, triage)
        await hooks.on_handoff(ctx, triage, support)
        await hooks.on_agent_start(ctx, support)
    await hooks.on_agent_end(ctx, support, "Claro, vamos ver os planos.")
    await hooks.flush()

    assert _warnings(caplog) == []
    user_msgs = [m for r in hooks.uploaded for m in r["msg"] if m["role"] == "user"]
    assert user_msgs and all(m["content"] == "Quero trocar meu plano" for m in user_msgs)


@pytest.mark.asyncio
async def test_turn_without_any_user_input_still_warns(caplog):
    hooks = _hooks()

    with caplog.at_level(logging.WARNING, logger="monkai_trace.integrations.openai_agents"):
        await hooks.on_agent_start(_ctx(), _agent("Support"))

    assert len(_warnings(caplog)) == 1


@pytest.mark.asyncio
async def test_next_turn_without_input_warns_after_previous_turn_ended(caplog):
    hooks = _hooks()
    agent, ctx = _agent("Support"), _ctx()

    hooks.set_user_input("Oi")
    await hooks.on_agent_start(ctx, agent)
    await hooks.on_agent_end(ctx, agent, "Olá!")

    with caplog.at_level(logging.WARNING, logger="monkai_trace.integrations.openai_agents"):
        await hooks.on_agent_start(ctx, agent)

    assert len(_warnings(caplog)) == 1
