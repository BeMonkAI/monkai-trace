"""Hardcoded baseline PII redaction rules. Always applied; no fetch involved."""

from dataclasses import dataclass
from typing import List, Optional, Pattern
import re


@dataclass(frozen=True)
class BaselineRule:
    name: str
    pattern: Pattern[str]
    replacement: str


def _luhn_valid(digits: str) -> bool:
    digits = [int(c) for c in digits if c.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


_CARD_PATTERN = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")

_CPF_PATTERN = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def _redact_card(match: re.Match) -> str:
    raw = match.group(0)
    if _luhn_valid(raw):
        return "[CARD]"
    return raw


def _cpf_check_digits_valid(cpf_digits: str) -> bool:
    """Validate the two CPF check digits (BR ID number)."""
    digits = [int(c) for c in cpf_digits if c.isdigit()]
    if len(digits) != 11:
        return False
    if len(set(digits)) == 1:  # all-same-digit CPFs are syntactically invalid
        return False
    s1 = sum(d * (10 - i) for i, d in enumerate(digits[:9]))
    d1 = (s1 * 10) % 11
    if d1 == 10:
        d1 = 0
    if d1 != digits[9]:
        return False
    s2 = sum(d * (11 - i) for i, d in enumerate(digits[:10]))
    d2 = (s2 * 10) % 11
    if d2 == 10:
        d2 = 0
    return d2 == digits[10]


def _redact_cpf(match: re.Match) -> str:
    raw = match.group(0)
    if _cpf_check_digits_valid(raw):
        return "[CPF]"
    return raw


# Order matters: longer/more-specific patterns first so they win against the
# generic phone matcher. CNPJ before CPF; CARD before phone; IP before phone.
BASELINE_RULES: List[BaselineRule] = [
    BaselineRule(
        name="email",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        replacement="[EMAIL]",
    ),
    BaselineRule(
        name="cnpj",
        pattern=re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
        replacement="[CNPJ]",
    ),
    BaselineRule(
        name="rg",
        pattern=re.compile(r"\b\d{1,2}\.\d{3}\.\d{3}-[\dxX]\b"),
        replacement="[RG]",
    ),
    BaselineRule(
        name="ipv6",
        pattern=re.compile(
            r"\b[0-9a-fA-F]{1,4}(?::{1,2}[0-9a-fA-F]{1,4}){2,7}\b"
        ),
        replacement="[IP]",
    ),
    BaselineRule(
        name="ipv4",
        pattern=re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        replacement="[IP]",
    ),
    BaselineRule(
        name="brazilian_phone",
        # Lookarounds prevent matching inside longer digit runs (e.g. card
        # numbers like "4111 1111 1111 1111" should not be partially matched
        # as a phone before the CARD pass runs).
        pattern=re.compile(
            r"(?<!\d)(?:\+?55[\s-]?)?(?:\(\d{2}\)|\d{2})[\s-]?9?\s?\d{4}[\s-]?\d{4}(?![\s-]?\d)"
        ),
        replacement="[PHONE]",
    ),
    # CARD uses a callable to enforce Luhn; we apply it last so it does not
    # accidentally swallow CPF/CNPJ.
]


class BaselineAnonymizer:
    """Applies BASELINE_RULES to text content. No configuration."""

    def __init__(self, rules: Optional[List[BaselineRule]] = None):
        self._rules = rules if rules is not None else BASELINE_RULES
        self._card_pattern = _CARD_PATTERN
        self._cpf_pattern = _CPF_PATTERN

    def apply(self, text: str) -> str:
        if not text:
            return text
        # CPF runs first via a callable that validates the check digits.
        # This prevents 11-digit phone numbers from being mistaken for CPFs.
        text = self._cpf_pattern.sub(_redact_cpf, text)
        for rule in self._rules:
            text = rule.pattern.sub(rule.replacement, text)
        # CARD runs last via a callable that enforces Luhn so it does not
        # accidentally swallow other numeric IDs.
        text = self._card_pattern.sub(_redact_card, text)
        return text
