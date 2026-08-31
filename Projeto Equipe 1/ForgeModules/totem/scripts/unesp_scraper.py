#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNESP Background Scraper & Seeder for Mina SQLite DB.
Collects Jornal da Unesp news/events, and registers Sorocaba (ECA/EA) courses and rooms.
Can be executed daily via cron.
"""

import sys
import os
import urllib.request
import xml.etree.ElementTree as ET
import json
from datetime import datetime

# Adjust Python path to allow importing from src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.academic_db import init_db, save_professor, save_schedule, save_news_event, clear_schedules

# Predefined list of UNESP Sorocaba Faculty & Rooms (ECA / Ambiental)
PROFESSORS_DATA = [
    {"name": "Prof. Eduardo", "room": "Sala 01 - Depto. ECA", "email": "eduardo@unesp.br", "dept": "Controle e Automação"},
    {"name": "Profa. Maria", "room": "Sala 02 - Depto. Matemática", "email": "maria@unesp.br", "dept": "Matemática"},
    {"name": "Prof. José Silva", "room": "Sala 03 - Depto. ECA", "email": "jose.silva@unesp.br", "dept": "Controle e Automação"},
    {"name": "Profa. Ana Costa", "room": "Sala 04 - Depto. Ambiental", "email": "ana.costa@unesp.br", "dept": "Ambiental"},
    {"name": "Prof. Marcos Paulo", "room": "Sala 05 - Depto. ECA", "email": "marcos.paulo@unesp.br", "dept": "Controle e Automação"},
    {"name": "Profa. Juliana", "room": "Sala 06 - Depto. Ambiental", "email": "juliana@unesp.br", "dept": "Ambiental"},
    {"name": "Prof. Roberto", "room": "Sala 07 - Depto. Física", "email": "roberto@unesp.br", "dept": "Física"},
]

# Semester class schedule for UNESP Sorocaba
SCHEDULES_DATA = [
    # Segunda-feira (0)
    {"subject": "Cálculo Diferencial e Integral I", "weekday": 0, "start": "08:00", "end": "11:40", "room": "Sala 1 (ECA 1º Termo)", "teacher": "Profa. Maria"},
    {"subject": "Química Geral", "weekday": 0, "start": "14:00", "end": "17:40", "room": "Lab 1 (Amb 1º Termo)", "teacher": "Profa. Ana Costa"},
    
    # Terça-feira (1)
    {"subject": "Física I", "weekday": 1, "start": "08:00", "end": "11:40", "room": "Sala 2 (ECA 1º Termo)", "teacher": "Prof. Roberto"},
    {"subject": "Introdução à Engenharia de Controle e Automação", "weekday": 1, "start": "14:00", "end": "16:00", "room": "Sala 1 (ECA 1º Termo)", "teacher": "Prof. Eduardo"},
    
    # Quarta-feira (2)
    {"subject": "Circuitos Elétricos I", "weekday": 2, "start": "08:00", "end": "11:40", "room": "Lab 2 (ECA 3º Termo)", "teacher": "Prof. José Silva"},
    {"subject": "Ecologia Básica", "weekday": 2, "start": "14:00", "end": "17:40", "room": "Sala 3 (Amb 3º Termo)", "teacher": "Profa. Juliana"},
    
    # Quinta-feira (3)
    {"subject": "Sistemas de Controle I", "weekday": 3, "start": "08:00", "end": "11:40", "room": "Lab 3 (ECA 5º Termo)", "teacher": "Prof. Marcos Paulo"},
    {"subject": "Tratamento de Água", "weekday": 3, "start": "14:00", "end": "17:40", "room": "Lab 1 (Amb 5º Termo)", "teacher": "Profa. Ana Costa"},
    
    # Sexta-feira (4)
    {"subject": "Instrumentação Industrial", "weekday": 4, "start": "08:00", "end": "11:40", "room": "Lab 2 (ECA 5º Termo)", "teacher": "Prof. Eduardo"},
    {"subject": "Gestão Ambiental", "weekday": 4, "start": "14:00", "end": "17:40", "room": "Sala 4 (Amb 7º Termo)", "teacher": "Profa. Juliana"},
]

# Try loading custom academic data from config/academic_data.json to avoid hardcoded fallbacks
_script_dir = os.path.dirname(os.path.abspath(__file__))
_json_path = os.path.join(os.path.dirname(_script_dir), "config", "academic_data.json")
if os.path.exists(_json_path):
    try:
        with open(_json_path, "r", encoding="utf-8") as f:
            _custom_data = json.load(f)
            if "professors" in _custom_data:
                PROFESSORS_DATA = _custom_data["professors"]
            if "schedules" in _custom_data:
                SCHEDULES_DATA = _custom_data["schedules"]
            print(f"Loaded custom academic data from {_json_path}")
    except Exception as _e:
        print(f"Failed to load custom academic data: {_e}", file=sys.stderr)

def scrape_unesp_rss():
    """Scrape Jornal da Unesp RSS and populate the SQLite database."""
    feed_url = "https://jornal.unesp.br/feed/"
    print(f"Fetching RSS feed from: {feed_url}")
    try:
        req = urllib.request.Request(
            feed_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        count = 0
        for item in root.findall(".//item"):
            title = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
            categories = [cat.text for cat in item.findall("category") if cat.text]
            desc_elem = item.find("description")
            description = desc_elem.text if desc_elem is not None else ""
            
            # Identify if it is an academic event/agenda item
            is_event = False
            cats_lower = [c.lower() for c in categories]
            if any(term in cats_lower for term in ["acontece", "eventos", "oportunidades", "agenda"]):
                is_event = True
                
            category_str = ", ".join(categories) if categories else "Notícias"
            
            save_news_event(
                title=title,
                link=link,
                pub_date=pub_date,
                category=category_str,
                is_event=is_event
            )
            count += 1
        print(f"Successfully processed {count} feed items.")
    except Exception as e:
        print(f"Failed to scrape RSS feed: {e}", file=sys.stderr)

def main():
    print("=== Running UNESP Sorocaba SQLite Scraper/Seeder ===")
    
    # 1. Initialize tables
    init_db()
    
    # 2. Seed/Scrape Professors list
    print("Updating professors database...")
    # Clear existing professors for clean slate
    conn = __import__('sqlite3').connect(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "academic.db"))
    conn.execute("DELETE FROM professors")
    conn.commit()
    conn.close()

    for p in PROFESSORS_DATA:
        save_professor(
            name=p["name"],
            room=p["room"],
            email=p["email"],
            department=p["dept"]
        )
    print(f"Registered {len(PROFESSORS_DATA)} professors.")

    # 3. Seed Class Schedules
    print("Updating weekly class schedules...")
    clear_schedules()
    for s in SCHEDULES_DATA:
        save_schedule(
            subject=s["subject"],
            weekday=s["weekday"],
            start_time=s["start"],
            end_time=s["end"],
            room=s["room"],
            teacher_name=s["teacher"]
        )
    print(f"Registered {len(SCHEDULES_DATA)} weekly class schedule slots.")

    # 4. Scrape real-time news/events from RSS
    scrape_unesp_rss()
    
    print("=== Scraping and seeding complete! ===")

if __name__ == "__main__":
    main()
