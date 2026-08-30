"""
Adapter OPC UA (usando a lib assíncrona `asyncua`).

Config esperada no sensor (campo `config`):
  {
    "endpoint_url": "opc.tcp://192.168.1.20:4840/freeopcua/server/",
    "node_id": "ns=2;i=2",
    "intervalo_ms": 1000   # intervalo de amostragem da subscription
  }

Usa uma subscription nativa do OPC UA (data change notification), então
o servidor só nos avisa quando o valor realmente muda — mais eficiente
que ficar fazendo polling.
"""
import asyncio
import logging

from asyncua import Client

from .base import AdapterBase

logger = logging.getLogger("opcua_adapter")


class _Handler:
    """Recebe as notificações de mudança de valor da lib asyncua e repassa
    para a coroutine de emissão do adapter. A asyncua não exige herdar de
    uma classe base — basta ter um método `datachange_notification`
    (pode ser síncrono ou, como aqui, assíncrono)."""

    def __init__(self, adapter: "OpcuaAdapter"):
        self._adapter = adapter

    async def datachange_notification(self, node, val, data):
        try:
            valor = float(val)
        except (TypeError, ValueError):
            logger.warning("Valor OPC UA não numérico ignorado: %r (sensor=%s)", val, self._adapter.sensor.nome)
            return
        await self._adapter._emitir(valor)


class OpcuaAdapter(AdapterBase):
    def __init__(self, sensor, on_leitura):
        super().__init__(sensor, on_leitura)
        self._client: Client | None = None
        self._task: asyncio.Task | None = None

    async def iniciar(self) -> None:
        self._task = asyncio.create_task(self._loop_conexao())
        self._rodando = True

    async def _loop_conexao(self) -> None:
        cfg = self.sensor.config
        endpoint = cfg["endpoint_url"]
        node_id = cfg["node_id"]
        intervalo_ms = int(cfg.get("intervalo_ms", 1000))

        while self._rodando:
            try:
                async with Client(url=endpoint) as client:
                    self._client = client
                    node = client.get_node(node_id)
                    handler = _Handler(self)
                    sub = await client.create_subscription(intervalo_ms, handler)
                    await sub.subscribe_data_change(node)
                    logger.info("OPC UA conectado a %s, node=%s (sensor=%s)", endpoint, node_id, self.sensor.nome)

                    # mantém a conexão viva até pararem o adapter
                    while self._rodando:
                        await asyncio.sleep(1)
            except Exception as exc:
                logger.error("Erro na conexão OPC UA (sensor=%s): %s — tentando de novo em 5s", self.sensor.nome, exc)
                await asyncio.sleep(5)

    async def parar(self) -> None:
        self._rodando = False
        if self._task:
            self._task.cancel()
