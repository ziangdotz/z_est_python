"""NIST SP 800-90B Entropy Assessment - Restart Test"""

from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

import numpy as np

from ._config import DEFAULT_SIM_ROUNDS, MIN_SIZE, ZALPHA
from ._io import free_data, read_file
from ._rng import Xoshiro256StarStar
from ._types import DataT
from .mcv import most_common_value


def simulate_count(k_effective: int, p: float, seed: list[int]) -> int:
    """
    Simulate one row (1000 i.i.d. samples), return max symbol count.
    Distribution: floor(1/p) symbols each with prob p, remainder to one symbol.
    """
    rng = Xoshiro256StarStar(np.array(seed, dtype=np.uint64))
    counts = np.zeros(k_effective, dtype=np.uint16)
    for _ in range(1000):
        idx = int(math.floor(rng.random_unit() / p))
        if idx >= k_effective:
            idx = k_effective - 1
        counts[idx] += 1
    return int(np.max(counts))


def simulate_batch(
    num_rounds: int, k_effective: int, p: float, base_seed: list[int]
) -> list[int]:
    """Run a batch of simulation rounds."""
    results = []
    for i in range(num_rounds):
        seed = [(s + i * 7 + 13) & 0xFFFFFFFFFFFFFFFF for s in base_seed]
        results.append(simulate_count(k_effective, p, seed))
    return results


def simulate_bound(
    alpha: float, k: int, H_I: float,
    simulation_rounds: int = DEFAULT_SIM_ROUNDS,
    num_workers: Optional[int] = None,
) -> int:
    """
    Monte Carlo simulation to find X_cutoff.
    """
    p = 2.0 ** (-H_I)
    k_effective = math.ceil(1.0 / p)
    assert 1 < k_effective <= k <= 256

    if num_workers is None:
        num_workers = os.cpu_count() or 1

    base_seed = [0x1234567890ABCDEF, 0xFEDCBA0987654321,
                 0x1111111111111111, 0x2222222222222222]

    batch_size = simulation_rounds // num_workers
    if batch_size == 0:
        batch_size = 1

    with ProcessPoolExecutor(max_workers=num_workers) as ex:
        futures = []
        for _ in range(num_workers):
            futures.append(ex.submit(simulate_batch, batch_size, k_effective, p, base_seed))

        results = []
        for f in futures:
            results.extend(f.result())

    results.sort()
    return_index = int(math.floor((1.0 - alpha) * simulation_rounds)) - 1
    if return_index < 0:
        return_index = 0
    if return_index >= len(results):
        return_index = len(results) - 1
    return results[return_index]


def max_count_in_rows(data: np.ndarray, rows: int, cols: int, alph_size: int) -> int:
    """Find the maximum symbol count across all rows."""
    max_count = 0
    for r in range(rows):
        counts = np.zeros(alph_size, dtype=np.int64)
        for c in range(cols):
            counts[int(data[r * cols + c])] += 1
        row_max = int(np.max(counts))
        if row_max > max_count:
            max_count = row_max
    return max_count


def restart_test(
    file_path: str, H_I: float, iid: bool = False,
    verbose: int = 1, simulation_rounds: int = DEFAULT_SIM_ROUNDS,
) -> float:
    """
    Complete Restart Test.
    Returns min(H_r, H_c, H_I).
    """
    dp = DataT()
    if not read_file(file_path, dp):
        raise RuntimeError(f"Failed to read file: {file_path}")

    if dp.len != MIN_SIZE:
        raise RuntimeError(f"Need {MIN_SIZE} samples, got {dp.len}")

    if H_I > dp.word_size:
        raise RuntimeError(f"H_I ({H_I}) > word_size ({dp.word_size})")

    if dp.alph_size <= 1:
        raise RuntimeError("Alphabet size must be > 1")

    r, c = 1000, 1000
    rdata = dp.symbols.copy()

    cdata = np.zeros(dp.len, dtype=np.uint8)
    for j in range(c):
        for i in range(r):
            cdata[j * r + i] = rdata[i * c + j]

    alpha = 1.0 - math.exp(math.log(0.99) / (r + c))
    X_cutoff = simulate_bound(alpha, dp.alph_size, H_I, simulation_rounds)

    X_r = max_count_in_rows(rdata, r, c, dp.alph_size)
    X_c = max_count_in_rows(cdata, c, r, dp.alph_size)
    X_max = max(X_r, X_c)

    if verbose >= 2:
        print(f"Restart Sanity Check: X_r = {X_r}, X_c = {X_c}, X_max = {X_max}, X_cutoff = {X_cutoff}")

    if X_max > X_cutoff:
        raise RuntimeError(f"Restart Sanity Check Failed: X_max={X_max} > X_cutoff={X_cutoff}")

    H_r = most_common_value(rdata, dp.len, dp.alph_size, verbose, "Row")
    H_c = most_common_value(cdata, dp.len, dp.alph_size, verbose, "Column")

    if verbose >= 2:
        print(f"Restart Validation: H_r = {H_r}, H_c = {H_c}, H_I = {H_I}")

    if min(H_r, H_c) < H_I / 2.0:
        raise RuntimeError(f"Validation Test Failed: min(H_r, H_c)={min(H_r, H_c)} < H_I/2={H_I/2.0}")

    free_data(dp)
    return min(H_r, H_c, H_I)
