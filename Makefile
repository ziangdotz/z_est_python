ifeq ($(OS), Windows_NT)
	FIX_PATH = $(subst /,\,$(1))
	RF = if exist $(call FIX_PATH, $(1)) del /f /q $(call FIX_PATH, $(1))
	MD = if not exist $(call FIX_PATH, $(1)) mkdir $(call FIX_PATH, $(1))
	CP_FILE = copy /Y $(call FIX_PATH, $(1)) $(call FIX_PATH, $(2))
else
	FIX_PATH = $(1)
	RF = rm -f $(1)
	MD = mkdir -p $(1)
	CP_FILE = cp $(1) $(2)
endif

CONDA_ENV_PYTHON = C:/Tools/miniconda3/envs/z_est_env_python/python.exe
CONDA_ENV_PYTHON_FOUND = $(wildcard $(CONDA_ENV_PYTHON))
ifneq ($(CONDA_ENV_PYTHON_FOUND),)
DEFAULT_PYTHON = $(CONDA_ENV_PYTHON)
else
DEFAULT_PYTHON = python
endif

PYTHON ?= $(DEFAULT_PYTHON)
MAKE_PYTHON = $(MAKE) PYTHON="$(PYTHON)"

WEB_CODE_PATH = ./est_web_fastapi
WEB_MAIN = run.py
TEST_CODE_PATH = ./est_test
TEST_MAIN = est_test.py
TEST_MAIN_PATH = $(TEST_CODE_PATH)/$(TEST_MAIN)
TEST_NIST_CPP_RECODE_CODE_PATH = ./est_test_nist_cpp_recode
TEST_NIST_CPP_RECODE_MAIN = est_test_nist_cpp_recode.py
TEST_NIST_CPP_RECODE_MAIN_PATH = $(TEST_NIST_CPP_RECODE_CODE_PATH)/$(TEST_NIST_CPP_RECODE_MAIN)
TEST_ARGS ?= --help
LRS_BENCH_SAMPLE = 8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
JOB_BENCH_SAMPLE = 8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
TEST_X_VUE3_PYWEBVIEW_CODE_PATH = ./est_test_x_vue3_pywebview
# 与桌面子 Makefile 的输出目录和文件名保持一致。
TEST_X_VUE3_PYWEBVIEW_BUILD_DIR = $(TEST_X_VUE3_PYWEBVIEW_CODE_PATH)/bin
TEST_X_VUE3_PYWEBVIEW_APPNAME = est_test_x_vue3_pywebview.exe

BUILDDIR = release

RELEASE_EST_TEST_X_VUE3_PYWEBVIEW_WINDOWS_AMD64 = $(BUILDDIR)/est_test_x_vue3_pywebview_windows_amd64.exe

all: help

.PHONY: all prepare clean help \
        run_web_fastapi run_test run_test_nist_cpp_recode run_test_x_vue3_pywebview \
        refdata_diff refdata_diff_all lrs_bench jit_crosscheck job_bench \
        build_test_x_vue3_pywebview_windows_amd64 build_all

prepare:
	@$(call MD, $(BUILDDIR))

run_web_fastapi:
	cd "$(WEB_CODE_PATH)" && "$(PYTHON)" "$(WEB_MAIN)"

run_test:
	"$(PYTHON)" "$(TEST_MAIN_PATH)" $(TEST_ARGS)

run_test_nist_cpp_recode:
	"$(PYTHON)" "$(TEST_NIST_CPP_RECODE_MAIN_PATH)" $(TEST_ARGS)

# 开发校验与基准：不参与程序运行或打包依赖链。
refdata_diff:
	"$(PYTHON)" "$(TEST_NIST_CPP_RECODE_CODE_PATH)/refdata_diff.py"

# 全量参考输出使用 1e-6 相对容差，原因见 est_test_nist_cpp_recode/README.md。
refdata_diff_all:
	"$(PYTHON)" "$(TEST_NIST_CPP_RECODE_CODE_PATH)/refdata_diff.py" --all --tol 1e-6

lrs_bench:
	"$(PYTHON)" "$(TEST_NIST_CPP_RECODE_CODE_PATH)/lrs_bench.py" "$(LRS_BENCH_SAMPLE)"

jit_crosscheck:
	"$(PYTHON)" "$(TEST_NIST_CPP_RECODE_CODE_PATH)/jit_crosscheck.py"

job_bench:
	"$(PYTHON)" "$(TEST_NIST_CPP_RECODE_CODE_PATH)/job_bench.py" "$(JOB_BENCH_SAMPLE)"

run_test_x_vue3_pywebview:
	+$(MAKE_PYTHON) -C "$(TEST_X_VUE3_PYWEBVIEW_CODE_PATH)" run_dev

build_test_x_vue3_pywebview_windows_amd64: prepare
	@echo "Build started: vue3 pywebview Windows amd64 version..."
	+$(MAKE_PYTHON) -C "$(TEST_X_VUE3_PYWEBVIEW_CODE_PATH)" build_windows_amd64
	$(call CP_FILE, $(TEST_X_VUE3_PYWEBVIEW_BUILD_DIR)/$(TEST_X_VUE3_PYWEBVIEW_APPNAME), $(RELEASE_EST_TEST_X_VUE3_PYWEBVIEW_WINDOWS_AMD64))
	@echo "Build completed: $(RELEASE_EST_TEST_X_VUE3_PYWEBVIEW_WINDOWS_AMD64)"

build_all: build_test_x_vue3_pywebview_windows_amd64

clean:
	$(call RF, $(RELEASE_EST_TEST_X_VUE3_PYWEBVIEW_WINDOWS_AMD64))

help:
	@echo ------------------------
	@echo "Run:"
	@echo "  make run_test [TEST_ARGS=...]:                  est_core CLI (default: --help)"
	@echo "  make run_test_nist_cpp_recode [TEST_ARGS=...]:  C++ recode CLI (default: --help)"
	@echo "  make run_test_x_vue3_pywebview:                 desktop development mode"
	@echo "  make run_web_fastapi:                           web server at http://127.0.0.1:8888"
	@echo "Validation / benchmarks (development only):"
	@echo "  make refdata_diff:                              3 short samples, relative tolerance 1e-9"
	@echo "  make refdata_diff_all:                          all 11 samples, relative tolerance 1e-6"
	@echo "  make jit_crosscheck:                            Python vs numba predictor counts"
	@echo "  make lrs_bench [LRS_BENCH_SAMPLE=...]:          SA / LCP timing and sampled fingerprints"
	@echo "  make job_bench [JOB_BENCH_SAMPLE=...]:          non-IID estimator timings (excluding MCV)"
	@echo "Build / cleanup:"
	@echo "  make prepare:                                  create release directory"
	@echo "  make build_test_x_vue3_pywebview_windows_amd64: desktop onefile exe in release/"
	@echo "  make build_all:                                 desktop build alias"
	@echo "  make clean:                                     remove released exe only"
	@echo "Overrides: PYTHON=path; TEST_ARGS are passed to the CLI from the repository root."
	@echo "Default Python: conda env z_est_env_python if found, otherwise python on PATH."
	@echo "make / make all / make help: show this help"
	@echo ------------------------
