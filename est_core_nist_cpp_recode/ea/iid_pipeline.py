"""NIST SP 800-90B Entropy Assessment - IID Pipeline"""

from __future__ import annotations

import datetime
import sys
from typing import Optional

import numpy as np

from ._config import MIN_SIZE
from ._io import file_sha256, free_data, read_file, read_file_subset
from ._types import DataT, IidTestCase, IidTestRun
from ._util import calc_stats
from .chi_square import chi_square_tests
from .mcv import most_common_value
from .permutation import permutation_tests
from ._lrs import len_lrs_test


def run_iid_test(
    file_path: str,
    bits_per_symbol: int = 0,
    initial: bool = True,
    all_bits: bool = True,
    verbose: int = 1,
    num_workers: Optional[int] = None,
) -> IidTestRun:
    """
    Run the full IID entropy assessment pipeline.
    Matches C++ iid_main.cpp logic.

    ``num_workers`` bounds the processes the permutation test may spread its
    rounds over; ``None`` uses one per physical core.
    """
    run = IidTestRun()
    run.timestamp = datetime.datetime.now().isoformat()
    run.commandline = " ".join(sys.argv)
    run.filename = file_path
    run.type = "IID"

    run.sha256 = file_sha256(file_path)

    dp = DataT(word_size=bits_per_symbol)
    if not read_file(file_path, dp, run):
        return run

    # A single-symbol alphabet carries no entropy to assess; the reference
    # (`iid_main.cpp`) reports it as an error and stops.
    if dp.alph_size <= 1:
        run.error_level = -1
        run.error_msg = "Symbol alphabet consists of 1 symbol. No entropy awarded..."
        print(run.error_msg)
        free_data(dp)
        return run

    if not all_bits and dp.blen > MIN_SIZE:
        dp.blen = MIN_SIZE

    # Anything below MIN_SIZE samples is merely a warning: the assessment is
    # less reliable, but the reference still runs every estimate on it.
    if dp.len < MIN_SIZE:
        print(f"\n*** Warning: data contains less than {MIN_SIZE} samples ***\n")

    rawmean, median = calc_stats(dp)
    binary = dp.alph_size == 2

    tc = IidTestCase()
    tc.mean = rawmean
    tc.median = median
    tc.binary = binary
    tc.data_word_size = float(dp.word_size)
    tc.test_case_number = "Initial" if initial else "Conditioned"

    print(f"Data Word Size: {dp.word_size}")
    print(f"Alphabet Size: {dp.alph_size}")
    print(f"Sample Size: {dp.len}")
    print(f"Mean: {rawmean}")
    print(f"Median: {median}")

    chi_sq_passed = chi_square_tests(dp.symbols, dp.len, dp.alph_size, verbose)
    tc.passed_chi_square_tests = chi_sq_passed
    print(f"Chi Square Tests: {'Passed' if chi_sq_passed else 'Failed'}")

    lrs_passed = len_lrs_test(dp.symbols, dp.len, dp.alph_size, verbose, "")
    tc.passed_longest_repeated_substring_test = lrs_passed
    print(f"Longest Repeated Substring Test: {'Passed' if lrs_passed else 'Failed'}")

    h_original = most_common_value(dp.symbols, dp.len, dp.alph_size, verbose, "", tc)
    tc.ret_min_entropy = h_original
    print(f"H_original: {h_original}")

    # ``dp.blen`` already reflects the `-a`/`-t` choice made above; the bit
    # buffer itself is never trimmed, so hand the estimate a view of the prefix
    # that is to be assessed.
    bit_len = dp.blen
    bit_data = dp.bsymbols[:bit_len]

    h_bitstring = most_common_value(bit_data, bit_len, 2, verbose, "")
    print(f"H_bitstring: {h_bitstring}")

    perm_passed = permutation_tests(dp, rawmean, median, verbose, tc, num_workers=num_workers)
    tc.passed_iid_permutation_tests = perm_passed
    print(f"IID Permutation Tests: {'Passed' if perm_passed else 'Failed'}")

    tc.h_original = h_original
    tc.h_bitstring = h_bitstring
    tc.h_assessed = min(h_original, dp.word_size * h_bitstring)

    print(f"H_assessed: {tc.h_assessed}")

    run.test_cases = [tc]
    free_data(dp)
    return run


def run_iid_test_subset(
    file_path: str,
    subset_index: int,
    subset_size: int,
    bits_per_symbol: int = 0,
    verbose: int = 1,
    num_workers: Optional[int] = None,
) -> IidTestRun:
    """Run IID test on a subset of the file."""
    run = IidTestRun()
    run.timestamp = datetime.datetime.now().isoformat()
    run.commandline = " ".join(sys.argv)
    run.filename = file_path
    run.type = "IID"

    dp = DataT(word_size=bits_per_symbol)
    if not read_file_subset(file_path, dp, subset_index, subset_size, run):
        return run

    rawmean, median = calc_stats(dp)
    binary = dp.alph_size == 2

    tc = IidTestCase()
    tc.mean = rawmean
    tc.median = median
    tc.binary = binary
    tc.data_word_size = float(dp.word_size)
    tc.test_case_number = f"Subset {subset_index}"

    chi_sq_passed = chi_square_tests(dp.symbols, dp.len, dp.alph_size, verbose)
    tc.passed_chi_square_tests = chi_sq_passed

    lrs_passed = len_lrs_test(dp.symbols, dp.len, dp.alph_size, verbose, "")
    tc.passed_longest_repeated_substring_test = lrs_passed

    h_original = most_common_value(dp.symbols, dp.len, dp.alph_size, verbose, "", tc)
    tc.ret_min_entropy = h_original

    h_bitstring = most_common_value(dp.bsymbols, dp.blen, 2, verbose, "")

    perm_passed = permutation_tests(dp, rawmean, median, verbose, tc, num_workers=num_workers)
    tc.passed_iid_permutation_tests = perm_passed

    tc.h_original = h_original
    tc.h_bitstring = h_bitstring
    tc.h_assessed = min(h_original, dp.word_size * h_bitstring)

    run.test_cases = [tc]
    free_data(dp)
    return run
