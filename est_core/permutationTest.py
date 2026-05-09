"""
【模块名称】: permutationTest.py
【模块功能】: 实现 IID 验证的核心手段之一：置换测试（Permutation Test）。
【设计要点】:
 1. 测试基础前提：如果数据是 IID 的，其序列经过任意随机打乱后，内部各种统计特征的值分布应该与原序列一致。
 2. 利用大量伪随机置换（Shuffling）不断生成对照组数据，检查诸如碰撞次数、重复子串长度等特征。
 3. 若原序列统计特征大幅偏离对照组（即 P-value 过低或过高），则推翻其独立同分布（IID）假设。
【核心函数】:
 - run_permutation_tests: 控制多轮数据打乱与统计指标重算，整合并比较各项统计测试（如碰撞、LRS等）的 P 值。
"""
import sys
import bz2


try:
    import numpy as np
    shuffle = np.random.shuffle
except:
    import random
    shuffle = random.shuffle


def calc_stats(dataset):
    """
    Calculate the mean and median and identify if binary or not
    """
    mean = sum(dataset)/float(len(dataset))

    if min(dataset) == 0 and max(dataset) == 1:
        is_binary = True
        median = 0.5
    else:
        is_binary = False
        sd = sorted(dataset)
        halfway = len(sd) // 2
        if len(sd) % 2 == 0:
            median = (sd[halfway] + sd[halfway-1]) / 2.0
        else:
            median = sd[halfway]

    return (mean, median, is_binary)


###########################################
# Section 5.1 conversions for binary data #
###########################################

def conversion1(s):
    """
    conversion I
    partitions the sequences into 8-bit non-overlapping blocks, and counts the number of ones in each block.
    """
    sp = [s[i:i+8].count(1) for i in range(0, len(s)-len(s) % 8, 8)]
    if len(s) % 8 > 0:
        sp.append(s[len(sp)*8:].count(1))

    return sp


def conversion2(s):
    """
    conversion II
    partitions the sequences into 8-bit non-overlapping blocks, and calculates the integer value of each block.
    """
    sp = str(s)[1:-1]
    sp = sp.replace(', ', '')
    if len(s) % 8 == 0:
        padding = 0
    else:
        padding = 8 - len(s) % 8
    padded = sp + '0' * padding
    sp_bytes = [int(padded[i:i+8], 2) for i in range(0, len(padded), 8)]

    return sp_bytes


###############################
# Section 5.1 test statistics #
###############################

def excursionTestStatistic(s, mean):
    """
    Section 5.1.1 - Excursion Test Statistic
    """
    # 1. Calculate the average of the sample values (passed as argument)
    # 2. For i=1 to L, calculate d_i
    # 3. T = max(d_1, ..., d_L)
    L = len(s)
    di = 0
    maximum = 0
    runningsum = 0
    for i in range(L):
        runningsum += s[i]
        di = runningsum-(i+1)*mean

        if di > maximum:
            maximum = di
        elif -di > maximum:
            maximum = -di

    return maximum


def numOfDirectionalRuns(s):
    """
    Section 5.1.2 - Number of Directional Runs
    """
    L = len(s)

    # 1. Construct the sequence s'. We've given s' as input. just double check
    if set(s) != set([1, -1]):
        print("error - input string is not sequence of 1's and -1's")
        quit()

    # 2. The test statistic T is the number of runs in s'
    numruns = 1
    for i in range(1, L):
        if s[i] != s[i-1]:
            numruns += 1

    return numruns


def lenOfDirectionalRuns(s):
    """
    Section 5.1.3 - Length of Directional Runs
    """
    L = len(s)

    # 1. Construct the sequence s'. We've given s' as input. just double check
    if not set(s).issubset(set([1, -1])):  # set(s) > set([1, -1]):
        print("error - input string is not sequence of 1's and -1's")
        quit()

    # 2. The test statistic T is the length of the longest run in s'
    maxrun = 0
    run = 1
    for i in range(1, L):
        if s[i] == s[i-1]:
            run += 1
        else:
            if run > maxrun:
                maxrun = run
            run = 1

    # handle the last observed run
    if run > maxrun:
        maxrun = run

    return maxrun


def numOfIncreasesDecreases(s):
    """
    Section 5.1.4 - Number of Increases and Decreases
    """
    L = len(s)

    # 1. Construct the sequence s'. We've given s' as input. just double check
    if set(s) != set([1, -1]):
        print("error - input string is not sequence of 1's and -1's")
        quit()

    # 2. calculate the number of +1 and -1 in s'; the test statisitic T is the maximum of these two numbers
    pos = s.count(1)
    return max(pos, L-pos)


def numOfRunsBasedOnTheMedian(sp):
    """
    Section 5.1.5 - Number of Runs Based on the Median
    """
    # Steps 1 and 2 found in function alt_sequence2
    # 3. The test statistic is the number of runs in s'
    numruns = 1
    for i in range(1, len(sp)):
        if sp[i] != sp[i-1]:
            numruns += 1

    return numruns


def lenOfRunsBasedOnTheMedian(sp):
    """
    Section 5.1.6 - Length of Runs Based on Median
    """
    # Steps 1 and 2 found in function alt_sequence2
    # 3. The test statistic is the length of the longest run in s'
    maxrun = 0
    run = 1
    for i in range(1, len(sp)):
        if sp[i] == sp[i-1]:
            run += 1
        else:
            if run > maxrun:
                maxrun = run
            run = 1

    # handle the last observed run
    if run > maxrun:
        maxrun = run

    return maxrun


def avgCollisionTestStatistic(C):
    """
    Section 5.1.7 - Average Collision Test Statistic, takes list of collisions, C, as input
    """
    # Steps 1 through 3 found in function find_collisions
    # 4. The test statistic T is the average of all values in the list C.
    return sum(C)/float(len(C))


def maxCollisionTestStatistic(C):
    """
    Section 5.1.8 - Maximum Collision Test Statistic, takes list of collisions, C, as input
    """
    # Steps 1 through 3 found in function find_collisions
    # 4. The test statistic T is the maximum value in the list C.
    return max(C)


def periodicityTestStatistic(s, p):
    """
    Section 5.1.9 - Periodicity Test Statistic
    """
    L = len(s)

    # 1. Initialize T to 0
    T = 0

    # 2. For i=1 to L-p
    #      If (s_i = s_(i+p)), increment T by one
    i = 0
    while i < (L-p):
        if s[i] == s[i+p]:
            T += 1
        i += 1

    return T


def covarianceTestStatistic(s, p):
    """
    Section 5.1.10 - Covariance Test Statistic
    """
    L = len(s)

    # 1. Initialize T to 0
    T = 0

    # 2. For i=1 to L-p
    #      T = T+s_i*s_(i+p)
    i = 0
    while i < (L-p):
        T = T+(s[i]*s[i+p])
        i += 1

    return T


def compressionTestStatistic(s):
    """
    Section 5.1.11 - Compression Test Statistics
    """
    # 1. Samples in the data subset are encoded as a character string containing a list of values separated by a single space, e.g., (144,21,139,0,0,15) becomes "144 21 139 0 0 15"
    encodeS = " ".join([str(i) for i in s])

    # 2. The character string is processed with the BZ2 compression algorithm.
    compressed_string = bz2.compress(encodeS.encode())

    # 3. The score returned is the length of the compressed string, in bytes.
    return (len(compressed_string),)


def get_test_names():
    test_names = ('excursionTestStatistic',
                  'numOfDirectionalRuns',
                  'lenOfDirectionalRuns',
                  'numOfIncreasesDecreases',
                  'numOfRunsBasedOnTheMedian',
                  'lenOfRunsBasedOnTheMedian',
                  'avgCollisionTestStatistic',
                  'maxCollisionTestStatistic',
                  'periodicityTestStatistic(1)',
                  'periodicityTestStatistic(2)',
                  'periodicityTestStatistic(8)',
                  'periodicityTestStatistic(16)',
                  'periodicityTestStatistic(32)',
                  'covarianceTestStatistic(1)',
                  'covarianceTestStatistic(2)',
                  'covarianceTestStatistic(8)',
                  'covarianceTestStatistic(16)',
                  'covarianceTestStatistic(32)',
                  'compressionTestStatistic')

    return test_names


def alt_sequence1(s):
    """
    create alternate sequence for several statistics
    """
    L = len(s)
    sp = []
    for i in range(L-1):
        if s[i] > s[i+1]:
            sp.append(-1)
        else:
            sp.append(1)
    return sp


def alt_sequence2(s, X):
    """
    create alternate sequence for median-based statistics
    """
    L = len(s)

    # 1. Find the median X of S (argument into function)
    # 2. construct a temporary sequence s'
    sp = []
    for i in range(L):
        if s[i] < X:
            sp.append(-1)
        else:
            sp.append(1)
    return sp


def find_collisions(s):
    """
    Finds list of collisions for collision statistics
    """
    L = len(s)
    # 1. Let C be a list of the number of the samples observed to find two occurrences of the same value in the input sequence. C is initially empty.
    C = []

    # 2. Let i = 1
    i = 0  # adjusted for index starting at 0

    # 3. While i<L
    # 3a. Find the smallest j such that (s_i,...s_(i+j-1)) contains two identical values. If no such j exists, break out of the while loop.
    # 3b. Add j to the list C
    # 3c. i = i+j +1
    i = 0
    for ell, index in enumerate(s):
        if index in s[i:ell]:
            C.append(ell - i + 1)  # j = ell-i+1
            i = ell + 1

    return C


def permutationTest(s, verbose=False):
    """
    Permutation testing
    """
    mean, median, is_binary = calc_stats(s)

    # 1. For each test i
    # 1.1 Assign the counters to zero
    C = {}
    for i in get_test_names():
        C[i] = [0, 0]

    if verbose:
        print("Calculating statistics on original sequence")

    # 1.2 Calculate the test statistic T_i on s; denote the result as t[i]
    t = {}

    # conversions for binary data
    if is_binary:
        cs1 = conversion1(s)
        cs2 = conversion2(s)

    t['excursionTestStatistic'] = excursionTestStatistic(s, mean)

    if is_binary:
        # conversion 1 required for binary data for directional run and increases/decreases statistics
        sp1 = alt_sequence1(cs1)
        t['numOfDirectionalRuns'] = numOfDirectionalRuns(sp1)
        t['lenOfDirectionalRuns'] = lenOfDirectionalRuns(sp1)
        t['numOfIncreasesDecreases'] = numOfIncreasesDecreases(sp1)
    else:
        sp1 = alt_sequence1(s)
        t['numOfDirectionalRuns'] = numOfDirectionalRuns(sp1)
        t['lenOfDirectionalRuns'] = lenOfDirectionalRuns(sp1)
        t['numOfIncreasesDecreases'] = numOfIncreasesDecreases(sp1)

    if is_binary:
        sp2 = alt_sequence2(s, 0.5)
    else:
        sp2 = alt_sequence2(s, median)
    t['numOfRunsBasedOnTheMedian'] = numOfRunsBasedOnTheMedian(sp2)
    t['lenOfRunsBasedOnTheMedian'] = lenOfRunsBasedOnTheMedian(sp2)

    if is_binary:
        # conversion 2 required for collision statistics on binary data
        collision_list = find_collisions(cs2)
    else:
        collision_list = find_collisions(s)
    t['avgCollisionTestStatistic'] = avgCollisionTestStatistic(collision_list)
    t['maxCollisionTestStatistic'] = maxCollisionTestStatistic(collision_list)

    if is_binary:
        # conversion 1 required for periodicity statistics on binary data
        t['periodicityTestStatistic(1)'] = periodicityTestStatistic(cs1, 1)
        t['periodicityTestStatistic(2)'] = periodicityTestStatistic(cs1, 2)
        t['periodicityTestStatistic(8)'] = periodicityTestStatistic(cs1, 8)
        t['periodicityTestStatistic(16)'] = periodicityTestStatistic(cs1, 16)
        t['periodicityTestStatistic(32)'] = periodicityTestStatistic(cs1, 32)
    else:
        t['periodicityTestStatistic(1)'] = periodicityTestStatistic(s, 1)
        t['periodicityTestStatistic(2)'] = periodicityTestStatistic(s, 2)
        t['periodicityTestStatistic(8)'] = periodicityTestStatistic(s, 8)
        t['periodicityTestStatistic(16)'] = periodicityTestStatistic(s, 16)
        t['periodicityTestStatistic(32)'] = periodicityTestStatistic(s, 32)

    if is_binary:
        # conversion 1 required for covariance statistics on binary data
        t['covarianceTestStatistic(1)'] = covarianceTestStatistic(cs1, 1)
        t['covarianceTestStatistic(2)'] = covarianceTestStatistic(cs1, 2)
        t['covarianceTestStatistic(8)'] = covarianceTestStatistic(cs1, 8)
        t['covarianceTestStatistic(16)'] = covarianceTestStatistic(cs1, 16)
        t['covarianceTestStatistic(32)'] = covarianceTestStatistic(cs1, 32)
    else:
        t['covarianceTestStatistic(1)'] = covarianceTestStatistic(s, 1)
        t['covarianceTestStatistic(2)'] = covarianceTestStatistic(s, 2)
        t['covarianceTestStatistic(8)'] = covarianceTestStatistic(s, 8)
        t['covarianceTestStatistic(16)'] = covarianceTestStatistic(s, 16)
        t['covarianceTestStatistic(32)'] = covarianceTestStatistic(s, 32)

    t['compressionTestStatistic'] = compressionTestStatistic(s)

    # 2. For j=1 to 10000
    # 2.1 Permute the input data using Fisher-Yates
    if verbose:
        print("Calculating statistics on permuted sequences")
    for j in range(10000):
        if verbose:
            sys.stdout.write(
                "\rpermutation tests:\t%.2f percent complete" % (float(j)/100))
            sys.stdout.flush()
        shuffle(s)

        # 2.2 for each test i
        # 2.2.1 Calcualte the test statistic; denote the result as tp[i]
        tp = {}

        # conversions for binary data
        if is_binary:
            cs1 = conversion1(s)
            cs2 = conversion2(s)

        tp['excursionTestStatistic'] = excursionTestStatistic(s, mean)

        if is_binary:
            # conversion 1 required for binary data for directional run and increases/decreases statistics
            sp1 = alt_sequence1(cs1)
            tp['numOfDirectionalRuns'] = numOfDirectionalRuns(sp1)
            tp['lenOfDirectionalRuns'] = lenOfDirectionalRuns(sp1)
            tp['numOfIncreasesDecreases'] = numOfIncreasesDecreases(sp1)
        else:
            sp1 = alt_sequence1(s)
            tp['numOfDirectionalRuns'] = numOfDirectionalRuns(sp1)
            tp['lenOfDirectionalRuns'] = lenOfDirectionalRuns(sp1)
            tp['numOfIncreasesDecreases'] = numOfIncreasesDecreases(sp1)

        if is_binary:
            sp2 = alt_sequence2(s, 0.5)
        else:
            sp2 = alt_sequence2(s, median)
        tp['numOfRunsBasedOnTheMedian'] = numOfRunsBasedOnTheMedian(sp2)
        tp['lenOfRunsBasedOnTheMedian'] = lenOfRunsBasedOnTheMedian(sp2)

        if is_binary:
            # conversion 2 required for collision statistics on binary data
            collision_list = find_collisions(cs2)
        else:
            collision_list = find_collisions(s)
        tp['avgCollisionTestStatistic'] = avgCollisionTestStatistic(
            collision_list)
        tp['maxCollisionTestStatistic'] = maxCollisionTestStatistic(
            collision_list)

        if is_binary:
            # conversion 1 required for periodicity statistics on binary data
            tp['periodicityTestStatistic(1)'] = periodicityTestStatistic(
                cs1, 1)
            tp['periodicityTestStatistic(2)'] = periodicityTestStatistic(
                cs1, 2)
            tp['periodicityTestStatistic(8)'] = periodicityTestStatistic(
                cs1, 8)
            tp['periodicityTestStatistic(16)'] = periodicityTestStatistic(
                cs1, 16)
            tp['periodicityTestStatistic(32)'] = periodicityTestStatistic(
                cs1, 32)
        else:
            tp['periodicityTestStatistic(1)'] = periodicityTestStatistic(s, 1)
            tp['periodicityTestStatistic(2)'] = periodicityTestStatistic(s, 2)
            tp['periodicityTestStatistic(8)'] = periodicityTestStatistic(s, 8)
            tp['periodicityTestStatistic(16)'] = periodicityTestStatistic(
                s, 16)
            tp['periodicityTestStatistic(32)'] = periodicityTestStatistic(
                s, 32)

        if is_binary:
            # conversion 1 required for covariance statistics on binary data
            tp['covarianceTestStatistic(1)'] = covarianceTestStatistic(cs1, 1)
            tp['covarianceTestStatistic(2)'] = covarianceTestStatistic(cs1, 2)
            tp['covarianceTestStatistic(8)'] = covarianceTestStatistic(cs1, 8)
            tp['covarianceTestStatistic(16)'] = covarianceTestStatistic(
                cs1, 16)
            tp['covarianceTestStatistic(32)'] = covarianceTestStatistic(
                cs1, 32)
        else:
            tp['covarianceTestStatistic(1)'] = covarianceTestStatistic(s, 1)
            tp['covarianceTestStatistic(2)'] = covarianceTestStatistic(s, 2)
            tp['covarianceTestStatistic(8)'] = covarianceTestStatistic(s, 8)
            tp['covarianceTestStatistic(16)'] = covarianceTestStatistic(s, 16)
            tp['covarianceTestStatistic(32)'] = covarianceTestStatistic(s, 32)

        tp['compressionTestStatistic'] = compressionTestStatistic(s)

        # 2.2.2 If (tp[i] > t[i]), increment C[i,0]. If (tp[i] = t[i]), increment C[i,1].
        for i in get_test_names():
            if tp[i] > t[i]:
                C[i][0] += 1
            elif tp[i] == t[i]:
                C[i][1] += 1

    if verbose:
        print("\n                statistic  C[i][0]  C[i][1]")
        print("-------------------------------------------")
        for i in get_test_names():
            if ((C[i][0]+C[i][1]) <= 5) or (C[i][0] >= 9995):
                print("%24s* %8d %8d" % (i, C[i][0], C[i][1]))
            else:
                print("%25s %8d %8d" % (i, C[i][0], C[i][1]))
        print("(* denotes failed test)")

    # 3. If (C[i][0]+C[i][1] <= 5) or (C[i][0] >= 9995) for any i, reject the IID assumption. Else assume the noise source produces IID output.
    for i in get_test_names():
        if ((C[i][0]+C[i][1]) <= 5) or (C[i][0] >= 9995):
            return False
    return True
