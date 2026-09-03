"""
【模块名称】: jit_crosscheck.py
【模块功能】: 对每个「纯 Python 循环 / numba kernel」双胞胎跑同一份数据，要求返回的计数逐位相同。
【为什么需要它】:
    `refdata_diff.py` 验的是端到端输出，而 JIT 只在样本数超过 `ea/_jit.JIT_MIN_SAMPLES`
    时才启用（默认 10 万），短样本的回归根本不会走到 kernel 上。更关键的是：一份
    预测器最终只输出 `correct_count` / `max_run` 两个整数，双胞胎里任何一侧写错
    （平局取谁、窗口边界、计数回写时机）都可能让熵值照样落在容差内。这里绕开
    `use_jit()` 的尺寸门槛，直接把两条路的原始计数拿出来比。
【用法】:
    python jit_crosscheck.py                    # 默认全部 refdata 样本，每视图截断 250k 符号
    python jit_crosscheck.py --cap 0            # 不截断（Python 一侧 ~9 µs/符号，大文件很慢）
    python jit_crosscheck.py --samples rand8_short truerand_4bit
【判定】:
    每个用例都要求 numba 真的编译出了 kernel（`Kernel.compiled` 非空）——静默退回
    Python 侧会让「两边相同」变成同义反复，所以这也是一项检查。退出码 0/1。
【加新 kernel 时】:
    往 CASES 里加一行：py 与 jit 两个 callable 都收 (uint8 符号数组, 长度, 字母表大小)，
    返回同样形状的计数元组；kernel 字段是那个 Kernel 对象，用来确认编译真的发生了。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable, List, NamedTuple, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "est_core_nist_cpp_recode"))

from ea._config import B_len, D_MMC, W  # noqa: E402
from ea._io import read_file  # noqa: E402
from ea._jit import Kernel, numba_njit  # noqa: E402
from ea._types import DataT, NonIidTestRun  # noqa: E402
from ea.lag_test import _lag_counts, _lag_kernel  # noqa: E402
from ea.lz78y import (  # noqa: E402
    _as_bytes as _lz78y_as_bytes, _binary_lz78y_counts, _binary_lz78y_kernel)
from ea.multi_mcw import (  # noqa: E402
    _W_ARRAY, _multi_mcw_counts, _multi_mcw_kernel)
from ea.multi_mmc import (  # noqa: E402
    _as_bytes, _binary_multi_mmc_counts, _binary_multi_mmc_kernel)

BIN_DIR = REPO_ROOT / "8ckup" / "NIST_SP800-90B_EntropyAssessment" / "bin"
ALL_SAMPLES = (
    "rand1_short", "rand4_short", "rand8_short",
    "biased-random-bits", "biased-random-bytes", "data.pi", "normal",
    "ringOsc-nist", "truerand_1bit", "truerand_4bit", "truerand_8bit",
)

#: One predictor that has a plain-Python loop and a numba kernel side by side.
class Case(NamedTuple):
    label: str
    bits_only: bool     #: only the binary view can run it
    min_n: int          #: below this the predictor's own precondition fails
    py: Callable        #: (uint8 symbols, length, alph_size) -> counts
    jit: Callable       #: same data, through the Kernel proxy
    kernel: Kernel      #: the proxy, so the run can see whether it compiled


CASES: List[Case] = [
    Case("MultiMMC(binary)", True, D_MMC + 2,
         lambda a, n, k: _binary_multi_mmc_counts(_as_bytes(a, n), n),
         lambda a, n, k: _binary_multi_mmc_kernel(a, n),
         _binary_multi_mmc_kernel),
    Case("LZ78Y(binary)", True, B_len + 2,
         lambda a, n, k: _binary_lz78y_counts(_lz78y_as_bytes(a, n), n),
         lambda a, n, k: _binary_lz78y_kernel(a, n),
         _binary_lz78y_kernel),
    Case("Lag", False, 2,
         lambda a, n, k: _lag_counts(a.astype(np.int64).tolist(), n, k),
         lambda a, n, k: _lag_kernel(a, n, k),
         _lag_kernel),
    Case("MultiMCW", False, W[-1] + 1,
         lambda a, n, k: _multi_mcw_counts(a.astype(np.int64).tolist(), n, k),
         lambda a, n, k: _multi_mcw_kernel(a, n, k, _W_ARRAY),
         _multi_mcw_kernel),
]


def _same(a: tuple, b: tuple) -> bool:
    """numba 交出 Python int、numpy 标量都可能，按整数逐项比。"""
    return len(a) == len(b) and all(int(x) == int(y) for x, y in zip(a, b))


def views_of(dp: DataT, cap: int) -> List[Tuple[str, np.ndarray, int, int]]:
    """The same two views the non-IID pipeline estimates."""
    out = []
    if dp.alph_size != 2:
        n = dp.blen if not cap else min(dp.blen, cap)
        out.append(("Bitstring", dp.bsymbols, n, 2))
    n = dp.len if not cap else min(dp.len, cap)
    out.append(("Literal", dp.symbols, n, dp.alph_size))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="对拍预测器的纯 Python 循环与 numba kernel")
    parser.add_argument("--samples", nargs="*", metavar="SAMPLE",
                        default=list(ALL_SAMPLES),
                        help=f"样本名（不含 .bin），默认全部 {len(ALL_SAMPLES)} 个")
    parser.add_argument("--cap", type=int, default=250_000, metavar="N",
                        help="每个视图最多取多少符号，0 = 不截断 (默认: 250000)")
    args = parser.parse_args()

    if numba_njit() is None:
        print("numba 不可用：JIT 侧无法验证（装好 numba 或去掉 EA_DISABLE_JIT 再来）")
        return 1

    failures = 0
    for name in args.samples:
        data_file = BIN_DIR / f"{name}.bin"
        if not data_file.is_file():
            print(f"=== {name}: SKIP (missing {data_file.name})")
            failures += 1
            continue

        dp = DataT(word_size=0)
        if not read_file(str(data_file), dp, NonIidTestRun()):
            print(f"=== {name}: SKIP (read_file failed)")
            failures += 1
            continue

        parts = [f"=== {name}"]
        for view, raw, n, alph in views_of(dp, args.cap):
            arr = np.ascontiguousarray(raw[:n], dtype=np.uint8)
            for case in CASES:
                if case.bits_only and alph != 2:
                    continue
                if n < case.min_n:
                    parts.append(f"{case.label}/{view}: SKIP (n={n})")
                    continue
                t0 = time.perf_counter()
                expected = case.py(arr, n, alph)
                t1 = time.perf_counter()
                got = case.jit(arr, n, alph)
                t2 = time.perf_counter()
                if case.kernel.compiled is None:
                    parts.append(f"{case.label}/{view}: NOT COMPILED")
                    failures += 1
                elif not _same(got, expected):
                    parts.append(f"{case.label}/{view}: MISMATCH {got} != {expected}")
                    failures += 1
                else:
                    ratio = (t1 - t0) / (t2 - t1) if t2 > t1 else float("inf")
                    parts.append(f"{case.label}/{view}: ok {expected} "
                                 f"({t1 - t0:.2f}s vs {t2 - t1:.3f}s, {ratio:.0f}x)")
        print("; ".join(parts), flush=True)

    print(f"\n{'PASS' if not failures else 'FAIL'}: {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
