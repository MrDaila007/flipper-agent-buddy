"""Context usage extraction tests."""

import importlib.util
from pathlib import Path


SCRIPTS = Path(__file__).parents[2] / "scripts"


def load_module():
    path = SCRIPTS / "context_usage.py"
    spec = importlib.util.spec_from_file_location("context_usage", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extract_usage_percent_field():
    cu = load_module()
    out = cu.extract_usage({"usage_percent": 83})
    assert out["context_pct"] == 83


def test_extract_usage_from_tokens():
    cu = load_module()
    out = cu.extract_usage({"token_count": 250000, "context_window_size": 1000000})
    assert out["context_pct"] == 25


def test_extract_session_rate_limit():
    cu = load_module()
    out = cu.extract_usage({"rate_limits": {"primary": {"used_percent": 72.4}}})
    assert out["session_pct"] == 72


def test_compact_level_for_high_context():
    cu = load_module()
    assert cu.compact_level_for(93, "auto") == 3
    assert cu.compact_level_for(80, "manual") == 2
