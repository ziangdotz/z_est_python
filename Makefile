ifeq ($(OS), Windows_NT)
	FIX_PATH = $(subst /,\,$(1))
	RM = if exist $(call FIX_PATH, $(1)) rd /s /q $(call FIX_PATH, $(1))
	RF = if exist $(call FIX_PATH, $(1)) del /f /q $(call FIX_PATH, $(1))
	MD = if not exist $(call FIX_PATH, $(1)) mkdir $(call FIX_PATH, $(1))
else
	FIX_PATH = $(1)
	RM = rm -rf $(1)
	RF = rm -f $(1)
	MD = mkdir -p $(1)
endif


# Python 解释器。默认用 PATH 上的 python；本项目的开发环境是 conda 环境
# z_est_env_python（PATH 上的 python 没有 numpy），需要时覆盖：
#   make refdata_diff PYTHON=D:/Tools/miniconda3/envs/z_est_env_python/python.exe
PYTHON ?= python

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

BUILDDIR = release

RELEASE_EST_TEST_X_VUE3_PYWEBVIEW_WINDOWS_AMD64 = $(BUILDDIR)/est_test_x_vue3_pywebview_windows_amd64.exe

all: help

.PHONY: prepare clean help refdata_diff refdata_diff_all lrs_bench jit_crosscheck job_bench

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

refdata_diff_all:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/refdata_diff.py --all

lrs_bench:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/lrs_bench.py $(LRS_BENCH_SAMPLE)

jit_crosscheck:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/jit_crosscheck.py

job_bench:
	$(PYTHON) $(TEST_NIST_CPP_RECODE_CODE_PATH)/job_bench.py $(JOB_BENCH_SAMPLE)

run_test_x_vue3_pywebview:
	cd $(TEST_X_VUE3_PYWEBVIEW_CODE_PATH) && \
	make run_dev

build_test_x_vue3_pywebview_windows_amd64:
	@echo "Build started: vue3 pywebview Windows amd64 version..."
	cd $(TEST_X_VUE3_PYWEBVIEW_CODE_PATH) && \
	make build_windows_amd64
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
	@echo "make PYTHON=path:                               point any target at another interpreter (default: python on PATH)"
	@echo "make help:                                      see custom commands"
	@echo "make:                                           like 'make help'"
	@echo ------------------------

