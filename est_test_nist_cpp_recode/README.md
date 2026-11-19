# NIST SP800-90B 熵评估测试工具 — C++ Recode 版

基于 [NIST SP800-90B](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-90B.pdf) 标准实现的熵源评估工具（C++ v1.1.8 Python 重写版），支持 **Restart**、**IID** 和 **Non-IID** 三类测试模式。

---

## 环境要求

- 建议 Python 3.12；解释器选择与完整依赖安装见[根 README](../README.md#2-环境)
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
├── job_bench.py                   # 主要估计器计时与最慢项，不代表完整调度覆盖
└── README.md                      # 本说明文档
```

核心算法模块位于上级目录 `est_core_nist_cpp_recode/` 中。
四个校验/基准脚本是开发工具，桌面应用和 Web 服务直接调用核心库，不依赖这些脚本。

---

## 使用方法

以下直接调用的示例在 `est_test_nist_cpp_recode/` 目录执行，并使用已安装依赖的 Python：

```bash
python est_test_nist_cpp_recode.py <数据文件路径> [选项]
```

也可从仓库根目录传入参数（相对数据路径按根目录解析）：

```bash
make run_test_nist_cpp_recode TEST_ARGS="data/source.bin --non-iid -j 1"
```

不传 `TEST_ARGS` 时，Make 目标默认显示 `--help`，不会自动选择数据或测试模式。

---

## 参数说明

### 基础参数

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `datafile` | （位置参数） | 待测试的二进制数据文件路径 | （必填） |
| `--bits` | | IID / Non-IID 的符号位宽，1～8；0 = 自动检测。Restart 仍自动检测 | `0` |
| `--verbose` | `-v` | 增加输出详细程度：无标志为 1，`-v` 为 2，`-vv` 为 3 | `1` |

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
| `--workers` | IID / Non-IID | 并行进程数，缩写 `-j`：IID 按置换轮次并行、Non-IID 按估计器并行；默认按逻辑 CPU 数的一半估算，至少 1 个；`-j 1` 关闭并行 |

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

IID 置换检验在同一随机种子下按轮序计数；Non-IID 在父进程按固定顺序重放估计器的输出。
当前统一入口不提供 IID 随机种子参数，不能假定两次独立运行的 JSON 逐字相同。
共享机器上可用 `-j` 限制占用，或用 `-j 1` 退回单进程：

```bash
python est_test_nist_cpp_recode.py source_out.bin --iid -j 4
python est_test_nist_cpp_recode.py source_out.bin --non-iid -j 1
```

---

## 开发校验与基准

这些脚本不会被 `build_all` 自动执行，也不是最终程序的运行依赖。

### 与 C++ 参考实现的回归比对（refdata_diff.py）

脚本运行 `ea_non_iid -vv`，只提取含 ` Estimate:` 的明细行，与
`../8ckup/NIST_SP800-90B_EntropyAssessment/cpp/selftest/refdata/*.res` 比较。
`8ckup/` 不入库，需另行准备样本和参考输出；缺失用例会计入失败。

```bash
python refdata_diff.py                       # 3 个 10000 样本的短文件，默认容差 1e-9
python refdata_diff.py --all --tol 1e-6       # 11 个 refdata 样本，耗时较长
python refdata_diff.py truerand_4bit --show-ulp -j 1
```

每个行对先比文本骨架（仅遮住 `= 数值`），再按位置比较数值的相对误差。
字段名、段名或行序不一致报 `wording drift`，数值超容差报 `value mismatch`。
全部用例通过时退出码为 0，否则为 1；头部提示、`H_*` 汇总、JSON 和其它测试模式不在比对范围内。

默认 `1e-9` 用于短样本严格回归。全量目标保留 `--tol 1e-6`，因为 C++ `long double`、
Python `float` 与不同数学库可能产生收敛点和舍入差异；预测器 `-log2(p)` 的相对误差又会按
`1/|ln p|` 放大，已知参考样本会在严格档超容差。该阈值仅用于输出验收，**不改变最终熵计算**，
也不表示其它算法错误可以通过放宽容差忽略。

---

### 后缀数组 / LCP 的中间量指纹（lrs_bench.py）

打印后缀数组的首尾抽样、LCP 的 max/sum、两个熵值的 `repr()`，并分别计时。
相比只看最终熵值，它更容易发现 `_lrs.py` 改动造成的中间量差异：

```bash
python lrs_bench.py ../8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
# 或 make lrs_bench（仓库根目录，默认就是上面这份样本）
```

改动前后比较打印的指纹，计时字段不参与判等。**抽样指纹相同并不能证明完整数组逐元素相同**，
必要时仍应增加完整数组比对和边界用例；耗时比较需控制样本、负载及冷热启动条件。

---

### 纯 Python / numba 对拍（jit_crosscheck.py）

脚本比较 MultiMCW / Lag 的两种视图，以及二元 MultiMMC / LZ78Y 的 Python 与 numba 原始计数。
它绕过 `JIT_MIN_SAMPLES`（默认 10 万）的尺寸门槛，因此可覆盖短样本正常评估不会执行的 JIT 路径：

```bash
python jit_crosscheck.py                       # 11 个 refdata 样本，每视图截断 25 万符号
python jit_crosscheck.py --samples truerand_8bit --cap 0
```

每个有效用例还要求 `Kernel.compiled` 非空，避免两侧都退回 Python 后得到无效的“通过”。
numba 不可用或设置了 `EA_DISABLE_JIT=1` 时无法完成 JIT 验证，会报错退出。

---

### 逐 job 耗时分布（job_bench.py）

在单进程中对主要 Non-IID 估计器逐个计时，辅助定位热点，不做正确性判定：

```bash
python job_bench.py ../8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
# 或 make job_bench（仓库根目录，默认就是上面这份样本）
```

每行一个 (估计器, 视图)，`SUM` 为本次计时之和，`MAX` 为最慢项，仅用于估计理想并行的下限，
不是端到端墙钟时间。脚本不计 MCV，且当前跳过 Collision / Markov / Compression 的 Literal 视图，
因此二元样本也不会测到这三项，不能视作完整调度覆盖。
比较 JIT 开关时需固定样本、机器负载及缓存状态；首次内核编译成本可能计入首个调用。

---

## 输出说明

- 测试过程中会在控制台输出各阶段的执行进度与中间结果（使用 `-v` 开启详细输出）。
- 所有测试完成后，以 **JSON 格式** 输出汇总结果，便于日志记录与二次集成处理。
- 若某项测试发生异常，错误信息会单独记录在 JSON 结果中，不会中断其他测试的执行。
- 外层 `status: pass` 仅表示核心调用未抛异常；还需检查 `data.errorLevel`、`errorMsg` 及 IID 的各检验标志。
- 当前入口不会按各项测试的失败结果设置进程退出码，自动化验收不能只看退出码 0。

输出结构示意（只包含所选测试）：

```json
{
    "Restart_Test": {"status": "pass", "h_min": 0.9, "H_I": 0.9},
    "IID_Test": {"status": "pass", "data": {}},
    "Non_IID_Test": {"status": "pass", "data": {}}
}
```

---

## 数据文件要求

- 数据文件必须为**二进制格式**。
- 每个 1～8 位样本单独占一个字节；当前读取器不支持 9～16 位样本的多字节解码。
- 按 bit 打包的文件先用上级 `est_core_nist_cpp_recode/cli/ea_unpack_bits.py` 展开。
- IID / Non-IID 建议不少于 **1,000,000** 个连续样本；Restart 必须恰好 **1,000,000** 个，按 1000 × 1000 排列。
