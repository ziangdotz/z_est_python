"""
【模块名称】: main_restart.py
【模块功能】: NIST SP800-90B 重启测试（Restart Test）的评估入口。
【设计要点】:
 1. 旨在评估发生器每次重新启动后产生的前置输出数据是否具有足够的熵。
 2. 对于硬件和物理发生器而言，重启时的状态可能不是完全随机的，因此标准要求独立收集多次启动的数据。
 3. 检查按行（各次重启间的同一位置）与按列（单次重启内的连续序列）的数据分布。
【核心函数】:
 - run_restart_tests: 读取由多组短序列构成的矩阵形式的数据集，对行和列进行统计评估和熵估算，以确定重启过程的可靠性和最小熵。
"""
import math

from util import get_parser, to_dataset, get_z
from mostCommonValue import mostCommonValueRestart


def main_restart(datafile, bits_per_symbol, H_I, verbose=False):
    """
    执行 Restart 重启数据的 sanity 验证。
    :param datafile: 数据集文件路径
    :param bits_per_symbol: 每个符号的比特数
    :param H_I: 需要验证的目标估计熵值
    :param verbose: 是否输出详细测试信息
    :return: 包含验证结果和有效估算熵值的字典
    """
    with open(datafile, 'rb') as file:
        bytes_in = bytearray(file.read())
        dataset = to_dataset(bytes_in, bits_per_symbol)
        k = len(set(dataset))
        if verbose:
            print("file and dataset details")
            print("Read in file %s, %d bytes long." %
                  (datafile, len(bytes_in)))
            print("Dataset: %d %d-bit symbols, %d symbols in alphabet." %
                  (len(dataset), bits_per_symbol, k))
            print("Output symbol values: min = %d, max = %d" %
                  (min(dataset), max(dataset)))

        # max min-entropy is -log_2(1/k)
        minEntropy = float(math.log(k, 2))

        # make sure that the dataset is the expected size (otherwise, the column dataset won't be created correctly)
        assert len(dataset) == 1000000

        # 1. Let alpha be 0.01/(2000k), where k is the sample size
        alpha = 0.01/(2000*k)

        # 2. For each row of the matrix, find the frequency of the most common sample value. Let F_R be the maximum.
        if verbose:
            print("\nRunning sanity check on row dataset:")
        f = [0 for i in range(1000)]
        for i in range(1000):
            f[i] = mostCommonValueRestart(dataset[i*1000:(i+1)*1000])
        F_R = max(f)
        if verbose:
            print("- F_R: %d" % F_R)

        # 3. repeat the sample process for the column matrix. Let F_C be the maximum.
        if verbose:
            print("Running sanity check on column dataset:")
        f = [0 for i in range(1000)]
        for i in range(1000):
            column = []
            for j in range(1000):
                column.append(dataset[j*1000+i])
            f[i] = mostCommonValueRestart(column)
        F_C = max(f)
        if verbose:
            print("- F_C: %d" % F_C)

        # 4. Let F = max(F_R, F_C)
        F = max(F_R, F_C)

        # 5. Let p = 2**-H_I. Find the upper bound U of the (1-alpha)% confidence interval
        p = math.pow(2, -H_I)
        Z = get_z(alpha)
        U = 1000*p + Z*math.sqrt(1000*p*(1-p))
        if verbose:
            print("U: %f" % U)

        # 6. If F is greater than U, the test fails
        if F > U:
            print("Failed the restart tests")
            print("*** Validation failed. No entropy estimate awarded.")
            return {"passed": False, "H_I": None, "F": F, "U": U}
        else:
            print("Passed the restart tests")
            print("*** Final entropy estimate: %f" % H_I)
            return {"passed": True, "H_I": H_I, "F": F, "U": U}


if __name__ == "__main__":
    args = get_parser('restart').parse_args()
    main_restart(args.datafile, int(args.bits_per_symbol),
                 float(args.H_I), bool(args.verbose))
