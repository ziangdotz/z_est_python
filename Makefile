ifeq ($(OS), Windows_NT)
	FIX_PATH = $(subst /,\,$(1))
	RM = if exist $(call FIX_PATH, $(1)) rd /s /q $(call FIX_PATH, $(1))
	RF = if exist $(call FIX_PATH, $(1)) del /f /q $(call FIX_PATH, $(1))
	MD = if not exist $(call FIX_PATH, $(1)) mkdir $(call FIX_PATH, $(1))
	CP_FILE = copy /Y $(call FIX_PATH, $(1)) $(call FIX_PATH, $(2))
else
	FIX_PATH = $(1)
	RM = rm -rf $(1)
	RF = rm -f $(1)
	MD = mkdir -p $(1)
	CP_FILE = cp $(1) $(2)
endif


# Python 解释器。本工程的开发/构建环境固定是 conda 环境 z_est_env_python：
#   C:\Tools\miniconda3\envs\z_est_env_python（Python 3.12）
# 而 PATH 上的 python 是 msys64 的那份（C:\Tools\msys64\mingw64\bin\python.exe），
# 既没有 numpy 也没有 nuitka，裸用会让 run/build 目标全挂，所以默认取 conda 环境的
# 绝对路径；该路径不存在时（换机器、换盘符）回退到 PATH 上的 python。需要时覆盖：
#   make refdata_diff PYTHON=C:/Tools/miniconda3/envs/z_est_env_python/python.exe
CONDA_ENV_PYTHON = C:/Tools/miniconda3/envs/z_est_env_python/python.exe
CONDA_ENV_PYTHON_FOUND = $(wildcard $(CONDA_ENV_PYTHON))
ifneq ($(CONDA_ENV_PYTHON_FOUND),)
DEFAULT_PYTHON = $(CONDA_ENV_PYTHON)
else
DEFAULT_PYTHON = python
endif

PYTHON ?= $(DEFAULT_PYTHON)
# 递归进子 Makefile 时把解释器一起传下去，否则子 Makefile 会按自己看到的 PATH 解析
MAKE_PYTHON = $(MAKE) PYTHON="$(PYTHON)"

WEB_CODE_PATH = ./est_web_fastapi
WEB_MAIN = run.py
WEB_MAIN_PATH = $(WEB_CODE_PATH)/$(WEB_MAIN)
TEST_CODE_PATH = ./est_test
TEST_MAIN = est_test.py
TEST_MAIN_PATH = $(TEST_CODE_PATH)/$(TEST_MAIN)
TEST_NIST_CPP_RECODE_CODE_PATH = ./est_test_nist_cpp_recode
TEST_NIST_CPP_RECODE_MAIN = est_test_nist_cpp_recode.py
TEST_NIST_CPP_RECODE_MAIN_PATH = $(TEST_NIST_CPP_RECODE_CODE_PATH)/$(TEST_NIST_CPP_RECODE_MAIN)
LRS_BENCH_SAMPLE = 8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
JOB_BENCH_SAMPLE = 8ckup/NIST_SP800-90B_EntropyAssessment/bin/truerand_4bit.bin
TEST_X_VUE3_PYWEBVIEW_CODE_PATH = ./est_test_x_vue3_pywebview
# 子 Makefile 的 Nuitka 输出位置（APPNAME / BUILD_DIR 要跟它一致）
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
	cd $(WEB_CODE_PATH) \
	&& $(PYTHON) $(WEB_MAIN)

run_test:
	cd $(TEST_CODE_PATH) \
	&& $(PYTHON) $(TEST_MAIN)

run_test_nist_cpp_recode:
	cd $(TEST_NIST_CPP_RECODE_CODE_PATH) \
	&& $(PYTHON) $(TEST_NIST_CPP_RECODE_MAIN)

refdata_diff:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/refdata_diff.py

# 全量 11 样本必须配 --tol 1e-6：预测器派生值（MultiMCW 的 -log2 会按 1/|ln p| 放大相对误差）
# 在默认的 1e-9 严格档下本来就会超容差，不配这个标志该目标恒为 FAIL。见 refdata_diff.py 头部说明。
refdata_diff_all:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/refdata_diff.py --all --tol 1e-6

lrs_bench:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/lrs_bench.py $(LRS_BENCH_SAMPLE)

jit_crosscheck:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/jit_crosscheck.py

job_bench:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/job_bench.py $(JOB_BENCH_SAMPLE)

run_test_x_vue3_pywebview:
	$(MAKE_PYTHON) -C $(TEST_X_VUE3_PYWEBVIEW_CODE_PATH) run_dev

build_test_x_vue3_pywebview_windows_amd64:
	@echo "Build started: vue3 pywebview Windows amd64 version..."
	$(MAKE_PYTHON) -C $(TEST_X_VUE3_PYWEBVIEW_CODE_PATH) build_windows_amd64
	$(call MD, $(BUILDDIR))
	$(call CP_FILE, $(TEST_X_VUE3_PYWEBVIEW_BUILD_DIR)/$(TEST_X_VUE3_PYWEBVIEW_APPNAME), $(RELEASE_EST_TEST_X_VUE3_PYWEBVIEW_WINDOWS_AMD64))
	@echo "Build completed: $(RELEASE_EST_TEST_X_VUE3_PYWEBVIEW_WINDOWS_AMD64)"

build_all: build_test_x_vue3_pywebview_windows_amd64

clean:
	$(call RF, $(RELEASE_EST_TEST_X_VUE3_PYWEBVIEW_WINDOWS_AMD64))

help:
	@echo ------------------------
	@echo "make run_web_fastapi:                           run web fastapi server"
	@echo "make run_test:                                  run test"
	@echo "make run_test_nist_cpp_recode:                  run est_test_nist_cpp_recode"
	@echo "make refdata_diff:                              diff ea_non_iid -vv against C++ refdata (3 short samples)"
	@echo "make refdata_diff_all:                          diff ea_non_iid -vv against C++ refdata (all 11 samples)"
	@echo "make lrs_bench [LRS_BENCH_SAMPLE=...]:          time and fingerprint ea/_lrs.py (SA/LCP/sa_algs)"
	@echo "make jit_crosscheck:                            diff each predictor's Python loop against its numba kernel"
	@echo "make job_bench [JOB_BENCH_SAMPLE=...]:          time every non-IID estimate job per data view"
	@echo "make run_test_x_vue3_pywebview:                 run est_test_x_vue3_pywebview"
	@echo "make build_test_x_vue3_pywebview_windows_amd64: build est_test_x_vue3_pywebview -- test x vue3 pywebview windows amd64 version"
	@echo "make build_all:                                 build all works"
	@echo "make clean:                                     clean middle files"
	@echo "make PYTHON=path:                               point any target at another interpreter (default: conda env z_est_env_python, else python on PATH)"
	@echo "make help:                                      see custom commands"
	@echo "make:                                           like 'make help'"
	@echo ------------------------

