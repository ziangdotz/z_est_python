"""
【模块名称】: lrs_bench.py
【模块功能】: 对 `ea/_lrs.py` 的三个函数分别计时，并打印它们之间的**中间量指纹**。
【为什么需要它】:
    `refdata_diff.py` 只能看到 t-Tuple / LRS 两个最终熵值，而熵值是标量：后缀数组或 LCP
    数组里某个位置错了，只要不落在取胜的那几个前缀上，熵值可能照样对。本脚本把
    `build_suffix_array` 的首尾若干项和 `sa_to_lcp` 的 max/sum 一起打出来，改 `_lrs.py`
    时前后各跑一次，逐元素对得上才算等价。
【用法】:
    python lrs_bench.py <file.bin> [bits_per_symbol]      # 路径相对仓库根或直接给绝对路径
    python lrs_bench.py 8ckup/.../bin/truerand_4bit.bin
    指纹与 §14.3/§14.5 的耗时参考值对应 `truerand_4bit.bin`（位串 4M 符号 + 符号 1M 符号）。
【读数】:
    本机（i7-11800H）持续负载下会降频，同一份数据热态整体约 ×1.3；因此耗时只用于
    「同一次运行内比较函数之间」，跨运行请只看指纹与比值。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "est_core_nist_cpp_recode"))

import numpy as np  # noqa: E402

from ea._io import read_file  # noqa: E402
from ea._lrs import build_suffix_array, sa_algs, sa_to_lcp  # noqa: E402
from ea._types import DataT, NonIidTestRun  # noqa: E402


def bench(label: str, data: np.ndarray, n: int, alph_size: int) -> None:
    # A plain int64 array is what the pipeline hands the estimate; keep that shape.
    data = np.ascontiguousarray(data[:n], dtype=np.int64)

    t0 = time.perf_counter()
    sa = build_suffix_array(data, n)
    t1 = time.perf_counter()
    lcp = sa_to_lcp(data, n, sa)
    t2 = time.perf_counter()
    t_tuple, lrs = sa_algs(data, n, alph_size, 0, label)
    t3 = time.perf_counter()

    print(f"{label}: sa={t1 - t0:.2f}s lcp={t2 - t1:.2f}s algs={t3 - t2:.2f}s")
    # The empty suffix sorts first at index n, so sa[0] == n is part of the fingerprint.
    print(f"   sa[:8]={sa[:8].tolist()} sa[-8:]={sa[-8:].tolist()}")
    print(f"   lcp max={int(lcp.max())} sum={int(lcp.sum())}")
    # repr() rather than a formatted value: the point is bit-for-bit equality.
    print(f"   t_tuple={t_tuple!r} lrs={lrs!r}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    dp = DataT(word_size=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    if not read_file(sys.argv[1], dp, NonIidTestRun()):
        print("read_file failed", file=sys.stderr)
        return 1

    print(f"samples={dp.len} alph={dp.alph_size} blen={dp.blen}")
    # The same two views the non-IID pipeline estimates: the bit string (only when
    # the data is not already binary) and the symbols.
    if dp.alph_size != 2:
        bench("Bitstring", dp.bsymbols, dp.blen, 2)
    bench("Literal", dp.symbols, dp.len, dp.alph_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
