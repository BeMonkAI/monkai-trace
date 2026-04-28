"""Bot Framework integration helpers for monkai-trace.

Helps callers translate Microsoft Bot Framework activity payloads into the
fields monkai-trace's upload_record expects. Currently scoped to channel
inference; future helpers can land here as Bot Framework adoption grows.
"""

from typing import Mapping

# Microsoft Bot Framework channelId -> MonkAI channel string.
# https://learn.microsoft.com/en-us/azure/bot-service/bot-service-channels-reference
_CHANNEL_MAP: Mapping[str, str] = {
    "msteams": "teams",
    "directline": "web",
    "webchat": "web",
    "emulator": "emulator",
}


def infer_channel(payload: dict) -> str:
    """Map a Bot Framework activity's ``channelId`` to a MonkAI channel string.

    Unknown values pass through lower-cased so the dashboard surfaces them
    for investigation rather than silently mislabelling. Missing or empty
    channelId returns ``"unknown"``.

    Args:
        payload: A Bot Framework activity payload (the dict from
            ``await req.json()`` in the webhook handler).

    Returns:
        The channel string suitable for ``MonkAIClient.upload_record``'s
        ``external_user_channel`` argument.
    """
    raw = (payload.get("channelId") or "").lower()
    return _CHANNEL_MAP.get(raw, raw or "unknown")
