"""Shared pytest fixtures for the test suite."""
import pytest


@pytest.fixture(autouse=True)
def _clear_api_key(monkeypatch):
    """Remove API_KEY so unit tests bypass auth (no real server key in CI)."""
    monkeypatch.delenv("API_KEY", raising=False)
