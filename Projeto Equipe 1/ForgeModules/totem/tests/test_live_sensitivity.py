import os
import queue
import sys
import numpy as np
import sounddevice as sd
import sherpa_onnx

def main():
    model_dir = "models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
    encoder = f"{model_dir}/encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
    decoder = f"{model_dir}/decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
    joiner = f"{model_dir}/joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
    tokens = f"{model_dir}/tokens.txt"
    keywords = f"{model_dir}/keywords.txt"
    
    # Let's write a highly sensitive keywords.txt first!
    with open(keywords, 'w', encoding='utf-8') as f:
        f.write('\u2581A LE X A :2.5 #0.02\n')
        f.write('\u2581HE Y \u2581JA R VI S :2.5 #0.02\n')
        
    print("Initializing KeywordSpotter with high sensitivity...")
    kws = sherpa_onnx.KeywordSpotter(
        tokens=tokens,
        encoder=encoder,
        decoder=decoder,
        joiner=joiner,
        keywords_file=keywords,
        num_threads=2,
        provider="cpu"
    )
    
    stream = kws.create_stream()
    q = queue.Queue()
    
    def callback(indata, frames, time, status):
        q.put(indata.copy())
        
    print("\n[ACTIVE] Listening... Speak 'ALEXA' or 'HEY JARVIS'...")
    try:
        with sd.InputStream(channels=1, samplerate=16000, dtype='float32', callback=callback):
            while True:
                chunk = q.get()
                stream.accept_waveform(16000, chunk.reshape(-1))
                while kws.is_ready(stream):
                    kws.decode_stream(stream)
                    r = kws.get_result(stream)
                    if r:
                        print(f"🎉 TRIGGERED: {r}")
                        kws.reset_stream(stream)
    except KeyboardInterrupt:
        print("Stopped.")

if __name__ == "__main__":
    main()
