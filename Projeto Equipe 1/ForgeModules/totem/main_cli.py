#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import os
import sys
import argparse
import json
from typing import Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.config_manager import ConfigManager
from src.utils.chat_bridge import ChatBridge
from src.utils.tts_client import TTSClient
from src.utils.stt_client import STTClient, STTClientError
from src.utils.system_optimizer import optimize_system
from src.utils.logging_config import get_logger, setup_logging

# ANSI Color Escape Codes
CLR_CYAN = "\033[1;36m"
CLR_GREEN = "\033[1;32m"
CLR_YELLOW = "\033[1;33m"
CLR_RED = "\033[1;31m"
CLR_BLUE = "\033[1;34m"
CLR_MAGENTA = "\033[1;35m"
CLR_RESET = "\033[0m"

logger = get_logger("mina_cli")


async def cli_loop():
    setup_logging()
    optimize_system()
    cfg = ConfigManager()
    
    # Parse options
    parser = argparse.ArgumentParser(description="Mina - Assistente Virtual (Modo CLI/GUI)")
    parser.add_argument("--no-tts", action="store_true", help="Desativar saída de voz (TTS)")
    parser.add_argument("--no-stt", action="store_true", help="Desativar entrada de microfone (STT)")
    parser.add_argument("-w", "--windowed", "--gui", action="store_true", help="Iniciar em modo janela (GUI)")
    parser.add_argument("-f", "-F", "--fullscreen", action="store_true", help="Iniciar em modo tela cheia (GUI)")
    parser.add_argument("-s", "--studio", action="store_true", help="Iniciar modo studio de layout")
    parser.add_argument("-g", "-r", "--gravity", choices=["right", "left"], nargs="?", const="right", default=None, help="Rotação da GUI (right/left)")
    args, unknown = parser.parse_known_args()

    if args.windowed or args.fullscreen or args.studio or (args.gravity is not None):
        import main_gui
        main_gui.main()
        return

    # Init chat bridge
    llm_opts = cfg.get_config("LLM_OPTIONS", {})
    backend = llm_opts.get("BACKEND", "cerebras")
    model = llm_opts.get("MODEL", "zai-glm-4.7")
    
    print(f"{CLR_CYAN}==================================================")
    print(f"   Mina - Assistente Virtual do G.E.R.A (UNESP)   ")
    print(f"                     Modo CLI                     ")
    print(f"=================================================={CLR_RESET}")
    print(f"{CLR_GREEN}Backend ativo: {backend.upper()} | Modelo: {model}{CLR_RESET}")
    
    # Init TTS
    tts_opts = cfg.get_config("TTS_OPTIONS", {})
    use_tts = tts_opts.get("ENABLED", True) and not args.no_tts
    tts_client = None
    if use_tts:
        tts_client = TTSClient(
            base_url=tts_opts.get("API_URL", "http://localhost:8000"),
            enabled=True,
            voice=tts_opts.get("VOICE", "pt-BR-FranciscaNeural"),
            rate=tts_opts.get("RATE", "+15%"),
            pitch=tts_opts.get("PITCH", "+3Hz"),
            volume=tts_opts.get("VOLUME", "+0%"),
        )
        try:
            await tts_client.health_check()
            print(f"{CLR_GREEN}TTS (Voz): Ativo e conectado{CLR_RESET}")
        except Exception:
            print(f"{CLR_YELLOW}TTS (Voz): Indisponível (rodando em modo apenas texto){CLR_RESET}")
            use_tts = False

    # Init STT
    stt_opts = cfg.get_config("STT_OPTIONS", {})
    use_stt = stt_opts.get("ENABLED", True) and not args.no_stt
    stt_client = None
    if use_stt:
        try:
            stt_client = STTClient()
            print(f"{CLR_GREEN}STT (Microfone): Ativo e pronto{CLR_RESET}")
        except Exception as e:
            print(f"{CLR_YELLOW}STT (Microfone): Indisponível ({e}){CLR_RESET}")
            use_stt = False

    chat_bridge = ChatBridge()
    print(f"{CLR_GREEN}Mina está pronta!{CLR_RESET}")
    if use_stt:
        print(f"{CLR_GREEN}Digite sua mensagem OU pressione Enter com texto vazio para gravar voz.{CLR_RESET}")
    else:
        print(f"{CLR_GREEN}Digite sua mensagem abaixo.{CLR_RESET}")
    print(f"{CLR_GREEN}Digite 'sair' para encerrar.{CLR_RESET}")
    print(f"{CLR_CYAN}==================================================\n{CLR_RESET}")

    # Start loop
    while True:
        try:
            # Read input using asyncio to prevent blocking the event loop
            prompt_label = f"{CLR_BLUE}Você (Enter para falar):{CLR_RESET} " if use_stt else f"{CLR_BLUE}Você:{CLR_RESET} "
            user_input = await asyncio.to_thread(input, prompt_label)
            user_input = user_input.strip()
            
            # Voice input triggers when user inputs empty text in STT mode
            if not user_input:
                if use_stt:
                    print(f"{CLR_YELLOW}[STT] Gravando... Fale e pressione Enter para parar.{CLR_RESET}")
                    try:
                        stt_client.start_recording()
                        # Wait for user to hit Enter again to stop
                        await asyncio.to_thread(input, "")
                        print(f"{CLR_YELLOW}[STT] Transcrevendo...{CLR_RESET}")
                        raw_response = stt_client.stop_recording().strip()
                        transcription = ""
                        if raw_response:
                            try:
                                payload = json.loads(raw_response)
                                if isinstance(payload, dict):
                                    transcription = str(payload.get("text", "")).strip()
                                else:
                                    transcription = raw_response
                            except json.JSONDecodeError:
                                transcription = raw_response
                                
                        if not transcription:
                            print(f"{CLR_YELLOW}[STT] Nenhuma fala detectada.{CLR_RESET}")
                            continue
                            
                        print(f"{CLR_BLUE}Você (Voz):{CLR_RESET} {transcription}")
                        user_input = transcription
                    except Exception as exc:
                        print(f"{CLR_RED}[Erro STT]: {exc}{CLR_RESET}")
                        continue
                else:
                    continue
                
            if user_input.lower() in ["sair", "exit", "quit"]:
                print(f"{CLR_YELLOW}\nAté mais! Encerrando a Mina...{CLR_RESET}")
                break

            # Interceptador de intenções local (MABI/Offline)
            from src.utils.intent_classifier import IntentClassifier
            intent_classifier = IntentClassifier()
            intent_detected, local_response = intent_classifier.classify_and_execute(user_input)

            if intent_detected:
                print(f"{CLR_MAGENTA}Mina (Local):{CLR_RESET} {local_response}")
                if use_tts and tts_client:
                    audio_task = tts_client.pre_synthesize(local_response)
                    if audio_task:
                        audio_bytes = await audio_task
                        if audio_bytes:
                            await tts_client.play(audio_bytes)
                print("")  # Nova linha
                continue

            print(f"{CLR_MAGENTA}Mina:{CLR_RESET} ", end="", flush=True)

            # TTS Tracking
            tts_futures = {}
            chunk_counter = 0
            first_audio_ready = asyncio.Event()

            # Emitter for CLI print + audio sync
            async def chunk_emitter(queue):
                try:
                    await first_audio_ready.wait()
                    while True:
                        chunk = await queue.get()
                        if chunk is None:
                            return
                        delay = max(0.0, min(chunk.get("delay", 2.5), 2.5))
                        text = chunk.get("text", "")
                        tts_idx = chunk.get("tts_idx", -1)
                        emotion = chunk.get("emotion", "neutral")

                        # Print chunk text
                        print(text, end="", flush=True)

                        # Play audio if exists
                        audio_bytes = None
                        if tts_idx in tts_futures:
                            try:
                                audio_bytes = await tts_futures.pop(tts_idx)
                            except Exception:
                                pass
                        
                        coros = []
                        if audio_bytes and use_tts:
                            coros.append(tts_client.play(audio_bytes))
                        coros.append(asyncio.sleep(delay))
                        await asyncio.gather(*coros)
                except asyncio.CancelledError:
                    pass

            chunk_queue = asyncio.Queue()
            emitter_task = asyncio.create_task(chunk_emitter(chunk_queue))

            # Callbacks
            async def on_chunk(chunk_text: str, delay: float, emotion: str):
                nonlocal chunk_counter
                if not chunk_text:
                    return
                idx = chunk_counter
                chunk_counter += 1

                if use_tts:
                    task = tts_client.pre_synthesize(chunk_text)
                    if task:
                        tts_futures[idx] = task
                        if idx == 0:
                            async def _signal_first():
                                try:
                                    await task
                                except Exception:
                                    pass
                                first_audio_ready.set()
                            asyncio.create_task(_signal_first())
                    elif idx == 0:
                        first_audio_ready.set()
                elif idx == 0:
                    first_audio_ready.set()

                await chunk_queue.put({"text": chunk_text, "delay": delay, "emotion": emotion, "tts_idx": idx})

            async def on_emotion(emotion: str):
                pass

            async def on_control(ctrl: str):
                pass

            try:
                await chat_bridge.send_and_stream(
                    user_input, on_chunk=on_chunk, on_emotion=on_emotion, on_control=on_control
                )
            except Exception as e:
                print(f"{CLR_RED}\n[Erro no Chat]: {e}{CLR_RESET}")
            finally:
                first_audio_ready.set()
                await chunk_queue.put(None)
                await emitter_task
                
                # Cleanup remaining tasks
                for task in tts_futures.values():
                    task.cancel()
                print("\n")  # New line after the response completes

        except (KeyboardInterrupt, EOFError):
            print(f"{CLR_YELLOW}\n\nEncerrando a Mina...{CLR_RESET}")
            break
            
    if tts_client:
        await tts_client.close()
    await chat_bridge.stop()


GUI_FLAGS = ("-w", "--windowed", "-g", "--gui", "-f", "--fullscreen", "-s", "--studio", "-r", "--gravity")


def _check_gui_launch_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-w", "--windowed", "--gui", action="store_true")
    parser.add_argument("-f", "-F", "--fullscreen", action="store_true")
    parser.add_argument("-s", "--studio", action="store_true")
    parser.add_argument("-g", "-r", "--gravity", choices=["right", "left"], nargs="?", const="right", default=None)
    args, _ = parser.parse_known_args(sys.argv[1:])
    return bool(args.windowed or args.fullscreen or args.studio or (args.gravity is not None))


def main():
    if _check_gui_launch_args():
        import main_gui
        main_gui.main()
        return
    try:
        asyncio.run(cli_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
