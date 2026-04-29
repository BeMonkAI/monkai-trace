"""Hardcoded baseline PII redaction rules. Always applied; no fetch involved."""

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Pattern, Set
import logging
import re

logger = logging.getLogger(__name__)


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

    def apply(self, text: str, disabled_classes: Optional[Iterable[str]] = None) -> str:
        if not text:
            return text
        disabled = self._coerce_disabled(disabled_classes)
        # CPF runs first via a callable that validates the check digits.
        # This prevents 11-digit phone numbers from being mistaken for CPFs.
        if "cpf" not in disabled:
            text = self._cpf_pattern.sub(_redact_cpf, text)
        for rule in self._rules:
            if rule.name in disabled:
                continue
            text = rule.pattern.sub(rule.replacement, text)
        # CARD runs last via a callable that enforces Luhn so it does not
        # accidentally swallow other numeric IDs.
        if "credit_card" not in disabled and "card" not in disabled:
            text = self._card_pattern.sub(_redact_card, text)
        return text

    @staticmethod
    def _coerce_disabled(disabled_classes: Optional[Iterable[str]]) -> Set[str]:
        if not disabled_classes:
            return set()
        return {c.lower() for c in disabled_classes}

    def apply_to_messages(
        self,
        messages: Any,
        disabled_classes: Optional[Iterable[str]] = None,
    ) -> List[Any]:
        """Anonymize a list of chat messages before transmission.

        Handles two shapes for ``content``:
          * ``str`` — legacy format; redacted directly via ``apply``.
          * ``list[dict]`` — Anthropic / OpenAI tool-use format. Each block
            is inspected and any visible text is redacted: ``text`` blocks,
            ``tool_use.input`` string values, and ``tool_result.content``
            (string or nested list of blocks).

        Unknown shapes are passed through unchanged with a single warning
        emitted, so we get visibility without dropping the record.
        """
        disabled = self._coerce_disabled(disabled_classes)
        if isinstance(messages, dict):
            messages = [messages]
        out: List[Any] = []
        for msg in messages:
            if not isinstance(msg, dict) or "content" not in msg:
                out.append(msg)
                continue
            content = msg["content"]
            new_msg = dict(msg)
            if isinstance(content, str):
                new_msg["content"] = self.apply(content, disabled)
            elif isinstance(content, list):
                new_msg["content"] = [self._anonymize_block(b, disabled) for b in content]
            else:
                logger.warning(
                    "BaselineAnonymizer: skipping message with unsupported content "
                    "type %s; PII may be transmitted unredacted",
                    type(content).__name__,
                )
            out.append(new_msg)
        return out

    def _anonymize_block(self, block: Any, disabled: Set[str]) -> Any:
        """Anonymize a single content block from a tool-use style message."""
        if not isinstance(block, dict):
            return block
        new_block = dict(block)
        block_type = new_block.get("type")
        if block_type == "text" and isinstance(new_block.get("text"), str):
            new_block["text"] = self.apply(new_block["text"], disabled)
        elif block_type == "tool_use" and isinstance(new_block.get("input"), dict):
            new_block["input"] = self._anonymize_dict(new_block["input"], disabled)
        elif block_type == "tool_result":
            inner = new_block.get("content")
            if isinstance(inner, str):
                new_block["content"] = self.apply(inner, disabled)
            elif isinstance(inner, list):
                new_block["content"] = [self._anonymize_block(b, disabled) for b in inner]
        return new_block

    def _anonymize_dict(self, d: dict, disabled: Set[str]) -> dict:
        """Recursively redact string values in a dict (e.g. tool_use.input)."""
        out: dict = {}
        for k, v in d.items():
            if isinstance(v, str):
                out[k] = self.apply(v, disabled)
            elif isinstance(v, dict):
                out[k] = self._anonymize_dict(v, disabled)
            elif isinstance(v, list):
                out[k] = [
                    self.apply(item, disabled) if isinstance(item, str)
                    else self._anonymize_dict(item, disabled) if isinstance(item, dict)
                    else item
                    for item in v
                ]
            else:
                out[k] = v
        return out
