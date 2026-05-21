"""NIST SP 800-90B Entropy Assessment - Markov Estimate (Section 6.3.3)"""

from __future__ import annotations

import math

import numpy as np


def markov_test(
    data: np.ndarray, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.3: Markov Estimate.
    Binary data only. Returns min-entropy per bit.
    """
    c0 = int(np.sum(data[:length - 1] == 0))
    c1 = (length - 1) - c0
    c00 = int(np.sum((data[:length - 1] == 0) & (data[1:length] == 0)))
    c10 = int(np.sum((data[:length - 1] == 1) & (data[1:length] == 0)))

    p0 = c0 / length
    p1 = 1.0 - p0

    if c0 > 0:
        p00 = c00 / c0
        p01 = 1.0 - p00
    else:
        p00 = p01 = 0.0

    if c1 > 0:
        p10 = c10 / c1
        p11 = 1.0 - p10
    else:
        p10 = p11 = 0.0

    h_min = 128.0

    def try_seq(h: float):
        nonlocal h_min
        if h < h_min:
            h_min = h

    if p00 > 0:
        try_seq(-math.log2(p0) - 127.0 * math.log2(p00))
    if p01 > 0 and p10 > 0:
        try_seq(-math.log2(p0) - 64.0 * math.log2(p01) - 63.0 * math.log2(p10))
    if p01 > 0 and p11 > 0:
        try_seq(-math.log2(p0) - math.log2(p01) - 126.0 * math.log2(p11))
    if p10 > 0 and p00 > 0:
        try_seq(-math.log2(p1) - math.log2(p10) - 126.0 * math.log2(p00))
    if p10 > 0 and p01 > 0:
        try_seq(-math.log2(p1) - 64.0 * math.log2(p10) - 63.0 * math.log2(p01))
    if p11 > 0:
        try_seq(-math.log2(p1) - 127.0 * math.log2(p11))

    ent_est = min(h_min / 128.0, 1.0)

    if verbose == 2:
        print(f"{label} Markov Estimate: h_min = {h_min:.17g}, entropy/bit = {ent_est:.17g}")
    elif verbose == 3:
        print(f"{label} Markov Estimate: p0 = {p0:.17g}, p1 = {p1:.17g}")
        print(f"{label} Markov Estimate: p00 = {p00:.17g}, p01 = {p01:.17g}")
        print(f"{label} Markov Estimate: p10 = {p10:.17g}, p11 = {p11:.17g}")
        print(f"{label} Markov Estimate: h_min = {h_min:.17g}")
        print(f"{label} Markov Estimate: min entropy = {ent_est:.17g}")

    return ent_est
