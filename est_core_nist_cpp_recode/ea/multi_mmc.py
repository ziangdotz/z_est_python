"""NIST SP 800-90B Entropy Assessment - MultiMMC (Section 6.3.9)"""

from __future__ import annotations

from typing import Sequence, Union

import numpy as np

from ._config import D_MMC, MAX_ENTRIES
from ._jit import Kernel, use_jit
from ._types import PostfixDictionary
from ._util import prediction_estimate

_ArrayLike = Union[np.ndarray, Sequence[int]]


def _as_bytes(data: _ArrayLike, length: int) -> bytes:
    """
    Symbol stream as ``bytes``.

    The tests walk the alphabet one symbol at a time; indexing a numpy array
    costs several times more than indexing a ``bytes`` object, and the symbol
    values always fit in a byte (alph_size <= 256).
    """
    if isinstance(data, np.ndarray):
        return data[:length].tobytes()
    return bytes(data[:length])


def _binary_multi_mmc_counts(s: bytes, length: int) -> tuple:
    """
    The binary MultiMMC prediction loop, returning ``(correct_count, max_run)``.

    ``binaryDict[d]`` stores, for every (d+1)-bit context, the pair of counters
    of the symbols that followed it. Contexts are addressed with the *newest*
    symbol in bit 0 - the same layout the reference builds with
    ``curPattern | (S[i-d-1] << d)`` - so the whole d-loop only needs one
    rolling register instead of re-reading d+1 symbols per context.

    This is the CPython version: the per-depth tables are lists of lists and
    every counter access is a plain Python integer operation.
    """
    D = D_MMC

    binary_dict = [[0] * (1 << (d + 2)) for d in range(D)]
    dict_elems = [0] * D
    scoreboard = [0] * D
    masks = [(1 << (d + 1)) - 1 for d in range(D)]
    full_mask = masks[-1]
    winner = 0

    # Initialize the MMC counts with (S[0], S[1]), (S[0..1], S[2]), ...
    # The reference only guards on L > 3, so stop early for very short inputs.
    cur_pattern = 0
    for d in range(min(D, length - 1)):
        cur_pattern = (cur_pattern << 1) | (s[d] & 1)
        binary_dict[d][(cur_pattern << 1) | (s[d + 1] & 1)] = 1
        dict_elems[d] = 1

    correct_count = 0
    cur_run = 0
    max_run = 0

    # i is the index of the symbol to be predicted; bit j of ``window`` holds
    # S[i-1-j], i.e. the window slides with the newest symbol in bit 0.
    window = s[1] & 1

    for i in range(2, length):
        cur_winner = winner
        sym = s[i] & 1
        found_x = False
        cur_prediction = 0
        cur_count = 0

        for d in range(min(D, i - 1)):
            entry = binary_dict[d]
            pos = (window & masks[d]) << 1

            if d == 0 or found_x:
                c0 = entry[pos]
                c1 = entry[pos + 1]
                if c0 > c1:
                    cur_prediction = 0
                    cur_count = c0
                else:
                    cur_prediction = 1
                    cur_count = c1
                found_x = cur_count != 0

            if found_x:
                if cur_prediction == sym:
                    scoreboard[d] += 1
                    if scoreboard[d] >= scoreboard[winner]:
                        winner = d
                    if d == cur_winner:
                        correct_count += 1
                        cur_run += 1
                        if cur_run > max_run:
                            max_run = cur_run
                elif d == cur_winner:
                    cur_run = 0

                pos |= sym
                if entry[pos] != 0:
                    entry[pos] += 1
                elif dict_elems[d] < MAX_ENTRIES:
                    entry[pos] = 1
                    dict_elems[d] += 1
            elif dict_elems[d] < MAX_ENTRIES:
                entry[pos | sym] = 1
                dict_elems[d] += 1

        window = ((window << 1) | sym) & full_mask

    return correct_count, max_run


@Kernel
def _binary_multi_mmc_kernel(bits, length):
    """
    Same loop as :func:`_binary_multi_mmc_counts`, written so that numba can
    compile it: one flat ``int64`` table instead of a list of lists, every
    counter a machine integer. ``bits`` is the same buffer :func:`_as_bytes`
    produced, taken as a read-only uint8 view.

    The two bodies have to stay in lockstep - ``est_test_nist_cpp_recode/
    jit_crosscheck.py`` checks that they do. Uncompiled this is slower than the
    Python version above (numpy element access boxes an integer every time),
    which is why the caller only picks it once numba has compiled it.
    """
    D = D_MMC

    # binary_dict[d] occupies the slice starting at sum_{e<d} 2^(e+2) = 2^(d+2) - 4
    offsets = np.empty(D, dtype=np.int64)
    for d in range(D):
        offsets[d] = (1 << (d + 2)) - 4

    binary_dict = np.zeros((1 << (D + 2)) - 4, dtype=np.int64)
    dict_elems = np.zeros(D, dtype=np.int64)
    scoreboard = np.zeros(D, dtype=np.int64)
    masks = np.empty(D, dtype=np.int64)
    for d in range(D):
        masks[d] = (1 << (d + 1)) - 1
    full_mask = masks[D - 1]
    winner = 0

    cur_pattern = 0
    for d in range(min(D, length - 1)):
        cur_pattern = (cur_pattern << 1) | (int(bits[d]) & 1)
        binary_dict[offsets[d] + ((cur_pattern << 1) | (int(bits[d + 1]) & 1))] = 1
        dict_elems[d] = 1

    correct_count = 0
    cur_run = 0
    max_run = 0
    window = int(bits[1]) & 1

    for i in range(2, length):
        cur_winner = winner
        sym = int(bits[i]) & 1
        found_x = False
        cur_prediction = 0
        cur_count = 0

        for d in range(min(D, i - 1)):
            base = offsets[d]
            pos = (window & masks[d]) << 1

            if d == 0 or found_x:
                c0 = binary_dict[base + pos]
                c1 = binary_dict[base + pos + 1]
                if c0 > c1:
                    cur_prediction = 0
                    cur_count = c0
                else:
                    cur_prediction = 1
                    cur_count = c1
                found_x = cur_count != 0

            if found_x:
                if cur_prediction == sym:
                    scoreboard[d] += 1
                    if scoreboard[d] >= scoreboard[winner]:
                        winner = d
                    if d == cur_winner:
                        correct_count += 1
                        cur_run += 1
                        if cur_run > max_run:
                            max_run = cur_run
                elif d == cur_winner:
                    cur_run = 0

                pos |= sym
                if binary_dict[base + pos] != 0:
                    binary_dict[base + pos] += 1
                elif dict_elems[d] < MAX_ENTRIES:
                    binary_dict[base + pos] = 1
                    dict_elems[d] += 1
            elif dict_elems[d] < MAX_ENTRIES:
                binary_dict[base + (pos | sym)] = 1
                dict_elems[d] += 1

        window = ((window << 1) | sym) & full_mask

    return correct_count, max_run


def binary_multi_mmc_test(
    data: _ArrayLike, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.9: Multi Markov Model with Counting (MultiMMC) Test.
    Binary-optimized version, matching ``binaryMultiMMCPredictionEstimate()``.

    Both paths below count the same predictions; only the estimate step is shared.
    """
    assert length > 3, "MultiMMC needs more than 3 samples"
    assert D_MMC < 31  # D+1 < 32 so the reference's shifts stay well defined

    s = _as_bytes(data, length)
    if use_jit(length):
        correct_count, max_run = _binary_multi_mmc_kernel(
            np.frombuffer(s, dtype=np.uint8), length)
    else:
        correct_count, max_run = _binary_multi_mmc_counts(s, length)

    return prediction_estimate(correct_count, length - 2, max_run, 2, "MultiMMC", verbose, label)


def multi_mmc_test(
    data: _ArrayLike, length: int, alph_size: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.9: MultiMMC Test (general alphabet).

    Matching ``multi_mmc_test()`` in ``multi_mmc_test.h``, the model is one
    map per context length ``d``, keyed by the context itself and holding a
    :class:`PostfixDictionary` of the observed continuations. Contexts are
    packed into an integer with the newest symbol in the low byte, which is a
    bijection for the fixed length of each map.
    """
    if alph_size == 2:
        return binary_multi_mmc_test(data, length, verbose, label)

    if length < 3:
        print("\t*** Warning: not enough samples to run multiMMC test (need more than 3) ***")
        return -1.0

    D = D_MMC
    s = _as_bytes(data, length)

    # N = number of predictions attempted (the reference starts at i = 2)
    N = length - 2
    M = [dict() for _ in range(D)]
    entries = [0] * D
    masks = [(1 << (8 * (d + 1))) - 1 for d in range(D)]
    full_mask = masks[-1]
    scoreboard = [0] * D
    winner = 0

    C = 0
    run_len = 0
    max_run_len = 0

    # Initialize the counts for the (d+1)-tuple (S[0]...S[d]) -> S[d+1]
    init_window = 0
    for d in range(min(D, N)):
        init_window = (init_window << 8) | s[d]
        M[d].setdefault(init_window, PostfixDictionary()).increment_postfix(s[d + 1], True)
        entries[d] = 1

    # i is the index of the symbol to be predicted; byte j of ``window`` holds
    # S[i-1-j]. At i = 2 only the first byte is in use, and the loop below
    # slides one symbol in per prediction.
    window = s[1]

    for i in range(2, length):
        cur_winner = winner
        sym = s[i]
        found_x = False
        curp = None

        for d in range(min(D, i - 1)):
            key = window & masks[d]

            if d == 0 or found_x:
                curp = M[d].get(key)
                found_x = curp is not None

            if found_x:
                count, prediction = curp.predict()
                if prediction == sym:
                    scoreboard[d] += 1
                    if scoreboard[d] >= scoreboard[winner]:
                        winner = d
                    if d == cur_winner:
                        C += 1
                        run_len += 1
                        if run_len > max_run_len:
                            max_run_len = run_len
                elif d == cur_winner:
                    run_len = 0

                if curp.increment_postfix(sym, entries[d] < MAX_ENTRIES):
                    entries[d] += 1
            elif entries[d] < MAX_ENTRIES:
                # The context hasn't been seen, so (x, y) surely hasn't either:
                # insert it. The reference does this with map::operator[].
                M[d].setdefault(key, PostfixDictionary()).increment_postfix(sym, True)
                entries[d] += 1

        window = ((window << 8) | sym) & full_mask

    return prediction_estimate(C, N, max_run_len, alph_size, "MultiMMC", verbose, label)
