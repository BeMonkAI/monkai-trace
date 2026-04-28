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
