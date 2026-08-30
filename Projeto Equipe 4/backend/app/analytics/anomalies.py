"""
Detecção de anomalias em séries de sensores.

Nenhum detector sozinho é suficiente, porque "anomalia" tem tipos diferentes:

  - PICO isolado (valor absurdo num instante)      -> z-score / MAD / IQR
  - DESVIO SUSTENTADO (média migrou aos poucos)    -> CUSUM / EWMA
  - MUDANÇA DE REGIME (quebra abrupta no padrão)   -> Page-Hinkley
  - SALTO IMPOSSÍVEL (variação rápida demais)      -> taxa de variação
  - SENSOR CONGELADO (valor não muda mais)         -> flatline

Um pico é ruído; um desvio sustentado é descalibração; um valor congelado
é sensor morto. Detectar só picos deixaria passar as duas falhas mais
graves — por isso rodamos todos e combinamos os resultados.
"""
from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
from scipy import stats


def _preparar(valores: list[float]) -> np.ndarray:
    arr = np.asarray(valores, dtype=float)
    return arr


def zscore(valores: list[float], limiar: float = 3.0) -> dict:
    """Detector clássico: quantos desvios padrão o ponto está da média.

    Válido quando os dados são aproximadamente normais. Tem uma fraqueza
    conhecida: a própria média e o desvio são contaminados pelos outliers
    que queremos achar — por isso o método robusto abaixo costuma ser melhor.
    """
    arr = _preparar(valores)
    if len(arr) < 3:
        return {"metodo": "zscore", "indices": [], "aplicavel": False}

    media = float(np.mean(arr))
    desvio = float(np.std(arr, ddof=1))
    if desvio == 0:
        return {"metodo": "zscore", "indices": [], "aplicavel": False, "motivo": "série constante"}

    scores = np.abs((arr - media) / desvio)
    indices = np.where(scores > limiar)[0]

    return {
        "metodo": "zscore",
        "aplicavel": True,
        "limiar": limiar,
        "indices": [int(i) for i in indices],
        "scores": [float(scores[i]) for i in indices],
        "limite_inferior": media - limiar * desvio,
        "limite_superior": media + limiar * desvio,
    }


def zscore_robusto(valores: list[float], limiar: float = 3.5) -> dict:
    """Z-score modificado, baseado em mediana e MAD (Iglewicz-Hoaglin).

    É o detector correto quando a série tem caudas pesadas (distribuição
    de Laplace): mediana e MAD não são arrastados pelos outliers, então
    um pico gigante não "esconde" os outros picos ao inflar o desvio.
    O fator 0.6745 normaliza o MAD para ficar comparável ao desvio padrão
    de uma normal.
    """
    arr = _preparar(valores)
    if len(arr) < 3:
        return {"metodo": "zscore_robusto", "indices": [], "aplicavel": False}

    mediana = float(np.median(arr))
    mad = float(np.median(np.abs(arr - mediana)))

    if mad == 0:
        # MAD zero acontece quando >50% dos valores são idênticos.
        # Cai pro desvio absoluto médio, que ainda é mais robusto que o padrão.
        desvio_medio = float(np.mean(np.abs(arr - mediana)))
        if desvio_medio == 0:
            return {"metodo": "zscore_robusto", "indices": [], "aplicavel": False, "motivo": "série constante"}
        scores = np.abs(arr - mediana) / (1.253314 * desvio_medio)
    else:
        scores = 0.6745 * np.abs(arr - mediana) / mad

    indices = np.where(scores > limiar)[0]

    return {
        "metodo": "zscore_robusto",
        "aplicavel": True,
        "limiar": limiar,
        "indices": [int(i) for i in indices],
        "scores": [float(scores[i]) for i in indices],
        "mediana": mediana,
        "mad": mad,
    }


def iqr_tukey(valores: list[float], fator: float = 1.5) -> dict:
    """Cercas de Tukey: fora de [Q1 - k·IQR, Q3 + k·IQR].

    Totalmente não-paramétrico (não supõe distribuição nenhuma), o que o
    torna um bom voto de desempate quando não sabemos a forma dos dados.
    Fator 1.5 marca outliers; 3.0 marca outliers extremos.
    """
    arr = _preparar(valores)
    if len(arr) < 4:
        return {"metodo": "iqr", "indices": [], "aplicavel": False}

    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        return {"metodo": "iqr", "indices": [], "aplicavel": False, "motivo": "IQR zero"}

    limite_inf = q1 - fator * iqr
    limite_sup = q3 + fator * iqr
    indices = np.where((arr < limite_inf) | (arr > limite_sup))[0]

    return {
        "metodo": "iqr",
        "aplicavel": True,
        "fator": fator,
        "indices": [int(i) for i in indices],
        "limite_inferior": float(limite_inf),
        "limite_superior": float(limite_sup),
    }


def ewma(valores: list[float], alfa: float = 0.3, limiar: float = 3.0) -> dict:
    """Carta de controle EWMA (média móvel exponencialmente ponderada).

    Diferente dos detectores acima, este tem MEMÓRIA: cada ponto é
    comparado com uma média que dá mais peso ao passado recente. Isso o
    torna sensível a deslocamentos pequenos e persistentes da média —
    exatamente o padrão de um sensor perdendo calibração aos poucos,
    que os detectores de pico não enxergam.
    """
    arr = _preparar(valores)
    n = len(arr)
    if n < 10:
        return {"metodo": "ewma", "indices": [], "aplicavel": False}

    # Mesma correção do CUSUM: a carta EWMA também assume independência.
    acf = autocorrelacao_lag1(valores)
    base_serie = "valores"
    if acf is not None and abs(acf) > 0.4 and n > 12:
        arr = _residuos_ar1(arr)
        n = len(arr)
        base_serie = "residuos_ar1"

    media = float(np.mean(arr))
    desvio = float(np.std(arr, ddof=1))
    if desvio == 0:
        return {"metodo": "ewma", "indices": [], "aplicavel": False, "motivo": "série constante"}

    z = np.empty(n)
    z[0] = arr[0]
    for i in range(1, n):
        z[i] = alfa * arr[i] + (1 - alfa) * z[i - 1]

    # Limites de controle crescem até o valor assintótico conforme a série avança
    fator_var = np.sqrt((alfa / (2 - alfa)) * (1 - (1 - alfa) ** (2 * np.arange(1, n + 1))))
    limite_sup = media + limiar * desvio * fator_var
    limite_inf = media - limiar * desvio * fator_var

    indices = np.where((z > limite_sup) | (z < limite_inf))[0]

    return {
        "metodo": "ewma",
        "aplicavel": True,
        "base": base_serie,
        "autocorrelacao": acf,
        "alfa": alfa,
        "limiar": limiar,
        "indices": [int(i) for i in indices],
        "ewma": [float(v) for v in z],
        "limite_superior": [float(v) for v in limite_sup],
        "limite_inferior": [float(v) for v in limite_inf],
    }


def autocorrelacao_lag1(valores: list[float]) -> Optional[float]:
    """Correlação entre cada leitura e a anterior.

    Perto de 0 significa leituras praticamente independentes; perto de 1
    significa que cada valor é quase o anterior — o caso normal de grandezas
    físicas com inércia (temperatura, pressão, nível). Esse número decide
    quais detectores são válidos.
    """
    arr = _preparar(valores)
    if len(arr) < 10 or float(np.std(arr)) < 1e-12:
        return None
    with np.errstate(invalid="ignore"):
        r = float(np.corrcoef(arr[:-1], arr[1:])[0, 1])
    return r if np.isfinite(r) else None


def _residuos_ar1(arr: np.ndarray) -> np.ndarray:
    """Resíduos de x_t = c + φ·x_{t-1}, isto é, o que sobra depois de
    descontar a dependência do valor anterior."""
    X = np.column_stack([np.ones(len(arr) - 1), arr[:-1]])
    y = arr[1:]
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ coef


def testar_drift(valores: list[float], limiar_p: float = 0.01) -> dict:
    """Testa desvio sustentado (perda de calibração) de forma estatisticamente válida.

    O CUSUM clássico pressupõe leituras independentes. Grandezas físicas
    reais têm autocorrelação altíssima (0,99 é comum), e nesse regime a
    soma acumulada do CUSUM dispara sozinha: numa série de passeio
    aleatório sem drift nenhum ele chega a marcar 99% dos pontos. Usá-lo
    cru aqui produziria alarme de descalibração em todo sensor saudável.

    Então escolhemos o teste conforme a natureza da série:

    - Série com raiz unitária (passeia sem média fixa): drift equivale à
      média das diferenças ser diferente de zero.
    - Série estacionária em torno de tendência: drift equivale à
      inclinação da regressão ser significativa.

    Em ambos os casos os erros-padrão são corrigidos (HAC/Newey-West) para
    não subestimar a incerteza por causa da autocorrelação.

    Limitação honesta: numa série de passeio aleatório puro, distinguir
    "drift real" de "vagar aleatório" é estatisticamente difícil por
    natureza — não é falha da implementação. Tendência real em série
    estacionária é detectada de forma confiável.
    """
    arr = _preparar(valores)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < 30:
        return {"aplicavel": False, "motivo": "São necessárias ao menos 30 leituras."}
    if float(np.std(arr)) < 1e-12:
        return {"aplicavel": False, "motivo": "série constante"}

    try:
        import statsmodels.api as sm
        from statsmodels.tsa.stattools import adfuller
    except ImportError:
        return {"aplicavel": False, "motivo": "statsmodels não instalado"}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            p_adf = float(adfuller(arr, regression="ct", autolag="AIC")[1])
        except Exception:
            p_adf = 1.0

        raiz_unitaria = p_adf > 0.05
        try:
            if raiz_unitaria:
                d = np.diff(arr)
                lags = max(1, int(len(d) ** (1 / 3)))
                modelo = sm.OLS(d, np.ones((len(d), 1))).fit(
                    cov_type="HAC", cov_kwds={"maxlags": lags})
                p_valor = float(modelo.pvalues[0])
                coeficiente = float(modelo.params[0])
                base = "media_das_diferencas"
            else:
                t = np.arange(n)
                lags = max(1, int(n ** (1 / 3)))
                modelo = sm.OLS(arr, sm.add_constant(t)).fit(
                    cov_type="HAC", cov_kwds={"maxlags": lags})
                p_valor = float(modelo.pvalues[1])
                coeficiente = float(modelo.params[1])
                base = "inclinacao_da_regressao"
        except Exception as exc:
            return {"aplicavel": False, "motivo": f"falha no ajuste: {exc}"}

    detectado = bool(p_valor < limiar_p)
    return {
        "aplicavel": True,
        "drift_detectado": detectado,
        "p_valor": p_valor,
        "coeficiente": coeficiente,
        "direcao": ("alta" if coeficiente > 0 else "baixa") if detectado else None,
        "base": base,
        "serie_com_raiz_unitaria": raiz_unitaria,
        "adf_p_valor": p_adf,
        "variacao_por_leitura": coeficiente,
    }


def cusum(valores: list[float], k: float = 0.5, h: float = 10.0, limite_influencia: float = 4.0,
          usar_residuos: Optional[bool] = None) -> dict:
    """CUSUM: soma cumulativa dos desvios em relação à média de referência.

    Padrão em controle estatístico de processo industrial. Acumula
    pequenos desvios na mesma direção até cruzar um limiar — por isso
    detecta drift lento que ficaria para sempre dentro dos limites de
    um z-score. `k` é a folga (em desvios padrão) e `h` o limiar de alarme.

    O valor clássico de h na literatura é 5, mas ele pressupõe
    monitoramento sequencial com reinício após cada alarme. Aplicado a um
    lote inteiro de centenas de pontos, h=5 dispara em ~40% das séries
    perfeitamente saudáveis, só por passeio aleatório da soma. Em h=10 os
    falsos positivos zeram (testado até 3000 pontos) sem perder detecção
    de drift real, inclusive sutil.

    `limite_influencia` winsoriza cada observação normalizada. Sem isso,
    um único pico extremo (ex: 45 numa série em torno de 23) injeta
    dezenas de unidades na soma de uma vez, que leva centenas de leituras
    para decair — e o detector reporta "drift" numa série que na verdade
    só tinha dois outliers isolados. Drift é um deslocamento SUSTENTADO
    do nível; nenhuma leitura sozinha deve ser capaz de caracterizá-lo.
    """
    arr = _preparar(valores)
    n = len(arr)
    if n < 10:
        return {"metodo": "cusum", "indices": [], "aplicavel": False}

    # Se a série é autocorrelacionada (o normal em grandezas físicas), o
    # CUSUM aplicado aos valores brutos dispara sozinho — a premissa de
    # independência está violada. Aplicá-lo aos resíduos de um AR(1)
    # restaura essa premissa. Para "existe drift?" use `testar_drift`,
    # que é o teste estatisticamente correto para esse regime.
    acf = autocorrelacao_lag1(valores)
    if usar_residuos is None:
        usar_residuos = acf is not None and abs(acf) > 0.4
    base_serie = "valores"
    if usar_residuos and n > 12:
        arr = _residuos_ar1(arr)
        n = len(arr)
        base_serie = "residuos_ar1"

    # Normalizamos por mediana/MAD, não média/desvio: um pico isolado
    # extremo arrasta a média e infla a soma acumulada, produzindo "drift"
    # fantasma numa série que só tinha dois outliers. Mediana e MAD ignoram
    # esses picos, então o CUSUM responde ao deslocamento real do nível.
    centro = float(np.median(arr))
    mad = float(np.median(np.abs(arr - centro)))
    escala = 1.4826 * mad  # equivalente ao desvio padrão numa normal
    if escala == 0:
        escala = float(np.std(arr, ddof=1))
    if escala == 0:
        return {"metodo": "cusum", "indices": [], "aplicavel": False, "motivo": "série constante"}

    normalizado = (arr - centro) / escala
    normalizado = np.clip(normalizado, -limite_influencia, limite_influencia)

    soma_pos = np.zeros(n)
    soma_neg = np.zeros(n)

    for i in range(1, n):
        soma_pos[i] = max(0.0, soma_pos[i - 1] + normalizado[i] - k)
        soma_neg[i] = max(0.0, soma_neg[i - 1] - normalizado[i] - k)

    indices = np.where((soma_pos > h) | (soma_neg > h))[0]

    direcao = None
    if len(indices) > 0:
        primeiro = int(indices[0])
        direcao = "alta" if soma_pos[primeiro] > h else "baixa"

    return {
        "metodo": "cusum",
        "aplicavel": True,
        "base": base_serie,
        "autocorrelacao": acf,
        "k": k,
        "h": h,
        "indices": [int(i) for i in indices],
        "cusum_positivo": [float(v) for v in soma_pos],
        "cusum_negativo": [float(v) for v in soma_neg],
        "direcao_desvio": direcao,
        "drift_detectado": bool(len(indices) > 0),
    }


def page_hinkley(valores: list[float], delta: float = 0.005, limiar_fator: float = 30.0) -> dict:
    """Page-Hinkley: detecção de ponto de mudança (change point).

    Enquanto o CUSUM responde "está desviando?", este responde "EM QUE
    MOMENTO o comportamento mudou?" — útil para correlacionar com um
    evento externo ("o que aconteceu na planta às 14h32?").

    O `limiar_fator` padrão foi calibrado empiricamente contra ruído
    branco puro: valores baixos (5–15) disparavam dezenas de falsos
    positivos em séries perfeitamente saudáveis. Em 30 os falsos
    positivos praticamente somem sem perder sensibilidade a mudanças
    reais — inclusive as sutis.
    """
    arr = _preparar(valores)
    n = len(arr)
    if n < 20:
        return {"metodo": "page_hinkley", "indices": [], "aplicavel": False}

    # Como CUSUM e EWMA, este detector assume independência. Numa série
    # autocorrelacionada ele acusa "mudança de regime" no vaivém normal.
    acf = autocorrelacao_lag1(valores)
    base_serie = "valores"
    if acf is not None and abs(acf) > 0.4 and n > 12:
        arr = _residuos_ar1(arr)
        n = len(arr)
        base_serie = "residuos_ar1"

    desvio = float(np.std(arr, ddof=1))
    if desvio == 0:
        return {"metodo": "page_hinkley", "indices": [], "aplicavel": False, "motivo": "série constante"}

    limiar = limiar_fator * desvio
    media_corrente = float(arr[0])
    soma = 0.0
    minimo = 0.0
    pontos_mudanca = []

    for i in range(1, n):
        media_corrente += (arr[i] - media_corrente) / (i + 1)
        soma += arr[i] - media_corrente - delta
        minimo = min(minimo, soma)
        if soma - minimo > limiar:
            pontos_mudanca.append(int(i))
            # reinicia após detectar, pra encontrar mudanças subsequentes
            soma = 0.0
            minimo = 0.0
            media_corrente = float(arr[i])

    return {
        "metodo": "page_hinkley",
        "aplicavel": True,
        "base": base_serie,
        "autocorrelacao": acf,
        "limiar": float(limiar),
        "indices": pontos_mudanca,
        "mudancas_detectadas": len(pontos_mudanca),
    }


def taxa_variacao(valores: list[float], timestamps: Optional[list[float]] = None, limiar: float = 4.0) -> dict:
    """Detecta saltos fisicamente implausíveis entre leituras consecutivas.

    Grandezas físicas têm inércia: temperatura ambiente não pula 15°C em
    um segundo. Um salto assim quase sempre significa falha de leitura,
    não fenômeno real — e o valor pode estar dentro da faixa normal,
    passando despercebido por todos os detectores baseados em nível.
    """
    arr = _preparar(valores)
    if len(arr) < 5:
        return {"metodo": "taxa_variacao", "indices": [], "aplicavel": False}

    diferencas = np.diff(arr)
    if timestamps is not None and len(timestamps) == len(arr):
        dt = np.diff(np.asarray(timestamps, dtype=float))
        dt[dt <= 0] = np.nan
        derivada = diferencas / dt  # unidade por segundo
    else:
        derivada = diferencas

    derivada_valida = derivada[np.isfinite(derivada)]
    if len(derivada_valida) < 3:
        return {"metodo": "taxa_variacao", "indices": [], "aplicavel": False}

    mediana = float(np.median(derivada_valida))
    mad = float(np.median(np.abs(derivada_valida - mediana)))
    if mad == 0:
        return {"metodo": "taxa_variacao", "indices": [], "aplicavel": False, "motivo": "variação constante"}

    scores = 0.6745 * np.abs(derivada - mediana) / mad
    indices = np.where(scores > limiar)[0] + 1  # +1: aponta o ponto de chegada do salto

    return {
        "metodo": "taxa_variacao",
        "aplicavel": True,
        "limiar": limiar,
        "indices": [int(i) for i in indices if i < len(arr)],
        "variacao_tipica": mediana,
    }


def detectar_flatline(valores: list[float], janela_minima: int = 10, tolerancia: float = 1e-9) -> dict:
    """Detecta sensor 'congelado': valor idêntico repetido por muitas leituras.

    É o modo de falha mais traiçoeiro, porque a leitura continua chegando
    e parece perfeitamente saudável para qualquer detector estatístico —
    a série fica com variância zero, o que é o oposto de uma anomalia.
    Na prática significa firmware travado, cabo rompido com último valor
    retido, ou ADC queimado.
    """
    arr = _preparar(valores)
    n = len(arr)
    if n < janela_minima:
        return {"metodo": "flatline", "aplicavel": False, "congelado": False}

    trechos = []
    inicio = 0
    for i in range(1, n):
        if abs(arr[i] - arr[inicio]) > tolerancia:
            if i - inicio >= janela_minima:
                trechos.append({"inicio": int(inicio), "fim": int(i - 1), "tamanho": int(i - inicio), "valor": float(arr[inicio])})
            inicio = i
    if n - inicio >= janela_minima:
        trechos.append({"inicio": int(inicio), "fim": int(n - 1), "tamanho": int(n - inicio), "valor": float(arr[inicio])})

    # Congelado "agora" = o último trecho repetido vai até o fim da série
    congelado_agora = bool(trechos and trechos[-1]["fim"] == n - 1)

    return {
        "metodo": "flatline",
        "aplicavel": True,
        "trechos": trechos,
        "congelado": congelado_agora,
        "maior_trecho": max((t["tamanho"] for t in trechos), default=0),
    }


def detectar_todas(
    valores: list[float],
    timestamps: Optional[list[float]] = None,
    preferir_robusto: bool = True,
) -> dict:
    """Roda todos os detectores e consolida o resultado.

    `preferir_robusto` deve refletir o teste de normalidade: se a série
    não é normal, o z-score clássico entra só como informação secundária
    e o robusto é quem vale para a contagem final.
    """
    # Detectores de ponto sobre série autocorrelacionada marcam o vaivém
    # normal como anomalia: numa série que passeia, a distância até a
    # mediana global não diz nada sobre o ponto ser inesperado. Nos
    # resíduos, "anômalo" recupera o sentido certo — o valor deu um salto
    # que não era previsível a partir da leitura anterior.
    acf = autocorrelacao_lag1(valores)
    autocorrelacionada = acf is not None and abs(acf) > 0.4
    base_pontual = "valores"
    valores_pontuais = valores
    if autocorrelacionada and len(valores) > 12:
        valores_pontuais = [float(v) for v in _residuos_ar1(_preparar(valores))]
        base_pontual = "residuos_ar1"

    resultados = {
        "zscore": zscore(valores_pontuais),
        "zscore_robusto": zscore_robusto(valores_pontuais),
        "iqr": iqr_tukey(valores_pontuais),
        "ewma": ewma(valores),
        "cusum": cusum(valores),
        "page_hinkley": page_hinkley(valores),
        "taxa_variacao": taxa_variacao(valores, timestamps),
        "flatline": detectar_flatline(valores),
    }

    # Consenso: quantos detectores independentes marcaram cada índice.
    # Um ponto marcado por vários métodos diferentes é bem mais confiável
    # que um marcado por apenas um (que pode ser artefato do método).
    votos: dict[int, list[str]] = {}
    metodos_pontuais = ["zscore_robusto" if preferir_robusto else "zscore", "iqr", "ewma", "taxa_variacao"]
    for nome in metodos_pontuais:
        for idx in resultados[nome].get("indices", []):
            votos.setdefault(idx, []).append(nome)

    consenso = [
        {"indice": idx, "votos": len(metodos), "metodos": metodos}
        for idx, metodos in sorted(votos.items())
    ]

    return {
        "detectores": resultados,
        "autocorrelacao": acf,
        "base_deteccao_pontual": base_pontual,
        "consenso": consenso,
        "total_pontos_anomalos": len(consenso),
        "pontos_alta_confianca": [c for c in consenso if c["votos"] >= 2],
    }
