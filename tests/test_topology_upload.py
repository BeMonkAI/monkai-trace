"""upload_topology: declared agent topology of a namespace (#60)."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from monkai_trace import AsyncMonkAIClient, MonkAIClient
from monkai_trace.exceptions import MonkAIAPIError

TOPOLOGY = {"schema_version": 1, "entry_point": "triage", "agents": {"triage": {"name": "Triage", "handoffs": []}}}
ACK = {"namespace": "acme", "topology_hash": "ab12", "changed": True}


def _response(status, payload):
    resp = Mock(status_code=status, reason="x")
    resp.json.return_value = payload
    return resp


@patch("requests.Session.request")
def test_sync_posts_namespace_and_topology_verbatim(mock_request):
    mock_request.return_value = _response(200, ACK)

    result = MonkAIClient(tracer_token="tk_test").upload_topology("acme", TOPOLOGY)

    assert result == ACK
    method, url = mock_request.call_args.args
    assert (method, url) == ("POST", f"{MonkAIClient.BASE_URL}/topology/upload")
    assert mock_request.call_args.kwargs["json"] == {"namespace": "acme", "topology": TOPOLOGY}


@patch("requests.Session.request")
def test_sync_unknown_namespace_raises(mock_request):
    mock_request.return_value = _response(404, {"error": {"code": "not_found"}})

    with pytest.raises(MonkAIAPIError, match="404"):
        MonkAIClient(tracer_token="tk_test").upload_topology("missing", TOPOLOGY)


@pytest.mark.asyncio
async def test_async_posts_to_topology_upload():
    resp = MagicMock(status=200)
    resp.json = AsyncMock(return_value=ACK)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession.request", return_value=resp) as mock_request:
        async with AsyncMonkAIClient(tracer_token="tk_test") as client:
            result = await client.upload_topology("acme", TOPOLOGY)

    assert result == ACK
    assert mock_request.call_args.args[1].endswith("/topology/upload")
    assert mock_request.call_args.kwargs["json"] == {"namespace": "acme", "topology": TOPOLOGY}
