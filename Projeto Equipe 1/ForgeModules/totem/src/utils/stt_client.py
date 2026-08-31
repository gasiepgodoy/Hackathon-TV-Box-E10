"""Python binding for the C-based STT helper that drives PortAudio + Groq."""

import ctypes
import logging
import os
import platform
from pathlib import Path
from typing import Optional

from src.utils.config_manager import ConfigManager


class STTClientError(RuntimeError):
    """Raised when the native STT helper cannot perform an action."""


class STTClient:
    """Wrapper around the native shared library exported by stt.c."""

    def __init__(self, lib_path: Optional[str] = None):
        self._logger = logging.getLogger(__name__)
        self._config = ConfigManager.get_instance()
        
        # Inject configurations into environment variables for the native STT library
        stt_opts = self._config.get_config("STT_OPTIONS", {})
        if stt_opts.get("API_KEY"):
            os.environ["GROQ_API_KEY"] = stt_opts["API_KEY"]
        if stt_opts.get("LANGUAGE"):
            os.environ["STT_LANGUAGE"] = stt_opts["LANGUAGE"]
        if stt_opts.get("API_URL"):
            os.environ["STT_API_URL"] = stt_opts["API_URL"]
        if stt_opts.get("MODEL"):
            os.environ["STT_MODEL"] = stt_opts["MODEL"]

        self._lib_path = Path(lib_path) if lib_path else self._guess_library_path()
        if not self._lib_path.exists():
            self._logger.error("STT library not found: %s", self._lib_path)
            raise STTClientError(f"STT library not found: {self._lib_path}")

        self._lib = ctypes.CDLL(str(self._lib_path))
        self._configure_prototypes()

        if self._lib.stt_initialize() != 0:
            self._logger.error("Native STT initialization failed")
            raise STTClientError("Failed to initialize native STT components")

    def _guess_library_path(self) -> Path:
        # Check config first
        config_path = self._config.get_config("STT_OPTIONS.LIBRARY_PATH")
        if config_path:
            return Path(config_path)

        env_value = os.environ.get("STT_LIBRARY_PATH")
        if env_value:
            return Path(env_value)

        try:
            from src.utils.binary_manager import binary_manager
            path = binary_manager.ensure_stt_lib()
            if path and path.exists():
                return path
        except Exception as e:
            self._logger.warning("Could not resolve STT library path using binary_manager: %s", e)

        platform_map = {
            "Linux": "libstt.so",
            "Darwin": "libstt.dylib",
            "Windows": "stt.dll",
        }
        suffix = platform_map.get(platform.system(), "libstt.so")
        
        # Check architecture-specific subfolder in libs
        arch = platform.machine().lower()
        if arch == "aarch64":
            arch = "arm64"
        elif arch in ("i386", "i686"):
            arch = "x86"
        arch_path = Path(__file__).resolve().parents[2] / "libs" / arch / suffix
        if arch_path.exists():
            return arch_path

        return Path(__file__).resolve().parents[2] / "libs" / "stt" / suffix

    def _configure_prototypes(self) -> None:
        self._lib.stt_initialize.restype = ctypes.c_int
        self._lib.stt_start_recording.restype = ctypes.c_int
        self._lib.stt_stop_recording_and_transcribe.restype = ctypes.c_void_p
        self._lib.stt_free_transcription.argtypes = [ctypes.c_void_p]
        self._lib.stt_is_recording.restype = ctypes.c_int
        self._lib.stt_shutdown.restype = None

    def start_recording(self) -> None:
        """Begin a new STT capture session."""
        self._logger.info("Starting STT recording")
        if self._lib.stt_start_recording() != 0:
            self._logger.error("Native STT start_recording returned failure")
            raise STTClientError("Unable to start the STT recording buffer")

    def stop_recording(self) -> str:
        """Stop the capture and return the transcription (empty if nothing captured)."""
        self._logger.info("Stopping STT recording")
        ptr = self._lib.stt_stop_recording_and_transcribe()
        if not ptr:
            self._logger.warning("Native STT returned no transcription")
            return ""

        raw = ctypes.cast(ptr, ctypes.c_char_p).value
        transcription = raw.decode("utf-8", errors="ignore") if raw else ""
        self._logger.info("Transcription received (%d chars)", len(transcription))
        self._lib.stt_free_transcription(ptr)
        return transcription

    def is_recording(self) -> bool:
        """Answers whether a recording run is in progress."""
        return bool(self._lib.stt_is_recording())

    def shutdown(self) -> None:
        """Release native resources (PortAudio + curl)."""
        self._logger.info("Shutting down native STT")
        self._lib.stt_shutdown()

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass
