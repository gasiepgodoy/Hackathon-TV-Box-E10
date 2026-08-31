import sherpa_onnx
import wave
import numpy as np

def main():
    kws = sherpa_onnx.KeywordSpotter(
        tokens='models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/tokens.txt',
        encoder='models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx',
        decoder='models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx',
        joiner='models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx',
        keywords_file='models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/test_wavs/test_keywords.txt'
    )
    s = kws.create_stream()
    f = wave.open('models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01/test_wavs/0.wav')
    samples = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    s.accept_waveform(f.getframerate(), samples)

    tail_paddings = np.zeros(int(0.66 * f.getframerate()), dtype=np.float32)
    s.accept_waveform(f.getframerate(), tail_paddings)
    s.input_finished()

    print("Running decode...")
    while kws.is_ready(s):
        kws.decode_stream(s)
        r = kws.get_result(s)
        if r != "":
            print("Detected KWS:", r)
            kws.reset_stream(s)

if __name__ == "__main__":
    main()
