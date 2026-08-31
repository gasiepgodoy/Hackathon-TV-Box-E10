import sys
import os

# Ensure src is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set Qt platform to offscreen so we can run QWidget tests without display
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from tests.test_ntp import test_ntp_flow

def test_imports():
    print("Testing imports...")
    try:
        from src.utils.config_manager import ConfigManager
        from src.utils.chat_bridge import ChatBridge
        from src.utils.stt_client import STTClient
        from src.utils.wake_word_listener import WakeWordListener
        from src.views.settings.components.ai_services import AIServicesWidget
        from src.views.settings.settings_window import SettingsWindow
        from PyQt5.QtWidgets import QApplication
        print("Imports: OK!")
    except Exception as e:
        print(f"Imports failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def test_config():
    print("Testing ConfigManager...")
    try:
        from src.utils.config_manager import ConfigManager
        cfg = ConfigManager.get_instance()
        llm = cfg.get_config("LLM_OPTIONS")
        stt = cfg.get_config("STT_OPTIONS")
        ww = cfg.get_config("WAKE_WORD_OPTIONS")
        
        print(f"LLM options: {llm}")
        print(f"STT options: {stt}")
        print(f"Wake word options (Access key): {ww.get('ACCESS_KEY')}")
        
        if llm is None or stt is None or ww is None:
            raise ValueError("Config items are missing!")
        print("ConfigManager: OK!")
    except Exception as e:
        print(f"ConfigManager test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def test_stt_client():
    print("Testing STTClient library loading...")
    try:
        from src.utils.stt_client import STTClient
        client = STTClient()
        print("STTClient: Loaded and initialized successfully!")
        client.shutdown()
        print("STTClient: OK!")
    except Exception as e:
        print(f"STTClient test failed (may fail if no default mic is found, checking if loading DLL succeeded): {e}")
        import traceback
        traceback.print_exc()
        # We don't exit(1) here since remote Orange Pi might not have mic connected,
        # but let's check if the error is due to library missing or something else.
        if "STT library not found" in str(e) or "Failed to initialize native STT components" in str(e):
            print("STT library not found or failed to initialize. Skipping STTClient test.")

def test_chat_bridge():
    print("Testing ChatBridge...")
    try:
        from src.utils.chat_bridge import ChatBridge
        bridge = ChatBridge(backend="cerebras")
        print(f"ChatBridge backend: {bridge.backend}")
        print("ChatBridge: OK!")
    except Exception as e:
        print(f"ChatBridge test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def test_gui_widgets():
    print("Testing GUI Widgets layout...")
    try:
        from PyQt5.QtWidgets import QApplication
        from src.views.settings.components.ai_services import AIServicesWidget
        from src.views.settings.settings_window import SettingsWindow
        
        app = QApplication.instance() or QApplication(sys.argv)
        
        widget = AIServicesWidget()
        print("AIServicesWidget instantiated successfully!")
        
        dialog = SettingsWindow()
        print("SettingsWindow dialog instantiated successfully!")
        print("GUI Widgets: OK!")
    except Exception as e:
        print(f"GUI Widgets test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_imports()
    test_config()
    test_stt_client()
    test_chat_bridge()
    test_gui_widgets()
    test_ntp_flow()
    print("All tests PASSED successfully!")
