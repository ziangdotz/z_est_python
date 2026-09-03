"""NIST SP 800-90B Entropy Assessment - File I/O and Symbol Mapping"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

import numpy as np

from ._types import DataT, TestRunBase

_SHA256_CHUNK = 1 << 20


def file_sha256(file_path: str) -> str:
    """
    SHA-256 of a file, streamed in chunks.

    Reading the whole file into memory just to hash it doubles peak memory for
    large samples, so hash incrementally instead. Returns "" on failure
    (same convention the pipelines already use).
    """
    digest = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(_SHA256_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _detect_word_size(symbols: np.ndarray) -> int:
    """
    Auto-detect word size by finding the highest bit in use.
    Matches C++ logic: OR-reduce every symbol, then scan down from bit 7 until a
    set bit is found. The scan is just the bit length of the OR-reduced mask.
    """
    if symbols.size == 0:
        return 0
    datamask = int(np.bitwise_or.reduce(symbols)) & 0xFF
    return datamask.bit_length()


def _word_size_error(actual_width: int, dp: DataT, test_run: Optional[TestRunBase]) -> bool:
    """
    Validate a caller-supplied word size against the detected one.
    Returns True if the data does not fit the described bit width.
    """
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
        return True
    return False


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

    # Build symbol_map_down_table: every value actually present is ranked by how
    # many present values precede it (C++ assigns alph_size++ while scanning the
    # table upwards, which is the same ordering).
    present = np.bincount(dp.symbols, minlength=max_symbols)[:max_symbols] > 0
    dp.alph_size = int(present.sum())
    symbol_map = np.cumsum(present, dtype=np.int32) - 1

    # Map down symbols
    dp.symbols = symbol_map[dp.symbols].astype(np.uint8)

    # Build bsymbols from rawsymbols (non-mapped, but masked)
    dp.blen = dp.len * dp.word_size
    if dp.word_size == 1:
        dp.bsymbols = dp.symbols
    else:
        # unpackbits() yields each byte MSB-first, so the low word_size bits of a
        # symbol are the trailing columns of every row.
        bits = np.unpackbits(dp.rawsymbols, bitorder='big').reshape(dp.len, 8)
        dp.bsymbols = np.ascontiguousarray(bits[:, 8 - dp.word_size:]).reshape(-1)


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
        if dp.word_size == 0:
            if test_run:
                test_run.error_level = -1
                test_run.error_msg = (
                    f"Error: unable to determine word size for '{file_path}': "
                    f"every input byte is zero."
                )
            return False
    elif _word_size_error(_detect_word_size(dp.symbols), dp, test_run):
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
        if dp.word_size == 0:
            if test_run:
                test_run.error_level = -1
                test_run.error_msg = (
                    f"Error: unable to determine word size for '{file_path}': "
                    f"every input byte is zero."
                )
            return False
    elif _word_size_error(_detect_word_size(dp.symbols), dp, test_run):
        return False

    _map_symbols(dp)
    return True


def free_data(dp: DataT) -> None:
    """Release DataT numpy arrays."""
    dp.symbols = None
    dp.rawsymbols = None
    if dp.word_size > 1:
        dp.bsymbols = None
