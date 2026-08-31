import json
import uuid
from typing import Any, Dict

from src.utils.logging_config import get_logger
from src.utils.resource_finder import resource_finder

logger = get_logger(__name__)


class ConfigManager:
    """Configuration manager - singleton."""

    _instance = None

    # Default configuration.
    DEFAULT_CONFIG = {
        "SYSTEM_OPTIONS": {
            "CLIENT_ID": None,
            "DEVICE_ID": None,
            "NETWORK": {
                "OTA_VERSION_URL": "https://api.tenclass.net/xiaozhi/ota/",
                "WEBSOCKET_URL": None,
                "WEBSOCKET_ACCESS_TOKEN": None,
                "MQTT_INFO": None,
                "ACTIVATION_VERSION": "v2",  # Optional values: v1, v2
                "AUTHORIZATION_URL": "https://xiaozhi.me/",
            },
            # seconds before auto-stopping listening in AUTO_STOP mode
            "LISTENING_AUTO_STOP_SECONDS": 60,
        },
        "WEBHOOKS": {
            # URL to call when listening starts. Example: "http://example.local/hooks/listen_start"
            "on_listening_start": None,
            # URL to call when listening stops/returns to idle. Example: "http://example.local/hooks/listen_stop"
            "on_listening_stop": None,
        },
        "WAKE_WORD_OPTIONS": {
            "USE_WAKE_WORD": True,
            "ACCESS_KEY": "",
            "MODEL_PATH": "models",
            "PORCUPINE_MODEL_PATH": "",
            "PORCUPINE_KEYWORD_PATH": "",
            "AUDIO_DEVICE_INDEX": None,
            "NUM_THREADS": 4,
            "PROVIDER": "cpu",
            "MAX_ACTIVE_PATHS": 2,
            "KEYWORDS_SCORE": 1.8,
            "KEYWORDS_THRESHOLD": 0.2,
            "NUM_TRAILING_BLANKS": 1,
        },
        "CAMERA": {
            "camera_index": 0,
            "frame_width": 640,
            "frame_height": 480,
            "fps": 30,
            "Local_VL_url": "https://open.bigmodel.cn/api/paas/v4/",
            "VLapi_key": "",
            "models": "glm-4v-plus",
        },
        "SHORTCUTS": {
            "ENABLED": True,
            "MANUAL_PRESS": {"modifier": "ctrl", "key": "j", "description": "Hold to talk"},
            "AUTO_TOGGLE": {"modifier": "ctrl", "key": "k", "description": "Auto dialogue"},
            "ABORT": {"modifier": "ctrl", "key": "q", "description": "Interrupt dialogue"},
            "MODE_TOGGLE": {"modifier": "ctrl", "key": "m", "description": "Toggle mode"},
            "WINDOW_TOGGLE": {
                "modifier": "ctrl",
                "key": "w",
                "description": "Show/Hide window",
            },
        },
        "AEC_OPTIONS": {
            "ENABLED": False,
            "BUFFER_MAX_LENGTH": 200,
            "FRAME_DELAY": 3,
            "FILTER_LENGTH_RATIO": 0.4,
            "ENABLE_PREPROCESS": True,
        },
        "AUDIO_DEVICES": {
            "input_device_id": None,
            "input_device_name": None,
            "output_device_id": None,
            "output_device_name": None,
            "input_sample_rate": None,
            "output_sample_rate": None,
            "input_channels": None,
            "output_channels": None,
        },
        "VAD_OPTIONS": {
            "ENABLED": True,
            "MODEL_PATH": "models/silero_vad.onnx",
            "SAMPLE_RATE": 16000,
            "FRAME_SIZE": 512,
            "CHANNELS": 1,
            "THRESHOLD": 0.5,
            "TIMEOUT_SECONDS": 3.0,
            "USE_CPP_BINARY": False,
            "CPP_BINARY_PATH": "vad_cpp/build/vad_cpp",
            "CPP_CONFIG_PATH": "config/config.json",
        },
        "TTS_OPTIONS": {
            "ENABLED": True,
            "API_URL": "http://localhost:8000",
            "VOICE": "pt-BR-FranciscaNeural",
            "RATE": "+15%",
            "PITCH": "+3Hz",
            "VOLUME": "+0%",
        },
        "LLM_OPTIONS": {
            "ENABLED": True,
            "BACKEND": "cerebras",
            "API_KEY": "",
            "MODEL": "zai-glm-4.7",
            "API_URL": "https://api.cerebras.ai/v1/chat/completions",
            "TEMPERATURE": 0.7,
            "MAX_TOKENS": 2048,
        },
        "STT_OPTIONS": {
            "ENABLED": True,
            "API_KEY": "",
            "MODEL": "whisper-large-v3",
            "LANGUAGE": "pt",
            "API_URL": "https://api.groq.com/openai/v1/audio/transcriptions",
            "LIBRARY_PATH": "",
        },
    }

    def __new__(cls):
        """
        Ensure singleton mode.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """
        Initialize the configuration manager.
        """
        if self._initialized:
            return
        self._initialized = True

        # Initialize config file paths.
        self._init_config_paths()

        # Ensure required directories exist.
        self._ensure_required_directories()

        # Load configuration.
        self._config = self._load_config()

    def _init_config_paths(self):
        """
        Initialize config file paths.
        """
        # Use resource_finder to locate or create config directory.
        self.config_dir = resource_finder.find_config_dir()
        if not self.config_dir:
            # Create config directory under project root if missing.
            project_root = resource_finder.get_project_root()
            self.config_dir = project_root / "config"
            self.config_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created config directory: {self.config_dir.absolute()}")

        self.config_file = self.config_dir / "config.json"

        # Log config file paths.
        logger.info(f"Config directory: {self.config_dir.absolute()}")
        logger.info(f"Config file: {self.config_file.absolute()}")

    def _ensure_required_directories(self):
        """
        Ensure required directories exist.
        """
        project_root = resource_finder.get_project_root()

        # Create models directory.
        models_dir = project_root / "models"
        if not models_dir.exists():
            models_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created models directory: {models_dir.absolute()}")

        # Create cache directory.
        cache_dir = project_root / "cache"
        if not cache_dir.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created cache directory: {cache_dir.absolute()}")

    def _load_config(self) -> Dict[str, Any]:
        """
        Load config file, creating it if missing.
        """
        try:
            # Try to find config file with resource_finder.
            config_file_path = resource_finder.find_file("config/config.json")

            if config_file_path:
                logger.debug(f"Found config file via resource_finder: {config_file_path}")
                config = json.loads(config_file_path.read_text(encoding="utf-8"))
                return self._merge_configs(self.DEFAULT_CONFIG, config)

            # If not found, try instance path.
            if self.config_file.exists():
                logger.debug(f"Found config file via instance path: {self.config_file}")
                config = json.loads(self.config_file.read_text(encoding="utf-8"))
                return self._merge_configs(self.DEFAULT_CONFIG, config)
            else:
                # Create default config file.
                logger.info("Config file missing; creating default configuration.")
                self._save_config(self.DEFAULT_CONFIG)
                return self.DEFAULT_CONFIG.copy()

        except Exception as e:
            logger.error(f"Config load error: {e}")
            return self.DEFAULT_CONFIG.copy()

    def _save_config(self, config: dict) -> bool:
        """
        Save configuration to file.
        """
        try:
            # Ensure config directory exists.
            self.config_dir.mkdir(parents=True, exist_ok=True)

            # Save config file.
            self.config_file.write_text(
                json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.debug(f"Config saved to: {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"Config save error: {e}")
            return False

    @staticmethod
    def _merge_configs(default: dict, custom: dict) -> dict:
        """
        Recursively merge configuration dictionaries.
        """
        result = default.copy()
        for key, value in custom.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ConfigManager._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def get_config(self, path: str, default: Any = None) -> Any:
        """
        Get configuration value by path.
        path: Dot-separated config path, e.g. "SYSTEM_OPTIONS.NETWORK.MQTT_INFO"
        """
        try:
            value = self._config
            for key in path.split("."):
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def update_config(self, path: str, value: Any) -> bool:
        """
        Update a specific configuration value.
        path: Dot-separated config path, e.g. "SYSTEM_OPTIONS.NETWORK.MQTT_INFO"
        """
        try:
            current = self._config
            *parts, last = path.split(".")
            for part in parts:
                current = current.setdefault(part, {})
            current[last] = value
            return self._save_config(self._config)
        except Exception as e:
            logger.error(f"Config update error {path}: {e}")
            return False

    def reload_config(self) -> bool:
        """
        Reload the configuration file.
        """
        try:
            self._config = self._load_config()
            logger.info("Configuration file reloaded.")
            return True
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            return False

    def initialize_client_id(self):
        """
        Ensure a client ID exists.
        """
        if not self.get_config("SYSTEM_OPTIONS.CLIENT_ID"):
            client_id = str(uuid.uuid4())
            success = self.update_config("SYSTEM_OPTIONS.CLIENT_ID", client_id)
            if success:
                logger.info(f"Generated new client ID: {client_id}")
            else:
                logger.error("Failed to save new client ID.")

    @classmethod
    def get_instance(cls):
        """
        Get the configuration manager instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
