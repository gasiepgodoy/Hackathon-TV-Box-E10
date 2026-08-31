"""
Common utility helpers including text-to-speech, browser operations, and clipboard.
"""

import queue
import shutil
import threading
import time
import webbrowser
from typing import Optional

from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# Global audio playback queue and locks.
_audio_queue = queue.Queue()
_audio_lock = threading.Lock()
_audio_worker_thread = None
_audio_worker_running = False
_audio_device_warmed_up = False


def _warm_up_audio_device():
    """
    Warm up the audio device to avoid clipping the first sound.
    """
    global _audio_device_warmed_up
    if _audio_device_warmed_up:
        return

    try:
        import platform
        import subprocess

        system = platform.system()

        if system == "Darwin":
            subprocess.run(
                ["say", "-v", "Ting-Ting", "hum"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif system == "Linux" and shutil.which("espeak"):
            subprocess.run(
                ["espeak", "-v", "zh", "hum"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif system == "Windows":
            import win32com.client

            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak("hum")

        _audio_device_warmed_up = True
        logger.info("Audio device warmed up.")
    except Exception as e:
        logger.warning(f"Failed to warm up audio device: {e}")


def _audio_queue_worker():
    """
    Audio queue worker thread to keep playback ordered and unclipped.
    """

    while _audio_worker_running:
        try:
            text = _audio_queue.get(timeout=1)
            if text is None:
                break

            with _audio_lock:
                logger.info(f"Starting audio playback: {text[:50]}...")
                success = _play_system_tts(text)

                if not success:
                    logger.warning("System TTS failed; trying fallback.")
                    import os

                    if os.name == "nt":
                        _play_windows_tts(text, set_chinese_voice=False)
                    else:
                        _play_system_tts(text)

                time.sleep(0.5)  # Pause after playback to avoid tail clipping.

            _audio_queue.task_done()

        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Audio queue worker error: {e}")

    logger.info("Audio queue worker stopped.")


def _ensure_audio_worker():
    """
    Ensure the audio worker thread is running.
    """
    global _audio_worker_thread, _audio_worker_running

    if _audio_worker_thread is None or not _audio_worker_thread.is_alive():
        _warm_up_audio_device()
        _audio_worker_running = True
        _audio_worker_thread = threading.Thread(target=_audio_queue_worker, daemon=True)
        _audio_worker_thread.start()
        logger.info("Audio queue worker started.")


def open_url(url: str) -> bool:
    try:
        success = webbrowser.open(url)
        if success:
            logger.info(f"Opened webpage successfully: {url}")
        else:
            logger.warning(f"Unable to open webpage: {url}")
        return success
    except Exception as e:
        logger.error(f"Error opening webpage: {e}")
        return False


def copy_to_clipboard(text: str) -> bool:
    try:
        import pyperclip

        pyperclip.copy(text)
        logger.info(f'Text "{text}" copied to clipboard.')
        return True
    except ImportError:
        logger.warning("pyperclip is not installed; cannot copy to clipboard.")
        return False
    except Exception as e:
        logger.error(f"Error copying to clipboard: {e}")
        return False


def _play_windows_tts(text: str, set_chinese_voice: bool = True) -> bool:
    try:
        import win32com.client

        speaker = win32com.client.Dispatch("SAPI.SpVoice")

        if set_chinese_voice:
            try:
                voices = speaker.GetVoices()
                for i in range(voices.Count):
                    if "Chinese" in voices.Item(i).GetDescription():
                        speaker.Voice = voices.Item(i)
                        break
            except Exception as e:
                logger.warning(f"Failed to set Chinese voice: {e}")

        try:
            speaker.Rate = -2
        except Exception:
            pass

        enhanced_text = text + "..."
        speaker.Speak(enhanced_text)
        logger.info("Played text with Windows TTS.")
        time.sleep(0.5)
        return True
    except ImportError:
        logger.warning("Windows TTS unavailable; skipping playback.")
        return False
    except Exception as e:
        logger.error(f"Windows TTS playback error: {e}")
        return False


def _play_linux_tts(text: str) -> bool:
    import subprocess

    if shutil.which("espeak"):
        try:
            enhanced_text = text + "..."
            result = subprocess.run(
                ["espeak", "-v", "zh", "-s", "150", "-g", "10", enhanced_text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            time.sleep(0.5)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.warning("espeak playback timed out.")
            return False
        except Exception as e:
            logger.error(f"espeak playback error: {e}")
            return False
    else:
        logger.warning("espeak unavailable; skipping playback.")
        return False


def _play_macos_tts(text: str) -> bool:
    import subprocess

    if shutil.which("say"):
        try:
            enhanced_text = text + "..."
            result = subprocess.run(
                ["say", "-r", "180", enhanced_text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            time.sleep(0.5)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.warning("say command playback timed out.")
            return False
        except Exception as e:
            logger.error(f"say command playback error: {e}")
            return False
    else:
        logger.warning("say command unavailable; skipping playback.")
        return False


def _play_system_tts(text: str) -> bool:
    import os
    import platform

    if os.name == "nt":
        return _play_windows_tts(text)
    else:
        system = platform.system()
        if system == "Linux":
            return _play_linux_tts(text)
        elif system == "Darwin":
            return _play_macos_tts(text)
        else:
            logger.warning(f"Unsupported system {system}; skipping playback.")
            return False


def play_audio_nonblocking(text: str) -> None:
    try:
        _ensure_audio_worker()
        _audio_queue.put(text)
        logger.info(f"Added audio task to queue: {text[:50]}...")
    except Exception as e:
        logger.error(f"Error adding audio task to queue: {e}")

        def audio_worker():
            try:
                _warm_up_audio_device()
                _play_system_tts(text)
            except Exception as e:
                logger.error(f"Fallback audio playback error: {e}")

        threading.Thread(target=audio_worker, daemon=True).start()


def extract_verification_code(text: str) -> Optional[str]:
    try:
        import re

        # TODO(i18n): Activation keywords include Chinese data for matching.
        # Activation-related keywords (lowercase for case-insensitive matching).
        activation_keywords = [
            "登录",
            "控制面板",
            "激活",
            "验证码",
            "绑定设备",
            "添加设备",
            "输入验证码",
            "输入",
            "面板",
            "xiaozhi.me",
            "激活码",
            "login",
            "control panel",
            "activate",
            "verification code",
            "bind device",
            "add device",
            "enter verification code",
            "enter code",
            "enter",
            "panel",
            "activation code",
        ]

        # Check if the text contains activation-related keywords.
        text_lower = text.lower()
        has_activation_keyword = any(
            keyword in text_lower for keyword in activation_keywords
        )

        if not has_activation_keyword:
            logger.debug(
                "Text does not contain activation keywords; skip code extraction: %s",
                text,
            )
            return None

        # More precise verification code patterns.
        # Match 6-digit codes, possibly separated by spaces.
        patterns = [
            r"验证码[：:]\s*(\d{6})",  # Verification code: 123456
            r"输入验证码[：:]\s*(\d{6})",  # Enter verification code: 123456
            r"输入\s*(\d{6})",  # Enter 123456
            r"验证码\s*(\d{6})",  # Verification code 123456
            r"激活码[：:]\s*(\d{6})",  # Activation code: 123456
            r"verification code[：:]\s*(\d{6})",
            r"enter verification code[：:]\s*(\d{6})",
            r"enter code[：:]\s*(\d{6})",
            r"enter\s*(\d{6})",
            r"code\s*(\d{6})",
            r"(\d{6})[，,。.]",  # 123456, or 123456.
            r"[，,。.]\s*(\d{6})",  # , 123456
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                code = match.group(1)
                logger.info(f"Extracted verification code from text: {code}")
                return code

        # If activation keywords exist but no precise match, try a generic pattern.
        # Require surrounding context for safety.
        match = re.search(r"((?:\d\s*){6,})", text)
        if match:
            code = "".join(match.group(1).split())
            # Verification code should be 6 digits.
            if len(code) == 6 and code.isdigit():
                logger.info(f"Extracted verification code (generic match): {code}")
                return code

        logger.warning(f"Failed to find verification code in text: {text}")
        return None
    except Exception as e:
        logger.error(f"Error extracting verification code: {e}")
        return None


def handle_verification_code(text: str) -> None:
    code = extract_verification_code(text)
    if not code:
        return

    copy_to_clipboard(code)
