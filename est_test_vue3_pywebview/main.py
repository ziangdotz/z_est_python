"""
NIST SP800-90B Entropy Assessment Tool — application entry point.

Creates a pywebview window backed by either the Vite dev server
(``--dev``) or a bundled static-file server, and optionally starts
a system-tray icon for quick window toggling.
"""

from __future__ import annotations

import argparse
import ctypes
import functools
import http.server
import logging
import os
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request

import webview

from backend.api import Api
from backend.config import (
    APP_HOST,
    APP_PORT,
    APP_TITLE,
    LIMIT_MIN_HEIGHT,
    LIMIT_MIN_WIDTH,
    VITE_URL,
)
from backend.tray import HAS_TRAY, TrayManager
from backend.win32 import (
    find_window_by_title,
    get_physical_screen_size,
    set_taskbar_icon,
    set_titlebar_icon,
)

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            logger.debug("Could not set DPI awareness", exc_info=True)


# ── Static file server ───────────────────────────────────────────────


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Suppress request logging; add CORS headers; SPA fallback."""

    def log_message(self, format, *args):
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        if not os.path.exists(
            os.path.join(self.directory, self.path.lstrip("/"))
        ) and not self.path.startswith("/assets/"):
            self.path = "/index.html"
        return super().do_GET()


def start_vite_server() -> subprocess.Popen | None:
    frontend_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "frontend"
    )
    if not os.path.exists(frontend_dir):
        return None
    return subprocess.Popen(
        "npm run dev",
        shell=True,
        cwd=frontend_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def create_static_server(dist_dir: str, host: str, port: int) -> None:
    handler = functools.partial(QuietHandler, directory=dist_dir)
    with socketserver.TCPServer((host, port), handler) as httpd:
        httpd.serve_forever()


def wait_for_server(url: str, timeout: float = 3.0) -> bool:
    for _ in range(int(timeout / 0.1)):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


# ── Window sizing ─────────────────────────────────────────────────────


def get_adaptive_size() -> tuple[int, int]:
    try:
        phys_w, phys_h = get_physical_screen_size()
        width = max(int(phys_w * 0.5), LIMIT_MIN_WIDTH)
        height = max(int(phys_h * 0.5), LIMIT_MIN_HEIGHT)
        return width, height
    except Exception:
        return LIMIT_MIN_WIDTH, LIMIT_MIN_HEIGHT


def get_resource_path(relative_path: str) -> str:
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# ── pywebview lifecycle callbacks ─────────────────────────────────────


def on_start(window: object, *, actual_title: str, api: Api, tray: TrayManager | None) -> None:
    """Called after the webview window has fully loaded."""
    api.set_window(window, actual_title)
    if tray is not None:
        tray.set_window(window)

    # Sync native title-bar + background on a background thread
    threading.Thread(
        target=api.sync_titlebar_immediate,
        args=(api.get_saved_theme(),),
        daemon=True,
    ).start()

    # Set window icons (DPI-adaptive)
    def _setup_icon():
        time.sleep(0.5)
        hwnd = find_window_by_title(actual_title)
        if hwnd:
            icon_path = get_resource_path("assets/app_logo.ico")
            if os.path.exists(icon_path):
                set_titlebar_icon(hwnd, icon_path)
                set_taskbar_icon(hwnd, icon_path)

    threading.Thread(target=_setup_icon, daemon=True).start()
    window.evaluate_js('console.log("窗口已启动")')


def on_closed(tray: TrayManager | None) -> None:
    if tray:
        tray.stop()


# ── Entry point ───────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()

    vite_process = None
    title = f"{APP_TITLE} (Dev)" if args.dev else APP_TITLE
    api = Api()

    if args.dev:
        vite_process = start_vite_server()
        url = VITE_URL
    else:
        dist_dir = get_resource_path("dist")
        url = f"http://{APP_HOST}:{APP_PORT}"
        threading.Thread(
            target=create_static_server,
            args=(dist_dir, APP_HOST, APP_PORT),
            daemon=True,
        ).start()
        wait_for_server(url)

    init_width, init_height = get_adaptive_size()
    window = webview.create_window(
        title,
        url=url,
        js_api=api,
        width=init_width,
        height=init_height,
        min_size=(init_width, init_height),
        resizable=True,
        frameless=False,
    )

    # Tray setup
    tray: TrayManager | None = None
    if HAS_TRAY:
        tray = TrayManager(api, get_resource_path)
        threading.Thread(target=tray.run, daemon=True).start()
    else:
        logger.info("pystray/Pillow not installed — system tray disabled")

    window.events.closed += lambda: on_closed(tray)

    # pywebview.start() only passes positional args to the callback,
    # so we capture the extra context via a closure.
    def _on_start(win):
        on_start(win, actual_title=title, api=api, tray=tray)

    try:
        webview.start(
            _on_start,
            args=(window,),
            debug=args.dev,
            gui="edgechromium",
        )
    finally:
        if tray:
            tray.stop()
        if vite_process:
            subprocess.call(
                ["taskkill", "/F", "/T", "/PID", str(vite_process.pid)]
            )


if __name__ == "__main__":
    main()
