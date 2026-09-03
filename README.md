# z_est_python — NIST SP 800-90B 熵评估（Python）

按 NIST SP 800-90B（January 2018）评估熵源的 min-entropy。仓库里有**两条独立实现**（纯 Python 原版、
按 C++ 参考实现逐函数重写版）与**三种调用外壳**（命令行测试脚本、pywebview 桌面应用、FastAPI Web 服务）。

---

## 1. 环境

- conda 环境 `z_est_env_python`（Python 3.10）。**系统默认 python 没装 numpy**，直接 `python xxx.py` 会
  `ModuleNotFoundError`；`make` 的目标一律用 `PYTHON=` 指到目标解释器（见 §5）。
- 安装依赖：`pip install -r requirements.txt`
  - `requirements.txt` 是 **UTF-8 + LF**（历史上被存成 UTF-16LE+BOM，已转换；`.gitattributes` 负责守住这条线）
  - 全部版本锁定；`scipy` / `numba` 是可选项，缺失时代码自动回退（回退不改变任何计算结果）

| 依赖 | 必需 | 缺失时的行为 |
|------|:----:|--------------|
| `numpy` | ✅ | — |
| `scipy` | ⬜ | χ² p-value 走内置 Cephes `igamc` 实现 |
| `mpmath` | ✅ | 条件化评估需要任意精度 |
| `numba` + `llvmlite` | ⬜ | 四个逐样本预测器回退到纯 Python 双胞胎，结果逐位相同、约慢 4.7× |

---

## 2. 目录结构

```
z_est_python/
├── est_core/                      # 实现 A：纯 Python 原版（含 DNN 预测器 FC / RNN）
├── est_core_nist_cpp_recode/      # 实现 B：按 NIST C++ 参考实现逐函数重写
│   ├── ea/                        #   算法库（_config / _io / _lrs / _jit / _parallel / 各估计器）
│   └── cli/                       #   ea_iid · ea_non_iid · ea_restart · ea_conditioning
│                                  #   ea_transpose · ea_unpack_bits（数据预处理）
├── est_test/                      # 实现 A 的测试入口
├── est_test_nist_cpp_recode/      # 实现 B 的测试入口 + 四个校验/基准工具（见 §4）
├── est_test_x_vue3_pywebview/     # Vue3 + pywebview 桌面应用（前端在 frontend/，PyInstaller 打包）
├── est_web_fastapi/               # FastAPI Web 服务（两条实现各挂一套路由）
├── 8ckup/                         # NIST C++ 上游源码副本 + 11 个测试样本 + selftest/refdata 基准（不入库）
├── data/                          # 本地输入数据与评估产物（不入库）
├── docs/                          # 本地设计笔记与实现分析（不入库）
├── release/                       # 打包输出（不入库）
└── Makefile                       # 常用目标，见 §5
```

---

## 3. 快速开始

四个入口脚本都接受一个二进制数据文件，输出 JSON 汇总：

```bash
# 实现 A（est_core）
cd est_test && python est_test.py

# 实现 B（est_core_nist_cpp_recode）—— 推荐，与 C++ 参考实现同源
cd est_test_nist_cpp_recode && python est_test_nist_cpp_recode.py

# 桌面应用（开发模式，需先在 frontend/ 里 npm install）
cd est_test_x_vue3_pywebview && python main.py --dev

# Web 服务
cd est_web_fastapi && python run.py
```

只想跑单个环节时用 `cli/` 下的入口（详细参数 `-h`）：

```bash
python ../est_core_nist_cpp_recode/cli/ea_non_iid.py <file> -vv      # 非 IID 全套，-vv 打印与 C++ 逐行同构
python ../est_core_nist_cpp_recode/cli/ea_iid.py <file>              # IID 全套
python ../est_core_nist_cpp_recode/cli/ea_unpack_bits.py <packed>    # 8 bit/byte → 1 bit/byte
```

---

## 4. 与 C++ 参考实现的一致性

`8ckup/NIST_SP800-90B_EntropyAssessment` 是上游 C++ 实现的副本，其中
`cpp/selftest/refdata/*.res` 是 11 个官方样本的参考输出，被当作验收基准。
围绕它有四个工具，分工不重叠（都在 `est_test_nist_cpp_recode/` 下，各有 `make` 目标）：

| 工具 | 管什么 | 典型命令 |
|------|--------|---------|
| `refdata_diff.py` | **端到端正确性**：`ea_non_iid -vv` 逐行比对 refdata，退出码 0/1 | `refdata_diff.py --all --tol 1e-6` |
| `lrs_bench.py` | **中间量指纹**：后缀数组 / LCP 的抽样值与 `repr()`，不只看熵值 | `lrs_bench.py <file>` |
| `jit_crosscheck.py` | **两条路等价**：每个预测器的纯 Python 循环 vs numba kernel 的原始计数 | `jit_crosscheck.py` |
| `job_bench.py` | **速度分布**：逐 job 计时，给出 SUM 与并行后的最长 job（墙钟下限） | `job_bench.py <file>` |

当前基线：11/11 样本通过 1e-6 档；严格 1e-9 档下 3 个短样本 `exact = 53 / 89 / 87`；
numba 开与关给出的 `H_assessed` 逐字相同。

---

## 5. Make 目标

```bash
make help                                     # 列出全部目标
make refdata_diff                             # 3 个短样本快速回归
make refdata_diff_all                         # 11 个样本全量回归（数十分钟）
make jit_crosscheck                           # 纯 Python / numba 两条路对拍
make lrs_bench                                # 后缀数组 / LCP 计时与指纹
make job_bench                                # 逐 job 耗时分布
```

目标里调用的是裸 `python`。本机环境是 conda，所以要么先激活环境，要么显式指定解释器（样本路径用
`LRS_BENCH_SAMPLE` / `JOB_BENCH_SAMPLE` 覆盖）：

```bash
make refdata_diff PYTHON=D:/Tools/miniconda3/envs/z_est_env_python/python.exe
```

---

## 6. 数据文件格式

- 必须为**二进制**格式。熵源输出 1~8 位样本时每个样本占一个字节；9~16 位用两个连续字节（高字节在前），依此类推。
- 建议采集不少于 **1,000,000** 个连续样本；无法满足时请记录原因。
- 若采集端是按 bit 打包的文件，先用 `cli/ea_unpack_bits.py` 展开成每样本一字节。
