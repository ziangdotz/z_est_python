FIX_PATH = $(subst /,\,$(1))
RM = if exist $(call FIX_PATH, $(1)) rd /s /q $(call FIX_PATH, $(1))
MD = if not exist $(call FIX_PATH, $(1)) mkdir $(call FIX_PATH, $(1))
CP = xcopy /s /e /i /y

# 独立调用时与根 Makefile 使用同一解释器探测规则；上级可通过 PYTHON= 覆盖。
CONDA_ENV_PYTHON = C:/Tools/miniconda3/envs/z_est_env_python/python.exe
CONDA_ENV_PYTHON_FOUND = $(wildcard $(CONDA_ENV_PYTHON))
ifneq ($(CONDA_ENV_PYTHON_FOUND),)
DEFAULT_PYTHON = $(CONDA_ENV_PYTHON)
else
DEFAULT_PYTHON = python
endif

PYTHON ?= $(DEFAULT_PYTHON)

RESOURCES_DIR := dist
BUILD_DIR := bin

FRONTEND_DIR = frontend
FRONTENDDIST_DIR = $(FRONTEND_DIR)/dist

APPNAME := est_test_x_vue3_pywebview
APPLOGO_TRAY_IMG := assets/app_logo.png
APPLOGO_ICON := assets/app_logo.ico

MAIN := main.py

# Nuitka 编译期需要通过 PYTHONPATH 定位两套核心库，不能只依赖运行时 sys.path。
ifeq ($(OS),Windows_NT)
PATH_SEP := ;
else
PATH_SEP := :
endif
EST_CORE_DIR := $(abspath ../est_core)
EST_CORE_RECODE_DIR := $(abspath ../est_core_nist_cpp_recode)
export PYTHONPATH := $(EST_CORE_DIR)$(PATH_SEP)$(EST_CORE_RECODE_DIR)

# 默认关闭进度，避免 Nuitka 在输出重定向时出错；交互式控制台可覆盖 NUITKA_PROGRESS。
NUITKA_PROGRESS :=

# 未激活 conda 时依赖扫描可能遗漏 Library/bin 中的 DLL，存在的文件需显式打包。
# tk-inter 插件另收 Tcl/Tk 脚本库；DLL 对应关系见 README.md。
PYTHON_HOME := $(patsubst %/,%,$(dir $(PYTHON)))
CONDA_LIBRARY_BIN := $(PYTHON_HOME)/Library/bin
CONDA_NATIVE_DLLS := tcl86t.dll tk86t.dll ffi.dll libbz2.dll liblzma.dll libexpat.dll libssl-3-x64.dll libcrypto-3-x64.dll
CONDA_DLL_FLAGS := $(foreach d,$(wildcard $(addprefix $(CONDA_LIBRARY_BIN)/,$(CONDA_NATIVE_DLLS))),--include-data-files=$(d)=$(notdir $(d)))

# 冻结产物排除 numba/llvmlite，导入不可用时回退到 Python 内核。
# 当前 frozen() 对 Nuitka 的检测有缺口，不能只依赖该守卫；见 README.md 的已知限制。
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
	@$(call MD, $(RESOURCES_DIR))
	@$(call MD, $(BUILD_DIR))

run_dev: prepare
	@"$(PYTHON)" $(MAIN) --dev

build_frontend: clean
	+@$(MAKE) prepare
	@echo "Build started: frontend..."
	@cd $(FRONTEND_DIR) && npm run build
	@echo "Frontend build completed."
	@echo "Syncing dist..."
	@$(CP) $(call FIX_PATH, $(FRONTENDDIST_DIR)) $(call FIX_PATH, $(RESOURCES_DIR))
	@echo "Syncing completed."

build_windows_amd64: build_frontend
	@echo "Build started: Windows amd64 version..."
	@$(PY_NUITKA_PACKAGE) $(MAIN)
	@echo "Build completed."

build_all: build_windows_amd64

clean:
	$(call RM, $(RESOURCES_DIR))
	$(call RM, $(BUILD_DIR))

help:
	@echo ------------------------
	@echo "make prepare:             install frontend dependencies and create output directories"
	@echo "make run_dev:             desktop development mode"
	@echo "make build_frontend:      clean outputs, build frontend and sync dist"
	@echo "make build_windows_amd64: build -- Windows amd64 version"
	@echo "make build_all:           desktop build alias"
	@echo "make clean:               remove local bin/ and dist/ outputs"
	@echo "make help:                see custom commands"
	@echo "make:                     like 'make help'"
	@echo ------------------------
	@echo "PYTHON: interpreter used for nuitka / run_dev (default: conda env z_est_env_python, else python on PATH)"
	@echo "NUITKA_PROGRESS: extra nuitka flags, e.g. NUITKA_PROGRESS=--show-progress (only safe in an interactive console)"
