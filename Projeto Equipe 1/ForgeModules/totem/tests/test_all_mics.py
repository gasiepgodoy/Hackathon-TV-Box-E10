import numpy as np
import sounddevice as sd
import sys

def main():
    print("=== Diagnostic: Testing all input audio devices ===")
    devices = sd.query_devices()
    input_devices = []
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            input_devices.append((i, d['name']))
            
    if not input_devices:
        print("Error: No input devices found!")
        sys.exit(1)
        
    print(f"Found {len(input_devices)} input devices. Testing 1.5 seconds on each...")
    print("Please make continuous noise/speak while this test runs!\n")
    
    sample_rate = 16000
    duration = 1.5
    
    for idx, name in input_devices:
        print(f"Testing device [{idx}]: {name} ...", end="", flush=True)
        try:
            # We record with 1 channel if supported, otherwise we fall back to max_input_channels
            channels = 1
            # Record
            audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=channels, dtype='int16', device=idx)
            sd.wait()
            
            max_val = np.max(np.abs(audio))
            rms = np.sqrt(np.mean(audio.astype(np.float32)**2))
            
            print(f" Done. Peak: {max_val} | RMS: {rms:.1f}")
        except Exception as e:
            # Try recording with the native maximum channel count of the device
            try:
                max_ch = sd.query_devices(idx)['max_input_channels']
                audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=max_ch, dtype='int16', device=idx)
                sd.wait()
                max_val = np.max(np.abs(audio))
                rms = np.sqrt(np.mean(audio.astype(np.float32)**2))
                print(f" Done (using {max_ch} ch). Peak: {max_val} | RMS: {rms:.1f}")
            except Exception as e2:
                print(f" FAILED to record: {e2}")

if __name__ == "__main__":
    main()
