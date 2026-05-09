"""
【模块名称】: main_dnn.py
【模块功能】: NIST SP800-90B 标准下基于 DNN 的 Non-IID 熵评估主入口。
【设计要点】:
 1. 使用全连接网络（FC）和循环神经网络（RNN）预测下一个符号，根据预测准确率估计最小熵。
 2. 取所有预测器结果中的最小值作为最终保守熵估计。
【核心函数】:
 - main_dnn: 整体协调脚本，加载数据序列并依次传给 FC 和 RNN 预测器，汇总输出熵估值。
"""
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'           # suppress C++ TF logs
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'          # disable oneDNN info messages

import logging
logging.getLogger('absl').setLevel(logging.ERROR)   # suppress absl Python warnings

import time
import math

from util import get_parser, to_dataset, map_data
from DNNPredictors import FC, RNN


def main_dnn(datafile, bits_per_symbol, use_bits=None, verbose=False):
    """
    执行基于 DNN 的 Non-IID 熵评估流程。
    :param datafile: 数据集文件路径
    :param bits_per_symbol: 每个符号的比特数
    :param use_bits: 使用低位比特截断位数（可选，默认为 bits_per_symbol）
    :param verbose: 是否输出详细的测试进度和状态信息
    :return: 包含各预测器结果的字典和最小保守熵 min_entropy
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

        mapped = map_data(dataset)

        minEntropy = float(math.log(k, 2))

        if verbose:
            print("\nRunning DNN statistic estimates:")

        # FC Estimate
        minH = FC(dataset, bits_per_symbol, verbose)
        results["FC"] = minH
        print("-----------------------")
        print("FC estimate min-entropy = %g" % (minH))
        minEntropy = min(minH, minEntropy)

        # RNN Estimate
        minH = RNN(dataset, bits_per_symbol, verbose)
        results["RNN"] = minH
        print("-----------------------")
        print("RNN estimate min-entropy = %g" % (minH))
        minEntropy = min(minH, minEntropy)

        print("-----------------------")
        print("min-entropy = %g" % (minEntropy))
        print("\nDon't forget to run the sanity check on a restart dataset using H_I = %g" % minEntropy)
        end = time.perf_counter()
        print('Running time: %s Seconds' % (end - start))

        return {"min_entropy": minEntropy, "details": results}


if __name__ == '__main__':
    args = get_parser('non-IID').parse_args()
    use_b = int(args.use_bits) if args.use_bits else None
    main_dnn(args.datafile, int(args.bits_per_symbol),
             use_b, bool(args.verbose))
