# -*- coding: utf-8 -*-
"""
academic_tools.py
==============================================================================
MABI / ForgeOS — Ferramentas Oficiais de Consulta Acadêmica (Tool Calling)
==============================================================================
Mapeia o banco de dados oficial (academic.db) da UNESP Sorocaba para o formato
de Function Calling (OpenAI / Groq Tools).
Elimina necessidade de Intent Classifier estático via regex.
"""

import os
import sys
import json
import sqlite3
import unicodedata
from pathlib import Path
from typing import Dict, Any, List
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

def strip_accents(s: str) -> str:
    """Remove acentos e converte para minúsculas para buscas semânticas flexíveis."""
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").lower()

def get_db_path() -> str:
    candidates = [
        Path(__file__).parent.parent.parent / "config" / "academic.db",
        Path("config/academic.db"),
        Path("/root/app/config/academic.db"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return str(candidates[0])

def _get_conn() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.create_function("strip_accents", 1, strip_accents)
    return conn

# ==============================================================================
# FUNÇÕES DE CONSULTA DIRETA
# ==============================================================================

def consultar_professor(nome_professor: str) -> Dict[str, Any]:
    """Consulta salas, gabinetes, ramais e e-mails de docentes."""
    try:
        conn = _get_conn()
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
            return {"status": "not_found", "message": f"Nenhum professor encontrado com '{nome_professor}'."}
        return {
            "status": "found",
            "total": len(rows),
            "professores": [
                {"nome": r[0], "sala_gabinete": r[1], "email": r[2] or "Não informado", "departamento": r[3] or "Geral"}
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("Erro ao consultar professor: %s", e)
        return {"status": "error", "message": str(e)}

def consultar_aulas(dia_semana: str = "segunda", curso: str = "todos") -> Dict[str, Any]:
    """Consulta a grade de horários de aulas, turmas e salas por dia da semana."""
    try:
        weekday_map = {
            "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6
        }
        dia_clean = strip_accents(dia_semana).replace("-feira", "")
        day_idx = weekday_map.get(dia_clean, 0)
        
        conn = _get_conn()
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
            "total_aulas": len(rows),
            "aulas": [
                {"disciplina": r[0], "horario": f"{r[1]} às {r[2]}", "sala": r[3], "docente": r[4]}
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("Erro ao consultar aulas: %s", e)
        return {"status": "error", "message": str(e)}

def consultar_calendario_academico(termo_busca: str = "aulas") -> Dict[str, Any]:
    """Consulta eventos escolares, datas de matrículas, exames, recessos e início das aulas."""
    try:
        conn = _get_conn()
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
            return {"status": "not_found", "message": f"Nenhum evento encontrado no calendário para '{termo_busca}'."}
        return {
            "status": "ok",
            "eventos": [
                {"data_inicio": r[0], "data_fim": r[1], "evento": r[2], "categoria": r[3], "detalhe": r[4]}
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("Erro ao consultar calendário: %s", e)
        return {"status": "error", "message": str(e)}

def buscar_documentos_academicos(termo: str) -> Dict[str, Any]:
    """Pesquisa em regulamentos, manuais do aluno e resoluções do campus."""
    try:
        conn = _get_conn()
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
            return {"status": "not_found", "message": f"Nenhum regulamento encontrado com '{termo}'."}
        return {
            "status": "ok",
            "trechos": [
                {"documento": r[0], "secao": r[1], "resumo": r[2][:200]}
                for r in rows
            ]
        }
    except Exception as e:
        logger.error("Erro ao buscar documentos: %s", e)
        return {"status": "error", "message": str(e)}

AVAILABLE_TOOLS = {
    "consultar_professor": consultar_professor,
    "consultar_aulas": consultar_aulas,
    "consultar_calendario_academico": consultar_calendario_academico,
    "buscar_documentos_academicos": buscar_documentos_academicos,
}

TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "consultar_professor",
            "description": "Consulta a localização da sala, gabinete, e-mail e departamento de um docente da UNESP Sorocaba.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_professor": {
                        "type": "string",
                        "description": "Nome ou sobrenome do professor a pesquisar (ex: Eduardo, Liberado, Maria)"
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
            "description": "Consulta a grade horária oficial de aulas, turmas e salas por dia da semana da UNESP Sorocaba.",
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
            "description": "Consulta datas oficiais do calendário letivo: início de aulas, término, feriados, exames e prazos de matrícula.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_busca": {
                        "type": "string",
                        "description": "Termo a pesquisar no calendário (ex: inicio, matricula, feriado, recesso, exame)"
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
            "description": "Pesquisa em normas oficiais, manuais de graduação e resoluções acadêmicas do campus Sorocaba.",
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

def execute_academic_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Executa a ferramenta correspondente de forma segura."""
    fn = AVAILABLE_TOOLS.get(tool_name)
    if not fn:
        return {"status": "error", "message": f"Ferramenta desconhecida: {tool_name}"}
    try:
        return fn(**arguments)
    except Exception as e:
        logger.error("Falha ao executar tool %s com args %s: %s", tool_name, arguments, e)
        return {"status": "error", "message": str(e)}
