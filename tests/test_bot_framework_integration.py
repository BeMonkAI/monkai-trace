"""Tests for the Bot Framework channel inference helper."""

import pytest
from monkai_trace.integrations.bot_framework import infer_channel


@pytest.mark.parametrize("channel_id, expected", [
    ("msteams", "teams"),
    ("directline", "web"),
    ("webchat", "web"),
    ("emulator", "emulator"),
])
def test_known_channel_ids_map_correctly(channel_id, expected):
    assert infer_channel({"channelId": channel_id}) == expected


@pytest.mark.parametrize("channel_id, expected", [
    ("MSTEAMS", "teams"),
    ("MsTeams", "teams"),
    ("DirectLine", "web"),
    ("WEBCHAT", "web"),
])
def test_known_channel_ids_are_case_insensitive(channel_id, expected):
    assert infer_channel({"channelId": channel_id}) == expected


@pytest.mark.parametrize("channel_id, expected", [
    ("slack", "slack"),
    ("Slack", "slack"),
    ("custom-bot", "custom-bot"),
])
def test_unknown_channel_ids_pass_through_lowercased(channel_id, expected):
    assert infer_channel({"channelId": channel_id}) == expected


@pytest.mark.parametrize("payload", [
    {},
    {"channelId": None},
    {"channelId": ""},
])
def test_missing_or_empty_channel_id_returns_unknown(payload):
    assert infer_channel(payload) == "unknown"


def test_other_payload_fields_are_ignored():
    payload = {
        "channelId": "msteams",
        "from": {"id": "user-123", "aadObjectId": "aad-456"},
        "type": "message",
        "text": "hello",
    }
    assert infer_channel(payload) == "teams"


def test_helper_is_exported_at_integrations_level():
    """Verify the flat re-export from monkai_trace.integrations works."""
    from monkai_trace.integrations import infer_channel as flat_export
    assert flat_export({"channelId": "msteams"}) == "teams"
