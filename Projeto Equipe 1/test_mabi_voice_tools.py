#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_mabi_voice_tools.py
==============================================================================
MABI / ForgeOS — Assistente Vocal Inteligente com Tool Calling Direto
==============================================================================
Zero Regex / Zero Intent Classifier.
A LLM (Groq / openai/gpt-oss-20b) recebe prompt engineering orientado a voz,
avalia a pergunta, decide autonomamente executar ferramentas (Tool Calls)
sobre o banco de dados oficial da UNESP Sorocaba (SQLite/APIs), formula uma
resposta concisa para síntese de voz (TTS) e reproduz o áudio nos alto-falantes.
"""

import os
import sys
import json
import sqlite3
import requests
import asyncio
import tempfile
import time
import argparse
import unicodedata
import subprocess
from pathlib import Path

# Suporte a caracteres acentuados no terminal Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def strip_accents(s: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas."""
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").lower()

def get_groq_key() -> str:
    key = os.getenv("GROQ_API_KEY", "")
    if key:
        return key
    candidates = [
        Path(__file__).parent / "ForgeModules" / "totem" / ".env",
        Path(__file__).parent / ".env",
        Path(r"C:\Users\Aluno\Hackathon-TV-Box-E10\Projeto Equipe 1\ForgeModules\totem\.env"),
        Path("/root/app/.env"),
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
    return os.getenv("GROQ_API_KEY", "")

GROQ_API_KEY = get_groq_key()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"

def get_db_path() -> str:
    candidates = [
        Path(__file__).parent / "config" / "academic.db",
        Path(r"C:\Users\Aluno\Hackathon-TV-Box-E10\Projeto Equipe 1\config\academic.db"),
        Path(r"C:\Users\Aluno\Hackathon-TV-Box-E10\Projeto Equipe 1\ForgeModules\totem\config\academic.db"),
        Path("/root/app/config/academic.db"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(Path(__file__).parent / "config" / "academic.db")

DB_PATH = get_db_path()

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.create_function("strip_accents", 1, strip_accents)
    return conn

# ==============================================================================
# FERRAMENTAS ACADÊMICAS (TOOL CALLING)
# ==============================================================================

def consultar_professor(nome_professor: str):
    """Consulta salas, gabinetes, ramais, e-mails e departamentos de docentes da UNESP."""
    if not os.path.exists(DB_PATH):
        return {"status": "error", "message": "Banco de dados acadêmico indisponível."}
    conn = get_db_conn()
    c = conn.cursor()
    term = f"%{strip_accents(nome_professor)}%"
    c.execute("""
        SELECT name, room, email, department 
        FROM professors 
        WHERE strip_accents(name) LIKE ? OR strip_accents(email) LIKE ?
        LIMIT 5
    """, (term, term))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return {"status": "not_found", "message": f"Nenhum professor encontrado com o nome '{nome_professor}'."}
    return {
        "status": "found",
        "professores": [
            {"nome": r[0], "sala_gabinete": r[1], "email": r[2] or "Não informado", "departamento": r[3] or "Geral"} 
            for r in rows
        ]
    }

def consultar_aulas(dia_semana: str = "segunda", curso: str = "todos"):
    """Consulta a grade horária oficial de aulas e salas por dia da semana."""
    if not os.path.exists(DB_PATH):
        return {"status": "error", "message": "Banco de dados indisponível."}
    weekday_map = {
        "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6
    }
    dia_clean = strip_accents(dia_semana).replace("-feira", "")
    day_idx = weekday_map.get(dia_clean, 0)
    
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT subject_name, start_time, end_time, room, professor_name 
        FROM classes 
        WHERE weekday = ? 
        LIMIT 6
    """, (day_idx,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return {"status": "empty", "message": f"Não há aulas cadastradas para {dia_semana}."}
    return {
        "status": "ok",
        "dia": dia_semana,
        "total_encontrado": len(rows),
        "aulas": [
            {"disciplina": r[0], "horario": f"{r[1]} às {r[2]}", "sala": r[3], "docente": r[4]}
            for r in rows
        ]
    }

def consultar_calendario_academico(termo_busca: str = "aulas"):
    """Consulta eventos letivos, feriados, datas de matrícula e início das aulas."""
    if not os.path.exists(DB_PATH):
        return {"status": "error", "message": "Banco de dados indisponível."}
    conn = get_db_conn()
    c = conn.cursor()
    term = f"%{strip_accents(termo_busca)}%"
    c.execute("""
        SELECT date_start, date_end, title, category, description 
        FROM academic_calendar 
        WHERE strip_accents(title) LIKE ? 
           OR strip_accents(category) LIKE ? 
           OR strip_accents(description) LIKE ?
        ORDER BY date_start ASC 
        LIMIT 5
    """, (term, term, term))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return {"status": "not_found", "message": f"Nenhum evento do calendário encontrado para '{termo_busca}'."}
    return {
        "status": "ok",
        "eventos": [
            {"data_inicio": r[0], "data_fim": r[1], "evento": r[2], "categoria": r[3], "detalhe": r[4]}
            for r in rows
        ]
    }

def buscar_documentos_academicos(termo: str):
    """Busca em normas acadêmicas, manuais de estágio e resoluções do campus."""
    if not os.path.exists(DB_PATH):
        return {"status": "error", "message": "Banco de dados indisponível."}
    conn = get_db_conn()
    c = conn.cursor()
    term = f"%{strip_accents(termo)}%"
    c.execute("""
        SELECT d.title, s.section_title, s.content 
        FROM document_sections s
        JOIN documents d ON s.document_id = d.id
        WHERE strip_accents(s.content) LIKE ? OR strip_accents(s.section_title) LIKE ?
        LIMIT 3
    """, (term, term))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return {"status": "not_found", "message": f"Nenhum regulamento encontrado com o termo '{termo}'."}
    return {
        "status": "ok",
        "trechos": [
            {"documento": r[0], "secao": r[1], "resumo": r[2][:180]}
            for r in rows
        ]
    }

AVAILABLE_TOOLS = {
    "consultar_professor": consultar_professor,
    "consultar_aulas": consultar_aulas,
    "consultar_calendario_academico": consultar_calendario_academico,
    "buscar_documentos_academicos": buscar_documentos_academicos
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "consultar_professor",
            "description": "Consulta a localização da sala, gabinete, e-mail e departamento de um professor da UNESP Sorocaba.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_professor": {
                        "type": "string",
                        "description": "Nome ou sobrenome do professor pesquisado (ex: Eduardo, Liberado, Maria)"
                    }
                },
                "required": ["nome_professor"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_aulas",
            "description": "Consulta a grade oficial de aulas, horários e salas por dia da semana da UNESP Sorocaba.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dia_semana": {
                        "type": "string",
                        "description": "Dia da semana (segunda, terca, quarta, quinta, sexta)"
                    },
                    "curso": {
                        "type": "string",
                        "description": "Sigla do curso (ECA ou EA, ou 'todos')"
                    }
                },
                "required": ["dia_semana"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_calendario_academico",
            "description": "Consulta datas oficiais do calendário escolar: início de aulas, término, feriados, exames e prazos de matrícula.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_busca": {
                        "type": "string",
                        "description": "Termo de busca no calendário (ex: inicio, matricula, aulas, recesso, exame)"
                    }
                },
                "required": ["termo_busca"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_documentos_academicos",
            "description": "Pesquisa em normas oficiais, manuais de graduação e resoluções do campus Sorocaba.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {
                        "type": "string",
                        "description": "Palavra-chave sobre regulamentos ou procedimentos acadêmicos"
                    }
                },
                "required": ["termo"]
            }
        }
    }
]

# ==============================================================================
# SÍNTESE E REPRODUÇÃO DE ÁUDIO REAL (TTS + ALTO-FALANTES)
# ==============================================================================

async def synthesize_speech(text: str, output_path: str):
    """Sintetiza áudio MP3 utilizando Edge-TTS pt-BR."""
    import edge_tts
    comm = edge_tts.Communicate(text, "pt-BR-FranciscaNeural", rate="-6%", pitch="+0Hz")
    await comm.save(output_path)

def play_audio(audio_file: str):
    """Toca o áudio diretamente nos alto-falantes."""
    if sys.platform == "win32":
        import ctypes
        alias = f"mabi_spk_{int(time.time()*1000)}"
        ctypes.windll.winmm.mciSendStringW(f'open "{audio_file}" type mpegvideo alias {alias}', None, 0, None)
        ctypes.windll.winmm.mciSendStringW(f'play {alias} wait', None, 0, None)
        ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, None)
    else:
        for player in ["mpv", "play", "ffplay", "mplayer"]:
            try:
                subprocess.run([player, audio_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                return
            except Exception:
                pass

# ==============================================================================
# PIPELINE COMPLETO (PROMPT ENGINEERING + TOOL CALLING)
# ==============================================================================

def process_question_with_tools(user_text: str, play_sound: bool = True):
    print("\n" + "=" * 70)
    print(f"👤 ALUNO: \"{user_text}\"")
    print("=" * 70)
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "Você é a MABI (Módulo Acadêmico Baseado em Inteligência Artificial), a voz oficial do Totem da UNESP Sorocaba.\n\n"
        "DIRETRIZES FUNDAMENTAIS:\n"
        "1. SEM REGEX / SEM ADIVINHAÇÃO: Você não decora salas ou horários. Toda vez que o usuário perguntar sobre professores, salas, aulas, calendário escolar ou documentos acadêmicos, VOCÊ DEVE OBRIGATORIAMENTE EXECUTAR A FERRAMENTA ADEQUADA.\n"
        "2. DESIGN PARA VOZ (TTS): A sua resposta será FALADA para o usuário. Use linguagem amigável, clara, empática e fluida. NUNCA use tabelas, markdown com asteriscos, códigos ou listas longas que soem mecânicas quando lidas em voz alta.\n"
        "3. CONCISÃO: Diga a resposta direta em 1 a 3 frases naturais."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]

    t0 = time.perf_counter()
    print("🤖 IA analisando a pergunta e decidindo ferramentas (Tool Calling)...")
    resp = requests.post(
        GROQ_URL,
        headers=headers,
        json={"model": GROQ_MODEL, "messages": messages, "tools": TOOLS_SCHEMA, "tool_choice": "auto"},
        timeout=15
    )
    if resp.status_code != 200:
        print(f"❌ Erro na chamada à Groq ({resp.status_code}): {resp.text}")
        return

    msg = resp.json()["choices"][0]["message"]
    messages.append(msg)

    # Executa as ferramentas chamadas pela IA
    if msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except Exception:
                args = {}
            print(f"🛠️  TOOL CALL ACIONADA: {fn_name}({args})")
            fn = AVAILABLE_TOOLS.get(fn_name)
            if fn:
                result = fn(**args)
                print(f"📊 Dados obtidos do Banco/API: {result}")
            else:
                result = {"status": "error", "message": "Ferramenta desconhecida."}

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False)
            })

        print("🧠 Sintetizando resposta final orientada a voz...")
        resp2 = requests.post(
            GROQ_URL,
            headers=headers,
            json={"model": GROQ_MODEL, "messages": messages},
            timeout=15
        )
        if resp2.status_code != 200:
            print(f"❌ Erro na síntese da resposta ({resp2.status_code}): {resp2.text}")
            return
        final_reply = resp2.json()["choices"][0]["message"]["content"]
    else:
        print("ℹ️ Nenhuma ferramenta foi solicitada pela IA.")
        final_reply = msg["content"]

    t_total = time.perf_counter() - t0
    print("\n" + "-" * 70)
    print(f"🗣️  RESPOSTA MABI (Fala):")
    print(f"\"{final_reply}\"")
    print(f"⏱️  Tempo total de resposta: {t_total:.2f}s")
    print("-" * 70)

    if play_sound:
        print("🔊 Sintetizando e reproduzindo áudio nos alto-falantes...")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            audio_path = f.name
        try:
            asyncio.run(synthesize_speech(final_reply, audio_path))
            play_audio(audio_path)
            print("✅ Áudio reproduzido com sucesso!")
        finally:
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

def main():
    parser = argparse.ArgumentParser(description="MABI Voice & Tool Calling Tester")
    parser.add_argument("--pergunta", "-p", type=str, help="Pergunta direta para a MABI")
    parser.add_argument("--no-sound", action="store_true", help="Desabilitar áudio nos alto-falantes")
    args = parser.parse_args()

    print("==============================================================================")
    print("  MABI / ForgeOS — TESTE DE VOZ COM TOOL CALLING DIRETO (SEM CLASSIFIER)")
    print("==============================================================================")
    print(f"• Banco Acadêmico: {DB_PATH}")
    print(f"• Modelo LLM: {GROQ_MODEL} (Groq API)")
    print(f"• Reprodução de Som: {'Desabilitada' if args.no_sound else 'Ativada (Alto-falantes)'}")

    if args.pergunta:
        process_question_with_tools(args.pergunta, play_sound=not args.no_sound)
        return

    perguntas_demo = [
        "Onde fica a sala do professor Eduardo?",
        "Quais aulas acontecem na segunda-feira?",
        "Quando é o início das aulas no calendário letivo?"
    ]

    print("\nPerguntas demonstrativas:")
    for i, q in enumerate(perguntas_demo, 1):
        print(f" [{i}] {q}")
    print(" [0] Digitar uma pergunta personalizada\n")

    try:
        escolha = input("Selecione uma opção (1-3) ou pressione Enter para a primeira: ").strip()
    except EOFError:
        escolha = "1"

    if escolha in ["1", "2", "3"]:
        q = perguntas_demo[int(escolha) - 1]
        process_question_with_tools(q, play_sound=not args.no_sound)
    elif escolha == "0":
        try:
            q = input("Digite sua pergunta para a MABI: ").strip()
        except EOFError:
            q = perguntas_demo[0]
        if q:
            process_question_with_tools(q, play_sound=not args.no_sound)
    else:
        process_question_with_tools(perguntas_demo[0], play_sound=not args.no_sound)

if __name__ == "__main__":
    main()
