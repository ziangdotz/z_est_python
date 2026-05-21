"""NIST SP 800-90B Entropy Assessment - MultiMCW (Section 6.3.7)"""

from __future__ import annotations

import numpy as np

from ._config import NUM_WINS, W
from ._util import prediction_estimate


def multi_mcw_test(
    data: np.ndarray, length: int, alph_size: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.7: Multi Most Common in Window (MultiMCW) Test.
    Returns min-entropy estimate via prediction estimate framework.
    """
    if length < W[-1] + 1:
        return -1.0

    scoreboard = [0] * NUM_WINS
    win_cnts = [np.zeros(alph_size, dtype=np.int64) for _ in range(NUM_WINS)]
    win_poses = [np.zeros(alph_size, dtype=np.int64) for _ in range(NUM_WINS)]
    max_cnts = [0] * NUM_WINS
    frequent = [0] * NUM_WINS

    for i in range(W[-1]):
        for j in range(NUM_WINS):
            if i < W[j]:
                sym = int(data[i])
                win_cnts[j][sym] += 1
                if win_cnts[j][sym] >= max_cnts[j]:
                    max_cnts[j] = win_cnts[j][sym]
                    frequent[j] = sym
                win_poses[j][sym] = i

    winner = 0
    C = 0
    run_len = 0
    max_run_len = 0

    for i in range(W[0], length):
        cur_sym = int(data[i])
        if frequent[winner] == cur_sym:
            C += 1
            run_len += 1
            if run_len > max_run_len:
                max_run_len = run_len
        else:
            run_len = 0

        for j in range(NUM_WINS):
            if i >= W[j] and frequent[j] == cur_sym:
                scoreboard[j] += 1
                if scoreboard[j] >= scoreboard[winner]:
                    winner = j

        for j in range(NUM_WINS):
            if i >= W[j]:
                out_sym = int(data[i - W[j]])
                in_sym = cur_sym
                win_cnts[j][out_sym] -= 1
                win_cnts[j][in_sym] += 1
                win_poses[j][in_sym] = i

                if out_sym != frequent[j] and max_cnts[j] <= win_cnts[j][in_sym]:
                    max_cnts[j] = win_cnts[j][in_sym]
                    frequent[j] = in_sym
                elif out_sym == frequent[j]:
                    max_cnts[j] -= 1
                    if max_cnts[j] < win_cnts[j][in_sym]:
                        max_cnts[j] = win_cnts[j][in_sym]
                        frequent[j] = in_sym
                    else:
                        idx = int(np.argmax(win_cnts[j]))
                        if win_cnts[j][idx] > max_cnts[j]:
                            max_cnts[j] = win_cnts[j][idx]
                            frequent[j] = idx

    N = length - W[0]
    return prediction_estimate(C, N, max_run_len, alph_size, "MultiMCW", verbose, label)
