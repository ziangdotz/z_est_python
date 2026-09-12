"""NIST SP 800-90B Entropy Assessment - process pool helpers

Several stages of the assessment are embarrassingly parallel: independent passes
over the same read-only sample, with no random numbers and no shared state.
Spreading them over processes turns "sum of the parts" into "most expensive
part", which is worth doing for the estimates that take tens of seconds each.

Two constraints shape the helpers here:

* starting a worker can be impossible (a frozen executable without
  ``freeze_support()``, a host with no spare process slots), and that has to
  degrade into a plain serial run instead of failing halfway through an
  assessment;
* the reference writes its ``verbose`` progress to stdout in a fixed order that
  the pipelines reproduce line for line, so work that moves into a worker has to
  carry the lines it printed back to the caller.
"""

from __future__ import annotations

import io
import multiprocessing
import os
import sys
import weakref
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from typing import Any, Callable, Dict, Hashable, Optional, Sequence, Tuple

_Job = Tuple[Hashable, Callable[..., Any], Sequence[Any]]


def frozen() -> bool:
    """
    True when running out of a single-file executable (Nuitka, PyInstaller).

    A frozen build has no interpreter to hand a spawned child: the child just
    re-runs the executable, which only behaves when the entry point calls
    ``multiprocessing.freeze_support()`` and every module the child needs got
    packed along. Whether that holds is a packaging question, so an
    auto-selected worker count stays at one until the build says otherwise.
    """
    return bool(getattr(sys, "frozen", False) or hasattr(sys, "__compiled__"))


def auto_workers() -> int:
    """
    Worker count for a caller that named none: one per physical core.

    The passes stream megabytes per sample, so an SMT sibling adds little
    throughput while competing for the memory bandwidth the parent needs.
    An explicit count overrides this, a frozen build does not get one at all.
    """
    return 1 if frozen() else max(1, (os.cpu_count() or 1) // 2)


def inside_worker() -> bool:
    """
    True when this process is itself a pool worker.

    Workers started for one stage of the assessment must not start a pool of
    their own: a nested ``ProcessPoolExecutor`` multiplies the process count with
    the nesting depth, which is how a bounded run turns into hundreds of
    interpreters.
    """
    return multiprocessing.parent_process() is not None


def _probe() -> bool:
    """Target that proves :func:`open_pool` can run work at all."""
    return True


def open_pool(
    workers: int,
    subject: str = "running the estimates",
    initializer: Optional[Callable[..., Any]] = None,
    initargs: Sequence[Any] = (),
) -> Optional[ProcessPoolExecutor]:
    """
    Start ``workers`` worker processes, or return None where spawning is not
    available.

    ``ProcessPoolExecutor`` only spawns on the first submission, so an entry
    point that cannot spawn would otherwise fail partway through the assessment.
    The probe spends one worker startup to turn that into a serial run.

    ``initializer``/``initargs`` hand the sample to each worker once instead of
    with every task; ``subject`` names what the caller will fall back to doing in
    this process, for the warning line.
    """
    pool = ProcessPoolExecutor(
        max_workers=workers,
        initializer=initializer,
        initargs=tuple(initargs),
    )
    try:
        assert pool.submit(_probe).result()
    except (AssertionError, RuntimeError, OSError) as exc:
        # ``AssertionError`` is the daemon case: ``BaseProcess.start()`` refuses to
        # spawn from a daemon process, which is exactly how a GUI backend runs an
        # assessment - in a daemon child of its own.  Degrade like every other
        # unspawnable host instead of failing halfway through.
        pool.shutdown(wait=False, cancel_futures=True)
        print(f"\t*** Warning: cannot start worker processes ({exc}); "
              f"{subject} in this process only ***")
        return None
    return pool


def _shutdown(pool: ProcessPoolExecutor) -> None:
    """Finalizer target; holds no reference back to the owning object."""
    pool.shutdown(wait=True)


def capture(fn: Callable[..., Any], args: Sequence[Any]) -> Tuple[Any, str]:
    """
    Run ``fn(*args)`` and return its value together with whatever it printed.

    Used both in the worker and in the serial fallback, so the caller sees one
    shape of result either way and replays the progress lines itself.
    """
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        value = fn(*args)
    return value, buffer.getvalue()


class ParallelJobs:
    """
    A fixed set of independent jobs, spread over worker processes where possible.

    Everything is submitted in :meth:`__init__` so that no worker idles while the
    first result is awaited, yet :meth:`get` blocks per job, which lets the
    caller keep consuming - and printing - in the serial order the reference uses.

    Fewer than two jobs, or a requested worker count of one, skips the pool
    entirely and computes the whole set up front in this process.
    """

    def __init__(self, jobs: Sequence[_Job], workers: int) -> None:
        self._results: Dict[Hashable, Tuple[Any, str]] = {}
        self._futures: Dict[Hashable, Any] = {}
        self._pool: Optional[ProcessPoolExecutor] = None
        self._finalizer = None

        # One process per job is enough; a wider pool would only sit idle.
        workers = max(1, min(workers, len(jobs)))
        if workers > 1 and len(jobs) > 1 and not inside_worker():
            self._pool = open_pool(workers)

        if self._pool is None:
            for key, fn, args in jobs:
                self._results[key] = capture(fn, args)
            return

        submit = self._pool.submit
        for key, fn, args in jobs:
            self._futures[key] = submit(capture, fn, args)
        # An estimate that raises has to hand the workers back too, and the
        # interpreter may be long-lived (web service, GUI backend).
        self._finalizer = weakref.finalize(self, _shutdown, self._pool)

    def get(self, key: Hashable) -> Tuple[Any, str]:
        """The ``(value, printed text)`` of job ``key``, waiting if needed."""
        if key in self._results:
            return self._results[key]
        result = self._futures.pop(key).result()
        self._results[key] = result
        return result

    def close(self) -> None:
        """Release the workers; safe to call more than once."""
        pool, self._pool = self._pool, None
        if pool is None:
            return
        if self._finalizer is not None:
            self._finalizer.detach()
            self._finalizer = None
        pool.shutdown(wait=True)
