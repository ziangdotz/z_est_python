"""NIST SP 800-90B Entropy Assessment - Compression Estimate (Section 6.3.4)"""

from __future__ import annotations

import math

import numpy as np

from ._config import DBL_EPSILON, DBL_MIN, ITERMAX, ZALPHA
from ._util import rel_epsilon_equal

# Bits below the smallest denormal double; powers under this are exactly 0.
_SUBNORMAL_BITS = 1075.0


def _in_closed_interval(x: float, a: float, b: float) -> bool:
    """C++ INCLOSEDINTERVAL(): the bounds may arrive in either order."""
    lo, hi = (b, a) if a > b else (a, b)
    return lo <= x <= hi


def _in_open_interval(x: float, a: float, b: float) -> bool:
    """C++ INOPENINTERVAL(): the bounds may arrive in either order."""
    lo, hi = (b, a) if a > b else (a, b)
    return lo < x < hi


def _g(z: float, d: int, num_blocks: int) -> float:
    """
    C++ ``G(z, d, num_blocks)`` from the Compression Estimate.

    It accumulates ``log2(i) * (1-z)**(i-1)`` into A (i = 2..num_blocks) and the
    same terms weighted by ``num_blocks - i`` into firstSum (i = d+1..
    num_blocks-1), plus ``(num_blocks - d) * A_{d+1}``, and returns
    ``z * (z * firstSum + (A - A_{d+1})) / v``.

    The reference stops the second loop as soon as a weighted term underflows to
    a double; every later term is then 0 in double precision anyway, so the sums
    are cut off at that point instead of looping over ``num_blocks``.
    """
    v = num_blocks - d
    assert d > 0 and v > 0

    # z == 0 kills the leading factor, and z == 1 leaves (1-z)**(i-1) == 0 for
    # every i >= 2, so both ends of the domain give G = 0.
    if z <= 0.0 or z >= 1.0:
        return 0.0

    r = 1.0 - z
    hi = min(num_blocks, d + int(math.ceil(_SUBNORMAL_BITS / -math.log2(r))) + 2)

    idx = np.arange(2, d + 1, dtype=np.float64)
    a_d1 = float(np.sum(np.log2(idx) * np.power(r, idx - 1.0)))

    total = a_d1
    first_sum = (num_blocks - d) * a_d1

    if hi > d:
        idx = np.arange(d + 1, hi + 1, dtype=np.float64)
        terms = np.log2(idx) * np.power(r, idx - 1.0)
        total += float(np.sum(terms))
        # The i == num_blocks term carries a weight of 0 in firstSum, which is
        # why the reference only adds it to A: letting it through the array
        # reproduces that without a special case.
        first_sum += float(np.sum((num_blocks - idx) * terms))

    return z * (z * first_sum + (total - a_d1)) / v


def _com_exp(p: float, alph_size: int, d: int, num_blocks: int) -> float:
    """
    C++ ``com_exp()``: expected value of log2(gap) when one symbol carries
    probability p and each of the remaining ``alph_size - 1`` carries
    ``(1 - p) / (alph_size - 1)``.
    """
    k = float(alph_size - 1)
    q = (1.0 - p) / k
    return _g(p, d, num_blocks) + k * _g(q, d, num_blocks)


def _binary_search_p(
    x_prime: float, alph_size: int, d: int, num_blocks: int
) -> float:
    """
    Invert the strictly decreasing ``com_exp()`` on [1/alph_size, 1], following
    the reference bisection (including its "give up and take the lower bound"
    invariants) so that the returned p is bit-for-bit the one the C++ picks.
    """
    ldomain = 1.0 / float(alph_size)
    hdomain = 1.0

    lbound = ldomain
    hbound = hdomain
    lvalue = math.inf
    hvalue = -math.inf

    # We don't need the initial pVal invariant, as our initial bounds are
    # infinite, and we don't need the initial bounds, as they are the domain.
    p = (lbound + hbound) / 2.0
    p_val = _com_exp(p, alph_size, d, num_blocks)

    for _ in range(ITERMAX):
        # Have we reached "equality"?
        if rel_epsilon_equal(p_val, x_prime, DBL_MIN, DBL_EPSILON, 4):
            break

        if x_prime < p_val:
            lbound = p
            lvalue = p_val
        else:
            hbound = p
            hvalue = p_val

        if lbound >= hbound:
            p = min(max(lbound, hbound), hdomain)
            break

        # Invariants: a search outside the domain, or past a bracketed target,
        # is a failure, and step 8 of the document calls for "full entropy".
        if not (_in_closed_interval(lbound, ldomain, hdomain)
                and _in_closed_interval(hbound, ldomain, hdomain)):
            return ldomain

        if not _in_closed_interval(x_prime, lvalue, hvalue):
            return ldomain

        last_p = p
        p = (lbound + hbound) / 2.0

        if not _in_open_interval(p, lbound, hbound):
            p = hbound
            break

        if last_p == p:                     # cycle: the interval is exhausted
            p = hbound
            break

        p_val = _com_exp(p, alph_size, d, num_blocks)

        if not _in_closed_interval(p_val, lvalue, hvalue):
            p = hbound
            break

    return p


def _block_values(data: np.ndarray, num_blocks: int, b: int) -> np.ndarray:
    """Pack ``b`` bits per block, MSB first, exactly like the reference loop."""
    bits = np.asarray(data[:num_blocks * b], dtype=np.uint8).reshape(num_blocks, b) & 1
    weights = (1 << np.arange(b - 1, -1, -1, dtype=np.int64))
    return bits.astype(np.int64) @ weights


def _last_occurrence(block_vals: np.ndarray) -> np.ndarray:
    """
    ``prev[i]`` is the 1-based index of the block's previous occurrence, or 0
    when there is none - i.e., the contents of the reference dictionary right
    before block ``i`` is looked up.
    """
    order = np.argsort(block_vals, kind='stable')
    ranked = block_vals[order]
    same = ranked[1:] == ranked[:-1]
    prev = np.zeros(block_vals.shape[0], dtype=np.int64)
    prev[order[1:][same]] = order[:-1][same] + 1
    return prev


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
        print(f"\t*** Warning: not enough samples to run compression test (need more than {d}) ***")
        return -1.0

    v = num_blocks - d
    prev = _last_occurrence(_block_values(data, num_blocks, b))

    # gap = (i + 1) - dict[block], with dict[block] == 0 for a first occurrence
    log_vals = np.log2(np.arange(1, num_blocks + 1, dtype=np.float64) - prev)
    tail = log_vals[d:]

    # Exactly rounded, like the reference's compensated accumulation.
    x_bar = math.fsum(tail) / v
    sigma = 0.5907 * math.sqrt(math.fsum(tail * tail) / (v - 1.0) - x_bar * x_bar)

    if verbose == 2:
        print(f"{label} Compression Estimate: X-bar = {x_bar:.17g}, sigma-hat = {sigma:.17g}, ", end="")
    elif verbose == 3:
        print(f"{label} Compression Estimate: X-bar = {x_bar:.17g}")
        print(f"{label} Compression Estimate: sigma-hat = {sigma:.17g}")

    # binary search for p
    x_prime = x_bar - ZALPHA * sigma / math.sqrt(v)

    if verbose == 3:
        print(f"{label} Compression Estimate: X-bar' = {x_prime:.17g}")

    if _com_exp(1.0 / float(alph_size), alph_size, d, num_blocks) > x_prime:
        p = _binary_search_p(x_prime, alph_size, d, num_blocks)
    else:
        p = -1.0

    if p > 1.0 / float(alph_size):
        ent_est = -math.log2(p) / b
        if verbose == 3:
            print(f"{label} Compression Estimate: Found p.")
    else:
        p = 1.0 / float(alph_size)
        ent_est = 1.0
        if verbose == 3:
            print(f"{label} Compression Estimate: Could Not Find p. Proceeding with the lower bound for p.")

    if verbose == 2:
        print(f"p = {p:.17g}")
    elif verbose == 3:
        print(f"{label} Compression Estimate: p = {p:.17g}")
        print(f"{label} Compression Estimate: min entropy = {ent_est:.17g}")

    return ent_est
