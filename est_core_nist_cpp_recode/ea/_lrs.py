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
    """
    rank = np.full(n + 1, -1, dtype=np.int64)
    for i in range(n + 1):
        rank[sa[i]] = i

    lcp = np.full(n + 1, -1, dtype=np.int64)
    lcp[0] = -1
    lcp[1] = 0

    h = 0
    for i in range(n):
        k = rank[i]
        if k > 1:
            j = sa[k - 1]
            while (i + h < n) and (j + h < n) and text[i + h] == text[j + h]:
                h += 1
            lcp[k] = h
        if h > 0:
            h -= 1
    return lcp


def build_suffix_array(text: np.ndarray, n: int) -> np.ndarray:
    """
    Build suffix array using prefix doubling algorithm.
    O(n log^2 n) time, O(n) space. Memory efficient for large n (~1M).
    """
    # Initial ranks from text values. Index n is the empty suffix (smallest).
    rank = text.tolist()
    rank.append(-1)
    
    sa = list(range(n + 1))
    k = 1
    while k <= n:
        # Sort by (rank[i], rank[i+k])
        sa.sort(key=lambda i: (rank[i], rank[i + k] if i + k <= n else -1))
        
        # Recompute ranks based on sorted order
        new_rank = [0] * (n + 1)
        for i in range(1, n + 1):
            prev, curr = sa[i-1], sa[i]
            prev_key = (rank[prev], rank[prev + k] if prev + k <= n else -1)
            curr_key = (rank[curr], rank[curr + k] if curr + k <= n else -1)
            new_rank[curr] = new_rank[prev] + (1 if prev_key != curr_key else 0)
        rank = new_rank
        
        # If all ranks are distinct, sorting is complete
        if rank[sa[n]] == n:
            break
        k <<= 1
        
    return np.array(sa, dtype=np.int64)


def sa_algs(
    text: np.ndarray, n: int, k: int, verbose: int = 0, label: str = ""
) -> tuple:
    """
    Simultaneously compute t-Tuple and LRS estimates.
    Matches C++ SAalgs32/SAalgs64 in lrs_test.h.
    Uses Python int for arbitrary precision (replaces uint128_t).
    """
    sa = build_suffix_array(text, n)
    L = sa_to_lcp(text, n, sa)

    L = L.tolist()
    L.append(0)
    L = L[1:]
    assert L[0] == 0

    v = 0
    for i in range(n):
        if L[i] > v:
            v = L[i]

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
