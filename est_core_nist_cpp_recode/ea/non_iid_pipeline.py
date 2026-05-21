"""NIST SP 800-90B Entropy Assessment - Non-IID Pipeline"""

from __future__ import annotations

import datetime
import hashlib
import sys
from typing import Optional

import numpy as np

from ._config import MIN_SIZE
from ._io import free_data, read_file
from ._types import DataT, NonIidTestCase, NonIidTestRun
from ._util import calc_stats
from .mcv import most_common_value
from .collision import collision_test
from .markov import markov_test
from .compression import compression_test
from ._lrs import sa_algs
from .multi_mcw import multi_mcw_test
from .lag_test import lag_test
from .multi_mmc import multi_mmc_test
from .lz78y import lz78y_test


def run_non_iid_test(
    file_path: str,
    bits_per_symbol: int = 0,
    verbose: int = 1,
) -> NonIidTestRun:
    """
    Run the full Non-IID entropy assessment pipeline.
    Matches C++ non_iid_main.cpp logic.
    """
    run = NonIidTestRun()
    run.timestamp = datetime.datetime.now().isoformat()
    run.commandline = " ".join(sys.argv)
    run.filename = file_path
    run.type = "Non-IID"

    try:
        with open(file_path, 'rb') as f:
            run.sha256 = hashlib.sha256(f.read()).hexdigest()
    except Exception:
        run.sha256 = ""

    dp = DataT(word_size=bits_per_symbol)
    if not read_file(file_path, dp, run):
        return run

    if dp.len < MIN_SIZE:
        run.error_level = -1
        run.error_msg = f"Data too short: {dp.len} < {MIN_SIZE}"
        free_data(dp)
        return run

    rawmean, median = calc_stats(dp)
    binary = dp.alph_size == 2

    test_cases = []

    print(f"Data Word Size: {dp.word_size}")
    print(f"Alphabet Size: {dp.alph_size}")
    print(f"Sample Size: {dp.len}")
    print(f"Mean: {rawmean}")
    print(f"Median: {median}")

    # ===================== Case 1: Most Common Value =====================
    tc_mcv = NonIidTestCase()
    h_original = most_common_value(dp.symbols, dp.len, dp.alph_size, verbose, "", tc_mcv)
    tc_mcv.h_original = h_original
    h_bitstring_mcv = most_common_value(dp.bsymbols, dp.blen, 2, verbose, "Bitstring")
    tc_mcv.h_bitstring = h_bitstring_mcv
    tc_mcv.test_case_number = "Most Common Value"
    test_cases.append(tc_mcv)
    print(f"H_original: {h_original}")
    print(f"H_bitstring (MCV): {h_bitstring_mcv}")

    # ===================== Cases 2-4: Binary-only estimators =====================
    h_col = h_markov = h_comp = -1.0
    if binary:
        h_col = collision_test(dp.bsymbols, dp.blen, verbose, "")
        h_markov = markov_test(dp.bsymbols, dp.blen, verbose, "")
        h_comp = compression_test(dp.bsymbols, dp.blen, verbose, "")

    # Case 2: Collision
    tc_collision = NonIidTestCase()
    tc_collision.test_case_number = "Collision Test (for bit strings only)"
    if h_col >= 0:
        tc_collision.h_bitstring = h_col
        tc_collision.h_original = h_col
        print(f"H_bitstring (Collision): {h_col}")
    test_cases.append(tc_collision)

    # Case 3: Markov
    tc_markov = NonIidTestCase()
    tc_markov.test_case_number = "Markov Test (for bit strings only)"
    if h_markov >= 0:
        tc_markov.h_bitstring = h_markov
        tc_markov.h_original = h_markov
        print(f"H_bitstring (Markov): {h_markov}")
    test_cases.append(tc_markov)

    # Case 4: Compression
    tc_comp = NonIidTestCase()
    tc_comp.test_case_number = "Compression Test (for bit strings only)"
    if h_comp >= 0:
        tc_comp.h_bitstring = h_comp
        tc_comp.h_original = h_comp
        print(f"H_bitstring (Compression): {h_comp}")
    test_cases.append(tc_comp)

    # Build h_bitstring running min
    h_bitstring = h_bitstring_mcv
    if h_col >= 0:
        h_bitstring = min(h_bitstring, h_col)
    if h_markov >= 0:
        h_bitstring = min(h_bitstring, h_markov)
    if h_comp >= 0:
        h_bitstring = min(h_bitstring, h_comp)

    # ===================== Cases 5-6: t-Tuple and LRS =====================
    t_tuple_res, lrs_res = sa_algs(dp.symbols, dp.len, dp.alph_size, verbose, "")
    bin_t_tuple_res, bin_lrs_res = -1.0, -1.0
    if binary:
        bin_t_tuple_res, bin_lrs_res = sa_algs(dp.bsymbols, dp.blen, 2, verbose, "Bin")

    # Case 5: T-Tuple
    tc_ttuple = NonIidTestCase()
    tc_ttuple.test_case_number = "T-Tuple Test"
    tc_ttuple.t_tuple_res = t_tuple_res
    tc_ttuple.bin_t_tuple_res = bin_t_tuple_res
    test_cases.append(tc_ttuple)
    if t_tuple_res >= 0:
        print(f"H_original (t-Tuple): {t_tuple_res}")
    if bin_t_tuple_res >= 0:
        print(f"H_bitstring (t-Tuple): {bin_t_tuple_res}")

    # Case 6: LRS
    tc_lrs = NonIidTestCase()
    tc_lrs.test_case_number = "LRS Test"
    tc_lrs.lrs_res = lrs_res
    tc_lrs.bin_lrs_res = bin_lrs_res
    test_cases.append(tc_lrs)
    if lrs_res >= 0:
        print(f"H_original (LRS): {lrs_res}")
    if bin_lrs_res >= 0:
        print(f"H_bitstring (LRS): {bin_lrs_res}")

    if t_tuple_res >= 0:
        h_original = min(h_original, t_tuple_res)
    if lrs_res >= 0:
        h_original = min(h_original, lrs_res)
    if bin_t_tuple_res >= 0:
        h_bitstring = min(h_bitstring, bin_t_tuple_res)
    if bin_lrs_res >= 0:
        h_bitstring = min(h_bitstring, bin_lrs_res)

    # ===================== Cases 7-10: Prediction-based estimators =====================
    # Case 7: Multi Most Common in Window
    h_multi_mcw = multi_mcw_test(dp.symbols, dp.len, dp.alph_size, verbose, "")
    h_multi_mcw_bit = multi_mcw_test(dp.bsymbols, dp.blen, 2, verbose, "Bin")
    tc_multi_mcw = NonIidTestCase()
    tc_multi_mcw.test_case_number = "Multi Most Common in Window Test"
    tc_multi_mcw.h_original = h_multi_mcw
    tc_multi_mcw.h_bitstring = h_multi_mcw_bit
    test_cases.append(tc_multi_mcw)
    print(f"H_original (MultiMCW): {h_multi_mcw}")
    print(f"H_bitstring (MultiMCW): {h_multi_mcw_bit}")
    h_original = min(h_original, h_multi_mcw)
    h_bitstring = min(h_bitstring, h_multi_mcw_bit)

    # Case 8: Lag Prediction
    h_lag = lag_test(dp.symbols, dp.len, dp.alph_size, verbose, "")
    h_lag_bit = lag_test(dp.bsymbols, dp.blen, 2, verbose, "Bin")
    tc_lag = NonIidTestCase()
    tc_lag.test_case_number = "Lag Prediction Test"
    tc_lag.h_original = h_lag
    tc_lag.h_bitstring = h_lag_bit
    test_cases.append(tc_lag)
    print(f"H_original (Lag): {h_lag}")
    print(f"H_bitstring (Lag): {h_lag_bit}")
    h_original = min(h_original, h_lag)
    h_bitstring = min(h_bitstring, h_lag_bit)

    # Case 9: Multi Markov Model with Counting Test (MultiMMC)
    h_multi_mmc = multi_mmc_test(dp.symbols, dp.len, dp.alph_size, verbose, "")
    h_multi_mmc_bit = multi_mmc_test(dp.bsymbols, dp.blen, 2, verbose, "Bin")
    tc_multi_mmc = NonIidTestCase()
    tc_multi_mmc.test_case_number = "Multi Markov Model with Counting Test (MultiMMC)"
    tc_multi_mmc.h_original = h_multi_mmc
    tc_multi_mmc.h_bitstring = h_multi_mmc_bit
    test_cases.append(tc_multi_mmc)
    print(f"H_original (MultiMMC): {h_multi_mmc}")
    print(f"H_bitstring (MultiMMC): {h_multi_mmc_bit}")
    h_original = min(h_original, h_multi_mmc)
    h_bitstring = min(h_bitstring, h_multi_mmc_bit)

    # Case 10: LZ78Y
    h_lz78y = lz78y_test(dp.symbols, dp.len, dp.alph_size, verbose, "")
    h_lz78y_bit = lz78y_test(dp.bsymbols, dp.blen, 2, verbose, "Bin")
    tc_lz78y = NonIidTestCase()
    tc_lz78y.test_case_number = "LZ78Y Test"
    tc_lz78y.h_original = h_lz78y
    tc_lz78y.h_bitstring = h_lz78y_bit
    test_cases.append(tc_lz78y)
    print(f"H_original (LZ78Y): {h_lz78y}")
    print(f"H_bitstring (LZ78Y): {h_lz78y_bit}")
    h_original = min(h_original, h_lz78y)
    h_bitstring = min(h_bitstring, h_lz78y_bit)

    # ===================== Case 11: Overall =====================
    tc_overall = NonIidTestCase()
    tc_overall.test_case_number = "Overall"
    tc_overall.h_original = h_original
    tc_overall.h_bitstring = h_bitstring
    tc_overall.data_word_size = float(dp.word_size)
    tc_overall.h_assessed = min(h_original, dp.word_size * h_bitstring)
    test_cases.append(tc_overall)

    print(f"H_original (final): {h_original}")
    print(f"H_bitstring (final): {h_bitstring}")
    print(f"H_assessed: {tc_overall.h_assessed}")

    run.test_cases = test_cases
    free_data(dp)
    return run
