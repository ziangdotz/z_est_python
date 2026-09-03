"""NIST SP 800-90B Entropy Assessment - Restart Test"""

from __future__ import annotations

import math
import os
from concurrent.futures import ProcessPoolExecutor
from itertools import repeat
from typing import Optional

import numpy as np

from ._config import DEFAULT_SIM_ROUNDS, MIN_SIZE
from ._io import free_data, read_file
from ._types import DataT
from .mcv import most_common_value

# The reference reseeds xoshiro from system entropy on every run, which makes
# X_cutoff unreproducible; a fixed seed keeps a run repeatable instead.
_SIM_BASE_SEED = 0x5EED0001
# multinomial() is chunked so its int64 buffer stays around 16 MB
_SIM_CELLS_PER_CHUNK = 2_000_000


def _simulate_rows(num_rounds: int, k_effective: int, p: float, seed) -> np.ndarray:
    """
    ``num_rounds`` simulated rows: the largest symbol count in 1000 draws.

    ``simulateCount()`` maps every uniform draw to ``floor(U / p)``, which
    splits [0, 1) into ``floor(1/p)`` intervals of width p plus one residual
    interval of width ``1 - floor(1/p) * p``. A row is therefore exactly one
    multinomial trial with those probabilities, and numpy samples that (BTDC,
    no normal approximation) thousands of times faster than a per-symbol loop.
    """
    probs = np.full(k_effective, p)
    probs[-1] = 1.0 - (k_effective - 1) * p

    rng = np.random.default_rng(seed)
    out = np.empty(num_rounds, dtype=np.uint16)
    chunk = max(1, _SIM_CELLS_PER_CHUNK // k_effective)

    for start in range(0, num_rounds, chunk):
        stop = min(start + chunk, num_rounds)
        out[start:stop] = rng.multinomial(1000, probs, size=stop - start).max(axis=1)

    return out


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
    num_workers = max(1, min(num_workers, simulation_rounds))

    # One independent stream per worker - the reference reaches the same
    # separation with xoshiro_jump(thread_num * 2^128) - and an exact split of
    # the rounds: every round has to be simulated once and only once, or the
    # quantile below is taken from the wrong number of samples.
    children = np.random.SeedSequence(_SIM_BASE_SEED).spawn(num_workers)
    base, extra = divmod(simulation_rounds, num_workers)
    rounds = [base + (1 if w < extra else 0) for w in range(num_workers)]

    if num_workers == 1:
        parts = [_simulate_rows(rounds[0], k_effective, p, children[0])]
    else:
        with ProcessPoolExecutor(max_workers=num_workers) as ex:
            parts = list(ex.map(_simulate_rows, rounds, repeat(k_effective), repeat(p), children))

    results = np.concatenate(parts)
    assert results.size == simulation_rounds

    results.sort()
    # Same sanity bounds the reference asserts on the simulated extremes.
    assert (1000 // k) <= results[0] <= results[-1] <= 1000

    return_index = int(math.floor((1.0 - alpha) * simulation_rounds)) - 1
    return_index = min(max(return_index, 0), results.size - 1)
    return int(results[return_index])


def max_count_in_rows(data: np.ndarray, rows: int, cols: int, alph_size: int) -> int:
    """Find the maximum symbol count across all rows."""
    syms = data[:rows * cols].astype(np.int64)
    offsets = np.repeat(np.arange(rows, dtype=np.int64) * alph_size, cols)
    hist = np.bincount(syms + offsets, minlength=rows * alph_size).reshape(rows, alph_size)
    return int(hist.max())


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
    rdata = dp.symbols

    # cdata[j * r + i] = rdata[i * c + j], i.e. the sample matrix transposed
    cdata = rdata.reshape(r, c).T.reshape(-1)

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
