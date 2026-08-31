from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QDoubleSpinBox, QSpinBox, QLabel, QScrollArea
)

from src.utils.config_manager import ConfigManager
from src.utils.logging_config import get_logger

class AIServicesWidget(QWidget):
    """
    Widget for configuring LLM, STT, and TTS services.
    """
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger(__name__)
        self.config_manager = ConfigManager.get_instance()
        
        self.ui_controls = {}
        self._setup_ui()
        self._connect_events()
        self._load_config_values()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Scroll area for clean overflow handling if needed
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # --- LLM Options Group ---
        llm_group = QGroupBox("LLM Options (Large Language Model)")
        llm_layout = QFormLayout()
        
        self.llm_backend_combo = QComboBox()
        self.llm_backend_combo.addItems(["cerebras", "groq", "openai", "ollama", "binary"])
        
        self.llm_api_key_edit = QLineEdit()
        self.llm_api_key_edit.setEchoMode(QLineEdit.Password)
        self.llm_api_key_edit.setPlaceholderText("Enter API Key (falls back to env var if empty)")
        
        self.llm_model_edit = QLineEdit()
        self.llm_model_edit.setPlaceholderText("e.g. zai-glm-4.7, llama3-8b-8192")
        
        self.llm_url_edit = QLineEdit()
        self.llm_url_edit.setPlaceholderText("Leave empty for default API URL")
        
        self.llm_temp_spin = QDoubleSpinBox()
        self.llm_temp_spin.setRange(0.0, 2.0)
        self.llm_temp_spin.setSingleStep(0.1)
        self.llm_temp_spin.setValue(0.7)
        
        self.llm_max_tokens_spin = QSpinBox()
        self.llm_max_tokens_spin.setRange(1, 8192)
        self.llm_max_tokens_spin.setValue(2048)
        
        llm_layout.addRow(QLabel("Backend:"), self.llm_backend_combo)
        llm_layout.addRow(QLabel("API Key:"), self.llm_api_key_edit)
        llm_layout.addRow(QLabel("Model Name:"), self.llm_model_edit)
        llm_layout.addRow(QLabel("API URL:"), self.llm_url_edit)
        llm_layout.addRow(QLabel("Temperature:"), self.llm_temp_spin)
        llm_layout.addRow(QLabel("Max Tokens:"), self.llm_max_tokens_spin)
        llm_group.setLayout(llm_layout)
        scroll_layout.addWidget(llm_group)
        
        # --- STT Options Group ---
        stt_group = QGroupBox("STT Options (Speech to Text)")
        stt_layout = QFormLayout()
        
        self.stt_api_key_edit = QLineEdit()
        self.stt_api_key_edit.setEchoMode(QLineEdit.Password)
        self.stt_api_key_edit.setPlaceholderText("Enter STT API Key (Groq / OpenAI API key)")
        
        self.stt_model_edit = QLineEdit()
        self.stt_model_edit.setPlaceholderText("e.g. whisper-large-v3")
        
        self.stt_lang_edit = QLineEdit()
        self.stt_lang_edit.setPlaceholderText("e.g. pt, en")
        
        self.stt_url_edit = QLineEdit()
        self.stt_url_edit.setPlaceholderText("Groq STT API URL (e.g. https://api.groq.com/...)")
        
        self.stt_lib_path_edit = QLineEdit()
        self.stt_lib_path_edit.setPlaceholderText("Leave empty to auto-detect")
        
        stt_layout.addRow(QLabel("API Key:"), self.stt_api_key_edit)
        stt_layout.addRow(QLabel("Model Name:"), self.stt_model_edit)
        stt_layout.addRow(QLabel("Language (ISO-639-1):"), self.stt_lang_edit)
        stt_layout.addRow(QLabel("API URL:"), self.stt_url_edit)
        stt_layout.addRow(QLabel("Native Library Path:"), self.stt_lib_path_edit)
        stt_group.setLayout(stt_layout)
        scroll_layout.addWidget(stt_group)
        
        # --- TTS Options Group ---
        tts_group = QGroupBox("TTS Options (Text to Speech)")
        tts_layout = QFormLayout()
        
        self.tts_enabled_check = QCheckBox("Enable TTS Voice Response")
        self.tts_url_edit = QLineEdit()
        self.tts_voice_edit = QLineEdit()
        self.tts_rate_edit = QLineEdit()
        self.tts_pitch_edit = QLineEdit()
        self.tts_volume_edit = QLineEdit()
        
        tts_layout.addRow(self.tts_enabled_check)
        tts_layout.addRow(QLabel("API URL:"), self.tts_url_edit)
        tts_layout.addRow(QLabel("Voice ID:"), self.tts_voice_edit)
        tts_layout.addRow(QLabel("Speech Rate:"), self.tts_rate_edit)
        tts_layout.addRow(QLabel("Speech Pitch:"), self.tts_pitch_edit)
        tts_layout.addRow(QLabel("Speech Volume:"), self.tts_volume_edit)
        tts_group.setLayout(tts_layout)
        scroll_layout.addWidget(tts_group)
        
        # --- Wake Word Keys ---
        ww_keys_group = QGroupBox("Picovoice Porcupine Access Key")
        ww_keys_layout = QFormLayout()
        self.picovoice_key_edit = QLineEdit()
        self.picovoice_key_edit.setEchoMode(QLineEdit.Password)
        self.picovoice_key_edit.setPlaceholderText("Enter Picovoice Access Key")
        ww_keys_layout.addRow(QLabel("Access Key:"), self.picovoice_key_edit)
        ww_keys_group.setLayout(ww_keys_layout)
        scroll_layout.addWidget(ww_keys_group)
        
        # Register ui controls
        self.ui_controls = {
            "llm_backend": self.llm_backend_combo,
            "llm_api_key": self.llm_api_key_edit,
            "llm_model": self.llm_model_edit,
            "llm_url": self.llm_url_edit,
            "llm_temp": self.llm_temp_spin,
            "llm_max_tokens": self.llm_max_tokens_spin,
            "stt_api_key": self.stt_api_key_edit,
            "stt_model": self.stt_model_edit,
            "stt_lang": self.stt_lang_edit,
            "stt_url": self.stt_url_edit,
            "stt_lib_path": self.stt_lib_path_edit,
            "tts_enabled": self.tts_enabled_check,
            "tts_url": self.tts_url_edit,
            "tts_voice": self.tts_voice_edit,
            "tts_rate": self.tts_rate_edit,
            "tts_pitch": self.tts_pitch_edit,
            "tts_volume": self.tts_volume_edit,
            "picovoice_key": self.picovoice_key_edit
        }
        
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)
        self.setLayout(main_layout)

    def _connect_events(self):
        for control in self.ui_controls.values():
            if isinstance(control, QLineEdit):
                control.textChanged.connect(self.settings_changed.emit)
            elif isinstance(control, QComboBox):
                control.currentTextChanged.connect(self.settings_changed.emit)
            elif isinstance(control, QCheckBox):
                control.stateChanged.connect(self.settings_changed.emit)
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.valueChanged.connect(self.settings_changed.emit)

    def _load_config_values(self):
        try:
            # Load LLM Options
            llm_opts = self.config_manager.get_config("LLM_OPTIONS", {})
            self.llm_backend_combo.setCurrentText(llm_opts.get("BACKEND", "cerebras"))
            self.llm_api_key_edit.setText(llm_opts.get("API_KEY", ""))
            self.llm_model_edit.setText(llm_opts.get("MODEL", ""))
            self.llm_url_edit.setText(llm_opts.get("API_URL", ""))
            self.llm_temp_spin.setValue(float(llm_opts.get("TEMPERATURE", 0.7)))
            self.llm_max_tokens_spin.setValue(int(llm_opts.get("MAX_TOKENS", 2048)))

            # Load STT Options
            stt_opts = self.config_manager.get_config("STT_OPTIONS", {})
            self.stt_api_key_edit.setText(stt_opts.get("API_KEY", ""))
            self.stt_model_edit.setText(stt_opts.get("MODEL", ""))
            self.stt_lang_edit.setText(stt_opts.get("LANGUAGE", "pt"))
            self.stt_url_edit.setText(stt_opts.get("API_URL", ""))
            self.stt_lib_path_edit.setText(stt_opts.get("LIBRARY_PATH", ""))

            # Load TTS Options
            tts_opts = self.config_manager.get_config("TTS_OPTIONS", {})
            self.tts_enabled_check.setChecked(tts_opts.get("ENABLED", True))
            self.tts_url_edit.setText(tts_opts.get("API_URL", ""))
            self.tts_voice_edit.setText(tts_opts.get("VOICE", ""))
            self.tts_rate_edit.setText(tts_opts.get("RATE", ""))
            self.tts_pitch_edit.setText(tts_opts.get("PITCH", ""))
            self.tts_volume_edit.setText(tts_opts.get("VOLUME", ""))

            # Load Wake Word options (picovoice key)
            picovoice_key = self.config_manager.get_config("WAKE_WORD_OPTIONS.ACCESS_KEY", "")
            self.picovoice_key_edit.setText(picovoice_key)

        except Exception as e:
            self.logger.error(f"Error loading AI Services configuration: {e}", exc_info=True)

    def get_config_data(self) -> dict:
        config_data = {}
        try:
            # Collect LLM Options
            config_data["LLM_OPTIONS.BACKEND"] = self.llm_backend_combo.currentText()
            config_data["LLM_OPTIONS.API_KEY"] = self.llm_api_key_edit.text().strip()
            config_data["LLM_OPTIONS.MODEL"] = self.llm_model_edit.text().strip()
            config_data["LLM_OPTIONS.API_URL"] = self.llm_url_edit.text().strip()
            config_data["LLM_OPTIONS.TEMPERATURE"] = self.llm_temp_spin.value()
            config_data["LLM_OPTIONS.MAX_TOKENS"] = self.llm_max_tokens_spin.value()

            # Collect STT Options
            config_data["STT_OPTIONS.API_KEY"] = self.stt_api_key_edit.text().strip()
            config_data["STT_OPTIONS.MODEL"] = self.stt_model_edit.text().strip()
            config_data["STT_OPTIONS.LANGUAGE"] = self.stt_lang_edit.text().strip()
            config_data["STT_OPTIONS.API_URL"] = self.stt_url_edit.text().strip()
            config_data["STT_OPTIONS.LIBRARY_PATH"] = self.stt_lib_path_edit.text().strip()

            # Collect TTS Options
            config_data["TTS_OPTIONS.ENABLED"] = self.tts_enabled_check.isChecked()
            config_data["TTS_OPTIONS.API_URL"] = self.tts_url_edit.text().strip()
            config_data["TTS_OPTIONS.VOICE"] = self.tts_voice_edit.text().strip()
            config_data["TTS_OPTIONS.RATE"] = self.tts_rate_edit.text().strip()
            config_data["TTS_OPTIONS.PITCH"] = self.tts_pitch_edit.text().strip()
            config_data["TTS_OPTIONS.VOLUME"] = self.tts_volume_edit.text().strip()

            # Collect Wake Word options
            config_data["WAKE_WORD_OPTIONS.ACCESS_KEY"] = self.picovoice_key_edit.text().strip()

        except Exception as e:
            self.logger.error(f"Error gathering AI Services settings: {e}", exc_info=True)
            
        return config_data

    def reset_to_defaults(self):
        try:
            default_config = ConfigManager.DEFAULT_CONFIG
            
            # Reset LLM
            llm_def = default_config.get("LLM_OPTIONS", {})
            self.llm_backend_combo.setCurrentText(llm_def.get("BACKEND", "cerebras"))
            self.llm_api_key_edit.setText("")
            self.llm_model_edit.setText(llm_def.get("MODEL", "zai-glm-4.7"))
            self.llm_url_edit.setText(llm_def.get("API_URL", "https://api.cerebras.ai/v1/chat/completions"))
            self.llm_temp_spin.setValue(0.7)
            self.llm_max_tokens_spin.setValue(2048)

            # Reset STT
            stt_def = default_config.get("STT_OPTIONS", {})
            self.stt_api_key_edit.setText("")
            self.stt_model_edit.setText(stt_def.get("MODEL", "whisper-large-v3"))
            self.stt_lang_edit.setText(stt_def.get("LANGUAGE", "pt"))
            self.stt_url_edit.setText(stt_def.get("API_URL", "https://api.groq.com/openai/v1/audio/transcriptions"))
            self.stt_lib_path_edit.setText("")

            # Reset TTS
            tts_def = default_config.get("TTS_OPTIONS", {})
            self.tts_enabled_check.setChecked(tts_def.get("ENABLED", True))
            self.tts_url_edit.setText(tts_def.get("API_URL", "http://localhost:8000"))
            self.tts_voice_edit.setText(tts_def.get("VOICE", "pt-BR-FranciscaNeural"))
            self.tts_rate_edit.setText(tts_def.get("RATE", "+15%"))
            self.tts_pitch_edit.setText(tts_def.get("PITCH", "+3Hz"))
            self.tts_volume_edit.setText(tts_def.get("VOLUME", "+0%"))

            # Reset Picovoice Key
            self.picovoice_key_edit.setText("")

        except Exception as e:
            self.logger.error(f"Error resetting AI Services configuration: {e}", exc_info=True)
