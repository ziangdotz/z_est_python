"""NIST SP 800-90B Entropy Assessment - Utility Functions"""

from __future__ import annotations

import math
import struct

import numpy as np

from ._config import DBL_EPSILON, DBL_MIN, ITERMAX, ZALPHA
from ._types import DataT


def calc_stats(dp: DataT) -> tuple[float, float]:
    """Computes raw mean and median. For binary data, median = 0.5."""
    rawmean = float(np.sum(dp.rawsymbols)) / dp.len

    if dp.alph_size == 2:
        median = 0.5
    else:
        v = np.sort(dp.symbols)
        half = dp.len // 2
        if dp.len & 1:
            median = float(v[half])
        else:
            median = (float(v[half]) + float(v[half - 1])) / 2.0

    return rawmean, median


def calc_proportions(data: np.ndarray, p: np.ndarray, sample_size: int) -> None:
    """Computes frequency proportions p[i] = count(i) / n, modifies p in-place."""
    for i in range(sample_size):
        p[data[i]] += 1.0 / sample_size


def calc_counts(data: np.ndarray, c: np.ndarray, sample_size: int) -> None:
    """Computes frequency counts, modifies c in-place."""
    for i in range(sample_size):
        c[data[i]] += 1


def n_choose_2(n: int) -> int:
    """Returns n*(n-1)/2."""
    return (n * n - n) // 2


def substr(text: np.ndarray, pos: int, length: int, total: int) -> np.ndarray:
    """Safe substring extraction with bounds checking."""
    if pos + length > total:
        length = total - pos
    return text[pos:pos + length].copy()


def fast_substr(text: np.ndarray, pos: int, length: int) -> np.ndarray:
    """Fast substring extraction without bounds checking (max 16 bytes)."""
    return text[pos:pos + length].copy()


def max_vector(vals: np.ndarray) -> float:
    """Maximum of array."""
    return float(np.max(vals))


def divide(a: int, b: int) -> float:
    """Safe division."""
    return a / b


def rel_epsilon_equal(
    A: float, B: float,
    max_abs_factor: float = DBL_EPSILON,
    max_rel_factor: float = DBL_EPSILON,
    max_ulp: int = 4
) -> bool:
    """
    C++ relEpsilonEqual exact Python translation.
    Knuth-style floating-point near-equality: relative + absolute + ULP.
    """
    if math.isnan(A) or math.isnan(B):
        return False

    if A == B:
        return True

    if math.isinf(A) or math.isinf(B):
        return False

    absA = abs(A)
    absB = abs(B)

    if absA > absB:
        A, B = B, A
        absA, absB = absB, absA

    diff = abs(B - A)

    if (absA < DBL_MIN) or (diff < DBL_MIN) or math.isinf(diff) or (absB * max_rel_factor < DBL_MIN):
        return diff <= max_abs_factor
    else:
        if diff <= absB * max_rel_factor:
            return True

    if math.copysign(1.0, A) != math.copysign(1.0, B):
        return False

    Aint = struct.unpack('>Q', struct.pack('>d', absA))[0]
    Bint = struct.unpack('>Q', struct.pack('>d', absB))[0]

    assert Bint > Aint
    return (Bint - Aint) <= max_ulp


def compressed_bit_symbols(S: np.ndarray, length: int) -> int:
    """Packs <=32 bits into uint32."""
    assert length <= 32
    ret_pattern = 0
    for j in range(length):
        assert S[j] <= 1
        ret_pattern = (ret_pattern << 1) | int(S[j])
    return ret_pattern


def prediction_estimate_function(p: float, r: int, N: int) -> float:
    """
    Returns log(1-p*x) - log((r+1-r*x)*q) - (N+1)*log(x)
    where q=1-p, x solved iteratively: x_{i+1} = 1 + q*p^r * x_i^(r+1)
    """
    assert p > 0.0
    assert p < 1.0

    q = 1.0 - p
    x = 1.0
    x_last = 0.0

    for i in range(66):
        if (x - x_last) <= (DBL_EPSILON * x):
            break
        x_last = x
        x = 1.0 + q * (p ** r) * (x ** (r + 1.0))
        assert x >= x_last
        assert p * x <= 1.0

    return math.log(1.0 - p * x) - math.log((r + 1.0 - r * x) * q) - (N + 1.0) * math.log(x)


def calc_p_local(max_run_len: int, N: int, ldomain: float) -> float:
    """Binary search for p_local using rel_epsilon_equal termination."""
    log_alpha = math.log(0.99)

    hdomain = 1.0
    lbound = ldomain
    hbound = hdomain

    lvalue = float('inf')
    hvalue = float('-inf')

    p = (lbound + hbound) / 2.0
    p_val = prediction_estimate_function(p, max_run_len + 1, N)

    for j in range(ITERMAX):
        if rel_epsilon_equal(p_val, log_alpha, DBL_MIN, DBL_EPSILON, 4):
            break

        if log_alpha < p_val:
            lbound = p
            lvalue = p_val
        else:
            hbound = p
            hvalue = p_val

        if lbound >= hbound:
            p = min(max(lbound, hbound), hdomain)
            break

        if not (ldomain <= lbound <= hdomain and ldomain <= hbound <= hdomain):
            p = hdomain
            break

        if not (lvalue <= log_alpha <= hvalue or hvalue <= log_alpha <= lvalue):
            p = hdomain
            break

        last_p = p
        p = (lbound + hbound) / 2.0

        if not (lbound < p < hbound):
            p = hbound
            break

        if last_p == p:
            p = hbound
            break

        p_val = prediction_estimate_function(p, max_run_len + 1, N)

        if not ((lvalue <= p_val <= hvalue) or (hvalue <= p_val <= lvalue)):
            p = hbound
            break

    return p


def prediction_estimate(
    C: int, N: int, max_run_len: int, k: int,
    test_name: str = "", verbose: int = 0, label: str = ""
) -> float:
    """
    Unified prediction estimate framework.
    Returns min-entropy = -log2(max(p_global', p_local))
    """
    cur_max = 1.0 / k
    p_global = C / N

    if p_global > 0:
        p_global_prime = min(1.0, p_global + ZALPHA * math.sqrt(
            p_global * (1.0 - p_global) / (N - 1.0)))
    else:
        p_global_prime = 1.0 - 0.01 ** (1.0 / N)

    cur_max = max(cur_max, p_global_prime)

    r = max_run_len + 1
    p_local = -1.0

    if cur_max < 1.0 and prediction_estimate_function(cur_max, r, N) > math.log(0.99):
        p_local = calc_p_local(max_run_len, N, cur_max)
        cur_max = max(cur_max, p_local)

    ent_est = -math.log2(cur_max)

    if verbose == 2:
        if p_local > 0.0:
            print(f"{label} {test_name} Prediction Estimate: N = {N}, Pglobal' = {p_global_prime:.17g} (C = {C}) Plocal = {p_local:.17g} (r = {r})")
        else:
            print(f"{label} {test_name} Prediction Estimate: N = {N}, Pglobal' = {p_global_prime:.17g} (C = {C}) Plocal can't affect result (r = {r})")
    elif verbose == 3:
        print(f"{label} {test_name} Prediction Estimate: C = {C}")
        print(f"{label} {test_name} Prediction Estimate: r = {r}")
        print(f"{label} {test_name} Prediction Estimate: N = {N}")
        print(f"{label} {test_name} Prediction Estimate: P_global = {p_global:.17g}")
        print(f"{label} {test_name} Prediction Estimate: P_global' = {p_global_prime:.17g}")
        if p_local > 0.0:
            print(f"{label} {test_name} Prediction Estimate: P_local = {p_local:.17g}")
        else:
            print(f"{label} {test_name} Prediction Estimate: P_local can't change the result.")
        print(f"{label} {test_name} Prediction Estimate: min entropy = {ent_est:.17g}")

    return ent_est


def kahan_add(sum_val: float, comp: float, inp: float) -> tuple[float, float]:
    """Kahan compensated summation. Returns (new_sum, new_comp)."""
    y = inp - comp
    t = sum_val + y
    comp = (t - sum_val) - y
    return t, comp
