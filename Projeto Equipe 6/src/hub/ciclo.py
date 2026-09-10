"""Ciclo periodico: agrega, detecta eventos e tenta enviar.

Executado por um timer do systemd. Separado do coletor de proposito: o coletor
so precisa gravar rapido e nunca perder mensagem; o resto pode falhar e ser
repetido no ciclo seguinte sem consequencia.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .agregador import agregar
from .config import Config
from .db import conectar, inicializar
from .enviador import (Transporte, TransporteIndisponivel, TransporteLog,
                       TransporteMQTT, enviar_pendentes)
from .eventos import detectar

log = logging.getLogger("hub.ciclo")


def transporte_de(nome: str, cfg: Config) -> Transporte:
    if nome == "mqtt":
        return TransporteMQTT(cfg.txt("mqtt", "host"), cfg.txt("mqtt", "port"),
                              cfg.txt("mqtt", "topico_saida"))
    if nome == "offline":
        return TransporteIndisponivel()
    return TransporteLog()


def main() -> int:
    ap = argparse.ArgumentParser(description="Ciclo de agregacao, eventos e envio")
    ap.add_argument("--transporte", choices=("log", "mqtt", "offline"), default="log")
    ap.add_argument("--max", type=int, default=10)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    cfg = Config()
    con = conectar(cfg.txt("banco", "caminho"))
    inicializar(con)
    try:
        janelas = agregar(con, cfg.num("agregador", "janela_s"))
        novos = detectar(con, cfg)
        res = enviar_pendentes(con, transporte_de(args.transporte, cfg), args.max)
        log.info("janelas=%d eventos_novos=%d enviados=%s", janelas, novos, res)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
