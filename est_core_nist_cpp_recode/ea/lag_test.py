"""NIST SP 800-90B Entropy Assessment - Lag Prediction (Section 6.3.8)"""

from __future__ import annotations

import numpy as np

from ._config import D_LAG, LAGMASK
from ._types import LagBuffer
from ._util import prediction_estimate


def lag_test(
    data: np.ndarray, length: int, alph_size: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.8: Lag Prediction Test.
    Returns min-entropy estimate via prediction estimate framework.
    """
    scoreboard = [0] * D_LAG
    ring_buffers = [LagBuffer() for _ in range(alph_size)]

    ring_buffers[int(data[0])].buf[0] = 0
    ring_buffers[int(data[0])].start = 0
    ring_buffers[int(data[0])].end = 1

    winner = 0
    correct_count = 0
    cur_run = 0
    max_run = 0
    high_score = 0

    for i in range(1, length):
        cur_sym = int(data[i])
        cur_rb = ring_buffers[cur_sym]

        lag_idx = i - winner - 1
        if lag_idx >= 0 and int(data[lag_idx]) == cur_sym:
            correct_count += 1
            cur_run += 1
            if cur_run > max_run:
                max_run = cur_run
        else:
            cur_run = 0

        if cur_rb.start != cur_rb.end:
            cutoff = i - D_LAG if i >= D_LAG else 0
            ci = cur_rb.end
            while True:
                ci -= 1
                idx = ci & LAGMASK
                if cur_rb.buf[idx] >= cutoff:
                    offset = i - cur_rb.buf[idx] - 1
                    scoreboard[offset] += 1
                    if scoreboard[offset] >= high_score:
                        winner = offset
                        high_score = scoreboard[offset]
                else:
                    cur_rb.start = ci + 1
                    break
                if ci == cur_rb.start:
                    break

        if cur_rb.end - cur_rb.start == D_LAG:
            cur_rb.start += 1
        cur_rb.buf[cur_rb.end & LAGMASK] = i
        cur_rb.end += 1

    return prediction_estimate(correct_count, length - 1, max_run, alph_size, "Lag", verbose, label)
