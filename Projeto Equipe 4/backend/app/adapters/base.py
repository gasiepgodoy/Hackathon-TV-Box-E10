"""
Todo adapter de protocolo (MQTT, OPC UA, simulado, ou um novo que você
for adicionar) implementa essa interface. Isso é o que torna o gateway
"universal": o resto do sistema (InfluxDB, WebSocket, dashboard) não
sabe nem se importa de qual protocolo o dado veio — só recebe uma
`Leitura` já normalizada.
"""
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from ..models import Leitura, Sensor

# Callback chamado pelo adapter toda vez que uma nova leitura chega
CallbackLeitura = Callable[[Leitura], Awaitable[None]]


class AdapterBase(ABC):
    def __init__(self, sensor: Sensor, on_leitura: CallbackLeitura):
        self.sensor = sensor
        self.on_leitura = on_leitura
        self._rodando = False

    @abstractmethod
    async def iniciar(self) -> None:
        """Conecta ao broker/servidor e começa a escutar/coletar dados.
        Deve retornar rápido — a coleta roda em background (task/thread)."""
        raise NotImplementedError

    @abstractmethod
    async def parar(self) -> None:
        """Encerra a conexão e libera recursos."""
        raise NotImplementedError

    async def _emitir(self, valor: float) -> None:
        """Helper: monta a Leitura normalizada e dispara o callback."""
        import time
        leitura = Leitura(
            sensor_id=self.sensor.id,
            nome=self.sensor.nome,
            tipo=self.sensor.tipo,
            protocolo=self.sensor.protocolo,
            local=self.sensor.local,
            unidade=self.sensor.unidade,
            valor=valor,
            timestamp=time.time(),
        )
        await self.on_leitura(leitura)
