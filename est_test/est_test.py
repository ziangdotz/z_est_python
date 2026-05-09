"""
【模块名称】: est_test.py
【模块功能】: 统一的 NIST SP800-90B 熵评估测试调用接口（支持 Restart, IID, Non-IID）。
【设计要点】:
 1. 提供产品级的命令行接口（CLI），支持对单个数据文件灵活选择执行 Restart, IID 或 Non-IID 测试。
 2. 动态调整 Python 导包路径 (sys.path) 从而优雅地调用同级 `est_core` 目录下的核心算法模块，解耦业务逻辑与调用逻辑。
 3. 结构化捕获与输出测试结果（使用 JSON 格式格式化输出），具备异常隔离捕获机制，便于系统集成和二次开发日志分析。
"""
import os
import sys
import json

current_dir = os.path.dirname(os.path.abspath(__file__))
core_dir = os.path.abspath(os.path.join(current_dir, '..', 'est_core'))
if core_dir not in sys.path:
    sys.path.insert(0, core_dir)

try:
    from main_restart import main_restart
    from main_iid import main_iid
    from main_noniid import main_noniid
    from util import get_parser
except ImportError as e:
    print(f"导入核心模块失败: {e}")
    print(f"请确保核心目录存在且结构完整: {core_dir}")
    sys.exit(1)


def run_est_test():
    """
    主执行逻辑：根据用户命令行输入执行指定的测试
    """
    parser = get_parser(test=None)
    args = parser.parse_args()

    if not os.path.isfile(args.datafile):
        print(f"[错误] 数据文件未找到: {args.datafile}")
        sys.exit(1)

    if args.restart and args.H_I is None:
        print("[错误] 执行 Restart 测试必须使用 --h-i 参数指定初始熵估值 (H_I)")
        sys.exit(1)

    if not (args.iid or args.non_iid or args.restart):
        print("[警告] 没有指定任何测试项目。请使用 --iid, --non-iid 或 --restart 指定至少一项进行测试")
        sys.exit(1)

    results = {}

    print("="*60)
    print(f"🚀 开始测试分析目标文件: {args.datafile}")
    print(f"📊 符号位宽设置: {args.bits_per_symbol} bits")
    print("="*60)

    # ==========================
    # 1. 执行 Restart 测试
    # ==========================
    if args.restart:
        print("\n>>> [1/3] 执行 Restart 重启数据检验 ...")
        try:
            restart_res = main_restart(
                args.datafile, args.bits_per_symbol, args.H_I, args.verbose)
            results["Restart_Test"] = restart_res
        except Exception as e:
            results["Restart_Test"] = {"status": "error", "message": str(e)}
            print(f"[Restart 测试引发异常]: {e}")

    # ==========================
    # 2. 执行 IID 测试
    # ==========================
    if args.iid:
        print("\n>>> [2/3] 执行 IID 独立同分布测试 ...")
        try:
            iid_res = main_iid(
                args.datafile, args.bits_per_symbol, args.verbose)
            results["IID_Test"] = iid_res
        except Exception as e:
            results["IID_Test"] = {"status": "error", "message": str(e)}
            print(f"[IID 测试引发异常]: {e}")

    # ==========================
    # 3. 执行 Non-IID 测试
    # ==========================
    if args.non_iid:
        print("\n>>> [3/3] 执行 Non-IID 保守熵综合评估测试 ...")
        try:
            noniid_res = main_noniid(
                args.datafile, args.bits_per_symbol, args.use_bits, args.verbose)
            results["Non_IID_Test"] = noniid_res
        except Exception as e:
            results["Non_IID_Test"] = {"status": "error", "message": str(e)}
            print(f"[Non-IID 测试引发异常]: {e}")

    # ==========================
    # 结果汇总与输出
    # ==========================
    print("\n" + "="*60)
    print("✅ 测试结果汇总 (JSON格式):")
    print("="*60)
    print(json.dumps(results, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8')

    run_est_test()
