"""
Adapter simulado — gera leituras aleatórias periodicamente.

Não fala com nenhum protocolo real: serve para testar o dashboard, o
InfluxDB e o WebSocket de ponta a ponta antes de conectar sensores
físicos. Config esperada:
  {"valor_min": 18, "valor_max": 28, "intervalo_segundos": 5}
"""
import asyncio
import logging
import random
import time

from .base import AdapterBase

logger = logging.getLogger("simulator_adapter")


class SimulatorAdapter(AdapterBase):
    def __init__(self, sensor, on_leitura):
        super().__init__(sensor, on_leitura)
        self._task: asyncio.Task | None = None

    async def iniciar(self) -> None:
        self._rodando = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Simulador iniciado para sensor=%s", self.sensor.nome)

    async def _loop(self) -> None:
        cfg = self.sensor.config
        minimo = float(cfg.get("valor_min", 0))
        maximo = float(cfg.get("valor_max", 100))
        intervalo = float(cfg.get("intervalo_segundos", 5))

        # começa de um valor no meio da faixa e passeia com pequenos passos,
        # pra parecer uma leitura real em vez de ruído puro
        atual = (minimo + maximo) / 2
        while self._rodando:
            inicio = time.monotonic()
            passo = (maximo - minimo) * 0.05
            atual = max(minimo, min(maximo, atual + random.uniform(-passo, passo)))
            await self._emitir(round(atual, 2))
            # Desconta o tempo gasto emitindo (gravação + broadcast) do
            # intervalo. Sem isso a cadência real vira `intervalo + tempo de
            # escrita`, e o sensor entrega menos leituras do que foi
            # configurado — o que a análise de saúde reportaria, com razão,
            # como perda de leituras.
            resto = intervalo - (time.monotonic() - inicio)
            await asyncio.sleep(max(0.0, resto))

    async def parar(self) -> None:
        self._rodando = False
        if self._task:
            self._task.cancel()
