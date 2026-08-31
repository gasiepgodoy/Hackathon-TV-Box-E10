import os
import sys
import platform
import json
from pathlib import Path

# Try importing dependencies
try:
    import pvporcupine
    from pvrecorder import PvRecorder
except ImportError:
    print("Error: Picovoice libraries are missing.")
    print("Please install them using: pip install pvporcupine pvrecorder")
    sys.exit(1)

def get_access_key():
    # 1. Try reading from config.json
    config_path = Path(__file__).parent / "config" / "config.json"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                key = config.get("WAKE_WORD_OPTIONS", {}).get("ACCESS_KEY")
                if key:
                    return key
        except Exception:
            pass

    # 2. Try environment variables
    key = os.environ.get("PICOVOICE_ACCESS_KEY") or os.environ.get("PICOVOICEKEY") or os.environ.get("picovoicekey")
    if key:
        return key

    # 3. Prompt user if run interactively
    print("\n--- Picovoice Access Key Needed ---")
    print("Sign up for a free key at: https://console.picovoice.ai/")
    user_key = input("Enter your Picovoice Access Key: ").strip()
    return user_key

def main():
    print("=== stand-alone Wake Word Test (Porcupine) ===")
    
    access_key = get_access_key()
    if not access_key:
        print("Error: No Access Key provided. Exiting.")
        sys.exit(1)

    system = platform.system().lower()
    machine = platform.machine().lower()
    print(f"Detected OS: {system} | Architecture: {machine}")

    # Determine paths
    project_root = Path(__file__).parent
    model_path = project_root / "models" / "porcupine_params_pt.pv"
    
    # Resolve keyword file depending on OS/architecture
    if system == "windows":
        keyword_path = project_root / "keywords" / "keyword_files_pt" / "windows" / "abacaxi_windows.ppn"
    elif system == "darwin":
        keyword_path = project_root / "keywords" / "keyword_files_pt" / "mac" / "abacaxi_mac.ppn"
    else: # Linux
        if "arm" in machine or "aarch" in machine:
            keyword_path = project_root / "keywords" / "keyword_files_pt" / "raspberry-pi" / "abacaxi_raspberry-pi.ppn"
        else:
            keyword_path = project_root / "keywords" / "keyword_files_pt" / "linux" / "abacaxi_linux.ppn"

    print(f"Using model file: {model_path}")
    print(f"Using keyword file: {keyword_path}")

    if not model_path.exists():
        print(f"Error: Model file {model_path} does not exist.")
        sys.exit(1)
    if not keyword_path.exists():
        print(f"Error: Keyword file {keyword_path} does not exist.")
        sys.exit(1)

    # Initialize Porcupine
    try:
        porcupine = pvporcupine.create(
            access_key=access_key,
            model_path=str(model_path),
            keyword_paths=[str(keyword_path)]
        )
    except Exception as e:
        print(f"Failed to initialize Porcupine: {e}")
        sys.exit(1)

    # Initialize Recorder
    recorder = PvRecorder(device_index=-1, frame_length=porcupine.frame_length)
    
    try:
        print("\n--- Audio Devices Available ---")
        for i, device in enumerate(PvRecorder.get_audio_devices()):
            print(f"[{i}]: {device}")
        
        print(f"\nUsing default input device: {recorder.selected_device}")
        recorder.start()
        print("\n>>> [LISTENING] Speak the wake word: 'ABACAXI'...")
        print("Press Ctrl+C to stop.\n")

        while True:
            pcm = recorder.read()
            result = porcupine.process(pcm)
            if result >= 0:
                print("🎉 [WAKE WORD DETECTED] !!! (Detected: 'ABACAXI')")
                
    except KeyboardInterrupt:
        print("\nStopping wake word listener...")
    finally:
        recorder.stop()
        recorder.delete()
        porcupine.delete()
        print("Cleaned up resources. Goodbye!")

if __name__ == "__main__":
    main()
