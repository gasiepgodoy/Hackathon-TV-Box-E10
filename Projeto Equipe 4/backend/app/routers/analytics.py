"""
Endpoints de análise por sensor.

O trabalho pesado (consulta + estatística) roda sob demanda quando a
página de análise é aberta, com um cache curto em memória: recalcular
tudo a cada requisição é caro para a CPU de um gateway de borda, e os
dados não mudam tanto assim entre dois cliques.
"""
from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .. import database, influx_writer
from ..analytics import anomalies, forecast as forecast_mod, health, statistics as stats_mod
from .data import _executar_consulta_influx, _validar_intervalo

router = APIRouter(prefix="/api/analise", tags=["analise"])


def _sanitizar(valor):
    """Substitui NaN/Infinito por None em toda a estrutura da resposta.

    JSON não tem representação para esses valores, então um único NaN
    vindo de qualquer cálculo derruba a resposta inteira com erro 500 —
    e o usuário vê só "Internal Server Error", sem pista do motivo.
    Corrigimos as origens conhecidas (séries constantes quebravam o teste
    de normalidade e o ajuste de distribuições), mas mantemos esta rede de
    segurança: é preferível um campo nulo no painel a uma análise inteira
    indisponível por causa de um número.
    """
    if isinstance(valor, dict):
        return {k: _sanitizar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_sanitizar(v) for v in valor]
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return valor

# Cache simples: chave -> (timestamp, resultado). Evita recomputar a
# análise inteira em cliques repetidos na mesma janela.
_cache: dict[str, tuple[float, dict]] = {}
_TTL_CACHE = 30.0  # segundos


def _cache_get(chave: str) -> Optional[dict]:
    entrada = _cache.get(chave)
    if entrada and (time.time() - entrada[0]) < _TTL_CACHE:
        return entrada[1]
    return None


def _cache_set(chave: str, valor: dict) -> None:
    _cache[chave] = (time.time(), valor)
    if len(_cache) > 64:
        mais_antigo = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(mais_antigo, None)


def invalidar_cache() -> None:
    _cache.clear()


def _carregar_serie(sensor_id: str, inicio: str, fim: Optional[str]) -> tuple[list[float], list[float]]:
    """Busca os pontos do sensor e devolve (valores, timestamps_epoch)."""
    pontos = _executar_consulta_influx(
        influx_writer.consultar_series, sensor_id=sensor_id, inicio=inicio, fim=fim
    )
    valores: list[float] = []
    timestamps: list[float] = []
    for p in pontos:
        valor = p.get("valor")
        if valor is None:
            continue
        try:
            ts = datetime.fromisoformat(str(p["timestamp"]).replace("Z", "+00:00")).timestamp()
        except (ValueError, KeyError):
            continue
        valores.append(float(valor))
        timestamps.append(ts)
    return valores, timestamps


def _intervalo_esperado(sensor) -> Optional[float]:
    """Extrai da config do sensor o intervalo esperado entre leituras.

    Ordem de precedência:

    1. `intervalo_esperado_s` declarado explicitamente — vale para qualquer
       protocolo. Em MQTT/OPC UA o gateway não tem como inferir a cadência
       (quem decide quando publicar é o dispositivo), mas quem instalou o
       sensor sabe. Sem essa declaração, a detecção de perda de leituras
       fica desligada nesses protocolos, e uma queda de conexão passaria
       despercebida.
    2. O intervalo de polling, nos protocolos em que o gateway controla o
       ritmo (HTTP, simulado).

    Para MQTT/OPC UA sem declaração explícita devolvemos None: chutar um
    valor faria o teste de Poisson acusar perda de leituras em sensores
    perfeitamente saudáveis que simplesmente publicam noutro ritmo.
    """
    cfg = sensor.config or {}

    declarado = cfg.get("intervalo_esperado_s")
    if declarado is not None:
        try:
            valor = float(declarado)
            if valor > 0:
                return valor
        except (TypeError, ValueError):
            pass

    if sensor.protocolo in ("mqtt", "opcua"):
        return None

    for chave in ("intervalo_segundos", "intervalo_ms"):
        if chave in cfg:
            try:
                valor = float(cfg[chave])
                return valor / 1000 if chave.endswith("_ms") else valor
            except (TypeError, ValueError):
                pass
    return None


def _info_sensor(sensor) -> dict:
    return {
        "id": sensor.id, "nome": sensor.nome, "tipo": sensor.tipo,
        "unidade": sensor.unidade, "protocolo": sensor.protocolo, "status": sensor.status,
        "limite_min": sensor.limite_min, "limite_max": sensor.limite_max,
    }


@router.get("")
def saude_de_todos(inicio: str = Query("-24h")):
    """Panorama de saúde de todos os sensores cadastrados."""
    resultados = []
    for sensor in database.listar_sensores():
        try:
            valores, timestamps = _carregar_serie(sensor.id, inicio, None)
            diagnostico = health.avaliar(valores, timestamps, _intervalo_esperado(sensor))
            resultados.append({
                "sensor_id": sensor.id, "nome": sensor.nome, "tipo": sensor.tipo,
                "status": sensor.status,
                "pontuacao": diagnostico["pontuacao"],
                "estado": diagnostico["estado"],
                "n_problemas": len(diagnostico["problemas"]),
                "n_leituras": diagnostico.get("n_leituras", 0),
            })
        except Exception as exc:
            resultados.append({"sensor_id": sensor.id, "nome": sensor.nome, "erro": str(exc)})
    return _sanitizar(resultados)


@router.get("/{sensor_id}")
def analise_completa(
    sensor_id: str,
    inicio: str = Query("-24h", description="ISO-8601 ou duração relativa do Flux"),
    fim: Optional[str] = Query(None),
):
    """Análise completa de um sensor: estatísticas, distribuição, anomalias e saúde."""
    sensor = database.obter_sensor(sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor não encontrado")

    _validar_intervalo(inicio, fim)

    chave = f"{sensor_id}|{inicio}|{fim}"
    em_cache = _cache_get(chave)
    if em_cache:
        return em_cache

    valores, timestamps = _carregar_serie(sensor_id, inicio, fim)

    if not valores:
        resultado = {
            "sensor": _info_sensor(sensor),
            "periodo": {"inicio": inicio, "fim": fim},
            "n_leituras": 0,
            "saude": health.avaliar([], [], None),
            "serie": {"timestamps": [], "valores": []},
            "mensagem": "Nenhuma leitura encontrada no período selecionado.",
        }
        _cache_set(chave, resultado)
        return resultado

    esperado = _intervalo_esperado(sensor)
    normalidade = stats_mod.testar_normalidade(valores)
    preferir_robusto = not (normalidade or {}).get("parece_normal", False)
    deteccao = anomalies.detectar_todas(valores, timestamps, preferir_robusto=preferir_robusto)

    pontos_anomalos = [
        {
            "indice": c["indice"],
            "timestamp": timestamps[c["indice"]],
            "valor": valores[c["indice"]],
            "votos": c["votos"],
            "metodos": c["metodos"],
        }
        for c in deteccao["consenso"] if c["indice"] < len(valores)
    ]

    resultado = {
        "sensor": _info_sensor(sensor),
        "periodo": {"inicio": inicio, "fim": fim},
        "n_leituras": len(valores),
        "serie": {"timestamps": timestamps, "valores": valores},
        "descritivas": stats_mod.descritivas(valores),
        "intervalo_confianca": stats_mod.intervalo_confianca_t(valores),
        "normalidade": normalidade,
        "distribuicao": stats_mod.ajustar_distribuicoes(valores),
        "taxa_chegada": stats_mod.analisar_taxa_chegada(timestamps, esperado),
        "anomalias": {
            "total": deteccao["total_pontos_anomalos"],
            "alta_confianca": len(deteccao["pontos_alta_confianca"]),
            "metodo_principal": "zscore_robusto" if preferir_robusto else "zscore",
            "pontos": pontos_anomalos,
            "resumo_por_metodo": {
                nome: {
                    "aplicavel": info.get("aplicavel", False),
                    "encontrados": len(info.get("indices", [])),
                    **({"motivo": info["motivo"]} if "motivo" in info else {}),
                }
                for nome, info in deteccao["detectores"].items()
            },
        },
        "saude": health.avaliar(valores, timestamps, esperado),
    }

    resultado = _sanitizar(resultado)
    _cache_set(chave, resultado)
    return resultado


@router.get("/{sensor_id}/previsao")
def previsao(
    sensor_id: str,
    inicio: str = Query("-24h"),
    fim: Optional[str] = Query(None),
    passos: int = Query(12, ge=1, le=100, description="Quantas leituras à frente projetar"),
    confianca: float = Query(0.95, ge=0.5, le=0.999),
):
    """Previsão ARIMA com banda de confiança + backtest na série observada.

    Separado do endpoint de análise geral porque o ajuste do modelo é a
    parte mais cara do sistema: numa CPU de borda leva alguns segundos.
    Manter separado deixa a página principal responsiva e permite que a
    previsão carregue depois, sem travar o resto.
    """
    sensor = database.obter_sensor(sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor não encontrado")

    _validar_intervalo(inicio, fim)

    chave = f"prev|{sensor_id}|{inicio}|{fim}|{passos}|{confianca}"
    em_cache = _cache_get(chave)
    if em_cache:
        return em_cache

    valores, timestamps = _carregar_serie(sensor_id, inicio, fim)
    if not valores:
        return {"sensor": _info_sensor(sensor), "previsao": {"disponivel": False,
                "motivo": "Nenhuma leitura encontrada no período selecionado."}}

    projecao = forecast_mod.prever(valores, timestamps, passos=passos, confianca=confianca)
    retro = forecast_mod.backtest(valores, timestamps)
    alerta = forecast_mod.avaliar_alerta(projecao, sensor.limite_min, sensor.limite_max,
                                         valor_atual=valores[-1] if valores else None)

    resultado = {
        "sensor": _info_sensor(sensor),
        "limites": {"minimo": sensor.limite_min, "maximo": sensor.limite_max},
        "periodo": {"inicio": inicio, "fim": fim},
        "serie": {"timestamps": timestamps, "valores": valores},
        "previsao": projecao,
        "backtest": retro,
        "alerta": alerta,
    }
    resultado = _sanitizar(resultado)
    _cache_set(chave, resultado)
    return resultado


@router.get("/{sensor_id}/saude")
def apenas_saude(sensor_id: str, inicio: str = Query("-24h"), fim: Optional[str] = Query(None)):
    """Só o diagnóstico de saúde — mais leve, para badges e listagens."""
    sensor = database.obter_sensor(sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor não encontrado")
    _validar_intervalo(inicio, fim)
    valores, timestamps = _carregar_serie(sensor_id, inicio, fim)
    return _sanitizar({
        "sensor_id": sensor_id, "nome": sensor.nome,
        **health.avaliar(valores, timestamps, _intervalo_esperado(sensor)),
    })
