"""
pywebview JavaScript-API bridge.

Exposes Python methods to the frontend via ``window.pywebview.api.*``.
"""

from __future__ import annotations

import json as _json
import logging
import os
import time
import urllib.request

from .win32 import (
    find_hwnd_by_title,
    find_main_hwnd,
    set_native_background,
    set_window_dark_titlebar,
)

logger = logging.getLogger(__name__)


class Api:
    """pywebview JS-API bridge — methods are called from the frontend."""

    def __init__(self) -> None:
        self._window = None
        self._window_title: str | None = None
        self._saved_theme: str | None = None

    def set_window(self, window: object, title: str) -> None:
        self._window = window
        self._window_title = title

    # ──────────── HTTP proxy (frontend calls via pywebview) ────────────

    def post_json(self, url: str, payload: dict) -> dict:
        """Forward a JSON POST request from the frontend to the target URL."""
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return _json.loads(resp.read().decode("utf-8"))

    # ──────────── Settings (frontend reads on mount) ────────────────────

    def get_settings(self) -> dict:
        return {"theme": self.get_saved_theme()}

    # ──────────── Theme persistence ───────────────────────────────────

    @staticmethod
    def get_system_dark() -> bool:
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        except Exception:
            return False

    def get_saved_theme(self) -> str:
        if self._saved_theme in ("light", "dark"):
            return self._saved_theme
        return "dark" if self.get_system_dark() else "light"

    @staticmethod
    def is_dark_mode(theme: str) -> bool:
        if theme == "dark":
            return True
        if theme == "light":
            return False
        return Api.get_system_dark()

    # ──────────── Result export to file ───────────────────────────────

    def export_results_file(self, json_str: str, filepath: str) -> str:
        filepath = os.path.normpath(filepath)
        try:
            dirname = os.path.dirname(filepath)
            if dirname and not os.path.exists(dirname):
                os.makedirs(dirname, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json_str)
        except OSError:
            logger.exception("Failed to export results to %s", filepath)
            raise
        return filepath

    # ──────────── Window handle resolution ────────────────────────────

    def _get_hwnd(self) -> int | None:
        hwnd = find_main_hwnd()
        if hwnd:
            return hwnd
        if self._window_title:
            hwnd = find_hwnd_by_title(self._window_title)
            if hwnd:
                return hwnd
        if self._window:
            for attr in ("native_handle", "_native_handle", "handle"):
                if hasattr(self._window, attr):
                    handle = getattr(self._window, attr)
                    if handle:
                        return handle
        return None

    def sync_titlebar_immediate(self, theme: str) -> None:
        """Poll for HWND readiness, then set native background + title bar color."""
        dark = self.is_dark_mode(theme)
        for _ in range(20):
            hwnd = self._get_hwnd()
            if hwnd:
                set_native_background(hwnd, dark)
                set_window_dark_titlebar(hwnd, dark)
                return
            time.sleep(0.05)
        logger.warning("HWND not found after 20 retries, skipping titlebar sync")

    def set_theme(self, theme: str) -> None:
        """Persist theme preference and apply to the native window."""
        if theme in ("light", "dark"):
            self._saved_theme = theme
        hwnd = self._get_hwnd()
        if hwnd is None:
            return
        dark = self.is_dark_mode(theme)
        set_native_background(hwnd, dark)
        set_window_dark_titlebar(hwnd, dark)
