"""NIST SP 800-90B Entropy Assessment - Data Types"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

@dataclass
class DataT:
    """Corresponds to C++ data_t struct."""
    word_size: int = 0
    alph_size: int = 0
    maxsymbol: int = 0
    rawsymbols: Optional[np.ndarray] = None
    symbols: Optional[np.ndarray] = None
    bsymbols: Optional[np.ndarray] = None
    len: int = 0
    blen: int = 0


@dataclass
class TestCaseBase:
    """Base class for test case results."""
    h_original: float = -1.0
    h_bitstring: float = -1.0
    h_assessed: float = -1.0
    mcv_estimate_mode: float = -1.0
    mcv_estimate_p_hat: float = -1.0
    mcv_estimate_p_u: float = -1.0
    literal_mcv_estimate: bool = False
    ret_min_entropy: float = -1.0
    data_word_size: float = -1.0
    test_case_number: str = ""

    def to_dict(self) -> dict:
        d = {
            "testCaseDesc": self.test_case_number,
        }
        if self.ret_min_entropy != -1:
            d["retMinEntropy"] = self.ret_min_entropy
        if self.data_word_size != -1:
            d["dataWordSize"] = self.data_word_size
        if self.h_original != -1:
            d["hOriginal"] = self.h_original
        if self.h_bitstring != -1:
            d["hBitstring"] = self.h_bitstring
        if self.h_assessed != -1:
            d["hAssessed"] = self.h_assessed
        if self.mcv_estimate_mode != -1:
            d["mcvEstimateMode"] = self.mcv_estimate_mode
        if self.mcv_estimate_p_hat != -1:
            d["mcvEstimatePHat"] = self.mcv_estimate_p_hat
        if self.mcv_estimate_p_u != -1:
            d["mcvEstimatePU"] = self.mcv_estimate_p_u
        return d


@dataclass
class IidTestCase(TestCaseBase):
    """IID test case results."""
    mean: float = 0.0
    median: float = 0.0
    binary: bool = False
    passed_chi_square_tests: bool = False
    passed_longest_repeated_substring_test: bool = False
    passed_iid_permutation_tests: bool = False
    h_r: float = -1.0
    h_c: float = -1.0
    h_i: float = -1.0
    test_results: list[PermutationTestResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "mean": self.mean,
            "median": self.median,
            "binary": self.binary,
            "passedChiSquareTests": self.passed_chi_square_tests,
            "passedLongestRepeatedSubstringTest": self.passed_longest_repeated_substring_test,
            "passedIidPermutationTests": self.passed_iid_permutation_tests,
        })
        if self.h_r != -1:
            d["hRow"] = self.h_r
        if self.h_c != -1:
            d["hColumn"] = self.h_c
        if self.h_i != -1:
            d["hInitial"] = self.h_i
        if self.test_results:
            d["permutationTestResults"] = [r.to_dict() for r in self.test_results]
        return d


@dataclass
class NonIidTestCase(TestCaseBase):
    """Non-IID test case results."""
    bin_t_tuple_res: float = -1.0
    t_tuple_res: float = -1.0
    bin_lrs_res: float = -1.0
    lrs_res: float = -1.0
    h_r: float = -1.0
    h_c: float = -1.0
    h_i: float = -1.0
    n_in: float = -1.0
    n_out: float = -1.0
    nw: float = -1.0
    h_in: float = -1.0
    h_out: float = -1.0
    h_p: float = -1.0

    def to_dict(self) -> dict:
        d = super().to_dict()
        if self.bin_t_tuple_res != -1:
            d["binTTupleRes"] = self.bin_t_tuple_res
        if self.t_tuple_res != -1:
            d["tTupleRes"] = self.t_tuple_res
        if self.bin_lrs_res != -1:
            d["binLrsRes"] = self.bin_lrs_res
        if self.lrs_res != -1:
            d["lrsRes"] = self.lrs_res
        if self.h_r != -1:
            d["hRow"] = self.h_r
        if self.h_c != -1:
            d["hColumn"] = self.h_c
        if self.h_i != -1:
            d["hInitial"] = self.h_i
        if self.n_in != -1:
            d["nIn"] = self.n_in
        if self.n_out != -1:
            d["nOut"] = self.n_out
        if self.nw != -1:
            d["nw"] = self.nw
        if self.h_in != -1:
            d["hIn"] = self.h_in
        if self.h_out != -1:
            d["hOut"] = self.h_out
        if self.h_p != -1:
            d["hP"] = self.h_p
        return d


@dataclass
class PermutationTestResult:
    """Single permutation test iteration result."""
    iteration: int = -1
    excursion: float = -1.0
    num_directional_runs: float = -1.0
    len_directional_runs: float = -1.0
    num_increases_decreases: float = -1.0
    num_runs_median: float = -1.0
    len_runs_median: float = -1.0
    avg_collision: float = -1.0
    max_collision: float = -1.0
    periodicity1: float = -1.0
    periodicity2: float = -1.0
    periodicity8: float = -1.0
    periodicity16: float = -1.0
    periodicity32: float = -1.0
    covariance1: float = -1.0
    covariance2: float = -1.0
    covariance8: float = -1.0
    covariance16: float = -1.0
    covariance32: float = -1.0
    compression: float = -1.0

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "excursion": self.excursion,
            "numDirectionalRuns": self.num_directional_runs,
            "lenDirectionalRuns": self.len_directional_runs,
            "numIncreasesDecreases": self.num_increases_decreases,
            "numRunsMedian": self.num_runs_median,
            "lenRunsMedian": self.len_runs_median,
            "avgCollision": self.avg_collision,
            "maxCollision": self.max_collision,
            "periodicity1": self.periodicity1,
            "periodicity2": self.periodicity2,
            "periodicity8": self.periodicity8,
            "periodicity16": self.periodicity16,
            "periodicity32": self.periodicity32,
            "covariance1": self.covariance1,
            "covariance2": self.covariance2,
            "covariance8": self.covariance8,
            "covariance16": self.covariance16,
            "covariance32": self.covariance32,
            "compression": self.compression,
        }


@dataclass
class TestRunBase:
    """Base class for test run output."""
    timestamp: str = ""
    sha256: str = ""
    filename: str = ""
    error_level: int = 0
    error_msg: str = ""
    type: str = ""
    commandline: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "sha256": self.sha256,
            "filename": self.filename,
            "errorLevel": self.error_level,
            "errorMsg": self.error_msg,
            "type": self.type,
            "commandline": self.commandline,
        }


@dataclass
class IidTestRun(TestRunBase):
    """IID test run output."""
    iid: bool = True
    test_cases: list[IidTestCase] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["iid"] = True
        d["testCases"] = [tc.to_dict() for tc in self.test_cases]
        return d


@dataclass
class NonIidTestRun(TestRunBase):
    """Non-IID test run output."""
    iid: bool = False
    test_cases: list[NonIidTestCase] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["iid"] = False
        d["testCases"] = [tc.to_dict() for tc in self.test_cases]
        return d


@dataclass
class LagBuffer:
    """Ring buffer for Lag Prediction Test."""
    start: int = 0
    end: int = 0
    buf: list[int] = field(default_factory=lambda: [0] * 128)


class PostfixDictionary:
    """Used by LZ78Y and MultiMMC for (prefix -> postfix count) mapping."""

    def __init__(self):
        self._postfixes: dict[int, int] = {}
        self._cur_best: int = 0
        self._cur_prediction: int = 0

    def predict(self) -> tuple[int, int]:
        """Returns (count, prediction)."""
        assert self._cur_best > 0
        return self._cur_best, self._cur_prediction

    def increment_postfix(self, postfix: int, make_new: bool) -> bool:
        """Increments postfix count. Returns True if new entry was created."""
        if postfix in self._postfixes:
            self._postfixes[postfix] += 1
            cur_count = self._postfixes[postfix]
        elif make_new:
            self._postfixes[postfix] = 1
            cur_count = 1
        else:
            return False

        if (cur_count > self._cur_best) or \
           ((cur_count == self._cur_best) and (postfix > self._cur_prediction)):
            self._cur_prediction = postfix
            self._cur_best = cur_count

        return postfix not in self._postfixes or self._postfixes[postfix] == 1
