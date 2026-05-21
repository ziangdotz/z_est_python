"""
【模块名称】: est_test_nist_cpp_recode.py
【模块功能】: 统一的 NIST SP800-90B 熵评估测试调用接口（支持 Restart, IID, Non-IID）。
【设计要点】:
  1. 提供产品级的命令行接口（CLI），支持对单个数据文件灵活选择执行 Restart, IID 或 Non-IID 测试。
  2. 动态调整 Python 导包路径 (sys.path) 从而优雅地调用 `est_core_nist_cpp_recode` 目录下的核心算法模块。
  3. 结构化捕获与输出测试结果（使用 JSON 格式格式化输出），具备异常隔离捕获机制。
"""
import os
import sys
import json
import argparse

current_dir = os.path.dirname(os.path.abspath(__file__))
core_dir = os.path.abspath(os.path.join(
    current_dir, '..', 'est_core_nist_cpp_recode'))
if core_dir not in sys.path:
    sys.path.insert(0, core_dir)

try:
    from ea.restart import restart_test
    from ea.iid_pipeline import run_iid_test
    from ea.non_iid_pipeline import run_non_iid_test
except ImportError as e:
    print(f"导入核心模块失败: {e}")
    print(f"请确保核心目录存在且结构完整: {core_dir}")
    sys.exit(1)


def get_parser():
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="NIST SP 800-90B 熵评估测试 (C++ Recode Python 版)"
    )
    parser.add_argument("datafile", help="二进制数据文件路径")
    parser.add_argument("--bits", type=int, default=0,
                        help="每个符号的位数 (0 = 自动检测)")
    parser.add_argument("--restart", action="store_true", help="执行 Restart 测试")
    parser.add_argument("--iid", action="store_true", help="执行 IID 测试")
    parser.add_argument("--non-iid", action="store_true", help="执行 Non-IID 测试")
    parser.add_argument("--h-i", type=float, default=None,
                        help="Restart 测试所需的初始熵估值 H_I")
    parser.add_argument("-v", "--verbose", action="count", default=1,
                        help="增加输出详细程度 (-v, -vv)")
    return parser


def run_est_test():
    """主执行逻辑：根据用户命令行输入执行指定的测试"""
    parser = get_parser()
    args = parser.parse_args()

    if not os.path.isfile(args.datafile):
        print(f"[错误] 数据文件未找到: {args.datafile}")
        sys.exit(1)

    if args.restart and args.h_i is None:
        print("[错误] 执行 Restart 测试必须使用 --h-i 参数指定初始熵估值 (H_I)")
        sys.exit(1)

    if not (args.restart or args.iid or args.non_iid):
        print("[警告] 没有指定任何测试项目。请使用 --restart, --iid 或 --non-iid 指定至少一项进行测试")
        sys.exit(1)

    results = {}

    print("=" * 60)
    print(f"🚀 开始测试分析目标文件: {args.datafile}")
    print(f"📊 符号位宽设置: {args.bits} bits")
    print("=" * 60)

    # ==========================
    # 1. 执行 Restart 测试
    # ==========================
    if args.restart:
        print("\n>>> [1/3] 执行 Restart 重启数据检验 ...")
        try:
            h_min = restart_test(
                file_path=args.datafile,
                H_I=args.h_i,
                iid=False,
                verbose=args.verbose,
            )
            results["Restart_Test"] = {
                "status": "pass", "h_min": h_min, "H_I": args.h_i}
        except Exception as e:
            results["Restart_Test"] = {"status": "error", "message": str(e)}
            print(f"[Restart 测试引发异常]: {e}")

    # ==========================
    # 2. 执行 IID 测试
    # ==========================
    if args.iid:
        print("\n>>> [2/3] 执行 IID 独立同分布测试 ...")
        try:
            run = run_iid_test(
                file_path=args.datafile,
                bits_per_symbol=args.bits,
                initial=True,
                all_bits=True,
                verbose=args.verbose,
            )
            results["IID_Test"] = {"status": "pass", "data": run.to_dict()}
        except Exception as e:
            results["IID_Test"] = {"status": "error", "message": str(e)}
            print(f"[IID 测试引发异常]: {e}")

    # ==========================
    # 3. 执行 Non-IID 测试
    # ==========================
    if args.non_iid:
        print("\n>>> [3/3] 执行 Non-IID 保守熵综合评估测试 ...")
        try:
            run = run_non_iid_test(
                file_path=args.datafile,
                bits_per_symbol=args.bits,
                verbose=args.verbose,
            )
            results["Non_IID_Test"] = {"status": "pass", "data": run.to_dict()}
        except Exception as e:
            import traceback
            traceback.print_exc()
            results["Non_IID_Test"] = {"status": "error", "message": str(e)}
            print(f"[Non-IID 测试引发异常]: {e}")

    # ==========================
    # 结果汇总与输出
    # ==========================
    print("\n" + "=" * 60)
    print("✅ 测试结果汇总 (JSON格式):")
    print("=" * 60)
    print(json.dumps(results, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8')
    run_est_test()
