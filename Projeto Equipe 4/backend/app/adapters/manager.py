"""
Sobe/derruba os adapters de cada sensor ativo e liga o fio entre eles:

  adapter -> Leitura -> grava no InfluxDB + manda pro WebSocket

É aqui que a lógica "independente de protocolo" ganha vida: pra adicionar
um protocolo novo, basta criar um adapter (ver base.py) e registrar a
classe no dicionário ADAPTERS abaixo.
"""
import logging

from .. import database, influx_writer
from ..models import Leitura, Sensor
from ..ws_manager import gerenciador_ws
from .base import AdapterBase
from .http_adapter import HttpAdapter
from .mqtt_adapter import MqttAdapter
from .opcua_adapter import OpcuaAdapter
from .simulator_adapter import SimulatorAdapter

logger = logging.getLogger("adapter_manager")

ADAPTERS: dict[str, type[AdapterBase]] = {
    "mqtt": MqttAdapter,
    "opcua": OpcuaAdapter,
    "http": HttpAdapter,
    "simulado": SimulatorAdapter,
}


class AdapterManager:
    def __init__(self) -> None:
        self._ativos: dict[str, AdapterBase] = {}

    async def _on_leitura(self, leitura: Leitura) -> None:
        try:
            await influx_writer.escrever_leitura_async(leitura)
        except Exception:
            logger.exception("Falha ao gravar leitura no InfluxDB (sensor=%s)", leitura.sensor_id)

        await gerenciador_ws.broadcast({
            "tipo_evento": "leitura",
            "sensor_id": leitura.sensor_id,
            "nome": leitura.nome,
            "tipo": leitura.tipo,
            "local": leitura.local,
            "unidade": leitura.unidade,
            "valor": leitura.valor,
            "timestamp": leitura.timestamp,
        })

    async def iniciar_sensor(self, sensor: Sensor) -> None:
        if sensor.id in self._ativos:
            await self.parar_sensor(sensor.id)

        classe_adapter = ADAPTERS.get(sensor.protocolo)
        if not classe_adapter:
            database.atualizar_status(sensor.id, "erro", f"protocolo desconhecido: {sensor.protocolo}")
            return

        adapter = classe_adapter(sensor, self._on_leitura)
        try:
            database.atualizar_status(sensor.id, "conectando")
            await adapter.iniciar()
            self._ativos[sensor.id] = adapter
            database.atualizar_status(sensor.id, "ativo")
        except Exception as exc:
            logger.exception("Falha ao iniciar adapter (sensor=%s)", sensor.nome)
            database.atualizar_status(sensor.id, "erro", str(exc))

    async def parar_sensor(self, sensor_id: str) -> None:
        adapter = self._ativos.pop(sensor_id, None)
        if adapter:
            await adapter.parar()
        database.atualizar_status(sensor_id, "parado")

    async def iniciar_todos_ativos(self) -> None:
        for sensor in database.listar_sensores():
            if sensor.ativo:
                await self.iniciar_sensor(sensor)

    async def parar_todos(self) -> None:
        for sensor_id in list(self._ativos.keys()):
            await self.parar_sensor(sensor_id)


gerenciador_adapters = AdapterManager()
