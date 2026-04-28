"""Verify the SDK applies BaselineAnonymizer before transmission."""

import json
from unittest.mock import patch, MagicMock
from monkai_trace import MonkAIClient


def test_upload_record_anonymizes_message_content_before_send():
    client = MonkAIClient(tracer_token="tk_test")
    captured_payload = {}

    def fake_request(method, url, json=None, **kwargs):
        if json is not None:
            captured_payload.update(json)
        resp = MagicMock()
        resp.status_code = 201
        resp.reason = "Created"
        resp.json.return_value = {"inserted_count": 1}
        return resp

    with patch("requests.Session.request", side_effect=fake_request):
        client.upload_record(
            namespace="test",
            agent="bot",
            messages=[
                {"role": "user", "content": "my CPF is 123.456.789-09"},
                {"role": "assistant", "content": "ok arthur@monkai.com.br"},
            ],
        )

    serialized = json.dumps(captured_payload)
    assert "123.456.789-09" not in serialized
    assert "arthur@monkai.com.br" not in serialized
    assert "[CPF]" in serialized
    assert "[EMAIL]" in serialized
