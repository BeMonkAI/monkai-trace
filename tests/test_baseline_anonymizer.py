"""Tests for BaselineAnonymizer hardcoded PII rules."""

import pytest
from monkai_trace.anonymizer.baseline import (
    BaselineAnonymizer,
    _cpf_check_digits_valid,
    _luhn_valid,
)


def test_anonymizer_can_be_instantiated():
    a = BaselineAnonymizer()
    assert a is not None


def test_apply_returns_string_for_string_input():
    a = BaselineAnonymizer()
    result = a.apply("hello world")
    assert isinstance(result, str)
    assert result == "hello world"


@pytest.mark.parametrize("text, expected_redacted", [
    ("CPF 123.456.789-09 do cliente", "CPF [CPF] do cliente"),
    ("12345678909 sem mascara", "[CPF] sem mascara"),
])
def test_redacts_cpf(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


def test_does_not_redact_invalid_cpf_length():
    assert BaselineAnonymizer().apply("number 1234") == "number 1234"


@pytest.mark.parametrize("text, expected_redacted", [
    ("CNPJ 12.345.678/0001-95", "CNPJ [CNPJ]"),
    ("12345678000195 raw", "[CNPJ] raw"),
])
def test_redacts_cnpj(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


@pytest.mark.parametrize("text, expected_redacted", [
    ("contact arthur@monkai.com.br please", "contact [EMAIL] please"),
    ("first.last+tag@sub.example.io", "[EMAIL]"),
])
def test_redacts_email(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


@pytest.mark.parametrize("text, expected_redacted", [
    ("call (11) 99999-1234 today", "call [PHONE] today"),
    ("+55 11 9 9999-1234", "[PHONE]"),
    ("11999991234", "[PHONE]"),
])
def test_redacts_brazilian_phone(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


def test_redacts_credit_card_with_luhn():
    # 4111 1111 1111 1111 is the Visa test card (passes Luhn)
    assert BaselineAnonymizer().apply("card 4111 1111 1111 1111 ok") == "card [CARD] ok"


def test_does_not_redact_non_luhn_card_number():
    # 4111 1111 1111 1112 fails Luhn
    assert BaselineAnonymizer().apply("4111 1111 1111 1112") == "4111 1111 1111 1112"


@pytest.mark.parametrize("text, expected_redacted", [
    ("server 192.168.1.1 down", "server [IP] down"),
    ("ipv6 2001:0db8:85a3::8a2e:0370:7334", "ipv6 [IP]"),
])
def test_redacts_ip(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


@pytest.mark.parametrize("text, expected_redacted", [
    ("RG 12.345.678-9", "RG [RG]"),
])
def test_redacts_rg(text, expected_redacted):
    assert BaselineAnonymizer().apply(text) == expected_redacted


def test_redacts_multiple_pii_in_same_text():
    text = "User arthur@monkai.com.br with CPF 123.456.789-09 from 192.168.1.1"
    expected = "User [EMAIL] with CPF [CPF] from [IP]"
    assert BaselineAnonymizer().apply(text) == expected


def test_pipeline_order_cpf_before_card():
    """Both shapes present; redaction must produce both labels in correct order.
    Protects the contract: CPF callable runs first, CARD callable runs last.
    """
    text = "CPF 12345678909 e card 4111111111111111"
    expected = "CPF [CPF] e card [CARD]"
    assert BaselineAnonymizer().apply(text) == expected


@pytest.mark.parametrize("digits, expected", [
    ("12345678909", True),    # canonical Receita example, valid
    ("11111111111", False),   # all-same-digit rejected
    ("12345678900", False),   # wrong second check digit
    ("123", False),           # too short
])
def test_cpf_check_digits_valid(digits, expected):
    assert _cpf_check_digits_valid(digits) is expected


@pytest.mark.parametrize("digits, expected", [
    ("4111111111111111", True),
    ("4111111111111112", False),
    ("123", False),
])
def test_luhn_valid(digits, expected):
    assert _luhn_valid(digits) is expected


# ---------------------------------------------------------------------------
# apply_to_messages — list-of-blocks content (Anthropic/OpenAI tool-use)
# ---------------------------------------------------------------------------


def test_apply_to_messages_redacts_string_content():
    a = BaselineAnonymizer()
    out = a.apply_to_messages([{"role": "user", "content": "CPF 123.456.789-09"}])
    assert out == [{"role": "user", "content": "CPF [CPF]"}]


def test_apply_to_messages_redacts_text_block_in_list_content():
    a = BaselineAnonymizer()
    msg = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "O CPF do cliente e 123.456.789-09"},
            {"type": "tool_use", "id": "x", "name": "lookup", "input": {"cpf": "12345678909"}},
        ],
    }
    out = a.apply_to_messages([msg])
    blocks = out[0]["content"]
    assert blocks[0]["text"] == "O CPF do cliente e [CPF]"
    # tool_use input is also scrubbed recursively
    assert blocks[1]["input"]["cpf"] == "[CPF]"


def test_apply_to_messages_redacts_tool_result_content_string():
    a = BaselineAnonymizer()
    msg = {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "x", "content": "email arthur@monkai.com.br"}
        ],
    }
    out = a.apply_to_messages([msg])
    assert out[0]["content"][0]["content"] == "email [EMAIL]"


def test_apply_to_messages_redacts_tool_result_content_blocks():
    a = BaselineAnonymizer()
    msg = {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "x",
                "content": [{"type": "text", "text": "phone +55 11 91234-5678"}],
            }
        ],
    }
    out = a.apply_to_messages([msg])
    inner = out[0]["content"][0]["content"][0]
    assert inner["text"] == "phone [PHONE]"


def test_apply_to_messages_redacts_nested_dict_in_tool_use_input():
    a = BaselineAnonymizer()
    msg = {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "x",
                "name": "search",
                "input": {
                    "query": "find CPF 123.456.789-09",
                    "filters": {"email": "arthur@monkai.com.br"},
                    "tags": ["12.345.678/0001-95"],
                },
            }
        ],
    }
    out = a.apply_to_messages([msg])
    inp = out[0]["content"][0]["input"]
    assert inp["query"] == "find CPF [CPF]"
    assert inp["filters"]["email"] == "[EMAIL]"
    assert inp["tags"] == ["[CNPJ]"]


def test_apply_to_messages_passes_through_unknown_block_types():
    a = BaselineAnonymizer()
    msg = {"role": "assistant", "content": [{"type": "image", "source": {"data": "..."}}]}
    out = a.apply_to_messages([msg])
    assert out == [msg]


def test_apply_to_messages_warns_on_unsupported_content_shape(caplog):
    a = BaselineAnonymizer()
    msg = {"role": "user", "content": 42}  # neither str nor list
    with caplog.at_level("WARNING", logger="monkai_trace.anonymizer.baseline"):
        out = a.apply_to_messages([msg])
    # Message is preserved (unchanged) but a warning is emitted
    assert out[0]["content"] == 42
    assert any("unsupported content" in rec.message for rec in caplog.records)


def test_apply_to_messages_accepts_single_dict():
    a = BaselineAnonymizer()
    out = a.apply_to_messages({"role": "user", "content": "CPF 123.456.789-09"})
    assert out == [{"role": "user", "content": "CPF [CPF]"}]


def test_apply_to_messages_does_not_mutate_input():
    a = BaselineAnonymizer()
    original = {
        "role": "assistant",
        "content": [{"type": "text", "text": "CPF 123.456.789-09"}],
    }
    a.apply_to_messages([original])
    # input untouched
    assert original["content"][0]["text"] == "CPF 123.456.789-09"
