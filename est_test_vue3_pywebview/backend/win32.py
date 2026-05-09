"""
Win32 API helpers for window management and theming.

Consolidates all ctypes-based Win32 operations:
window icon management, DPI detection, dark-mode title bar,
native background color, and HWND lookup utilities.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment,misc]

# ── Win32 constants ──────────────────────────────────────────────────
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
GCLP_HICONSM = -34
GCLP_HICON = -14
GCLP_HBRBACKGROUND = -10
_GWL_STYLE: int = -16
_WS_CAPTION: int = 0x00C00000

DWMWA_USE_IMMERSIVE_DARK_MODE = 20

SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOOWNERZORDER = 0x0200
SWP_FLAGS = (
    SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE
    | SWP_NOZORDER | SWP_NOOWNERZORDER
)

user32 = ctypes.windll.user32  # type: ignore[attr-defined]


# ══════════════════════════════════════════════════════════════════════
# Window icon management (from main.py)
# ══════════════════════════════════════════════════════════════════════


def find_window_by_title(title: str) -> int | None:
    """Find a visible HWND whose title contains *title*."""
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if title in buf.value:
                result.append(hwnd)
        return True

    user32.EnumWindows(enum_callback, 0)
    return result[0] if result else None


def get_system_dpi() -> int:
    """Return the system DPI without requiring a window handle.

    Uses GetDpiForSystem (Win 10+) with fallback to GDI LOGPIXELSX.
    Works before any window is created.
    """
    try:
        return user32.GetDpiForSystem()
    except Exception:
        try:
            hdc = user32.GetDC(0)  # desktop DC
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            user32.ReleaseDC(0, hdc)
            return dpi
        except Exception:
            return 96


def get_physical_screen_size() -> tuple[int, int]:
    """Return the primary monitor's physical pixel resolution.

    Uses SM_CXSCREEN / SM_CYSCREEN which always report real device
    pixels regardless of the calling process's DPI-awareness level.
    """
    try:
        w = user32.GetSystemMetrics(0)   # SM_CXSCREEN
        h = user32.GetSystemMetrics(1)   # SM_CYSCREEN
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    try:
        hdc = ctypes.windll.gdi32.CreateDCW("DISPLAY", None, None, None)
        w = ctypes.windll.gdi32.GetDeviceCaps(hdc, 8)   # HORZRES
        h = ctypes.windll.gdi32.GetDeviceCaps(hdc, 10)  # VERTRES
        ctypes.windll.gdi32.DeleteDC(hdc)
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return 1920, 1080


def get_dpi_for_window(hwnd: int) -> int:
    """Return the DPI of the display that contains *hwnd*."""
    try:
        return user32.GetDpiForWindow(hwnd)
    except Exception:
        try:
            hdc = user32.GetDC(hwnd)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            user32.ReleaseDC(hwnd, hdc)
            return dpi
        except Exception:
            return 96


def _dpi_scale_icon_size(base_size: int, dpi: int, standards: tuple[int, ...]) -> int:
    """Scale *base_size* by *dpi* and snap to the nearest standard icon size."""
    size = int(base_size * dpi / 96)
    for standard in standards:
        if size <= standard:
            return standard
    return size


def set_titlebar_icon(hwnd: int, icon_path: str) -> None:
    """Set the title-bar small icon (DPI-adaptive)."""
    dpi = get_dpi_for_window(hwnd)
    size = _dpi_scale_icon_size(16, dpi, (16, 24, 32, 48))
    hicon = user32.LoadImageW(
        None, icon_path, IMAGE_ICON, size, size, LR_LOADFROMFILE
    )
    if hicon:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
        user32.SetClassLongPtrW(hwnd, GCLP_HICONSM, hicon)


def set_taskbar_icon(hwnd: int, icon_path: str) -> None:
    """Set the taskbar / Alt+Tab large icon (DPI-adaptive)."""
    dpi = get_dpi_for_window(hwnd)
    size = _dpi_scale_icon_size(32, dpi, (32, 48, 64, 128, 256))
    hicon = user32.LoadImageW(
        None, icon_path, IMAGE_ICON, size, size, LR_LOADFROMFILE
    )
    if hicon:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
        user32.SetClassLongPtrW(hwnd, GCLP_HICON, hicon)


# ══════════════════════════════════════════════════════════════════════
# Dark-mode title bar & native background (from api.py)
# ══════════════════════════════════════════════════════════════════════


def set_window_dark_titlebar(hwnd: int, dark: bool) -> None:
    """Set the Windows title bar to light/dark mode."""
    value = ctypes.c_int(1 if dark else 0)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(value), ctypes.sizeof(value),
    )
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)


def set_native_background(hwnd: int, dark: bool) -> None:
    """Set the Win32 native window background color."""
    color = 0x001E1E1E if dark else 0x00F3F3F3
    brush = ctypes.windll.gdi32.CreateSolidBrush(color)
    old = ctypes.windll.user32.SetClassLongPtrW(
        hwnd, GCLP_HBRBACKGROUND, brush)
    if old:
        ctypes.windll.gdi32.DeleteObject(old)
    ctypes.windll.user32.InvalidateRect(hwnd, None, True)
    ctypes.windll.user32.UpdateWindow(hwnd)


# ══════════════════════════════════════════════════════════════════════
# HWND lookup utilities (from api.py)
# ══════════════════════════════════════════════════════════════════════


def find_hwnd_by_title(title: str) -> int | None:
    """Find a window HWND by exact title match."""
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    return hwnd if hwnd else None


def find_main_hwnd() -> int | None:
    """Find the current process's main window HWND by PID."""
    current_pid = os.getpid()
    result = [None]

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_callback(hwnd, lparam):
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == current_pid and ctypes.windll.user32.IsWindowVisible(hwnd):
            style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_STYLE)
            if style & _WS_CAPTION:
                result[0] = hwnd
                return False
        return True

    ctypes.windll.user32.EnumWindows(enum_callback, 0)
    return result[0]
