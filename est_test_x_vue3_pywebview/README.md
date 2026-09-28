# EST Test X Windows 应用

Vue 3 + pywebview 桌面外壳，把仓库里两条熵评估实现（`est_core` 纯 Python 原版、
`est_core_nist_cpp_recode` C++ 逐函数重写版）包成一个免安装的 Windows 单文件 exe。

---

## 1. 组成

```
est_test_x_vue3_pywebview/
├── main.py                     # 入口：建窗口、起托盘、--dev / --selftest 分支
├── backend/
│   ├── api.py                  # pywebview JS-API 桥（window.pywebview.api.*）
│   ├── config.py               # 配置常量单一来源（版本/路径/网络/UI 尺寸），main 与 api 共用
│   ├── tray.py                 # pystray 托盘：生命周期、i18n 菜单、主题/语言切换
│   ├── win32.py                # ctypes Win32：窗口图标、DPI 检测、暗色标题栏、HWND 查找
│   ├── est_test_vue3_pywebview.py              # runner A：驱动 est_core
│   └── est_test_nist_cpp_recode_vue3_pywebview.py  # runner B：驱动 est_core_nist_cpp_recode
├── frontend/                   # Vue 3.3 + Vite 5.4 前端源码（dev server 端口 3001）
├── assets/                     # app_logo.ico / app_logo.png（exe 图标与托盘图）
├── tools/img2ico.py            # png → 多尺寸 ico
├── dist/                       # 前端构建产物同步落点（不入库，构建时由 frontend/dist 拷入）
└── bin/                        # Nuitka 输出：main.build / main.dist / main.onefile-build（不入库）
```

**每次评估都跑在子进程里**：Windows 上 `gc.collect()` 归还不掉内存（CPython 的 pymalloc
会攥着已释放的块），只有子进程退出才能让 OS 真正回收数据集数组与缓存。

> ⚠️ 两个 runner 里对 `ea` / `est_core` 的 import **必须留在模块顶层**。Nuitka 的
> standalone 分析只跟随顶层 import；写进函数里的话，这些模块连同 numpy / scipy /
> mpmath 全都不会进产物，exe 构建照样"成功"、一跑就挂。

---

## 2. 运行前置

| 依赖 | 来源 | 说明 |
|---|---|---|
| Python 3.12 | conda 环境 `z_est_env_python` | `C:\Tools\miniconda3\envs\z_est_env_python`；两份 Makefile 已绑定 |
| Nuitka 4.0.8 | 同上 conda 环境 | 构建器；会**忽略 msys64 的 gcc**，自行下载 winlibs gcc 14.2.0 |
| node / npm | nvm | 前端构建（`npm install` + `vite build`） |
| make | `C:\Tools\msys64\mingw64\bin\make.exe` | Windows 分支走 cmd 语法 |

**PATH 上的 `python` 不是这个 conda 环境**，而是 msys64 的
`C:\Tools\msys64\mingw64\bin\python.exe`（没 numpy 也没 nuitka）。直接 `python main.py`
会 `ModuleNotFoundError`。走 `make` 目标即可，或先 `conda activate z_est_env_python`。

---

## 3. 开发模式

```bash
# 在仓库根目录
make run_test_x_vue3_pywebview

# 或在本目录（等价）
make run_dev
```

`run_dev` 会先 `npm install`，再以 `main.py --dev` 启动：窗口指向 Vite dev server
（端口 3001），前端改动热更新。

---

## 4. 构建

```bash
# 在仓库根目录（推荐：构建完自动拷到 release/）
make build_all

# 或在本目录（只产出 bin/，不拷 release/）
make build_windows_amd64
```

流水线：`clean`（删 `bin/`、`dist/`）→ `prepare`（`npm install`）→ `vite build` →
同步 `frontend/dist` 到 `dist/` → Nuitka `--standalone --onefile` → 拷到
`release/est_test_x_vue3_pywebview_windows_amd64.exe`。

- 产物 **46.77 MiB**（实测 49,050,112 B）；775 个 C 文件；`bin/main.dist` 展开后 232 MiB
- payload 压缩靠 `zstandard`：没装只会在开头提一句 `Onefile mode cannot compress` 然后照样构建成功
  （产物大不少），装上后走 `Using compression`。当前环境已装
- 耗时：ccache 冷启约 9 min（含首次下载 winlibs gcc），热启约 6 min
- 想看进度：`make build_windows_amd64 NUITKA_PROGRESS=--show-progress`
  （默认不带——stdout 被重定向时该选项会让 Nuitka 抛 `OSError[Errno 22]` 静默中止）

---

## 5. 验证产物

GUI 构建没有控制台，所以自检结果必须落文件：

```powershell
release\est_test_x_vue3_pywebview_windows_amd64.exe --selftest --selftest-log selftest.log
echo $LASTEXITCODE      # 0 = 全部通过
```

| 参数 | 作用 |
|---|---|
| `--selftest` | 无头跑一遍真实评估后退出，**0 = 通过** |
| `--selftest-log <path>` | 结果写文件而非 stdout（`--windows-console-mode=disable` 构建没有 stdout） |
| `--selftest-timeout <秒>` | 单条 leg 的超时，默认 900 |
| `--selftest-all` | 额外覆盖慢的纯 Python `est_core` 引擎（默认只跑 nist_cpp_recode） |

自检走**前端同一个 `Api`**，真跑一次 IID + 一次 Non-IID，用退出码回答"冻结产物到底有没有
把分析库打进去"。数据集优先用仓库里的 `8ckup/.../bin/rand4_short.bin`（10000 个 4-bit
符号）；冻结产物旁边没有仓库时，自动在 `%TEMP%` 生成确定性合成样本（seed `0x5EED`）。

当前基线（冻结产物 `release\...exe --selftest`，实测 7.4 s / 退出码 0）：

```
dataset: %TEMP%\est_selftest_rand4.bin
frozen:  True
signals: builtins.__nuitka_binary_dir, module.__compiled__
paths:   resource_base=%TEMP%\ONEFIL~1\
PASS  nist/iid     min_entropy=3.759097
PASS  nist/noniid  min_entropy=2.714157
PASS  frontend     %TEMP%\ONEFIL~1\dist
SELFTEST PASS (3/3 checks)
```

源码态跑（`python main.py --selftest`）则是 `frozen: False` + `SKIP frontend`，且数据集换成
仓库里的 `rand4_short.bin`，熵值随之不同（3.790037 / 3.215488）——两边都对，差别只来自样本。

---

## 6. Windows 构建陷阱（都踩过）

### 6.1 缺 Anaconda 原生 DLL → 启动即崩

用绝对路径调 `python -m nuitka`（**没有** `conda activate`）时，env 的 `Library\bin`
不在 PATH 上，Nuitka 的依赖扫描就找不到那里的原生 DLL，它们不会进产物。冻结后一旦加载
依赖这些 DLL 的扩展模块，`LoadLibrary` 解析失败即 native abort——异常码
`0x40000015`（`STATUS_FATAL_APP_EXIT`）、退出码 3，**早于任何 Python traceback**，
`faulthandler` 也抓不到，GUI 构建连 stderr 都是空的。

实测缺 8 个，已在 Makefile 里用 `CONDA_DLL_FLAGS` 逐个 `wildcard` 守卫后显式打包：

| 扩展模块 | 缺的 DLL |
|---|---|
| `_ctypes.pyd` / `_cffi_backend.pyd` | `ffi.dll` ← `main.py` 顶层 `import ctypes`，**最先崩** |
| `_tkinter.pyd` | `tcl86t.dll` / `tk86t.dll`（`--enable-plugin=tk-inter` 另收 89 Tk + 837 Tcl 脚本文件） |
| `_bz2.pyd` / `_lzma.pyd` / `pyexpat.pyd` | `libbz2.dll` / `liblzma.dll` / `libexpat.dll` |
| `_ssl.pyd` / `_hashlib.pyd` | `libssl-3-x64.dll` / `libcrypto-3-x64.dll` |

定位手法：`PYTHONVERBOSE=1` 让内嵌 CPython 打印每个 import，abort 前最后一行就是失败模块。

### 6.2 Defender 把产物当病毒删掉

Nuitka onefile 的自解压引导会被 Windows Defender 的机器学习启发式判成
**`Program:Win32/Wacapew.A!ml`**（`.A!ml` 后缀即 ML 误报），构建完几秒内 exe 就被隔离，
表现为"`make build_all` 明明成功了，`release/` 却是空的"。

ML 评分按**哈希**，所以每次改代码重新构建都可能换一个家族重新触发。实测到两个：
`Wacapew.A!ml` 打构建产物 exe（就是上面那句“`release/` 却是空的”），`Contebrew.A!ml`
打运行时解压出的 `%TEMP%\onefile_<pid>_<ticks>\main.dll`——exe 好端端在着，但一跑就
退出码 2，`--selftest-log` 一个字都没写。

需在**管理员 PowerShell** 里加三条路径排除（两个产物目录 + onefile 每次运行必然落盘的
自解压目录）再加一条进程名排除：

```powershell
# $env:TEMP 在部分账户下返回 8.3 短名（C:\Users\XXX~1\...），而 Defender 按字面串匹配、
# 上报时用的却是长名——短名条目覆盖不到任何资源，必须先解析成长路径。
$onefile = Join-Path ([IO.Path]::GetFullPath($env:TEMP)) 'onefile_*'
Add-MpPreference -ExclusionPath '<repo>\release','<repo>\est_test_x_vue3_pywebview\bin',$onefile `
                 -ExclusionProcess 'est_test_x_vue3_pywebview.exe'
```

只加进程名排除**不够**：实测 `main.dll` 仍被删（`CleaningActionID=3` = Remove），只是删在
DLL 已映射进内存之后，于是“碰巧”跑通了——时序侥幸，不能依赖。

这是**本机设置、不进仓库**，换机或 Defender 重置后要重加。查历史隔离用
`Get-MpThreatDetection`，查当前排除项用 `Get-MpPreference`（需管理员）。

---

## 7. 打包取舍

- **排除 numba / llvmlite**（`--noinclude-numba-mode=nofollow` + `--nofollow-import-to`）：
  `ea._jit` 的 `from numba import njit` 是函数内延迟导入且被 `frozen()` 守卫，冻结态永远走
  纯 Python 孪生内核、结果逐位相同；但静态分析仍会把整棵 numba + llvmlite（上百 MB 原生
  LLVM）编进来，Nuitka 官方也警告 numba 在 standalone 下 "not yet fully working"。
  排除后产物 **87.5 → 46.77 MiB**，编译省十几分钟。
- **保留 scipy**：只有 `ea/chi_square.py` 用 `gammaincc`，缺失时会回退到内置 Cephes
  `igamc`（数值等价），所以它可排可不排；当前保留。
- **nofollow `tensorflow` / `keras`**：只有 `est_core/main_dnn.py` 的 DNN 预测器需要，桌面应用的
  两个 runner 都不走那条路。本机**已装**（TF+keras 约 1,394 MiB），所以排除它纯粹是为了产物体积
  与启动时间——真被静态分析跟进去的话 onefile 会膨胀到几百 MiB 量级，且导入本身要 +2–4 s。
  这条与 `docs/优化候选清单与资源预算.md` §4-C 的「DNN 只应挂独立入口、绝不进主路径」是同一个判断。
- **nofollow `markov_chain_generate`**：该模块没有 `__main__` 守卫，import 即写文件。

---

## 8. 已知限制

- **自检覆盖面**：默认只跑 `nist_cpp_recode` 引擎，`--selftest-all` 才带上慢的纯 Python
  `est_core`；`frontend` 一项只验 `dist/index.html` 在不在，不校验 JS/CSS 资产完整性。
- **自检不启动 GUI**：pywebview 窗口、托盘、渲染一概不碰，所以目标机缺 WebView2 Runtime
  这类问题它测不出来。Nuitka 构建时也明确告警 `Cannot find Windows Runtime DLLs to
  include, requiring them to be installed on target systems`。本机手动跑过 GUI（`release/` 下
  留有 WebView2 用户数据目录），但那是人工验证，不在自检的退出码里。
- **exe 把 WebView2 用户数据写在自身旁边**：跑过 GUI 后 `release/` 里会多出
  `est_test_x_vue3_pywebview_windows_amd64.exe.WebView2\EBWebView\...`（含 `Default` 配置、
  `GPUPersistentCache` / `ShaderCache` / `Crashpad`）。`release/` 已被 `.gitignore` 覆盖，不污染仓库；
  但这意味着**产物不能放进只读目录**（如 `Program Files`）——那里建不出这个目录，WebView2 初始化会失败。
  要装到只读位置得先给 pywebview 显式指定一个可写的 `user_data_dir`。
- **`ea/_parallel.py` 的 `frozen()` 对 Nuitka 失效（截至 `4d3e1bd` 仍未修）**：它判的是 `sys.frozen` 或
  `sys.__compiled__`，而 Nuitka 两者都不设——上面 `signals:` 那行实测只命中
  `builtins.__nuitka_binary_dir` 与模块级 `__compiled__`。后果是冻结产物里 `auto_workers()`
  仍返回多进程数、`_jit` 的 numba 守卫也不生效（靠 numba 未被打包后 import 失败再回退兜底，
  结果仍逐位正确）。修它会改变并发度、属于功能变更，故 `4d3e1bd` 只修了 `main.py` 的
  `is_frozen()`（四信号 or 链，已改用正确的多信号判定），`ea/_parallel.py` 这一处原样留着。
  注意别把两者的修复状态搞混：`main.py` 已修，`ea/_parallel.py` 未修。
