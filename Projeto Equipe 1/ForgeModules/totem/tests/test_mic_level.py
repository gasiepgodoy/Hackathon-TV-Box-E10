import numpy as np
import sounddevice as sd
import sys

def get_kinect_index():
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and "kinect_clean" in d['name'].lower():
            return i
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0 and "kinect" in d['name'].lower():
            return i
    return sd.default.device[0]

def main():
    idx = get_kinect_index()
    try:
        dev_name = sd.query_devices(idx)['name']
    except Exception:
        dev_name = "Unknown"
        
    print(f"Testing audio level on device {idx}: {dev_name}")
    print("Capturing 5 seconds of audio. Please speak into the microphone...")
    
    duration = 5.0  # seconds
    sample_rate = 16000
    
    try:
        # Record audio
        audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16', device=idx)
        sd.wait()
        
        # Calculate levels
        rms = np.sqrt(np.mean(audio.astype(np.float32)**2))
        max_val = np.max(np.abs(audio))
        print(f"\n--- Results ---")
        print(f"RMS (Average volume): {rms:.2f}")
        print(f"Max Amplitude (Peak volume): {max_val}")
        
        if max_val == 0:
            print("\n❌ ERROR: Absolute silence detected! The microphone is MUTED or not working.")
            print("Please open alsamixer ('alsamixer' in terminal) and make sure the Kinect input capture is unmuted and volume is up.")
        elif max_val < 100:
            print("\n⚠️ WARNING: Volume is extremely low! Check if the mic volume is low in alsamixer.")
        else:
            print("\n✅ SUCCESS: Sound detected! The microphone is working and capturing sound.")
            
    except Exception as e:
        print(f"Error capturing audio: {e}")

if __name__ == "__main__":
    main()
