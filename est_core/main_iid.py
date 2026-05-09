"""
【模块名称】: main_iid.py
【模块功能】: NIST SP800-90B 标准下针对 IID（独立同分布）假设数据的熵评估主入口。
【设计要点】:
 1. 是针对声称是 IID 的噪声源进行测试的核心协调脚本。
 2. 先后调用置换测试（Permutation Test）和卡方测试（Chi-Square Test）以验证数据的独立同分布特性。
 3. 如果数据通过了 IID 测试，模块将基于最高频值（Most Common Value, MCV）方法直接给出数据的最小熵；否则报告其未通过 IID 假设。
【核心函数】:
 - main_iid: 执行 IID 验证流程，输出最终验证结论和计算得出的 Min-Entropy。
"""
import time


from util import get_parser, to_dataset
from permutationTest import permutationTest
from chiSquareTest import chiSquareTest
from longestRepeatedSubstring import lenOfTheLongestRepeatedSubstringTest
from mostCommonValue import theMostCommonValueEstimate


def main_iid(datafile, bits_per_symbol, verbose=False):
    """
    执行 IID 验证及熵评估流程。
    :param datafile: 数据集文件路径
    :param bits_per_symbol: 每个符号的比特数
    :param verbose: 是否输出详细的测试进度和状态信息
    :return: 包含 IID 测试结果和最小熵估计值的字典
    """
    start = time.perf_counter()

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
            print("Output symbol values: min = %d, max = %d\n" %
                  (min(dataset), max(dataset)))

        # determine if dataset is IID using shuffle
        passed_permutationTests = permutationTest(dataset, verbose)
        if passed_permutationTests:
            if verbose:
                print("** Passed IID permutation tests")
        else:
            if verbose:
                print("** Failed IID permutation tests")
            print("IID = False")
            return {"IID": False, "min_entropy": None, "reason": "Failed IID permutation tests"}

        # run chi-square test
        if chiSquareTest(dataset, verbose):
            if verbose:
                print("** Passed chi square tests")
        else:
            if verbose:
                print("** Failed chi square tests")
            print("IID = False")
            return {"IID": False, "min_entropy": None, "reason": "Failed chi square tests"}

        # run longest repeated substring test
        if lenOfTheLongestRepeatedSubstringTest(dataset, verbose):
            if verbose:
                print("** Passed LRS test")
            print("\nIID = True")
        else:
            print("** Failed LRS test")
            print("IID = False")
            return {"IID": False, "min_entropy": None, "reason": "Failed LRS test"}

        # calculate min-entropy
        pmax, minH = theMostCommonValueEstimate(dataset)

        print("min-entropy = %g" % (minH))
        print("\nDon't forget to run the sanity check on a restart dataset using H_I = %g" % minH)
        end = time.perf_counter()
        print('Running time: %s Seconds' % (end - start))

        return {"IID": True, "min_entropy": minH}


if __name__ == "__main__":
    args = get_parser('IID').parse_args()
    main_iid(args.datafile, int(args.bits_per_symbol), bool(args.verbose))
