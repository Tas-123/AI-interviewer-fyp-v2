"""Shared pytest fixtures for backend tests."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure backend package is importable when running from repo root
BACKEND = os.path.join(os.path.dirname(__file__), "..")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture(autouse=True)
def _quiet_live_debug_logging(monkeypatch):
    """Disable file debug logging during unit tests."""
    monkeypatch.setenv("DEBUG_LIVE_LOGGING", "false")
