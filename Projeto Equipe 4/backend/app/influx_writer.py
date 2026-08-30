"""
Escrita e consulta de dados no InfluxDB.

Modelo de dados adotado:
  - measurement = sensor.tipo        (ex: "temperatura", "umidade", "pressao")
  - tags        = sensor_id, protocolo, local   -> indexados, baratos de filtrar
  - field       = valor              (float)
  - time        = timestamp da leitura

Isso substitui a ideia de "um arquivo por sensor": em vez de arquivos,
cada sensor vira uma combinação única da tag `sensor_id`, então dá pra
filtrar/consultar cada sensor isoladamente sem misturar dados, e ainda
assim consultar "todas as temperaturas" de uma vez quando fizer sentido.
"""
import asyncio
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from .config import settings
from .models import Leitura

logger = logging.getLogger("influx_writer")

_client: Optional[InfluxDBClient] = None
_write_api = None


def conectar() -> None:
    global _client, _write_api
    _client = InfluxDBClient(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org,
    )
    # Criado uma vez só: instanciar o write_api a cada leitura desperdiça
    # trabalho e impede o reuso da conexão HTTP subjacente.
    _write_api = _client.write_api(write_options=SYNCHRONOUS)

    # Falha rápido e com uma mensagem clara se as credenciais estiverem erradas
    health = _client.health()
    if health.status != "pass":
        logger.warning("InfluxDB respondeu status=%s: %s", health.status, health.message)
    else:
        logger.info("Conectado ao InfluxDB em %s", settings.influx_url)


def desconectar() -> None:
    global _write_api
    _write_api = None
    if _client:
        _client.close()


def _montar_ponto(leitura: Leitura) -> Point:
    return (
        Point(leitura.tipo)
        .tag("sensor_id", leitura.sensor_id)
        .tag("protocolo", leitura.protocolo)
        .tag("local", leitura.local or "sem_local")
        .field("valor", leitura.valor)
        .time(int(leitura.timestamp * 1e9), WritePrecision.NS)
    )


def escrever_leitura(leitura: Leitura) -> None:
    """Grava uma leitura no InfluxDB (chamada bloqueante).

    Em código assíncrono use `escrever_leitura_async`, não esta função:
    a escrita é uma chamada HTTP síncrona e travaria o event loop inteiro.
    """
    if _write_api is None:
        raise RuntimeError("InfluxDB não conectado — chame conectar() no startup")
    _write_api.write(bucket=settings.influx_bucket, record=_montar_ponto(leitura))


async def escrever_leitura_async(leitura: Leitura) -> None:
    """Versão assíncrona: executa a escrita bloqueante numa thread.

    Sem isso, cada gravação congela o event loop até o InfluxDB responder —
    e como todos os adapters e o WebSocket compartilham esse mesmo loop, um
    InfluxDB lento derruba a cadência de TODOS os sensores ao mesmo tempo.
    O sintoma é uma taxa de entrega baixa que parece falha do sensor, mas na
    verdade é o gateway travando a si mesmo.
    """
    await asyncio.to_thread(escrever_leitura, leitura)


def _flux_range(inicio: Optional[str], fim: Optional[str]) -> str:
    inicio_flux = inicio or "-30d"
    if fim:
        return f"range(start: {inicio_flux}, stop: {fim})" if not inicio.startswith("-") else f"range(start: {inicio_flux})"
    return f"range(start: {inicio_flux})"


def consultar_series(
    sensor_id: Optional[str] = None,
    tipo: Optional[str] = None,
    inicio: str = "-24h",
    fim: Optional[str] = None,
    sensor_ids_validos: Optional[set[str]] = None,
) -> list[dict]:
    """Consulta pontos no InfluxDB para alimentar os gráficos do dashboard.

    `inicio`/`fim` aceitam tanto ISO-8601 (ex: 2026-08-01T00:00:00Z) quanto
    durações relativas do Flux (ex: -24h, -7d).

    `sensor_ids_validos`, se informado, filtra o resultado pra só incluir
    pontos de sensores que ainda existem no cadastro (SQLite). Usado na
    visão "todos os sensores": o InfluxDB nunca apaga histórico de sensor
    removido — de propósito, pra permitir auditoria depois — mas isso não
    deve poluir a visão geral do dashboard com sensores que não existem mais.
    """
    if _client is None:
        raise RuntimeError("InfluxDB não conectado")

    range_clause = f"range(start: {inicio}" + (f", stop: {fim})" if fim else ")")

    filtros = []
    if tipo:
        filtros.append(f'r._measurement == "{tipo}"')
    if sensor_id:
        filtros.append(f'r.sensor_id == "{sensor_id}"')
    filtros.append('r._field == "valor"')
    filtro_clause = " and ".join(filtros)

    flux = f'''
    from(bucket: "{settings.influx_bucket}")
      |> {range_clause}
      |> filter(fn: (r) => {filtro_clause})
      |> sort(columns: ["_time"])
    '''

    query_api = _client.query_api()
    tabelas = query_api.query(flux)

    pontos = []
    for tabela in tabelas:
        for registro in tabela.records:
            sid = registro.values.get("sensor_id")
            if sensor_ids_validos is not None and sid not in sensor_ids_validos:
                continue
            pontos.append({
                "sensor_id": sid,
                "tipo": registro.get_measurement(),
                "local": registro.values.get("local"),
                "valor": registro.get_value(),
                "timestamp": registro.get_time().isoformat(),
            })
    return pontos


def gerar_csv(
    sensor_id: Optional[str],
    tipo: Optional[str],
    inicio: str,
    fim: Optional[str],
    sensor_ids_validos: Optional[set[str]] = None,
) -> str:
    """Gera um CSV em memória a partir da mesma consulta usada pelo gráfico."""
    pontos = consultar_series(
        sensor_id=sensor_id, tipo=tipo, inicio=inicio, fim=fim, sensor_ids_validos=sensor_ids_validos
    )

    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=["timestamp", "sensor_id", "tipo", "local", "valor"])
    escritor.writeheader()
    for p in pontos:
        escritor.writerow(p)
    return buffer.getvalue()
