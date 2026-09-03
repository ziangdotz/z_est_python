"""NIST SP 800-90B Entropy Assessment - MultiMCW (Section 6.3.7)"""

from __future__ import annotations

import numpy as np

from ._config import NUM_WINS, W
from ._jit import Kernel, use_jit
from ._util import prediction_estimate

#: ``W`` as it reaches the kernel - numba cannot walk a global Python list.
_W_ARRAY = np.array(W, dtype=np.int64)


def _multi_mcw_counts(syms: list, length: int, alph_size: int) -> tuple:
    """
    The MultiMCW prediction loop, returning ``(C, max_run_len)``.

    This is the CPython version: one window walk at a time over the sample and
    over the four windows, so it runs on plain Python integers - numpy scalars
    cost several times as much per access and this loop is accessed
    ``4 * length`` times.
    """
    scoreboard = [0] * NUM_WINS
    win_cnts = [[0] * alph_size for _ in range(NUM_WINS)]
    win_poses = [[0] * alph_size for _ in range(NUM_WINS)]
    max_cnts = [0] * NUM_WINS
    frequent = [0] * NUM_WINS

    # compute initial window counts
    for i in range(W[-1]):
        cur = syms[i]
        for j in range(NUM_WINS):
            if i < W[j]:
                cnts = win_cnts[j]
                cnts[cur] += 1
                if max_cnts[j] <= cnts[cur]:
                    max_cnts[j] = cnts[cur]
                    frequent[j] = cur
                win_poses[j][cur] = i

    winner = 0
    C = 0
    run_len = 0
    max_run_len = 0

    # perform predictions
    for i in range(W[0], length):
        cur = syms[i]
        if frequent[winner] == cur:
            C += 1
            run_len += 1
            if run_len > max_run_len:
                max_run_len = run_len
        else:
            run_len = 0

        # update scoreboard and select new winner
        for j in range(NUM_WINS):
            if i >= W[j] and frequent[j] == cur:
                scoreboard[j] += 1
                if scoreboard[j] >= scoreboard[winner]:
                    winner = j

        # update window counts and select new frequents
        for j in range(NUM_WINS):
            if i < W[j]:
                continue
            out = syms[i - W[j]]
            cnts = win_cnts[j]
            cnts[out] -= 1
            cnt = cnts[cur] + 1
            cnts[cur] = cnt
            poses = win_poses[j]
            poses[cur] = i

            if out != frequent[j]:
                if max_cnts[j] <= cnt:
                    max_cnts[j] = cnt
                    frequent[j] = cur
                continue

            # The incumbent just lost its leading copy, so the reference rescans
            # the alphabet for a symbol with the largest count and - on equal
            # counts - the most recent position (a full tie hands the crown to the
            # larger symbol, since the comparison is ``max_pos <= win_poses[k]``).
            # The old incumbent starts out as the incumbent-to-beat with position
            # ``i - W[j]``, the copy that just left the window. The scan can push
            # the count back above the value it started from, so the result has to
            # be written back rather than kept in the local.
            max_cnt = max_cnts[j] - 1
            best = frequent[j]
            best_pose = i - W[j]
            for k in range(alph_size):
                kcnt = cnts[k]
                if kcnt > max_cnt or (kcnt == max_cnt and best_pose <= poses[k]):
                    max_cnt = kcnt
                    best = k
                    best_pose = poses[k]
            max_cnts[j] = max_cnt
            frequent[j] = best

    return C, max_run_len


@Kernel
def _multi_mcw_kernel(syms, length, alph_size, wins):
    """
    Same loop as :func:`_multi_mcw_counts`, written so that numba can compile
    it: the per-window tables are ``int64`` arrays, so the rescan over the
    alphabet and the four count updates stay in machine code. ``wins`` is
    :data:`._config.W` as an array - a global Python list has no numba type -
    and the loop body is otherwise the one above, comments and tie-breaking
    included. ``est_test_nist_cpp_recode/jit_crosscheck.py`` checks they agree.
    """
    NW = NUM_WINS

    scoreboard = np.zeros(NW, dtype=np.int64)
    win_cnts = np.zeros((NW, alph_size), dtype=np.int64)
    win_poses = np.zeros((NW, alph_size), dtype=np.int64)
    max_cnts = np.zeros(NW, dtype=np.int64)
    frequent = np.zeros(NW, dtype=np.int64)

    for i in range(int(wins[NW - 1])):
        cur = int(syms[i])
        for j in range(NW):
            if i < wins[j]:
                cnts = win_cnts[j]
                cnts[cur] += 1
                if max_cnts[j] <= cnts[cur]:
                    max_cnts[j] = cnts[cur]
                    frequent[j] = cur
                win_poses[j][cur] = i

    winner = 0
    C = 0
    run_len = 0
    max_run_len = 0

    for i in range(int(wins[0]), length):
        cur = int(syms[i])
        if frequent[winner] == cur:
            C += 1
            run_len += 1
            if run_len > max_run_len:
                max_run_len = run_len
        else:
            run_len = 0

        for j in range(NW):
            if i >= wins[j] and frequent[j] == cur:
                scoreboard[j] += 1
                if scoreboard[j] >= scoreboard[winner]:
                    winner = j

        for j in range(NW):
            if i < wins[j]:
                continue
            out = int(syms[i - int(wins[j])])
            cnts = win_cnts[j]
            cnts[out] -= 1
            cnt = cnts[cur] + 1
            cnts[cur] = cnt
            poses = win_poses[j]
            poses[cur] = i

            if out != frequent[j]:
                if max_cnts[j] <= cnt:
                    max_cnts[j] = cnt
                    frequent[j] = cur
                continue

            max_cnt = max_cnts[j] - 1
            best = frequent[j]
            best_pose = i - wins[j]
            for k in range(alph_size):
                kcnt = cnts[k]
                if kcnt > max_cnt or (kcnt == max_cnt and best_pose <= poses[k]):
                    max_cnt = kcnt
                    best = k
                    best_pose = poses[k]
            max_cnts[j] = max_cnt
            frequent[j] = best

    return C, max_run_len


def multi_mcw_test(
    data: np.ndarray, length: int, alph_size: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.7: Multi Most Common in Window (MultiMCW) Test.
    Returns min-entropy estimate via prediction estimate framework.

    Both paths below count the same predictions; only the estimate step is shared.
    """
    if length < W[-1] + 1:
        return -1.0

    if use_jit(length):
        C, max_run_len = _multi_mcw_kernel(
            np.ascontiguousarray(data[:length], dtype=np.uint8), length, alph_size, _W_ARRAY)
    else:
        C, max_run_len = _multi_mcw_counts(data.astype(np.int64).tolist(), length, alph_size)

    N = length - W[0]
    return prediction_estimate(C, N, max_run_len, alph_size, "MultiMCW", verbose, label)
