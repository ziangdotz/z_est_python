"""
Application-wide configuration constants.

Single source of truth for version numbers, paths, network settings,
and UI layout limits. Imported by both ``main.py`` and ``backend/api.py``.
"""

from __future__ import annotations

from typing import Final

# ── Application identity ──────────────────────────────────────────────
APP_TITLE: Final = "est_test"
APP_VERSION: Final = "1.0.1"

# ── Network / server ──────────────────────────────────────────────────
APP_HOST: Final = "127.0.0.1"
APP_PORT: Final = 8081
VITE_URL: Final = "http://localhost:3001"

# ── Window size limits ────────────────────────────────────────────────
LIMIT_MIN_WIDTH: Final = 1000
LIMIT_MIN_HEIGHT: Final = 700
