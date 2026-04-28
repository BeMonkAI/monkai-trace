"""Tests for BaselineAnonymizer hardcoded PII rules."""

import pytest
from monkai_trace.anonymizer.baseline import BaselineAnonymizer


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
