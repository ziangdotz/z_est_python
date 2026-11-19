# z_est_python — NIST SP 800-90B 熵评估（Python）

基于 NIST SP 800-90B（January 2018）评估熵源的最小熵（min-entropy）。项目包含两套核心实现，
以及命令行、Windows 桌面应用和 FastAPI Web 服务三种调用方式。

## 1. 项目架构

| 层次 | 位置 | 职责 |
|---|---|---|
| 核心实现 A | `est_core/` | 原版 Python 算法；DNN 的 FC / RNN 预测器使用独立入口 `main_dnn.py` |
| 核心实现 B | `est_core_nist_cpp_recode/ea/` | 按 NIST C++ v1.1.8 参考实现重写，包含 IID、Non-IID、Restart 和 Conditioning |
| 命令行 | `est_test/`、`est_test_nist_cpp_recode/`、实现 B 的 `cli/` | 评估入口输出日志及 JSON 汇总；数据预处理入口生成二进制文件 |
| 桌面应用 | `est_test_x_vue3_pywebview/` | Vue 3 → pywebview `Api` → 两套 runner；评估任务在子进程内运行 |
| Web 服务 | `est_web_fastapi/` | 两套路由分别调用两套核心；请求中的 Base64 数据转为临时二进制文件 |
| 开发工具 | `est_test_nist_cpp_recode/` 下四个校验/基准脚本 | 回归验证与性能测量，不是应用的运行依赖 |

实现 B 的 Non-IID 流程包含标准 §6.3 的十个估计器；`_io.py` 负责读取与符号映射，
`_lrs.py` 负责后缀数组与 t-Tuple / LRS，`_parallel.py` 负责进程调度，`_jit.py` 提供可选 numba 加速。
桌面和 Web 均可调用两套实现，但不能用一套实现的回归结果代替另一套的验收。

```text
z_est_python/
├── est_core/                     # 原版核心算法
├── est_core_nist_cpp_recode/
│   ├── ea/                       # 重写版算法库
│   └── cli/                      # 评估与数据预处理入口
├── est_test/                     # 原版统一命令行入口
├── est_test_nist_cpp_recode/      # 重写版命令行入口及开发工具
├── est_test_x_vue3_pywebview/     # Windows 桌面应用及前端构建
├── est_web_fastapi/              # Web 服务
├── 8ckup/                        # 本地 C++ 源码、样本与 refdata（不入库）
├── data/                         # 本地输入与结果（仅 .gitkeep 入库）
├── docs/                         # 设计方案与优化记录（部分已跟踪，其余默认忽略）
├── release/                      # 发布产物（不入库）
├── requirements.txt              # 各入口和构建工具的全量锁定依赖
└── Makefile                      # 运行、开发校验、构建与清理入口
```

## 2. 环境

建议使用 Python 3.12。现有 Makefile 优先探测
`C:/Tools/miniconda3/envs/z_est_env_python/python.exe`，路径不存在时使用 PATH 上的 `python`；
可通过 `PYTHON=` 覆盖，根 Makefile 会将选择传给桌面子 Makefile。不要假定 PATH 上的解释器已安装项目依赖。

```bash
conda activate z_est_env_python
python -m pip install -r requirements.txt
```

| 依赖 | 用途 |
|---|---|
| `numpy` | 重写版的数据处理、统计计算与数组算法 |
| `mpmath` | 重写版 Conditioning 的任意精度计算 |
| `scipy` | 重写版 χ² p-value；缺失时使用内置 Cephes 实现 |
| `numba` / `llvmlite` | 源码运行时可选的预测器加速；不可用时使用 Python 内核 |
| `tensorflow` / `keras` | 原版独立 DNN 入口，不用于常规 IID / Non-IID 主流程 |
| `fastapi` / `uvicorn` / `pydantic` | Web 服务 |
| `pywebview` / `pystray` / `pillow` | 桌面窗口与托盘 |
| `Nuitka` / `zstandard` | 桌面 onefile 构建与压缩 |

“可选”指核心算法存在回退路径；安装完整 `requirements.txt` 仍会安装这些锁定项。
使用 Make 目标需 GNU make；桌面开发与构建另需 Node.js / npm，桌面目标机需 WebView2 Runtime。

## 3. 快速开始

以下命令均从**仓库根目录**执行；先将待评估文件放到示例路径，或替换为实际路径：

```bash
make run_test_nist_cpp_recode TEST_ARGS="data/source.bin --non-iid -j 1"
make run_test TEST_ARGS="-f data/source.bin -b 8 --iid"
make run_test_x_vue3_pywebview       # 桌面开发模式，自动启动 Vite
make run_web_fastapi                # http://127.0.0.1:8888
```

两个命令行 Make 目标默认 `TEST_ARGS=--help`，不传参数时显示帮助。
`TEST_ARGS` 中的相对文件路径按仓库根目录解析；桌面应用通过界面选择文件，Web 服务通过页面或 API 接收数据。
完整参数见 [`est_test/README.md`](est_test/README.md) 与
[`est_test_nist_cpp_recode/README.md`](est_test_nist_cpp_recode/README.md)。

单独运行重写版环节时，先激活上述环境，再执行：

```bash
python est_core_nist_cpp_recode/cli/ea_non_iid.py data/source.bin -vv -j 1
python est_core_nist_cpp_recode/cli/ea_iid.py data/source.bin
python est_core_nist_cpp_recode/cli/ea_unpack_bits.py data/packed.bin -o data/unpacked.bin
```

## 4. 开发校验与基准

以下五个 Make 目标对应四个独立脚本。**它们对开发和交付验证有用，但不参与正常运行或 `build_all` 的依赖链，
当前桌面打包配置也不包含这些脚本。最终用户无需运行它们；不要仅因它们不在运行链上就删掉回归工具。**

| Make 目标 | 脚本 | 用途 |
|---|---|---|
| `refdata_diff` | `refdata_diff.py` | 三个短样本的 Non-IID 参考输出回归，相对容差 `1e-9` |
| `refdata_diff_all` | 同上，`--all --tol 1e-6` | 十一个参考样本的全量 Non-IID 回归 |
| `jit_crosscheck` | `jit_crosscheck.py` | 比较 Python / numba 预测器的原始计数，并确认内核实际编译 |
| `lrs_bench` | `lrs_bench.py` | 后缀数组、LCP 和熵值的计时与抽样指纹，辅助检查 `_lrs.py` 改动 |
| `job_bench` | `job_bench.py` | 主要估计器计时，定位热点；不包含轻量 MCV，`MAX` 不是端到端耗时 |

`refdata_diff` / `refdata_diff_all` 需要另行准备
`8ckup/NIST_SP800-90B_EntropyAssessment/bin/*.bin` 和
`8ckup/NIST_SP800-90B_EntropyAssessment/cpp/selftest/refdata/*.res`；
`jit_crosscheck` 需要这些样本及可用的 numba。`8ckup/` 不入库，普通克隆不会自动带上这些测试资源。
两个 benchmark 默认用 `truerand_4bit.bin`，也可传自己的数据文件：

```bash
make refdata_diff
make refdata_diff_all
make lrs_bench LRS_BENCH_SAMPLE=data/source.bin
make job_bench JOB_BENCH_SAMPLE=data/source.bin
make refdata_diff PYTHON=C:/path/to/python.exe
make help
```

全量比对保留 `--tol 1e-6`：C++ `long double` 与 Python `float` 的计算差异可能经预测器的 `-log2`
放大，在默认 `1e-9` 档下超容差。**该参数只改变参考输出的验收阈值，不改变算法、计算精度或最终熵值。**
具体比对范围与使用方法见重写版测试 README；它只检查 Non-IID 的 `Estimate:` 明细，不覆盖全部 JSON、IID、Restart 或 GUI。

## 5. 打包与清理

```bash
make build_all                                  # 当前仅构建 Windows amd64 桌面应用
make build_test_x_vue3_pywebview_windows_amd64    # 与 build_all 等价
make prepare                                    # 仅创建 release/；构建时自动执行
make clean                                      # 仅删除根目录的已发布 exe
```

构建使用 Nuitka onefile，输出为 `release/est_test_x_vue3_pywebview_windows_amd64.exe`。
根 `clean` 不清理桌面的中间目录；需要时执行 `make -C est_test_x_vue3_pywebview clean`。
构建不会自动运行参考回归或产物自检；完整构建配置与已知限制见
[`est_test_x_vue3_pywebview/README.md`](est_test_x_vue3_pywebview/README.md)。

GUI 产物没有控制台；在仓库根目录用 PowerShell 等待自检结束，并读取日志及退出码：

```powershell
$process = Start-Process -FilePath ".\release\est_test_x_vue3_pywebview_windows_amd64.exe" `
    -ArgumentList '--selftest', '--selftest-log', 'selftest.log' -Wait -PassThru
$process.ExitCode    # 0 = 自检通过
Get-Content selftest.log
```

`--selftest` 通过与前端相同的 `Api` 运行重写版 IID / Non-IID，并检查打包的 `dist/index.html`。
它不验证 GUI 渲染或全部统计边界；`--selftest-all` 额外覆盖原版引擎。

## 6. 数据文件格式

- 必须为二进制文件，**每个 1～8 位样本单独占一个字节**，有效值放在低位；1 位样本也不能直接按 bit 打包。
- 当前两套核心读取器都按字节处理，**不支持把两个连续字节解析成一个 9～16 位样本**。
- 按 bit 打包的数据先用 `est_core_nist_cpp_recode/cli/ea_unpack_bits.py` 展开，输出为 MSB-first 的 `0x00` / `0x01` 字节。
- IID / Non-IID 建议不少于 **1,000,000** 个连续样本；Restart 要求恰好 **1,000,000** 个样本，按 1000 次重启、每次 1000 个样本排列。

## 7. 开发注意事项

- 当前桌面构建排除 numba / llvmlite，所以 JIT 优化的收益不能直接当作发布 exe 的收益。
- `main.py` 已有 Nuitka 冻结态识别，但 `ea/_parallel.py` 的 `frozen()` 仍只检查 `sys` 信号；其并发/JIT 守卫并未完成同样的修复。
- FastAPI 路由仍通过进程级 `redirect_stdout` 捕获日志，并发请求存在日志互相干扰的风险；不应将开发服务器视作已验证的并发部署方案。

设计与后续优化记录见 [`docs/NIST SP800-90B EntropyAssessment Python 重写方案.md`](docs/NIST%20SP800-90B%20EntropyAssessment%20Python%20重写方案.md)
和 [`docs/优化候选清单与资源预算.md`](docs/优化候选清单与资源预算.md)。方案、历史测量与待办不等于当前实现或本次验收结果，修改算法时仍需重新验证。
