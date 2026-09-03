"""NIST SP 800-90B Entropy Assessment - LZ78Y (Section 6.3.10)"""

from __future__ import annotations

from typing import Sequence, Union

import numpy as np

from ._config import B_len, MAX_DICTIONARY_SIZE
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


def _binary_lz78y_counts(s: bytes, length: int) -> tuple:
    """
    The binary LZ78Y prediction loop, returning ``(correct_count, max_run)``.

    Unlike MultiMMC, LZ78Y queries every context length from the longest one
    down to a single bit, keeps *all* of them (a miss on a long context does
    not stop the shorter ones) and predicts with the context that has the
    largest count. One dictionary budget is shared by every length.

    ``binary_dict[j - 1]`` is the table for the ``j``-bit contexts, addressed
    with the *newest* symbol in bit 0, so the whole j-loop only needs one
    rolling register instead of re-reading j symbols per context.

    This is the CPython version: the per-length tables are lists of lists and
    every counter access is a plain Python integer operation.
    """
    B = B_len

    binary_dict = [[0] * (1 << (j + 2)) for j in range(B)]
    masks = [(1 << j) - 1 for j in range(B + 1)]
    full_mask = masks[B]
    dict_elems = 0

    # Initialize with (S[B-1]) -> S[B], (S[B-2], S[B-1]) -> S[B], ...
    init_window = 0
    for j in range(B):
        init_window = (init_window << 1) | (s[j] & 1)

    for j in range(1, B + 1):
        binary_dict[j - 1][((init_window & masks[j]) << 1) | (s[B] & 1)] = 1
        dict_elems += 1

    correct_count = 0
    cur_run = 0
    max_run = 0

    # i is the index of the bit to be predicted; bit j of ``window`` holds
    # S[i-1-j], which is exactly the reference's compressedBitSymbols() window.
    # The first prediction covers S[1]...S[B].
    window = ((init_window << 1) | (s[B] & 1)) & full_mask

    for i in range(B + 1, length):
        sym = s[i] & 1
        have_prediction = False
        cur_prediction = 2
        max_count = 0

        for j in range(B, 0, -1):
            entry = binary_dict[j - 1]
            pos = (window & masks[j]) << 1

            c0 = entry[pos]
            c1 = entry[pos + 1]
            if c0 > c1:
                round_prediction = 0
                cur_count = c0
            else:
                round_prediction = 1
                cur_count = c1

            if cur_count != 0:
                # x is present in the dictionary as a prefix
                if cur_count > max_count:
                    max_count = cur_count
                    have_prediction = True
                    cur_prediction = round_prediction
                entry[pos | sym] += 1
            elif dict_elems < MAX_DICTIONARY_SIZE:
                entry[pos | sym] = 1
                dict_elems += 1

        if have_prediction and cur_prediction == sym:
            correct_count += 1
            cur_run += 1
            if cur_run > max_run:
                max_run = cur_run
        else:
            cur_run = 0

        window = ((window << 1) | sym) & full_mask

    return correct_count, max_run


@Kernel
def _binary_lz78y_kernel(bits, length):
    """
    Same loop as :func:`_binary_lz78y_counts`, written so that numba can
    compile it: the ``B`` tables are flattened into one ``int64`` array, since
    a numba array of arrays would box on every access. ``bits`` is the same
    buffer :func:`_as_bytes` produced, taken as a read-only uint8 view.

    The two bodies have to stay in lockstep - ``est_test_nist_cpp_recode/
    jit_crosscheck.py`` checks that they do.
    """
    B = B_len

    # binary_dict[j - 1] occupies the slice starting at sum_{e<j} 2^(e+2) = 2^(j+2) - 8
    offsets = np.empty(B, dtype=np.int64)
    for j in range(1, B + 1):
        offsets[j - 1] = (1 << (j + 2)) - 8

    binary_dict = np.zeros((1 << (B + 3)) - 8, dtype=np.int64)
    masks = np.empty(B + 1, dtype=np.int64)
    for j in range(B + 1):
        masks[j] = (1 << j) - 1
    full_mask = masks[B]
    dict_elems = 0

    init_window = 0
    for j in range(B):
        init_window = (init_window << 1) | (int(bits[j]) & 1)

    for j in range(1, B + 1):
        binary_dict[offsets[j - 1] + (((init_window & masks[j]) << 1) | (int(bits[B]) & 1))] = 1
        dict_elems += 1

    correct_count = 0
    cur_run = 0
    max_run = 0
    window = ((init_window << 1) | (int(bits[B]) & 1)) & full_mask

    for i in range(B + 1, length):
        sym = int(bits[i]) & 1
        have_prediction = False
        cur_prediction = 2
        max_count = 0

        for j in range(B, 0, -1):
            base = offsets[j - 1]
            pos = (window & masks[j]) << 1

            c0 = binary_dict[base + pos]
            c1 = binary_dict[base + pos + 1]
            if c0 > c1:
                round_prediction = 0
                cur_count = c0
            else:
                round_prediction = 1
                cur_count = c1

            if cur_count != 0:
                if cur_count > max_count:
                    max_count = cur_count
                    have_prediction = True
                    cur_prediction = round_prediction
                binary_dict[base + (pos | sym)] += 1
            elif dict_elems < MAX_DICTIONARY_SIZE:
                binary_dict[base + (pos | sym)] = 1
                dict_elems += 1

        if have_prediction and cur_prediction == sym:
            correct_count += 1
            cur_run += 1
            if cur_run > max_run:
                max_run = cur_run
        else:
            cur_run = 0

        window = ((window << 1) | sym) & full_mask

    return correct_count, max_run


def binary_lz78y_test(
    data: _ArrayLike, length: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.10: LZ78Y Test (binary optimized), matching
    ``binaryLZ78YPredictionEstimate()``.

    Both paths below count the same predictions; only the estimate step is shared.
    """
    assert length > B_len, "LZ78Y needs more than B_len samples"
    assert length - B_len > 2
    assert B_len < 32  # B < 32 so the reference's shifts stay well defined

    B = B_len
    s = _as_bytes(data, length)
    if use_jit(length):
        correct_count, max_run = _binary_lz78y_kernel(
            np.frombuffer(s, dtype=np.uint8), length)
    else:
        correct_count, max_run = _binary_lz78y_counts(s, length)

    return prediction_estimate(correct_count, length - B - 1, max_run, 2, "LZ78Y", verbose, label)


def lz78y_test(
    data: _ArrayLike, length: int, alph_size: int,
    verbose: int = 0, label: str = ""
) -> float:
    """
    Section 6.3.10: LZ78Y Test (general alphabet).

    Matching ``LZ78Y_test()`` in ``lz78y_test.h``, one map per context length
    ``j`` holds the observed contexts and their :class:`PostfixDictionary` of
    continuations. Contexts are packed into an integer with the newest symbol
    in the low byte, a bijection for the fixed length of each map.
    """
    if alph_size == 2:
        return binary_lz78y_test(data, length, verbose, label)

    if length < B_len + 2:
        print(f"\t*** Warning: not enough samples to run LZ78Y test (need more than {B_len + 2}) ***")
        return -1.0

    B = B_len
    s = _as_bytes(data, length)

    N = length - B - 1
    D = [dict() for _ in range(B)]
    masks = [(1 << (8 * j)) - 1 for j in range(B + 1)]
    full_mask = masks[B]

    C = 0
    run_len = 0
    max_run_len = 0

    # Initialize the dictionary with (S[B-1]) -> S[B], ..., (S[0]...S[B-1]) -> S[B]
    dict_size = 0
    init_window = 0
    for j in range(B):
        init_window = (init_window << 8) | s[j]

    for j in range(1, B + 1):
        D[j - 1].setdefault(init_window & masks[j], PostfixDictionary()).increment_postfix(s[B], True)
        dict_size += 1

    # i is the index of the symbol to be predicted; byte j of ``window`` holds
    # S[i-1-j]. The first prediction covers S[1]...S[B].
    window = ((init_window << 8) | s[B]) & full_mask

    for i in range(B + 1, length):
        sym = s[i]
        have_prediction = False
        prediction = 0
        max_count = 0

        for j in range(B, 0, -1):
            key = window & masks[j]
            curp = D[j - 1].get(key)

            if curp is not None:
                # x has occurred; the prediction is the most likely postfix.
                count, y = curp.predict()
                if count > max_count:
                    max_count = count
                    prediction = y
                    have_prediction = True
                # x exists as a prefix, so (x, y) is always counted.
                curp.increment_postfix(sym, True)
            elif dict_size < MAX_DICTIONARY_SIZE:
                D[j - 1].setdefault(key, PostfixDictionary()).increment_postfix(sym, True)
                dict_size += 1

        if have_prediction and prediction == sym:
            C += 1
            run_len += 1
            if run_len > max_run_len:
                max_run_len = run_len
        else:
            run_len = 0

        window = ((window << 8) | sym) & full_mask

    return prediction_estimate(C, N, max_run_len, alph_size, "LZ78Y", verbose, label)
