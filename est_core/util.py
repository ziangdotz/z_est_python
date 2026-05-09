"""
【模块名称】: util.py
【模块功能】: est_core 的公共底层工具库，提供读写、位运算和数学转换等辅助支持。
【设计要点】:
 1. 作为基础设施层，它处理诸如将多字节符号转换为位、计算汉明重量、处理各类统计计数的通用逻辑。
 2. 避免各个测试算法中重复出现相似的数据转换和矩阵操作逻辑，确保底层计算统一。
【核心函数】:
 - get_symbol_counts / _internal_get_symbol_counts: 统一提供数据中各唯一值的出现频次计算。
 - kbit_element: 将位数组聚合转化为整数，支撑定长字符测试。
 - hamming_weight: 快速计算整数或字节数据的汉明重量。
"""
import argparse


def get_parser(test=None):
    """
    提供标准化的 NIST SP800-90B 统一命令行解析器。
    支持原有模块的单独调用参数（传入 test="restart"/"IID"/"non-IID"）
    或者生成一个大一统的综合参数解析器（传入 test=None）。
    """
    if test is not None:
        valid = {'restart', 'IID', 'non-IID'}
        if test not in valid:
            raise ValueError(
                f"Unknown test type: {test!r}. Expect one of {sorted(valid)}")

        descr = 'Run the Draft NIST SP800-90B (January 2018) %s Tests' % test
        parser = argparse.ArgumentParser(description=descr)
        parser.add_argument(dest='datafile',
                            metavar='datafile',
                            help='dataset on which to run tests')
        parser.add_argument(dest='bits_per_symbol',
                            metavar='bits_per_symbol',
                            help='number of bits used to represent sample output values')

        if test == 'restart':
            parser.add_argument(dest='H_I',
                                metavar='H_I',
                                help='initial entropy estimate')
        elif test == 'IID':
            pass
        elif test == 'non-IID':
            parser.add_argument('-u',
                                '--usebits',
                                dest='use_bits',
                                metavar='use_bits',
                                help='use only the N lowest order bits per sample')

        parser.add_argument('-v',
                            '--verbose',
                            dest='verbose',
                            action='store_true',
                            help='verbose mode: show detailed test results')
        return parser

    # 如果是统一调用（test=None），生成大一统规范接口
    parser = argparse.ArgumentParser(
        description="NIST SP800-90B 统一熵评估测试工具",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # 必填基础参数（使用可选标志的方式，更符合现代 CLI 设计）
    parser.add_argument('-f', '--file', dest='datafile', required=True,
                        help="需要测试的二进制数据文件路径 (必须)")
    parser.add_argument('-b', '--bits_per_symbol', dest='bits_per_symbol', type=int, default=8,
                        help="每个符号的比特数 (默认: 8)")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="输出详细的内部测试过程信息")

    # 测试模式开关（可多选）
    test_group = parser.add_argument_group("测试模式选项 (至少选择一项)")
    test_group.add_argument('--restart', action='store_true',
                            help="执行 Restart 重启状态完整性检验")
    test_group.add_argument('--iid', action='store_true',
                            help="执行 IID 独立同分布检验及熵评估")
    test_group.add_argument('--non-iid', action='store_true',
                            help="执行 Non-IID 保守最小熵综合评估")

    # 模式特定参数
    specific_group = parser.add_argument_group("特定测试的高级参数")
    specific_group.add_argument('--use-bits', dest='use_bits', type=int, default=None,
                                help="[Non-IID专用] 指定提取的低位比特数进行测试 (若不指定则等于 bits_per_symbol)")
    specific_group.add_argument('--h-i', dest='H_I', type=float, default=None,
                                help="[Restart专用] 需要验证的目标初始最小熵估计值 H_I (执行重启测试时必须)")

    return parser


def to_dataset(bytes, bits_per_symbol):
    """
    Convert a bytearray of raw bytes to a list containing the dataset
    Use bits-per-symbol to do the mapping
    Note that 1 bit per symbol assumes that 1 bit per byte is used, the data is not packed (i.e., 8 1-bit output samples are not packed into 1 byte)
    Does not handle > 8 bits per symbol.
    """
    assert bits_per_symbol > 0
    assert bits_per_symbol <= 8

    # mask for relevant bits
    mask = 2**bits_per_symbol - 1

    N = len(bytes)
    print("reading %d bytes of data" % N)

    if bits_per_symbol <= 8:  # includes 1-bit per symbol
        return [b & mask for b in bytes]
    else:
        return list()


def get_z(alpha):
    """
    Find the z-value for restart tests
    Given alpha, find z corresponding to upper bound of confidence interval alpha_min= 1.95312E-08, alpha_max=2.5E-06
    """
    z_values = {2.5E-06: 4.708129716,
                2.45E-06: 4.712247134,
                2.4E-06: 4.716446023,
                2.35E-06: 4.72072975,
                2.3E-06: 4.725101895,
                2.25E-06: 4.729566273,
                2.2E-06: 4.734126952,
                2.15E-06: 4.738788277,
                2.1E-06: 4.743554897,
                2.05E-06: 4.748431792,
                2E-06: 4.753424309,
                1.95E-06: 4.758538192,
                1.9E-06: 4.763779631,
                1.85E-06: 4.769155304,
                1.8E-06: 4.77467243,
                1.75E-06: 4.780338834,
                1.7E-06: 4.78616301,
                1.65E-06: 4.792154206,
                1.6E-06: 4.798322513,
                1.55E-06: 4.804678972,
                1.5E-06: 4.811235695,
                1.45E-06: 4.818006016,
                1.4E-06: 4.825004652,
                1.35E-06: 4.832247908,
                1.3E-06: 4.839753915,
                1.25E-06: 4.847542912,
                1.2E-06: 4.855637585,
                1.15E-06: 4.864063487,
                1.1E-06: 4.872849536,
                1.05E-06: 4.882028643,
                1E-06: 4.891638476,
                9.5E-07: 4.901722437,
                9E-07: 4.912330888,
                8.5E-07: 4.923522727,
                8E-07: 4.935367445,
                7.5E-07: 4.947947838,
                7E-07: 4.96136365,
                6.5E-07: 4.975736557,
                6E-07: 4.99121714,
                5.5E-07: 5.007994871,
                5E-07: 5.026312837,
                4.5E-07: 5.046490185,
                4E-07: 5.06895775,
                3.5E-07: 5.094317391,
                3E-07: 5.123447001,
                2.5E-07: 5.157701313,
                2E-07: 5.199337583,
                1.5E-07: 5.252559482,
                1E-07: 5.326723889,
                5E-08: 5.451310443,
                1.95312E-08: 5.61610279}

    if alpha in z_values.keys():
        return z_values[alpha]
    else:
        if alpha < min(z_values.keys()):
            return z_values[min(z_values.keys())]
        elif alpha > max(z_values.keys()):
            return z_values[max(z_values.keys())]
        else:
            # find closest match
            best = 10  # just a number that's too high
            for k in z_values.keys():
                if abs(k-alpha) < abs(best-alpha):
                    best = k
            return z_values[best]


def map_data(seq):
    """
    Map dataset to list 0..n. This is necessary for datasets here k is not a power of 2 or not all symbols in the range are present in the dataset. For example, a trinary source that outputs 13,14, and 15 would then convert the sequence to 0, 1, and 2 so that it will play nicely with the list indices used in the methods.
    """
    # create new sorted list of unique symbols
    sortedData = sorted(list(set(seq)))
    return [sortedData.index(seq[i]) for i in range(len(seq))]
