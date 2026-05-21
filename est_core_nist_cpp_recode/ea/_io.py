"""NIST SP 800-90B Entropy Assessment - File I/O and Symbol Mapping"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

from ._types import DataT, TestRunBase


def _detect_word_size(symbols: np.ndarray) -> int:
    """
    Auto-detect word size by finding the highest bit in use.
    Matches C++ logic: iterates from bit 7 down, finds first set bit.
    """
    datamask = 0
    for b in symbols:
        datamask |= int(b)

    curbit = 0x80
    i = 8
    while i > 0 and (datamask & curbit) == 0:
        curbit >>= 1
        i -= 1
    return i


def _map_symbols(dp: DataT) -> None:
    """
    Map symbols to contiguous indices [0, alph_size).
    Builds bsymbols (bit-expanded) from the non-mapped data.
    """
    dp.rawsymbols = dp.symbols.copy()
    dp.maxsymbol = int(np.max(dp.symbols))

    max_symbols = 1 << dp.word_size
    mask = max_symbols - 1

    # Apply mask
    dp.symbols = dp.symbols & mask

    # Update maxsymbol after masking
    dp.maxsymbol = int(np.max(dp.symbols))

    # Build symbol_map_down_table
    unique_vals = np.unique(dp.symbols)
    dp.alph_size = len(unique_vals)

    symbol_map = np.zeros(max_symbols, dtype=np.int32)
    for new_idx, val in enumerate(unique_vals):
        symbol_map[val] = new_idx

    # Map down symbols
    dp.symbols = symbol_map[dp.symbols].astype(np.uint8)

    # Build bsymbols from rawsymbols (non-mapped, but masked)
    dp.blen = dp.len * dp.word_size
    if dp.word_size == 1:
        dp.bsymbols = dp.symbols
    else:
        dp.bsymbols = np.zeros(dp.blen, dtype=np.uint8)
        for i in range(dp.len):
            for j in range(dp.word_size):
                dp.bsymbols[i * dp.word_size + j] = \
                    (dp.rawsymbols[i] >> (dp.word_size - 1 - j)) & 0x1


def read_file(
    file_path: str,
    dp: DataT,
    test_run: Optional[TestRunBase] = None
) -> bool:
    """
    Read binary file into DataT.
    Matches C++ read_file() in utils.h.
    """
    if not os.path.exists(file_path):
        if test_run:
            test_run.error_level = -1
            test_run.error_msg = f"Error: could not open '{file_path}'"
        return False

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        if test_run:
            test_run.error_level = -1
            test_run.error_msg = f"Error: '{file_path}' is empty"
        return False

    with open(file_path, 'rb') as f:
        raw = np.frombuffer(f.read(), dtype=np.uint8).copy()

    dp.len = len(raw)
    dp.symbols = raw

    # Detect/validate word size
    if dp.word_size == 0:
        dp.word_size = _detect_word_size(dp.symbols)
    else:
        actual_width = _detect_word_size(dp.symbols)
        if actual_width < dp.word_size:
            if test_run:
                test_run.error_msg = "Warning: Symbols appear to be narrower than described."
        elif actual_width > dp.word_size:
            if test_run:
                test_run.error_level = -1
                test_run.error_msg = (
                    f"Error: Incorrect bit width specification: "
                    f"Data ({actual_width}) does not fit within described "
                    f"bit width: {dp.word_size}."
                )
            return False

    _map_symbols(dp)
    return True


def read_file_subset(
    file_path: str,
    dp: DataT,
    subset_index: int,
    subset_size: int,
    test_run: Optional[TestRunBase] = None
) -> bool:
    """
    Read a subset of a binary file into DataT.
    Matches C++ read_file_subset() in utils.h.
    """
    if not os.path.exists(file_path):
        if test_run:
            test_run.error_level = -1
            test_run.error_msg = f"Error: could not open '{file_path}'"
        return False

    file_size = os.path.getsize(file_path)

    with open(file_path, 'rb') as f:
        if subset_size == 0:
            f.seek(0)
            raw = np.frombuffer(f.read(), dtype=np.uint8).copy()
            dp.len = len(raw)
        else:
            offset = subset_index * subset_size
            if offset > file_size:
                if test_run:
                    test_run.error_level = -1
                    test_run.error_msg = "Error: fseek failed"
                return False
            f.seek(offset)
            available = file_size - offset
            to_read = min(available, subset_size)
            if to_read == 0:
                if test_run:
                    test_run.error_level = -1
                    test_run.error_msg = f"Error: '{file_path}' is empty"
                return False
            raw = np.frombuffer(f.read(to_read), dtype=np.uint8).copy()
            dp.len = len(raw)

    dp.symbols = raw

    if dp.word_size == 0:
        dp.word_size = _detect_word_size(dp.symbols)
    else:
        actual_width = _detect_word_size(dp.symbols)
        if actual_width < dp.word_size:
            if test_run:
                test_run.error_msg = "Warning: Symbols appear to be narrower than described."
        elif actual_width > dp.word_size:
            if test_run:
                test_run.error_level = -1
                test_run.error_msg = (
                    f"Error: Incorrect bit width specification: "
                    f"Data ({actual_width}) does not fit within described "
                    f"bit width: {dp.word_size}."
                )
            return False

    _map_symbols(dp)
    return True


def free_data(dp: DataT) -> None:
    """Release DataT numpy arrays."""
    dp.symbols = None
    dp.rawsymbols = None
    if dp.word_size > 1:
        dp.bsymbols = None
