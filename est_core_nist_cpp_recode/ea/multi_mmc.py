"""NIST SP 800-90B Entropy Assessment - MultiMMC (Section 6.3.9)"""

from __future__ import annotations

import numpy as np

from ._config import D_MMC, MAX_ENTRIES
from ._util import prediction_estimate


def binary_multi_mmc_test(
    data: np.ndarray, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.9: Multi Markov Model with Counting (MultiMMC) Test.
    Binary-optimized version.
    Returns min-entropy estimate via prediction estimate framework.
    """
    D = D_MMC
    scoreboard = [0] * D
    binary_dict = [np.zeros(1 << (d + 2), dtype=np.int64) for d in range(D)]
    dict_elems = [0] * D
    winner = 0

    cur_pattern = 0
    for d in range(D):
        cur_pattern |= (int(data[d]) & 1) << d
        idx = (cur_pattern << 1) | (int(data[d + 1]) & 1)
        binary_dict[d][idx] = 1
        dict_elems[d] = 1

    correct_count = 0
    cur_run = 0
    max_run = 0

    for i in range(2, length):
        cur_winner = winner
        cur_pattern = 0
        found_x = False

        for d in range(D):
            if d > i - 2:
                break
            cur_pattern |= (int(data[i - d - 1]) & 1) << d
            cur_pattern &= (1 << (d + 1)) - 1

            entry = binary_dict[d]

            if d == 0 or found_x:
                idx = (cur_pattern << 1)
                c0 = entry[idx]
                c1 = entry[idx + 1]
                if c0 > c1:
                    cur_prediction = 0
                    cur_count = c0
                else:
                    cur_prediction = 1
                    cur_count = c1
                found_x = cur_count > 0

            if found_x:
                cur_sym = int(data[i]) & 1
                if cur_prediction == cur_sym:
                    scoreboard[d] += 1
                    if scoreboard[d] >= scoreboard[winner]:
                        winner = d
                    if d == cur_winner:
                        correct_count += 1
                        cur_run += 1
                        if cur_run > max_run:
                            max_run = cur_run
                elif d == cur_winner:
                    cur_run = 0

                entry[(cur_pattern << 1) | cur_sym] += 1
            elif dict_elems[d] < MAX_ENTRIES:
                entry[(cur_pattern << 1) | (int(data[i]) & 1)] = 1
                dict_elems[d] += 1

    return prediction_estimate(correct_count, length - 2, max_run, 2, "MultiMMC", verbose, label)


def multi_mmc_test(
    data: np.ndarray, length: int, alph_size: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.9: MultiMMC Test (general alphabet).
    Uses PostfixDictionary for each context length.
    """
    if alph_size == 2:
        return binary_multi_mmc_test(data, length, verbose, label)

    from ._types import PostfixDictionary

    D = D_MMC
    scoreboard = [0] * D
    dicts = [PostfixDictionary() for _ in range(D)]
    winner = 0

    correct_count = 0
    cur_run = 0
    max_run = 0

    for i in range(1, length):
        cur_winner = winner
        found_x = False
        cur_prediction = 0
        cur_count = 0

        for d in range(D):
            if d > i - 1:
                break

            if d == 0 or found_x:
                cur_count, cur_prediction = dicts[d].predict()
                found_x = cur_count > 0

            if found_x:
                if cur_prediction == int(data[i]):
                    scoreboard[d] += 1
                    if scoreboard[d] >= scoreboard[winner]:
                        winner = d
                    if d == cur_winner:
                        correct_count += 1
                        cur_run += 1
                        if cur_run > max_run:
                            max_run = cur_run
                elif d == cur_winner:
                    cur_run = 0

                new_entry = dicts[d].increment_postfix(int(data[i]), True)
                if new_entry and len(dicts[d]._postfixes) >= MAX_ENTRIES:
                    pass
            else:
                new_entry = dicts[d].increment_postfix(int(data[i]), True)
                if new_entry and len(dicts[d]._postfixes) >= MAX_ENTRIES:
                    pass

    return prediction_estimate(correct_count, length - 1, max_run, alph_size, "MultiMMC", verbose, label)
