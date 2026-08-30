"""
Modelos de dados da aplicação.

`tipo` do sensor vira o "measurement" no InfluxDB (ex: temperatura, umidade,
pressao). `protocolo` define qual adapter cuida da leitura (mqtt, opcua,
simulado). `config` guarda os parâmetros específicos daquele protocolo, ex:

  MQTT:     {"broker_host": "...", "broker_port": 1883, "topico": "...", "qos": 0}
  OPC UA:   {"endpoint_url": "opc.tcp://...", "node_id": "ns=2;i=2"}
  Simulado: {"valor_min": 18, "valor_max": 28, "intervalo_segundos": 5}
"""
from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
import uuid
import time

Protocolo = Literal["mqtt", "opcua", "http", "simulado"]


class SensorBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    tipo: str = Field(..., min_length=1, max_length=50, description="Vira o measurement no InfluxDB, ex: temperatura")
    protocolo: Protocolo
    unidade: Optional[str] = Field(None, max_length=20, description="Ex: °C, %, hPa")
    local: Optional[str] = Field(None, max_length=100)
    limite_min: Optional[float] = Field(None, description="Limite operacional inferior; alimenta o alerta preditivo")
    limite_max: Optional[float] = Field(None, description="Limite operacional superior; alimenta o alerta preditivo")
    config: dict[str, Any] = Field(default_factory=dict)
    ativo: bool = True


class SensorCreate(SensorBase):
    pass


class SensorUpdate(BaseModel):
    nome: Optional[str] = None
    tipo: Optional[str] = None
    protocolo: Optional[Protocolo] = None
    unidade: Optional[str] = None
    local: Optional[str] = None
    limite_min: Optional[float] = None
    limite_max: Optional[float] = None
    config: Optional[dict[str, Any]] = None
    ativo: Optional[bool] = None


class Sensor(SensorBase):
    id: str
    criado_em: float
    status: str = "parado"  # parado | conectando | ativo | erro
    ultimo_erro: Optional[str] = None

    @staticmethod
    def novo(dados: SensorCreate) -> "Sensor":
        return Sensor(
            id=str(uuid.uuid4()),
            criado_em=time.time(),
            **dados.model_dump(),
        )


class Leitura(BaseModel):
    """Uma leitura normalizada, pronta para ir ao InfluxDB e ao WebSocket."""
    sensor_id: str
    nome: str
    tipo: str
    protocolo: str
    local: Optional[str] = None
    unidade: Optional[str] = None
    valor: float
    timestamp: float  # epoch seconds
