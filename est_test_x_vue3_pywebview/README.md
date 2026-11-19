# EST Test X Windows 应用

Vue 3 + pywebview 桌面外壳，将 `est_core` 原版和 `est_core_nist_cpp_recode` 重写版
两套熵评估实现打包为 Windows amd64 单文件 exe。

## 1. 组成

```text
est_test_x_vue3_pywebview/
├── main.py                     # 窗口、托盘、开发模式与产物自检
├── backend/
│   ├── api.py                  # window.pywebview.api.* 桥接
│   ├── config.py               # 版本、网络地址与窗口尺寸配置
│   ├── tray.py                 # 托盘、主题与语言菜单
│   ├── win32.py                # 图标、DPI 与原生窗口操作
│   ├── est_test_vue3_pywebview.py                # 原版 runner
│   └── est_test_nist_cpp_recode_vue3_pywebview.py # 重写版 runner
├── frontend/                   # Vue 3 + Vite，开发端口 3001
├── assets/                     # 窗口和托盘图标
├── tools/img2ico.py            # png → 多尺寸 ico
├── dist/                       # frontend/dist 的同步副本（不入库）
└── bin/                        # Nuitka 产物与中间目录（不入库）
```

前端通过 `Api` 选择 runner；每次评估在独立子进程中运行，退出后回收数据集和缓存内存。
runner 的核心库导入与 Makefile 中的 `PYTHONPATH` / `--include-package=ea` 是配套配置。
调整导入或打包方式后必须重新运行冻结产物的 `--selftest`，不能仅以编译成功判断依赖已收齐。

## 2. 运行前置

| 依赖 | 来源 | 说明 |
|---|---|---|
| Python | 建议 Python 3.12，依赖见根 `requirements.txt` | Make 优先探测 conda 环境路径，不存在时回退 PATH；可用 `PYTHON=` 覆盖 |
| Nuitka / zstandard | 同一 Python 环境 | onefile 构建及载荷压缩；版本以 `requirements.txt` 为准 |
| Node.js / npm | 本机安装 | 前端依赖安装与 Vite 构建 |
| GNU make | 如 MSYS2 提供的 make | 本目录 Makefile 的文件操作使用 Windows cmd 语法 |
| WebView2 Runtime | 目标 Windows 系统 | EdgeChromium GUI 运行需要，自检不会验证它 |

默认探测路径是 `C:/Tools/miniconda3/envs/z_est_env_python/python.exe`。
依赖安装见[根 README](../README.md#2-环境)；直接使用 `python` 前确认已激活正确环境。
部署 exe 不需要 Python、Node.js 或 make，但仍需满足 Windows GUI 的系统依赖。

## 3. 开发模式

```bash
# 在仓库根目录
make run_test_x_vue3_pywebview

# 或在本目录
make run_dev
```

`run_dev` 先安装前端依赖，再启动 `main.py --dev`；主程序自动启动 Vite dev server，前端改动可热更新。

## 4. 构建

```bash
# 在仓库根目录，构建完自动拷到 release/
make build_all

# 或在本目录，只产出 bin/
make build_windows_amd64
```

构建顺序：清理本目录 `bin/`、`dist/` → `prepare`（安装前端依赖、创建输出目录）→
`vite build` → 同步 `frontend/dist` → Nuitka `--standalone --onefile`。
清理与准备按顺序执行，避免 `make -j` 将二者并行导致输出目录被再次删除。

本目录产物是 `bin/est_test_x_vue3_pywebview.exe`；根构建另复制为
`release/est_test_x_vue3_pywebview_windows_amd64.exe`。构建器可能下载编译工具链，首次构建需网络。

- `make build_frontend`：只构建并同步前端，但同样会先清理本目录 `bin/`、`dist/`。
- `make clean`：只删除本目录 `bin/`、`dist/`；根 Makefile 的 `clean` 只删除发布 exe。
- 默认不传 `--show-progress`，避免当前 Nuitka 在重定向输出时出错；交互式控制台可显式设置
  `NUITKA_PROGRESS=--show-progress`。
- 构建不自动运行回归或 `--selftest`；产物大小、耗时和压缩效果取决于依赖及构建环境，不作为验收判据。

## 5. 验证产物

GUI 构建没有控制台，所以自检结果必须落文件。在仓库根目录使用 PowerShell 等待进程结束：

```powershell
$process = Start-Process -FilePath ".\release\est_test_x_vue3_pywebview_windows_amd64.exe" `
    -ArgumentList '--selftest', '--selftest-log', 'selftest.log' -Wait -PassThru
$process.ExitCode    # 0 = 自检覆盖项通过
Get-Content selftest.log
```

| 参数 | 作用 |
|---|---|
| `--selftest` | 不启动 GUI，默认经 `Api` 运行重写版 IID / Non-IID，并检查前端入口文件 |
| `--selftest-log <path>` | 将自检结果写入文件 |
| `--selftest-timeout <秒>` | 单项评估超时，默认 900 |
| `--selftest-all` | 配合 `--selftest` 额外覆盖原版 `est_core` 引擎 |

源码态可在本目录执行 `python main.py --selftest`，但会跳过冻结前端检查，不能替代 exe 自检。
样本优先使用本地 `8ckup/.../bin/rand4_short.bin`；不可用时在临时目录生成确定性合成数据。
日志中的 `dataset`、`frozen`、`signals` 和前端检查结果可用于判断实际测试了哪种环境。

## 6. Windows 构建排查

### 6.1 原生 DLL 缺失

未激活 conda 而直接调用其解释器时，`Library/bin` 可能不在 PATH，导致 Nuitka 遗漏原生 DLL。
这种故障可能发生在 Python traceback 之前。Makefile 的 `CONDA_DLL_FLAGS` 显式收集存在的下列 DLL：

| 扩展模块 | 对应 DLL |
|---|---|
| `_ctypes.pyd` / `_cffi_backend.pyd` | `ffi.dll` |
| `_tkinter.pyd` | `tcl86t.dll` / `tk86t.dll`；tk-inter 插件另收脚本库 |
| `_bz2.pyd` / `_lzma.pyd` / `pyexpat.pyd` | `libbz2.dll` / `liblzma.dll` / `libexpat.dll` |
| `_ssl.pyd` / `_hashlib.pyd` | `libssl-3-x64.dll` / `libcrypto-3-x64.dll` |

该目录从 `PYTHON` 的路径推导；更换解释器或 conda 版本后，应检查 DLL 路径、构建报告及产物自检。

### 6.2 安全软件隔离

onefile 的自解压行为可能触发启发式检测。若构建后产物消失，或启动时未生成自检日志，先查看
Windows 安全中心的保护历史与隔离记录，同时核对构建来源和报告，不能将报警一概认定为误报。
确认可信后按组织安全策略复核或提交误报；不要默认关闭 Defender 或对整个临时目录、所有 onefile 载荷作宽泛排除。

## 7. 打包取舍

- **排除 numba / llvmlite**：通过 `--noinclude-numba-mode=nofollow` 和 `--nofollow-import-to` 控制体积及原生依赖。
  发布 exe 使用 Python 内核；源码态的 JIT 性能不能直接套用到 exe。
- **保留 scipy**：重写版 χ² p-value 使用 `gammaincc`；算法虽有内置回退，当前构建仍保留 scipy。
- **排除 tensorflow / keras**：DNN 使用原版独立入口，桌面两套 runner 均不调用它。
- **排除 markov_chain_generate**：该模块导入即写文件，不应进入应用的导入链。
- **不打包开发工具**：根 Makefile、README、`8ckup/` 与四个校验/基准脚本不属于运行依赖。
  `main.py` 内置的 `--selftest` 则保留在 exe 中，用于验证实际发布产物。

## 8. 已知限制

- **自检范围有限**：不覆盖 Restart、全部统计边界或 JS/CSS 资产完整性；前端项只检查 `dist/index.html`。
- **GUI 仍需人工验证**：窗口、托盘、渲染及 WebView2 Runtime 可用性不在无头自检范围内。
- **用户数据目录需可写**：当前 WebView2 用户数据写在 exe 旁，放到只读目录可能导致初始化失败；
  若需安装到只读位置，应先配置可写的 `user_data_dir`。
- **核心冻结态检测仍有缺口**：`main.py` 已识别 Nuitka 的 builtins / 模块信号，但 `ea/_parallel.py`
  的 `frozen()` 仍只检查 `sys.frozen` / `sys.__compiled__`，可能错误选择自动 worker 数或绕过 JIT 冻结态守卫。
  numba 未被打包后的导入回退不等于检测逻辑已修复；修改这处需重新验证并发与产物行为。
