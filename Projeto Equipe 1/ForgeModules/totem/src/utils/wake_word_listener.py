import os
import threading
from pathlib import Path
from typing import Callable, Optional

from src.utils.config_manager import ConfigManager
from src.utils.logging_config import get_logger
from src.utils.resource_finder import resource_finder


class WakeWordListener:
    """Background wake-word listener powered by Picovoice Porcupine."""

    def __init__(
        self,
        on_detected: Callable[[], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self._logger = get_logger(__name__)
        self._config = ConfigManager.get_instance()
        self._on_detected = on_detected
        self._on_error = on_error
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._porcupine = None
        self._recorder = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._cleanup()

    def _resolve_file(self, raw_path: str) -> Optional[Path]:
        if not raw_path:
            return None
        candidate = Path(raw_path)
        if candidate.is_file():
            return candidate
        found = resource_finder.find_file(raw_path)
        if found and found.is_file():
            return found
        base = resource_finder.get_project_root()
        alt = base / raw_path
        if alt.is_file():
            return alt
        return candidate

    def _get_access_key(self) -> Optional[str]:
        config_key = self._config.get_config("WAKE_WORD_OPTIONS.ACCESS_KEY")
        if config_key:
            return config_key
        return os.environ.get("picovoicekey") or os.environ.get("PICOVOICEKEY")

    def _run(self) -> None:
        try:
            access_key = self._get_access_key()
            if not access_key:
                raise RuntimeError("Missing Picovoice access key in $picovoicekey")

            model_path = self._config.get_config(
                "WAKE_WORD_OPTIONS.PORCUPINE_MODEL_PATH", ""
            )
            keyword_path = self._config.get_config(
                "WAKE_WORD_OPTIONS.PORCUPINE_KEYWORD_PATH", ""
            )
            audio_device_index = self._config.get_config(
                "WAKE_WORD_OPTIONS.AUDIO_DEVICE_INDEX", None
            )

            model_file = self._resolve_file(str(model_path)) if model_path else None
            keyword_file = (
                self._resolve_file(str(keyword_path)) if keyword_path else None
            )

            if not model_file or not model_file.exists():
                raise RuntimeError("Porcupine model file not found")
            if not keyword_file or not keyword_file.exists():
                raise RuntimeError("Porcupine keyword (.ppn) file not found")

            import pvporcupine
            from pvrecorder import PvRecorder

            self._porcupine = pvporcupine.create(
                access_key=access_key,
                model_path=str(model_file),
                keyword_paths=[str(keyword_file)],
            )

            device_index = -1
            try:
                if audio_device_index is not None:
                    device_index = int(audio_device_index)
            except Exception:
                device_index = -1

            self._recorder = PvRecorder(
                frame_length=self._porcupine.frame_length,
                device_index=device_index,
            )
            self._recorder.start()

            self._logger.info("Wake word listener started")
            while not self._stop_event.is_set():
                pcm = self._recorder.read()
                result = self._porcupine.process(pcm)
                if result >= 0:
                    self._logger.info("Wake word detected")
                    try:
                        self._on_detected()
                    except Exception:
                        self._logger.error("Wake word callback failed", exc_info=True)

        except Exception as exc:
            self._logger.error("Wake word listener error", exc_info=True)
            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception:
                    self._logger.error("Wake word error callback failed", exc_info=True)
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        try:
            if self._recorder:
                self._recorder.delete()
        except Exception:
            pass
        finally:
            self._recorder = None
        try:
            if self._porcupine:
                self._porcupine.delete()
        except Exception:
            pass
        finally:
            self._porcupine = None
