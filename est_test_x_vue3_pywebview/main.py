"""
NIST SP800-90B Entropy Assessment Tool — application entry point.

Creates a pywebview window backed by either the Vite dev server
(``--dev``) or a bundled static-file server, and optionally starts
a system-tray icon for quick window toggling.

With ``--selftest`` no GUI is started: one minimal IID and Non-IID
estimation is pushed through the same ``Api`` the frontend uses, which is
the only way to tell whether a frozen build actually shipped the analysis
libraries (``ea`` / ``est_core`` and their numpy / scipy / numba stack).
"""

from __future__ import annotations

import argparse
import builtins
import ctypes
import functools
import http.server
import logging
import multiprocessing
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


# -- Static file server ---------------------------------------------------


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


# -- Window sizing --------------------------------------------------------


def get_adaptive_size() -> tuple[int, int]:
    try:
        phys_w, phys_h = get_physical_screen_size()
        width = max(int(phys_w * 0.610), LIMIT_MIN_WIDTH)
        height = max(int(phys_h * 0.610), LIMIT_MIN_HEIGHT)
        return width, height
    except Exception:
        return LIMIT_MIN_WIDTH, LIMIT_MIN_HEIGHT


def is_frozen() -> bool:
    """
    True when running out of a single-file executable (Nuitka, PyInstaller).

    The two packers advertise themselves in different places and no single name
    covers both:

    * PyInstaller sets ``sys.frozen`` and ``sys._MEIPASS``.
    * Nuitka sets neither. It injects ``__nuitka_binary_dir`` into ``builtins``
      (unconditionally in standalone mode) and hangs ``__compiled__`` off modules
      and functions - not off ``sys``, so ``hasattr(sys, "__compiled__")`` is just
      as false here as ``sys.frozen`` is.

    Testing either ``sys`` name therefore reports a Nuitka build as a plain source
    checkout, which is what made the frontend check below skip itself.
    ``ea._parallel.frozen()`` shares the blind spot.
    """
    return bool(
        getattr(sys, "frozen", False)
        or hasattr(sys, "_MEIPASS")
        or hasattr(builtins, "__nuitka_binary_dir")
        or "__compiled__" in globals()
    )


def get_resource_path(relative_path: str) -> str:
    if is_frozen():
        # PyInstaller names the unpacked payload directory ``sys._MEIPASS``; Nuitka
        # never sets that name, it puts the binary directory in the builtin
        # ``__nuitka_binary_dir``. Taking the first that exists lets one source tree
        # work for both, with ``__file__`` - which Nuitka also points into the
        # payload - left as the fallback for packers advertising neither.
        base_path = (
            getattr(sys, "_MEIPASS", None)
            or getattr(builtins, "__nuitka_binary_dir", None)
            or os.path.dirname(os.path.abspath(__file__))
        )
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# -- pywebview lifecycle callbacks ----------------------------------------


def on_start(
    window: object,
    *,
    actual_title: str,
    api: Api,
    tray: TrayManager | None,
) -> None:
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


# -- Headless self test --------------------------------------------------

# A onefile build can be built successfully and still be unusable: anything the
# runner modules import from inside a function never reaches the binary.  These
# helpers run one real estimation per (engine, mode) pair so that question is
# answered by an exit code instead of by clicking through the UI.

SELFTEST_SAMPLE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "8ckup",
    "NIST_SP800-90B_EntropyAssessment",
    "bin",
    "rand4_short.bin",
)


def selftest_dataset() -> str:
    """Return a 10 000-symbol 4-bit dataset — the C++ project's short sample
    when the repository is around, otherwise a deterministic synthetic copy,
    because a frozen build has no repository next to it."""
    path = os.path.normpath(SELFTEST_SAMPLE)
    if os.path.isfile(path):
        return path

    import random
    import tempfile

    path = os.path.join(tempfile.gettempdir(), "est_selftest_rand4.bin")
    if not os.path.isfile(path):
        rng = random.Random(0x5EED)
        with open(path, "wb") as fh:
            fh.write(bytes(rng.randrange(16) for _ in range(10000)))
    return path


def selftest_leg(
    api: Api,
    engine: str,
    mode: str,
    datafile: str,
    timeout: float,
    report,
) -> bool:
    """Run one *engine*/*mode* combination; True once a numeric min-entropy
    comes back from the worker process."""
    label = "%s/%s" % (engine, mode)
    started = api.start_entropy_test({
        "mode": mode,
        "datafile": datafile,
        "bits_per_symbol": 4,
        "verbose": 0,
        "use_nist_cpp_recode": engine == "nist",
    })
    if not started.get("ok"):
        report("FAIL  %-12s %s" % (label, started.get("error", "start failed")))
        return False

    min_entropy: object = None
    error: str | None = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        poll = api.poll_entropy_test()
        for msg in poll.get("logs", []):
            if msg.get("type") == "result":
                tests = msg.get("data", {}).get("data", {})
                body = next(iter(tests.values()), {})
                min_entropy = body.get("min_entropy")
            elif msg.get("type") == "error":
                error = msg.get("message")
        if not poll.get("running"):
            break
        time.sleep(0.2)
    api.cleanup_entropy_test()

    if error:
        report("FAIL  %-12s %s" % (label, error))
        return False
    if not isinstance(min_entropy, (int, float)) or min_entropy <= 0:
        report("FAIL  %-12s no numeric min_entropy (got %r)" % (label, min_entropy))
        return False

    report("PASS  %-12s min_entropy=%.6f" % (label, min_entropy))
    return True


def selftest_frontend(report) -> bool:
    """Inside a onefile payload the Vue bundle travels with the code; a build
    that dropped ``dist`` opens a blank window, so check where it landed."""
    dist_dir = get_resource_path("dist")
    if not is_frozen():
        report("SKIP  frontend     only checked in a frozen build")
        return True
    ok = os.path.isdir(dist_dir) and os.path.isfile(
        os.path.join(dist_dir, "index.html"))
    report("%-5s frontend     %s" % ("PASS" if ok else "FAIL", dist_dir))
    return ok


def run_selftest(all_engines: bool, timeout: float, log_path: str | None) -> int:
    """Headless smoke test; returns the process exit code (0 = everything passed)."""
    lines: list[str] = []
    report = lines.append

    datafile = selftest_dataset()
    report("dataset: %s" % datafile)
    report("frozen:  %s" % is_frozen())
    if is_frozen():
        # Name every signal that actually fired: the packers disagree about where
        # they announce themselves, and a silent SKIP is how that disagreement hid.
        signals = [
            name for name, present in (
                ("sys.frozen", bool(getattr(sys, "frozen", False))),
                ("sys._MEIPASS", hasattr(sys, "_MEIPASS")),
                ("sys.__compiled__", hasattr(sys, "__compiled__")),
                ("builtins.__nuitka_binary_dir", hasattr(builtins, "__nuitka_binary_dir")),
                ("module.__compiled__", "__compiled__" in globals()),
            ) if present
        ]
        report("signals: %s" % (", ".join(signals) or "(none)"))
        report("paths:   resource_base=%s" % get_resource_path(""))

    engines = ["nist", "orig"] if all_engines else ["nist"]
    api = Api()
    passed = [
        selftest_leg(api, engine, mode, datafile, timeout, report)
        for engine in engines
        for mode in ("iid", "noniid")
    ]
    passed.append(selftest_frontend(report))

    ok = all(passed)
    report("SELFTEST %s (%d/%d checks)" % ("PASS" if ok else "FAIL", sum(passed), len(passed)))
    text = "\n".join(lines) + "\n"
    if log_path:
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0 if ok else 1


# -- Entry point ----------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    parser.add_argument(
        "--selftest", action="store_true",
        help="run one headless estimation per mode and exit (0 = pass)")
    parser.add_argument(
        "--selftest-all", action="store_true",
        help="with --selftest: also cover the slow pure-Python est_core engine")
    parser.add_argument(
        "--selftest-timeout", type=float, default=900.0,
        help="seconds a single selftest leg may take (default: 900)")
    parser.add_argument(
        "--selftest-log", default=None,
        help="write selftest output to this file instead of stdout (a --windows-console-mode=disable "
             "build has no stdout to write to)")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(run_selftest(args.selftest_all, args.selftest_timeout, args.selftest_log))

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
    # The assessment spreads its estimates over worker processes. In a onefile
    # build a spawned child re-runs this executable, and without the call below
    # it would boot another window instead of running its task; the pipelines
    # keep multiprocessing off when they detect a frozen build, so this only
    # matters for a run that asks for workers explicitly.
    multiprocessing.freeze_support()
    main()
