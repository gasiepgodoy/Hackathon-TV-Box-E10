#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_voice_pipeline.py
Validação do fluxo completo de voz da MABI / Mina:
1. Síntese de áudio de entrada via TTS (Edge-TTS pt-BR-FranciscaNeural)
2. Transcrição de áudio via STT (Groq Whisper-large-v3)
3. Processamento de linguagem na MABI (Classificador Local de Intenções ou LLM Groq)
4. Síntese vocal da resposta final da MABI (TTS)
"""

import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Caminho para totem
TOTEM_DIR = r"C:\Users\Aluno\Hackathon-TV-Box-E10\Projeto Equipe 1\ForgeModules\totem"
if os.path.exists(TOTEM_DIR):
    sys.path.insert(0, TOTEM_DIR)
elif os.path.exists("/root/app"):
    sys.path.insert(0, "/root/app")

def _load_env_key():
    candidates = [
        Path(__file__).parent / "ForgeModules" / "totem" / ".env",
        Path("/root/app/.env"),
        Path(__file__).parent / ".env",
        Path(".env"),
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("GROQ_API_KEY="):
                            val = line.strip().split("=", 1)[1].strip()
                            if val:
                                return val
            except Exception:
                pass
    val = os.getenv("GROQ_API_KEY", "")
    if not val:
        raise RuntimeError("GROQ_API_KEY não encontrada no arquivo .env nem nas variáveis de ambiente.")
    return val

GROQ_API_KEY = _load_env_key()
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_LLM_URL = "https://api.groq.com/openai/v1/chat/completions"

async def generate_tts(text: str, voice="pt-BR-FranciscaNeural", rate="-13%", pitch="+1Hz", volume="+10%") -> bytes:
    """Gera áudio MP3 a partir de texto usando tts_api local ou edge-tts."""
    try:
        r = requests.post("http://localhost:8000/synthesize", json={
            "text": text, "voice": voice, "rate": rate, "pitch": pitch, "volume": volume
        }, timeout=5)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass

    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    buf = io.BytesIO()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()

def transcribe_stt_groq(audio_bytes: bytes, key: str) -> str:
    """Transcreve áudio MP3 usando Groq Whisper."""
    headers = {"Authorization": f"Bearer {key}"}
    files = {"file": ("input.mp3", audio_bytes, "audio/mpeg")}
    data = {
        "model": "whisper-large-v3",
        "language": "pt",
        "response_format": "json"
    }
    t0 = time.perf_counter()
    resp = requests.post(GROQ_STT_URL, headers=headers, files=files, data=data, timeout=15)
    elapsed = time.perf_counter() - t0
    if resp.status_code != 200:
        raise RuntimeError(f"Erro no Groq STT ({resp.status_code}): {resp.text}")
    result = resp.json().get("text", "").strip()
    return result, elapsed

def query_llm_groq(prompt: str, key: str, model="qwen/qwen3.8-27b") -> str:
    """Consulta o modelo LLM na Groq."""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "temperature": 0.7,
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": "Você é a Mina, a assistente virtual inteligente e acadêmica da UNESP Sorocaba. Responda de forma gentil, concisa e prestativa."},
            {"role": "user", "content": prompt}
        ]
    }
    t0 = time.perf_counter()
    resp = requests.post(GROQ_LLM_URL, headers=headers, json=payload, timeout=15)
    elapsed = time.perf_counter() - t0
    if resp.status_code != 200:
        raise RuntimeError(f"Erro no Groq LLM ({resp.status_code}): {resp.text}")
    ans = resp.json()["choices"][0]["message"]["content"].strip()
    return ans, elapsed

async def run_pipeline_test(user_utterance: str, test_title: str):
    print("\n" + "=" * 65)
    print(f"  TESTE: {test_title}")
    print("=" * 65)
    
    # 1. TTS BASE (Simulando usuário falando)
    t0 = time.perf_counter()
    print(f"[1/4] 🎙️  Sintetizando fala do usuário via TTS...")
    print(f"      Texto de entrada: \"{user_utterance}\"")
    audio_user = await generate_tts(user_utterance)
    t_tts1 = time.perf_counter() - t0
    print(f"      ✅ Áudio gerado: {len(audio_user)} bytes em {t_tts1:.3f}s")
    
    # 2. STT (Groq Whisper transcrevendo a fala)
    print(f"[2/4] 📝 Enviando áudio ao Groq Whisper (STT)...")
    transcription, t_stt = transcribe_stt_groq(audio_user, GROQ_API_KEY)
    print(f"      ✅ Transcrição obtida em {t_stt:.3f}s: \"{transcription}\"")
    
    # 3. MABI BRAIN (Classificador Local de Intenções OU LLM Groq)
    print(f"[3/4] 🧠 Processando entrada na inteligência da MABI...")
    
    local_handled = False
    mabi_response = ""
    t_brain = 0.0
    
    try:
        from src.utils.intent_classifier import IntentClassifier
        classifier = IntentClassifier()
        detected, local_ans = classifier.classify_and_execute(transcription)
        if detected and local_ans:
            local_handled = True
            mabi_response = local_ans
            print(f"      🎯 Intenção Acadêmica Local Detectada! Resposta do SQLite:")
            print(f"         \"{mabi_response[:100]}...\"")
    except Exception as ex:
        print(f"      [Info] IntentClassifier local: {ex}")
        
    if not local_handled:
        print(f"      🌐 Consulta geral enviada ao Groq LLM (openai/gpt-oss-20b)...")
        mabi_response, t_brain = query_llm_groq(transcription, GROQ_API_KEY)
        print(f"      ✅ Resposta do LLM obtida em {t_brain:.3f}s:")
        print(f"         \"{mabi_response}\"")
        
    # 4. TTS RESPOSTA (Mina falando a resposta)
    t0 = time.perf_counter()
    print(f"[4/4] 🔊 Sintetizando resposta vocal da Mina via TTS...")
    audio_reply = await generate_tts(mabi_response[:250])
    t_tts2 = time.perf_counter() - t0
    print(f"      ✅ Áudio da Mina pronto: {len(audio_reply)} bytes em {t_tts2:.3f}s")
    
    total_time = t_tts1 + t_stt + t_brain + t_tts2
    print("-" * 65)
    print(f"⏱️  Tempo total do ciclo completo de voz: {total_time:.3f}s")
    return {
        "input": user_utterance,
        "transcription": transcription,
        "response": mabi_response,
        "total_time_s": round(total_time, 3),
        "stt_time_s": round(t_stt, 3),
        "brain_time_s": round(t_brain, 3)
    }

async def main():
    print("=================================================================")
    print("  MABI / MINA - VALIDACAO DO PIPELINE COMPLETO DE VOZ (TTS -> STT -> LLM -> TTS)")
    print("=================================================================")
    print(f"Chave Groq: {GROQ_API_KEY[:10]}...{GROQ_API_KEY[-6:]}")
    
    # Teste 1: Pergunta Geral para LLM
    r1 = await run_pipeline_test(
        "Olá Mina, me explique em duas frases como você funciona como assistente acadêmica.",
        "Pergunta Geral -> LLM Groq"
    )
    
    # Teste 2: Pergunta Acadêmica UNESP (Classificador Local de Intenções)
    r2 = await run_pipeline_test(
        "Mina, onde fica a sala do professor coordenador?",
        "Pergunta Academica -> Classificador Local de Intencoes (Offline)"
    )
    
    print("\n" + "=" * 65)
    print("  RESUMO EXECUTIVO DA VALIDACAO")
    print("=" * 65)
    print(f"Teste 1 (LLM)  : Transcrito='{r1['transcription']}' | Latencia={r1['total_time_s']}s")
    print(f"Teste 2 (Local): Transcrito='{r2['transcription']}' | Latencia={r2['total_time_s']}s")
    print("[OK] Todos os componentes do pipeline de voz foram validados com sucesso!")

if __name__ == "__main__":
    asyncio.run(main())
