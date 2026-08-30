"""
Adapter Modbus TCP.

Modbus é o protocolo mais comum em equipamento industrial: CLPs,
medidores de energia, inversores de frequência, transmissores de pressão
e temperatura. Diferente de MQTT e OPC UA, ele não tem notificação por
evento — o mestre (aqui, o gateway) pergunta e o escravo responde. Por
isso este adapter faz polling num intervalo configurável.

Config esperada no sensor (campo `config`):
  {
    "host": "192.168.1.30",
    "porta": 502,
    "device_id": 1,             # endereço do escravo (unit ID / slave ID)
    "registrador": 0,           # endereço do registrador a ler
    "tipo_registrador": "holding",   # holding | input
    "tipo_dado": "uint16",      # uint16 | int16 | uint32 | int32 | float32
    "ordem_palavras": "big",    # big | little (para valores de 32 bits)
    "escala": 0.1,              # multiplicador aplicado ao valor bruto
    "offset": 0.0,              # somado depois da escala
    "intervalo_segundos": 5
  }

Sobre `escala` e `offset`: equipamentos Modbus quase sempre transmitem
inteiros, não decimais. Um transmissor que lê 23,5 °C normalmente envia
235 e o manual informa "escala 0,1". Sem esses dois campos, o gateway
gravaria 235 °C no histórico e toda a análise estatística ficaria sobre
uma grandeza errada.
"""
import asyncio
import logging
import struct
import time
from typing import Optional

from .base import AdapterBase

logger = logging.getLogger("modbus_adapter")

# Quantos registradores (16 bits cada) cada tipo de dado ocupa
PALAVRAS_POR_TIPO = {
    "uint16": 1,
    "int16": 1,
    "uint32": 2,
    "int32": 2,
    "float32": 2,
}


class ModbusAdapter(AdapterBase):
    def __init__(self, sensor, on_leitura):
        super().__init__(sensor, on_leitura)
        self._task: asyncio.Task | None = None
        self._cliente = None

    async def iniciar(self) -> None:
        self._rodando = True
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        try:
            from pymodbus.client import AsyncModbusTcpClient
        except ImportError:
            logger.error(
                "pymodbus não instalado — o sensor '%s' não será lido. "
                "Instale com: pip install pymodbus", self.sensor.nome,
            )
            return

        cfg = self.sensor.config
        host = cfg["host"]
        porta = int(cfg.get("porta", 502))
        device_id = int(cfg.get("device_id", 1))
        registrador = int(cfg.get("registrador", 0))
        tipo_registrador = str(cfg.get("tipo_registrador", "holding")).lower()
        tipo_dado = str(cfg.get("tipo_dado", "uint16")).lower()
        ordem_palavras = str(cfg.get("ordem_palavras", "big")).lower()
        escala = float(cfg.get("escala", 1.0))
        offset = float(cfg.get("offset", 0.0))
        intervalo = float(cfg.get("intervalo_segundos", 5))

        n_palavras = PALAVRAS_POR_TIPO.get(tipo_dado, 1)

        while self._rodando:
            inicio = time.monotonic()
            try:
                if self._cliente is None or not self._cliente.connected:
                    self._cliente = AsyncModbusTcpClient(host, port=porta, timeout=5)
                    await self._cliente.connect()
                    if not self._cliente.connected:
                        raise ConnectionError(f"não foi possível conectar em {host}:{porta}")
                    logger.info("Modbus conectado a %s:%d (sensor=%s)", host, porta, self.sensor.nome)

                if tipo_registrador == "input":
                    resposta = await self._cliente.read_input_registers(
                        registrador, count=n_palavras, device_id=device_id)
                else:
                    resposta = await self._cliente.read_holding_registers(
                        registrador, count=n_palavras, device_id=device_id)

                if resposta.isError():
                    raise IOError(f"o escravo respondeu com erro: {resposta}")

                bruto = self._decodificar(resposta.registers, tipo_dado, ordem_palavras)
                if bruto is not None:
                    await self._emitir(bruto * escala + offset)

            except Exception as exc:
                logger.error("Erro na leitura Modbus (sensor=%s): %s", self.sensor.nome, exc)
                # Força reconexão na próxima volta: manter um socket meio
                # aberto depois de um erro costuma resultar em leituras
                # travadas em vez de um erro claro.
                if self._cliente is not None:
                    try:
                        self._cliente.close()
                    except Exception:
                        pass
                    self._cliente = None

            # Desconta o tempo da leitura para manter a cadência configurada
            resto = intervalo - (time.monotonic() - inicio)
            await asyncio.sleep(max(0.0, resto))

    @staticmethod
    def _decodificar(registradores: list[int], tipo_dado: str, ordem_palavras: str) -> Optional[float]:
        """Converte os registradores de 16 bits no tipo de dado configurado.

        Valores de 32 bits ocupam dois registradores, e não há consenso
        entre fabricantes sobre qual vem primeiro — daí `ordem_palavras`.
        Se o valor lido vier absurdo (tipo 1e9 numa temperatura), inverter
        essa opção costuma ser a correção.
        """
        if not registradores:
            return None

        if tipo_dado == "uint16":
            return float(registradores[0])

        if tipo_dado == "int16":
            valor = registradores[0]
            return float(valor - 0x10000 if valor >= 0x8000 else valor)

        if len(registradores) < 2:
            return None

        alto, baixo = registradores[0], registradores[1]
        if ordem_palavras == "little":
            alto, baixo = baixo, alto
        bruto = struct.pack(">HH", alto & 0xFFFF, baixo & 0xFFFF)

        if tipo_dado == "uint32":
            return float(struct.unpack(">I", bruto)[0])
        if tipo_dado == "int32":
            return float(struct.unpack(">i", bruto)[0])
        if tipo_dado == "float32":
            return float(struct.unpack(">f", bruto)[0])

        return float(registradores[0])

    async def parar(self) -> None:
        self._rodando = False
        if self._task:
            self._task.cancel()
        if self._cliente is not None:
            try:
                self._cliente.close()
            except Exception:
                pass
            self._cliente = None
