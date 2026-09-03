"""NIST SP 800-90B Entropy Assessment - Suffix Array + t-Tuple + LRS"""

from __future__ import annotations

import math

import numpy as np

from ._config import ZALPHA
from ._util import calc_proportions, n_choose_2

ZALPHA_L = ZALPHA  # Use same value (C++ uses long double version)


def sa_to_lcp(text: np.ndarray, n: int, sa: np.ndarray) -> np.ndarray:
    """
    Kasai et al. O(n) LCP construction.
    Matches C++ sa2lcp32/sa2lcp64 in lrs_test.h.

    The suffix comparisons run over plain Python lists: `text` arrives as a
    uint8 array, and a per-element numpy lookup costs several times what the
    list indexing costs while the whole loop touches every sample.
    """
    rank = np.empty(n + 1, dtype=np.int64)
    rank[sa] = np.arange(n + 1)

    t = text[:n].tolist()
    s = sa.tolist()
    r = rank.tolist()

    # Only slot 0 keeps its initial value: the empty suffix sits at s[0], so
    # every other slot is the rank of some sample and gets written below.
    lcp = [0] * (n + 1)
    lcp[0] = -1

    h = 0
    for i in range(n):
        k = r[i]
        if k > 1:
            j = s[k - 1]
            while (i + h < n) and (j + h < n) and t[i + h] == t[j + h]:
                h += 1
            lcp[k] = h
        if h > 0:
            h -= 1
    return np.array(lcp, dtype=np.int64)


def build_suffix_array(text: np.ndarray, n: int) -> np.ndarray:
    """
    Suffix array of ``text[:n]`` plus the empty suffix at position ``n``, which
    sorts first - the layout the reference gets out of divsufsort and what
    :func:`sa_to_lcp` expects. Index ``n`` is therefore ``sa[0]``.

    Prefix doubling (Manber-Myers): ``rank`` holds the order of the length-``k``
    prefixes, and sorting by the pair ``(rank[i], rank[i + k])`` resolves twice
    as much, so ``ceil(log2(n))`` rounds suffice - far fewer in practice, since
    the round after which every suffix is separated already yields the final
    order. The pair fits in one ``int64`` key as long as both components stay
    inside ``[-1, n]``: packing with base ``n + 2`` keeps the lexicographic
    order and lets a single argsort do the work.

    O(n log n) time with a vectorised body, O(n) space.
    """
    if n == 0:
        return np.array([0], dtype=np.int64)

    m = n + 1
    rank = np.empty(m, dtype=np.int64)
    rank[:n] = text[:n]
    rank[n] = -1  # the empty suffix is smaller than any symbol
    # A wider alphabet than sample count breaks the packing bound above, so give
    # such inputs dense ranks first; the remap in `read_file` keeps this rare.
    if int(rank[:n].max()) >= n:
        rank[:n] = np.unique(text[:n], return_inverse=True)[1]

    second = np.empty(m, dtype=np.int64)
    key = np.empty(m, dtype=np.int64)

    k = 1
    while k <= n:
        # second[i] = rank[i + k], or -1 where the prefix runs past the sample
        second.fill(-1)
        if k < m:
            second[:m - k] = rank[k:]
        np.multiply(rank, m + 1, out=key)
        key += second
        key += 1

        # Tied keys receive one and the same rank, so the round's outcome does
        # not depend on the order within a tie - which frees the faster,
        # unstable introsort (~6x the cost of a stable sort on these keys)
        sa = np.argsort(key)

        # New ranks walk the sorted order, stepping up whenever the pair changes
        sorted_key = key[sa]
        rank = np.empty(m, dtype=np.int64)
        rank[sa] = np.concatenate((
            np.zeros(1, dtype=np.int64),
            np.cumsum(sorted_key[1:] != sorted_key[:-1]),
        ))

        # If all ranks are distinct, the order is final
        if rank[sa[n]] == n:
            break
        k <<= 1

    return sa


def sa_algs(
    text: np.ndarray, n: int, k: int, verbose: int = 0, label: str = ""
) -> tuple:
    """
    Simultaneously compute t-Tuple and LRS estimates.
    Matches C++ SAalgs32/SAalgs64 in lrs_test.h.
    Uses Python int for arbitrary precision (replaces uint128_t).
    """
    sa = build_suffix_array(text, n)
    L = sa_to_lcp(text, n, sa).tolist()

    # The reference reads the LCP array one slot over - entry i holds what
    # sa_to_lcp reported for slot i + 1 - and closes the list with a 0 for the
    # slot past its end. Dropping the leading slot in place avoids a second
    # n + 1 element copy, and that trailing 0 is why the maxima below may run
    # over the whole list: every real entry is >= 0.
    del L[0]
    L.append(0)
    assert L[0] == 0

    v = max(L)

    if v == 0:
        if verbose > 1:
            print(f"{label} LRS Estimate: v=0, cannot compute.")
        return -1.0, -1.0

    Q = [1] * (v + 1)
    A = [0] * (v + 2)
    I = [0] * (v + 3)

    j = 0
    for i in range(1, n + 1):
        c = 0
        if L[i] < L[i - 1]:
            t = L[i - 1]
            j -= 1
            while t > L[i]:
                if j > 0 and I[j] == t:
                    A[I[j]] += A[I[j + 1]]
                    A[I[j + 1]] = 0
                    j -= 1
                if Q[t] >= A[I[j + 1]] + 1:
                    t = I[j] if j > 0 else L[i]
                else:
                    Q[t] = A[I[j + 1]] + 1
                    t -= 1
            c = A[I[j + 1]]
            A[I[j + 1]] = 0

        if L[i] > 0:
            if j < 1 or I[j] < L[i]:
                j += 1
                I[j] = L[i]
            A[I[j]] += c + 1

    u = 1
    while u <= v and Q[u] >= 35:
        u += 1

    t_tuple_res = -1.0
    Pmax = -1.0
    for i in range(1, u):
        curP = Q[i] / (n - i + 1)
        curPMax = curP ** (1.0 / i)
        if curPMax > Pmax:
            Pmax = curPMax

    if Pmax > 0.0:
        pu = Pmax + ZALPHA_L * math.sqrt(Pmax * (1.0 - Pmax) / (n - 1))
        if pu > 1.0:
            pu = 1.0
        t_tuple_res = -math.log2(pu)
        if verbose == 2:
            print(f"{label} t-Tuple Estimate: t = {u - 1}, p-hat_max = {Pmax:.22g}, p_u = {pu:.22g}")
        elif verbose == 3:
            print(f"{label} t-Tuple Estimate: t = {u - 1}")
            print(f"{label} t-Tuple Estimate: p-hat_max = {Pmax:.22g}")
            print(f"{label} t-Tuple Estimate: p_u = {pu:.22g}")
            print(f"{label} t-Tuple Estimate: min entropy = {t_tuple_res:.17g}")
    else:
        if verbose > 1:
            print("t-Tuple Estimate: No strings are repeated 35 times.")
        t_tuple_res = -1.0

    lrs_res = -1.0
    if v >= u:
        S = [0] * (v + 1)
        A = [0] * (v + 2)

        for i in range(1, n + 1):
            if L[i - 1] >= u and L[i] < L[i - 1]:
                b = L[i]
                if b < u:
                    b = u - 1
                for tt in range(L[i - 1], b, -1):
                    A[tt] += A[tt + 1]
                    A[tt + 1] = 0
                    choices = (A[tt] + 1) * A[tt] // 2
                    S[tt] += choices

                if b >= u:
                    A[b] += A[b + 1]
                A[b + 1] = 0

            if L[i] >= u:
                A[L[i]] += 1

        Pmax = 0.0
        for i in range(u, v + 1):
            choices = (n - i) * (n - i + 1) // 2
            curP = S[i] / choices
            curPMax = curP ** (1.0 / i)
            if Pmax < curPMax:
                Pmax = curPMax

        pu = Pmax + ZALPHA_L * math.sqrt(Pmax * (1.0 - Pmax) / (n - 1))
        if pu > 1.0:
            pu = 1.0
        lrs_res = -math.log2(pu)

        if verbose == 2:
            print(f"{label} LRS Estimate: u = {u}, v = {v}, p-hat = {Pmax:.17g}, p_u = {pu:.17g}")
        elif verbose == 3:
            print(f"{label} LRS Estimate: u = {u}")
            print(f"{label} LRS Estimate: v = {v}")
            print(f"{label} LRS Estimate: p-hat = {Pmax:.22g}")
            print(f"{label} LRS Estimate: p_u = {pu:.22g}")
            print(f"{label} LRS Estimate: min entropy = {lrs_res:.17g}")
    else:
        if verbose > 1:
            print("LRS Estimate: v<u. Can't Run LRS Test.")
        lrs_res = -1.0

    return t_tuple_res, lrs_res


def len_lrs_test(
    data: np.ndarray, L: int, k: int, verbose: int = 0, label: str = ""
) -> bool:
    """
    IID LRS test. Returns True if Pr(X >= 1) >= 0.001.
    Matches C++ len_LRS_test in lrs_test.h.
    """
    p = np.zeros(k, dtype=np.float64)
    calc_proportions(data, p, L)
    p_col = float(np.sum(p ** 2))

    if p_col > 1.0 - 1e-15:
        if verbose == 2:
            print("\tPr(X >= 1) = 1.0")
        elif verbose > 2:
            print(f"{label} Longest Repeated Substring: P_col = 1.0")
            print(f"{label} Longest Repeated Substring: Pr(X >= 1) = 1.0")
        return True

    sa = build_suffix_array(data, L)
    lcp = sa_to_lcp(data, L, sa)
    W = int(np.max(lcp))

    p_col_power = p_col ** W
    if p_col_power < 1e-300:
        log_prob_no_col_per_pair = math.log1p(-p_col_power)
    else:
        log_prob_no_col_per_pair = math.log(1.0 - p_col_power)

    N = n_choose_2(L - W + 1)

    if verbose > 1:
        prob_no_cols = math.exp(N * log_prob_no_col_per_pair)
        if verbose > 2:
            print(f"{label} Longest Repeated Substring results: P_col = {p_col:.22g}")
            print(f"{label} Longest Repeated Substring results: W = {W}")
            print(f"{label} Longest Repeated Substring results: Pr(X >= 1) = {1.0 - prob_no_cols:.22g}")
        else:
            print(f"{label} Longest Repeated Substring results")
            print(f"\tP_col: {p_col}")
            print(f"\tLength of LRS: {W}")
            print(f"\tPr(X >= 1): {1.0 - prob_no_cols}")

    return math.log(0.999) >= N * log_prob_no_col_per_pair
