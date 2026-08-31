import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

import numpy as np
import onnxruntime as ort
import sounddevice as sd

from src.utils.config_manager import ConfigManager
from src.utils.logging_config import get_logger
from src.utils.vad_cpp_helper import VADCppProcess

logger = get_logger(__name__)


class VADMonitor:
    """Simple VAD monitor using a Silero ONNX model and a PortAudio input stream."""

    def __init__(self):
        cfg = ConfigManager.get_instance()
        vad_cfg = cfg.get_config("VAD_OPTIONS", {})
        self.enabled = bool(vad_cfg.get("ENABLED", True))
        model_path_str = vad_cfg.get("MODEL_PATH", "silero_vad.onnx")
        repo_root = Path(__file__).resolve().parents[2]
        self._project_root = repo_root
        self.model_path = str((repo_root / model_path_str).resolve())
        self.sample_rate = int(vad_cfg.get("SAMPLE_RATE", 16000))
        self.frame_size = int(vad_cfg.get("FRAME_SIZE", 512))
        self.channels = int(vad_cfg.get("CHANNELS", 1))
        self.threshold = float(vad_cfg.get("THRESHOLD", 0.5))
        self.timeout_seconds = float(vad_cfg.get("TIMEOUT_SECONDS", 3.0))
        self._vad_options: Dict[str, object] = vad_cfg
        self._use_cpp = bool(vad_cfg.get("USE_CPP_BINARY", False))

        self._sess: Optional[ort.InferenceSession] = None
        self._inp_name = None
        self._state_name = None
        self._sr_name = None
        self._state = None

        self._stream: Optional[sd.InputStream] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cpp_monitor: Optional[VADCppProcess] = None
        self._on_timeout: Optional[Callable[[], None]] = None

        self._speech_active = False
        self._speech_timer = 0.0
        self._last_time = time.time()

    def _init_model(self):
        if self._sess is not None:
            return
        self._sess = ort.InferenceSession(self.model_path, providers=["CPUExecutionProvider"])
        inputs = self._sess.get_inputs()
        self._inp_name = inputs[0].name
        if len(inputs) >= 3:
            self._state_name = inputs[1].name
            self._sr_name = inputs[2].name
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr = np.array(self.sample_rate, dtype=np.int64)

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            return
        self._process_frame(indata[:, 0])

    def _process_frame(self, audio):
        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        audio = audio.reshape(1, -1).astype(np.float32)
        out, self._state = self._sess.run(
            None,
            {self._inp_name: audio, self._state_name: self._state, self._sr_name: self._sr},
        )
        score = float(out[0][0])

        if score > self.threshold:
            self._speech_timer = self.timeout_seconds
            if not self._speech_active:
                self._speech_active = True
        else:
            if self._speech_timer > 0:
                self._speech_timer -= dt
            if self._speech_active and self._speech_timer <= 0:
                self._speech_active = False
                if self._on_timeout:
                    try:
                        self._on_timeout()
                    except Exception:
                        pass

    def _start_cpp_monitor(self) -> bool:
        if not self._use_cpp:
            return False
        try:
            self._cpp_monitor = VADCppProcess(self._vad_options, project_root=self._project_root)
            self._cpp_monitor.start(self._on_timeout)
            return True
        except FileNotFoundError as exc:
            logger.warning("vad_cpp helper missing binary: %s", exc)
        except Exception:
            logger.exception("Failed to launch vad_cpp helper; falling back to python monitor")
        self._cpp_monitor = None
        self._use_cpp = False
        return False

    def start(self, on_timeout: Callable[[], None]) -> None:
        if not self.enabled:
            return
        if self._running:
            return
        self._on_timeout = on_timeout
        if self._start_cpp_monitor():
            self._running = True
            return
        self._init_model()
        self._running = True
        self._last_time = time.time()
        self._speech_timer = 0.0
        self._speech_active = False

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.frame_size,
            channels=self.channels,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._cpp_monitor:
            self._cpp_monitor.stop()
            self._cpp_monitor = None
            self._running = False
            return
        if not self._running:
            return
        self._running = False
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None


if __name__ == "__main__":
    print("VADMonitor module")
