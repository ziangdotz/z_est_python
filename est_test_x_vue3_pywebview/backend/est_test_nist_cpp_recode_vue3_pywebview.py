"""
NIST SP800-90B Entropy Test Runner (C++ Recode) — pywebview frontend backend.

Provides progress-aware test orchestration for three NIST test modes
(Restart, IID, Non-IID) using the ``est_core_nist_cpp_recode`` library,
and exposes a JSON-serialisable API for the Vue 3 frontend via the
pywebview JS-API bridge.

Each test runs in a **subprocess** so that all memory used by the core
library is fully reclaimed by the OS when the subprocess exits.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from multiprocessing import Process, Queue

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path setup — ensure est_core_nist_cpp_recode is importable
# ---------------------------------------------------------------------------

_CORE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "est_core_nist_cpp_recode")
)
if os.path.isdir(_CORE_DIR) and _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)


# ===========================================================================
#  Subprocess internals
# ===========================================================================


class _QueueIO:
    """File-like shim that redirects ``sys.stdout`` writes into a Queue."""

    __slots__ = ("_q",)

    def __init__(self, q: Queue) -> None:  # type: ignore[type-arg]
        self._q = q

    def write(self, text: str) -> int:
        self._q.put({"type": "log", "line": text})
        return len(text)

    def flush(self) -> None:
        pass

    def fileno(self) -> int:
        raise OSError("QueueIO does not support fileno()")


def _emit(log_queue: Queue, value: float) -> None:  # type: ignore[type-arg]
    """Non-blocking put of a progress message (0.0 – 1.0)."""
    try:
        log_queue.put_nowait({"type": "progress", "value": round(value, 4)})
    except Exception:
        pass


# ===========================================================================
#  Progress-aware test runners
# ===========================================================================


def _run_restart(payload: dict, log_queue: Queue) -> dict:  # type: ignore[type-arg]
    """Restart validation via ``est_core_nist_cpp_recode``."""

    from ea.restart import restart_test  # type: ignore[import-not-found]

    datafile = str(payload.get("datafile", "")).strip()
    H_I = float(payload.get("h_i"))
    verbose = int(payload.get("verbose", 1))

    _emit(log_queue, 0.05)
    if verbose:
        print("file and dataset details")
        print("Read in file %s" % datafile)

    try:
        h_min = restart_test(
            file_path=datafile,
            H_I=H_I,
            iid=False,
            verbose=verbose,
        )
    except RuntimeError as exc:
        print("*** Validation failed. No entropy estimate awarded.")
        print("*** %s" % str(exc))
        _emit(log_queue, 1.0)
        return {"passed": False, "H_I": None, "F": None, "U": None}

    print("Passed the restart tests")
    print("*** Final entropy estimate: %f" % h_min)
    _emit(log_queue, 1.0)
    return {"passed": True, "H_I": h_min, "F": None, "U": None}


def _run_iid(payload: dict, log_queue: Queue) -> dict:  # type: ignore[type-arg]
    """IID entropy estimation via ``est_core_nist_cpp_recode``."""

    from ea.iid_pipeline import run_iid_test  # type: ignore[import-not-found]

    datafile = str(payload.get("datafile", "")).strip()
    bits_per_symbol = int(payload.get("bits_per_symbol") or 0)
    verbose = int(payload.get("verbose", 1))
    initial = bool(payload.get("initial", True))
    all_bits = bool(payload.get("all_bits", True))

    _emit(log_queue, 0.05)
    if verbose:
        print("file and dataset details")
        print("Read in file %s" % datafile)

    run = run_iid_test(
        file_path=datafile,
        bits_per_symbol=bits_per_symbol,
        initial=initial,
        all_bits=all_bits,
        verbose=verbose,
    )

    if run.error_level != 0:
        print("IID = False")
        _emit(log_queue, 1.0)
        return {"IID": False, "min_entropy": None, "reason": run.error_msg}

    tc = run.test_cases[0]

    print("\nIID = True")
    print("H_original: %g" % tc.h_original)
    print("H_bitstring: %g" % tc.h_bitstring)
    print("H_assessed: %g" % tc.h_assessed)

    _emit(log_queue, 1.0)
    return {"IID": True, "min_entropy": tc.h_assessed}


def _run_noniid(payload: dict, log_queue: Queue) -> dict:  # type: ignore[type-arg]
    """Non-IID entropy estimation via ``est_core_nist_cpp_recode``."""

    from ea.non_iid_pipeline import run_non_iid_test  # type: ignore[import-not-found]

    t0 = time.perf_counter()

    datafile = str(payload.get("datafile", "")).strip()
    bits_per_symbol = int(payload.get("bits_per_symbol") or 0)
    verbose = int(payload.get("verbose", 1))

    _emit(log_queue, 0.02)
    if verbose:
        print("file and dataset details")
        print("Read in file %s" % datafile)

    run = run_non_iid_test(
        file_path=datafile,
        bits_per_symbol=bits_per_symbol,
        verbose=verbose,
    )

    if run.error_level != 0:
        print("Non-IID test failed: %s" % run.error_msg)
        _emit(log_queue, 1.0)
        return {"min_entropy": None, "details": {}, "error": run.error_msg}

    # Map test case labels to frontend estimator names
    ESTIMATOR_MAP = {
        "Most Common Value": "MCV",
        "Collision Test (for bit strings only)": "Collision",
        "Markov Test (for bit strings only)": "Markov",
        "Compression Test (for bit strings only)": "Compression",
        "T-Tuple Test": "t-Tuple",
        "LRS Test": "LRS",
        "Multi Most Common in Window Test": "MultiMCW",
        "Lag Prediction Test": "Lag",
        "Multi Markov Model with Counting Test (MultiMMC)": "MultiMMC",
        "LZ78Y Test": "LZ78Y",
    }

    details: dict = {}
    for tc in run.test_cases:
        name = ESTIMATOR_MAP.get(tc.test_case_number)
        if name is None:
            continue

        val = tc.h_original
        if val is None or val < 0:
            val = tc.h_bitstring
        if val is None or val < 0:
            val = getattr(tc, "t_tuple_res", None)
        if val is None or val < 0:
            val = getattr(tc, "lrs_res", None)
        if val is not None and val >= 0:
            details[name] = val

    # Find overall min-entropy
    min_entropy: float | None = None
    for tc in run.test_cases:
        if tc.test_case_number == "Overall":
            min_entropy = tc.h_assessed
            break
    if min_entropy is None and details:
        min_entropy = min(details.values())

    print("min-entropy = %g" % min_entropy if min_entropy is not None else "N/A")
    print("Running time: %s Seconds" % (time.perf_counter() - t0))

    _emit(log_queue, 1.0)
    return {"min_entropy": min_entropy, "details": details}


# ===========================================================================
#  Subprocess worker
# ===========================================================================


def _subprocess_worker(payload: dict, log_queue: Queue) -> None:  # type: ignore[type-arg]
    """Child-process entry point."""
    old_stdout = sys.stdout
    try:
        sys.stdout = _QueueIO(log_queue)  # type: ignore[assignment]

        mode = str(payload.get("mode", "")).strip().lower()

        if mode == "restart":
            if payload.get("h_i") is None:
                raise ValueError("Restart 测试需要填写 H_I")
            body = {"data": {"Restart_Test": _run_restart(payload, log_queue)}}

        elif mode == "iid":
            body = {"data": {"IID_Test": _run_iid(payload, log_queue)}}

        elif mode == "noniid":
            body = {"data": {"Non_IID_Test": _run_noniid(payload, log_queue)}}

        else:
            raise ValueError("未知测试模式: %s" % mode)

        log_queue.put({"type": "result", "data": body})

    except Exception as exc:
        logger.exception("Entropy test failed (mode=%s)", payload.get("mode"))
        log_queue.put({"type": "error", "message": str(exc)})

    finally:
        sys.stdout = old_stdout
        log_queue.put({"type": "done"})


# ===========================================================================
#  Main-process state
# ===========================================================================

_subprocess: Process | None = None  # type: ignore[type-arg]
_log_queue: Queue | None = None  # type: ignore[type-arg]
_done_seen: bool = False
_last_progress: float | None = None


# ===========================================================================
#  Public API  (called via pywebview JS-API bridge)
# ===========================================================================


def start_entropy_test(payload: dict) -> dict:
    """Validate *payload* and launch the test in a child process.

    Returns ``{"ok": True}`` on success, or ``{"ok": False, "error": "..."}``.
    """
    global _subprocess, _log_queue, _done_seen, _last_progress

    if _subprocess is not None and _subprocess.is_alive():
        return {"ok": False, "error": "已有测试在运行"}

    # -- Validate -----------------------------------------------------------

    datafile = str(payload.get("datafile", "")).strip()
    if not datafile or not os.path.isfile(datafile):
        return {"ok": False, "error": "数据文件未找到: %s" % datafile}

    mode = str(payload.get("mode", "")).strip().lower()
    if mode not in ("restart", "iid", "noniid"):
        return {"ok": False, "error": "未知测试模式: %s" % mode}

    bits_per_symbol = int(payload.get("bits_per_symbol") or 0)
    if not (0 <= bits_per_symbol <= 16):
        return {"ok": False, "error": "bits_per_symbol 必须在 0~16 之间"}

    if mode == "restart" and payload.get("h_i") is None:
        return {"ok": False, "error": "Restart 测试需要填写 H_I"}

    # -- Launch subprocess --------------------------------------------------

    _log_queue = Queue(maxsize=4096)
    _done_seen = False
    _last_progress = None

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
    When progress messages have been received, a ``"progress"`` key
    (float 0.0–1.0) is included.  Once the ``"done"`` sentinel arrives
    the subprocess is joined so its memory is released by the OS.
    """
    global _subprocess, _log_queue, _done_seen, _last_progress

    logs: list[dict] = []

    if _log_queue is not None:
        while True:
            try:
                msg = _log_queue.get_nowait()
                if msg.get("type") == "done":
                    _done_seen = True
                elif msg.get("type") == "progress":
                    _last_progress = msg.get("value", 0.0)
                else:
                    logs.append(msg)
            except Exception:
                break

    alive = _subprocess is not None and _subprocess.is_alive()

    if _done_seen and not alive and _subprocess is not None:
        _subprocess.join(timeout=5)
        _subprocess = None
        _log_queue = None

    result: dict = {"logs": logs, "running": alive or not _done_seen}
    if _last_progress is not None:
        result["progress"] = _last_progress
    return result


def cleanup_entropy_test() -> None:
    """Best-effort cleanup: terminate the subprocess and release resources."""
    global _subprocess, _log_queue, _done_seen, _last_progress
    if _subprocess is not None:
        if _subprocess.is_alive():
            _subprocess.terminate()
        _subprocess.join(timeout=3)
    _subprocess = None
    _log_queue = None
    _done_seen = False
    _last_progress = None
