"""Live-mode wiring, verified without any network call."""

import pytest

from agent_support_resolution.drafting import LiveDrafter, MockDrafter, get_drafter
from agent_support_resolution.models import LiveModeError


def test_mock_is_default():
    assert isinstance(get_drafter(), MockDrafter)
    assert isinstance(get_drafter(live=False), MockDrafter)


def test_live_without_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LiveModeError, match="GEMINI_API_KEY"):
        LiveDrafter()


def test_live_with_key_constructs(monkeypatch):
    # Construction only — no API call is made here. Skipped when the
    # optional `live` extra is not installed.
    pytest.importorskip("langchain_google_genai")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    drafter = LiveDrafter()
    assert drafter is not None
