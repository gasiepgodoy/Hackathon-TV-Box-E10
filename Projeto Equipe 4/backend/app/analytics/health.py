"""
Avaliação de saúde do sensor.

Junta os sinais dos módulos de estatística e anomalia num diagnóstico
único e acionável. A pontuação começa em 100 e cada problema encontrado
desconta pontos proporcionalmente à gravidade.

Importante sobre o que isso é e o que não é: este é um sistema baseado
em regras estatísticas, não um modelo preditivo treinado. Ele descreve
com rigor o estado ATUAL e recente do sensor (drift, ruído, entrega,
travamento) e sinaliza tendências. Ele não prevê data de falha futura —
isso exigiria histórico de falhas reais rotulado, que um gateway novo
não tem. Prometer previsão de falha aqui seria vender o que o método
não entrega.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from . import anomalies, statistics as stats_mod


# Pesos de desconto por tipo de problema (soma máxima limitada a 100)
PESOS = {
    "congelado": 45,
    "sem_dados": 50,
    "perda_leituras": 25,
    "drift": 20,
    "mudanca_regime": 15,
    "ruido_alto": 15,
    "anomalias_frequentes": 20,
    "chegada_irregular": 10,
    "cauda_pesada": 8,
}


def avaliar(
    valores: list[float],
    timestamps: list[float],
    intervalo_esperado_s: Optional[float] = None,
    janela_comparacao: float = 0.5,
) -> dict:
    """Produz o diagnóstico completo de saúde de um sensor.

    `janela_comparacao` = fração da série usada como "linha de base"
    para comparar com o período recente (0.5 = metade/metade).
    """
    n = len(valores)
    if n == 0:
        return {
            "pontuacao": 0,
            "estado": "sem_dados",
            "problemas": [{"tipo": "sem_dados", "gravidade": "critica",
                           "mensagem": "Nenhuma leitura recebida no período analisado."}],
            "recomendacoes": ["Verifique se o sensor está ativo e se a conexão com o gateway está funcionando."],
        }

    problemas: list[dict] = []
    desconto = 0

    # --- Sensor congelado -------------------------------------------------
    flat = anomalies.detectar_flatline(valores)
    if flat.get("congelado"):
        desconto += PESOS["congelado"]
        problemas.append({
            "tipo": "congelado",
            "gravidade": "critica",
            "mensagem": f"O sensor está reportando o mesmo valor há {flat['maior_trecho']} leituras consecutivas.",
            "detalhe": "Leituras continuam chegando, mas o valor não muda — sugere firmware travado, cabo rompido com valor retido, ou conversor A/D com defeito.",
        })

    # --- Entrega de leituras (Poisson) ------------------------------------
    chegada = stats_mod.analisar_taxa_chegada(timestamps, intervalo_esperado_s)
    if chegada:
        if chegada.get("perda_significativa"):
            desconto += PESOS["perda_leituras"]
            taxa = chegada.get("taxa_entrega")
            pct = f"{taxa * 100:.0f}%" if taxa is not None else "abaixo do esperado"
            problemas.append({
                "tipo": "perda_leituras",
                "gravidade": "alta",
                "mensagem": f"Taxa de entrega em {pct} do esperado.",
                "detalhe": "O déficit de leituras é grande demais para ser variação aleatória. Verifique estabilidade da rede, alimentação ou intervalo configurado.",
            })
        elif chegada.get("chegada_regular") is False:
            desconto += PESOS["chegada_irregular"]
            problemas.append({
                "tipo": "chegada_irregular",
                "gravidade": "media",
                "mensagem": "As leituras chegam em rajadas, não em intervalos regulares.",
                "detalhe": f"Maior silêncio observado: {chegada['intervalo_maximo_s']:.0f}s (mediana {chegada['intervalo_mediano_s']:.1f}s).",
            })

    # --- Drift e mudança de regime ----------------------------------------
    if n >= 30:
        # Usamos o teste de drift dedicado, não o CUSUM: em séries
        # autocorrelacionadas (o normal em sensores físicos) o CUSUM cru
        # acusa desvio em praticamente toda série saudável.
        drift = anomalies.testar_drift(valores)
        if drift.get("drift_detectado"):
            desconto += PESOS["drift"]
            direcao = drift.get("direcao", "")
            variacao = drift.get("variacao_por_leitura", 0.0)
            problemas.append({
                "tipo": "drift",
                "gravidade": "alta",
                "mensagem": f"Desvio sustentado da média detectado (tendência de {direcao}).",
                "detalhe": (
                    f"Variação estimada de {variacao:+.5f} por leitura (p={drift['p_valor']:.4f}). "
                    "O valor migrou consistentemente numa direção em vez de oscilar em torno da média — "
                    "padrão típico de perda de calibração."
                ),
            })

        ph = anomalies.page_hinkley(valores)
        if ph.get("mudancas_detectadas", 0) > 0:
            desconto += PESOS["mudanca_regime"]
            problemas.append({
                "tipo": "mudanca_regime",
                "gravidade": "media",
                "mensagem": f"{ph['mudancas_detectadas']} mudança(s) abrupta(s) de comportamento no período.",
                "detalhe": "Houve quebras no padrão da série. Vale correlacionar com eventos externos (manutenção, troca de turno, mudança de processo).",
            })

    # --- Comparação entre janelas -----------------------------------------
    # Numa série com raiz unitária (que passeia sem média fixa), a média
    # das duas metades difere por construção, não por falha do sensor.
    # Só interpretamos essa comparação como problema quando a série tem
    # média estável para comparar.
    drift_info = anomalies.testar_drift(valores) if n >= 30 else {}
    serie_estavel = not drift_info.get("serie_com_raiz_unitaria", False)

    comparacao = None
    if n >= 20 and serie_estavel:
        corte = int(n * janela_comparacao)
        comparacao = stats_mod.comparar_periodos(valores[:corte], valores[corte:])
        if comparacao:
            levene = comparacao.get("levene", {})
            magnitude = comparacao.get("magnitude_efeito")
            if levene.get("variancia_mudou") and comparacao["desvio_recente"] > comparacao["desvio_anterior"] * 1.5:
                desconto += PESOS["ruido_alto"]
                problemas.append({
                    "tipo": "ruido_alto",
                    "gravidade": "media",
                    "mensagem": "O sensor ficou significativamente mais ruidoso no período recente.",
                    "detalhe": f"Desvio padrão subiu de {comparacao['desvio_anterior']:.3f} para {comparacao['desvio_recente']:.3f}.",
                })
            # Só alarma mudança de média se ela também for grande na prática,
            # não apenas estatisticamente detectável
            if comparacao.get("t_student", {}).get("media_mudou") and magnitude in ("moderada", "grande"):
                problemas.append({
                    "tipo": "mudanca_media",
                    "gravidade": "media",
                    "mensagem": f"A média mudou {comparacao['variacao_media']:+.3f} entre o início e o fim do período (efeito de magnitude {magnitude}).",
                })

    # --- Anomalias pontuais -----------------------------------------------
    normalidade = stats_mod.testar_normalidade(valores)
    preferir_robusto = not (normalidade or {}).get("parece_normal", False)
    deteccao = anomalies.detectar_todas(valores, timestamps, preferir_robusto=preferir_robusto)

    alta_confianca = deteccao["pontos_alta_confianca"]
    proporcao = len(alta_confianca) / n if n else 0
    if proporcao > 0.05:
        desconto += PESOS["anomalias_frequentes"]
        problemas.append({
            "tipo": "anomalias_frequentes",
            "gravidade": "alta",
            "mensagem": f"{len(alta_confianca)} pontos anômalos ({proporcao * 100:.1f}% das leituras) confirmados por múltiplos métodos.",
            "detalhe": "Proporção alta demais para ruído normal. Verifique interferência elétrica, aterramento ou fixação do sensor.",
        })
    elif len(alta_confianca) > 0:
        problemas.append({
            "tipo": "anomalias_pontuais",
            "gravidade": "baixa",
            "mensagem": f"{len(alta_confianca)} ponto(s) anômalo(s) isolado(s) detectado(s).",
        })

    # --- Forma da distribuição --------------------------------------------
    # Ajustar uma distribuição fixa a uma série que passeia não faz
    # sentido: os valores não vêm de uma distribuição estável, então o
    # "melhor ajuste" descreve o passeio, não o comportamento do sensor.
    ajuste = stats_mod.ajustar_distribuicoes(valores)
    if ajuste and ajuste.get("aplicavel") is False:
        pass  # série constante: o problema já é reportado como "congelado"
    elif ajuste and not serie_estavel:
        ajuste = {**ajuste, "observacao": "A série não tem média estável; o ajuste descreve o passeio da série, não o ruído do sensor."}
    if (ajuste and ajuste.get("aplicavel") is not False and serie_estavel and ajuste.get("alguma_distribuicao_adere")
            and ajuste["melhor_ajuste"] == "cauchy"):
        desconto += PESOS["cauda_pesada"]
        problemas.append({
            "tipo": "cauda_pesada",
            "gravidade": "media",
            "mensagem": "A distribuição dos valores tem caudas muito pesadas (melhor ajuste: Cauchy).",
            "detalhe": "Leituras extremas ocorrem com frequência anormal — sinal de instrumentação instável.",
        })

    pontuacao = max(0, 100 - desconto)
    estado = (
        "saudavel" if pontuacao >= 85 else
        "atencao" if pontuacao >= 60 else
        "degradado" if pontuacao >= 35 else
        "critico"
    )

    return {
        "pontuacao": int(pontuacao),
        "estado": estado,
        "n_leituras": n,
        "problemas": problemas,
        "recomendacoes": _recomendar(problemas),
        "resumo_deteccao": {
            "total_anomalias": deteccao["total_pontos_anomalos"],
            "alta_confianca": len(alta_confianca),
            "metodo_principal": "zscore_robusto" if preferir_robusto else "zscore",
        },
        "distribuicao": ajuste,
        "normalidade": normalidade,
        "chegada": chegada,
        "comparacao_periodos": comparacao,
    }


def _recomendar(problemas: list[dict]) -> list[str]:
    """Traduz cada problema detectado numa ação concreta."""
    acoes = {
        "congelado": "Reinicie o sensor e verifique o cabeamento. Se o valor voltar a variar, investigue travamento de firmware.",
        "sem_dados": "Verifique se o sensor está ativo no cadastro e se o gateway consegue alcançá-lo na rede.",
        "perda_leituras": "Verifique a estabilidade da rede/alimentação e confirme se o intervalo configurado corresponde ao que o sensor realmente entrega.",
        "drift": "Agende recalibração. Compare com um sensor de referência no mesmo ponto antes de ajustar.",
        "mudanca_regime": "Correlacione o horário da mudança com eventos de manutenção ou alterações no processo.",
        "ruido_alto": "Verifique aterramento, blindagem do cabo e proximidade de fontes de interferência (motores, inversores).",
        "anomalias_frequentes": "Inspecione a fixação física do sensor e a qualidade da alimentação.",
        "chegada_irregular": "Avalie a qualidade do sinal (Wi-Fi/rede) entre o sensor e o gateway.",
        "cauda_pesada": "Investigue a fonte de alimentação e a integridade do circuito de medição.",
    }
    vistos = []
    for p in problemas:
        acao = acoes.get(p["tipo"])
        if acao and acao not in vistos:
            vistos.append(acao)
    return vistos
