"""Function tool arguments in the trace (#67) and failed batch upload logging (#66).

Uses the real ``agents.ToolContext`` the SDK passes to ``on_tool_start``; only the
upload boundary (``client.upload_records_batch`` / ``_upload_records_chunk``) is mocked.
"""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from monkai_trace.integrations.openai_agents import MonkAIRunHooks

ToolContext = pytest.importorskip("agents.tool_context").ToolContext


def _hooks(**kwargs):
    hooks = MonkAIRunHooks(tracer_token="tk_test", namespace="ns", batch_size=100, **kwargs)
    hooks.uploaded = []

    def upload(records):
        hooks.uploaded.extend(hooks.client._serialize_record(r) for r in records)
        return {"total_inserted": len(records), "total_records": len(records), "failures": []}

    hooks.client.upload_records_batch = Mock(side_effect=upload)
    hooks.set_user_id("user-1")
    return hooks


def _tool_ctx(arguments, call_id="call_1"):
    return ToolContext(
        context=None,
        tool_name="calcular_frete",
        tool_call_id=call_id,
        tool_arguments=arguments,
    )


async def _turn_with_tool(hooks, tool_ctx):
    agent = SimpleNamespace(name="Support", model="gpt-4o", instructions="Help.")
    tool = SimpleNamespace(name="calcular_frete")
    ctx = SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=5, requests=1))
    hooks.set_user_input("Quanto custa o frete?")
    await hooks.on_agent_start(ctx, agent)
    await hooks.on_tool_start(tool_ctx, agent, tool)
    await hooks.on_tool_end(tool_ctx, agent, tool, '{"status": "error", "error": "invalid_format"}')
    await hooks.on_agent_end(ctx, agent, "Não consegui calcular.")
    await hooks.flush()
    [record] = hooks.uploaded
    return [m for m in record["msg"] if m["role"] == "tool"]


# ---------------------------------------------------------------- #67 tool arguments


@pytest.mark.asyncio
async def test_function_tool_records_name_arguments_and_output():
    call, output = await _turn_with_tool(_hooks(), _tool_ctx('{"cep": "01310-100"}'))

    assert call["content"] == "Calling tool: calcular_frete"
    assert call["tool_calls"] == [
        {
            "name": "calcular_frete",
            "type": "function_call",
            "id": "call_1",
            "arguments": {"cep": "01310-100"},
        }
    ]
    assert output["content"] == '{"status": "error", "error": "invalid_format"}'


@pytest.mark.asyncio
async def test_tool_arguments_are_anonymized_before_upload():
    [call, _] = await _turn_with_tool(
        _hooks(), _tool_ctx('{"email": "ana@acme.com", "cep": "01310-100"}')
    )

    assert call["tool_calls"][0]["arguments"] == {"email": "[EMAIL]", "cep": "01310-100"}


@pytest.mark.asyncio
async def test_non_json_arguments_are_kept_as_string():
    [call, _] = await _turn_with_tool(_hooks(), _tool_ctx("not json"))

    assert call["tool_calls"][0]["arguments"] == "not json"


@pytest.mark.asyncio
async def test_capture_tool_arguments_false_sends_no_arguments():
    [call, _] = await _turn_with_tool(
        _hooks(capture_tool_arguments=False), _tool_ctx('{"cep": "01310-100"}')
    )

    assert "tool_calls" not in call


@pytest.mark.asyncio
async def test_context_without_tool_arguments_records_name_only():
    """Older SDKs pass a plain RunContextWrapper to on_tool_start."""
    [call, _] = await _turn_with_tool(_hooks(), SimpleNamespace(usage=None))

    assert call["content"] == "Calling tool: calcular_frete"
    assert "tool_calls" not in call


# ---------------------------------------------------------------- #66 failed upload


async def _flush_with_chunk_error(error, caplog):
    hooks = MonkAIRunHooks(tracer_token="tk_test", namespace="ns-nao-registrado")
    hooks.client._upload_records_chunk = Mock(side_effect=Exception(error))
    hooks.set_user_id("user-1")
    agent = SimpleNamespace(name="Support", model="gpt-4o", instructions="Help.")
    ctx = SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=1, requests=1))
    hooks.set_user_input("oi")
    await hooks.on_agent_start(ctx, agent)
    await hooks.on_agent_end(ctx, agent, "olá")
    with caplog.at_level(logging.INFO, logger="monkai_trace.integrations.openai_agents"):
        await hooks.flush()
    return [r for r in caplog.records if r.name == "monkai_trace.integrations.openai_agents"]


@pytest.mark.asyncio
async def test_unregistered_namespace_failure_logs_actionable_warning(caplog):
    records = await _flush_with_chunk_error(
        "403 Forbidden: Namespace não registrado. unregistered_namespaces: ['ns-nao-registrado']",
        caplog,
    )

    warnings = [r.getMessage() for r in records if r.levelno == logging.WARNING]
    assert any(
        "unregistered_namespaces" in w and "Register namespace 'ns-nao-registrado'" in w
        for w in warnings
    )
    assert any("Uploaded 0 records; 1 records lost" in w for w in warnings)
    assert not any(r.levelno == logging.INFO and "Uploaded" in r.getMessage() for r in records)


@pytest.mark.asyncio
async def test_generic_failure_logs_warning_without_namespace_hint(caplog):
    records = await _flush_with_chunk_error("500 Internal Server Error", caplog)

    warnings = [r.getMessage() for r in records if r.levelno == logging.WARNING]
    assert any("500 Internal Server Error" in w for w in warnings)
    assert not any("Register namespace" in w for w in warnings)
    assert all("tk_test" not in r.getMessage() for r in records)


@pytest.mark.asyncio
async def test_successful_upload_still_logs_info(caplog):
    hooks = _hooks()
    agent = SimpleNamespace(name="Support", model="gpt-4o", instructions="Help.")
    ctx = SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=1, requests=1))
    hooks.set_user_input("oi")
    await hooks.on_agent_start(ctx, agent)
    await hooks.on_agent_end(ctx, agent, "olá")
    with caplog.at_level(logging.INFO, logger="monkai_trace.integrations.openai_agents"):
        await hooks.flush()

    levels = [(r.levelno, r.getMessage()) for r in caplog.records if "Uploaded" in r.getMessage()]
    assert levels == [(logging.INFO, "Uploaded 1 records")]
