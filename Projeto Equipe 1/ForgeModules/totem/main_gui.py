#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal GUI Launcher for Xiaozhi AI Client (GUI-only version)

This launcher starts only the GUI display without any backend services.
Ideal for testing and developing the GUI components in isolation.
"""

import asyncio
import argparse
import json
import sys
import os
import signal
import time
from typing import Optional

# Configure Qt platform before importing Qt
is_wayland = (
    os.environ.get("WAYLAND_DISPLAY")
    or os.environ.get("XDG_SESSION_TYPE") == "wayland"
)

if is_wayland and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
    os.environ.setdefault("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")

try:
    import qasync
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication
except ImportError as e:
    print(f"ERROR: GUI mode requires qasync and PyQt5: {e}")
    print("Please install: pip install PyQt5 qasync")
    sys.exit(1)

from src.display.gui_display import GuiDisplay
from src.utils.chat_bridge import ChatBridge
from src.utils.config_manager import ConfigManager
from src.utils.logging_config import get_logger, setup_logging
from src.utils.stt_client import STTClient, STTClientError
from src.utils.tts_client import TTSClient
from src.utils.system_optimizer import optimize_system

logger = get_logger(__name__)


class STTController:
    """Manages the STT lifecycle and ties it to the GUI talk button."""

    def __init__(self, gui_display, send_text_callback, stt_client):
        self._gui_display = gui_display
        self._send_text_callback = send_text_callback
        self._stt_client = stt_client
        self._recording = False
        self._busy = False

    async def toggle(self):
        if self._busy:
            return
        self._busy = True
        try:
            if not self._recording:
                await self._start()
            else:
                await self._stop()
        finally:
            self._busy = False

    async def _start(self, status_text: str = "Ouvindo...", button_text: str = "Parar"):
        await self._gui_display.update_status(status_text, True)
        await self._gui_display.update_button_status(button_text)
        await self._gui_display.update_emotion("listening")
        try:
            logger.info("STT: starting recording")
            await asyncio.to_thread(self._stt_client.start_recording)
        except STTClientError:
            logger.error("STT: start_recording failed", exc_info=True)
            await self._gui_display.update_status("STT indisponível", False)
            await self._gui_display.update_button_status("Falar")
            await self._gui_display.update_emotion("neutral")
            return
        self._recording = True

    async def start_from_wake(self):
        if self._busy or self._recording:
            return
        self._busy = True
        try:
            await self._start("Acordado, ouvindo", "Parar de ouvir")
        finally:
            self._busy = False

    async def _stop(self):
        transcription = ""
        stt_failed = False
        try:
            await self._gui_display.update_status("Transcrevendo...", True)
            logger.info("STT: stopping recording and transcribing")
            raw_response = (await asyncio.to_thread(self._stt_client.stop_recording)).strip()
            if raw_response:
                logger.info("STT: raw response length=%d", len(raw_response))
                try:
                    payload = json.loads(raw_response)
                    if isinstance(payload, dict):
                        transcription = str(payload.get("text", "")).strip()
                    else:
                        transcription = raw_response
                except json.JSONDecodeError:
                    transcription = raw_response
        except STTClientError:
            stt_failed = True
            logger.error("STT: stop_recording failed", exc_info=True)
            await self._gui_display.update_status("Falha no STT", False)
        finally:
            self._recording = False
            await self._gui_display.update_button_status("Falar")
            await self._gui_display.update_emotion("neutral")

        if transcription:
            logger.info("STT: parsed transcription length=%d", len(transcription))
            await self._send_text_callback(transcription)
        elif not stt_failed:
            logger.warning("STT: transcription empty")
            await self._gui_display.update_status("Ready", True)

    async def shutdown(self):
        await asyncio.to_thread(self._stt_client.shutdown)


def _parse_cli_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-f", "-F", "--fullscreen", action="store_true", help="Run in fullscreen mode")
    parser.add_argument("-w", "--windowed", "--gui", action="store_true", help="Run in windowed mode")
    parser.add_argument("-s", "--studio", action="store_true", help="Open the layout editor mode")
    parser.add_argument("-g", "-r", "--gravity", choices=["right", "left"], nargs="?", const="right", default=None,
                        help="Rotate the GUI 90 degrees: 'right' (clockwise) or 'left' (counter-clockwise)")
    args, remaining = parser.parse_known_args(sys.argv[1:])
    sys.argv = [sys.argv[0]] + remaining
    windowed = bool(args.windowed)
    fullscreen = bool(args.fullscreen) and not windowed
    return fullscreen, args.studio, args.gravity, windowed


async def run_gui(
    fullscreen: bool = False,
    studio_mode: bool = False,
    rotation_gravity: str = None,
    windowed: bool = False,
):
    """
    Run the GUI display in standalone mode.
    """
    logger.info("Starting Xiaozhi GUI (standalone mode)")
    optimize_system()
    
    try:
        chat_bridge = ChatBridge()

        # Initialise TTS client from configuration
        cfg = ConfigManager()
        tts_opts = cfg.get_config("TTS_OPTIONS", {})
        tts_client = TTSClient(
            base_url=tts_opts.get("API_URL", "http://localhost:8000"),
            enabled=tts_opts.get("ENABLED", True),
            voice=tts_opts.get("VOICE", "pt-BR-FranciscaNeural"),
            rate=tts_opts.get("RATE", "+15%"),
            pitch=tts_opts.get("PITCH", "+3Hz"),
            volume=tts_opts.get("VOLUME", "+0%"),
        )
        if tts_client.enabled:
            await tts_client.health_check()
            logger.info("TTS client ready (enabled=%s)", tts_client.enabled)

        # Create and start the GUI display
        gui_display = GuiDisplay(studio_mode=studio_mode, rotation_gravity=rotation_gravity)
        if fullscreen and not windowed:
            gui_display.set_force_fullscreen(True)

        _last_request_time: float = 0
        _last_interaction_time: float = time.monotonic()
        _idle_reset_done: bool = False

        async def handle_send_text(text: str):
            """Send text to the chat backend, pre-synthesise TTS for every
            chunk, and only start displaying text + emoji once the first.
            """
            nonlocal _last_request_time, _last_interaction_time, _idle_reset_done

            # Rate limiter: 3s cooldown between requests
            now = time.monotonic()
            if now - _last_request_time < 3.0:
                await gui_display.update_status("Aguarde um momento...", True)
                return
            _last_request_time = now

            # Interceptador de intenções local (MABI/Offline)
            from src.utils.intent_classifier import IntentClassifier
            intent_classifier = IntentClassifier()
            intent_detected, local_response = intent_classifier.classify_and_execute(text)

            if intent_detected:
                await gui_display.update_button_bar_visibility(False)
                await gui_display.update_status("Respondendo...", True)
                await gui_display.update_text(local_response)
                await gui_display.update_emotion("neutral")
                
                if tts_client.enabled:
                    audio_task = tts_client.pre_synthesize(local_response)
                    if audio_task:
                        audio_bytes = await audio_task
                        if audio_bytes:
                            await tts_client.play(audio_bytes, on_start=lambda: None)
                            
                await asyncio.sleep(1.0)
                await gui_display.update_button_bar_visibility(True)
                await gui_display.update_status("Pronto", True)
                _last_interaction_time = time.monotonic()
                _idle_reset_done = False
                return

            await gui_display.update_button_bar_visibility(False)
            await gui_display.update_status("Pensando...", True)
            await gui_display.update_text("")
            await gui_display.update_emotion("neutral")

            # Check if LLM is enabled
            llm_opts = cfg.get_config("LLM_OPTIONS", {})
            if not llm_opts.get("ENABLED", True):
                await gui_display.update_status("LLM Desativado", False)
                await asyncio.sleep(2.0)
                await gui_display.update_button_bar_visibility(True)
                return

            SMALL_REPLY_THRESHOLD = 80
            chunk_queue: asyncio.Queue = asyncio.Queue()
            extra_pause_ms = 0
            final_text = ""
            stream_success = False
            chunks_emitted = False
            last_chunk_emotion: Optional[str] = None

            # TTS pre-synthesis tracking (per-interaction)
            tts_futures: dict[int, asyncio.Task] = {}
            chunk_counter = 0
            first_audio_ready = asyncio.Event()

            async def chunk_emitter():
                nonlocal extra_pause_ms
                try:
                    # Gate: wait until the first TTS audio is ready
                    await first_audio_ready.wait()

                    while True:
                        chunk = await chunk_queue.get()
                        if chunk is None:
                            return
                        delay = max(0.0, min(chunk.get("delay", 2.5), 2.5))
                        emotion = chunk.get("emotion")
                        tts_idx = chunk.get("tts_idx", -1)

                        async def on_audio_start():
                            await gui_display.update_emotion(emotion or "neutral")
                            await gui_display.update_text(chunk.get("text", ""))

                        # Retrieve pre-synthesised audio
                        audio_bytes = None
                        if tts_idx in tts_futures:
                            try:
                                audio_bytes = await tts_futures.pop(tts_idx)
                            except Exception as exc:
                                logger.warning("TTS synthesis failed for chunk %d: %s", tts_idx, exc)

                        # Display text and play audio; duration is dictated by TTS, with fallback to character-count reading speed
                        if audio_bytes and tts_client.enabled:
                            # Play audio (blocks for the exact duration of the sound)
                            await tts_client.play(audio_bytes, on_start=on_audio_start)
                            # Add a small natural pause after the speech (e.g., 0.3s)
                            await asyncio.sleep(0.3)
                        else:
                            # Fallback if TTS is disabled: read at a human-like speed
                            await on_audio_start()
                            char_count = len(chunk.get("text", ""))
                            reading_delay = max(1.0, char_count * 0.06)
                            await asyncio.sleep(reading_delay)

                        if extra_pause_ms > 0:
                            await asyncio.sleep(extra_pause_ms / 1000.0)
                            extra_pause_ms = 0
                except asyncio.CancelledError:
                    pass

            emitter_task = asyncio.create_task(chunk_emitter())

            async def on_chunk(chunk_text: str, delay: float, emotion: Optional[str]):
                nonlocal last_chunk_emotion, chunks_emitted, chunk_counter
                if not chunk_text:
                    return
                chunks_emitted = True
                last_chunk_emotion = emotion
                idx = chunk_counter
                chunk_counter += 1

                # Fire TTS synthesis immediately
                if tts_client.enabled:
                    task = tts_client.pre_synthesize(chunk_text)
                    if task:
                        tts_futures[idx] = task

                await chunk_queue.put({"text": chunk_text, "delay": delay, "emotion": emotion, "tts_idx": idx})

            async def on_control(ctrl: str):
                nonlocal extra_pause_ms
                if ctrl.upper().startswith("PAUSE:"):
                    try:
                        ms = int(ctrl.split(":", 1)[1])
                    except Exception:
                        ms = 300
                    extra_pause_ms += ms

            async def on_emotion(emotion: str):
                # update GUI emotion (file names expect lower-case keys)
                await gui_display.update_emotion(emotion)

            try:
                final_text = await chat_bridge.send_and_stream(
                    text, on_chunk=on_chunk, on_emotion=on_emotion, on_control=on_control
                )
                stream_success = True
                
                # Wait for all TTS chunks to be fully synthesized before starting playback
                if tts_futures:
                    await asyncio.gather(*tts_futures.values(), return_exceptions=True)
                first_audio_ready.set()
                
                stderr_chunk = await chat_bridge.read_stderr()
                if stderr_chunk:
                    logger.info(stderr_chunk.strip())
                await gui_display.update_status("Pronto", True)
            except Exception as exc:
                logger.error(f"Chat error: {exc}", exc_info=True)
                await gui_display.update_status("Erro no Chat", False)
            finally:
                first_audio_ready.set()  # ensure emitter isn't stuck
                await chunk_queue.put(None)
                try:
                    await emitter_task
                except asyncio.CancelledError:
                    pass
                # Cancel any remaining TTS futures
                for task in tts_futures.values():
                    task.cancel()
                tts_futures.clear()
                if not chunks_emitted and stream_success and final_text and len(final_text) <= SMALL_REPLY_THRESHOLD:
                    if last_chunk_emotion:
                        await gui_display.update_emotion(last_chunk_emotion)
                    await gui_display.update_text(final_text)
                await asyncio.sleep(1.0)
                await gui_display.update_button_bar_visibility(True)
                _last_interaction_time = time.monotonic()
                _idle_reset_done = False

        stt_controller = None
        stt_opts = cfg.get_config("STT_OPTIONS", {})
        if stt_opts.get("ENABLED", True):
            try:
                stt_client = STTClient()
                stt_controller = STTController(gui_display, handle_send_text, stt_client)
            except STTClientError:
                logger.error("Failed to initialize native STT support", exc_info=True)
        else:
            logger.info("STT is disabled in configuration")

        def schedule_toggle() -> None:
            if stt_controller:
                asyncio.create_task(stt_controller.toggle())
            else:
                logger.warning("Talk feature disabled because the STT library could not be loaded")

        # Set callbacks so GUI input flows into the C backend
        await gui_display.set_callbacks(
            auto_callback=schedule_toggle,
            abort_callback=lambda: logger.info("Aborted"),
            send_text_callback=handle_send_text,
        )
        
        # Start the GUI
        await gui_display.start()
        
        # Set initial status
        await gui_display.update_status("Interface Pronta", True)
        await gui_display.update_emotion("neutral")

        # Background internet status checking loop
        async def check_internet_loop():
            import socket
            while gui_display._running:
                online = False
                try:
                    def ping():
                        try:
                            socket.setdefaulttimeout(1.5)
                            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
                            return True
                        except Exception:
                            return False
                    online = await asyncio.to_thread(ping)
                except Exception:
                    pass
                
                if not online:
                    await gui_display.update_status("Modo Local (Offline)", False)
                else:
                    if gui_display.current_status in ["Modo Local (Offline)", "Interface Pronta (Offline)"]:
                        await gui_display.update_status("Interface Pronta", True)
                await asyncio.sleep(10.0)

        asyncio.create_task(check_internet_loop())

        logger.info("GUI started successfully")
        
        # Keep the event loop running until GUI is closed
        try:
            while gui_display._running:
                await asyncio.sleep(0.5)
                # Session reset on inactivity (120s)
                if not _idle_reset_done and time.monotonic() - _last_interaction_time > 120:
                    chat_bridge._history.clear()
                    _idle_reset_done = True
                    logger.info("Inactivity timeout: chat history cleared")
        finally:
            if stt_controller:
                await stt_controller.shutdown()
            await tts_client.close()
            await chat_bridge.stop()
            
    except Exception as e:
        logger.error(f"GUI error: {e}", exc_info=True)
        return 1
    
    return 0


def main():
    """
    Main entry point for the GUI-only launcher.
    """
    exit_code = 1
    
    try:
        # Setup logging
        setup_logging()
        
        # Handle signals
        try:
            if hasattr(signal, "SIGTRAP"):
                signal.signal(signal.SIGTRAP, signal.SIG_IGN)
        except Exception:
            pass
        
        fullscreen, studio_mode, rotation_gravity, windowed = _parse_cli_args()
        
        # Configure Qt High DPI scaling attributes before Application creation
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        if hasattr(Qt, "AA_UseHighDpiPixmaps"):
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Create Qt application
        qt_app = QApplication.instance() or QApplication(sys.argv)
        qt_app.setQuitOnLastWindowClosed(False)
        
        # Create qasync event loop
        loop = qasync.QEventLoop(qt_app)
        asyncio.set_event_loop(loop)
        logger.info("Created qasync event loop")
        
        # Run the GUI
        with loop:
            exit_code = loop.run_until_complete(
                run_gui(
                    fullscreen=fullscreen,
                    studio_mode=studio_mode,
                    rotation_gravity=rotation_gravity,
                    windowed=windowed,
                )
            )
            
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
        exit_code = 0
    except RuntimeError as e:
        if "Event loop stopped before Future completed" in str(e):
            logger.info("GUI closed before loop completion")
            exit_code = 0
        else:
            logger.error(f"Program exited with error: {e}", exc_info=True)
            exit_code = 1
    except Exception as e:
        logger.error(f"Program exited with error: {e}", exc_info=True)
        exit_code = 1
    finally:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
