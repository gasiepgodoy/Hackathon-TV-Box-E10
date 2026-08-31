import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    print(f"[{i}]: {d['name']} (in={d['max_input_channels']}, out={d['max_output_channels']})")
