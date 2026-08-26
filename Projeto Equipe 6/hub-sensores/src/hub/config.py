"""Configuracao do hub, lida de um .ini com valores padrao sensatos."""
from __future__ import annotations

import configparser
import logging
import os
from pathlib import Path

PADROES = {
    "banco": {
        "caminho": "/var/lib/hub/dados.db",
    },
    "mqtt": {
        "host": "localhost",
        "port": "1883",
        "topico": "zigbee2mqtt/+",
        "topico_saida": "hub/lora/saida",
    },
    "coletor": {
        # Gravar em lote poupa o cartao SD: em vez de milhares de escritas
        # diarias, poucas centenas.
        "lote_max": "20",
        "intervalo_flush_s": "300",
    },
    "agregador": {
        "janela_s": "3600",
    },
    "eventos": {
        "temp_min": "3.0",       # abaixo disso: risco de geada
        "temp_max": "40.0",      # acima disso: calor extremo
        "umid_min": "20.0",
        "umid_max": "95.0",
        "bateria_min": "20",     # %
        "silencio_s": "3600",    # sensor sem reportar por mais que isso: mudo
        "repetir_apos_s": "3600",  # nao repetir o mesmo evento antes disso
    },
    "retencao": {
        "dias_leituras": "90",   # agregados sao mantidos para sempre
    },
}


class Config:
    def __init__(self, caminho: str | os.PathLike | None = None):
        self._cp = configparser.ConfigParser()
        self._cp.read_dict(PADROES)
        caminho = caminho or os.environ.get("HUB_CONFIG")
        if caminho:
            if Path(caminho).is_file():
                self._cp.read(caminho)
            else:
                # Sem o aviso, um caminho errado faria o hub usar os padroes em
                # silencio — e o banco apareceria num lugar inesperado.
                logging.getLogger("hub.config").warning(
                    "config '%s' nao encontrada; usando valores padrao", caminho
                )
        # Variavel de ambiente sobrepoe o arquivo (util em testes e containers).
        if env_db := os.environ.get("HUB_DB"):
            self._cp["banco"]["caminho"] = env_db

    def txt(self, secao: str, chave: str) -> str:
        return self._cp[secao][chave]

    def num(self, secao: str, chave: str) -> int:
        return int(float(self._cp[secao][chave]))

    def dec(self, secao: str, chave: str) -> float:
        return float(self._cp[secao][chave])
