"""NIST SP 800-90B Entropy Assessment - PRNG (xoshiro256**)"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

MASK64 = (1 << 64) - 1
JUMP_CONSTANTS = [0x180ec6d33cfd0aba, 0xd5a61266f0c9392c, 0xa9582618e03fc9aa, 0x39abdc4529b1661c]


def _rotl64(x: int, k: int) -> int:
    """64-bit rotate left."""
    return ((x << k) | (x >> (64 - k))) & MASK64


class Xoshiro256StarStar:
    """
    xoshiro256** 1.0 by Blackman & Vigna.
    Matches C++ implementation in utils.h exactly.
    """

    def __init__(self, seed: Optional[np.ndarray] = None):
        if seed is None:
            raw = np.frombuffer(os.urandom(32), dtype=np.uint64)
        else:
            raw = np.asarray(seed, dtype=np.uint64)
        # State lives in plain Python ints: next() is called millions of times per
        # run and per-element numpy uint64 access costs several times more.
        self._s = [int(v) & MASK64 for v in raw]

    @property
    def state(self) -> np.ndarray:
        return np.array(self._s, dtype=np.uint64)

    def next(self) -> int:
        """Returns a 64-bit random number, updates state."""
        s0, s1, s2, s3 = self._s
        # `* 5` must wrap to 64 bits before the rotate, as it does in C++.
        result = _rotl64((s1 * 5) & MASK64, 7) * 9 & MASK64
        t = (s1 << 17) & MASK64

        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = _rotl64(s3, 45)

        self._s = [s0, s1, s2, s3]

        return int(result)

    def jump(self, count: int = 1) -> None:
        """
        Equivalent to count * 2^128 calls to next().
        Used to generate non-overlapping subsequences for parallel computations.

        Matches ``xoshiro_jump()``: the accumulators span the whole scan and the
        state is replaced only once, at the end.
        """
        s0 = 0
        s1 = 0
        s2 = 0
        s3 = 0

        for _ in range(count):
            for j in range(4):
                for b in range(64):
                    if JUMP_CONSTANTS[j] & (1 << b):
                        s0 ^= self._s[0]
                        s1 ^= self._s[1]
                        s2 ^= self._s[2]
                        s3 ^= self._s[3]
                    self.next()

        self._s = [s0, s1, s2, s3]

    def random_range64(self, s: int) -> int:
        """
        Lemire algorithm: returns integer in [0, s] uniformly, no modular bias.
        Modified from Lemire's [0,s) to [0,s].
        """
        x = self.next()

        if s == MASK64:
            return x

        s_plus_1 = s + 1  # We want [0, s], not [0, s)
        m = x * s_plus_1
        l = m & MASK64  # m mod 2^64

        if l < s_plus_1:
            t = ((-s_plus_1) & MASK64) % s_plus_1  # (2^64 - s) mod s
            while l < t:
                x = self.next()
                m = x * s_plus_1
                l = m & MASK64

        return (m >> 64) & MASK64

    def random_unit(self) -> float:
        """Returns [0, 1) uniformly distributed float64."""
        return (self.next() >> 11) * 1.1102230246251565e-16

    def fy_shuffle(self, data: np.ndarray, rawdata: np.ndarray) -> None:
        """
        Fisher-Yates in-place shuffle: permutes data and rawdata identically.

        Bit-identical to the C++ reference (same random stream, same swap order).
        The swaps run on bytearray views because per-element numpy scalar access
        costs roughly 5x more, and the sequence itself is unchanged.
        """
        n = len(data)
        d = bytearray(data)
        rd = bytearray(rawdata)
        rr = self.random_range64

        for i in range(n - 1, 0, -1):
            r = rr(i)
            d[i], d[r] = d[r], d[i]
            rd[i], rd[r] = rd[r], rd[i]

        data[:] = d
        rawdata[:] = rd


def fy_shuffle(data: np.ndarray, rawdata: np.ndarray, rng: Xoshiro256StarStar) -> None:
    """Standalone Fisher-Yates shuffle function."""
    rng.fy_shuffle(data, rawdata)


def random_range64(s: int, rng: Xoshiro256StarStar) -> int:
    """Standalone random range function."""
    return rng.random_range64(s)


def random_unit(rng: Xoshiro256StarStar) -> float:
    """Standalone random unit function."""
    return rng.random_unit()


def create_parallel_rngs(
    main_seed: np.ndarray, n_threads: int
) -> list[Xoshiro256StarStar]:
    """Create independent RNG instances for each thread via xoshiro_jump."""
    rngs = []
    for t in range(n_threads):
        rng = Xoshiro256StarStar(main_seed)
        rng.jump(t)
        rngs.append(rng)
    return rngs


def random_permutation(n: int, rng: np.random.Generator) -> np.ndarray:
    """
    Uniform random permutation of [0, n).

    Distribution-equivalent to :meth:`Xoshiro256StarStar.fy_shuffle` (both draw a
    uniformly random permutation of the sample) but vectorized, and therefore not
    reproducible against a C++ run. Pass an explicit ``seed`` to
    :func:`numpy.random.default_rng` when a reproducible run is wanted.
    """
    return rng.permutation(n)
