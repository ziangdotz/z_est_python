"""NIST SP 800-90B Entropy Assessment - Non-IID Pipeline"""

from __future__ import annotations

import datetime
import sys
from typing import Optional

import numpy as np

from ._config import MIN_SIZE
from ._io import file_sha256, free_data, read_file
from ._parallel import ParallelJobs, auto_workers
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
    all_bits: bool = True,
    num_workers: Optional[int] = None,
) -> NonIidTestRun:
    """
    Run the full Non-IID entropy assessment pipeline.
    Matches C++ non_iid_main.cpp logic.

    ``num_workers`` bounds the processes the estimates may spread over; ``None``
    uses one per physical core, ``1`` keeps everything in this process.
    """
    run = NonIidTestRun()
    run.timestamp = datetime.datetime.now().isoformat()
    run.commandline = " ".join(sys.argv)
    run.filename = file_path
    run.type = "Non-IID"

    run.sha256 = file_sha256(file_path)

    dp = DataT(word_size=bits_per_symbol)
    if not read_file(file_path, dp, run):
        return run

    # A single-symbol alphabet carries no entropy to assess; the reference
    # (`non_iid_main.cpp`) reports it as an error and stops.
    if dp.alph_size <= 1:
        run.error_level = -1
        run.error_msg = "Symbol alphabet consists of 1 symbol. No entropy awarded..."
        print(run.error_msg)
        free_data(dp)
        return run

    # `-t` shortens the bit string behind the "Bitstring" estimates to its first
    # MIN_SIZE bits, `-a` (the default) keeps every bit read. The buffer stays
    # whole, so the estimates work off a view of the assessed prefix.
    if not all_bits and dp.blen > MIN_SIZE:
        dp.blen = MIN_SIZE
    bit_len = dp.blen
    bit_data = dp.bsymbols[:bit_len]

    # Anything below MIN_SIZE samples is merely a warning: the assessment is
    # less reliable, but the reference still runs every estimate on it.
    if dp.len < MIN_SIZE:
        print(f"\n*** Warning: data contains less than {MIN_SIZE} samples ***\n")

    rawmean, median = calc_stats(dp)
    # C++ gates every section twice: the bit-string variant runs when
    # `(alph_size > 2) || !initial_entropy`, the symbol ("literal") variant when
    # `initial_entropy`, and for sections 6.3.2-6.3.4 the literal variant also
    # requires `alph_size == 2`. This tool only ever performs the initial
    # entropy assessment, so `initial_entropy` holds by construction here.
    binary = dp.alph_size == 2
    run_bitstring = not binary

    test_cases = []

    print(f"Data Word Size: {dp.word_size}")
    print(f"Alphabet Size: {dp.alph_size}")
    print(f"Sample Size: {dp.len}")
    print(f"Mean: {rawmean}")
    print(f"Median: {median}")

    # Both running minima start from the largest value the data could report.
    h_original = float(dp.word_size)
    h_bitstring = 1.0

    # ===================== Estimate schedule =====================
    # From section 6.3.2 on, every estimate reads the sample and nothing else:
    # the non-IID assessment draws no random numbers and no estimate looks at
    # another's result, so the whole set can be submitted at once. The run is
    # then bounded by its most expensive estimate instead of by their sum.
    # MCV stays out - it costs microseconds and fills in its own test case.
    #
    # Two views of the sample, named the way the reference labels its output:
    # the bit string (skipped when the data already is binary) and the symbols.
    views = []
    if run_bitstring:
        views.append(("Bitstring", bit_data, bit_len, 2))
    views.append(("Literal", dp.symbols, dp.len, dp.alph_size))

    jobs = []
    for short, func in (("Collision", collision_test),
                        ("Markov", markov_test),
                        ("Compression", compression_test)):
        for view, data, length, _ in views:
            # 6.3.2-6.3.4 are "for bit strings only": they see the symbols only
            # when the data already is binary.
            if view == "Literal" and not binary:
                continue
            jobs.append(((short, view), func, (data, length, verbose, view)))

    # One sa_algs() call yields both the t-Tuple and the LRS estimate.
    for short, func in (("tTupleLRS", sa_algs),
                        ("MultiMCW", multi_mcw_test),
                        ("Lag", lag_test),
                        ("MultiMMC", multi_mmc_test),
                        ("LZ78Y", lz78y_test)):
        for view, data, length, alph_size in views:
            jobs.append(((short, view), func, (data, length, alph_size, verbose, view)))

    estimates = ParallelJobs(jobs, auto_workers() if num_workers is None else num_workers)

    def take(key):
        """Wait for one estimate, echoing the progress lines it printed."""
        value, text = estimates.get(key)
        if text:
            sys.stdout.write(text)
        return value

    # ===================== Case 1: Most Common Value =====================
    tc_mcv = NonIidTestCase()
    if run_bitstring:
        h_mcv_bit = most_common_value(bit_data, bit_len, 2, verbose, "Bitstring")
        tc_mcv.h_bitstring = h_mcv_bit
        h_bitstring = min(h_bitstring, h_mcv_bit)
        print(f"H_bitstring (MCV): {h_mcv_bit}")
    h_mcv = most_common_value(dp.symbols, dp.len, dp.alph_size, verbose, "Literal", tc_mcv)
    tc_mcv.h_original = h_mcv
    h_original = min(h_original, h_mcv)
    tc_mcv.test_case_number = "Most Common Value"
    test_cases.append(tc_mcv)
    print(f"H_original (MCV): {h_mcv}")

    # ========== Cases 2-4: Collision / Markov / Compression (6.3.2-6.3.4) ==========
    # Tagged "for bit strings only": the reference applies them to the bit
    # expansion for multi-bit symbols, and to the symbols themselves only when
    # the data already is binary.
    for short in ("Collision", "Markov", "Compression"):
        tc = NonIidTestCase()
        tc.test_case_number = f"{short} Test (for bit strings only)"
        if run_bitstring:
            h = take((short, "Bitstring"))
            if h >= 0:
                tc.h_bitstring = h
                h_bitstring = min(h_bitstring, h)
                print(f"H_bitstring ({short}): {h}")
        if binary:
            h = take((short, "Literal"))
            if h >= 0:
                tc.h_original = h
                h_original = min(h_original, h)
                print(f"H_original ({short}): {h}")
        test_cases.append(tc)

    # ===================== Cases 5-6: t-Tuple and LRS =====================
    # One SAalgs() call yields both estimates, so the pair is evaluated once
    # per data view and the LRS half is reported by its own section.
    tc_ttuple = NonIidTestCase()
    tc_lrs = NonIidTestCase()
    bin_t_tuple_res = bin_lrs_res = -1.0

    if run_bitstring:
        bin_t_tuple_res, bin_lrs_res = take(("tTupleLRS", "Bitstring"))
        if bin_t_tuple_res >= 0.0:
            tc_ttuple.bin_t_tuple_res = bin_t_tuple_res
            h_bitstring = min(h_bitstring, bin_t_tuple_res)
            print(f"H_bitstring (t-Tuple): {bin_t_tuple_res}")
        if bin_lrs_res >= 0.0:
            tc_lrs.bin_lrs_res = bin_lrs_res
            h_bitstring = min(h_bitstring, bin_lrs_res)
            print(f"H_bitstring (LRS): {bin_lrs_res}")

    t_tuple_res, lrs_res = take(("tTupleLRS", "Literal"))
    if t_tuple_res >= 0.0:
        tc_ttuple.t_tuple_res = t_tuple_res
        h_original = min(h_original, t_tuple_res)
        print(f"H_original (t-Tuple): {t_tuple_res}")
    if lrs_res >= 0.0:
        tc_lrs.lrs_res = lrs_res
        h_original = min(h_original, lrs_res)
        print(f"H_original (LRS): {lrs_res}")

    tc_ttuple.test_case_number = "T-Tuple Test"
    test_cases.append(tc_ttuple)
    tc_lrs.test_case_number = "LRS Test"
    test_cases.append(tc_lrs)

    # ============ Cases 7-10: prediction estimates (MultiMCW/Lag/MultiMMC/LZ78Y) ============
    for short, name in (("MultiMCW", "Multi Most Common in Window Test"),
                        ("Lag", "Lag Prediction Test"),
                        ("MultiMMC", "Multi Markov Model with Counting Test (MultiMMC)"),
                        ("LZ78Y", "LZ78Y Test")):
        tc = NonIidTestCase()
        tc.test_case_number = name
        if run_bitstring:
            h = take((short, "Bitstring"))
            if h >= 0:
                tc.h_bitstring = h
                h_bitstring = min(h_bitstring, h)
                print(f"H_bitstring ({short}): {h}")
        h = take((short, "Literal"))
        if h >= 0:
            tc.h_original = h
            h_original = min(h_original, h)
            print(f"H_original ({short}): {h}")
        test_cases.append(tc)

    # Nothing below waits on an estimate, so the workers can go now.
    estimates.close()

    # ===================== Case 11: Overall =====================
    tc_overall = NonIidTestCase()
    tc_overall.test_case_number = "Overall"
    tc_overall.data_word_size = float(dp.word_size)
    h_assessed = float(dp.word_size)

    if run_bitstring:
        tc_overall.h_bitstring = h_bitstring
        h_assessed = min(h_assessed, h_bitstring * dp.word_size)

    tc_overall.h_original = h_original
    h_assessed = min(h_assessed, h_original)
    tc_overall.h_assessed = h_assessed
    test_cases.append(tc_overall)

    print(f"H_original (final): {h_original}")
    print(f"H_bitstring (final): {h_bitstring}")
    print(f"H_assessed: {h_assessed}")

    run.test_cases = test_cases
    free_data(dp)
    return run
