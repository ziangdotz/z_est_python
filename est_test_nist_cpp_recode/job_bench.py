"""
【模块名称】: job_bench.py
【模块功能】: 按 non_iid_pipeline 的调度顺序逐个计时，打印每个估计器在两个视图上的耗时与最长 job。
【为什么需要它】:
    估计器并行之后墙钟 ≈ 最长 job + 父进程开销，所以「还能不能再快」只看这张表：
    `refdata_diff.py` 管端到端正确性，`jit_crosscheck.py` 管纯 Python / numba 两条路等价，
    速度分布归这里。它在单进程里跑，代表一个 worker 内部的开销（kernel 编译只算在第一次调用上）。
【用法】:
    python job_bench.py ../8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
    # 或 make job_bench（仓库根目录，默认就是上面这份样本）
【读数】:
    每行一个 (估计器, 视图)；Collision / Markov / Compression 按参考实现「仅用于位串」，
    多比特样本上它们没有符号视图那一行。SUM 是单进程跑完全部估计器的量，MAX 才是并行后
    墙钟的下限。本机是笔记本，持续负载会降频（热态整体约 ×1.3），所以只有同一次运行内的
    比值可信；比较 JIT 开 / 关请用 EA_DISABLE_JIT=1 在同一轮里各跑一次。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "est_core_nist_cpp_recode"))

from ea import _jit  # noqa: E402
from ea._io import read_file  # noqa: E402
from ea._lrs import sa_algs  # noqa: E402
from ea._types import DataT, NonIidTestRun  # noqa: E402
from ea.collision import collision_test  # noqa: E402
from ea.compression import compression_test  # noqa: E402
from ea.lag_test import lag_test  # noqa: E402
from ea.lz78y import lz78y_test  # noqa: E402
from ea.markov import markov_test  # noqa: E402
from ea.multi_mcw import multi_mcw_test  # noqa: E402
from ea.multi_mmc import multi_mmc_test  # noqa: E402

#: 6.3.2-6.3.4 的签名是 (data, length, verbose, label)，其余多一个 alph_size
_BITSTRING_ONLY = (collision_test, markov_test, compression_test)

SCHEDULE = (
    ("Collision", collision_test),
    ("Markov", markov_test),
    ("Compression", compression_test),
    ("tTupleLRS", sa_algs),
    ("MultiMCW", multi_mcw_test),
    ("Lag", lag_test),
    ("MultiMMC", multi_mmc_test),
    ("LZ78Y", lz78y_test),
)


def main() -> int:
    if len(sys.argv) < 2:
        print(f"usage: {Path(sys.argv[0]).name} <binary data file>")
        return 2

    path = sys.argv[1]
    dp = DataT(word_size=0)
    if not read_file(path, dp, NonIidTestRun()):
        print(f"read_file failed: {path}")
        return 1

    # The same two views, named the way the pipeline labels them.
    views = []
    if dp.alph_size != 2:
        views.append(("Bitstring", dp.bsymbols, dp.blen, 2))
    views.append(("Literal", dp.symbols, dp.len, dp.alph_size))

    print(f"{path}  len={dp.len} blen={dp.blen} alph={dp.alph_size} "
          f"jit={'on' if _jit.numba_njit() is not None else 'off'}")

    total = 0.0
    slowest = ("", 0.0)
    for short, func in SCHEDULE:
        for view, data, length, alph in views:
            if view == "Literal" and func in _BITSTRING_ONLY:
                continue
            args = ((data, length, 0, view) if func in _BITSTRING_ONLY
                    else (data, length, alph, 0, view))
            t0 = time.perf_counter()
            func(*args)
            dt = time.perf_counter() - t0
            total += dt
            if dt > slowest[1]:
                slowest = (f"{short}/{view}", dt)
            print(f"  {short:12} {view:10} {dt:7.2f} s")

    print(f"  {'SUM':23} {total:7.2f} s")
    print(f"  {'MAX (critical path)':23} {slowest[1]:7.2f} s  {slowest[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
