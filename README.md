# z_est_python — NIST SP 800-90B 熵评估（Python）

按 NIST SP 800-90B（January 2018）评估熵源的 min-entropy。仓库里有**两条独立实现**（纯 Python 原版、
按 C++ 参考实现逐函数重写版）与**三种调用外壳**（命令行测试脚本、pywebview 桌面应用、FastAPI Web 服务）。

---

## 1. 环境

- 本工程固定使用 conda 环境 `z_est_env_python`，目录 `C:\Tools\miniconda3\envs\z_est_env_python`
  （当前实测 Python 3.12.14）。**PATH 上的 `python` 不是这个环境**，而是 msys64 的
  `C:\Tools\msys64\mingw64\bin\python.exe`，没装 numpy / nuitka，直接 `python xxx.py` 会
  `ModuleNotFoundError`、`make build_all` 会 `No module named nuitka`。
- `make` 的目标已经默认指向上面那个 conda 解释器（探测到该路径就用，探不到才回退 PATH 上的
  `python`），无需每次手写 `PYTHON=`；要用别的解释器时显式覆盖（见 §5）。
- 安装依赖：`pip install -r requirements.txt`
  - `requirements.txt` 是 **UTF-8 + LF**（历史上被存成 UTF-16LE+BOM，已转换；`.gitattributes` 负责守住这条线）
  - 全部版本锁定；`scipy` / `numba` 是可选项，缺失时代码自动回退（回退不改变任何计算结果）
  - 当前环境按**构建 + 桌面应用**范围装配（已实测 `make build_all` / `jit_crosscheck` / `lrs_bench` 跑通），
    64 条锁定项中精确命中 16 条；**未装的是三个功能栈**：`tensorflow` / `keras` 及其传递依赖
    （只有 `est_core/main_dnn.py` 的 DNN 预测器需要）、`fastapi` / `uvicorn` / `pydantic`
    （只有 `est_web_fastapi` 需要）、`pytest` / `coverage`。跑这些入口前先补装。

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
├── est_test_x_vue3_pywebview/     # Vue3 + pywebview 桌面应用（Nuitka 打包 onefile，详见其 README）
├── est_web_fastapi/               # FastAPI Web 服务（两条实现各挂一套路由）
├── 8ckup/                         # NIST C++ 上游源码副本 + 11 个测试样本 + selftest/refdata 基准（不入库）
├── data/                          # 本地输入数据与评估产物（不入库）
├── docs/                          # 本地设计笔记与实现分析（不入库）
├── release/                       # 打包输出（不入库）
├── requirements.txt               # 全量版本锁定（UTF-8 + LF，见 §1）
└── Makefile                       # 常用目标，见 §5
```

---

## 3. 快速开始

四个入口脚本都接受一个二进制数据文件、输出 JSON 汇总，且都有对应的 `make` 目标
（解释器已绑定 conda 环境，不必手写 `PYTHON=`）：

```bash
make run_test                        # 实现 A（est_core）
make run_test_nist_cpp_recode        # 实现 B —— 推荐，与 C++ 参考实现同源
make run_test_x_vue3_pywebview       # 桌面应用开发模式（自动 npm install，连 Vite dev server）
make run_web_fastapi                 # FastAPI Web 服务
```

只想跑单个环节时用 `cli/` 下的入口（详细参数 `-h`）。这些没有 make 目标，下面的
`python` 需先 `conda activate z_est_env_python`、或换成该解释器的绝对路径——裸
`python` 会命中 msys64 那份（见 §1）：

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
make help                                       # 列出全部目标

# 运行四个入口
make run_test                                   # 实现 A（est_core）
make run_test_nist_cpp_recode                   # 实现 B（推荐，与 C++ 参考实现同源）
make run_test_x_vue3_pywebview                  # 桌面应用开发模式
make run_web_fastapi                            # FastAPI Web 服务

# 与 C++ 参考实现的校验 / 基准（见 §4）
make refdata_diff                               # 3 个短样本快速回归
make refdata_diff_all                           # 11 个样本全量回归（数十分钟）
make jit_crosscheck                             # 纯 Python / numba 两条路对拍
make lrs_bench                                  # 后缀数组 / LCP 计时与指纹
make job_bench                                  # 逐 job 耗时分布

# 打包与清理
make build_all                                  # 桌面应用 → release/（见 §6）
make build_test_x_vue3_pywebview_windows_amd64  # build_all 目前唯一的成员目标
make clean                                      # 删 release/ 里的产物
```

目标里用的解释器默认是 conda 环境 `z_est_env_python`（自动继承到 `est_test_x_vue3_pywebview/`
子 Makefile），所以直接 `make xxx` 即可；样本路径用 `LRS_BENCH_SAMPLE` / `JOB_BENCH_SAMPLE`
覆盖，换解释器用 `PYTHON=` 覆盖：

```bash
make refdata_diff
make refdata_diff PYTHON=C:/Tools/miniconda3/envs/z_est_env_python/python.exe   # 等价于默认值
```

---

## 6. 打包桌面应用

`make build_all` 用 **Nuitka 4.0.8**（不是 PyInstaller）把桌面应用打成免安装的 onefile exe，
产物落在 `release/est_test_x_vue3_pywebview_windows_amd64.exe`（约 46.8 MiB）。完整构建链、
打包取舍，以及两个 Windows 陷阱（缺 Anaconda `Library\bin` 原生 DLL 导致启动即 native abort、
Defender 的 ML 启发式把产物当病毒删——`Wacapew.A!ml` 打构建出的 exe、`Contebrew.A!ml`
打运行时解压到 `%TEMP%\onefile_*` 的 `main.dll`，后者需单独加排除），详见
[`est_test_x_vue3_pywebview/README.md`](est_test_x_vue3_pywebview/README.md)。

构建完务必验证一次——GUI 构建没有控制台，结果必须落文件：

```powershell
release\est_test_x_vue3_pywebview_windows_amd64.exe --selftest --selftest-log selftest.log
echo $LASTEXITCODE      # 0 = 通过
```

`--selftest` 走前端同一个 `Api` 真跑一次 IID + Non-IID，并校验 Vue 产物 `dist/index.html`
确实在载荷里，用退出码回答“产物到底有没有把分析库和前端打进去”，比手点 UI 可靠。其它参数
（`--selftest-all` / `--selftest-timeout`）见上述子 README。

---

## 7. 数据文件格式

- 必须为**二进制**格式。熵源输出 1~8 位样本时每个样本占一个字节；9~16 位用两个连续字节（高字节在前），依此类推。
- 建议采集不少于 **1,000,000** 个连续样本；无法满足时请记录原因。
- 若采集端是按 bit 打包的文件，先用 `cli/ea_unpack_bits.py` 展开成每样本一字节。
