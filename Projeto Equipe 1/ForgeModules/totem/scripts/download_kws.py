import os
import urllib.request
import tarfile

MODEL_DIR = "models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2"
ARCHIVE_NAME = "models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2"

def main():
    if not os.path.exists(MODEL_DIR):
        print(f"Downloading {MODEL_URL}...")
        urllib.request.urlretrieve(MODEL_URL, ARCHIVE_NAME)
        print("Extracting archive...")
        with tarfile.open(ARCHIVE_NAME, "r:bz2") as tar:
            tar.extractall(path="models")
        print("Model downloaded and extracted successfully!")
    else:
        print("Model directory already exists.")

if __name__ == "__main__":
    main()
