"""NIST SP 800-90B Entropy Assessment - optional JIT support

Four estimates walk the sample one symbol at a time while carrying online state
(a scoreboard, a dictionary budget, a sliding window), so neither the walk nor
its update order can be expressed as numpy operations. In CPython those loops
are the wall-clock floor of the non-IID assessment; compiled machine code runs
the very same loop 50-70x faster.

numba is an *optional* dependency and every kernel here has a plain-Python twin
that stays authoritative:

* the twins make the JIT side testable - :mod:`est_test_nist_cpp_recode.jit_crosscheck`
  runs both over every reference sample and requires identical counts;
* with numba absent, broken, or disabled, the estimates fall back to the Python
  loop and the reported numbers do not change by one bit.

``numba`` is imported on first use rather than at module scope: loading it costs
about half a second, which is worth nothing on the ten-thousand-sample files
where a whole estimate takes milliseconds. :data:`JIT_MIN_SAMPLES` is where the
saved time starts to outweigh that load.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Optional

from ._parallel import frozen

#: Environment switch to keep the Python loops even where numba is installed:
#: ``EA_DISABLE_JIT=1`` makes a run comparable with a pre-JIT build of the same tree.
DISABLE_ENV = "EA_DISABLE_JIT"

#: Below this many samples a kernel cannot pay for loading numba. Chosen as the
#: break-even point: the Python MultiMMC loop costs ~9 us per sample, so 100_000
#: samples is ~1 s of work against a ~0.5 s load (a cold compile is ~1.6 s).
JIT_MIN_SAMPLES = 100_000

_lock = threading.Lock()
_njit: Optional[Callable[..., Any]] = None
_tried = False


def numba_njit() -> Optional[Callable[..., Any]]:
    """``numba.njit`` ready for use, or None when the JIT is not in play.

    Frozen builds are excluded on purpose: a packed executable has to carry
    llvmlite's binaries along and may not own a writable directory for the
    ``cache=True`` artefacts, so those builds keep running the Python loops.
    """
    global _njit, _tried
    if _tried or frozen() or os.environ.get(DISABLE_ENV, "") not in ("", "0"):
        return _njit
    with _lock:
        if not _tried:
            try:
                from numba import njit as _impl
            except Exception:  # noqa: BLE001 - any import failure means "no JIT"
                _impl = None
            _njit = _impl
            _tried = True
    return _njit


def available() -> bool:
    """True once numba has been loaded successfully (never triggers the load)."""
    return _njit is not None


def use_jit(length: int) -> bool:
    """Whether a per-sample loop of ``length`` samples should be compiled."""
    return length >= JIT_MIN_SAMPLES and numba_njit() is not None


class Kernel:
    """A machine-code version of one plain-Python estimate loop.

    ``fn`` is written for CPython and for numba at the same time - plain ints,
    ``range`` loops and fixed-dtype numpy arrays - so the proxy stays correct
    even if numba turns out to be unusable when the first call arrives. The
    ``cache=True`` artefacts make the load in a fresh process ~0.5 s instead of
    a ~1.6 s compile, which matters because every pool worker pays it once.
    """

    __slots__ = ("plain", "_compiled", "_tried")

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.plain = fn
        self._compiled: Optional[Callable[..., Any]] = None
        self._tried = False

    def __call__(self, *args: Any) -> Any:
        if self._compiled is None and not self._tried:
            impl = numba_njit()
            if impl is not None:
                try:
                    self._compiled = impl(cache=True)(self.plain)
                except Exception:  # noqa: BLE001 - compile trouble is not fatal
                    self._compiled = None
            self._tried = True
        fn = self._compiled if self._compiled is not None else self.plain
        return fn(*args)

    @property
    def compiled(self) -> Optional[Callable[..., Any]]:
        """The numba callable, for a tool that wants to compare the two paths."""
        return self._compiled

    @property
    def active(self) -> Optional[Callable[..., Any]]:
        """What a call would run right now."""
        return self._compiled if self._compiled is not None else self.plain
