import os
import sys
import asyncio
import logging
import aiohttp
from src.utils.chat_bridge import ChatBridge
from src.utils.tts_client import TTSClient

try:
    import pytest
except ImportError:
    class DummyMark:
        def __getattr__(self, name):
            return lambda func: func
    class DummyPytest:
        mark = DummyMark()
    pytest = DummyPytest()

# logging.basicConfig(level=logging.INFO)

@pytest.mark.asyncio
async def test_pipeline():
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    if not GROQ_API_KEY:
        print("GROQ_API_KEY is not set. Try sourcing ~/.bashrc or export it manually.")
        return

    wav_path = "test.wav"
    if not os.path.exists(wav_path):
        print("Generating test.wav using edge-tts...")
        os.system("edge-tts --text 'Olá Mina, o que você consegue fazer?' --voice pt-BR-FranciscaNeural --write-media test.wav")
    
    print("\n--- 1. Testing STT (Groq API with test.wav) ---")
    stt_text = ""
    async with aiohttp.ClientSession() as session:
        with open(wav_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename='test.wav', content_type='audio/wav')
            data.add_field('model', 'whisper-large-v3')
            data.add_field('language', 'pt')
            
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
            async with session.post("https://api.groq.com/openai/v1/audio/transcriptions", data=data, headers=headers) as resp:
                result = await resp.json()
                stt_text = result.get("text", "")
                print(f"STT Result: {stt_text}")
                
    if not stt_text:
        print("STT failed!")
        return
        
    print("\n--- 2. Testing LLM (ChatBridge) ---")
    bridge = ChatBridge()
    await bridge.start()
    
    full_response = ""
    
    async def on_chunk(text: str, delay: float, emotion: str):
        nonlocal full_response
        print(f"  Chunk received (delay={delay}, emotion={emotion}): {text}")
        if text.strip() and text != "<<END>>":
            full_response += text + " "
            
    print("Sending prompt to LLM...")
    await bridge.send_and_stream(stt_text, on_chunk=on_chunk)
                    
    print(f"\nFull Extracted Text for TTS: {full_response}")
    await bridge.stop()
    
    print("\n--- 3. Testing TTS (TTSClient) ---")
    tts = TTSClient()
    task = tts.pre_synthesize(full_response)
    if task:
        audio_bytes = await task
        if audio_bytes:
            print("Playing synthesized audio...")
            await tts.play(audio_bytes)
            print("TTS played successfully.")
        else:
            print("Synthesis failed to return bytes.")
    else:
        print("Synthesis task creation failed.")
        
    await tts.close()

if __name__ == "__main__":
    asyncio.run(test_pipeline())
