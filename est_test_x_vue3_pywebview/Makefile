FIX_PATH = $(subst /,\,$(1))
RM = if exist $(call FIX_PATH, $(1)) rd /s /q $(call FIX_PATH, $(1))
RF = if exist $(call FIX_PATH, $(1)) del /f /q $(call FIX_PATH, $(1))
MD = if not exist $(call FIX_PATH, $(1)) mkdir $(call FIX_PATH, $(1))
CP = xcopy /s /e /i /y
# UPX_PATH := $(shell where upx 2>nul)

# Python 解释器。与根 Makefile 同一套规则：默认用 conda 环境 z_est_env_python（构建
# 依赖 Nuitka / pywebview 只装在那里），该路径不存在时回退 PATH 上的 python。
# 从仓库根目录调时（make build_test_x_vue3_pywebview_windows_amd64）解释器由上级
# 通过 PYTHON= 传下来，命令行变量优先于下面的 ?=。
CONDA_ENV_PYTHON = C:/Tools/miniconda3/envs/z_est_env_python/python.exe
CONDA_ENV_PYTHON_FOUND = $(wildcard $(CONDA_ENV_PYTHON))
ifneq ($(CONDA_ENV_PYTHON_FOUND),)
DEFAULT_PYTHON = $(CONDA_ENV_PYTHON)
else
DEFAULT_PYTHON = python
endif

PYTHON ?= $(DEFAULT_PYTHON)

# ifdef UPX_PATH
# define compress
# 	@echo ">> 正在压缩 $(1) 并生成带 _upx 后缀的文件..."
# 	@if exist $(call FIX_PATH, $(1)) copy $(call FIX_PATH, $(1)) $(call FIX_PATH, $(patsubst %.exe,%_upx.exe,$(1))) >nul 2>&1 || cp $(1) $(1)_upx
# 	@upx --best --lzma $(call FIX_PATH, $(patsubst %.exe,%_upx.exe,$(1))) 2>nul || upx --best --lzma $(1)_upx 2>/dev/null || true
# endef
# else
# define compress
# 	@echo ">> 跳过压缩: 系统未安装 UPX"
# endef
# endif


RESOURCES_DIR := dist
BUILD_DIR := bin

FRONTEND_DIR = frontend
FRONTENDDIST_DIR = $(FRONTEND_DIR)/dist

APPNAME := est_test_x_vue3_pywebview
APPLOGO_TRAY_IMG := assets/app_logo.png
APPLOGO_ICON := assets/app_logo.ico

MAIN := main.py

# 两个核心库的路径。runner 里的 `from ea.xxx import ...` 与 est_core 散模块在运行时
# 靠顶层 sys.path.insert 生效，但 Nuitka 编译期不执行这段代码，看不到这些注入，
# 所以用 PYTHONPATH 把同样的路径喂给它，否则 ea / est_core 连同 numpy 依旧不会进产物。
ifeq ($(OS),Windows_NT)
PATH_SEP := ;
else
PATH_SEP := :
endif
EST_CORE_DIR := $(abspath ../est_core)
EST_CORE_RECODE_DIR := $(abspath ../est_core_nist_cpp_recode)
export PYTHONPATH := $(EST_CORE_DIR)$(PATH_SEP)$(EST_CORE_RECODE_DIR)

# --show-progress 在 Nuitka 4.0.8 里已标记 Obsolete，而且 stdout 被重定向时（后台
# 构建 / CI）会在 Tracing._printFormatted 抛 OSError[Errno 22] 让构建静默中止，
# 所以默认不带。本地想看进度：make build_windows_amd64 NUITKA_PROGRESS=--show-progress
NUITKA_PROGRESS :=

# Anaconda 的原生运行时 DLL。用绝对路径调 `python -m nuitka`（未 conda activate）时，env
# 的 Library/bin 不在 PATH 上，Nuitka 的依赖扫描就找不到该目录里的原生 DLL，它们不会进
# 产物；冻结后一旦加载依赖这些 DLL 的扩展模块（.pyd），LoadLibrary 解析失败即 native
# abort（异常码 0x40000015 STATUS_FATAL_APP_EXIT，exe 启动即崩，且早于任何 Python
# traceback，faulthandler 也抓不到）。PYTHONVERBOSE 跟踪定位到实测缺失的有：
#   _ctypes.pyd / _cffi_backend.pyd -> ffi.dll        （main.py 顶层 import ctypes，最先崩）
#   _tkinter.pyd                    -> tcl86t.dll / tk86t.dll （api.py 顶层 import tkinter）
#   _bz2.pyd -> libbz2.dll；_lzma.pyd -> liblzma.dll；pyexpat.pyd -> libexpat.dll
#   _ssl.pyd / _hashlib.pyd -> libssl-3-x64.dll / libcrypto-3-x64.dll
# 从实际解释器推出 env 根，把上述 DLL 逐个 wildcard 守卫后显式打进产物根目录（与对应 .pyd
# 同级，其 DLL 搜索能命中）；某个 DLL 不存在时（例如回退到 PATH 上的非 conda python）自动
# 跳过，不让构建失败。tk-inter 插件另收 Tcl/Tk 的脚本库（tcl8.6/tk8.6），与此处 DLL 互补。
PYTHON_HOME := $(patsubst %/,%,$(dir $(PYTHON)))
CONDA_LIBRARY_BIN := $(PYTHON_HOME)/Library/bin
CONDA_NATIVE_DLLS := tcl86t.dll tk86t.dll ffi.dll libbz2.dll liblzma.dll libexpat.dll libssl-3-x64.dll libcrypto-3-x64.dll
CONDA_DLL_FLAGS := $(foreach d,$(wildcard $(addprefix $(CONDA_LIBRARY_BIN)/,$(CONDA_NATIVE_DLLS))),--include-data-files=$(d)=$(notdir $(d)))

# numba/llvmlite 排除。ea._jit 里 `from numba import njit` 是函数内延迟导入，且被
# frozen() 守卫——冻结产物运行时永远走纯 Python 孪生内核，根本不会 import numba。
# 但 Nuitka 的静态分析仍会把整棵 numba + llvmlite 依赖树编进产物：llvmlite 带着上百 MB
# 的原生 LLVM 库，Nuitka 官方明确警告 numba “not yet fully working with standalone”，
# 是启动即 native abort（STATUS_FATAL_APP_EXIT）的头号嫌疑，还让编译慢上十几分钟。
# 用 nanny 推荐的 --noinclude-numba-mode=nofollow 关掉 numba，并把 numba/llvmlite 一并
# 加进 --nofollow-import-to 兜底；运行时那句 import 落到 try/except 里退化为无 JIT，安全。
NUITKA_FLAGS := --standalone \
				--onefile \
				--windows-console-mode=disable \
				--assume-yes-for-downloads \
				--windows-icon-from-ico=$(APPLOGO_ICON) --enable-plugin=tk-inter \
				--include-data-dir=$(RESOURCES_DIR)=$(RESOURCES_DIR) \
				--include-data-files=$(APPLOGO_TRAY_IMG)=$(APPLOGO_TRAY_IMG) \
				--include-data-files=$(APPLOGO_ICON)=$(APPLOGO_ICON) $(CONDA_DLL_FLAGS) \
				--include-package=ea \
				--nofollow-import-to=tensorflow,keras,markov_chain_generate,numba,llvmlite \
				--noinclude-numba-mode=nofollow \
				$(NUITKA_PROGRESS) \
				--output-dir=$(BUILD_DIR) \
				--output-filename=$(APPNAME).exe
PY_NUITKA_PACKAGE := "$(PYTHON)" -m nuitka $(NUITKA_FLAGS)

all: help

.PHONY: all prepare run_dev build_frontend build_windows_amd64 build_all clean help

prepare:
	@cd $(FRONTEND_DIR) && npm install
# 	@"$(PYTHON)" -m pip install -r ../requirements.txt
	@$(call MD, $(RESOURCES_DIR))
	@$(call MD, $(BUILD_DIR))

run_dev: prepare
	@"$(PYTHON)" $(MAIN) --dev

build_frontend: clean prepare
	@echo "Build started: frontend..."
	@cd $(FRONTEND_DIR) && npm run build
	@echo "Frontend build completed."
	@echo "Syncing dist..."
	@$(CP) $(call FIX_PATH, $(FRONTENDDIST_DIR)) $(call FIX_PATH, $(RESOURCES_DIR))
	@echo "Syncing completed."

build_windows_amd64: build_frontend
	@echo "Build started: Windows amd64 version..."
	@$(PY_NUITKA_PACKAGE) $(MAIN)
# 	$(call compress, $(BUILD_DIR)/$(APPNAME).exe)
	@echo "Build completed."

build_all: build_windows_amd64

clean:
	$(call RM, $(RESOURCES_DIR))
	$(call RM, $(BUILD_DIR))

help:
	@echo ------------------------
	@echo "make run_dev:             run"
	@echo "make build_windows_amd64: build -- Windows amd64 version"
	@echo "make build_all:           build all works"
	@echo "make clean:               clean middle files"
	@echo "make help:                see custom commands"
	@echo "make:                     like 'make help'"
	@echo ------------------------
	@echo "PYTHON: interpreter used for nuitka / run_dev (default: conda env z_est_env_python, else python on PATH)"
	@echo "NUITKA_PROGRESS: extra nuitka flags, e.g. NUITKA_PROGRESS=--show-progress (only safe in an interactive console)"

