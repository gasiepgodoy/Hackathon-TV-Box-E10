"""
Previsão de série temporal com banda de confiança.

Duas entregas distintas, que respondem perguntas diferentes:

  1. PREVISÃO FUTURA — para onde o sensor está indo nos próximos passos,
     com uma faixa de incerteza. Serve para antecipar que uma grandeza
     vai cruzar um limite operacional antes que ela cruze de fato.

  2. BACKTEST NA SÉRIE OBSERVADA — o modelo prevê cada ponto usando só o
     passado dele, e marcamos onde o valor real caiu fora da banda. Isso
     é uma detecção de anomalia mais forte que os limiares estatísticos
     do módulo `anomalies`, porque leva em conta tendência e autocorrelação:
     numa série que sobe de manhã todo dia, 26°C às 14h pode ser normal e
     26°C às 3h ser anômalo — um limiar fixo não distingue os dois.

Escolha do modelo: tentamos ARIMA com uma grade pequena de ordens e
escolhemos pelo AIC. Se a série for curta ou o ajuste falhar, caímos para
suavização exponencial (Holt), e em último caso para uma banda ingênua
baseada na variação recente. A ideia é sempre devolver algo útil em vez
de um erro — um gateway não pode ficar sem previsão porque um sensor tem
poucos dados.

Nota de custo: rodar isso numa CPU de borda não é grátis. A série é
subamostrada acima de um limite e a grade de ordens é deliberadamente
pequena, para o ajuste caber em segundos em vez de minutos.
"""
from __future__ import annotations

import logging
import warnings
from typing import Optional

import numpy as np

logger = logging.getLogger("forecast")

# Limites pensados para hardware de borda (ARM, pouca RAM)
MAX_PONTOS_AJUSTE = 1500
GRADE_ORDENS = [
    (1, 0, 0), (2, 0, 0), (1, 0, 1),
    (0, 1, 1), (1, 1, 0), (1, 1, 1), (2, 1, 1), (2, 1, 2),
]


def _subamostrar(valores: np.ndarray, timestamps: np.ndarray, maximo: int) -> tuple[np.ndarray, np.ndarray]:
    """Reduz a série mantendo o formato geral, quando ela é longa demais.

    Ajustar ARIMA em dezenas de milhares de pontos numa CPU de borda pode
    levar minutos. A forma da série se preserva bem com amostragem
    uniforme, e a previsão de curto prazo praticamente não muda.
    """
    n = len(valores)
    if n <= maximo:
        return valores, timestamps
    indices = np.linspace(0, n - 1, maximo).astype(int)
    return valores[indices], timestamps[indices]


def _serie_tem_variacao(valores: np.ndarray) -> bool:
    return float(np.std(valores)) > 1e-10


def _ajustar_arima(valores: np.ndarray) -> Optional[dict]:
    """Testa a grade de ordens e devolve o melhor ajuste por AIC."""
    try:
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError:
        logger.warning("statsmodels não instalado — previsão ARIMA indisponível")
        return None

    melhor = None
    with warnings.catch_warnings():
        # Ordens ruins da grade emitem avisos de convergência; isso é
        # esperado — elas simplesmente perdem no AIC e são descartadas.
        warnings.simplefilter("ignore")
        for ordem in GRADE_ORDENS:
            try:
                modelo = ARIMA(valores, order=ordem).fit()
                aic = float(modelo.aic)
                if not np.isfinite(aic):
                    continue
                if melhor is None or aic < melhor["aic"]:
                    melhor = {"modelo": modelo, "ordem": ordem, "aic": aic}
            except Exception:
                continue
    return melhor


def _ajustar_holt(valores: np.ndarray) -> Optional[dict]:
    """Suavização exponencial de Holt — alternativa leve quando o ARIMA falha."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except ImportError:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            modelo = ExponentialSmoothing(valores, trend="add", seasonal=None,
                                          initialization_method="estimated").fit()
        return {"modelo": modelo, "ordem": None, "aic": float(getattr(modelo, "aic", np.nan))}
    except Exception:
        return None


def prever(
    valores: list[float],
    timestamps: list[float],
    passos: int = 12,
    confianca: float = 0.95,
) -> dict:
    """Previsão dos próximos `passos` pontos, com banda de confiança."""
    arr = np.asarray(valores, dtype=float)
    ts = np.asarray(timestamps, dtype=float)
    mascara = np.isfinite(arr)
    arr, ts = arr[mascara], ts[mascara]

    n = len(arr)
    if n < 12:
        return {"disponivel": False, "motivo": "São necessárias ao menos 12 leituras para gerar previsão."}

    if not _serie_tem_variacao(arr):
        # Série constante: previsão é trivialmente o próprio valor. Dizer
        # isso explicitamente é mais honesto que devolver uma banda de
        # largura zero como se fosse uma previsão confiante.
        valor = float(arr[-1])
        passo_t = float(np.median(np.diff(ts))) if n > 1 else 60.0
        return {
            "disponivel": True,
            "modelo": "constante",
            "aviso": "A série não varia — o sensor pode estar congelado. A previsão apenas repete o último valor.",
            "passos": passos,
            "previsao": [
                {"timestamp": float(ts[-1] + passo_t * (i + 1)), "valor": valor,
                 "limite_inferior": valor, "limite_superior": valor}
                for i in range(passos)
            ],
        }

    arr_fit, ts_fit = _subamostrar(arr, ts, MAX_PONTOS_AJUSTE)

    ajuste = _ajustar_arima(arr_fit)
    nome_modelo = "arima"
    if ajuste is None:
        ajuste = _ajustar_holt(arr_fit)
        nome_modelo = "holt"
    if ajuste is None:
        return _previsao_ingenua(arr, ts, passos, confianca)

    alfa = 1 - confianca
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resultado = ajuste["modelo"].get_forecast(steps=passos)
            media = np.asarray(resultado.predicted_mean, dtype=float)
            intervalo = np.asarray(resultado.conf_int(alpha=alfa), dtype=float)
    except Exception as exc:
        logger.warning("Falha ao projetar com %s: %s — usando banda ingênua", nome_modelo, exc)
        return _previsao_ingenua(arr, ts, passos, confianca)

    passo_t = float(np.median(np.diff(ts))) if n > 1 else 60.0
    ultimo_t = float(ts[-1])

    previsao = [
        {
            "timestamp": ultimo_t + passo_t * (i + 1),
            "valor": float(media[i]),
            "limite_inferior": float(intervalo[i][0]),
            "limite_superior": float(intervalo[i][1]),
        }
        for i in range(len(media))
    ]

    return {
        "disponivel": True,
        "modelo": nome_modelo,
        "ordem": list(ajuste["ordem"]) if ajuste.get("ordem") else None,
        "aic": ajuste.get("aic"),
        "confianca": confianca,
        "passos": passos,
        "intervalo_amostragem_s": passo_t,
        "pontos_usados": int(len(arr_fit)),
        "previsao": previsao,
    }


def _previsao_ingenua(arr: np.ndarray, ts: np.ndarray, passos: int, confianca: float) -> dict:
    """Último recurso: repete o valor final com banda pela variação recente.

    Não é sofisticado, mas é honesto e sempre funciona. Melhor devolver
    uma banda larga e admitir a incerteza do que não devolver nada.
    """
    from scipy import stats as sp_stats

    janela = arr[-min(len(arr), 50):]
    centro = float(np.median(janela))
    desvio = float(np.std(janela, ddof=1)) if len(janela) > 1 else 0.0
    z = float(sp_stats.norm.ppf((1 + confianca) / 2))
    passo_t = float(np.median(np.diff(ts))) if len(ts) > 1 else 60.0
    ultimo_t = float(ts[-1])

    return {
        "disponivel": True,
        "modelo": "ingenuo",
        "aviso": "Não foi possível ajustar um modelo de série temporal; a banda usa apenas a variação recente.",
        "confianca": confianca,
        "passos": passos,
        "intervalo_amostragem_s": passo_t,
        "previsao": [
            {
                "timestamp": ultimo_t + passo_t * (i + 1),
                "valor": centro,
                # A incerteza cresce com o horizonte: prever 10 passos à
                # frente é mais incerto que prever 1
                "limite_inferior": centro - z * desvio * np.sqrt(i + 1),
                "limite_superior": centro + z * desvio * np.sqrt(i + 1),
            }
            for i in range(passos)
        ],
    }


def backtest(
    valores: list[float],
    timestamps: list[float],
    confianca: float = 0.99,
    minimo_treino: int = 30,
) -> dict:
    """Ajusta o modelo e marca onde o valor observado saiu da banda.

    Usa previsão um-passo-à-frente dentro da amostra: para cada ponto, o
    modelo estima onde ele deveria estar dado o comportamento anterior, e
    comparamos com o que realmente veio. Pontos fora da banda são
    anomalias contextuais — levam em conta tendência e autocorrelação,
    não só o nível absoluto.

    A confiança padrão aqui é mais alta (99%) que na previsão futura:
    numa série longa, uma banda de 95% marcaria ~5% dos pontos como
    anômalos só por acaso, o que seria ruído puro no alerta.
    """
    arr = np.asarray(valores, dtype=float)
    ts = np.asarray(timestamps, dtype=float)
    mascara = np.isfinite(arr)
    arr, ts = arr[mascara], ts[mascara]

    n = len(arr)
    if n < minimo_treino:
        return {"disponivel": False, "motivo": f"São necessárias ao menos {minimo_treino} leituras para o backtest."}

    if not _serie_tem_variacao(arr):
        return {"disponivel": False, "motivo": "A série não varia — não há o que modelar."}

    arr_fit, ts_fit = _subamostrar(arr, ts, MAX_PONTOS_AJUSTE)

    ajuste = _ajustar_arima(arr_fit)
    nome_modelo = "arima"
    if ajuste is None:
        ajuste = _ajustar_holt(arr_fit)
        nome_modelo = "holt"
    if ajuste is None:
        return {"disponivel": False, "motivo": "Não foi possível ajustar um modelo de série temporal."}

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            predicao = ajuste["modelo"].get_prediction(start=0)
            media = np.asarray(predicao.predicted_mean, dtype=float)
            intervalo = np.asarray(predicao.conf_int(alpha=1 - confianca), dtype=float)
    except Exception as exc:
        logger.warning("Falha no backtest: %s", exc)
        return {"disponivel": False, "motivo": "O modelo ajustou, mas não foi possível reconstruir a banda."}

    fora = []
    residuos = []
    for i in range(len(arr_fit)):
        if i >= len(media) or not np.isfinite(media[i]):
            continue
        inf, sup = float(intervalo[i][0]), float(intervalo[i][1])
        if not (np.isfinite(inf) and np.isfinite(sup)):
            continue
        real = float(arr_fit[i])
        residuos.append(real - float(media[i]))
        if real < inf or real > sup:
            desvio_rel = (real - sup) if real > sup else (inf - real)
            fora.append({
                "indice": int(i),
                "timestamp": float(ts_fit[i]),
                "valor": real,
                "esperado": float(media[i]),
                "limite_inferior": inf,
                "limite_superior": sup,
                "excesso": float(desvio_rel),
                "direcao": "acima" if real > sup else "abaixo",
            })

    # Descarta o começo da série: com pouquíssimo histórico o modelo ainda
    # não "aprendeu" o padrão e produz bandas irreais, gerando falsos alertas.
    aquecimento = min(minimo_treino, len(arr_fit) // 10)
    fora = [f for f in fora if f["indice"] >= aquecimento]

    banda = [
        {
            "timestamp": float(ts_fit[i]),
            "esperado": float(media[i]),
            "limite_inferior": float(intervalo[i][0]),
            "limite_superior": float(intervalo[i][1]),
        }
        for i in range(aquecimento, len(arr_fit))
        if i < len(media) and np.isfinite(media[i]) and np.isfinite(intervalo[i][0])
    ]
    # O aquecimento também é descartado da banda, não só dos alertas: nos
    # primeiros pontos o modelo ainda não tem informação e a inicialização
    # difusa produz limites absurdos (±2500 numa série de 18–28 °C). Se
    # esses pontos fossem para o gráfico, a escala do eixo Y esticaria para
    # acomodá-los e a série real viraria uma linha reta no meio.

    # As métricas de erro usam a mesma janela dos alertas (pós-aquecimento),
    # senão o erro do período em que o modelo ainda estava "aprendendo"
    # contaminaria um número que serve para julgar a qualidade do ajuste.
    residuos_arr = np.asarray(residuos[aquecimento:], dtype=float)
    n_avaliados = len(banda)

    return {
        "disponivel": True,
        "modelo": nome_modelo,
        "ordem": list(ajuste["ordem"]) if ajuste.get("ordem") else None,
        "aic": ajuste.get("aic"),
        "confianca": confianca,
        "pontos_avaliados": n_avaliados,
        "pontos_fora_banda": len(fora),
        "proporcao_fora": float(len(fora) / n_avaliados) if n_avaliados else 0.0,
        "fora_da_banda": fora,
        "banda": banda,
        "erro_medio_absoluto": float(np.mean(np.abs(residuos_arr))) if len(residuos_arr) else None,
        "rmse": float(np.sqrt(np.mean(residuos_arr ** 2))) if len(residuos_arr) else None,
    }


def avaliar_alerta(previsao: dict, limite_min: Optional[float] = None,
                   limite_max: Optional[float] = None,
                   valor_atual: Optional[float] = None) -> Optional[dict]:
    """Verifica se a previsão indica cruzamento de um limite operacional.

    Este é o uso mais acionável da previsão: em vez de avisar depois que
    a grandeza saiu da faixa, avisa que ela deve sair — e em quantos
    passos. Só faz sentido se o usuário definiu limites para o sensor.

    Antes de projetar, checamos o estado atual: se o valor JÁ está fora
    da faixa, anunciar "cruzamento provável em 1 leitura" seria enganoso —
    não há nada a antecipar, o problema já existe. Nesse caso o alerta
    muda de natureza (de previsão para constatação), o que também evita o
    caso degenerado de um limite mal configurado disparar alarme de
    cruzamento iminente em toda leitura.
    """
    if not previsao.get("disponivel") or (limite_min is None and limite_max is None):
        return None

    if valor_atual is not None:
        if limite_max is not None and valor_atual > limite_max:
            return {
                "tipo": "ja_fora_superior", "situacao": "atual",
                "limite": limite_max, "valor_atual": valor_atual,
                "mensagem": f"O valor atual ({valor_atual:.2f}) já está acima do limite superior ({limite_max}).",
            }
        if limite_min is not None and valor_atual < limite_min:
            return {
                "tipo": "ja_fora_inferior", "situacao": "atual",
                "limite": limite_min, "valor_atual": valor_atual,
                "mensagem": f"O valor atual ({valor_atual:.2f}) já está abaixo do limite inferior ({limite_min}).",
            }

    for i, p in enumerate(previsao.get("previsao", [])):
        if limite_max is not None and p["limite_superior"] > limite_max:
            certeza = "provável" if p["valor"] > limite_max else "possível"
            return {
                "tipo": "limite_superior", "situacao": "previsto",
                "passos_ate": i + 1, "timestamp": p["timestamp"],
                "limite": limite_max, "valor_previsto": p["valor"], "certeza": certeza,
                "mensagem": f"Cruzamento {certeza} do limite superior ({limite_max}) em {i + 1} leitura(s).",
            }
        if limite_min is not None and p["limite_inferior"] < limite_min:
            certeza = "provável" if p["valor"] < limite_min else "possível"
            return {
                "tipo": "limite_inferior", "situacao": "previsto",
                "passos_ate": i + 1, "timestamp": p["timestamp"],
                "limite": limite_min, "valor_previsto": p["valor"], "certeza": certeza,
                "mensagem": f"Cruzamento {certeza} do limite inferior ({limite_min}) em {i + 1} leitura(s).",
            }
    return None
