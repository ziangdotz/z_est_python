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


WEB_CODE_PATH = ./est_web_fastapi
WEB_MAIN = run.py
WEB_MAIN_PATH = $(WEB_CODE_PATH)/$(WEB_MAIN)
TEST_CODE_PATH = ./est_test
TEST_MAIN = est_test.py
TEST_MAIN_PATH = $(TEST_CODE_PATH)/$(TEST_MAIN)
TEST_VUE3_PYWEBVIEW_CODE_PATH = ./est_test_vue3_pywebview
TEST_NIST_CPP_RECODE_CODE_PATH = ./est_test_nist_cpp_recode
TEST_NIST_CPP_RECODE_MAIN = est_test_nist_cpp_recode.py
TEST_NIST_CPP_RECODE_MAIN_PATH = $(TEST_NIST_CPP_RECODE_CODE_PATH)/$(TEST_NIST_CPP_RECODE_MAIN)
TEST_NIST_CPP_RECODE_VUE3_PYWEBVIEW_CODE_PATH = ./est_test_nist_cpp_recode_vue3_pywebview

BUILDDIR = release

RELEASE_EST_TEST_VUE3_PYWEBVIEW_WINDOWS_AMD64 = $(BUILDDIR)/est_test_vue3_pywebview_windows_amd64.exe
RELEASE_EST_TEST_NIST_CPP_RECODE_VUE3_PYWEBVIEW_WINDOWS_AMD64 = $(BUILDDIR)/est_test_nist_cpp_recode_vue3_pywebview_windows_amd64.exe

all: help

.PHONY: prepare clean help

prepare:
	@$(call MD, $(BUILDDIR))

run_web_fastapi:
	cd $(WEB_CODE_PATH) \
	&& python $(WEB_MAIN)

run_test:
	cd $(TEST_CODE_PATH) \
	&& python $(TEST_MAIN)

run_test_nist_cpp_recode:
	cd $(TEST_NIST_CPP_RECODE_CODE_PATH) \
	&& python $(TEST_NIST_CPP_RECODE_MAIN)

run_test_vue3_pywebview:
	cd $(TEST_VUE3_PYWEBVIEW_CODE_PATH) && \
	make run_dev

build_test_vue3_pywebview_windows_amd64:
	@echo "Build started: vue3 pywebview Windows amd64 version..."
	cd $(TEST_VUE3_PYWEBVIEW_CODE_PATH) && \
	make build_windows_amd64
	@echo "Build completed: $(RELEASE_EST_TEST_VUE3_PYWEBVIEW_WINDOWS_AMD64)"

run_test_nist_cpp_recode_vue3_pywebview:
	cd $(TEST_NIST_CPP_RECODE_VUE3_PYWEBVIEW_CODE_PATH) && \
	make run_dev

build_test_nist_cpp_recode_vue3_pywebview_windows_amd64:
	@echo "Build started: nist cpp recode vue3 pywebview Windows amd64 version..."
	cd $(TEST_NIST_CPP_RECODE_VUE3_PYWEBVIEW_CODE_PATH) && \
	make build_windows_amd64
	@echo "Build completed: $(RELEASE_EST_TEST_NIST_CPP_RECODE_VUE3_PYWEBVIEW_WINDOWS_AMD64)"

build_all: build_test_vue3_pywebview_windows_amd64 build_test_nist_cpp_recode_vue3_pywebview_windows_amd64

clean:
	$(call RF, $(RELEASE_EST_TEST_VUE3_PYWEBVIEW_WINDOWS_AMD64))

help:
	@echo ------------------------
	@echo "make run_web_fastapi:                                         run web fastapi server"
	@echo "make run_test:                                                run test"
	@echo "make run_test_nist_cpp_recode:                                run est_test_nist_cpp_recode"
	@echo "make run_test_vue3_pywebview:                                 run est_test_vue3_pywebview"
	@echo "make build_test_vue3_pywebview_windows_amd64:                 build est_test_vue3_pywebview -- test vue3 pywebview windows amd64 version"
	@echo "make run_test_nist_cpp_recode_vue3_pywebview:                 run est_test_nist_cpp_recode_vue3_pywebview"
	@echo "make build_test_nist_cpp_recode_vue3_pywebview_windows_amd64: build est_test_nist_cpp_recode_vue3_pywebview -- test nist cpp recode vue3 pywebview windows amd64 version"
	@echo "make build_all:                                               build all works"
	@echo "make clean:                                                   clean middle files"
	@echo "make help:                                                    see custom commands"
	@echo "make:                                                         like 'make help'"
	@echo ------------------------

