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
    
    for f in [encoder, decoder, joiner, tokens, keywords]:
        if not os.path.exists(f):
            print(f"Error: Required file {f} does not exist!")
            sys.exit(1)
            
    print("Initializing KeywordSpotter...")
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
    
    print("\nListening... Speak one of the keywords from keywords.txt (e.g. 'ALEXA')...")
    print("Press Ctrl+C to stop.\n")
    
    q = queue.Queue()
    
    def callback(indata, frames, time, status):
        q.put(indata.copy())
        
    try:
        with sd.InputStream(channels=1, samplerate=16000, dtype='float32', callback=callback):
            while True:
                chunk = q.get()
                stream.accept_waveform(16000, chunk.reshape(-1))
                
                while kws.is_ready(stream):
                    kws.decode_stream(stream)
                    
                result = kws.get_result(stream)
                # Check if result has keyword property and is not empty
                if hasattr(result, "keyword") and result.keyword:
                    print(f"🎉 Detected Keyword: '{result.keyword}'")
                    # Reset stream to clear detection state
                    stream = kws.create_stream()
                elif isinstance(result, str) and result:
                    # Fallback if get_result returns a string directly
                    print(f"🎉 Detected: '{result}'")
                    stream = kws.create_stream()
                    
    except KeyboardInterrupt:
        print("\nStopping...")
        
if __name__ == "__main__":
    main()
