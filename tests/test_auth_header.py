"""Regression tests pinning the wire auth header to RFC 6750 bearer.

The SDK historically sent the legacy ``tracer_token`` header. Issue #40
migrates every transport (sync client, async client, RulesClient) to
``Authorization: Bearer <token>`` while the server keeps accepting the legacy
header as a fallback. These tests lock the outbound header so a regression to
the legacy form fails loudly, and assert the legacy header is no longer sent.
"""

import asyncio
from unittest.mock import MagicMock, patch

from monkai_trace import AsyncMonkAIClient, MonkAIClient
from monkai_trace.anonymizer.rules_client import RulesClient


def test_sync_client_sends_bearer_header():
    client = MonkAIClient(tracer_token="tk_abc123")
    headers = client._session.headers
    assert headers["Authorization"] == "Bearer tk_abc123"
    # Legacy header must no longer be emitted by the SDK.
    assert "tracer_token" not in headers


def test_async_client_sends_bearer_header():
    captured = {}

    class _FakeSession:
        def __init__(self, *args, **kwargs):
            captured["headers"] = kwargs.get("headers")
            self.closed = False

    async def _run():
        with patch("aiohttp.ClientSession", _FakeSession):
            client = AsyncMonkAIClient(tracer_token="tk_xyz789")
            await client._ensure_session()

    asyncio.run(_run())

    assert captured["headers"]["Authorization"] == "Bearer tk_xyz789"
    assert "tracer_token" not in captured["headers"]


def test_rules_client_sends_bearer_header():
    rc = RulesClient(tracer_token="tk_rules", hub_url="http://hub", ttl_seconds=300)
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["headers"] = headers
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"version": 1, "rules": {"toggles": {}, "custom": []}}
        resp.raise_for_status.return_value = None
        return resp

    with patch("monkai_trace.anonymizer.rules_client.requests.get", side_effect=fake_get):
        rc.get()

    assert captured["headers"]["Authorization"] == "Bearer tk_rules"
    assert "tracer_token" not in captured["headers"]
