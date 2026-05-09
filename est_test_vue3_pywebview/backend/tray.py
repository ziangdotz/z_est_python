"""
System tray icon manager.

Encapsulates pystray lifecycle, i18n-aware menu labels, and
theme / language toggling that pushes state changes to both the
Python backend and the frontend via ``evaluate_js``.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

try:
    import pystray
    from pystray import MenuItem as TrayMenuItem
    from PIL import Image as PilImage

    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

from .config import APP_TITLE

if TYPE_CHECKING:
    from collections.abc import Callable

    from .api import Api

logger = logging.getLogger(__name__)

# ── i18n strings for tray menu items ──────────────────────────────────

_TRAY_I18N: dict[str, dict[str, str]] = {
    "zh": {
        "show": "显示窗口",
        "hide": "隐藏窗口",
        "about": "关于应用",
        "switch_theme": "切换主题",
        "quit": "退出",
        "theme_light_label": "浅色",
        "theme_dark_label": "深色",
    },
}


class TrayManager:
    """Manages the system tray icon and its menu interactions."""

    def __init__(self, api: Api, get_resource_path: Callable[[str], str]) -> None:
        self._api = api
        self._get_resource_path = get_resource_path
        self._icon: pystray.Icon | None = None
        self._main_window: object | None = None
        self._window_visible = True

    # ── Public API ────────────────────────────────────────────────────

    def set_window(self, window) -> None:
        """Store the pywebview window reference for toggle operations."""
        self._main_window = window

    def run(self) -> None:
        """Block on the tray icon run-loop (call from a daemon thread)."""
        self._icon = self._build_icon()
        self._icon.run()

    # ── Internal helpers ──────────────────────────────────────────────

    def _t(self, key: str) -> str:
        return _TRAY_I18N["zh"].get(key, key)

    def _next_theme_label(self) -> str:
        key_map = {
            "light": "theme_dark_label",
            "dark": "theme_light_label",
        }
        return self._t(key_map.get(self._api.get_saved_theme(), "theme_light_label"))

    def _build_icon(self) -> pystray.Icon:
        return pystray.Icon(
            name=APP_TITLE,
            icon=self._create_image(),
            title=APP_TITLE,
            menu=self._build_menu(),
        )

    def _create_image(self):
        png_path = self._get_resource_path("assets/app_logo.png")
        if os.path.exists(png_path):
            try:
                image = PilImage.open(png_path).convert("RGBA")
                return image.resize((64, 64), PilImage.LANCZOS)
            except Exception as e:
                logger.warning("Failed to load tray icon: %s", e)
        return None

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            TrayMenuItem(
                self._t("show"), self._on_show, default=False
            ),
            TrayMenuItem(self._t("hide"), self._on_hide),
            pystray.Menu.SEPARATOR,
            TrayMenuItem(self._t("about"), self._on_show_about),
            TrayMenuItem(
                f"{self._t('switch_theme')} ({self._next_theme_label()})",
                self._on_toggle_theme,
            ),
            pystray.Menu.SEPARATOR,
            TrayMenuItem(self._t("quit"), self._on_quit),
        )

    def _refresh_menu(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                logger.exception("Failed to stop previous tray icon")
            self._icon = self._build_icon()
            threading.Thread(target=self._icon.run, daemon=True).start()

    # ── Menu callbacks ────────────────────────────────────────────────

    def _on_show(self, icon=None, item=None) -> None:
        if self._main_window:
            try:
                self._main_window.show()
                self._main_window.restore()
                self._window_visible = True
            except Exception:
                logger.exception("Failed to show/restore window")

    def _on_hide(self, icon=None, item=None) -> None:
        if self._main_window:
            try:
                self._main_window.hide()
                self._window_visible = False
            except Exception:
                logger.exception("Failed to hide window")

    def _on_show_about(self, icon=None, item=None) -> None:
        if self._main_window:
            try:
                self._main_window.show()
                self._main_window.restore()
                self._main_window.evaluate_js("showAboutPanel()")
            except Exception:
                logger.exception("Failed to show about panel")

    def _on_toggle_theme(self) -> None:
        if not self._api or not self._main_window:
            return
        theme_order = ["light", "dark"]
        current = self._api.get_saved_theme()
        try:
            idx = theme_order.index(current)
        except ValueError:
            idx = 0
        next_theme = theme_order[(idx + 1) % len(theme_order)]
        self._api.set_theme(next_theme)
        self._main_window.evaluate_js(f"setThemeFromTray('{next_theme}')")
        self._refresh_menu()

    def _on_quit(self, icon=None, item=None) -> None:
        if self._icon:
            self._icon.stop()
        if self._main_window:
            try:
                self._main_window.destroy()
            except Exception:
                logger.exception("Failed to destroy window")

    def stop(self) -> None:
        """Stop the tray icon if running."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                logger.exception("Failed to stop tray icon")
