"""NIST SP 800-90B Entropy Assessment - Permutation Tests (19 tests)

The statistic definitions follow ``cpp/iid/permutation_tests.h`` exactly; the
implementations below are vectorized with numpy. Every helper returns the same
value the scalar loops did, so the pass/fail decision is unchanged - only the
permutation stream differs: the default fast path draws a uniformly random
permutation (as the C++ Fisher-Yates shuffle does, which is itself seeded from
system entropy), while ``rng="xoshiro"`` selects the reference shuffle.

Running the rounds in separate processes is what makes a full 10000-round pass
tractable; see :func:`permutation_tests` for how the counting stays exactly what
a serial run over the same stream would produce.
"""

from __future__ import annotations

import bz2
import os
import time
from collections import OrderedDict
from concurrent.futures import Future, ProcessPoolExecutor
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ._config import PERMS
from ._parallel import auto_workers, open_pool
from ._rng import Xoshiro256StarStar, random_permutation
from ._types import DataT, IidTestCase, PermutationTestResult

NUM_TESTS = 19
TEST_NAMES = [
    "excursion", "numDirectionalRuns", "lenDirectionalRuns",
    "numIncreasesDecreases", "numRunsMedian", "lenRunsMedian",
    "avgCollision", "maxCollision", "periodicity(1)", "periodicity(2)",
    "periodicity(8)", "periodicity(16)", "periodicity(32)",
    "covariance(1)", "covariance(2)", "covariance(8)",
    "covariance(16)", "covariance(32)", "compression",
]

# PermutationTestResult attribute for each statistic index (see TEST_NAMES).
TEST_RESULT_FIELDS = [
    "excursion", "num_directional_runs", "len_directional_runs",
    "num_increases_decreases", "num_runs_median", "len_runs_median",
    "avg_collision", "max_collision", "periodicity1", "periodicity2",
    "periodicity8", "periodicity16", "periodicity32",
    "covariance1", "covariance2", "covariance8",
    "covariance16", "covariance32", "compression",
]

# Lag parameters shared by the periodicity (5.1.9) and covariance (5.1.10) tests.
LAGS = (1, 2, 8, 16, 32)

# ``"%u"`` rendering of every possible byte value, used by the compression test.
_DECIMAL = [str(i).encode('ascii') for i in range(256)]

# Same renderings laid out for vectorized assembly: fixed 3-column digit matrix
# (a byte value needs at most 3 decimal digits) plus its real width.
_DIGIT_COLS = np.zeros((256, 3), dtype=np.uint8)
_DIGIT_WIDTH = np.zeros(256, dtype=np.int64)
for _v in range(256):
    _s = str(_v).encode('ascii')
    _DIGIT_COLS[_v, :len(_s)] = np.frombuffer(_s, dtype=np.uint8)
    _DIGIT_WIDTH[_v] = len(_s)
del _v, _s

# Sample and constants, cached per worker process by :func:`_init_worker`.
_WORKER: dict = {}

# Rounds are handed to a worker in batches that add up to this many seconds: one
# round is worth the trip while the statistics are expensive, dozens once most of
# them have settled and a round costs milliseconds. Grouping further than this was
# measured to cost more than it saves - a batch is only counted once it has fully
# landed, so long batches make the workers wait on each other.
_TASK_BUDGET = 0.10
_MAX_BATCH = 64


def _batch_size(round_cost: float) -> int:
    """How many rounds of this cost fit into :data:`_TASK_BUDGET`."""
    if round_cost <= 0.0:
        return _MAX_BATCH
    return max(1, min(int(_TASK_BUDGET / round_cost), _MAX_BATCH))


def conversion1(data: np.ndarray, sample_size: int) -> np.ndarray:
    """Binary: partition into 8-bit blocks, count 1s in each block."""
    n_full = (sample_size // 8) * 8
    ret = data[:n_full].reshape(-1, 8).sum(axis=1).astype(np.uint8)
    if sample_size > n_full:
        # Trailing partial block contributes only the bits that are present.
        ret = np.append(ret, np.uint8(int(data[n_full:sample_size].sum())))
    return ret


def conversion2(data: np.ndarray, sample_size: int) -> np.ndarray:
    """Binary: partition into 8-bit blocks, interpret each block as a byte."""
    n_full = (sample_size // 8) * 8
    ret = np.packbits(data[:n_full], bitorder='big')
    if sample_size > n_full:
        # packbits() zero-pads the *low* end of the last byte, which is exactly
        # how the reference weights a partial block (bit i -> 7 - i).
        ret = np.concatenate([ret, np.packbits(data[n_full:sample_size], bitorder='big')[:1]])
    return ret


def excursion(data: np.ndarray, rawmean: float, sample_size: int) -> float:
    """5.1.1 Excursion Test: max |running sum - (i+1) * rawmean|."""
    if sample_size <= 0:
        return 0.0
    # float64 accumulation order matches the reference loop, so results are equal.
    running_sum = np.cumsum(data[:sample_size], dtype=np.float64)
    running_sum -= np.arange(1, sample_size + 1, dtype=np.float64) * rawmean
    running_sum = np.abs(running_sum, out=running_sum)
    return float(running_sum.max())


def alt_sequence1(data: np.ndarray, sample_size: int) -> np.ndarray:
    """Returns array of +1/-1 based on consecutive comparison."""
    a = data[:sample_size]
    return (a[:-1] <= a[1:]).astype(np.int8) * 2 - 1


def alt_sequence2(data: np.ndarray, median: float, sample_size: int) -> np.ndarray:
    """Returns array of +1/-1 based on median comparison."""
    return (data[:sample_size] >= median).astype(np.int8) * 2 - 1


def num_directional_runs(alt_seq: np.ndarray) -> int:
    """5.1.2 Number of Directional Runs."""
    if alt_seq.size == 0:
        return 0
    return int(np.count_nonzero(alt_seq[1:] != alt_seq[:-1])) + 1


def len_directional_runs(alt_seq: np.ndarray) -> int:
    """5.1.3 Length of Directional Runs."""
    if alt_seq.size == 0:
        return 0
    bounds = np.flatnonzero(alt_seq[1:] != alt_seq[:-1]) + 1
    starts = np.empty(bounds.size + 1, dtype=np.int64)
    starts[0] = 0
    starts[1:] = bounds
    ends = np.append(bounds, alt_seq.size)
    return int(np.max(ends - starts))


def num_increases_decreases(alt_seq: np.ndarray) -> int:
    """5.1.4 Number of Increases and Decreases."""
    pos = int(np.count_nonzero(alt_seq == 1))
    return max(pos, int(alt_seq.size) - pos)


def find_collisions(data: np.ndarray, n: int, k: int) -> List[int]:
    """
    Find collision lengths (helper for 5.1.7 / 5.1.8).

    Sequential by nature, so it stays a loop - but a stamp counter replaces the
    per-window ``[False] * k`` re-initialisation and a plain list replaces numpy
    scalar indexing, which together dominate the cost of this statistic.
    """
    ret: List[int] = []
    stamp = [0] * k
    values = data.tolist() if isinstance(data, np.ndarray) else list(data)

    i = 0
    j = 0
    mark = 0
    while i + j < n:
        mark += 1
        while i + j < n:
            v = values[i + j]
            if stamp[v] == mark:
                # j is one less than the window size at the collision
                ret.append(j + 1)
                i += j
                j = 0
                break
            stamp[v] = mark
            j += 1
        i += 1
    return ret


def avg_collision(col_seq: List[int]) -> float:
    """5.1.7 Average Collision Test."""
    return sum(col_seq) / len(col_seq) if col_seq else 0.0


def max_collision(col_seq: List[int]) -> int:
    """5.1.8 Maximum Collision Test."""
    return max(col_seq) if col_seq else 0


def periodicity(data: np.ndarray, p: int, n: int) -> int:
    """5.1.9 Periodicity Test: matches at lag p within the first n symbols."""
    if n <= p:
        return 0
    return int(np.count_nonzero(data[:n - p] == data[p:n]))


def covariance(data: np.ndarray, p: int, n: int) -> int:
    """5.1.10 Covariance Test: sum of data[i] * data[i+p] within the first n."""
    if n <= p:
        return 0
    a = data if data.dtype == np.int64 else data.astype(np.int64)
    return int(np.dot(a[:n - p], a[p:n]))


def compression_message(data: np.ndarray, max_symbol: int) -> bytes:
    """
    Render the compression test input the way the reference does: every symbol
    as ``"%u"`` separated by single spaces, no trailing space.
    """
    a = data
    if a.size == 0:
        return b''

    if max_symbol < 10:
        # Single digit per symbol: lay out "d d d..." directly, no per-element work.
        msg = np.empty(2 * a.size - 1, dtype=np.uint8)
        msg[0::2] = a + 48
        msg[1::2] = 32
        return msg.tobytes()

    if a.dtype == np.uint8:
        # Byte alphabet: assemble "dd " rows and drop the unused digit columns and
        # the final space in one compaction, instead of formatting per element.
        widths = _DIGIT_WIDTH[a]
        cols = np.empty((a.size, 4), dtype=np.uint8)
        cols[:, :3] = _DIGIT_COLS[a]
        cols[:, 3] = 32
        keep = np.empty((a.size, 4), dtype=bool)
        keep[:, 0] = True
        keep[:, 1] = widths > 1
        keep[:, 2] = widths > 2
        keep[:, 3] = True
        keep[-1, 3] = False
        return cols[keep].tobytes()

    table = _DECIMAL
    return b" ".join([table[v] for v in a.tolist()])


def compression(data: np.ndarray, sample_size: int, max_symbol: int) -> int:
    """
    5.1.11 Compression Test.
    Uses bzip2 compression via bz2 module.

    The message is ``"%u "``-formatted per symbol with the trailing space removed
    (matching the reference), i.e. decimal symbols joined by single spaces.
    """
    msg = compression_message(data[:sample_size], max_symbol)
    if not msg:
        return 0
    return len(bz2.compress(msg, compresslevel=5))


def run_tests(
    dp: DataT,
    data: np.ndarray,
    rawdata: np.ndarray,
    rawmean: float,
    median: float,
    test_status: Sequence[bool]
) -> np.ndarray:
    """Run all 19 tests, returns array of 19 float64 values."""
    n = dp.len
    binary = dp.alph_size == 2
    stats = np.full(NUM_TESTS, -1.0, dtype=np.float64)

    # conversion1() feeds the directional, periodicity and covariance groups.
    # The reference recomputes it once per group; cache it for the whole round.
    cs1_cache: List[np.ndarray] = []

    def converted1() -> np.ndarray:
        if not cs1_cache:
            cs1_cache.append(conversion1(data, n))
        return cs1_cache[0]

    # 5.1.1 Excursion
    if test_status[0]:
        stats[0] = excursion(rawdata, rawmean, n)

    # 5.1.2 - 5.1.4 Directional runs
    if test_status[1] or test_status[2] or test_status[3]:
        if binary:
            cs1 = converted1()
            alt_seq = alt_sequence1(cs1, cs1.size)
        else:
            alt_seq = alt_sequence1(data, n)
        if test_status[1]:
            stats[1] = num_directional_runs(alt_seq)
        if test_status[2]:
            stats[2] = len_directional_runs(alt_seq)
        if test_status[3]:
            stats[3] = num_increases_decreases(alt_seq)

    # 5.1.5 - 5.1.6 Runs based on the median
    if test_status[4] or test_status[5]:
        alt_seq = alt_sequence2(data, 0.5 if binary else median, n)
        if test_status[4]:
            stats[4] = num_directional_runs(alt_seq)
        if test_status[5]:
            stats[5] = len_directional_runs(alt_seq)

    # 5.1.7 - 5.1.8 Collisions
    if test_status[6] or test_status[7]:
        if binary:
            cs2 = conversion2(data, n)
            col_seq = find_collisions(cs2, cs2.size, 256)
        else:
            col_seq = find_collisions(data, n, dp.alph_size)
        if test_status[6]:
            stats[6] = avg_collision(col_seq)
        if test_status[7]:
            stats[7] = max_collision(col_seq)

    # 5.1.9 Periodicity / 5.1.10 Covariance over lags 1, 2, 8, 16, 32.
    # Both need at least max(lag) symbols (the reference asserts n >= p).
    if n >= LAGS[-1]:
        if test_status[8] or test_status[9] or test_status[10] or test_status[11] or test_status[12]:
            per_data = converted1() if binary else data
            per_len = int(per_data.size)
            for idx, lag in zip(range(8, 13), LAGS):
                if test_status[idx]:
                    stats[idx] = periodicity(per_data, lag, per_len)

        if test_status[13] or test_status[14] or test_status[15] or test_status[16] or test_status[17]:
            cov_data = converted1() if binary else rawdata
            cov_len = int(cov_data.size)
            cov_int = cov_data.astype(np.int64, copy=False)
            for idx, lag in zip(range(13, 18), LAGS):
                if test_status[idx]:
                    stats[idx] = covariance(cov_int, lag, cov_len)

    # 5.1.11 Compression
    if test_status[18]:
        stats[18] = compression(rawdata, n, dp.maxsymbol)

    return stats


def _slim_dp(dp: DataT) -> DataT:
    """
    Copy of ``dp`` holding just the fields :func:`run_tests` reads.

    ``bsymbols`` is the bit expansion of the sample - eight times the size of
    the two arrays actually used - so shipping the whole ``data_t`` to every
    worker process would cost more than the rounds it buys.
    """
    return DataT(
        word_size=dp.word_size,
        alph_size=dp.alph_size,
        maxsymbol=dp.maxsymbol,
        rawsymbols=dp.rawsymbols,
        symbols=dp.symbols,
        len=dp.len,
        blen=dp.blen,
    )


def _round_statistics(
    dp: DataT,
    rawmean: float,
    median: float,
    seed: int,
    round_index: int,
    test_status: np.ndarray,
) -> np.ndarray:
    """
    Statistics of permutation round ``round_index``.

    The shuffle is drawn from ``SeedSequence([seed, round_index])``, so a round's
    permutation depends on its index alone and not on how the rounds happen to be
    spread over processes - running the same ``seed`` with any worker count replays
    exactly the same sequence of shuffles.
    """
    rng = np.random.default_rng(np.random.SeedSequence([seed, round_index]))
    perm = random_permutation(dp.len, rng)
    return run_tests(dp, dp.symbols[perm], dp.rawsymbols[perm], rawmean, median, test_status)


def _init_worker(dp: DataT, rawmean: float, median: float) -> None:
    """Pool initializer: keep the sample in the worker instead of every task."""
    _WORKER['dp'] = dp
    _WORKER['rawmean'] = rawmean
    _WORKER['median'] = median


def _round_batch(
    dp: DataT,
    rawmean: float,
    median: float,
    seed: int,
    start: int,
    count: int,
    test_status: np.ndarray,
) -> Tuple[np.ndarray, float]:
    """
    ``count`` consecutive rounds from ``start``, and how long they took.

    The duration is the driver's measure of what a round costs on this machine
    right now - contention included - which is what it sizes the next batch by.
    """
    batch = np.empty((count, NUM_TESTS), dtype=np.float64)
    t0 = time.perf_counter()
    for i in range(count):
        batch[i] = _round_statistics(dp, rawmean, median, seed, start + i, test_status)
    return batch, time.perf_counter() - t0


def _worker_batch(start: int, count: int, seed: int, test_status: np.ndarray) -> Tuple[np.ndarray, float]:
    """Worker-side half of the round loop; see :func:`_round_batch`."""
    return _round_batch(_WORKER['dp'], _WORKER['rawmean'], _WORKER['median'],
                        seed, start, count, test_status)


def _open_pool(dp: DataT, rawmean: float, median: float, workers: int) -> Optional[ProcessPoolExecutor]:
    """
    Start ``workers`` round-producing processes, or return None where spawning is
    not available.

    The probe-and-fallback plumbing is shared with the non-IID estimates through
    :func:`ea._parallel.open_pool`: the sample goes in once per worker, as pool
    initializer arguments, rather than with every batch.
    """
    return open_pool(
        workers,
        "counting permutation rounds",
        _init_worker,
        (_slim_dp(dp), rawmean, median),
    )


def _default_workers() -> int:
    """
    One round producer per physical core, none at all in a frozen build.

    These passes stream megabytes per round, so an SMT sibling adds little
    throughput while taking the CPU the counting process itself needs: over the
    reference samples, half the logical CPUs was as fast as all of them on the
    long runs (4.5x vs 5.0x) and faster on the short ones (2.9x vs 2.5x).
    ``num_workers`` overrides it.
    """
    return auto_workers()


def permutation_tests(
    dp: DataT,
    rawmean: float,
    median: float,
    verbose: int,
    tc: IidTestCase,
    rng: str = "numpy",
    seed: Optional[int] = None,
    num_workers: Optional[int] = None,
) -> bool:
    """
    Full permutation test over up to PERMS rounds.

    A statistic stops being counted once both of its tails have settled
    (``C[i][0] + C[i][1] > 5`` and ``C[i][1] + C[i][2] > 5``). When all 19 have
    settled there is nothing left to count, so the loop stops - the reference
    keeps iterating all PERMS rounds but skips the work behind its
    ``passed_count < 19`` guard, which is equivalent in outcome.

    A round only reads the sample and its own permutation, so the rounds are
    computed ahead of the counting loop - by ``num_workers`` processes when the
    numpy shuffle is in use, one at a time otherwise. Counting still happens
    strictly in round order, which keeps ``C`` identical to a serial run over the
    same permutation stream; the only difference is that a batch submitted before
    its neighbours were settled may compute statistics that are no longer
    counted. ``rng="xoshiro"`` stays serial: its shuffle feeds its own state into
    the next round, so round ``i`` cannot be produced before round ``i - 1``.

    rng: ``"numpy"`` (default) draws each permutation with the vectorized
         generator; ``"xoshiro"`` uses the bit-exact reference Fisher-Yates.
    seed: optional seed for reproducible permutations (ignored by ``"xoshiro"``,
          which always seeds from system entropy, as the reference ``seed()`` does).
    num_workers: processes the round loop may spread over; ``None`` uses one per
         physical core, ``1`` disables multiprocessing entirely. Capped at four
         per logical CPU, past which throughput only falls.
    """
    C = np.zeros((NUM_TESTS, 3), dtype=np.int64)
    test_status = np.ones(NUM_TESTS, dtype=bool)

    # Timed, because the unpermuted run computes every statistic just as a first
    # round would: it is the estimate the very first batch is sized from.
    t0 = time.perf_counter()
    t = run_tests(dp, dp.symbols, dp.rawsymbols, rawmean, median, test_status)
    round_cost = time.perf_counter() - t0

    if verbose == 2:
        print("Initial test results")
        for i in range(NUM_TESTS):
            print(f"  {TEST_NAMES[i]}: {t[i]}")
    elif verbose >= 3:
        for i in range(NUM_TESTS):
            print(f"Permutation testing: Unpermuted result {TEST_NAMES[i]} = {t[i]:.17g}")

    data = dp.symbols
    rawdata = dp.rawsymbols
    ref_rng = Xoshiro256StarStar() if rng == "xoshiro" else None
    if num_workers is None:
        num_workers = _default_workers()
    workers = 1 if ref_rng is not None else num_workers
    # No use producing more rounds than there will be counted, and a stray -j
    # should not spawn thousands of processes on a box that cannot run them.
    workers = max(1, min(workers, PERMS, 4 * (os.cpu_count() or 1)))
    # One 64-bit draw is enough to start: every round re-derives its own stream,
    # so the per-round streams are as independent as the rounds are many.
    seed_val = int(np.random.SeedSequence(seed).generate_state(1, dtype=np.uint64)[0])

    pool: Optional[ProcessPoolExecutor] = None
    if workers > 1:
        pool = _open_pool(dp, rawmean, median, workers)
        if pool is None:
            workers = 1
    window = workers

    active = np.arange(NUM_TESTS)
    # First round of each batch in flight -> (its handle, how many rounds it covers)
    pending: "OrderedDict[int, Tuple[Future, int]]" = OrderedDict()
    submitted = 0
    rounds = 0

    def submit_batch(start: int, count: int) -> 'Future':
        if pool is not None:
            return pool.submit(_worker_batch, start, count, seed_val, test_status)
        finished: 'Future' = Future()
        if ref_rng is not None:
            batch = np.empty((1, NUM_TESTS), dtype=np.float64)
            begin = time.perf_counter()
            buf = data.copy()
            rawbuf = rawdata.copy()
            ref_rng.fy_shuffle(buf, rawbuf)
            batch[0] = run_tests(dp, buf, rawbuf, rawmean, median, test_status)
            finished.set_result((batch, time.perf_counter() - begin))
        else:
            finished.set_result(
                _round_batch(dp, rawmean, median, seed_val, start, count, test_status))
        return finished

    try:
        while pending or submitted < PERMS:
            # Stay ``window`` batches ahead of the counting so that no worker sits
            # idle while the main process works through the batch in front of them.
            while len(pending) < window and submitted < PERMS:
                # Only a pool is worth batching for; in this process the rounds run
                # one at a time, exactly as they always did.
                count = (_batch_size(round_cost) if pool is not None else 1)
                count = min(count, PERMS - submitted)
                pending[submitted] = (submit_batch(submitted, count), count)
                submitted += count

            _, (future, count) = pending.popitem(last=False)
            batch, elapsed = future.result()
            # Ease towards the newest measurement: it already includes whatever
            # the other workers are costing this one right now.
            round_cost += (elapsed / count - round_cost) / 4.0
            all_settled = False
            for tp in batch:
                rounds += 1
                current = tp[active]
                baseline = t[active]
                bucket = np.where(current > baseline, 0, np.where(current == baseline, 1, 2))
                C[active, bucket] += 1
                settled = (C[active, 0] + C[active, 1] > 5) & (C[active, 1] + C[active, 2] > 5)
                if settled.all():
                    all_settled = True
                    break
                if settled.any():
                    test_status[active[settled]] = False
                    active = active[~settled]
            if all_settled:
                break
    finally:
        if pool is not None:
            # Rounds still in flight are moot once every statistic has settled.
            pool.shutdown(wait=False, cancel_futures=True)

    failed = (C[:, 0] + C[:, 1] <= 5) | (C[:, 1] + C[:, 2] <= 5)

    if verbose >= 3:
        print(f"Permutation testing: {rounds} of {PERMS} rounds counted on {workers} process(es)")

    if verbose > 1:
        print("\n                statistic  C[i][0]  C[i][1]  C[i][2]")
        print("----------------------------------------------------")
        for i in range(NUM_TESTS):
            marker = "*" if failed[i] else " "
            print(f"{TEST_NAMES[i]:>24}{marker}{C[i][0]:>8}{C[i][1]:>8}{C[i][2]:>8}")
        print("(* denotes failed test)")

    tr0 = PermutationTestResult(iteration=0)
    tr1 = PermutationTestResult(iteration=1)
    tr2 = PermutationTestResult(iteration=2)

    for idx, field in enumerate(TEST_RESULT_FIELDS):
        setattr(tr0, field, float(C[idx][0]))
        setattr(tr1, field, float(C[idx][1]))
        setattr(tr2, field, float(C[idx][2]))

    tc.test_results = [tr0, tr1, tr2]

    return not bool(failed.any())
