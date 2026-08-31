"""
TTS API - Edge TTS FastAPI Service
Voz padrão: pt-BR-FranciscaNeural (feminina suave)
"""
import asyncio
import hashlib
import io
import logging
import re
import time
import socket
from typing import AsyncIterator

import edge_tts
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
    _HAS_ZEROCONF = True
except ImportError:
    _HAS_ZEROCONF = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tts_api")

# ---------------------------------------------------------------------------
# Configuração de voz padrão (edge_feminina_suave)
# ---------------------------------------------------------------------------
DEFAULT_VOICE = "pt-BR-FranciscaNeural"
DEFAULT_RATE = "-13%"    # reduzida para 87% da velocidade normal
DEFAULT_PITCH = "+1Hz"   # um pouco mais fina
DEFAULT_VOLUME = "+10%"

# Cache em memória: sha256(params) → bytes MP3
_AUDIO_CACHE: dict[str, bytes] = {}
_CACHE_MAX = 128

app = FastAPI(
    title="TTS API",
    description="API de síntese de voz com Edge TTS — voz feminina suave (pt-BR-FranciscaNeural).",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Startup: pré-aquecimento
# ---------------------------------------------------------------------------
zeroconf_instance = None
service_info_instance = None

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


# ---------------------------------------------------------------------------
# Startup & Shutdown with mDNS Zeroconf
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def warm_up():
    global zeroconf_instance, service_info_instance
    log.info("Warming up...")
    try:
        await _synthesize_bytes("Olá, estou pronta.", DEFAULT_VOICE, DEFAULT_RATE, DEFAULT_PITCH, DEFAULT_VOLUME)
        log.info("Pré-aquecimento concluído.")
    except Exception as exc:
        log.warning("Pré-aquecimento falhou: %s", exc)

    if _HAS_ZEROCONF:
        try:
            local_ip = get_local_ip()
            log.info(f"Registering mDNS service for local IP: {local_ip}")
            desc = {'path': '/synthesize'}
            service_info_instance = ServiceInfo(
                "_http._tcp.local.",
                "MinaTTS._http._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=8000,
                properties=desc,
                server="mina-tts.local."
            )
            zeroconf_instance = Zeroconf(ip_version=IPVersion.V4Only)
            zeroconf_instance.register_service(service_info_instance)
            log.info("mDNS service successfully registered: mina-tts.local on port 8000")
        except Exception as exc:
            log.error("Failed to register mDNS service: %s", exc)


@app.on_event("shutdown")
def shutdown_mdns():
    global zeroconf_instance, service_info_instance
    if zeroconf_instance and service_info_instance:
        try:
            log.info("Unregistering mDNS service...")
            zeroconf_instance.unregister_service(service_info_instance)
            zeroconf_instance.close()
            log.info("mDNS service unregistered.")
        except Exception as exc:
            log.error("Error during mDNS shutdown: %s", exc)


# ---------------------------------------------------------------------------
# # Helpers
# ---------------------------------------------------------------------------
def _normalize_text(text: str) -> str:
    if not text:
        return ""
    # Remove espaços duplos ou quebras de linha
    text = " ".join(text.split())
    
    # Substitui múltiplos pontos/reticências por "..."
    text = re.sub(r'\.{2,}', '...', text)
    
    # Garante que haja um espaço após pontuações comuns
    for punct in [".", ",", "!", "?", ";", ":"]:
        text = text.replace(f" {punct}", punct)
        text = text.replace(punct, f"{punct} ")
        
    # Corrige reticências espaçadas (ex: ". . .") geradas pelo loop anterior de volta para "..."
    text = re.sub(r'\.\s*\.\s*\.\s*', '... ', text)
    
    # Reduz espaços repetidos gerados
    text = " ".join(text.split())
    
    # Garante que o texto termine com alguma pontuação para fechar a entonação
    if text and text[-1] not in [".", "!", "?", "..."]:
        if not text.endswith("..."):
            text += "."
        
    return text.strip()


def _cache_key(text: str, voice: str, rate: str, pitch: str, volume: str) -> str:
    raw = f"{text}|{voice}|{rate}|{pitch}|{volume}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _synthesize_bytes(text: str, voice: str, rate: str, pitch: str, volume: str) -> bytes:
    key = _cache_key(text, voice, rate, pitch, volume)
    if key in _AUDIO_CACHE:
        return _AUDIO_CACHE[key]

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    audio = buf.getvalue()

    if len(_AUDIO_CACHE) >= _CACHE_MAX:
        oldest = next(iter(_AUDIO_CACHE))
        del _AUDIO_CACHE[oldest]
    _AUDIO_CACHE[key] = audio
    return audio


async def _stream_generator(text: str, voice: str, rate: str, pitch: str, volume: str) -> AsyncIterator[bytes]:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice: str = Field(DEFAULT_VOICE)
    rate: str = Field(DEFAULT_RATE)
    pitch: str = Field(DEFAULT_PITCH)
    volume: str = Field(DEFAULT_VOLUME)
    stream: bool = Field(False, description="True = streaming chunked; False = MP3 completo")


class VoiceInfo(BaseModel):
    name: str
    locale: str
    gender: str
    friendly_name: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["infra"])
async def health():
    return {"status": "ok", "cache_entries": len(_AUDIO_CACHE), "default_voice": DEFAULT_VOICE}


@app.get("/voices", tags=["infra"])
async def list_voices(locale: str = Query(None, description="Filtrar por locale, ex: pt-BR")):
    try:
        voices = await edge_tts.list_voices()
    except Exception as exc:
        raise HTTPException(502, f"Falha ao listar vozes: {exc}")
    return [
        {"name": v["ShortName"], "locale": v["Locale"], "gender": v["Gender"], "friendly_name": v["FriendlyName"]}
        for v in voices
        if locale is None or v["Locale"].lower().startswith(locale.lower())
    ]


@app.post("/synthesize", tags=["tts"])
async def synthesize(req: SynthesizeRequest):
    t0 = time.perf_counter()
    req.text = _normalize_text(req.text)

    if req.stream:
        gen = _stream_generator(req.text, req.voice, req.rate, req.pitch, req.volume)
        return StreamingResponse(gen, media_type="audio/mpeg")

    try:
        audio = await _synthesize_bytes(req.text, req.voice, req.rate, req.pitch, req.volume)
    except Exception as exc:
        log.error("Erro na síntese: %s", exc)
        raise HTTPException(502, f"Falha na síntese: {exc}")

    elapsed = time.perf_counter() - t0
    log.info("Síntese OK | chars=%d | latência=%.3fs | cache=%d", len(req.text), elapsed, len(_AUDIO_CACHE))

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "X-Latency-Seconds": f"{elapsed:.3f}",
            "X-Voice": req.voice,
            "X-Text-Length": str(len(req.text)),
        },
    )


@app.get("/synthesize", tags=["tts"])
async def synthesize_get(
    text: str = Query(..., min_length=1, max_length=2000),
    voice: str = Query(DEFAULT_VOICE),
    rate: str = Query(DEFAULT_RATE),
    pitch: str = Query(DEFAULT_PITCH),
    volume: str = Query(DEFAULT_VOLUME),
):
    """GET conveniente para testes rápidos no browser."""
    try:
        audio = await _synthesize_bytes(text, voice, rate, pitch, volume)
    except Exception as exc:
        raise HTTPException(502, f"Falha na síntese: {exc}")
    return Response(content=audio, media_type="audio/mpeg")
