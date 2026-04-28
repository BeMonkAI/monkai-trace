"""Verify the async SDK client surfaces server-side dedup drops."""

import logging
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from monkai_trace import AsyncMonkAIClient, MonkAIRecordDiscardedError


def _fake_aiohttp_response(json_payload, status=201):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_payload)
    resp.text = AsyncMock(return_value="")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_clean_insert_no_warning_no_raise(caplog):
    client = AsyncMonkAIClient(tracer_token="tk_test", strict_dedup=True)

    fake = _fake_aiohttp_response({"inserted_count": 1})
    with patch("aiohttp.ClientSession.request", return_value=fake):
        async with client:
            with caplog.at_level(logging.WARNING, logger="monkai_trace.async_client"):
                result = await client.upload_record(
                    namespace="t", agent="a",
                    messages=[{"role": "user", "content": "hi"}],
                )

    assert result == {"inserted_count": 1}
    assert "dropped" not in caplog.text.lower()


@pytest.mark.asyncio
async def test_all_dup_emits_warning(caplog):
    client = AsyncMonkAIClient(tracer_token="tk_test")

    fake = _fake_aiohttp_response({"inserted_count": 0, "duplicate": True}, status=200)
    with patch("aiohttp.ClientSession.request", return_value=fake):
        async with client:
            with caplog.at_level(logging.WARNING, logger="monkai_trace.async_client"):
                await client.upload_record(
                    namespace="t", agent="a",
                    messages=[{"role": "user", "content": "hi"}],
                )

    assert "dropped 1/1" in caplog.text.lower()


@pytest.mark.asyncio
async def test_strict_mode_raises_on_drop():
    client = AsyncMonkAIClient(tracer_token="tk_test", strict_dedup=True)

    fake = _fake_aiohttp_response({"inserted_count": 0, "duplicate": True}, status=200)
    with patch("aiohttp.ClientSession.request", return_value=fake):
        async with client:
            with pytest.raises(MonkAIRecordDiscardedError) as exc_info:
                await client.upload_record(
                    namespace="t", agent="a",
                    messages=[{"role": "user", "content": "hi"}],
                )

    err = exc_info.value
    assert err.dropped_count == 1
    assert err.total_received == 1


@pytest.mark.asyncio
async def test_strict_mode_no_raise_on_clean():
    client = AsyncMonkAIClient(tracer_token="tk_test", strict_dedup=True)

    fake = _fake_aiohttp_response({"inserted_count": 1})
    with patch("aiohttp.ClientSession.request", return_value=fake):
        async with client:
            await client.upload_record(
                namespace="t", agent="a",
                messages=[{"role": "user", "content": "hi"}],
            )
