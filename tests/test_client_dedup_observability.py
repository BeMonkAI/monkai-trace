"""Verify the SDK surfaces server-side dedup drops to callers."""

import logging
from unittest.mock import patch, MagicMock
import pytest
from monkai_trace import MonkAIClient, MonkAIRecordDiscardedError


def _fake_response(json_payload, status=201):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_payload
    return resp


def test_clean_insert_no_warning_no_raise(caplog):
    client = MonkAIClient(tracer_token="tk_test", strict_dedup=True)

    with patch("requests.Session.request", return_value=_fake_response({"inserted_count": 1})):
        with caplog.at_level(logging.WARNING, logger="monkai_trace.client"):
            result = client.upload_record(
                namespace="t", agent="a",
                messages=[{"role": "user", "content": "hi"}],
            )

    assert result == {"inserted_count": 1}
    assert "dropped" not in caplog.text.lower()


def test_all_dup_emits_warning(caplog):
    client = MonkAIClient(tracer_token="tk_test")

    payload = {"inserted_count": 0, "duplicate": True, "tokens_processed": 0}
    with patch("requests.Session.request", return_value=_fake_response(payload, status=200)):
        with caplog.at_level(logging.WARNING, logger="monkai_trace.client"):
            client.upload_record(
                namespace="t", agent="a",
                messages=[{"role": "user", "content": "hi"}],
            )

    assert "dropped 1/1" in caplog.text.lower()


def test_partial_drop_emits_warning_for_batch(caplog):
    from monkai_trace.models import ConversationRecord

    client = MonkAIClient(tracer_token="tk_test")
    records = [
        ConversationRecord(namespace="t", agent="a",
                           msg=[{"role": "user", "content": f"msg_{i}"}])
        for i in range(10)
    ]
    payload = {"inserted_count": 8, "duplicates_skipped": 2}

    with patch("requests.Session.request", return_value=_fake_response(payload)):
        with caplog.at_level(logging.WARNING, logger="monkai_trace.client"):
            client.upload_records_batch(records, chunk_size=10)

    assert "dropped 2/10" in caplog.text.lower()


def test_strict_mode_raises_on_drop():
    client = MonkAIClient(tracer_token="tk_test", strict_dedup=True)

    payload = {"inserted_count": 0, "duplicate": True}
    with patch("requests.Session.request", return_value=_fake_response(payload, status=200)):
        with pytest.raises(MonkAIRecordDiscardedError) as exc_info:
            client.upload_record(
                namespace="t", agent="a",
                messages=[{"role": "user", "content": "hi"}],
            )

    err = exc_info.value
    assert err.dropped_count == 1
    assert err.inserted_count == 0
    assert err.total_received == 1


def test_strict_mode_no_raise_on_clean():
    client = MonkAIClient(tracer_token="tk_test", strict_dedup=True)

    with patch("requests.Session.request", return_value=_fake_response({"inserted_count": 1})):
        # No raise.
        client.upload_record(
            namespace="t", agent="a",
            messages=[{"role": "user", "content": "hi"}],
        )
