"""
NIST SP800-90B entropy test runner for the pywebview frontend.

Wraps est_core functions (main_restart / main_iid / main_noniid) and
returns structured dicts that the JS-API bridge can serialise directly.

Runs each test in a **subprocess** so that all memory used by est_core
(dataset arrays, caches, imported modules) is fully reclaimed by the OS
when the subprocess exits.  On Windows, ``gc.collect()`` alone cannot
return memory to the OS because CPython's pymalloc holds onto freed
blocks — a subprocess is the only reliable solution.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from multiprocessing import Process, Queue

logger = logging.getLogger(__name__)

# -- Ensure est_core is importable ----------------------------------------

_CORE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "est_core")
)
if os.path.isdir(_CORE_DIR) and _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)


# ---------------------------------------------------------------------------
# Subprocess worker
# ---------------------------------------------------------------------------


class _QueueIO:
    """File-like object that feeds writes into a *multiprocessing.Queue*."""

    def __init__(self, q: Queue) -> None:  # type: ignore[type-arg]
        self._q = q

    def write(self, text: str) -> int:
        self._q.put({"type": "log", "line": text})
        return len(text)

    def flush(self) -> None:
        pass

    def fileno(self):
        raise OSError("QueueIO does not support fileno()")


def _subprocess_worker(payload: dict, log_queue: Queue) -> None:  # type: ignore[type-arg]
    """Entry point for the child process.

    *payload* contains all test parameters.  *log_queue* is a
    ``multiprocessing.Queue`` used to stream log lines and the final
    result back to the main process.
    """
    old_stdout = sys.stdout
    try:
        sys.stdout = _QueueIO(log_queue)  # type: ignore[assignment]

        from main_restart import main_restart  # type: ignore[import-not-found]
        from main_iid import main_iid  # type: ignore[import-not-found]
        from main_noniid import main_noniid  # type: ignore[import-not-found]

        datafile = str(payload.get("datafile", "")).strip()
        bits_per_symbol = int(payload.get("bits_per_symbol") or 8)
        verbose = bool(payload.get("verbose", False))
        mode = str(payload.get("mode", "")).strip().lower()

        if mode == "restart":
            h_i = payload.get("h_i")
            if h_i is None:
                raise ValueError("Restart 测试需要填写 H_I")
            result = main_restart(datafile, bits_per_symbol, float(h_i), verbose)
            body = {"data": {"Restart_Test": result}}

        elif mode == "iid":
            result = main_iid(datafile, bits_per_symbol, verbose)
            body = {"data": {"IID_Test": result}}

        elif mode == "noniid":
            use_bits = payload.get("use_bits")
            use_bits = int(use_bits) if use_bits is not None else None
            result = main_noniid(datafile, bits_per_symbol, use_bits, verbose)
            body = {"data": {"Non_IID_Test": result}}

        else:
            raise ValueError(f"未知测试模式: {mode}")

        log_queue.put({"type": "result", "data": body})

    except Exception as exc:
        logger.exception("Entropy test failed (mode=%s)", payload.get("mode"))
        log_queue.put({"type": "error", "message": str(exc)})

    finally:
        sys.stdout = old_stdout
        log_queue.put({"type": "done"})


# ---------------------------------------------------------------------------
# Main-process state
# ---------------------------------------------------------------------------

_subprocess: Process | None = None  # type: ignore[type-arg]
_log_queue: Queue | None = None  # type: ignore[type-arg]
_done_seen = False


# ---------------------------------------------------------------------------
# Public API (called via the pywebview JS-API bridge)
# ---------------------------------------------------------------------------


def start_entropy_test(payload: dict) -> dict:
    """Validate *payload* and launch the test in a child process.

    Returns ``{"ok": True}`` on success, or ``{"ok": False, "error": "..."}``.
    """
    global _subprocess, _log_queue, _done_seen

    if _subprocess is not None and _subprocess.is_alive():
        return {"ok": False, "error": "已有测试在运行"}

    # -- Validate ---------------------------------------------------------

    datafile = str(payload.get("datafile", "")).strip()
    if not datafile or not os.path.isfile(datafile):
        return {"ok": False, "error": f"数据文件未找到: {datafile}"}

    mode = str(payload.get("mode", "")).strip().lower()
    if mode not in ("restart", "iid", "noniid"):
        return {"ok": False, "error": f"未知测试模式: {mode}"}

    bits_per_symbol = int(payload.get("bits_per_symbol") or 8)
    if not (1 <= bits_per_symbol <= 8):
        return {"ok": False, "error": "bits_per_symbol 必须在 1~8 之间"}

    if mode == "restart" and payload.get("h_i") is None:
        return {"ok": False, "error": "Restart 测试需要填写 H_I"}

    # -- Launch subprocess ------------------------------------------------

    _log_queue = Queue(maxsize=4096)
    _done_seen = False

    _subprocess = Process(
        target=_subprocess_worker,
        args=(payload, _log_queue),
        daemon=True,
    )
    _subprocess.start()
    return {"ok": True}


def poll_entropy_test() -> dict:
    """Non-blocking poll: drain log messages from the child process.

    Returns ``{"logs": [...], "running": bool}``.
    Once the ``"done"`` sentinel is seen the subprocess is joined
    so that its memory is released by the OS.
    """
    global _subprocess, _log_queue, _done_seen

    logs: list[dict] = []

    if _log_queue is not None:
        while True:
            try:
                msg = _log_queue.get_nowait()
                if msg.get("type") == "done":
                    _done_seen = True
                else:
                    logs.append(msg)
            except Exception:
                break

    # Determine if still running
    alive = _subprocess is not None and _subprocess.is_alive()

    # Once done-sentinel received and queue drained, join to free OS memory
    if _done_seen and not alive and _subprocess is not None:
        _subprocess.join(timeout=5)
        _subprocess = None
        _log_queue = None

    return {"logs": logs, "running": alive or not _done_seen}


def cleanup_entropy_test() -> None:
    """Best-effort cleanup.  Most memory is already freed when the
    subprocess exits and is joined in ``poll_entropy_test``.
    """
    global _subprocess, _log_queue, _done_seen
    if _subprocess is not None:
        if _subprocess.is_alive():
            _subprocess.terminate()
        _subprocess.join(timeout=3)
    _subprocess = None
    _log_queue = None
    _done_seen = False
