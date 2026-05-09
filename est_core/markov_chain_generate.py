"""
【模块名称】: markov_chain_generate.py
【模块功能】: 测试数据的生成工具，基于设定的马尔可夫转移矩阵合成测试用的状态序列。
【设计要点】:
 1. 这是一个辅助测试脚本，用于生成已知属性的数据样本，从而验证其他统计检验（如马尔可夫测试、碰撞测试等）算法的准确性。
 2. 模拟非理想的随机发生器行为，可指定特定的前状态依赖性（转移概率矩阵）。
"""
# clear all % 清除工作区中的所有变量
# clc % 清空命令行窗口
# nlength=100000; % 定义要生成的马尔可夫序列的总长度为 100,000
# p=0.49; % 定义状态转移概率参数 p 为 0.49
# x(1)=randsrc(1,1,[0 1 2 3;.25 .25 .25 .2]); % 随机生成初始状态 x(1)，取值为 0,1,2,3，对应概率分别为 0.25, 0.25, 0.25, 0.2 (注：概率和0.95，MATLAB会做归一化)
# for i=2:nlength % 从第2个元素开始循环，生成后续的状态序列
#     if(x(i-1)==1) % 检查前一个状态是否为 1
#         x(i)=randsrc(1,1,[0 1;p 1-p]); % 若前一状态为 1，则当前状态有 p(0.49) 的概率转移为 0，1-p(0.51) 的概率转移为 1
#     else % 若前一个状态不为 1（如 0, 2 或 3）
#         x(i)=randsrc(1,1,[0 1;1-p p]); % 当前状态有 1-p(0.51) 的概率转移为 0，p(0.49) 的概率转移为 1
#     end % 结束状态转移条件判断
# end % 结束序列生成循环
# filename='markov_chain_generate.txt'; % 指定输出保存的文件名
#     fid=fopen(filename,'wb'); % 以二进制写入模式('wb')打开文件，返回文件标识符 fid
#         for i=1:length(x) % 遍历生成的整个马尔可夫状态序列 x
#             fwrite(fid,x(i),'uint8'); % 将每个状态值以 8位无符号整数(uint8) 格式逐字节写入到文件中
#         end % 结束写入循环
#     fclose('all'); % 关闭所有已打开的文件句柄，保存文件并释放系统资源

import numpy as np

# 参数设置
nlength = 100000
p = 0.49

# 初始化数组，使用 uint8 类型以匹配最终写入文件的格式
x = np.zeros(nlength, dtype=np.uint8)

# 1. 生成初始状态
# MATLAB中概率 [0.25, 0.25, 0.25, 0.2] 总和为 0.95，MATLAB会自动归一化
# np.random.choice 需要概率总和严格为 1，所以我们手动归一化
init_probs = np.array([0.25, 0.25, 0.25, 0.2])
init_probs = init_probs / init_probs.sum()
x[0] = np.random.choice([0, 1, 2, 3], p=init_probs)

# 2. 循环生成状态序列 (Python 索引从 0 开始，所以从 1 循环到 nlength-1)
for i in range(1, nlength):
    if x[i-1] == 1:
        # p 的概率为 0，1-p 的概率为 1
        x[i] = np.random.choice([0, 1], p=[p, 1-p])
    else:
        # 1-p 的概率为 0，p 的概率为 1
        x[i] = np.random.choice([0, 1], p=[1-p, p])

# 3. 将生成的数组以无符号 8 位整数（二进制形式）写入文件
# numpy 的 tofile 方法行为与 MATLAB 的 fwrite(..., 'uint8') 配合 wb 模式完全一致
filename = 'markov_chain_generate.txt'
x.tofile(filename)

print(f"成功生成 {nlength} 个状态，并已保存到 {filename}")
