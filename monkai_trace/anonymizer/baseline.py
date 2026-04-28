"""Hardcoded baseline PII redaction rules. Always applied; no fetch involved."""

from dataclasses import dataclass
from typing import List, Pattern
import re


@dataclass(frozen=True)
class BaselineRule:
    name: str
    pattern: Pattern[str]
    replacement: str


BASELINE_RULES: List[BaselineRule] = []


class BaselineAnonymizer:
    """Applies BASELINE_RULES to text content. No configuration."""

    def __init__(self, rules: List[BaselineRule] = BASELINE_RULES):
        self._rules = rules

    def apply(self, text: str) -> str:
        if not text:
            return text
        for rule in self._rules:
            text = rule.pattern.sub(rule.replacement, text)
        return text
