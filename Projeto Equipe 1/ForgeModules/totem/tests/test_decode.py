import miniaudio
import os

mp3_path = "/root/Repos/Mina-a-Assistente-Virtual-Do-G.E.R.A/tts_api/tts_api_outputs/api_sample_01.mp3"
if not os.path.exists(mp3_path):
    mp3_path = "tts_api/tts_api_outputs/api_sample_01.mp3"

with open(mp3_path, "rb") as f:
    audio_bytes = f.read()

decoded = miniaudio.decode(audio_bytes, output_format=miniaudio.SampleFormat.SIGNED16)
print("type:", type(decoded.samples))
print("len:", len(decoded.samples))
print("num_frames:", decoded.num_frames)
print("nchannels:", decoded.nchannels)
print("sample_rate:", decoded.sample_rate)
