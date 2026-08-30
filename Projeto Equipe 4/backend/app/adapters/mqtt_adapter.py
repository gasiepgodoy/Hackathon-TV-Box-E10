"""
Adapter MQTT.

Config esperada no sensor (campo `config`):
  {
    "broker_host": "192.168.1.10",
    "broker_port": 1883,
    "topico": "casa/sala/temperatura",
    "qos": 0,
    "campo_valor": "valor"   # opcional: se o payload for JSON, qual chave ler
  }

Aceita tanto payload numérico puro (ex: b"23.5") quanto JSON
(ex: {"valor": 23.5, "unidade": "C"}), usando `campo_valor` para
saber qual chave extrair no segundo caso.
"""
import asyncio
import json
import logging

import paho.mqtt.client as mqtt

from .base import AdapterBase

logger = logging.getLogger("mqtt_adapter")


class MqttAdapter(AdapterBase):
    def __init__(self, sensor, on_leitura):
        super().__init__(sensor, on_leitura)
        self._client: mqtt.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def iniciar(self) -> None:
        cfg = self.sensor.config
        host = cfg.get("broker_host", "localhost")
        port = int(cfg.get("broker_port", 1883))
        topico = cfg["topico"]
        qos = int(cfg.get("qos", 0))

        self._loop = asyncio.get_event_loop()
        self._client = mqtt.Client(client_id=f"gateway-{self.sensor.id}", protocol=mqtt.MQTTv311)

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                client.subscribe(topico, qos=qos)
                logger.info("MQTT conectado, assinando %s (sensor=%s)", topico, self.sensor.nome)
            else:
                logger.error("MQTT falhou ao conectar (rc=%s) sensor=%s", rc, self.sensor.nome)

        def on_message(client, userdata, msg):
            valor = self._extrair_valor(msg.payload, cfg.get("campo_valor", "valor"))
            if valor is not None and self._loop:
                asyncio.run_coroutine_threadsafe(self._emitir(valor), self._loop)

        self._client.on_connect = on_connect
        self._client.on_message = on_message

        self._client.connect_async(host, port)
        self._client.loop_start()
        self._rodando = True

    @staticmethod
    def _extrair_valor(payload: bytes, campo_valor: str) -> float | None:
        texto = payload.decode("utf-8", errors="ignore").strip()
        try:
            return float(texto)
        except ValueError:
            pass
        try:
            dado = json.loads(texto)
            if isinstance(dado, dict) and campo_valor in dado:
                return float(dado[campo_valor])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        logger.warning("Não consegui extrair valor numérico do payload MQTT: %r", texto[:100])
        return None

    async def parar(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        self._rodando = False
