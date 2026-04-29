"""End-to-end tests for the SDK applying custom rules + stamping version.

Covers both the sync ``MonkAIClient`` and the async ``AsyncMonkAIClient``,
exercising:
  * version stamp lands on the outbound payload as ``anonymization_version``.
  * custom rules redact text after the baseline runs.
  * baseline toggles disable specific classes (``toggles[name] = false``).
  * upload is blocked when ``RulesClient`` cannot be fetched and has no cache.
  * client without ``rules_url`` keeps Phase-1 behaviour (no version stamped,
    no custom rules applied).
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from monkai_trace import AsyncMonkAIClient, MonkAIClient
from monkai_trace.anonymizer.rules_client import RulesClient
from monkai_trace.exceptions import MonkAIAnonymizerNotReady


def _seed_rules(client, version, toggles=None, custom=None):
    """Seed the client's RulesClient cache so no network call is made."""
    rc = client._rules_client
    rc._cache = {
        "version": version,
        "rules": {
            "toggles": toggles or {},
            "custom": custom or [],
        },
    }
    rc._cached_at = 1e12  # far future


def _capture_post(captured):
    def fake(method, url, json=None, **kwargs):
        if json is not None:
            captured.append(json)
        resp = MagicMock()
        resp.status_code = 201
        resp.reason = "Created"
        resp.json.return_value = {"inserted_count": 1}
        return resp
    return fake


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------


def test_sync_stamps_anonymization_version_on_payload():
    client = MonkAIClient(tracer_token="tk_test", rules_url="http://hub")
    _seed_rules(client, version=7)
    captured = []

    with patch("requests.Session.request", side_effect=_capture_post(captured)):
        client.upload_record(
            namespace="t", agent="bot",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert len(captured) == 1
    record = captured[0]["records"][0]
    assert record["anonymization_version"] == 7


def test_sync_applies_custom_rule_on_top_of_baseline():
    client = MonkAIClient(tracer_token="tk_test", rules_url="http://hub")
    _seed_rules(
        client,
        version=2,
        custom=[{"name": "mk_id", "pattern": r"MK-\d+", "replacement": "[MK_ID]"}],
    )
    captured = []

    with patch("requests.Session.request", side_effect=_capture_post(captured)):
        client.upload_record(
            namespace="t", agent="bot",
            messages=[{"role": "user", "content": "id MK-12345 user@m.com"}],
        )

    body = json.dumps(captured[0])
    assert "MK-12345" not in body
    assert "[MK_ID]" in body
    # Baseline still runs first
    assert "user@m.com" not in body
    assert "[EMAIL]" in body


def test_sync_toggle_disables_baseline_class():
    client = MonkAIClient(tracer_token="tk_test", rules_url="http://hub")
    # email toggle off → email should NOT be redacted
    _seed_rules(client, version=4, toggles={"email": False})
    captured = []

    with patch("requests.Session.request", side_effect=_capture_post(captured)):
        client.upload_record(
            namespace="t", agent="bot",
            messages=[{"role": "user", "content": "arthur@monkai.com.br + cpf 123.456.789-09"}],
        )

    body = json.dumps(captured[0])
    assert "arthur@monkai.com.br" in body, "email toggle was off — email should pass through"
    # CPF not toggled → still redacted
    assert "[CPF]" in body


def test_sync_blocks_upload_when_rules_unavailable():
    client = MonkAIClient(tracer_token="tk_test", rules_url="http://hub")
    # Force RulesClient.get to fail with no cache
    with patch(
        "monkai_trace.anonymizer.rules_client.requests.get",
        side_effect=RuntimeError("hub down"),
    ):
        with pytest.raises(MonkAIAnonymizerNotReady):
            client.upload_record(
                namespace="t", agent="bot",
                messages=[{"role": "user", "content": "hi"}],
            )


def test_sync_without_rules_url_preserves_phase1_behaviour():
    """No rules_url → no version stamp, baseline still applies."""
    client = MonkAIClient(tracer_token="tk_test")
    captured = []

    with patch("requests.Session.request", side_effect=_capture_post(captured)):
        client.upload_record(
            namespace="t", agent="bot",
            messages=[{"role": "user", "content": "cpf 123.456.789-09"}],
        )

    record = captured[0]["records"][0]
    assert "anonymization_version" not in record
    assert "[CPF]" in json.dumps(record)


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


def _async_capture_request():
    captured = []

    class _Resp:
        def __init__(self, status=201, payload=None):
            self.status = status
            self._payload = payload or {"inserted_count": 1}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def raise_for_status(self):
            if self.status >= 400:
                raise RuntimeError(f"http {self.status}")

        async def json(self):
            return self._payload

    def fake_request(method, url, json=None, **kwargs):
        if json is not None:
            captured.append(json)
        return _Resp()

    return captured, fake_request


def test_async_stamps_version_and_applies_custom_rule():
    async def run():
        client = AsyncMonkAIClient(tracer_token="tk_test", rules_url="http://hub")
        _seed_rules(
            client,
            version=11,
            custom=[{"name": "mk_id", "pattern": r"MK-\d+", "replacement": "[MK_ID]"}],
        )
        captured, fake = _async_capture_request()
        with patch("aiohttp.ClientSession.request", side_effect=fake):
            await client.upload_record(
                namespace="t", agent="bot",
                messages=[{"role": "user", "content": "id MK-99 user@m.com"}],
            )
        await client.close()
        return captured

    captured = asyncio.run(run())
    body = json.dumps(captured[0])
    assert "MK-99" not in body
    assert "[MK_ID]" in body
    assert "[EMAIL]" in body
    assert captured[0]["records"][0]["anonymization_version"] == 11


def test_async_blocks_when_rules_unavailable():
    async def run():
        client = AsyncMonkAIClient(tracer_token="tk_test", rules_url="http://hub")
        with patch(
            "monkai_trace.anonymizer.rules_client.requests.get",
            side_effect=RuntimeError("hub down"),
        ):
            with pytest.raises(MonkAIAnonymizerNotReady):
                await client.upload_record(
                    namespace="t", agent="bot",
                    messages=[{"role": "user", "content": "hi"}],
                )
        await client.close()

    asyncio.run(run())


def test_async_without_rules_url_preserves_phase1_behaviour():
    async def run():
        client = AsyncMonkAIClient(tracer_token="tk_test")
        captured, fake = _async_capture_request()
        with patch("aiohttp.ClientSession.request", side_effect=fake):
            await client.upload_record(
                namespace="t", agent="bot",
                messages=[{"role": "user", "content": "cpf 123.456.789-09"}],
            )
        await client.close()
        return captured

    captured = asyncio.run(run())
    record = captured[0]["records"][0]
    assert "anonymization_version" not in record
    assert "[CPF]" in json.dumps(record)


def test_external_rules_client_injection():
    """User can pass a pre-built RulesClient (e.g. shared across multiple clients)."""
    rc = RulesClient(tracer_token="tk_test", hub_url="http://hub", ttl_seconds=300)
    rc._cache = {
        "version": 42,
        "rules": {"toggles": {}, "custom": []},
    }
    rc._cached_at = 1e12

    client = MonkAIClient(tracer_token="tk_test", rules_client=rc)
    captured = []
    with patch("requests.Session.request", side_effect=_capture_post(captured)):
        client.upload_record(
            namespace="t", agent="bot",
            messages=[{"role": "user", "content": "hi"}],
        )
    assert captured[0]["records"][0]["anonymization_version"] == 42
