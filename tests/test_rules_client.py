"""Tests for ``monkai_trace.anonymizer.rules_client.RulesClient``.

The RulesClient fetches per-tenant anonymization rules from the Hub edge
function and caches them with a TTL. Failure modes:
  * never-succeeded → raises ``MonkAIAnonymizerNotReady`` so the upload
    pipeline can block.
  * succeeded once, then transient failure → returns stale cache and warns.
  * cache hit within TTL → no network call.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from monkai_trace.anonymizer.rules_client import RulesClient
from monkai_trace.exceptions import MonkAIAnonymizerNotReady


def _ok_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def test_get_fetches_and_caches_within_ttl():
    payload = {"version": 3, "rules": {"toggles": {"email": True}, "custom": []}}
    with patch("monkai_trace.anonymizer.rules_client.requests.get") as g:
        g.return_value = _ok_response(payload)
        c = RulesClient(tracer_token="tk_x", hub_url="http://h", ttl_seconds=300)
        a = c.get()
        b = c.get()
    assert a == b
    assert a["version"] == 3
    assert g.call_count == 1, "Second call within TTL must hit cache, not network"


def test_get_refetches_after_ttl_expires():
    with patch("monkai_trace.anonymizer.rules_client.requests.get") as g:
        g.return_value = _ok_response(
            {"version": 1, "rules": {"toggles": {}, "custom": []}}
        )
        c = RulesClient(tracer_token="tk_x", hub_url="http://h", ttl_seconds=0)
        c.get()
        # second call: TTL=0 forces refetch
        g.return_value = _ok_response(
            {"version": 2, "rules": {"toggles": {}, "custom": []}}
        )
        result = c.get()
    assert result["version"] == 2
    assert g.call_count == 2


def test_get_blocks_when_never_fetched_and_failing():
    with patch(
        "monkai_trace.anonymizer.rules_client.requests.get",
        side_effect=RuntimeError("hub down"),
    ):
        c = RulesClient(tracer_token="tk_x", hub_url="http://h", ttl_seconds=300)
        with pytest.raises(MonkAIAnonymizerNotReady):
            c.get()


def test_get_returns_stale_cache_on_failure_after_first_success(caplog):
    with patch("monkai_trace.anonymizer.rules_client.requests.get") as g:
        g.return_value = _ok_response(
            {"version": 7, "rules": {"toggles": {}, "custom": []}}
        )
        c = RulesClient(tracer_token="tk_x", hub_url="http://h", ttl_seconds=0)
        first = c.get()
        assert first["version"] == 7
        # Now make the next fetch fail; cache must still serve.
        g.side_effect = RuntimeError("hub flapping")
        with caplog.at_level("WARNING"):
            second = c.get()
    assert second["version"] == 7
    assert any("stale cache" in r.message for r in caplog.records)


def test_invalidate_forces_refetch():
    with patch("monkai_trace.anonymizer.rules_client.requests.get") as g:
        g.return_value = _ok_response(
            {"version": 1, "rules": {"toggles": {}, "custom": []}}
        )
        c = RulesClient(tracer_token="tk_x", hub_url="http://h", ttl_seconds=300)
        c.get()
        c.invalidate()
        c.get()
    assert g.call_count == 2


def test_normalize_handles_missing_fields():
    with patch("monkai_trace.anonymizer.rules_client.requests.get") as g:
        g.return_value = _ok_response({"foo": "bar"})  # garbage
        c = RulesClient(tracer_token="tk_x", hub_url="http://h", ttl_seconds=300)
        result = c.get()
    assert result == {
        "version": 0,
        "rules": {"toggles": {}, "custom": []},
    }


def test_endpoint_strips_trailing_slash():
    c = RulesClient(tracer_token="tk_x", hub_url="http://h/", ttl_seconds=300)
    assert c.endpoint == "http://h/v1/anonymization-rules"


def test_get_async_runs_blocking_fetch_in_thread():
    import asyncio

    payload = {"version": 5, "rules": {"toggles": {}, "custom": []}}
    with patch("monkai_trace.anonymizer.rules_client.requests.get") as g:
        g.return_value = _ok_response(payload)
        c = RulesClient(tracer_token="tk_x", hub_url="http://h", ttl_seconds=300)
        result = asyncio.run(c.get_async())
    assert result["version"] == 5
