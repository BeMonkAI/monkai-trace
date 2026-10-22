"""Regression for #61: models must not use pydantic v1-style ``class Config``."""

import importlib
import sys
import warnings

import pytest


@pytest.mark.parametrize("module", ["monkai_trace.models", "monkai_trace"])
def test_import_emits_no_deprecation_warning(module, monkeypatch):
    # Re-import from scratch so class bodies run again; monkeypatch restores sys.modules.
    for name in [m for m in sys.modules if m == "monkai_trace" or m.startswith("monkai_trace.")]:
        monkeypatch.delitem(sys.modules, name)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        importlib.import_module(module)


def test_transfer_still_populates_by_name_and_alias():
    from monkai_trace.models import Transfer

    assert Transfer(from_agent="a", to_agent="b").from_agent == "a"
    assert Transfer(**{"from": "a", "to": "b"}).to_agent == "b"
