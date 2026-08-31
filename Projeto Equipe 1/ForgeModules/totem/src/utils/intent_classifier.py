# -*- coding: utf-8 -*-
"""
Intent Classifier Utility for Mina Assistant
-------------------------------------------
Intercepa as consultas do usuário (texto) antes de enviá-las ao LLM.
Se a intenção for mapeada para uma query local no banco acadêmico,
executa a query e responde instantaneamente de forma offline.
"""

import re
from typing import Tuple, Optional
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# Importa as funções do banco acadêmico
from src.utils.academic_db import (
    get_professors,
    get_recent_news_events,
    get_active_classes,
    get_upcoming_classes_today
)

class IntentClassifier:
    def __init__(self):
        # Mapeamento de regras de intenção baseado em Expressões Regulares / Palavras-chave
        self.rules = {
            "sala_professor": re.compile(
                r"\b(sala|gabinete|onde fica|onde atende|onde encontrar)\b.*\b(professor|professora|prof|profa)\b",
                re.IGNORECASE
            ),
            "horario_aulas": re.compile(
                r"\b(aula|horario|horário|cronograma|agenda|matéria|materia|grade)\b",
                re.IGNORECASE
            ),
            "noticias": re.compile(
                r"\b(notícia|noticia|notícias|noticias|evento|eventos|mural|novidade|novidades|jornal)\b",
                re.IGNORECASE
            ),
            "cantina": re.compile(
                r"\b(cantina|salgado|chipa|intervalo|comer|alimentação|refeição|fome)\b",
                re.IGNORECASE
            )
        }

    def classify_and_execute(self, user_query: str) -> Tuple[bool, Optional[str]]:
        """
        Classifica o texto do usuário e executa a resposta local correspondente.
        Retorna: (intent_detected, response_text)
        """
        query_clean = user_query.strip().lower()
        if not query_clean:
            return False, None

        # 1. Verificar Intenção: Sala de Professor
        if self.rules["sala_professor"].search(query_clean):
            return True, self._handle_sala_professor(query_clean)

        # 2. Verificar Intenção: Horários de Aula
        if self.rules["horario_aulas"].search(query_clean):
            return True, self._handle_horario_aulas(query_clean)

        # 3. Verificar Intenção: Mural de Notícias
        if self.rules["noticias"].search(query_clean):
            return True, self._handle_noticias(query_clean)

        # 4. Verificar Intenção: Cantina
        if self.rules["cantina"].search(query_clean):
            return True, self._handle_cantina()

        # Nenhuma intenção local detectada -> Fallback para o LLM
        return False, None

    def _handle_sala_professor(self, query: str) -> str:
        professores = get_professors()
        if not professores:
            return "Não encontrei nenhum professor cadastrado no banco de dados acadêmico."

        query_lower = query.lower()

        # 1. Match full clean names (without title prefixes) in the query
        for p in professores:
            clean_name = p["name"].replace("Prof. ", "").replace("Profa. ", "").strip().lower()
            if clean_name in query_lower:
                return f"O {p['name']} atende na {p['room']} do departamento de {p['department'] or 'Geral'}."

        # 2. Match individual unique components of names (longer than 2 chars)
        for p in professores:
            clean_name = p["name"].replace("Prof. ", "").replace("Profa. ", "").strip().lower()
            for word in clean_name.split():
                if len(word) > 2 and word in query_lower:
                    # Verify if this word is unique among all professors
                    matches = [prof for prof in professores if word in prof["name"].lower()]
                    if len(matches) == 1:
                        return f"O {p['name']} atende na {p['room']} do departamento de {p['department'] or 'Geral'}."

        # 3. Fallback to sequential word matching
        nome_procurado = ""
        query_limpa = re.sub(r"[^\w\s]", "", query)
        palavras = query_limpa.split()
        for i, pal in enumerate(palavras):
            if pal in ["prof", "professor", "professora", "profa"] and i + 1 < len(palavras):
                nome_procurado = palavras[i + 1]
                if nome_procurado in ["do", "da"] and i + 2 < len(palavras):
                    nome_procurado = palavras[i + 2]
                break

        if nome_procurado:
            for p in professores:
                if nome_procurado in p["name"].lower():
                    return f"O {p['name']} atende na {p['room']} do departamento de {p['department'] or 'Geral'}."

        # If not identified, list the first ones
        lista_profs = ", ".join([f"{p['name']} ({p['room']})" for p in professores[:3]])
        return f"Não identifiquei o nome do professor com clareza. Mas aqui estão alguns docentes que localizei: {lista_profs}."

    def _handle_horario_aulas(self, query: str) -> str:
        aulas_agora = get_active_classes()
        aulas_proximas = get_upcoming_classes_today()

        resposta_parts = []
        if aulas_agora:
            a = aulas_agora[0]
            resposta_parts.append(
                f"Neste momento, está ocorrendo a aula de {a['subject']} na {a['room']} com o professor {a['teacher_name']}."
            )
        
        if aulas_proximas:
            proximas_str = ", ".join([f"{a['subject']} na {a['room']} às {a['start_time']}" for a in aulas_proximas[:2]])
            resposta_parts.append(f"As próximas aulas de hoje são: {proximas_str}.")

        if not resposta_parts:
            return "Não encontrei aulas em andamento ou futuras registradas para o dia de hoje no cronograma acadêmico."

        return " ".join(resposta_parts)

    def _handle_noticias(self, query: str) -> str:
        noticias = get_recent_news_events(limit=3)
        if not noticias:
            return "O mural de notícias da UNESP Sorocaba está vazio no momento."

        lista_noticias = []
        for i, n in enumerate(noticias):
            tipo = "evento" if n["is_event"] else "notícia"
            lista_noticias.append(f"{i + 1} ({tipo}): {n['title']}")

        resumo = " | ".join(lista_noticias)
        return f"Encontrei as seguintes novidades no mural da UNESP: {resumo}."

    def _handle_cantina(self) -> str:
        return "A chipa quentinha e os salgados saem na cantina principal da UNESP Sorocaba nos intervalos das 9 horas da manhã e das 20h30 da noite."
