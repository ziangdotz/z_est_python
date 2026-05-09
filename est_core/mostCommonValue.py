"""
【模块名称】: mostCommonValue.py
【模块功能】: 实现 NIST SP800-90B (Section 6.3.1) 的最常见值（Most Common Value, MCV）估计测试。
【设计要点】:
 1. 无论是针对 IID 还是 Non-IID 数据，这是最简单直接的熵估算方法。
 2. 寻找序列中出现频率最高的值，并用其频率来计算二项分布的置信区间上限，以此推导保守的熵值。
 3. 即使对于复杂的发生器，这往往也能直接暴露出其随机性的基线问题。
【核心函数】:
 - mcv_estimate: 统计样本最高频次，计算统计上限比例，随后利用公式 `min_entropy = -log2(p_u)` 求得对应最小熵。
"""
import math
from collections import Counter


def mostCommonValueRestart(s):
    """
    Section 3.1.4.3 Sanity Check - Most Common Value in the Rows and Columns
    """
    # Get a count of all the sample values.
    d = Counter(s)
    L = float(len(s))

    # find the proportion of the most common value
    cmax = d.most_common(1)[0][1]

    return cmax


def theMostCommonValueEstimate(s):
    """
    Section 6.3.1 - The Most Common Value Estimate
    """
    # Get a count of all the sample values.
    d = Counter(s)
    L = float(len(s))

    # 1. find the proportion of the most common value
    cmax = d.most_common(1)[0][1]
    pmax = cmax/L

    # 2. Calculate an upper bound on the probability of the most common value, p_u
    ubound = pmax + 2.576*math.sqrt(pmax * (1.0-pmax)/L)
    pu = min(1, ubound)

    # 3. The estimated min-entropy is -log_2(p_u)
    return [pu, -math.log(pu, 2.0)]
