"""Gera historico sintetico de sensores — para testes e demonstracao.

Sem isso seria preciso esperar horas de dados reais para ver os agregados,
os eventos e a fila do LoRa funcionando.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import time

from .config import Config
from .db import conectar, gravar_leituras, inicializar

SENSORES = ("estufa_norte", "estufa_sul", "pomar")


def gerar(con, horas: int, intervalo_s: int = 300, geada: bool = True) -> int:
    """Cria `horas` de leituras com ciclo dia/noite e, opcionalmente, uma geada."""
    agora = int(time.time())
    inicio = agora - horas * 3600
    linhas = []
    for sensor_i, nome in enumerate(SENSORES):
        ts = inicio
        while ts < agora:
            hora_do_dia = (ts % 86400) / 3600.0
            # Ciclo senoidal: minimo de madrugada, maximo a tarde.
            base = 18 + 7 * math.sin((hora_do_dia - 9) / 24 * 2 * math.pi)
            temp = round(base + sensor_i * 1.5 + random.uniform(-0.6, 0.6), 1)
            umid = round(max(15, min(99, 95 - (temp - 12) * 2.5 + random.uniform(-4, 4))), 1)
            # Geada curta no sensor exposto, nas leituras mais recentes: cai
            # dentro da ultima janela agregada E e vista pelo detector, que
            # avalia a leitura mais nova de cada sensor.
            if geada and nome == "estufa_sul" and (agora - ts) < 40 * 60:
                temp = round(random.uniform(0.5, 2.5), 1)
            bateria = 95 - sensor_i * 40           # o terceiro sensor fica critico
            linhas.append((nome, ts, temp, umid, bateria, random.randint(60, 220)))
            ts += intervalo_s
    return gravar_leituras(con, linhas)


def main() -> int:
    ap = argparse.ArgumentParser(description="Popula o banco com dados sinteticos")
    ap.add_argument("--horas", type=int, default=12)
    ap.add_argument("--intervalo", type=int, default=300, help="segundos entre leituras")
    ap.add_argument("--sem-geada", action="store_true")
    args = ap.parse_args()

    cfg = Config()
    con = conectar(cfg.txt("banco", "caminho"))
    inicializar(con)
    n = gerar(con, args.horas, args.intervalo, geada=not args.sem_geada)
    print(f"{n} leituras sinteticas geradas ({args.horas}h, {len(SENSORES)} sensores)")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
