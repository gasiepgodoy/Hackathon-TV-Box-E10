import os
import platform
import subprocess
import logging
from pathlib import Path
from typing import Optional

from src.utils.dependency_manager import dependency_manager

logger = logging.getLogger(__name__)

class BinaryManager:
    """
    Manages architecture-specific native binaries and their compilation.
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        if project_root:
            self.project_root = project_root
        else:
            # Assume we are in src/utils/
            self.project_root = Path(__file__).resolve().parents[2]
            
        self.arch = platform.machine().lower()
        self.system = platform.system().lower()
        
        # Normalize arch names if needed (e.g., aarch64 -> arm64)
        if self.arch == "aarch64":
            self.arch = "arm64"
        elif self.arch in ("i386", "i686"):
            self.arch = "x86"
            
        self.bin_dir = self.project_root / "bin" / self.arch
        self.lib_dir = self.project_root / "libs" / self.arch
        
    def ensure_directories(self):
        """Ensure arch-specific directories exist."""
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self.lib_dir.mkdir(parents=True, exist_ok=True)

    def get_binary_path(self, name: str) -> Path:
        """Returns the expected path for a binary executable."""
        if self.system == "windows":
            name += ".exe"
        return self.bin_dir / name

    def get_lib_path(self, name: str) -> Path:
        """Returns the expected path for a shared library."""
        if self.system == "windows":
            if not name.endswith(".dll"):
                name += ".dll"
        elif self.system == "darwin":
            if not name.endswith(".dylib"):
                name += ".dylib"
        else: # Linux
            if not name.startswith("lib"):
                name = "lib" + name
            if not name.endswith(".so"):
                name += ".so"
        return self.lib_dir / name

    def _run_make(self, target: str):
        """Runs the Makefile for a specific target."""
        logger.info(f"Compiling binary for {self.arch} using target: {target}")
        try:
            # Pass ARCH and OUTDIR to Makefile
            env = os.environ.copy()
            env["ARCH"] = self.arch
            
            # Use the absolute path to the project root for make
            subprocess.run(
                ["make", target, f"ARCH={self.arch}"],
                cwd=str(self.project_root),
                check=True,
                capture_output=True,
                text=True,
                env=env
            )
            logger.info(f"Successfully compiled {target}")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or e.stdout
            logger.error(f"Failed to compile {target}: {error_msg}")
            
            # Attempt to handle missing dependencies automatically
            if dependency_manager.check_and_install_missing(error_msg):
                logger.info("Dependencies installed. Retrying compilation...")
                return self._run_make(target) # Recursive retry
                
            raise RuntimeError(f"Compilation failed for {target}: {error_msg}")
        except FileNotFoundError:
            logger.error("Make command not found. Please install build-essential or equivalent.")
            raise RuntimeError("Make not found on system.")

    def ensure_apicomm(self) -> Optional[Path]:
        """Ensures apicomm is compiled and returns its path."""
        path = self.get_binary_path("apicomm")
        if not path.exists():
            logger.warning(f"apicomm not found for {self.arch}, attempting auto-compilation...")
            try:
                self.ensure_directories()
                self._run_make("apicomm")
            except Exception as e:
                logger.error(f"Auto-compilation of apicomm failed: {e}")
                return None
        return path

    def ensure_stt_lib(self) -> Optional[Path]:
        """Ensures the STT shared library is compiled and returns its path."""
        lib_name = "stt"
        path = self.get_lib_path(lib_name)
        
        if not path.exists():
            logger.warning(f"STT library not found for {self.arch}, attempting auto-compilation...")
            try:
                self.ensure_directories()
                
                target = "stt-linux"
                if self.system == "windows":
                    target = "stt-windows"
                elif self.system == "darwin":
                    target = "stt-mac"
                    
                self._run_make(target)
            except Exception as e:
                logger.error(f"Auto-compilation of STT library failed: {e}")
                return None
            
        return path

# Global instance
binary_manager = BinaryManager()
