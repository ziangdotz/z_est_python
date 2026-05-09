"""
【模块名称】: collision.py
【模块功能】: 实现 NIST SP800-90B (Section 6.3.2) 标准中的 Collision Test (碰撞测试)。
【设计要点】:
 1. 主要用于评估 Non-IID 数据集的最小熵（Min-Entropy）。
 2. 基于数据序列中连续元素发生“碰撞”所需的时间（步长）来估计熵值。
 3. 通过二分查找（Binary Search）结合概率密度函数来求解发生碰撞的期望方程，进而反推得到最终的最小熵。
【核心函数】:
 - expected_value: 计算在给定概率分布 p 下，发生碰撞的理论期望值。
 - collision_test: 对输入数据集执行完整的碰撞测试逻辑，计算样本中的平均碰撞时间，并通过数值方法求解出对应的最小熵估算值。
"""
import math


def F(n, zInv):
    """
    Continued fraction for F(1/z) derived from Eq. 8.9.2 at http://dlmf.nist.gov/8.9
    Used in Step 9 in Section 6.3.2
    """
    z = 1.0/zInv
    denom = 1.0 + n/z
    for i in range(1, n):
        denom = z + -i/denom
        denom = 1.0 + (n-i)/denom

    denom = z + -n/denom
    return 1.0/denom


def calcEpS(p, k):
    """
    Expected value of statistic based on one-parameter family of prob distributions
    Used in step 9 of Section 6.3.2 (right side of equation)
    """
    q = (1.0 - p)/float(k - 1)
    i_k = 1.0 / k
    ip = 1.0/p
    iq = 1.0/q
    iq2 = iq * iq
    Ep = p * iq2 * (1.0 + i_k * (ip - iq)) * F(k, q) - \
        (p * iq * i_k * (ip - iq))
    return Ep


def solve_for_p(mu_bar, n):
    """
    Binary search for p that solves equation in step 9 of Section 6.3.2
    """
    minp = 1.0/float(n)
    p_c = (1-minp)/2.0+minp
    adj = (1-minp)
    Ep = calcEpS(p_c, n)
    Ep_maxvalid = calcEpS(1.0/float(n), n)
    if mu_bar > Ep_maxvalid:
        return False, 0.0
    while abs(mu_bar - Ep) > .0001:
        adj /= 2.0
        if mu_bar < Ep:
            p_c += adj
            # caclEps will crash if p_c is exactly 1.
            if p_c == 1.0:
                p_c -= 0.0001
        else:
            p_c -= adj
            # occasionally dips below lowest possible pmax. This is to fix that
            if p_c < minp:
                p_c = minp
        Ep = calcEpS(p_c, n)
        print('\tp = %g, Ep = %g, mu_bar = %g' % (p_c, Ep, mu_bar))
    return True, p_c


def theCollisionEstimate(s, n):
    """
    Section 6.3.2- Collision Estimate
    1. Set v=1, index=1
    2. Beginning with s_index, step through the dataset until any observed value is repeated; i.e., find smallest j s.t. si = sj for some i with 1 <= i < j
    3. Set t_v = j-index+1, v=v+1, and indes=j+1
    4. Repeat steps 2-3 until the end of the dataset is reached
    5. set v = v - 1
    6. If v < 1000, the noise source outputs will be mapped down based on the ranking provided, and the data will be retested.
    """
    k = len(set(s))
    index = 0
    t = [0]
    for ell, i in enumerate(s):
        if i in s[index:ell]:
            t.append(ell + 1)  # account for index starting at 1
            index = ell + 1
    diff_t = [t[i]-t[i-1] for i in range(1, len(t))]
    v = float(len(diff_t))  # float() so it works in Python 2.6,2.7
    if v < 1000:
        print("Must map down data for collision estimate, then retest")
        return 0.0, 0.0

    # 7. Calculate sample mean, mu, and sample stddev, sigma of the differences of collision times
    mu = sum(diff_t)/v
    sigma = sum([(ti-mu)**2 for ti in diff_t]) / v
    sigma = math.sqrt(sigma)

    # 8. Compute the lower-bound of the confidence interval for the mean based on a normal distribution with confidence level alpha=0.95
    mu_bar = mu - (2.576 * sigma / math.sqrt(v))

    # 9. Using a binary search, solve for the parameter p s.t. Ep equals mu_bar
    valid, p = solve_for_p(mu_bar, n)

    # 10. The min-entropy is the negative logarithm of the parameter p: min-entropy = -log2(p). If the search does not yield a solution, then estimate max min-entropy
    if not valid:
        # No solution to equation. Assume max min-entropy.
        return 1.0/k, math.log(k, 2)
    else:
        min_entropy = -math.log(p, 2.0)
        return p, min_entropy
