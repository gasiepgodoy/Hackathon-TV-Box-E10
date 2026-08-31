import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from src.utils.logging_config import get_logger

logger = get_logger(__name__)

EVENT_MESSAGE = "<<< FALA TERMINOU"


class VADCppProcess:
    """Run the vad_cpp binary and translate its output into `on_timeout` calls."""

    def __init__(self, vad_options: Dict[str, Any], project_root: Path):
        self._project_root = project_root
        self._binary_path = self._resolve_path(
            vad_options.get("CPP_BINARY_PATH", "vad_cpp/build/vad_cpp")
        )
        self._config_path = self._resolve_path(
            vad_options.get("CPP_CONFIG_PATH", "config/config.json")
        )
        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._timeout_event = threading.Event()

    def _resolve_path(self, value: Any) -> Path:
        candidate = Path(str(value)) if value is not None else Path()
        if candidate.is_absolute():
            return candidate
        return self._project_root / candidate

    def start(self, on_timeout: Callable[[], None]) -> None:
        if self._process is not None:
            return
        if not self._binary_path.exists():
            raise FileNotFoundError(f"vad_cpp binary not found at {self._binary_path}")
        if not self._config_path.exists():
            logger.warning("vad_cpp config %s missing; process may use defaults", self._config_path)
        self._stop_event.clear()
        self._timeout_event.clear()
        args = [str(self._binary_path), "--config", str(self._config_path)]
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(self._project_root),
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_output, args=(on_timeout,), daemon=True)
        self._reader.start()

    def _trigger_timeout(self, callback: Callable[[], None]) -> None:
        if self._timeout_event.is_set():
            return
        self._timeout_event.set()
        try:
            callback()
        except Exception:
            logger.exception("on_timeout callback raised an exception")

    def _read_output(self, callback: Callable[[], None]) -> None:
        assert self._process is not None
        if not self._process.stdout:
            return
        try:
            for raw_line in self._process.stdout:
                if self._stop_event.is_set():
                    break
                line = raw_line.strip()
                if not line:
                    continue
                logger.debug("vad_cpp: %s", line)
                if EVENT_MESSAGE in line:
                    self._trigger_timeout(callback)
                    break
                if self._process.poll() is not None:
                    break
        finally:
            self._cleanup()

    def stop(self) -> None:
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._reader:
            self._reader.join(timeout=1)
        self._cleanup()

    def _cleanup(self) -> None:
        if self._process and self._process.stdout:
            self._process.stdout.close()
        self._process = None
        self._reader = None
