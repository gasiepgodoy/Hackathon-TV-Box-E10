import asyncio
import time
import os
import sys
from src.utils.config_manager import ConfigManager
from src.utils.chat_bridge import ChatBridge
from src.utils.tts_client import TTSClient

async def run_benchmark():
    print("=" * 60)
    print("        MINA ASSISTANT - END-TO-END PIPELINE BENCHMARK")
    print("=" * 60)
    
    cfg = ConfigManager.get_instance()
    
    # Verify Cerebras key
    llm_opts = cfg.get_config("LLM_OPTIONS", {})
    api_key = os.getenv("CEREBRAS_API_KEY") or llm_opts.get("API_KEY")
    if not api_key:
        print("[-] Error: Cerebras API key is missing.")
        print("    Please set CEREBRAS_API_KEY environment variable or configure it in config.json")
        print("\n    Example: export CEREBRAS_API_KEY='your_key_here' && python3 benchmark_pipeline.py")
        sys.exit(1)
        
    # Temporary inject env var for ChatBridge if not configured in json
    if not llm_opts.get("API_KEY") and os.getenv("CEREBRAS_API_KEY"):
        llm_opts["API_KEY"] = os.getenv("CEREBRAS_API_KEY")

    chat_bridge = ChatBridge()
    tts_opts = cfg.get_config("TTS_OPTIONS", {})
    
    # Initialize native embedded TTS
    tts_client = TTSClient(
        enabled=True,
        voice=tts_opts.get("VOICE", "pt-BR-FranciscaNeural"),
        rate=tts_opts.get("RATE", "+15%"),
        pitch=tts_opts.get("PITCH", "+3Hz"),
        volume=tts_opts.get("VOLUME", "+0%"),
    )
    
    print("[*] Running engine initialization & health checks...")
    tts_healthy = await tts_client.health_check()
    if not tts_healthy:
        print("[-] TTS local engine failed health check (verify internet connection).")
        sys.exit(1)
        
    prompt = "Diga uma frase curta de teste com menos de 10 palavras."
    print(f"\n[*] Sending Prompt to Cerebras: '{prompt}'")
    print("-" * 60)
    
    t0 = time.perf_counter()
    first_token_time = None
    first_chunk_time = None
    first_audio_time = None
    audio_synthesis_time = 0
    audio_bytes_len = 0
    
    tts_tasks = []
    
    async def on_token(token: str):
        nonlocal first_token_time
        if first_token_time is None:
            first_token_time = time.perf_counter() - t0
            print(f"[LLM] -> Time to First Token (TTFT): {first_token_time:.3f}s")
            
    async def on_chunk(chunk_text: str, delay: float, emotion: str):
        nonlocal first_chunk_time, first_audio_time, audio_synthesis_time, audio_bytes_len
        now = time.perf_counter()
        if first_chunk_time is None:
            first_chunk_time = now - t0
            print(f"[LLM] -> Time to First Chunk: {first_chunk_time:.3f}s (Text: '{chunk_text}')")
            
        print(f"[TTS] -> Synthesizing chunk: '{chunk_text}' (Emotion: {emotion})")
        task = tts_client.pre_synthesize(chunk_text)
        if task:
            tts_tasks.append(task)
            if len(tts_tasks) == 1:
                audio_t0 = time.perf_counter()
                audio_bytes = await task
                audio_synthesis_time = time.perf_counter() - audio_t0
                first_audio_time = time.perf_counter() - t0
                if audio_bytes:
                    audio_bytes_len = len(audio_bytes)

    try:
        full_text = await chat_bridge.send_and_stream(
            prompt,
            on_token=on_token,
            on_chunk=on_chunk
        )
        
        # Wait for all background tasks to finish
        if tts_tasks:
            await asyncio.gather(*tts_tasks)
            
        total_time = time.perf_counter() - t0
        
        print("=" * 60)
        print("                   LATENCY METRICS SUMMARY")
        print("=" * 60)
        print(f"1. LLM Time to First Token (TTFT) : {first_token_time:.3f}s")
        print(f"2. LLM Time to First Chunk        : {first_chunk_time:.3f}s")
        print(f"3. First Audio Chunk Synthesis     : {audio_synthesis_time:.3f}s  ({audio_bytes_len} bytes)")
        print(f"4. TOTAL PIPELINE LATENCY         : {first_audio_time:.3f}s")
        print(f"   (Time from prompt sent until audio begins playing)")
        print("-" * 60)
        print(f"5. Total Stream Completion Time   : {total_time:.3f}s")
        print(f"6. Full Assistant Reply           : '{full_text}'")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[-] Error during benchmark execution: {e}")
    finally:
        await tts_client.close()
        await chat_bridge.stop()

if __name__ == "__main__":
    asyncio.run(run_benchmark())
