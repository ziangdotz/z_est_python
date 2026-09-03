"""NIST SP 800-90B Entropy Assessment - Lag Prediction (Section 6.3.8)"""

from __future__ import annotations

from bisect import bisect_left

import numpy as np

from ._config import D_LAG
from ._jit import Kernel, use_jit
from ._util import prediction_estimate


def _lag_counts(syms: list, length: int, alph_size: int) -> tuple:
    """
    The lag prediction loop, returning ``(correct_count, max_run)``.

    This is the CPython version. The reference keeps, per symbol, a ``lagBuf``:
    a 128 slot ring of the sample indices where that symbol was seen, plus head
    and tail pointers. A ring is not needed to reproduce it: at most ``D_LAG``
    samples lie within the window the walk stops at, so the ring can never hold
    an entry the window filter would keep but the ring would have dropped.
    Appending to a list and discarding everything older than the window is
    therefore equivalent, and iterating the list backwards visits the same
    entries in the same order - newest occurrence first, that is, ascending lag.
    """
    scoreboard = [0] * D_LAG
    occurs = [[] for _ in range(alph_size)]

    # Account for the very first symbol (there isn't a guess for this one).
    occurs[syms[0]].append(0)

    winner = 0
    correct_count = 0
    cur_run = 0
    max_run = 0
    high_score = 0

    # The rest of the values yield a prediction.
    for i in range(1, length):
        cur_sym = syms[i]
        seen = occurs[cur_sym]

        # Check the prediction first: ``winner`` is a lag picked at an earlier
        # sample, so it never reaches back past the start of the sample.
        lag_idx = i - winner - 1
        if lag_idx >= 0 and syms[lag_idx] == cur_sym:
            correct_count += 1
            cur_run += 1
            if cur_run > max_run:
                max_run = cur_run
        else:
            cur_run = 0

        # Update counters: every stored occurrence of this symbol that is still
        # within the last ``D_LAG`` samples scores the lag it implies. The
        # occurrences are stored oldest first and the window slides by one per
        # sample, so everything the walk would stop at sits in front.
        if seen:
            cutoff = i - D_LAG if i >= D_LAG else 0
            stale = bisect_left(seen, cutoff)
            if stale:
                del seen[:stale]
            for pos in reversed(seen):
                lag = i - pos - 1
                score = scoreboard[lag] + 1
                scoreboard[lag] = score
                if score >= high_score:
                    winner = lag
                    high_score = score

        # Add the new symbol.
        seen.append(i)

    return correct_count, max_run


@Kernel
def _lag_kernel(syms, length, alph_size):
    """
    Same loop as :func:`_lag_counts`, written so that numba can compile it:
    the reference's ``lagBuf`` verbatim - one row of ``D_LAG`` slots per symbol
    plus a count of how often that symbol has appeared, so no list ever grows
    and nothing is ever shifted.

    The ring holds the ``D_LAG`` newest occurrences, which can be *older* than
    the window for a rare symbol, so the walk still stops as soon as the lag
    leaves ``scoreboard`` - and since it runs newest to oldest, the lags only
    grow, making that a ``break`` and not a filter. ``est_test_nist_cpp_recode/
    jit_crosscheck.py`` checks the two bodies stay in lockstep.
    """
    D = D_LAG

    ring = np.zeros((alph_size, D), dtype=np.int64)
    counts = np.zeros(alph_size, dtype=np.int64)
    scoreboard = np.zeros(D, dtype=np.int64)

    first = int(syms[0])
    ring[first, 0] = 0
    counts[first] = 1

    winner = 0
    correct_count = 0
    cur_run = 0
    max_run = 0
    high_score = 0

    for i in range(1, length):
        sym = int(syms[i])

        lag_idx = i - winner - 1
        if lag_idx >= 0 and int(syms[lag_idx]) == sym:
            correct_count += 1
            cur_run += 1
            if cur_run > max_run:
                max_run = cur_run
        else:
            cur_run = 0

        n = counts[sym]
        valid = n if n < D else D
        for k in range(valid):
            pos = ring[sym, (n - 1 - k) % D]
            lag = i - pos - 1
            if lag >= D:
                break
            score = scoreboard[lag] + 1
            scoreboard[lag] = score
            if score >= high_score:
                high_score = score
                winner = lag

        ring[sym, n % D] = i
        counts[sym] = n + 1

    return correct_count, max_run


def lag_test(
    data: np.ndarray, length: int, alph_size: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.8: Lag Prediction Test.
    Returns min-entropy estimate via prediction estimate framework.

    Every sample walks the recorded occurrences of its own symbol back over the
    last ``D_LAG`` samples, scoring the lag each occurrence implies - a binary
    sample revisits some 60 of them per sample, which makes this the most
    expensive test of the suite in CPython. Both paths below count the same
    predictions; only the estimate step is shared.
    """
    if use_jit(length):
        correct_count, max_run = _lag_kernel(
            np.ascontiguousarray(data[:length], dtype=np.uint8), length, alph_size)
    else:
        correct_count, max_run = _lag_counts(data.astype(np.int64).tolist(), length, alph_size)

    return prediction_estimate(correct_count, length - 1, max_run, alph_size, "Lag", verbose, label)
