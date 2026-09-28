"""NIST SP 800-90B Entropy Assessment - Chi-Square Tests"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Tuple

import numpy as np

try:
    from scipy.special import gammaincc
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

from ._config import DBL_EPSILON, DBL_MIN
from ._util import calc_proportions, rel_epsilon_equal


def chi_square_pvalue(x: float, k: float) -> float:
    """
    Pearson chi-square p-value: Q(k/2, x/2).
    Uses scipy.special.gammaincc if available, otherwise Cephes fallback.
    """
    if _HAS_SCIPY:
        return float(gammaincc(k / 2.0, x / 2.0))
    else:
        return _cephes_igamc(k / 2.0, x / 2.0)


# --- Cephes fallback (from chi_square_tests.h) ---

_MACHEP = 1.11022302462515654042E-16
_MAXLOG = 7.09782712893383996732224E2
_MAXNUM = 1.7976931348623158E308
_PI = 3.14159265358979323846
_BIG = 4.503599627370496e15
_BIGINV = 2.22044604925031308085e-16
_MAXLGM = 2.556348e305

_A = [
    8.11614167470508450300E-4,
    -5.95061904284301438324E-4,
    7.93650340457716943945E-4,
    -2.77777777730099687205E-3,
    8.33333333333331927722E-2,
]
_B = [
    -1.37825152569120859100E3,
    -3.88016315134637840924E4,
    -3.31612992738871184744E5,
    -1.16237097492762307383E6,
    -1.72173700820839662146E6,
    -8.53555664245765465627E5,
]
_C = [
    -3.51815701436523470549E2,
    -1.70642106651881159223E4,
    -2.20528590553854454839E5,
    -1.13933444367982507207E6,
    -2.53252307177582951285E6,
    -2.01889141433532773231E6,
]


def _polevl(x: float, coef: list, n: int) -> float:
    ans = coef[0]
    for i in range(1, n + 1):
        ans = ans * x + coef[i]
    return ans


def _p1evl(x: float, coef: list, n: int) -> float:
    ans = x + coef[0]
    for i in range(1, n):
        ans = ans * x + coef[i]
    return ans


def _cephes_lgam(x: float) -> float:
    sgngam = 1
    if x < -34.0:
        q = -x
        w = _cephes_lgam(q)
        p = math.floor(q)
        if rel_epsilon_equal(p, q, DBL_EPSILON, DBL_EPSILON, 4):
            return sgngam * _MAXNUM
        i = int(p)
        if (i & 1) == 0:
            sgngam = -1
        z = q - p
        if z > 0.5:
            p += 1.0
            z = p - q
        z = q * math.sin(_PI * z)
        if rel_epsilon_equal(z, 0.0, DBL_EPSILON, DBL_EPSILON, 4):
            return sgngam * _MAXNUM
        return math.log(_PI) - math.log(z) - w

    if x < 13.0:
        z = 1.0
        p = 0.0
        u = x
        while u >= 3.0:
            p -= 1.0
            u = x + p
            z *= u
        while u < 2.0:
            if rel_epsilon_equal(u, 0.0, DBL_EPSILON, DBL_EPSILON, 4):
                return sgngam * _MAXNUM
            z /= u
            p += 1.0
            u = x + p
        if z < 0.0:
            sgngam = -1
            z = -z
        else:
            sgngam = 1
        if rel_epsilon_equal(u, 2.0, DBL_EPSILON, DBL_EPSILON, 4):
            return math.log(z)
        p -= 2.0
        x = x + p
        p = x * _polevl(x, _B, 5) / _p1evl(x, _C, 6)
        return math.log(z) + p

    if x > _MAXLGM:
        return sgngam * _MAXNUM

    q = (x - 0.5) * math.log(x) - x + math.log(math.sqrt(2.0 * _PI))
    if x > 1.0e8:
        return q
    p = 1.0 / (x * x)
    if x >= 1000.0:
        q += ((7.9365079365079365079365e-4 * p - 2.7777777777777777777778e-3) * p + 0.0833333333333333333333) / x
    else:
        q += _polevl(p, _A, 4) / x
    return q


def _cephes_igam(a: float, x: float) -> float:
    if x <= 0 or a <= 0:
        return 0.0
    if x > 1.0 and x > a:
        return 1.0 - _cephes_igamc(a, x)
    ax = a * math.log(x) - x - _cephes_lgam(a)
    if ax < -_MAXLOG:
        return 0.0
    ax = math.exp(ax)
    r = a
    c = 1.0
    ans = 1.0
    while True:
        r += 1.0
        c *= x / r
        ans += c
        if c / ans <= _MACHEP:
            break
    return ans * ax / a


def _cephes_igamc(a: float, x: float) -> float:
    if x <= 0 or a <= 0:
        return 1.0
    if x < 1.0 or x < a:
        return 1.0 - _cephes_igam(a, x)
    ax = a * math.log(x) - x - _cephes_lgam(a)
    if ax < -_MAXLOG:
        return 0.0
    ax = math.exp(ax)
    y = 1.0 - a
    z = x + y + 1.0
    c = 0.0
    pkm2 = 1.0
    qkm2 = x
    pkm1 = x + 1.0
    qkm1 = z * x
    ans = pkm1 / qkm1
    while True:
        c += 1.0
        y += 1.0
        z += 2.0
        yc = y * c
        pk = pkm1 * z - pkm2 * yc
        qk = qkm1 * z - qkm2 * yc
        if not rel_epsilon_equal(qk, 0.0, DBL_EPSILON, DBL_EPSILON, 4):
            r = pk / qk
            t = abs((ans - r) / r)
            ans = r
        else:
            t = 1.0
        pkm2 = pkm1
        pkm1 = pk
        qkm2 = qkm1
        qkm1 = qk
        if abs(pk) > _BIG:
            pkm2 *= _BIGINV
            pkm1 *= _BIGINV
            qkm2 *= _BIGINV
            qkm1 *= _BIGINV
        if t <= _MACHEP:
            break
    return ans * ax


# --- Helper data structures ---

@dataclass
class TupleTranslateEntry:
    tuple_val: int = 0
    expectation: float = 0.0
    bin: int = -1


def _expectation_order(a: TupleTranslateEntry, b: TupleTranslateEntry) -> bool:
    if a.expectation != b.expectation:
        return a.expectation < b.expectation
    return a.tuple_val < b.tuple_val


def _tuple_order(a: TupleTranslateEntry, b: TupleTranslateEntry) -> bool:
    return a.tuple_val < b.tuple_val


def _allocate_bins(e: list, bin_exp: list) -> None:
    current_bin = 0
    current_expectation = 0.0

    for i in range(len(e)):
        if current_expectation >= 5.0:
            bin_exp.append(current_expectation)
            current_bin += 1
            current_expectation = 0.0
        e[i].bin = current_bin
        current_expectation += e[i].expectation

    if current_bin != 0 and current_expectation < 5.0:
        for i in range(len(e) - 1, -1, -1):
            if e[i].bin == current_bin:
                e[i].bin = current_bin - 1
            else:
                break
        bin_exp[current_bin - 1] += current_expectation
    else:
        bin_exp.append(current_expectation)


def _calc_T(bin_expectations: list, o: list) -> float:
    T = 0.0
    for i in range(len(bin_expectations)):
        T += (o[i] - bin_expectations[i]) ** 2 / bin_expectations[i]
    return T


def _bin_lookup(e: list) -> np.ndarray:
    """``tuple_val -> bin`` as an array, so observed counts can be histogrammed.

    The per-sample loops in the reference index ``e[tuple_val].bin`` through a
    list of Python objects; scattering the same mapping into an array once lets
    ``bincount`` do the counting. Bins are exact integers, so this reproduces the
    loop's tallies exactly - ``_calc_T`` still sees the identical ``o``.
    """
    bin_of = np.zeros(len(e), dtype=np.int32)
    for entry in e:
        bin_of[entry.tuple_val] = entry.bin
    return bin_of


# --- Binary Chi-Square Independence ---

def binary_chi_square_independence(
    data: np.ndarray, sample_size: int
) -> Tuple[float, int]:
    p1 = float(np.sum(data)) / sample_size
    p0 = 1.0 - p1
    min_p = min(p0, p1)

    m = 11
    threshold = 5
    while m > 1:
        if (min_p ** m) * (sample_size / m) >= threshold:
            break
        m -= 1

    if m < 2:
        return 0.0, 0

    tuple_count = 1 << m
    block_count = sample_size // m

    # Each block of ``m`` bits is one tuple value, MSB first - the same integer
    # the reference builds by shifting in one bit per iteration. Counting them is
    # a histogram over exact integers, so bincount reproduces the per-tuple loop
    # bit for bit; only the loop is gone.
    blocks = np.asarray(data[: block_count * m], dtype=np.int32).reshape(block_count, m)
    weights = np.int32(1) << np.arange(m - 1, -1, -1, dtype=np.int32)
    occ = np.bincount(blocks @ weights, minlength=tuple_count)

    T = 0.0
    for i in range(tuple_count):
        w = bin(i).count('1')
        e = (p1 ** w) * (p0 ** (m - w)) * block_count
        T += (occ[i] - e) ** 2 / e

    return T, (1 << m) - 2


# --- Non-Binary Chi-Square Independence ---

def chi_square_independence(
    data: np.ndarray, sample_size: int, alphabet_size: int
) -> Tuple[float, int]:
    p = np.zeros(alphabet_size, dtype=np.float64)
    calc_proportions(data, p, sample_size)

    e = []
    for i in range(alphabet_size):
        for j in range(alphabet_size):
            entry = TupleTranslateEntry()
            entry.tuple_val = i * alphabet_size + j
            entry.expectation = p[i] * p[j] * math.floor(sample_size * 0.5)
            e.append(entry)

    e.sort(key=lambda x: (x.expectation, x.tuple_val))
    bin_expectations = []
    _allocate_bins(e, bin_expectations)
    e.sort(key=lambda x: x.tuple_val)

    # Consecutive non-overlapping pairs: the same j the reference steps through
    # with ``range(0, sample_size - 1, 2)``, so an odd trailing sample is dropped
    # here exactly as it is there.
    pair_count = len(range(0, sample_size - 1, 2))
    d = np.asarray(data, dtype=np.int32)
    index = d[0:2 * pair_count:2] * alphabet_size + d[1:2 * pair_count:2]
    o = np.bincount(_bin_lookup(e)[index], minlength=len(bin_expectations))

    score = _calc_T(bin_expectations, o.tolist())
    df = len(bin_expectations) - alphabet_size
    return score, df


# --- Binary Goodness of Fit ---

def binary_goodness_of_fit(
    data: np.ndarray, sample_size: int
) -> Tuple[float, int]:
    sublength = sample_size // 10
    ones = int(np.sum(data))
    p = ones / sample_size

    e0 = (1.0 - p) * sublength
    e1 = p * sublength

    T = 0.0
    for i in range(10):
        o1 = int(np.sum(data[i * sublength:(i + 1) * sublength]))
        o0 = sublength - o1
        T += (o0 - e0) ** 2 / e0 + (o1 - e1) ** 2 / e1

    return T, 9


# --- Non-Binary Goodness of Fit ---

def goodness_of_fit(
    data: np.ndarray, sample_size: int, alphabet_size: int
) -> Tuple[float, int]:
    p = np.zeros(alphabet_size, dtype=np.float64)
    calc_proportions(data, p, sample_size)

    e = []
    for j in range(alphabet_size):
        entry = TupleTranslateEntry()
        entry.tuple_val = j
        entry.expectation = p[j] * math.floor(sample_size / 10.0)
        e.append(entry)

    e.sort(key=lambda x: (x.expectation, x.tuple_val))
    bin_expectations = []
    _allocate_bins(e, bin_expectations)
    e.sort(key=lambda x: x.tuple_val)

    block_size = sample_size // 10
    bin_of = _bin_lookup(e)
    # Map every sample to its bin once, then reshape into the ten equal blocks the
    # reference walks. Same per-block tallies, same order for T to accumulate in.
    blocks = bin_of[np.asarray(data[: 10 * block_size], dtype=np.int32)].reshape(10, block_size)
    T = 0.0
    for j in range(10):
        o = np.bincount(blocks[j], minlength=len(bin_expectations))
        T += _calc_T(bin_expectations, o.tolist())

    df = 9 * (len(bin_expectations) - 1)
    return T, df


# --- Combined Chi-Square Tests ---

def chi_square_tests(
    data: np.ndarray, sample_size: int, alphabet_size: int, verbose: int = 0
) -> bool:
    result = True

    if alphabet_size == 2:
        score, df = binary_chi_square_independence(data, sample_size)
    else:
        score, df = chi_square_independence(data, sample_size, alphabet_size)

    pvalue = chi_square_pvalue(score, df) if df > 0 else 1.0

    if verbose == 2:
        print("Chi square independence")
        print(f"\tscore = {score}")
        print(f"\tdegrees of freedom = {df}")
        print(f"\tp-value = {pvalue}")
    elif verbose >= 3:
        print(f"Chi square independence: T = {score:.17g}")
        print(f"Chi square independence: df = {df}")
        print(f"Chi square independence: P-value = {pvalue:.17g}")

    if pvalue < 0.001:
        result = False

    if alphabet_size == 2:
        score, df = binary_goodness_of_fit(data, sample_size)
    else:
        score, df = goodness_of_fit(data, sample_size, alphabet_size)

    pvalue = chi_square_pvalue(score, df) if df > 0 else 1.0

    if verbose == 2:
        print("Chi square goodness of fit")
        print(f"\tscore = {score}")
        print(f"\tdegrees of freedom = {df}")
        print(f"\tp-value = {pvalue}")
    elif verbose >= 3:
        print(f"Chi square goodness of fit: T = {score:.17g}")
        print(f"Chi square goodness of fit: df = {df}")
        print(f"Chi square goodness of fit: P-value = {pvalue:.17g}")

    if pvalue < 0.001:
        result = False

    return result
