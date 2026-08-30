from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from influxdb_client.rest import ApiException
from urllib3.exceptions import HTTPError as Urllib3HTTPError
import io

from .. import influx_writer, database

router = APIRouter(prefix="/api/dados", tags=["dados"])


def _validar_intervalo(inicio: str, fim: Optional[str]) -> None:
    """Se `inicio` e `fim` forem datas absolutas (ISO-8601), confere que
    `fim` vem depois de `inicio`. Durações relativas do Flux (ex: -24h)
    não são validadas aqui — o Influx já lida bem com elas."""
    if not fim:
        return
    try:
        dt_inicio = datetime.fromisoformat(inicio.replace("Z", "+00:00"))
        dt_fim = datetime.fromisoformat(fim.replace("Z", "+00:00"))
    except ValueError:
        return  # não são datas absolutas (ex: "-24h") — nada a validar aqui

    if dt_fim <= dt_inicio:
        raise HTTPException(
            400,
            f'A data final ({fim}) precisa ser depois da data inicial ({inicio}). '
            'Confira os campos "De" e "Até".',
        )


def _executar_consulta_influx(func, *args, **kwargs):
    """Roda uma função que fala com o InfluxDB e traduz falhas comuns
    (serviço fora do ar, query rejeitada, credenciais erradas) em um
    HTTPException com mensagem legível, em vez de deixar vazar um 500 cru."""
    try:
        return func(*args, **kwargs)
    except ApiException as exc:
        raise HTTPException(400, f"InfluxDB recusou a consulta: {exc.reason}") from exc
    except Urllib3HTTPError as exc:
        raise HTTPException(
            503,
            "Não consegui conectar ao InfluxDB. Confira se o serviço está rodando "
            f"(sudo systemctl status influxdb) e se INFLUX_URL está correto no .env. Detalhe: {exc}",
        ) from exc


@router.get("")
def consultar(
    sensor_id: Optional[str] = None,
    tipo: Optional[str] = None,
    inicio: str = Query("-24h", description='ISO-8601 ou duração relativa do Flux, ex: -24h, -7d, 2026-08-01T00:00:00Z'),
    fim: Optional[str] = Query(None, description="ISO-8601. Se vazio, considera até agora"),
):
    """Retorna os pontos para o gráfico do dashboard, já ordenados no tempo.

    Quando `sensor_id` não é informado (visão "todos os sensores"), o
    resultado é restrito aos sensores que ainda existem no cadastro —
    histórico de sensor removido continua no InfluxDB, mas não aparece
    mais aqui (veja o docstring de `consultar_series`)."""
    _validar_intervalo(inicio, fim)
    ids_validos = None if sensor_id else {s.id for s in database.listar_sensores()}
    return _executar_consulta_influx(
        influx_writer.consultar_series,
        sensor_id=sensor_id, tipo=tipo, inicio=inicio, fim=fim, sensor_ids_validos=ids_validos,
    )


@router.get("/csv")
def exportar_csv(
    sensor_id: Optional[str] = None,
    tipo: Optional[str] = None,
    inicio: str = "-24h",
    fim: Optional[str] = None,
):
    """Gera o CSV do mesmo intervalo mostrado no gráfico, pronto para download."""
    _validar_intervalo(inicio, fim)
    ids_validos = None if sensor_id else {s.id for s in database.listar_sensores()}
    csv_texto = _executar_consulta_influx(
        influx_writer.gerar_csv,
        sensor_id=sensor_id, tipo=tipo, inicio=inicio, fim=fim, sensor_ids_validos=ids_validos,
    )
    nome_arquivo = f"dados_{sensor_id or tipo or 'todos'}.csv"
    return StreamingResponse(
        io.StringIO(csv_texto),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@router.get("/tipos")
def listar_tipos():
    """Lista os tipos (measurements) distintos com base nos sensores cadastrados,
    usado para popular o filtro do dashboard."""
    sensores = database.listar_sensores()
    tipos = sorted({s.tipo for s in sensores})
    return tipos
