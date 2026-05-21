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
            self._state = np.frombuffer(os.urandom(32), dtype=np.uint64).copy()
        else:
            self._state = seed.copy()

    @property
    def state(self) -> np.ndarray:
        return self._state

    def next(self) -> int:
        """Returns a 64-bit random number, updates state."""
        s = self._state
        result = _rotl64(int(s[1]) * 5, 7) * 9 & MASK64
        t = int(s[1]) << 17 & MASK64

        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = _rotl64(int(s[3]), 45)

        return int(result)

    def jump(self, count: int = 1) -> None:
        """
        Equivalent to count * 2^128 calls to next().
        Used to generate non-overlapping subsequences for parallel computations.
        """
        s0 = 0
        s1 = 0
        s2 = 0
        s3 = 0

        for _ in range(count):
            for j in range(4):
                for b in range(64):
                    if JUMP_CONSTANTS[j] & (1 << b):
                        s0 ^= int(self._state[0])
                        s1 ^= int(self._state[1])
                        s2 ^= int(self._state[2])
                        s3 ^= int(self._state[3])
                    self.next()

            self._state[0] = s0 & MASK64
            self._state[1] = s1 & MASK64
            self._state[2] = s2 & MASK64
            self._state[3] = s3 & MASK64

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
        """Fisher-Yates in-place shuffle: permutes data and rawdata identically."""
        n = len(data)
        for i in range(n - 1, 0, -1):
            r = self.random_range64(i)
            data[i], data[r] = data[r], data[i]
            rawdata[i], rawdata[r] = rawdata[r], rawdata[i]


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
