"""
【模块名称】: refdata_diff.py
【模块功能】: 用 C++ 自测基准 (selftest/refdata/*.res) 逐行校验 `ea_non_iid -vv` 的输出。
【设计要点】:
  1. 只比较两侧含 " Estimate:" 的行：头部提示、我们额外打印的 H_* 汇总行、尾部 JSON 都在范围之外。
  2. 每个行对做两级检查：先把「= 数值」里的数值遮成 '#' 比较"文本骨架"（字段名、段名、行数、
     顺序漂移会在这一级暴露，而标签里的下标如 P_{0,1} 不参与遮藏），再按位置提取数值做相对误差
     比较（默认容差 1e-9，见重写方案 §15.4）。
  3. 默认只跑 3 个 10000 样本的短文件（秒级）；--all 跑满 11 个样本（数十分钟）。
  4. 退出码：无硬差异为 0，否则为 1，可直接接进 CI 或 Makefile。
【容差怎么定】:
  默认 1e-9 是“严格筛查档”，能抓出字段写错与算法语义差异；`calc_p_local` 二分搜索在 C++
  （long double 参与运算）与 Python（double）之间不会收敛到同一点，实测 ringOsc-nist 的
  MultiMCW `P_local` 本身相差不到 1e-9（容差内），而 `-log2` 还按 1/|ln p|（p≈0.818 时约 5 倍）
  放大相对误差，派生的 `min entropy` 就成了 1.1e-9（超容差）。要按重写方案 §15.4 的
  「正常 1e-6」档验收预测器派生值，用 `--tol 1e-6`。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "est_core_nist_cpp_recode" / "cli" / "ea_non_iid.py"
BIN_DIR = REPO_ROOT / "8ckup" / "NIST_SP800-90B_EntropyAssessment" / "bin"
REF_DIR = BIN_DIR.parent / "cpp" / "selftest" / "refdata"

#: 10000 样本的短文件，秒级即可跑完，适合默认执行
QUICK_SAMPLES = ("rand1_short", "rand4_short", "rand8_short")
#: `generate-refdata` 覆盖的全部样本
ALL_SAMPLES = QUICK_SAMPLES + (
    "biased-random-bits", "biased-random-bytes", "data.pi", "normal",
    "ringOsc-nist", "truerand_1bit", "truerand_4bit", "truerand_8bit",
)

#: `… Estimate:` 行里的数值一律跟在 "= " 后面，所以只遮这一部分；字段名里的下标
#: （P_{0,1}、X-bar' 等）保持原样，写错字段名不会被当成数值差异吞掉
ASSIGNMENT = re.compile(r"= (-?[\d.]+(?:[eE][-+]?\d+)?)")


def estimate_lines(text: str) -> list[str]:
    """Keep the reference's per-estimate detail lines, in printed order."""
    return [line.rstrip() for line in text.splitlines() if " Estimate:" in line]


def skeleton(line: str) -> str:
    """Line with every reported value masked out, so wording drift shows up as a mismatch."""
    return ASSIGNMENT.sub("= #", line)


def numbers(line: str) -> list[float]:
    return [float(tok) for tok in ASSIGNMENT.findall(line)]


def compare(ours: list[str], ref: list[str], tol: float) -> tuple[int, int, list[str]]:
    """Return (exact, ulp, problems) for two aligned lists of estimate lines."""
    exact = ulp = 0
    problems: list[str] = []

    for i in range(max(len(ours), len(ref))):
        o = ours[i] if i < len(ours) else None
        r = ref[i] if i < len(ref) else None
        if o is None or r is None:
            problems.append(f"  [{i}] {'missing on our side' if o is None else 'extra line on our side'}: "
                            f"{r if o is None else o}")
            continue
        if o == r:
            exact += 1
            continue
        if skeleton(o) != skeleton(r):
            problems.append(f"  [{i}] wording drift\n       ours: {o}\n       ref : {r}")
            continue

        o_vals, r_vals = numbers(o), numbers(r)
        if len(o_vals) != len(r_vals) or any(
            abs(a - b) > tol * max(abs(a), abs(b), 1e-300)
            for a, b in zip(o_vals, r_vals)
        ):
            problems.append(f"  [{i}] value mismatch\n       ours: {o}\n       ref : {r}")
        else:
            ulp += 1

    return exact, ulp, problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按行比对 ea_non_iid -vv 输出与 C++ selftest/refdata 参考结果")
    parser.add_argument("samples", nargs="*", metavar="SAMPLE",
                        help=f"样本名（不含 .bin/.res 后缀），默认 {', '.join(QUICK_SAMPLES)}")
    parser.add_argument("--all", action="store_true", help="比对全部 11 个 refdata 样本")
    parser.add_argument("--tol", type=float, default=1e-9, metavar="REL",
                        help="数值相对误差容差 (默认: 1e-9；按 §15.4 的预测器档位用 1e-6)")
    parser.add_argument("-j", "--workers", type=int, default=None, metavar="N",
                        help="传给 ea_non_iid 的并行进程数 (默认: 每个物理核 1 个)")
    parser.add_argument("--show-ulp", action="store_true",
                        help="列出容差内的末位差异行（默认只报数量）")
    args = parser.parse_args()

    samples = ALL_SAMPLES if args.all else (args.samples or QUICK_SAMPLES)
    failures = 0

    for name in samples:
        data, ref_file = BIN_DIR / f"{name}.bin", REF_DIR / f"{name}.res"
        if not data.is_file() or not ref_file.is_file():
            print(f"=== {name}: SKIP (missing {data.name if not data.is_file() else ref_file.name})")
            failures += 1
            continue

        cmd = [sys.executable, str(CLI), str(data), "-vv"]
        if args.workers is not None:
            cmd += ["-j", str(args.workers)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        ours = estimate_lines(proc.stdout)
        ref = estimate_lines(ref_file.read_text(encoding="utf-8", errors="replace"))

        exact, ulp, problems = compare(ours, ref, args.tol)
        status = "OK" if not problems else f"{len(problems)} PROBLEM"
        print(f"=== {name}: {len(ours)}/{len(ref)} lines, exact={exact}, within-tol={ulp} -> {status}")
        for item in problems[:10]:
            print(item)
        if len(problems) > 10:
            print(f"  ... {len(problems) - 10} more")
        if args.show_ulp:
            for i, (o, r) in enumerate(zip(ours, ref)):
                if o != r:
                    print(f"  [{i}] ours: {o}\n       ref : {r}")
        failures += 1 if problems else 0

    print(f"\n{'PASS' if not failures else 'FAIL'}: "
          f"{len(samples) - failures}/{len(samples)} samples identical apart from tol={args.tol:g}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
