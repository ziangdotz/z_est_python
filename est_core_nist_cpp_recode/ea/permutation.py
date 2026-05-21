"""NIST SP 800-90B Entropy Assessment - Permutation Tests (19 tests)"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np

from ._config import PERMS
from ._rng import Xoshiro256StarStar
from ._types import DataT, IidTestCase, PermutationTestResult
from ._util import calc_stats

NUM_TESTS = 19
TEST_NAMES = [
    "excursion", "numDirectionalRuns", "lenDirectionalRuns",
    "numIncreasesDecreases", "numRunsMedian", "lenRunsMedian",
    "avgCollision", "maxCollision", "periodicity(1)", "periodicity(2)",
    "periodicity(8)", "periodicity(16)", "periodicity(32)",
    "covariance(1)", "covariance(2)", "covariance(8)",
    "covariance(16)", "covariance(32)", "compression",
]


def conversion1(data: np.ndarray, sample_size: int) -> np.ndarray:
    """Binary: partition into 8-bit blocks, count 1s in each block."""
    ret_size = (sample_size // 8) + (0 if sample_size % 8 == 0 else 1)
    ret = np.zeros(ret_size, dtype=np.uint8)
    for i in range(sample_size):
        ret[i // 8] += int(data[i])
    return ret


def conversion2(data: np.ndarray, sample_size: int) -> np.ndarray:
    """Binary: partition into 8-bit blocks, interpret as bytes."""
    ret_size = (sample_size // 8) + (0 if sample_size % 8 == 0 else 1)
    ret = np.zeros(ret_size, dtype=np.uint8)
    for i in range(sample_size):
        ret[i // 8] += int(data[i]) << (7 - i % 8)
    return ret


def excursion(data: np.ndarray, rawmean: float, sample_size: int) -> float:
    """5.1.1 Excursion Test."""
    max_d = 0.0
    running_sum = 0.0
    for i in range(sample_size):
        running_sum += int(data[i])
        d_i = abs(running_sum - (i + 1) * rawmean)
        if d_i > max_d:
            max_d = d_i
    return max_d


def alt_sequence1(data: np.ndarray, sample_size: int) -> np.ndarray:
    """Returns array of +1/-1 based on consecutive comparison."""
    ret = np.zeros(sample_size - 1, dtype=np.int32)
    for i in range(sample_size - 1):
        ret[i] = 1 if int(data[i]) <= int(data[i + 1]) else -1
    return ret


def alt_sequence2(data: np.ndarray, median: float, sample_size: int) -> np.ndarray:
    """Returns array of +1/-1 based on median comparison."""
    ret = np.zeros(sample_size, dtype=np.int32)
    for i in range(sample_size):
        ret[i] = 1 if int(data[i]) >= median else -1
    return ret


def num_directional_runs(alt_seq: np.ndarray) -> int:
    """5.1.2 Number of Directional Runs."""
    num_runs = 1 if len(alt_seq) > 0 else 0
    for i in range(1, len(alt_seq)):
        if alt_seq[i] != alt_seq[i - 1]:
            num_runs += 1
    return num_runs


def len_directional_runs(alt_seq: np.ndarray) -> int:
    """5.1.3 Length of Directional Runs."""
    max_run = 0
    run = 1
    for i in range(1, len(alt_seq)):
        if alt_seq[i] == alt_seq[i - 1]:
            run += 1
        else:
            if run > max_run:
                max_run = run
            run = 1
    if run > max_run:
        max_run = run
    return max_run


def num_increases_decreases(alt_seq: np.ndarray) -> int:
    """5.1.4 Number of Increases and Decreases."""
    pos = int(np.sum(alt_seq == 1))
    return max(pos, len(alt_seq) - pos)


def find_collisions(data: np.ndarray, n: int, k: int) -> List[int]:
    """Find collision lengths."""
    ret = []
    i = 0
    while i < n:
        dups = [False] * k
        j = 0
        while i + j < n:
            if dups[int(data[i + j])]:
                ret.append(j + 1)
                i += j
                j = 0
                break
            else:
                dups[int(data[i + j])] = True
                j += 1
        if j > 0 and i + j >= n:
            break
        i += 1
    return ret


def avg_collision(col_seq: List[int]) -> float:
    """5.1.7 Average Collision Test."""
    return sum(col_seq) / len(col_seq) if col_seq else 0.0


def max_collision(col_seq: List[int]) -> int:
    """5.1.8 Maximum Collision Test."""
    return max(col_seq) if col_seq else 0


def periodicity(data: np.ndarray, p: int, n: int) -> int:
    """5.1.9 Periodicity Test."""
    T = 0
    for i in range(n - p):
        if int(data[i]) == int(data[i + p]):
            T += 1
    return T


def covariance(data: np.ndarray, p: int, n: int) -> int:
    """5.1.10 Covariance Test."""
    T = 0
    for i in range(n - p):
        T += int(data[i]) * int(data[i + p])
    return T


def compression(data: np.ndarray, sample_size: int, max_symbol: int) -> int:
    """
    5.1.11 Compression Test.
    Uses bzip2 compression via bz2 module.
    """
    import bz2
    msg_parts = []
    for i in range(sample_size):
        msg_parts.append(str(int(data[i])))
    msg = " ".join(msg_parts).encode('ascii')
    compressed = bz2.compress(msg, compresslevel=5)
    return len(compressed)


def run_tests(
    dp: DataT,
    data: np.ndarray,
    rawdata: np.ndarray,
    rawmean: float,
    median: float,
    test_status: List[bool]
) -> np.ndarray:
    """Run all 19 tests, returns array of 19 float64 values."""
    stats = np.full(NUM_TESTS, -1.0, dtype=np.float64)

    if test_status[0]:
        stats[0] = excursion(rawdata, rawmean, dp.len)

    if test_status[1] or test_status[2] or test_status[3]:
        if dp.alph_size == 2:
            cs1 = conversion1(data, dp.len)
            alt_seq = alt_sequence1(cs1, len(cs1))
        else:
            alt_seq = alt_sequence1(data, dp.len)
        if test_status[1]:
            stats[1] = num_directional_runs(alt_seq)
        if test_status[2]:
            stats[2] = len_directional_runs(alt_seq)
        if test_status[3]:
            stats[3] = num_increases_decreases(alt_seq)

    if test_status[4] or test_status[5]:
        if dp.alph_size == 2:
            alt_seq = alt_sequence2(data, 0.5, dp.len)
        else:
            alt_seq = alt_sequence2(data, median, dp.len)
        if test_status[4]:
            stats[4] = num_directional_runs(alt_seq)
        if test_status[5]:
            stats[5] = len_directional_runs(alt_seq)

    if test_status[6] or test_status[7]:
        if dp.alph_size == 2:
            cs2 = conversion2(data, dp.len)
            col_seq = find_collisions(cs2, len(cs2), 256)
        else:
            col_seq = find_collisions(data, dp.len, dp.alph_size)
        if test_status[6]:
            stats[6] = avg_collision(col_seq)
        if test_status[7]:
            stats[7] = max_collision(col_seq)

    if test_status[8] or test_status[9] or test_status[10] or test_status[11] or test_status[12]:
        if dp.alph_size == 2:
            cs1 = conversion1(data, dp.len)
            cs_len = len(cs1)
            if test_status[8]:
                stats[8] = periodicity(cs1, 1, cs_len)
            if test_status[9]:
                stats[9] = periodicity(cs1, 2, cs_len)
            if test_status[10]:
                stats[10] = periodicity(cs1, 8, cs_len)
            if test_status[11]:
                stats[11] = periodicity(cs1, 16, cs_len)
            if test_status[12]:
                stats[12] = periodicity(cs1, 32, cs_len)
        else:
            if test_status[8]:
                stats[8] = periodicity(data, 1, dp.len)
            if test_status[9]:
                stats[9] = periodicity(data, 2, dp.len)
            if test_status[10]:
                stats[10] = periodicity(data, 8, dp.len)
            if test_status[11]:
                stats[11] = periodicity(data, 16, dp.len)
            if test_status[12]:
                stats[12] = periodicity(data, 32, dp.len)

    if test_status[13] or test_status[14] or test_status[15] or test_status[16] or test_status[17]:
        cov_data = data if dp.alph_size == 2 else rawdata
        if dp.alph_size == 2:
            cs1 = conversion1(data, dp.len)
            cov_data = cs1
            d_len = len(cs1)
        else:
            d_len = dp.len
        if test_status[13]:
            stats[13] = covariance(cov_data, 1, d_len)
        if test_status[14]:
            stats[14] = covariance(cov_data, 2, d_len)
        if test_status[15]:
            stats[15] = covariance(cov_data, 8, d_len)
        if test_status[16]:
            stats[16] = covariance(cov_data, 16, d_len)
        if test_status[17]:
            stats[17] = covariance(cov_data, 32, d_len)

    if test_status[18]:
        stats[18] = compression(rawdata, dp.len, dp.maxsymbol)

    return stats


def permutation_tests(
    dp: DataT, rawmean: float, median: float, verbose: int, tc: IidTestCase
) -> bool:
    """
    Full permutation test with PERMS rounds.
    Uses sequential execution (parallel version can be added later).
    """
    C = np.zeros((NUM_TESTS, 3), dtype=np.int64)
    test_status = [True] * NUM_TESTS

    t = run_tests(dp, dp.symbols, dp.rawsymbols, rawmean, median, test_status)

    if verbose == 2:
        print("Initial test results")
        for i in range(NUM_TESTS):
            print(f"  {TEST_NAMES[i]}: {t[i]}")
    elif verbose >= 3:
        for i in range(NUM_TESTS):
            print(f"Permutation testing: Unpermuted result {TEST_NAMES[i]} = {t[i]:.17g}")

    data = dp.symbols.copy()
    rawdata = dp.rawsymbols.copy()
    rng = Xoshiro256StarStar()

    for i in range(PERMS):
        rng.fy_shuffle(data, rawdata)
        tp = run_tests(dp, data, rawdata, rawmean, median, test_status)

        for j in range(NUM_TESTS):
            if test_status[j]:
                if tp[j] > t[j]:
                    C[j][0] += 1
                elif tp[j] == t[j]:
                    C[j][1] += 1
                else:
                    C[j][2] += 1
                if (C[j][0] + C[j][1] > 5) and (C[j][1] + C[j][2] > 5):
                    test_status[j] = False

    if verbose > 1:
        print("\n                statistic  C[i][0]  C[i][1]  C[i][2]")
        print("----------------------------------------------------")
        for i in range(NUM_TESTS):
            marker = "*" if (C[i][0] + C[i][1] <= 5) or (C[i][1] + C[i][2] <= 5) else " "
            print(f"{TEST_NAMES[i]:>24}{marker}{C[i][0]:>8}{C[i][1]:>8}{C[i][2]:>8}")
        print("(* denotes failed test)")

    tr0 = PermutationTestResult(iteration=0)
    tr1 = PermutationTestResult(iteration=1)
    tr2 = PermutationTestResult(iteration=2)

    for idx in range(NUM_TESTS):
        setattr(tr0, [
            "excursion", "num_directional_runs", "len_directional_runs",
            "num_increases_decreases", "num_runs_median", "len_runs_median",
            "avg_collision", "max_collision", "periodicity1", "periodicity2",
            "periodicity8", "periodicity16", "periodicity32",
            "covariance1", "covariance2", "covariance8",
            "covariance16", "covariance32", "compression",
        ][idx], float(C[idx][0]))
        setattr(tr1, [
            "excursion", "num_directional_runs", "len_directional_runs",
            "num_increases_decreases", "num_runs_median", "len_runs_median",
            "avg_collision", "max_collision", "periodicity1", "periodicity2",
            "periodicity8", "periodicity16", "periodicity32",
            "covariance1", "covariance2", "covariance8",
            "covariance16", "covariance32", "compression",
        ][idx], float(C[idx][1]))
        setattr(tr2, [
            "excursion", "num_directional_runs", "len_directional_runs",
            "num_increases_decreases", "num_runs_median", "len_runs_median",
            "avg_collision", "max_collision", "periodicity1", "periodicity2",
            "periodicity8", "periodicity16", "periodicity32",
            "covariance1", "covariance2", "covariance8",
            "covariance16", "covariance32", "compression",
        ][idx], float(C[idx][2]))

    tc.test_results = [tr0, tr1, tr2]

    for i in range(NUM_TESTS):
        if (C[i][0] + C[i][1] <= 5) or (C[i][1] + C[i][2] <= 5):
            return False
    return True
