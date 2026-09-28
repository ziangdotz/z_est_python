"""
NIST SP800-90B Entropy Test Runner — pywebview frontend backend.

Provides progress-aware test orchestration for three NIST test modes
(Restart, IID, Non-IID) and exposes a JSON-serialisable API for the
Vue 3 frontend via the pywebview JS-API bridge.

Each test runs in a **subprocess** so that all memory used by est_core
(dataset arrays, caches, imported modules) is fully reclaimed by the OS
when the subprocess exits.  On Windows, ``gc.collect()`` alone cannot
return memory because CPython's pymalloc holds onto freed blocks — a
subprocess is the only reliable solution.
"""

from __future__ import annotations

import logging
import math
import os
import sys
import time
from multiprocessing import Process, Queue

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path setup — ensure est_core is importable in both main & child processes
# ---------------------------------------------------------------------------

_CORE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "est_core")
)
if os.path.isdir(_CORE_DIR) and _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

# ---------------------------------------------------------------------------
# est_core entry points — these must stay at module level
#
# Nuitka's standalone analysis only follows top-level imports: left inside the
# worker functions below, these modules and the numpy / mpmath stack they pull
# in never reach the frozen artifact, so the exe builds cleanly and then fails
# at runtime.
# ---------------------------------------------------------------------------
from chiSquareTest import chiSquareTest  # type: ignore[import-not-found]
from collision import theCollisionEstimate  # type: ignore[import-not-found]
from compression import theCompressionEstimate  # type: ignore[import-not-found]
from longestRepeatedSubstring import (  # type: ignore[import-not-found]
    lenOfTheLongestRepeatedSubstringTest,
    longestRepeatedSubstringEstimate,
)
from markov import theMarkovEstimate  # type: ignore[import-not-found]
from mostCommonValue import (  # type: ignore[import-not-found]
    mostCommonValueRestart,
    theMostCommonValueEstimate,
)
from permutationTest import permutationTest  # type: ignore[import-not-found]
from SP80090Bv2Predictors import (  # type: ignore[import-not-found]
    LagPredictionEstimate,
    LZ78YPredictionEstimate,
    MultiMCWPredictionEstimate,
    MultiMMCPredictionEstimate,
)
from tTuple import tTupleEstimate  # type: ignore[import-not-found]
from util import get_z, map_data, to_dataset  # type: ignore[import-not-found]


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


# ---------------------------------------------------------------------------
#  Progress helper
# ---------------------------------------------------------------------------


def _emit(log_queue: Queue, value: float) -> None:  # type: ignore[type-arg]
    """Non-blocking put of a progress message (0.0 – 1.0)."""
    try:
        log_queue.put_nowait({"type": "progress", "value": round(value, 4)})
    except Exception:
        pass  # queue full or broken; progress is best-effort


# ===========================================================================
#  Progress-aware test runners
#
#  Each function replicates the orchestration logic of its est_core
#  counterpart (main_restart / main_iid / main_noniid) while emitting
#  progress messages between stages.  No est_core files are modified.
# ===========================================================================


def _run_restart(payload: dict, log_queue: Queue) -> dict:  # type: ignore[type-arg]
    """Restart validation with sub-progress within row/column loops."""

    datafile = str(payload.get("datafile", "")).strip()
    bits_per_symbol = int(payload.get("bits_per_symbol") or 8)
    verbose = bool(payload.get("verbose", False))
    H_I = float(payload.get("h_i"))

    with open(datafile, "rb") as fh:
        # -- Data loading ---------------------------------------------------
        raw = bytearray(fh.read())
        dataset = to_dataset(raw, bits_per_symbol)
        k = len(set(dataset))
        _emit(log_queue, 0.05)

        if verbose:
            print("file and dataset details")
            print("Read in file %s, %d bytes long." % (datafile, len(raw)))
            print(
                "Dataset: %d %d-bit symbols, %d symbols in alphabet."
                % (len(dataset), bits_per_symbol, k)
            )
            print("Output symbol values: min = %d, max = %d" % (min(dataset), max(dataset)))

        _min_entropy = float(math.log(k, 2))
        assert len(dataset) == 1_000_000

        alpha = 0.01 / (2000 * k)

        # -- Row analysis (1 000 rows) --------------------------------------
        if verbose:
            print("\nRunning sanity check on row dataset:")

        f = [0] * 1000
        for i in range(1000):
            f[i] = mostCommonValueRestart(dataset[i * 1000 : (i + 1) * 1000])
            if (i + 1) % 100 == 0:
                _emit(log_queue, 0.05 + 0.40 * ((i + 1) / 1000))

        F_R = max(f)
        _emit(log_queue, 0.45)
        if verbose:
            print("- F_R: %d" % F_R)

        # -- Column analysis (1 000 columns) --------------------------------
        if verbose:
            print("Running sanity check on column dataset:")

        f = [0] * 1000
        for i in range(1000):
            column = [dataset[j * 1000 + i] for j in range(1000)]
            f[i] = mostCommonValueRestart(column)
            if (i + 1) % 100 == 0:
                _emit(log_queue, 0.45 + 0.45 * ((i + 1) / 1000))

        F_C = max(f)
        _emit(log_queue, 0.90)
        if verbose:
            print("- F_C: %d" % F_C)

        # -- Confidence-interval validation ---------------------------------
        F = max(F_R, F_C)
        p = math.pow(2, -H_I)
        Z = get_z(alpha)
        U = 1000 * p + Z * math.sqrt(1000 * p * (1 - p))
        if verbose:
            print("U: %f" % U)

        if F > U:
            print("Failed the restart tests")
            print("*** Validation failed. No entropy estimate awarded.")
            _emit(log_queue, 1.0)
            return {"passed": False, "H_I": None, "F": F, "U": U}

        print("Passed the restart tests")
        print("*** Final entropy estimate: %f" % H_I)
        _emit(log_queue, 1.0)
        return {"passed": True, "H_I": H_I, "F": F, "U": U}


def _run_iid(payload: dict, log_queue: Queue) -> dict:  # type: ignore[type-arg]
    """IID entropy estimation with stage-level progress reporting."""

    t0 = time.perf_counter()

    datafile = str(payload.get("datafile", "")).strip()
    bits_per_symbol = int(payload.get("bits_per_symbol") or 8)
    verbose = bool(payload.get("verbose", False))

    with open(datafile, "rb") as fh:
        # -- Data loading ---------------------------------------------------
        raw = bytearray(fh.read())
        dataset = to_dataset(raw, bits_per_symbol)
        k = len(set(dataset))
        _emit(log_queue, 0.05)

        if verbose:
            print("file and dataset details")
            print("Read in file %s, %d bytes long." % (datafile, len(raw)))
            print(
                "Dataset: %d %d-bit symbols, %d symbols in alphabet."
                % (len(dataset), bits_per_symbol, k)
            )
            print("Output symbol values: min = %d, max = %d\n" % (min(dataset), max(dataset)))

        # -- Permutation test -----------------------------------------------
        if permutationTest(dataset, verbose):
            if verbose:
                print("** Passed IID permutation tests")
        else:
            if verbose:
                print("** Failed IID permutation tests")
            print("IID = False")
            _emit(log_queue, 0.60)
            return {"IID": False, "min_entropy": None, "reason": "Failed IID permutation tests"}

        _emit(log_queue, 0.60)

        # -- Chi-square test ------------------------------------------------
        if chiSquareTest(dataset, verbose):
            if verbose:
                print("** Passed chi square tests")
        else:
            if verbose:
                print("** Failed chi square tests")
            print("IID = False")
            _emit(log_queue, 0.75)
            return {"IID": False, "min_entropy": None, "reason": "Failed chi square tests"}

        _emit(log_queue, 0.75)

        # -- Longest Repeated Substring test --------------------------------
        if lenOfTheLongestRepeatedSubstringTest(dataset, verbose):
            if verbose:
                print("** Passed LRS test")
            print("\nIID = True")
        else:
            print("** Failed LRS test")
            print("IID = False")
            _emit(log_queue, 0.90)
            return {"IID": False, "min_entropy": None, "reason": "Failed LRS test"}

        _emit(log_queue, 0.90)

        # -- Most Common Value entropy estimate -----------------------------
        _pmax, minH = theMostCommonValueEstimate(dataset)
        print("min-entropy = %g" % minH)
        print(
            "\nDon't forget to run the sanity check on a restart dataset using H_I = %g"
            % minH
        )
        print("Running time: %s Seconds" % (time.perf_counter() - t0))

        _emit(log_queue, 1.0)
        return {"IID": True, "min_entropy": minH}


def _run_noniid(payload: dict, log_queue: Queue) -> dict:  # type: ignore[type-arg]
    """Non-IID entropy estimation with stage-level progress reporting."""

    t0 = time.perf_counter()

    datafile = str(payload.get("datafile", "")).strip()
    bits_per_symbol = int(payload.get("bits_per_symbol") or 8)
    verbose = bool(payload.get("verbose", False))
    use_bits = payload.get("use_bits")
    use_bits = int(use_bits) if use_bits is not None else bits_per_symbol

    results: dict = {}

    with open(datafile, "rb") as fh:
        # -- Data loading ---------------------------------------------------
        raw = bytearray(fh.read())
        dataset = to_dataset(raw, bits_per_symbol)
        k = len(set(dataset))
        _emit(log_queue, 0.02)

        if verbose:
            print("file and dataset details")
            print("Read in file %s, %d bytes long." % (datafile, len(raw)))
            print(
                "Dataset: %d %d-bit symbols, %d symbols in alphabet."
                % (len(dataset), bits_per_symbol, k)
            )
            print("Output symbol values: min = %d, max = %d" % (min(dataset), max(dataset)))

        if use_bits < bits_per_symbol:
            mask = (2 ** use_bits) - 1
            dataset = [s & mask for s in dataset]
            k = len(set(dataset))
            if verbose:
                print(
                    "* Using only low %d bits out of %d. %d symbols in reduced alphabet."
                    % (use_bits, bits_per_symbol, k)
                )
                print(
                    "* Using output symbol values: min = %d, max = %d"
                    % (min(dataset), max(dataset))
                )

        mapped = map_data(dataset)
        min_entropy = float(math.log(k, 2))

        if verbose:
            print("\nRunning entropic statistic estimates:")

        # Section 6.3.1 — Most Common Value
        pmax, minH = theMostCommonValueEstimate(dataset)
        results["MCV"] = minH
        _emit(log_queue, 0.04)
        if verbose:
            print("- Most Common Value Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        min_entropy = min(minH, min_entropy)

        # Section 6.3.2 — Collision
        pmax, minH = theCollisionEstimate(dataset, k)
        results["Collision"] = minH
        _emit(log_queue, 0.12)
        if verbose:
            if minH is None:
                print("- Collision Estimate: not applicable (v < 1000), excluded from the minimum")
            else:
                print("- Collision Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        if minH is not None:
            min_entropy = min(minH, min_entropy)

        # Section 6.3.3 — Markov
        if use_bits > 6:
            pmax, minH = theMarkovEstimate([s & 63 for s in dataset], 64, 0.99)
            if verbose:
                print(
                    "- Markov Estimate (map 6 bits): p(max) = %g, min-entropy = %g"
                    % (pmax, minH)
                )
        else:
            pmax, minH = theMarkovEstimate(mapped, k, 0.99)
            if verbose:
                print("- Markov Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        results["Markov"] = minH
        _emit(log_queue, 0.20)
        min_entropy = min(minH, min_entropy)

        # Section 6.3.4 — Compression
        pmax, minH = theCompressionEstimate(mapped, k)
        results["Compression"] = minH
        _emit(log_queue, 0.28)
        if verbose:
            print("- Compression Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        min_entropy = min(minH, min_entropy)

        # Section 6.3.5 — t-Tuple
        pmax, minH = tTupleEstimate(dataset)
        results["t-Tuple"] = minH
        _emit(log_queue, 0.40)
        if verbose:
            print("- t-Tuple Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        min_entropy = min(minH, min_entropy)

        # Section 6.3.6 — Longest Repeated Substring
        pmax, minH = longestRepeatedSubstringEstimate(dataset)
        results["LRS"] = minH
        _emit(log_queue, 0.52)
        if verbose:
            print("- LRS Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        min_entropy = min(minH, min_entropy)

        if verbose:
            print("\nRunning predictor estimates:")

        # Section 6.3.7 — Multi Most Common in Window
        pmax, minH = MultiMCWPredictionEstimate(dataset, verbose)
        results["MultiMCW"] = minH
        _emit(log_queue, 0.64)
        if verbose:
            print("MultiMCW Prediction Estimate: p(max) = %g, min-entropy = %g\n" % (pmax, minH))
        min_entropy = min(minH, min_entropy)

        # Section 6.3.8 — Lag Prediction
        pmax, minH = LagPredictionEstimate(dataset, verbose)
        results["Lag"] = minH
        _emit(log_queue, 0.76)
        if verbose:
            print("Lag Prediction Estimate: p(max) = %g, min-entropy = %g\n" % (pmax, minH))
        min_entropy = min(minH, min_entropy)

        # Section 6.3.9 — MultiMMC Prediction
        pmax, minH = MultiMMCPredictionEstimate(dataset, verbose)
        results["MultiMMC"] = minH
        _emit(log_queue, 0.88)
        if verbose:
            print("MultiMMC Prediction Estimate: p(max) = %g, min-entropy = %g\n" % (pmax, minH))
        min_entropy = min(minH, min_entropy)

        # Section 6.3.10 — LZ78Y Prediction
        pmax, minH = LZ78YPredictionEstimate(dataset, verbose)
        results["LZ78Y"] = minH
        _emit(log_queue, 0.96)
        if verbose:
            print("LZ78Y Prediction Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        min_entropy = min(minH, min_entropy)

        print("min-entropy = %g" % min_entropy)
        print(
            "\nDon't forget to run the sanity check on a restart dataset using H_I = %g"
            % min_entropy
        )
        print("Running time: %s Seconds" % (time.perf_counter() - t0))

        _emit(log_queue, 1.0)
        return {"min_entropy": min_entropy, "details": results}


# ===========================================================================
#  Subprocess worker
# ===========================================================================


def _subprocess_worker(payload: dict, log_queue: Queue) -> None:  # type: ignore[type-arg]
    """Child-process entry point.

    Replaces ``sys.stdout`` with a :class:`_QueueIO` so every ``print()``
    from the runner functions is streamed back as a log message.  On
    success a ``result`` message is posted; on failure an ``error``
    message.  A ``done`` sentinel is always posted last.
    """
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

    bits_per_symbol = int(payload.get("bits_per_symbol") or 8)
    if not (1 <= bits_per_symbol <= 8):
        return {"ok": False, "error": "bits_per_symbol 必须在 1~8 之间"}

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
