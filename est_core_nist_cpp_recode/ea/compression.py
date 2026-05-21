"""NIST SP 800-90B Entropy Assessment - Compression Estimate (Section 6.3.4)"""

from __future__ import annotations

import math

import numpy as np

from ._config import ZALPHA
from ._util import kahan_add


def _com_exp(p: float, alph_size: int, d: int, num_blocks: int) -> float:
    """
    Expected value of log2(gap) under geometric distribution with parameter p.
    G(z, d, num_blocks) function.
    """
    q = 1.0 - p
    max_k = num_blocks - d
    X_sum = 0.0
    X_comp = 0.0
    for k in range(1, max_k + 1):
        prob = p * (q ** (k - 1))
        log_val = math.log2(k) * prob
        X_sum, X_comp = kahan_add(X_sum, X_comp, log_val)
    return X_sum


def _binary_search_p(
    X_prime: float, alph_size: int, d: int, num_blocks: int
) -> float:
    """Binary search for p in compression estimate."""
    lbound = 1.0 / alph_size
    hbound = 1.0

    for _ in range(100):
        p = (lbound + hbound) / 2.0
        expected = _com_exp(p, alph_size, d, num_blocks)
        if expected > X_prime:
            lbound = p
        else:
            hbound = p

    return hbound


def compression_test(
    data: np.ndarray, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.4: Compression Estimate.
    Binary data only. Returns min-entropy per bit.
    """
    b = 6
    d = 1000
    alph_size = 1 << b
    num_blocks = length // b

    if num_blocks <= d:
        if verbose > 1:
            print(f"{label} Compression Estimate: num_blocks <= d, skipping.")
        return -1.0

    blocks = data[:num_blocks * b].reshape(-1, b)
    block_vals = np.zeros(num_blocks, dtype=np.int64)
    for i in range(num_blocks):
        val = 0
        for j in range(b):
            val |= int(blocks[i, j]) << (b - 1 - j)
        block_vals[i] = val

    dict_map = np.full(alph_size, -1, dtype=np.int64)
    for i in range(d):
        dict_map[block_vals[i]] = i + 1

    X_sum = 0.0
    X_comp = 0.0
    sigma_sum = 0.0
    sigma_comp = 0.0

    for i in range(d, num_blocks):
        log_val = math.log2(i + 1 - dict_map[block_vals[i]])
        X_sum, X_comp = kahan_add(X_sum, X_comp, log_val)
        sq = log_val * log_val
        sigma_sum, sigma_comp = kahan_add(sigma_sum, sigma_comp, sq)
        dict_map[block_vals[i]] = i + 1

    v = num_blocks - d
    X_bar = X_sum / v
    sigma_hat = 0.5907 * math.sqrt(sigma_sum / (v - 1.0) - X_bar * X_bar)
    X_prime = X_bar - ZALPHA * sigma_hat / math.sqrt(v)

    if _com_exp(1.0 / alph_size, alph_size, d, num_blocks) > X_prime:
        p = _binary_search_p(X_prime, alph_size, d, num_blocks)
    else:
        p = -1.0

    if p > 1.0 / alph_size:
        ent_est = -math.log2(p) / b
    else:
        ent_est = 1.0

    if verbose == 2:
        print(f"{label} Compression Estimate: X_bar = {X_bar:.17g}, X_prime = {X_prime:.17g}, p = {p:.17g}")
    elif verbose == 3:
        print(f"{label} Compression Estimate: v = {v}")
        print(f"{label} Compression Estimate: X_bar = {X_bar:.17g}")
        print(f"{label} Compression Estimate: sigma_hat = {sigma_hat:.17g}")
        print(f"{label} Compression Estimate: X_prime = {X_prime:.17g}")
        print(f"{label} Compression Estimate: p = {p:.17g}")
        print(f"{label} Compression Estimate: min entropy = {ent_est:.17g}")

    return ent_est
