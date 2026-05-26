FIX_PATH = $(subst /,\,$(1))
RM = if exist $(call FIX_PATH, $(1)) rd /s /q $(call FIX_PATH, $(1))
RF = if exist $(call FIX_PATH, $(1)) del /f /q $(call FIX_PATH, $(1))
MD = if not exist $(call FIX_PATH, $(1)) mkdir $(call FIX_PATH, $(1))
CP = xcopy /s /e /i /y
# UPX_PATH := $(shell where upx 2>nul)

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
NUITKA_FLAGS := --standalone \
				--onefile \
				--windows-disable-console \
				--assume-yes-for-downloads \
				--windows-icon-from-ico=$(APPLOGO_ICON) \
				--include-data-dir=$(RESOURCES_DIR)=$(RESOURCES_DIR) \
				--include-data-files=$(APPLOGO_TRAY_IMG)=$(APPLOGO_TRAY_IMG) \
				--include-data-files=$(APPLOGO_ICON)=$(APPLOGO_ICON) \
				--show-progress \
				--output-dir=$(BUILD_DIR) \
				--output-filename=$(APPNAME).exe
PY_NUITKA_PACKAGE := python -m nuitka $(NUITKA_FLAGS)

all: help

.PHONY: prepare clean help

prepare:
	@cd $(FRONTEND_DIR) && npm install
# 	@python -m pip install -r requirements.txt
	@$(call MD, $(RESOURCES_DIR))
	@$(call MD, $(BUILD_DIR))

run_dev: prepare
	@python $(MAIN) --dev

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

