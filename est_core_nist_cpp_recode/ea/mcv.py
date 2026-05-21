"""NIST SP 800-90B Entropy Assessment - Most Common Value (Section 6.3.1)"""

from __future__ import annotations

import math

import numpy as np

from ._config import ZALPHA
from ._types import TestCaseBase


def most_common_value(
    data: np.ndarray, length: int, alph_size: int,
    verbose: int = 0, label: str = "",
    tc: TestCaseBase | None = None
) -> float:
    """
    Section 6.3.1: Most Common Value Estimate.
    Returns min-entropy = -log2(p_u).
    """
    counts = np.bincount(data.astype(np.int64), minlength=alph_size)
    mode = int(np.max(counts))
    p_hat = mode / length
    p_u = min(1.0, p_hat + ZALPHA * math.sqrt(p_hat * (1.0 - p_hat) / (length - 1.0)))

    if tc is not None:
        tc.mcv_estimate_mode = float(mode)
        tc.mcv_estimate_p_hat = p_hat
        tc.mcv_estimate_p_u = p_u

    ent_est = -math.log2(p_u)

    if verbose == 2:
        print(f"{label} MCV Estimate: mode = {mode}, p_hat = {p_hat:.17g}, p_u = {p_u:.17g}")
    elif verbose == 3:
        print(f"{label} MCV Estimate: mode = {mode}")
        print(f"{label} MCV Estimate: p_hat = {p_hat:.17g}")
        print(f"{label} MCV Estimate: p_u = {p_u:.17g}")
        print(f"{label} MCV Estimate: min entropy = {ent_est:.17g}")

    return ent_est
