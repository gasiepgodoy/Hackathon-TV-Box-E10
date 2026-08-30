"""
Adapter HTTP/polling — o mais simples de todos: faz uma requisição
periódica numa URL e extrai o valor da resposta JSON.

Config esperada no sensor (campo `config`):
  {
    "url": "http://192.168.1.50/api/status",
    "metodo": "GET",                 # GET ou POST
    "intervalo_segundos": 10,
    "campo_valor": "leitura.valor",  # caminho pontilhado dentro do JSON
    "cabecalhos": {"Authorization": "Bearer ..."}   # opcional
  }

Cobre qualquer sensor/dispositivo barato que já exponha um endpoint REST
próprio em vez de falar um protocolo dedicado (muito comum em módulos
Wi-Fi genéricos, Tasmota, Shelly, ESPHome, etc).
"""
import asyncio
import logging
import time

import httpx

from .base import AdapterBase

logger = logging.getLogger("http_adapter")


class HttpAdapter(AdapterBase):
    def __init__(self, sensor, on_leitura):
        super().__init__(sensor, on_leitura)
        self._task: asyncio.Task | None = None

    async def iniciar(self) -> None:
        self._rodando = True
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        cfg = self.sensor.config
        url = cfg["url"]
        metodo = cfg.get("metodo", "GET").upper()
        intervalo = float(cfg.get("intervalo_segundos", 10))
        campo_valor = cfg.get("campo_valor", "valor")
        cabecalhos = cfg.get("cabecalhos") or {}

        async with httpx.AsyncClient(timeout=8) as cliente:
            while self._rodando:
                inicio = time.monotonic()
                try:
                    resposta = await cliente.request(metodo, url, headers=cabecalhos)
                    resposta.raise_for_status()
                    dado = resposta.json()
                    valor = self._extrair(dado, campo_valor)
                    if valor is not None:
                        await self._emitir(float(valor))
                    else:
                        logger.warning(
                            "Campo '%s' não encontrado na resposta do sensor=%s: %r",
                            campo_valor, self.sensor.nome, dado,
                        )
                except Exception as exc:
                    logger.error("Erro no polling HTTP (sensor=%s): %s", self.sensor.nome, exc)
                # Desconta o tempo da requisição para manter a cadência real
                resto = intervalo - (time.monotonic() - inicio)
                await asyncio.sleep(max(0.0, resto))

    @staticmethod
    def _extrair(dado, caminho: str):
        """Percorre um caminho tipo 'leitura.valor' dentro de um dict/JSON aninhado."""
        atual = dado
        for parte in caminho.split("."):
            if isinstance(atual, dict) and parte in atual:
                atual = atual[parte]
            else:
                return None
        return atual

    async def parar(self) -> None:
        self._rodando = False
        if self._task:
            self._task.cancel()
