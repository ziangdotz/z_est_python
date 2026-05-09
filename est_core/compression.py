"""
【模块名称】: compression.py
【模块功能】: 实现 NIST SP800-90B (Section 6.3.4) 压缩估计测试（Compression Estimate Test）。
【设计要点】:
 1. 利用类似 Maurer 的通用统计测试（Universal Statistical Test）概念，通过观察数据字典距离来评估熵。
 2. 它对于 Non-IID 数据的熵评估具有较强保守性。
 3. 算法将序列分割成字典部分和测试部分，根据观测值在历史中最近出现的位置来评估当前数据的可预测性，以此计算熵。
【核心函数】:
 - expected_value: 用于基于输入概率 p 评估期望值的目标函数。
 - compression_test: 压缩测试的具体实现主逻辑，遍历数据样本以构建字典距离分布，并求解熵值估计。
"""
from math import sqrt
from math import log
from math import floor


d = 1000


def G(p, v):
    """
    G(p) as defined in Step 8 of Section 9.3.6.3
    """
    Gsum = 0.0
    N = v + d
    # The inner sum for s = 1 -> d...compute once...use in every iteration of outer loop
    inSum = p * p * sum([log(s, 2.0) * pow(1.0-p, s-1)
                        for s in range(1, (d+1))])
    Gsum = inSum * (N - float(d))

    # log2(s) * (1-p)^(s-1) used in next two terms
    st = [log(s, 2.0) * pow(1.0-p, s-1) for s in range((d+1), N+1)]

    # The additional 's < t' sum term for s = (d+1) -> N-1
    Gsum += p * p * sum([(N-i-(d+1)) * st[i] for i in range(N-(d+1))])

    # The 's = t' term for s = (d+1) -> N
    Gsum += p * sum(st)

    return Gsum / v


def EppM(p, n, v):
    """
    Expected value of Maurer Statistic using the one-param family of probability distributions in Step 7. of 9.3.6.3
    """
    q = (1.0 - p)/(n - 1.0)
    return G(p, v) + (n - 1) * G(q, v)


def solve_for_p(mu_bar, n, v, tolerance=0.00001):
    """
    Binary search algorithm to find value of p s.t. the expected value of the Maurer Universal Statistic equals mu_bar within tolerance
    """
    minp = 1.0/float(n)
    p = (1-minp)/2.0+minp
    adj = (1-minp)

    Ep_maxvalid = EppM(1.0/float(n), n, v)
    if mu_bar > Ep_maxvalid:
        return False, 0.0

    Ep = EppM(p, n, v)
    while abs(mu_bar - Ep) > tolerance:
        adj /= 2.0
        if mu_bar > Ep:
            p -= adj
        else:
            p += adj
        Ep = EppM(p, n, v)

    return True, p


def theCompressionEstimate(dataset, k):
    """
    Section 6.3.4 The Compression Estimate
    """
    # 1. Partition the dataset into two disjoint groups. These two groups will form the dictionary and the test data.
    # 1.a. Create the dictionary from the first d=1000 observations,
    # 1.b. Use the remaining v = L - d observations for testing
    # 2. Initialize the dictionary, dict to an all zero array of size k. For i from 1 to d, let dict[s_i]=i
    v = len(dataset) - d
    dictionary = [0 for i in range(k)]
    for index, obs in enumerate(dataset[:d]):
        dictionary[obs] = index + 1

    # 3. Run the test data against the dictionary created in Step 2
    # 3.a. Let Di be a list of length v.
    # 3.b. For i from d+1 to L:
    # 3.b.i If dict[si] is non-zero, then Di-d = i - dict[si]. Update the dictionary with the index of the most recent observation, dict[si] = i.
    # 3.b.ii If dict[si] is zero, add that value to the dictionary, i.e., dict[si]=i. Let Di-d = i.
    D = []
    for index, obs in enumerate(dataset[d:]):
        D.append(index + (d+1) - dictionary[obs])
        dictionary[obs] = index + (d+1)

    # 4. Let b = the number of bits needed to represent the largest symbol in the out alphabet. Calculate the sample mean, mu, and the sample standard dev, sigma, of (log2(Di)) for i = 1 -> v where the Di are the calculated differences from Step 3b
    b = floor(log(max(dataset), 2.0))+1
    D = [log(Di, 2.0) for Di in D]
    mu = sum(D) / v
    c = 0.7 - 0.8/b + (4+32.0/b)*(v**(-3.0/b))/15
    sigma = sum([Di * Di for Di in D])/v - (mu * mu)
    sigma = sqrt(sigma)
    sigma = c*sigma

    # 5. Compute the lower-bound of the 99% confidence interval for the mean based on a normal distribution
    mu_bar = mu - (2.576*sigma)/sqrt(v)
    print("\tmu=%g, sigma=%g, mu_bar=%g\n" % (mu, sigma, mu_bar))

    # 6. Using a binary search, solve for parameter p
    valid, p = solve_for_p(mu_bar, k, v)
    if not valid:
        # No solution to equation. Assume max min-entropy.
        return 1.0/k, log(k, 2.0)

    # 7. The min-entropy is the negative logarithm of the parameter, p
    min_entropy = -log(p, 2.0)

    return p, min_entropy
