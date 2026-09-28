"""
【模块名称】: main_noniid.py
【模块功能】: NIST SP800-90B 标准下针对 Non-IID 数据（或者未通过 IID 测试的数据）的熵评估主入口。
【设计要点】:
 1. 采用极为保守的评估策略，通过调用多种不同的预测器和估计方法来综合衡量数据的随机性。
 2. 主要包括：最常见值测试(MCV)、碰撞测试(Collision)、马尔可夫测试(Markov)、压缩测试(Compression)以及所有 SP800-90B 草案中的高级预测器（如 MultiMCW, Lag, LZ78Y 等）。
 3. 最终输出的保守最小熵（Min-Entropy）是所有预测器得出结果中的最小值（即最坏情况下的熵）。
【核心函数】:
 - main_noniid: 整体协调脚本，加载数据序列并依次传给各个 Non-IID 测试算法，最终汇总输出所有的熵估值以及最小安全值。
"""
import time
import math

from util import get_parser, to_dataset, map_data
from mostCommonValue import theMostCommonValueEstimate
from collision import theCollisionEstimate
from markov import theMarkovEstimate
from compression import theCompressionEstimate
from tTuple import tTupleEstimate
from longestRepeatedSubstring import longestRepeatedSubstringEstimate
from SP80090Bv2Predictors import MultiMCWPredictionEstimate, LagPredictionEstimate, MultiMMCPredictionEstimate, LZ78YPredictionEstimate


def main_noniid(datafile, bits_per_symbol, use_bits=None, verbose=False):
    """
    执行 Non-IID 保守熵评估流程。
    :param datafile: 数据集文件路径
    :param bits_per_symbol: 每个符号的比特数
    :param use_bits: 使用低位比特截断位数（可选，默认为 bits_per_symbol）
    :param verbose: 是否输出详细的测试进度和状态信息
    :return: 包含各种预测器结果字典和最小保守熵 min_entropy
    """
    start = time.perf_counter()
    if use_bits is None:
        use_bits = bits_per_symbol

    results = {}

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

        if use_bits < bits_per_symbol:
            mask = (2 ** use_bits) - 1
            dataset = [s & mask for s in dataset]
            k = len(set(dataset))
            if verbose:
                print("* Using only low %d bits out of %d. %d symbols in reduced alphabet." %
                      (use_bits, bits_per_symbol, k))
                print("* Using output symbol values: min = %d, max = %d" %
                      (min(dataset), max(dataset)))
        # some estimates require mapping the dataset to sequential outputs starting at 0
        mapped = map_data(dataset)

        # max min-entropy is -log_2(1/k)
        minEntropy = float(math.log(k, 2))

        if verbose:
            print("\nRunning entropic statistic estimates:")

        # Section 6.3.1 The Most Common Value Estimate
        pmax, minH = theMostCommonValueEstimate(dataset)
        results["MCV"] = minH
        if verbose:
            print(
                "- Most Common Value Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        minEntropy = min(minH, minEntropy)

        # Section 6.3.2 The Collision Estimate
        pmax, minH = theCollisionEstimate(dataset, k)
        results["Collision"] = minH
        if verbose:
            if minH is None:
                print("- Collision Estimate: not applicable (v < 1000), excluded from the minimum")
            else:
                print("- Collision Estimate: p(max) = %g, min-entropy = %g" %
                      (pmax, minH))
        if minH is not None:
            minEntropy = min(minH, minEntropy)

        # Section 6.3.3 The Markov Estimate: If more than 6 bits per symbol, map down to 6 bits per symbol and run Markov test
        if use_bits > 6:
            pmax, minH = theMarkovEstimate([s & 63 for s in dataset], 64, 0.99)
            if verbose:
                print(
                    "- Markov Estimate (map 6 bits): p(max) = %g, min-entropy = %g" % (pmax, minH))
        else:
            pmax, minH = theMarkovEstimate(mapped, k, 0.99)
            if verbose:
                print("- Markov Estimate: p(max) = %g, min-entropy = %g" %
                      (pmax, minH))
        results["Markov"] = minH
        minEntropy = min(minH, minEntropy)

        # Section 6.3.4 The Compression Estimate
        pmax, minH = theCompressionEstimate(mapped, k)
        results["Compression"] = minH
        if verbose:
            print("- Compression Estimate: p(max) = %g, min-entropy = %g" %
                  (pmax, minH))
        minEntropy = min(minH, minEntropy)

        # Section 6.3.5 t-Tuple Estimate
        pmax, minH = tTupleEstimate(dataset)
        results["t-Tuple"] = minH
        if verbose:
            print("- t-Tuple Estimate: p(max) = %g, min-entropy = %g" %
                  (pmax, minH))
        minEntropy = min(minH, minEntropy)

        # Section 6.3.6 The Longest Repeated Substring Estimate
        pmax, minH = longestRepeatedSubstringEstimate(dataset)
        results["LRS"] = minH
        if verbose:
            print("- LRS Estimate: p(max) = %g, min-entropy = %g" % (pmax, minH))
        minEntropy = min(minH, minEntropy)

        if verbose:
            print("\nRunning predictor estimates:")

        # Section 6.3.7 Multi Most Common in Window prediction estimate
        pmax, minH = MultiMCWPredictionEstimate(dataset, verbose)
        results["MultiMCW"] = minH
        if verbose:
            print(
                "MultiMCW Prediction Estimate: p(max) = %g, min-entropy = %g\n" % (pmax, minH))
        minEntropy = min(minH, minEntropy)

        # Section 6.3.8 Lag prediction estimate
        pmax, minH = LagPredictionEstimate(dataset, verbose)
        results["Lag"] = minH
        if verbose:
            print("Lag Prediction Estimate: p(max) = %g, min-entropy = %g\n" %
                  (pmax, minH))
        minEntropy = min(minH, minEntropy)

        # Section 6.3.9 MultiMMC prediction estimate
        pmax, minH = MultiMMCPredictionEstimate(dataset, verbose)
        results["MultiMMC"] = minH
        if verbose:
            print(
                "MultiMMC Prediction Estimate: p(max) = %g, min-entropy = %g\n" % (pmax, minH))
        minEntropy = min(minH, minEntropy)

        # Section 6.3.10 LZ78Y prediction estimate
        pmax, minH = LZ78YPredictionEstimate(dataset, verbose)
        results["LZ78Y"] = minH
        if verbose:
            print("LZ78Y Prediction Estimate: p(max) = %g, min-entropy = %g" %
                  (pmax, minH))
        minEntropy = min(minH, minEntropy)

        print("min-entropy = %g" % (minEntropy))
        print("\nDon't forget to run the sanity check on a restart dataset using H_I = %g" % minEntropy)
        end = time.perf_counter()
        print('Running time: %s Seconds' % (end - start))

        return {"min_entropy": minEntropy, "details": results}


if __name__ == "__main__":
    args = get_parser('non-IID').parse_args()
    use_b = int(args.use_bits) if args.use_bits else None
    main_noniid(args.datafile, int(args.bits_per_symbol),
                use_b, bool(args.verbose))
