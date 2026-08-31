"""
TTS Client — Direct local edge-tts integration inside the application.

Synthesises audio in the background directly inside the python client, using edge-tts.
Eliminates the FastAPI HTTP server daemon and reduces latency.
"""

import asyncio
import io
import re
import time
import hashlib
import queue
import threading
from typing import Optional, Callable
from functools import lru_cache

from src.utils.logging_config import get_logger

logger = get_logger(__name__)

_MULTI_DOTS_RE = re.compile(r'\.{2,}')
_SPACED_DOTS_RE = re.compile(r'\.\s*\.\s*\.\s*')

try:
    import miniaudio
    _HAS_MINIAUDIO = True
except ImportError:
    _HAS_MINIAUDIO = False
    logger.warning("miniaudio not installed — TTS playback disabled")

try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False
    logger.warning("edge-tts not installed — TTS synthesis disabled")


class TTSClient:
    """Direct, embedded wrapper around the local edge-tts engine with persistent playback."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",  # Kept for compatibility
        enabled: bool = True,
        voice: str = "pt-BR-FranciscaNeural",
        rate: str = "-13%",
        pitch: str = "+3Hz",
        volume: str = "+0%",
    ):
        self._enabled = enabled and _HAS_MINIAUDIO and _HAS_EDGE_TTS
        self._voice = voice
        self._rate = rate
        self._pitch = pitch
        self._volume = volume
        self._audio_lock = asyncio.Lock()
        self._cache: dict[str, bytes] = {}
        self._cache_max = 128

        # Persistent audio playback queue & device
        self._queue = queue.Queue()
        self._device = None
        self._sample_rate = 24000
        self._channels = 1

        # mDNS / Remote API
        self._base_url = base_url
        self._resolved_url = None
        self._session = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    async def health_check(self) -> bool:
        """Verify the edge-tts local module functions properly."""
        if not self._enabled:
            return False

        # Resolve mDNS if base_url is set to mina-tts.local or mdns
        if "mina-tts.local" in self._base_url or self._base_url == "mdns":
            self._resolved_url = await asyncio.to_thread(self._resolve_mdns)
        elif self._base_url and self._base_url != "local":
            self._resolved_url = self._base_url

        try:
            await edge_tts.list_voices()
            logger.info("Local embedded TTS engine initialized (voice=%s, resolved_remote=%s)", self._voice, self._resolved_url)
            return True
        except Exception as exc:
            logger.warning("Embedded TTS engine check failed (no internet?): %s", exc)
        self._enabled = False
        return False

    def _resolve_mdns(self) -> Optional[str]:
        """Discover the MinaTTS FastAPI service dynamically using Zeroconf."""
        try:
            from zeroconf import Zeroconf
            import socket
            zc = Zeroconf()
            logger.info("Performing mDNS discovery for MinaTTS._http._tcp.local...")
            info = zc.get_service_info("_http._tcp.local.", "MinaTTS._http._tcp.local.", timeout=2000)
            if info:
                addresses = info.addresses
                if addresses:
                    ip = socket.inet_ntoa(addresses[0])
                    port = info.port
                    resolved = f"http://{ip}:{port}"
                    logger.info("mDNS discovered MinaTTS at %s", resolved)
                    return resolved
            logger.warning("mDNS service MinaTTS._http._tcp.local not found (timeout)")
        except Exception as exc:
            logger.warning("mDNS Zeroconf lookup error: %s", exc)
        finally:
            try:
                zc.close()
            except Exception:
                pass
        return None

    def pre_synthesize(self, text: str) -> Optional[asyncio.Task]:
        """Fire-and-forget synthesis — returns a Task that resolves to bytes."""
        if not self._enabled or not text.strip():
            return None
        return asyncio.create_task(self._fetch_audio(text))

    @staticmethod
    @lru_cache(maxsize=1024)
    def _normalize_text(text: str) -> str:
        if not text:
            return ""
        # Remove espaços duplos ou quebras de linha
        text = " ".join(text.split())

        # Substitui múltiplos pontos/reticências por "..."
        text = _MULTI_DOTS_RE.sub('...', text)

        # Garante que haja um espaço após pontuações comuns
        for punct in [".", ",", "!", "?", ";", ":"]:
            text = text.replace(f" {punct}", punct)
            text = text.replace(punct, f"{punct} ")

        # Corrige reticências espaçadas (ex: ". . .") geradas pelo loop anterior de volta para "..."
        text = _SPACED_DOTS_RE.sub('... ', text)

        # Reduz espaços repetidos gerados
        text = " ".join(text.split())

        # Garante que o texto termine com alguma pontuação para fechar a entonação
        if text and text[-1] not in [".", "!", "?", "..."]:
            if not text.endswith("..."):
                text += "."

        return text.strip()

    def _cache_key(self, text: str) -> str:
        raw = f"{text}|{self._voice}|{self._rate}|{self._pitch}|{self._volume}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _fetch_audio(self, text: str) -> Optional[bytes]:
        """Synthesize MP3 bytes using remote server if available, falling back to local edge_tts."""
        text = self._normalize_text(text)
        key = self._cache_key(text)
        if key in self._cache:
            logger.debug("TTS cache hit for: '%s'", text[:30])
            return self._cache[key]

        if self._resolved_url:
            try:
                t0 = time.perf_counter()
                import aiohttp

                if self._session is None or self._session.closed:
                    self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))

                payload = {
                    "text": text,
                    "voice": self._voice,
                    "rate": self._rate,
                    "pitch": self._pitch,
                    "volume": self._volume
                }
                async with self._session.post(f"{self._resolved_url}/synthesize", json=payload) as resp:
                    if resp.status == 200:
                        audio = await resp.read()
                        elapsed = time.perf_counter() - t0
                        logger.info("TTS remote synthesis OK | chars=%d | latency=%.3fs | server=%s", len(text), elapsed, self._resolved_url)

                        if len(self._cache) >= self._cache_max:
                            oldest = next(iter(self._cache))
                            del self._cache[oldest]
                        self._cache[key] = audio
                        return audio
                    else:
                        body = await resp.text()
                        logger.warning("Remote TTS synthesis returned error status %d: %s", resp.status, body)
            except Exception as exc:
                logger.warning("Failed to fetch remote TTS audio, falling back to local: %s", exc)

        try:
            t0 = time.perf_counter()
            communicate = edge_tts.Communicate(
                text,
                self._voice,
                rate=self._rate,
                pitch=self._pitch,
                volume=self._volume
            )
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            audio = buf.getvalue()

            elapsed = time.perf_counter() - t0
            logger.info("TTS local synthesis OK | chars=%d | latency=%.3fs | cache=%d", len(text), elapsed, len(self._cache))

            if len(self._cache) >= self._cache_max:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = audio
            return audio
        except Exception as exc:
            logger.warning("Local TTS synthesis error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Persistent Playback Device & Thread-Safe Queue
    # ------------------------------------------------------------------

    async def play(self, audio_bytes: bytes, on_start: Optional[Callable] = None) -> None:
        """Play MP3 bytes through the persistent output device (0ms latency, no cutoff)."""
        if not _HAS_MINIAUDIO or not audio_bytes:
            return
        async with self._audio_lock:
            try:
                decoded = await asyncio.to_thread(miniaudio.decode, audio_bytes, output_format=miniaudio.SampleFormat.SIGNED16)
                if not decoded.samples or decoded.num_frames == 0:
                    return

                # Ensure the playback device is initialized and active
                self._ensure_device_started(decoded.sample_rate, decoded.nchannels)

                # Convert array of samples to raw bytes
                samples_bytes = decoded.samples.tobytes()
                duration = decoded.num_frames / decoded.sample_rate

                # Create a completion event for this specific chunk
                chunk_started = threading.Event()
                chunk_finished = threading.Event()
                self._queue.put((samples_bytes, chunk_started, chunk_finished))

                # Wait until the hardware actually starts processing this chunk
                await asyncio.to_thread(chunk_started.wait)

                if on_start:
                    if asyncio.iscoroutinefunction(on_start):
                        await on_start()
                    else:
                        on_start()

                # Block until this chunk finishes playing through the speakers
                await asyncio.sleep(duration)
            except Exception as exc:
                logger.warning("TTS playback error: %s", exc)

    def _ensure_device_started(self, sample_rate: int, channels: int) -> None:
        if self._device is not None:
            if self._sample_rate == sample_rate and self._channels == channels:
                return
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

        self._sample_rate = sample_rate
        self._channels = channels

        logger.info("Starting persistent miniaudio PlaybackDevice (rate=%d, channels=%d)", sample_rate, channels)
        self._device = miniaudio.PlaybackDevice(
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=channels,
            sample_rate=sample_rate,
        )

        gen = self._generator()
        next(gen)
        self._device.start(gen)

    def _generator(self):
        # miniaudio expects bytes or array objects. Yield empty bytes to prime.
        required = yield b""

        current_samples = None
        current_pos = 0
        current_started = None
        current_finished = None

        while True:
            # SIGNED16 format has 2 bytes per sample
            bytes_needed = required * self._channels * 2
            out_buf = bytearray()

            while len(out_buf) < bytes_needed:
                if current_samples is None:
                    try:
                        item = self._queue.get_nowait()
                        current_samples, current_started, current_finished = item
                        current_pos = 0
                        if current_started:
                            current_started.set()
                    except queue.Empty:
                        # No more audio in queue. Pad the rest of the buffer with silence.
                        remaining = bytes_needed - len(out_buf)
                        out_buf.extend(b"\x00" * remaining)
                        break

                # Copy from current_samples to out_buf
                chunk_needed = bytes_needed - len(out_buf)
                available = len(current_samples) - current_pos
                to_read = min(chunk_needed, available)

                out_buf.extend(current_samples[current_pos : current_pos + to_read])
                current_pos += to_read

                if current_pos >= len(current_samples):
                    if current_finished:
                        current_finished.set()
                    current_samples = None
                    current_started = None
                    current_finished = None

            required = yield bytes(out_buf)
