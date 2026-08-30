"""
Estatística descritiva e ajuste de distribuições por sensor.

A ideia aqui é responder duas perguntas sobre a série de um sensor:
  1. Como esses dados se comportam? (média, dispersão, forma da distribuição)
  2. Qual modelo estatístico descreve melhor esses dados?

A segunda pergunta importa porque ela decide qual detector de anomalia
é válido: um limiar baseado em desvio padrão (z-score) pressupõe dados
aproximadamente normais. Se a série tem caudas pesadas (picos frequentes),
um modelo de Laplace com MAD é bem mais confiável — e é por isso que
testamos a normalidade antes de escolher o método, em vez de assumir.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from scipy import stats


def _limpar(valores: list[float]) -> np.ndarray:
    """Remove NaN/inf que podem vir de sensor com defeito."""
    arr = np.asarray(valores, dtype=float)
    return arr[np.isfinite(arr)]


def descritivas(valores: list[float]) -> dict:
    """Estatísticas básicas + medidas robustas (mediana/MAD/IQR).

    As medidas robustas existem porque média e desvio padrão são muito
    sensíveis a um único pico absurdo — comum em sensor com ruído elétrico.
    Mediana e MAD descrevem o comportamento "típico" mesmo com outliers.
    """
    arr = _limpar(valores)
    n = len(arr)
    if n == 0:
        return {"n": 0}

    q1, q2, q3 = np.percentile(arr, [25, 50, 75])
    mad = float(np.median(np.abs(arr - q2)))  # desvio absoluto mediano

    resultado = {
        "n": int(n),
        "media": float(np.mean(arr)),
        "mediana": float(q2),
        "desvio_padrao": float(np.std(arr, ddof=1)) if n > 1 else 0.0,
        "mad": mad,
        "minimo": float(np.min(arr)),
        "maximo": float(np.max(arr)),
        "amplitude": float(np.max(arr) - np.min(arr)),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(q3 - q1),
        "p05": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
    }

    # Coeficiente de variação: dispersão relativa à média. Útil pra comparar
    # a estabilidade de sensores com escalas diferentes (°C vs Pa).
    if resultado["media"] != 0:
        resultado["coef_variacao"] = abs(resultado["desvio_padrao"] / resultado["media"])

    # Assimetria e curtose não são definidas de forma estável quando a série
    # é (quase) constante — o scipy emite aviso de perda de precisão. Nesse
    # caso a resposta útil não é um número, é "não há variação para medir".
    serie_tem_variacao = resultado["desvio_padrao"] > 1e-10
    if n > 2 and serie_tem_variacao:
        resultado["assimetria"] = float(stats.skew(arr))
    if n > 3 and serie_tem_variacao:
        # Curtose alta = caudas pesadas = picos extremos mais frequentes
        # que o esperado numa normal. Sinal de que z-score vai falhar.
        resultado["curtose"] = float(stats.kurtosis(arr))
    if not serie_tem_variacao:
        resultado["serie_constante"] = True

    return resultado


def intervalo_confianca_t(valores: list[float], confianca: float = 0.95) -> Optional[dict]:
    """Intervalo de confiança da média usando distribuição t de Student.

    Usamos t em vez de normal porque, com amostras pequenas (poucas leituras)
    e desvio populacional desconhecido — que é sempre o caso aqui — a t tem
    caudas mais largas e dá um intervalo honestamente mais conservador.
    Com n grande a t converge pra normal de qualquer forma, então é seguro
    usar sempre.
    """
    arr = _limpar(valores)
    n = len(arr)
    if n < 2:
        return None

    media = float(np.mean(arr))
    erro_padrao = float(stats.sem(arr))
    graus_liberdade = n - 1
    margem = float(stats.t.ppf((1 + confianca) / 2, graus_liberdade) * erro_padrao)

    return {
        "media": media,
        "erro_padrao": erro_padrao,
        "graus_liberdade": graus_liberdade,
        "confianca": confianca,
        "limite_inferior": media - margem,
        "limite_superior": media + margem,
        "margem_erro": margem,
    }


def testar_normalidade(valores: list[float]) -> Optional[dict]:
    """Testa se a série segue distribuição normal.

    Isso não é curiosidade acadêmica: o resultado decide qual detector de
    anomalia usar. Se rejeitar normalidade, o z-score clássico produz
    falsos positivos (ou perde anomalias reais) e o método robusto de
    Laplace/MAD passa a ser o correto.
    """
    arr = _limpar(valores)
    n = len(arr)
    if n < 8:
        return None  # testes de normalidade não são confiáveis com amostra minúscula

    resultado: dict = {"n": int(n)}

    # Shapiro-Wilk é o mais potente para n moderado, mas satura acima de ~5000
    if n <= 5000:
        estatistica, p_valor = stats.shapiro(arr)
        resultado["shapiro"] = {"estatistica": float(estatistica), "p_valor": float(p_valor)}

    # D'Agostino-Pearson combina assimetria e curtose; funciona bem com n grande
    if n >= 20:
        estatistica, p_valor = stats.normaltest(arr)
        resultado["dagostino"] = {"estatistica": float(estatistica), "p_valor": float(p_valor)}

    # Decide pelo teste disponível mais apropriado
    p_referencia = (
        resultado.get("shapiro", {}).get("p_valor")
        or resultado.get("dagostino", {}).get("p_valor")
    )
    if p_referencia is not None:
        resultado["p_valor"] = float(p_referencia)
        resultado["parece_normal"] = bool(p_referencia > 0.05)

    return resultado


def ajustar_distribuicoes(valores: list[float]) -> Optional[dict]:
    """Compara o ajuste de Normal vs Laplace vs Cauchy nos dados.

    Normal  -> comportamento bem-comportado, ruído gaussiano típico.
    Laplace -> caudas mais pesadas: picos ocasionais são normais pro sensor.
    Cauchy  -> caudas MUITO pesadas: sinal de instrumentação instável.

    A escolha usa o teste de Kolmogorov-Smirnov (quão longe a distribuição
    teórica está da empírica) e o AIC (penaliza complexidade), e o vencedor
    define qual modelo de anomalia é o mais defensável para aquele sensor.
    """
    arr = _limpar(valores)
    n = len(arr)
    if n < 10:
        return None

    candidatas = {
        "normal": stats.norm,
        "laplace": stats.laplace,
        "cauchy": stats.cauchy,
    }

    ajustes = {}
    falhas = {}
    for nome, dist in candidatas.items():
        try:
            parametros = dist.fit(arr)
            congelada = dist(*parametros)
            # Passamos a CDF já parametrizada em vez do nome da distribuição:
            # passar o nome faz o scipy montar a chamada de forma incompatível
            # com algumas distribuições (a normal, entre elas).
            ks_stat, ks_p = stats.kstest(arr, congelada.cdf)
            log_verossimilhanca = float(np.sum(dist.logpdf(arr, *parametros)))
            k = len(parametros)
            aic = 2 * k - 2 * log_verossimilhanca
            ajustes[nome] = {
                "parametros": [float(p) for p in parametros],
                "ks_estatistica": float(ks_stat),
                "ks_p_valor": float(ks_p),
                "log_verossimilhanca": log_verossimilhanca,
                "aic": float(aic),
            }
        except Exception as exc:
            falhas[nome] = str(exc)

    if not ajustes:
        return None

    melhor = min(ajustes, key=lambda nome: ajustes[nome]["aic"])

    # O AIC sempre elege uma vencedora, mesmo que TODAS sejam ruins — ele
    # compara as candidatas entre si, não afere se alguma descreve os dados.
    # Quem responde isso é o teste de aderência (KS). Se ele rejeita todas,
    # anunciar "dados bem-comportados" seria contradizer o próprio teste de
    # normalidade exibido ao lado.
    alguma_adere = any(a["ks_p_valor"] > 0.05 for a in ajustes.values())
    if alguma_adere:
        interpretacao = _interpretar_ajuste(melhor)
    else:
        interpretacao = (
            "Nenhuma das distribuições testadas descreve bem os dados (todas rejeitadas pelo teste de "
            f"Kolmogorov-Smirnov). O ajuste de menor AIC foi '{melhor}', mas isso indica apenas a menos "
            "ruim entre as candidatas. Em séries de sensor isso é comum e costuma significar que o valor "
            "não vem de uma distribuição fixa: ele passeia ao longo do tempo. Por isso a detecção de "
            "anomalias usa o método robusto e trabalha sobre os resíduos, não sobre os valores brutos."
        )

    resultado = {
        "ajustes": ajustes,
        "melhor_ajuste": melhor,
        "alguma_distribuicao_adere": alguma_adere,
        "interpretacao": interpretacao,
    }
    if falhas:
        resultado["falhas"] = falhas
    return resultado


def _interpretar_ajuste(melhor: str) -> str:
    return {
        "normal": "Dados bem-comportados: ruído próximo do gaussiano. Limiares por desvio padrão são confiáveis.",
        "laplace": "Caudas mais pesadas que a normal: picos ocasionais fazem parte do comportamento do sensor. Detecção robusta (MAD) é mais adequada.",
        "cauchy": "Caudas muito pesadas: leituras extremas são frequentes. Verifique ruído elétrico, aterramento ou instabilidade na alimentação do sensor.",
    }.get(melhor, "")


def comparar_periodos(anteriores: list[float], recentes: list[float]) -> Optional[dict]:
    """Compara duas janelas da mesma série pra detectar mudança de regime.

    Usa três testes complementares:
      - t de Student (Welch): a MÉDIA mudou?
      - Levene: a VARIABILIDADE mudou? (sensor ficou mais ruidoso)
      - Mann-Whitney: mudança na distribuição, sem supor normalidade

    Mudança de média sugere drift/descalibração; mudança de variância
    sugere sensor degradando ou interferência nova.
    """
    a = _limpar(anteriores)
    b = _limpar(recentes)
    if len(a) < 8 or len(b) < 8:
        return None

    resultado: dict = {
        "n_anterior": int(len(a)),
        "n_recente": int(len(b)),
        "media_anterior": float(np.mean(a)),
        "media_recente": float(np.mean(b)),
        "desvio_anterior": float(np.std(a, ddof=1)),
        "desvio_recente": float(np.std(b, ddof=1)),
    }
    resultado["variacao_media"] = resultado["media_recente"] - resultado["media_anterior"]

    # Welch: não assume variâncias iguais entre as janelas
    t_stat, t_p = stats.ttest_ind(b, a, equal_var=False)
    resultado["t_student"] = {
        "estatistica": float(t_stat),
        "p_valor": float(t_p),
        "media_mudou": bool(t_p < 0.05),
    }

    lev_stat, lev_p = stats.levene(a, b)
    resultado["levene"] = {
        "estatistica": float(lev_stat),
        "p_valor": float(lev_p),
        "variancia_mudou": bool(lev_p < 0.05),
    }

    try:
        u_stat, u_p = stats.mannwhitneyu(b, a, alternative="two-sided")
        resultado["mann_whitney"] = {
            "estatistica": float(u_stat),
            "p_valor": float(u_p),
            "distribuicao_mudou": bool(u_p < 0.05),
        }
    except ValueError:
        pass

    # Cohen's d: tamanho do efeito. p-valor diz "mudou?", d diz "mudou quanto?".
    # Com muitos pontos, diferenças irrelevantes viram "significativas" — o d evita
    # alarmar por uma mudança estatisticamente detectável mas fisicamente irrelevante.
    n_a, n_b = len(a), len(b)
    var_combinada = ((n_a - 1) * np.var(a, ddof=1) + (n_b - 1) * np.var(b, ddof=1)) / (n_a + n_b - 2)
    desvio_combinado = math.sqrt(var_combinada) if var_combinada > 0 else 0.0
    if desvio_combinado > 0:
        d = float((np.mean(b) - np.mean(a)) / desvio_combinado)
        resultado["cohen_d"] = d
        resultado["magnitude_efeito"] = (
            "desprezível" if abs(d) < 0.2 else
            "pequena" if abs(d) < 0.5 else
            "moderada" if abs(d) < 0.8 else
            "grande"
        )

    return resultado


def analisar_taxa_chegada(timestamps: list[float], intervalo_esperado_s: Optional[float] = None) -> Optional[dict]:
    """Modela a chegada de leituras como processo de Poisson.

    Poisson não se aplica ao VALOR lido (temperatura não é contagem), mas
    se aplica perfeitamente à CONTAGEM de leituras por intervalo de tempo.
    Isso detecta um modo de falha que nenhuma análise do valor detecta:
    o sensor está online mas entregando menos leituras que deveria —
    perda de pacotes, rede instável, ou firmware travando.
    """
    if len(timestamps) < 3:
        return None

    ts = np.sort(np.asarray(timestamps, dtype=float))
    duracao = float(ts[-1] - ts[0])
    if duracao <= 0:
        return None

    n = len(ts)
    intervalos = np.diff(ts)
    taxa_observada = n / duracao  # leituras por segundo

    resultado = {
        "n_leituras": int(n),
        "duracao_segundos": duracao,
        "taxa_por_minuto": float(taxa_observada * 60),
        "intervalo_medio_s": float(np.mean(intervalos)),
        "intervalo_mediano_s": float(np.median(intervalos)),
        "intervalo_maximo_s": float(np.max(intervalos)),
    }

    # Índice de dispersão: variância/média dos intervalos.
    # ≈1 indica processo Poisson puro (chegadas aleatórias);
    # ≫1 indica rajadas e silêncios — típico de conexão instável.
    #
    # Calculado sobre os intervalos com os extremos aparados: um único
    # silêncio longo (reinício do gateway, manutenção, queda momentânea)
    # infla a variância o bastante para acusar "conexão instável" numa
    # série que entregou 96% das leituras com mediana exata no intervalo
    # configurado. Interrupção pontual e instabilidade crônica são
    # problemas diferentes, e só a segunda deve disparar esse alerta.
    media_int = float(np.mean(intervalos))
    if media_int > 0 and len(intervalos) >= 10:
        # "Silêncio anormal" é um intervalo muitas vezes maior que o típico,
        # não simplesmente o 1% maior — aparar por percentil removeria
        # intervalos perfeitamente normais e inflaria a contagem de
        # interrupções (13 "eventos" onde houve um único reinício).
        mediana_int = float(np.median(intervalos))
        limite = max(5.0 * mediana_int, mediana_int + 1e-9)
        centrais = intervalos[intervalos <= limite]
        n_interrupcoes = int(len(intervalos) - len(centrais))

        if len(centrais) >= 5:
            media_central = float(np.mean(centrais))
            indice_dispersao = float(np.var(centrais) / media_central) if media_central > 0 else 0.0
        else:
            indice_dispersao = float(np.var(intervalos) / media_int)
            n_interrupcoes = 0

        resultado["indice_dispersao"] = indice_dispersao
        resultado["chegada_regular"] = bool(indice_dispersao < 1.5)
        # As interrupções não somem do diagnóstico: viram um sinal próprio,
        # com significado distinto de irregularidade crônica.
        if n_interrupcoes:
            resultado["interrupcoes_pontuais"] = n_interrupcoes
            resultado["limite_silencio_s"] = float(limite)
    elif media_int > 0:
        indice_dispersao = float(np.var(intervalos) / media_int)
        resultado["indice_dispersao"] = indice_dispersao
        resultado["chegada_regular"] = bool(indice_dispersao < 1.5)

    if intervalo_esperado_s and intervalo_esperado_s > 0:
        esperadas = duracao / intervalo_esperado_s
        resultado["leituras_esperadas"] = float(esperadas)
        resultado["taxa_entrega"] = float(min(n / esperadas, 1.0)) if esperadas > 0 else None

        # Teste de Poisson: observar tão poucas leituras seria plausível por acaso?
        if esperadas >= 1:
            p_cauda = float(stats.poisson.cdf(n, esperadas))
            resultado["poisson_p_valor"] = p_cauda
            # p muito baixo = déficit de leituras grande demais pra ser aleatório
            resultado["perda_significativa"] = bool(p_cauda < 0.01)

    return resultado
