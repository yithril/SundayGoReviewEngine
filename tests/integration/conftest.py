from __future__ import annotations

"""
tests/integration/conftest.py
------------------------------
Session-scoped KataGo fixture and auto-skip logic for integration tests.

Environment variables
---------------------
KATAGO_BINARY  : path to the KataGo executable (default: C:/katago/katago.exe)
KATAGO_MODEL   : path to the KataGo .bin.gz model file (REQUIRED — no default)
KATAGO_CONFIG  : path to the KataGo analysis config (default: analysis.cfg)

Any test decorated with @pytest.mark.integration is automatically skipped if
KATAGO_MODEL is not set or KATAGO_BINARY does not exist on the filesystem.
This keeps CI green on machines that don't have a local KataGo installation.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from katago.engine import KataGoEngine

# Load .env.local first (local overrides), then fall back to .env.
# Shell environment variables always take precedence (override=False).
_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env.local", override=False)
load_dotenv(_ROOT / ".env", override=False)

KATAGO_BINARY = os.getenv("KATAGO_BINARY", "C:/katago/katago.exe")
KATAGO_MODEL  = os.getenv("KATAGO_MODEL", "")
KATAGO_CONFIG = os.getenv("KATAGO_CONFIG", "analysis.cfg")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires local KataGo binary and model",
    )


def pytest_collection_modifyitems(items):
    """Auto-skip integration tests when KataGo is unavailable."""
    missing = []
    if not KATAGO_MODEL:
        missing.append("KATAGO_MODEL env var not set")
    if not os.path.exists(KATAGO_BINARY):
        missing.append(f"KataGo binary not found at {KATAGO_BINARY!r}")

    if not missing:
        return

    reason = "; ".join(missing)
    skip_mark = pytest.mark.skip(reason=reason)
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_mark)


@pytest.fixture(scope="session")
async def katago():
    """Session-scoped KataGo engine.

    A single engine process is started once for the entire test session and
    shared across all integration tests.  pytest-asyncio keeps the event loop
    alive for the session (asyncio_mode = auto in pytest.ini), which is
    required because KataGoEngine uses background asyncio Tasks.
    """
    engine = KataGoEngine(KATAGO_BINARY, KATAGO_MODEL, KATAGO_CONFIG)
    await engine.start()
    yield engine
    await engine.stop()
