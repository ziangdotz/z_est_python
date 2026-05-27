"""
pywebview JavaScript-API bridge.

Exposes Python methods to the frontend via ``window.pywebview.api.*``.
"""

from __future__ import annotations

import json as _json
import logging
import os
import time
import tkinter as _tk
import urllib.request
from tkinter import filedialog as _filedialog

from . import est_test_vue3_pywebview as _orig
from . import est_test_nist_cpp_recode_vue3_pywebview as _nist

_active_module = _orig


def _use_module(payload: dict | None = None):
    global _active_module
    if payload is not None:
        _active_module = _nist if payload.pop("use_nist_cpp_recode", False) else _orig
    return _active_module

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

    # -- Static helpers ---------------------------------------------------

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

    @staticmethod
    def is_dark_mode(theme: str) -> bool:
        if theme == "dark":
            return True
        if theme == "light":
            return False
        return Api.get_system_dark()

    # -- Public: window & settings ----------------------------------------

    def set_window(self, window: object, title: str) -> None:
        self._window = window
        self._window_title = title

    def get_settings(self) -> dict:
        return {"theme": self.get_saved_theme()}

    # -- Theme persistence ------------------------------------------------

    def get_saved_theme(self) -> str:
        if self._saved_theme in ("light", "dark"):
            return self._saved_theme
        return "dark" if self.get_system_dark() else "light"

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
        logger.warning(
            "HWND not found after 20 retries, skipping titlebar sync")

    # -- HTTP proxy (frontend calls via pywebview) -------------------------

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

    # -- Entropy test (local est_core) ------------------------------------

    def start_entropy_test(self, payload: dict) -> dict:
        """Launch entropy test in a subprocess, returns immediately."""
        return _use_module(payload).start_entropy_test(payload)

    def poll_entropy_test(self) -> dict:
        """Non-blocking poll for log messages and completion status."""
        return _use_module().poll_entropy_test()

    def cleanup_entropy_test(self) -> None:
        """Release all held memory from the last test run."""
        _use_module().cleanup_entropy_test()

    # -- Result export to file --------------------------------------------

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

    # -- Native file picker -----------------------------------------------

    def pick_file(self) -> str | None:
        """Open a native Windows file-open dialog and return the selected path."""
        root = _tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return _filedialog.askopenfilename(
                title="选择文件",
                filetypes=[
                    ("所有支持的格式", "*.bin *.dat *.raw"),
                    ("所有文件", "*.*"),
                ],
            ) or None
        finally:
            root.destroy()

    def save_file(self, default_name: str = "result.json") -> str | None:
        """Open a native Windows save-file dialog and return the chosen path."""
        root = _tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return _filedialog.asksaveasfilename(
                title="导出结果",
                defaultextension=".json",
                initialfile=default_name,
                filetypes=[
                    ("JSON 文件", "*.json"),
                    ("所有文件", "*.*"),
                ],
            ) or None
        finally:
            root.destroy()

    # -- Window handle resolution -----------------------------------------

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
