"""
【模块名称】: markov.py
【模块功能】: 实现 NIST SP800-90B (Section 6.3.3) 马尔可夫测试（Markov Test）。
【设计要点】:
 1. 用于评估 Non-IID 数据，并特别关注序列中的一阶马尔可夫（一阶状态转移）特性。
 2. 算法通过统计数据中状态对之间的转移频率，建立转移概率矩阵，并搜索其中大概率的转移路径。
 3. 通过转移矩阵连乘估计状态序列可能产生的高概率输出，用于界定最小熵上限。
【核心函数】:
 - markov_test: 构建一阶转移概率和初始概率，进行连乘追踪，最终计算得出一阶马尔可夫假设下的 Min-Entropy 估算。
"""
import math


def theMarkovEstimate(s, k, alpha):
    # 1. Re-define the confidence level to be alpha = min(alpha^k^2,alpha^d) where k^2 is the number of terms in the transition matrix and d=128 is the assumed length of the Markov chain.
    d = 128
    alpha_exp = max(k * k, d)
    alpha = math.pow(alpha, alpha_exp)

    # 2. Estimate the initial state probability distribution, P, with: Pi = min(1, o_i/L + epsilon)
    count = [s.count(i) for i in range(k)]
    L = len(s)
    epsilon_term = math.log(1.0/(1.0 - alpha), 2)
    epsilon = math.sqrt(epsilon_term/(2 * L))
    P = [min(1.0, count[i]/float(L) + epsilon) for i in range(k)]

    # 3. Let o_s_L = o_s_L - 1. Need to subtract 1 from count of last symbol for bounding matrix construction. Nothing follows the last occurance, therefore it should not be included in transition proportion.
    count[s[-1]] -= 1
    # 3. Estimate the probabilities in the transition matrix T, overestimating where...; Ti,j = 1 if o_i = 0; min(1, oi,j + eps_i) otherwise
    oij = [[0 for j in range(k)] for i in range(k)]
    oi = s[0]
    for oj in s[1:]:
        oij[oi][oj] += 1
        oi = oj
    epsilon_i = [0.0 if count[i] == 0 else math.sqrt(
        epsilon_term/(2.0 * count[i])) for i in range(k)]
    T = [[0 if count[i] == 0 else min(
        1.0, oij[i][j]/float(count[i]) + epsilon_i[i]) for j in range(k)] for i in range(k)]

    # 4. Using the transition matrix T, find the probability of the most likely sequence of states (pmax) ...
    for j in range(d-1):
        h = [0 for i in range(k)]
        for c in range(k):
            Pp = [0 for i in range(k)]
            for i in range(k):
                Pp[i] = P[i]*T[i][c]
            h[c] = max(Pp)
        P[:] = h[:]
    pmax = max(P)

    # 5. The min-entropy is the negative logarithm of the probability of the most likely sequence of states (pmax)
    min_entropy = -math.log(pmax, 2.0) / d

    return pmax, min_entropy
