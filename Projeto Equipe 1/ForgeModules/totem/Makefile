.DEFAULT_GOAL := help

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
CC = gcc

# Detect and normalize architecture
ARCH ?= $(shell uname -m | tr '[:upper:]' '[:lower:]')
ifeq ($(ARCH),aarch64)
  ARCH := arm64
endif
ifeq ($(ARCH),i386)
  ARCH := x86
endif
ifeq ($(ARCH),i686)
  ARCH := x86
endif

EXE_SUFFIX =
ifeq ($(OS),Windows_NT)
  EXE_SUFFIX = .exe
endif

STT_LINUX ?= libs/$(ARCH)/libstt.so
STT_WINDOWS ?= libs/$(ARCH)/stt.dll

.PHONY: help install install-mac run run-fullscreen run-studio cli lint format sort-imports check test install-deps compile apicomm clean stt-linux stt-windows all

help:
	@echo "Available targets:"
	@echo "  install        Install Python dependencies"
	@echo "  install-mac    Install macOS-specific dependencies"
	@echo "  run            Launch the GUI"
	@echo "  run-fullscreen Launch the GUI in fullscreen"
	@echo "  run-studio     Launch the GUI in studio/layout mode"
	@echo "  cli            Launch the CLI interface"
	@echo "  lint           Run Flake8"
	@echo "  format         Run Black"
	@echo "  sort-imports   Run isort"
	@echo "  check          Run python -m compileall to validate syntax"
	@echo "  test           Alias for check"
	@echo "  install-deps   Install system deps (Debian/Ubuntu)"
	@echo "  compile        Builds apicomm"
	@echo "  apicomm        Compile apicomm.c"
	@echo "  stt-linux      Build libs/$(ARCH)/libstt.so"
	@echo "  stt-windows    Build libs/$(ARCH)/stt.dll"
	@echo "  windows-all    Build both apicomm and stt-windows for Windows"
	@echo "  install-deps-windows Install system deps on Windows via MSYS2 (pacman)"
	@echo "  all            install-deps + compile (Debian/Ubuntu helper)"

install:
	$(PIP) install -r requirements.txt

install-mac:
	$(PIP) install -r requirements_mac.txt

run:
	$(PYTHON) main_gui.py

run-fullscreen:
	$(PYTHON) main_gui.py -f

run-studio:
	$(PYTHON) main_gui.py -s

cli:
	$(PYTHON) main_cli.py

run-tts:
	$(PYTHON) -m uvicorn tts_api.main:app --host 0.0.0.0 --port 8000

lint:
	$(PYTHON) -m flake8 .

format:
	$(PYTHON) -m black .

sort-imports:
	$(PYTHON) -m isort .

check:
	$(PYTHON) -m compileall main_gui.py src

test: check

install-deps:
	@echo "Installing system dependencies on Debian/Ubuntu..."
	apt-get update
	apt-get install -y libcjson-dev libcurl4-openssl-dev portaudio19-dev

install-deps-windows:
	@echo "Installing system dependencies on Windows (requires MSYS2/pacman)..."
	pacman -S --noconfirm --needed mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-cjson mingw-w64-ucrt-x86_64-curl mingw-w64-ucrt-x86_64-portaudio

compile: apicomm

apicomm: c_src/apicomm.c
	@echo "Compiling apicomm..."
	$(PYTHON) -c "import os; os.makedirs('bin/$(ARCH)', exist_ok=True)"
	$(CC) -O2 -march=native -Wall -Wextra -o bin/$(ARCH)/apicomm$(EXE_SUFFIX) c_src/apicomm.c -lcurl -lcjson
	@ls -lh bin/$(ARCH)/apicomm$(EXE_SUFFIX)

clean:
	@echo "Cleaning binaries..."
	$(PYTHON) -c "import shutil, os; shutil.rmtree('bin/$(ARCH)', ignore_errors=True); [os.remove(f) for f in ['libs/$(ARCH)/libstt.so', 'libs/$(ARCH)/stt.dll'] if os.path.exists(f)]"

stt-linux:
	@echo "Building STT helper for Linux..."
	$(PYTHON) -c "import os; os.makedirs('libs/$(ARCH)', exist_ok=True)"
	$(CC) -shared -fPIC c_src/stt.c -o $(STT_LINUX) -lportaudio -lcurl

stt-windows:
	@echo "Building STT helper for Windows..."
	$(PYTHON) -c "import os; os.makedirs('libs/$(ARCH)', exist_ok=True)"
	$(CC) -shared -fPIC c_src/stt.c -o $(STT_WINDOWS) -lportaudio -lcurl

windows-all: install-deps-windows apicomm stt-windows

all: install-deps compile
