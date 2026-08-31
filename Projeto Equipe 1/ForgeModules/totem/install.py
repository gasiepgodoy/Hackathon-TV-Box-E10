#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-Platform Installation Script for Mina Virtual Assistant.
Works on Windows, Linux (Ubuntu/Debian/Arch/Fedora), macOS, and WSL2.

Steps:
1. Clone Repository (if executed outside repo directory)
2. Install System Build Essentials & Native C Libraries
3. Install Python Dependencies (pip requirements.txt)
4. Build Native C Components (apicomm & libstt / stt.dll)
5. Verify Installation
"""

import os
import sys
import shutil
import platform
import subprocess
import argparse
from pathlib import Path

REPO_URL = "https://github.com/GERA-UNESP/Mina-a-Assistente-Virtual.git"
DEFAULT_DIR_NAME = "Mina-a-Assistente-Virtual"

# Colors for terminal output
IS_TTY = sys.stdout.isatty()
CLR_CYAN = "\033[1;36m" if IS_TTY else ""
CLR_GREEN = "\033[1;32m" if IS_TTY else ""
CLR_YELLOW = "\033[1;33m" if IS_TTY else ""
CLR_RED = "\033[1;31m" if IS_TTY else ""
CLR_RESET = "\033[0m" if IS_TTY else ""


def log_step(msg: str):
    print(f"\n{CLR_CYAN}===> {msg}{CLR_RESET}")


def log_success(msg: str):
    print(f"{CLR_GREEN}[OK] {msg}{CLR_RESET}")


def log_warn(msg: str):
    print(f"{CLR_YELLOW}[!] {msg}{CLR_RESET}")


def log_err(msg: str):
    print(f"{CLR_RED}[X] {msg}{CLR_RESET}")


def run_command(cmd, cwd=None, check=True, shell=False):
    if isinstance(cmd, list):
        cmd_str = " ".join(cmd)
    else:
        cmd_str = cmd
    print(f"Executing: {cmd_str}")
    res = subprocess.run(cmd, cwd=cwd, shell=shell)
    if check and res.returncode != 0:
        raise subprocess.CalledProcessError(res.returncode, cmd)
    return res.returncode == 0


def get_architecture() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    elif machine in ("aarch64", "arm64"):
        return "arm64"
    elif machine in ("i386", "i686", "x86"):
        return "x86"
    return machine


def check_and_clone_repo(target_dir: Path) -> Path:
    log_step("Step 1: Checking Repository Setup")
    curr_dir = Path.cwd().resolve()

    if (curr_dir / "main_gui.py").exists() or (curr_dir / "c_src").exists():
        log_success(f"Already inside repository at: {curr_dir}")
        return curr_dir

    if (target_dir / "main_gui.py").exists():
        log_success(f"Found repository at: {target_dir}")
        os.chdir(target_dir)
        return target_dir

    log_step(f"Cloning repository from {REPO_URL} into {target_dir}")
    run_command(["git", "clone", REPO_URL, str(target_dir)])
    os.chdir(target_dir)
    log_success("Repository cloned successfully.")
    return target_dir


def install_system_dependencies():
    log_step("Step 2: Installing System Build Essentials & Libraries")
    system = platform.system().lower()

    if system == "linux":
        if shutil.which("apt-get"):
            log_step("Installing Debian/Ubuntu/WSL2 build dependencies via apt-get...")
            cmd = ["sudo", "apt-get", "update", "-y"]
            run_command(cmd, check=False)

            deps = [
                "build-essential",
                "gcc",
                "g++",
                "cmake",
                "libcjson-dev",
                "libcurl4-openssl-dev",
                "portaudio19-dev",
                "libasound2-dev",
                "python3-dev",
                "python3-pip",
                "python3-venv",
                "python3-pyqt5",
                "python3-pyqt5.qtsvg",
                "qt5-qmake",
                "qtbase5-dev"
            ]
            run_command(["sudo", "apt-get", "install", "-y"] + deps, check=False)
            log_success("Linux system dependencies installed.")
        elif shutil.which("pacman"):
            log_step("Installing Arch Linux build dependencies via pacman...")
            deps = ["base-devel", "gcc", "cmake", "cjson", "curl", "portaudio", "python-pip"]
            run_command(["sudo", "pacman", "-S", "--needed", "--noconfirm"] + deps, check=False)
            log_success("Arch Linux system dependencies installed.")
        elif shutil.which("dnf"):
            log_step("Installing Fedora build dependencies via dnf...")
            deps = ["gcc", "gcc-c++", "cmake", "libcjson-devel", "libcurl-devel", "portaudio-devel", "python3-devel"]
            run_command(["sudo", "dnf", "install", "-y"] + deps, check=False)
            log_success("Fedora system dependencies installed.")
        else:
            log_warn("Unrecognized Linux package manager. Please ensure gcc, libcjson, libcurl, and portaudio headers are installed.")

    elif system == "windows":
        has_gcc = shutil.which("gcc") is not None
        has_cl = shutil.which("cl") is not None
        has_clang = shutil.which("clang") is not None

        if has_gcc or has_cl or has_clang:
            compiler = "gcc" if has_gcc else ("cl" if has_cl else "clang")
            log_success(f"C/C++ compiler detected on Windows: {compiler}")
        else:
            log_warn("No C/C++ compiler (gcc/cl/clang) found in PATH.")
            if shutil.which("winget"):
                log_step("Attempting to install MSYS2 via winget...")
                try:
                    run_command(["winget", "install", "-e", "--id", "MSYS2.MSYS2", "--accept-package-agreements", "--accept-source-agreements"], check=False)
                except Exception:
                    pass
            log_warn("If C compilation fails in Step 4, please install MinGW (w64) or Visual Studio C++ Build Tools.")

    elif system == "darwin":
        log_step("Installing macOS build dependencies via brew...")
        if shutil.which("brew"):
            run_command(["brew", "install", "cjson", "curl", "portaudio", "cmake"], check=False)
            log_success("macOS system dependencies installed via Homebrew.")
        else:
            log_warn("Homebrew not found. Please ensure Xcode command line tools and portaudio are installed.")


def install_python_requirements():
    log_step("Step 3: Installing Python Requirements")
    python_exe = sys.executable

    extra_flags = []
    try:
        res = subprocess.run([python_exe, "-m", "pip", "install", "--help"], capture_output=True, text=True)
        if "--break-system-packages" in res.stdout:
            extra_flags.append("--break-system-packages")
    except Exception:
        pass

    run_command([python_exe, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"] + extra_flags, check=False)

    req_file = Path("requirements.txt")
    if req_file.exists():
        try:
            run_command([python_exe, "-m", "pip", "install", "-r", str(req_file)] + extra_flags)
            log_success("Python requirements installed.")
        except Exception as e:
            log_warn(f"System pip install failed ({e}). Creating local .venv virtual environment...")
            venv_dir = Path(".venv")
            run_command([python_exe, "-m", "venv", str(venv_dir)])
            bin_dir = "Scripts" if platform.system().lower() == "windows" else "bin"
            venv_python = venv_dir / bin_dir / ("python.exe" if platform.system().lower() == "windows" else "python")
            run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
            run_command([str(venv_python), "-m", "pip", "install", "-r", str(req_file)])
            log_success("Python requirements installed inside .venv virtual environment.")
    else:
        log_err("requirements.txt not found!")


def build_c_components():
    log_step("Step 4: Building Native C Components (stt & apicomm)")
    arch = get_architecture()
    system = platform.system().lower()

    bin_dir = Path(f"bin/{arch}")
    lib_dir = Path(f"libs/{arch}")
    bin_dir.mkdir(parents=True, exist_ok=True)
    lib_dir.mkdir(parents=True, exist_ok=True)

    compiler = "gcc"
    if not shutil.which("gcc"):
        if shutil.which("clang"):
            compiler = "clang"
        elif shutil.which("cl"):
            compiler = "cl"
        else:
            log_warn("No compiler executable found in PATH. Defaulting to gcc command.")

    inc_flags = []
    if system != "windows":
        if Path("/usr/include/cjson").exists():
            inc_flags.append("-I/usr/include/cjson")

    # 1. Build apicomm
    apicomm_src = Path("c_src/apicomm.c")
    if apicomm_src.exists():
        exe_suffix = ".exe" if system == "windows" else ""
        out_apicomm = bin_dir / f"apicomm{exe_suffix}"
        log_step(f"Compiling apicomm -> {out_apicomm}")

        if compiler == "cl":
            cmd = ["cl", "/O2", str(apicomm_src), f"/Fe:{out_apicomm}", "libcurl.lib", "cjson.lib"]
        else:
            cmd = [compiler, "-O2", "-Wall", "-Wextra"] + inc_flags + ["-o", str(out_apicomm), str(apicomm_src), "-lcurl", "-lcjson"]

        try:
            run_command(cmd)
            log_success(f"apicomm compiled successfully: {out_apicomm}")
        except Exception as e:
            log_err(f"Failed to compile apicomm: {e}")
    else:
        log_warn("c_src/apicomm.c not found.")

    # 2. Build STT library
    stt_src = Path("c_src/stt.c")
    if stt_src.exists():
        lib_name = "stt.dll" if system == "windows" else ("libstt.dylib" if system == "darwin" else "libstt.so")
        out_stt = lib_dir / lib_name
        log_step(f"Compiling STT library -> {out_stt}")

        if compiler == "cl":
            cmd = ["cl", "/LD", "/O2", str(stt_src), f"/Fe:{out_stt}", "portaudio.lib", "libcurl.lib"]
        else:
            cmd = [compiler, "-shared", "-fPIC"] + inc_flags + [str(stt_src), "-o", str(out_stt), "-lportaudio", "-lcurl"]

        try:
            run_command(cmd)
            log_success(f"STT library compiled successfully: {out_stt}")
        except Exception as e:
            log_err(f"Failed to compile STT library: {e}")
    else:
        log_warn("c_src/stt.c not found.")


def verify_installation():
    log_step("Step 5: Verifying Installation & Syntax Check")
    python_exe = sys.executable

    run_command([python_exe, "-m", "compileall", "main_gui.py", "main_cli.py", "src"])
    log_success("Python syntax check passed.")

    arch = get_architecture()
    system = platform.system().lower()
    exe_suffix = ".exe" if system == "windows" else ""
    lib_name = "stt.dll" if system == "windows" else ("libstt.dylib" if system == "darwin" else "libstt.so")

    apicomm_bin = Path(f"bin/{arch}/apicomm{exe_suffix}")
    stt_lib = Path(f"libs/{arch}/{lib_name}")

    if apicomm_bin.exists():
        log_success(f"apicomm binary found: {apicomm_bin}")
    else:
        log_warn(f"apicomm binary missing at {apicomm_bin}")

    if stt_lib.exists():
        log_success(f"stt library found: {stt_lib}")
    else:
        log_warn(f"stt library missing at {stt_lib}")

    log_step("SETUP COMPLETE!")
    print(f"{CLR_GREEN}To launch GUI mode run:  {python_exe} main_gui.py{CLR_RESET}")
    print(f"{CLR_GREEN}To launch CLI mode run:  {python_exe} main_cli.py{CLR_RESET}")


def main():
    parser = argparse.ArgumentParser(description="Installer for Mina Virtual Assistant")
    parser.add_argument("--dir", default=DEFAULT_DIR_NAME, help="Target directory for cloning if run outside repo")
    parser.add_argument("--skip-sys-deps", action="store_true", help="Skip OS package manager system dependencies")
    args = parser.parse_args()

    check_and_clone_repo(Path(args.dir).resolve())

    if not args.skip_sys_deps:
        install_system_dependencies()

    install_python_requirements()
    build_c_components()
    verify_installation()


if __name__ == "__main__":
    main()
