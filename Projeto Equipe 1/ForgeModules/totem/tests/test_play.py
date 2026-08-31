import asyncio
import os
from src.utils.tts_client import TTSClient

async def main():
    client = TTSClient(enabled=True)
    # Check if we can initialize
    await client.health_check()
    
    mp3_path = "/root/Repos/Mina-a-Assistente-Virtual-Do-G.E.R.A/tts_api/tts_api_outputs/api_sample_01.mp3"
    if not os.path.exists(mp3_path):
        # Fallback to check relative
        mp3_path = "tts_api/tts_api_outputs/api_sample_01.mp3"
        
    if not os.path.exists(mp3_path):
        print(f"Error: sample MP3 not found at {mp3_path}")
        return
        
    print(f"Loading {mp3_path}...")
    with open(mp3_path, "rb") as f:
        audio_bytes = f.read()
        
    print("Playing sample (1st call)...")
    await client.play(audio_bytes)
    
    print("Playing sample (2nd call)...")
    await client.play(audio_bytes)
    
    await client.close()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
