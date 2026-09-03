# NIST SP800-90B 熵评估测试工具 — C++ Recode 版

基于 [NIST SP800-90B](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-90B.pdf) 标准实现的熵源评估工具（C++ v1.1.8 Python 重写版），支持 **Restart**、**IID** 和 **Non-IID** 三类测试模式。

---

## 环境要求

- Python 3.x
- NumPy
- （可选）SciPy（用于 χ² 检验，无时回退到内置实现）
- （可选）numba（四个逐样本预测器的热点循环编译执行；缺失时自动回退到纯 Python 循环，结果不变）

---

## 目录结构

```
est_test_nist_cpp_recode/
├── est_test_nist_cpp_recode.py    # 统一测试入口脚本（基于 est_core_nist_cpp_recode）
├── refdata_diff.py                # 与 C++ selftest/refdata 逐行比对 Non-IID 输出（回归校验）
├── lrs_bench.py                   # t-Tuple/LRS 的 SA、LCP 分函数计时与中间量指纹
├── jit_crosscheck.py              # 对拍每个预测器的纯 Python 循环与 numba kernel
├── job_bench.py                   # 按调度顺序逐个计时，看并行后的最长 job（墙钟下限）
└── README.md                      # 本说明文档
```

核心算法模块位于上级目录 `est_core_nist_cpp_recode/` 中。

---

## 使用方法

基本语法：

```bash
python est_test_nist_cpp_recode.py <数据文件路径> [选项]
```

---

## 参数说明

### 基础参数

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `datafile` | （位置参数） | 待测试的二进制数据文件路径 | （必填） |
| `--bits` | | 每个符号的位数（0 = 自动检测） | `0` |
| `--verbose` | `-v` | 增加输出详细程度（可叠加：`-v`, `-vv`） | `1` |

### 测试模式选项（至少选择一项）

| 参数 | 说明 |
|------|------|
| `--restart` | 执行 Restart 重启状态完整性检验 |
| `--iid` | 执行 IID（独立同分布）检验及熵评估 |
| `--non-iid` | 执行 Non-IID 保守最小熵综合评估 |

### 特定测试的高级参数

| 参数 | 适用模式 | 说明 |
|------|----------|------|
| `--h-i` | Restart | 需要验证的目标初始最小熵估计值 H_I（执行 Restart 测试时**必须**指定） |
| `--workers` | IID / Non-IID | 并行进程数，缩写 `-j`：IID 按置换轮次并行、Non-IID 按各估计器并行；默认每个物理核 1 个，`-j 1` 关闭多进程 |

---

## 使用示例

### 1. 执行 Restart 测试

```bash
python est_test_nist_cpp_recode.py source_out.bin --restart --h-i 0.95 -v
```

### 2. 仅执行 IID 测试（自动检测符号位宽）

```bash
python est_test_nist_cpp_recode.py source_out.bin --iid
```

### 3. 指定 8 位符号执行 Non-IID 测试

```bash
python est_test_nist_cpp_recode.py source_out.bin --bits 8 --non-iid -v
```

### 4. 同时执行三项测试

```bash
python est_test_nist_cpp_recode.py source_out.bin --restart --iid --non-iid --h-i 0.95 -v
```

### 5. 限制并行度

IID 的 10000 轮置换按轮次分发到多个进程预先计算，计数仍严格按轮序进行，因此
并行与串行（同一随机种子下）的 `C[i][*]` 计数逐元素一致，判定结果不受影响。
Non-IID 的各估计器（§6.3.2 起）同样分发到多个进程，父进程按参考实现的顺序取回
并重放它们打印的明细行，所以 `-j 1` 与并行输出的唯一差异是 timestamp / commandline。
在共享机器上可用 `-j` 压低占用，或用 `-j 1` 完全退回单进程：

```bash
python est_test_nist_cpp_recode.py source_out.bin --iid -j 4
python est_test_nist_cpp_recode.py source_out.bin --non-iid -j 1
```

---

## 与 C++ 参考实现的回归比对（refdata_diff.py）

`ea_non_iid` 在 `-vv` 下打印的每一行 `… Estimate: …` 与 C++ 参考实现的行数、字段名、顺序
逐字一致，因此可以直接拿仓库里的 `8ckup/.../selftest/refdata/*.res` 做回归基准：

```bash
python refdata_diff.py                       # 3 个 10000 样本的短文件（秒级）
python refdata_diff.py --all                 # 11 个 refdata 样本（数十分钟）
python refdata_diff.py truerand_4bit --show-ulp -j 1
```

每个行对先比“文本骨架”（只把 `= 数值` 部分遮成 `#`，所以字段名/段名/行序漂移会直接报
“wording drift”），再按位置提取数值做相对误差比较（默认容差 `1e-9`，超出报
“value mismatch”，容差内计入 within-tol）。无硬差异时退出码为 0，可直接接进 CI 或 `make refdata_diff`。

当前基准上的结果：11 个样本的行数完全相同（binary 63 行、多比特 104 行），字段名与行序零漂移，
数值差异只来自三类已知原因：C++ 用 80-bit `long double` 打印 `%.22Lg`（Python 只有 `double`）；
`log2` / `sqrt` 派生值的 1–2 ULP libm 差异（refdata 在 Linux/glibc 下生成）；`calc_p_local` 二分搜索
的收敛点差异（仅 ringOsc-nist 的 MultiMCW，经 `-log2` 放大后为 1.1e-9）。因此验收预测器派生值时用
`python refdata_diff.py --all --tol 1e-6`（对应重写方案 §15.4 的「正常」档），平时回归用默认的 1e-9 严格档。

---

## 后缀数组 / LCP 的中间量指纹（lrs_bench.py）

`refdata_diff.py` 只能看到 t-Tuple / LRS 两个最终熵值，而熵值是标量：后缀数组或 LCP 数组里某个
位置错了，只要不落在取胜的那几个前缀上，熵值可能照样对。`lrs_bench.py` 把 `build_suffix_array`
的首尾若干项、`sa_to_lcp` 的 max/sum 与两个熵值的 `repr()` 一并打印，并分函数计时：

```bash
python lrs_bench.py ../8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
# 或 make lrs_bench（仓库根目录，默认就是上面这份样本）
```

改 `_lrs.py` 时前后各跑一次，要求指纹逐元素相同：熵值对上了只能说明错误没影响到结果的位置，
中间量对得上才是真的等价。耗时只能用于同一次运行内比较函数之间
（本机持续负载会降频，热态整体约 ×1.3）。

---

## 纯 Python / numba 双胞胎对拍（jit_crosscheck.py）

MultiMCW / Lag / MultiMMC / LZ78Y 各有一份逐样本循环，`ea/_jit.py` 让 numba 把同一份循环
编译成机器码。两条路必须交出完全相同的 `correct_count` / `max_run`，但仅靠端到端回归验不了：
JIT 只在样本数超过 `JIT_MIN_SAMPLES`（10 万）时才启用，短样本的回归根本不会走到 kernel 上。
`jit_crosscheck.py` 绕开这道尺寸门槛，直接把两条路的原始计数拿出来比：

```bash
python jit_crosscheck.py                       # 11 个 refdata 样本，每视图截断 25 万符号
python jit_crosscheck.py --samples truerand_8bit --cap 0
```

每个用例除了比计数，还要求 `Kernel.compiled` 非空——静默退回 Python 侧会让「两边相同」
变成同义反复。Lag 的两侧本来就是两种写法（列表 + 二分裁剪 vs 参考实现的 128 槽环形缓冲），
所以这一行同时对译了数据结构。改任一 kernel 后跑一次即可（无 numba 时直接报错退出）。

---

## 逐 job 耗时分布（job_bench.py）

估计器并行之后，墙钟 ≈ 最贵的单个 job + 父进程开销，所以「还能不能再快」只看这张表。
`refdata_diff.py` 管端到端正确性，`jit_crosscheck.py` 管两条路等价，速度分布归这里：

```bash
python job_bench.py ../8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
# 或 make job_bench（仓库根目录，默认就是上面这份样本）
```

它在单进程里跑，每行一个 (估计器, 视图)，末两行给出 `SUM`（单进程跑完全部估计器的量）
与 `MAX (critical path)`（并行后墙钟的下限）。要比较 JIT 开 / 关，用 `EA_DISABLE_JIT=1`
在**同一轮**里各跑一次：本机是笔记本，持续负载会降频（热态整体约 ×1.3），后台还有别的
进程时所有 job 会一起放慢（实测过 ×1.9），此时绝对值不可比、只有同一次运行内的比值可信。

---

## 输出说明

- 测试过程中会在控制台输出各阶段的执行进度与中间结果（使用 `-v` 开启详细输出）。
- 所有测试完成后，以 **JSON 格式** 输出汇总结果，便于日志记录与二次集成处理。
- 若某项测试发生异常，错误信息会单独记录在 JSON 结果中，不会中断其他测试的执行。

输出示例：

```json
{
    "Restart_Test": { ... },
    "IID_Test": { ... },
    "Non_IID_Test": { ... }
}
```

---

## 数据文件要求

- 数据文件必须为**二进制格式**。
- 若熵源输出 1~8 位样本，每个样本单独占一个字节；若为 9~16 位，使用两个连续字节表示（高字节在前），依此类推。
- 建议采集不少于 **1,000,000** 个连续样本；若无法满足，请记录原因。
