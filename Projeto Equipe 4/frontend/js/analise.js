/*
 * Página de análise por sensor: estatística descritiva, forma da
 * distribuição, detecção de anomalias e diagnóstico de saúde.
 */
let sensores = [];
let sensorSelecionado = '';
let rangeAtual = '-24h';
let grafico = null;
// Quando o usuário seleciona um trecho (por arrasto ou pelas datas), a
// análise passa a usar esse recorte em vez do período dos atalhos.
let recorte = null;   // { inicio: Date, fim: Date }

const elSelect = document.getElementById('select-sensor');
const elConteudo = document.getElementById('conteudo-analise');
const elVazio = document.getElementById('estado-vazio');
const elChipRow = document.getElementById('chip-row');

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}

function num(v, casas = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

async function carregarSensores() {
  try {
    sensores = await api('/api/sensores');
  } catch (e) {
    mostrarToast('Não consegui carregar os sensores: ' + e.message, 'error');
    return;
  }
  elSelect.innerHTML = '<option value="">Selecione um sensor…</option>' +
    sensores.map(s => `<option value="${s.id}">${esc(s.nome)} (${esc(s.tipo)})</option>`).join('');
}

elSelect.addEventListener('change', () => {
  sensorSelecionado = elSelect.value;
  if (sensorSelecionado) carregarAnalise();
  else { elConteudo.style.display = 'none'; elVazio.style.display = 'block'; }
});

const elCampoInicio = document.getElementById('campo-inicio');
const elCampoFim = document.getElementById('campo-fim');
const elInputInicio = document.getElementById('input-inicio');
const elInputFim = document.getElementById('input-fim');
const elBtnAplicar = document.getElementById('btn-aplicar-periodo');
const elBtnLimpar = document.getElementById('btn-limpar-selecao');
const elDica = document.getElementById('dica-selecao');

elChipRow.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    elChipRow.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    rangeAtual = chip.dataset.range;
    const personalizado = rangeAtual === 'custom';
    elCampoInicio.style.display = personalizado ? 'flex' : 'none';
    elCampoFim.style.display = personalizado ? 'flex' : 'none';
    elBtnAplicar.style.display = personalizado ? 'inline-flex' : 'none';
    // Trocar de atalho descarta o recorte: manter os dois ativos ao mesmo
    // tempo produziria um período ambíguo.
    limparRecorte(false);
    if (!personalizado && sensorSelecionado) carregarAnalise();
  });
});

elBtnAplicar.addEventListener('click', () => {
  if (!elInputInicio.value || !elInputFim.value) {
    mostrarToast('Preencha as duas datas do período.', 'error');
    return;
  }
  const ini = new Date(elInputInicio.value);
  const fim = new Date(elInputFim.value);
  if (fim <= ini) {
    mostrarToast('A data final precisa ser depois da inicial.', 'error');
    return;
  }
  recorte = { inicio: ini, fim: fim };
  atualizarDica();
  if (sensorSelecionado) carregarAnalise();
});

elBtnLimpar.addEventListener('click', () => limparRecorte(true));

function limparRecorte(recarregar) {
  recorte = null;
  const ret = document.querySelector('.selecao-retangulo');
  if (ret) ret.remove();
  elBtnLimpar.style.display = 'none';
  atualizarDica();
  if (recarregar && sensorSelecionado) carregarAnalise();
}

function atualizarDica() {
  if (recorte) {
    elDica.textContent = `Trecho: ${formatarHora(recorte.inicio.getTime() / 1000)} → ${formatarHora(recorte.fim.getTime() / 1000)}`;
    elDica.classList.add('ativa');
    elBtnLimpar.style.display = 'inline-flex';
  } else {
    elDica.textContent = 'Arraste sobre o gráfico para analisar um trecho';
    elDica.classList.remove('ativa');
  }
}

/** Monta os parâmetros de período: o recorte tem prioridade sobre o atalho. */
function paramsPeriodo() {
  const p = new URLSearchParams();
  if (recorte) {
    p.set('inicio', recorte.inicio.toISOString());
    p.set('fim', recorte.fim.toISOString());
  } else {
    p.set('inicio', rangeAtual);
  }
  return p;
}

async function carregarAnalise() {
  let dado;
  try {
    dado = await api(`/api/analise/${sensorSelecionado}?${paramsPeriodo().toString()}`);
  } catch (e) {
    mostrarToast('Não consegui carregar a análise: ' + e.message, 'error');
    return;
  }

  elVazio.style.display = 'none';
  elConteudo.style.display = 'block';

  renderSaude(dado);
  renderDescritivas(dado);
  renderDistribuicao(dado);
  renderEntrega(dado);
  renderAnomalias(dado);
  renderGrafico(dado);
}

/* ---------- Saúde ---------- */

const CORES_ESTADO = {
  saudavel: '#35D6A8', atencao: '#F2A93C',
  degradado: '#E88B3C', critico: '#E5565A', sem_dados: '#8B93A3',
};

const ROTULOS_ESTADO = {
  saudavel: 'Saudável', atencao: 'Atenção',
  degradado: 'Degradado', critico: 'Crítico', sem_dados: 'Sem dados',
};

function renderSaude(dado) {
  const s = dado.saude || {};
  const cor = CORES_ESTADO[s.estado] || '#8B93A3';
  const el = document.getElementById('bloco-saude');

  const problemas = (s.problemas || []).map(p => `
    <div class="problema grav-${esc(p.gravidade || 'baixa')}">
      <div class="problema-titulo">${esc(p.mensagem)}</div>
      ${p.detalhe ? `<div class="problema-detalhe">${esc(p.detalhe)}</div>` : ''}
    </div>`).join('');

  const recomendacoes = (s.recomendacoes || []).map(r => `<li>${esc(r)}</li>`).join('');

  const avisoRecorte = recorte
    ? `<div class="faixa-selecionada">Analisando o trecho selecionado:
         <strong>${formatarHora(recorte.inicio.getTime() / 1000)}</strong> até
         <strong>${formatarHora(recorte.fim.getTime() / 1000)}</strong></div>`
    : '';

  el.innerHTML = `
    ${avisoRecorte}
    <div class="saude-topo">
      <div class="saude-medidor">
        <div class="saude-valor" style="color:${cor}">${s.pontuacao ?? '—'}</div>
        <div class="saude-escala">/ 100</div>
      </div>
      <div class="saude-info">
        <div class="saude-estado" style="color:${cor}">${ROTULOS_ESTADO[s.estado] || s.estado || '—'}</div>
        <div class="saude-sub">${dado.n_leituras} leitura(s) no período analisado</div>
        <div class="barra-saude"><div class="barra-preenchida" style="width:${s.pontuacao || 0}%;background:${cor}"></div></div>
      </div>
    </div>
    ${problemas ? `<div class="lista-problemas">${problemas}</div>` : '<div class="sem-problemas">Nenhum problema detectado no período.</div>'}
    ${recomendacoes ? `<div class="recomendacoes"><div class="recomendacoes-titulo">Ações recomendadas</div><ul>${recomendacoes}</ul></div>` : ''}
  `;
}

/* ---------- Descritivas ---------- */

function renderDescritivas(dado) {
  const d = dado.descritivas || {};
  const ic = dado.intervalo_confianca;
  const u = dado.sensor?.unidade ? ` ${dado.sensor.unidade}` : '';

  const metricas = [
    ['Média', num(d.media) + u],
    ['Mediana', num(d.mediana) + u],
    ['Desvio padrão', num(d.desvio_padrao, 3)],
    ['MAD (robusto)', num(d.mad, 3)],
    ['Mínimo', num(d.minimo) + u],
    ['Máximo', num(d.maximo) + u],
    ['Amplitude', num(d.amplitude, 3)],
    ['IQR', num(d.iqr, 3)],
    ['P5 – P95', `${num(d.p05)} – ${num(d.p95)}`],
    ['Coef. variação', d.coef_variacao !== undefined ? (d.coef_variacao * 100).toFixed(1) + '%' : '—'],
    ['Assimetria', num(d.assimetria, 3)],
    ['Curtose', num(d.curtose, 3)],
  ];

  document.getElementById('bloco-descritivas').innerHTML = `
    <div class="metricas-grid">
      ${metricas.map(([k, v]) => `<div class="metrica"><div class="metrica-rotulo">${k}</div><div class="metrica-valor">${v}</div></div>`).join('')}
    </div>
    ${ic ? `<div class="nota-ic">Intervalo de confiança de 95% para a média (t de Student, ${ic.graus_liberdade} g.l.):
      <strong>${num(ic.limite_inferior, 3)} – ${num(ic.limite_superior, 3)}</strong>${u}</div>` : ''}
  `;
}

/* ---------- Distribuição ---------- */

function renderDistribuicao(dado) {
  const dist = dado.distribuicao;
  const norm = dado.normalidade;
  const el = document.getElementById('bloco-distribuicao');

  if (!dist) {
    el.innerHTML = '<div class="empty-state">Dados insuficientes para ajustar uma distribuição (mínimo 10 leituras).</div>';
    return;
  }

  const adere = dist.alguma_distribuicao_adere !== false;
  const linhas = Object.entries(dist.ajustes).map(([nome, info]) => `
    <tr class="${nome === dist.melhor_ajuste && adere ? 'linha-vencedora' : ''}">
      <td>${nome === dist.melhor_ajuste ? `<span class="marca-vencedor" style="color:${adere ? 'var(--accent)' : 'var(--text-faint)'}">●</span> ` : ''}${esc(nome)}</td>
      <td class="mono">${num(info.aic, 1)}</td>
      <td class="mono">${num(info.ks_estatistica, 4)}</td>
      <td class="mono">${num(info.ks_p_valor, 4)}</td>
    </tr>`).join('');

  el.innerHTML = `
    <table class="tabela-dist">
      <thead><tr><th>Distribuição</th><th>AIC</th><th>KS</th><th>p-valor</th></tr></thead>
      <tbody>${linhas}</tbody>
    </table>
    <div class="interpretacao">${esc(dist.interpretacao || '')}</div>
    ${norm && norm.p_valor !== undefined ? `
      <div class="nota-normalidade">
        Teste de normalidade: p = <strong>${num(norm.p_valor, 4)}</strong> —
        ${norm.parece_normal
          ? 'compatível com distribuição normal, limiares por desvio padrão são válidos.'
          : 'incompatível com normal, por isso a detecção usa o método robusto (mediana/MAD).'}
      </div>` : ''}
  `;
}

/* ---------- Entrega de leituras ---------- */

function renderEntrega(dado) {
  const c = dado.taxa_chegada;
  const el = document.getElementById('bloco-entrega');
  if (!c) {
    el.innerHTML = '<div class="empty-state">Leituras insuficientes para analisar a regularidade de entrega.</div>';
    return;
  }

  const metricas = [
    ['Leituras', c.n_leituras],
    ['Taxa', num(c.taxa_por_minuto, 1) + ' /min'],
    ['Intervalo mediano', num(c.intervalo_mediano_s, 1) + ' s'],
    ['Maior silêncio', num(c.intervalo_maximo_s, 1) + ' s'],
  ];
  if (c.taxa_entrega !== undefined && c.taxa_entrega !== null) {
    metricas.push(['Entrega', (c.taxa_entrega * 100).toFixed(0) + '%']);
  }
  if (c.indice_dispersao !== undefined) {
    metricas.push(['Índice dispersão', num(c.indice_dispersao, 2)]);
  }
  if (c.interrupcoes_pontuais) {
    metricas.push(['Interrupções', c.interrupcoes_pontuais]);
  }

  el.innerHTML = `
    <div class="metricas-grid">
      ${metricas.map(([k, v]) => `<div class="metrica"><div class="metrica-rotulo">${k}</div><div class="metrica-valor">${v}</div></div>`).join('')}
    </div>
    <div class="interpretacao">
      ${c.chegada_regular === false
        ? 'As leituras chegam em rajadas em vez de intervalos regulares — índice de dispersão acima de 1,5 indica conexão instável.'
        : 'Chegada regular: o intervalo entre leituras é consistente (modelo de Poisson).'}
      ${c.interrupcoes_pontuais
        ? ` Foram observadas ${c.interrupcoes_pontuais} interrupção(ões) pontual(is) (silêncio acima de ${num(c.limite_silencio_s, 1)}s), contadas à parte: uma parada isolada — reinício, manutenção — não caracteriza conexão instável.`
        : ''}
    </div>`;
}

/* ---------- Anomalias ---------- */

const ROTULOS_METODO = {
  zscore: 'Z-score (normal)',
  zscore_robusto: 'Z-score robusto (MAD/Laplace)',
  iqr: 'Cercas de Tukey (IQR)',
  ewma: 'Carta EWMA',
  cusum: 'CUSUM (desvio sustentado)',
  page_hinkley: 'Page-Hinkley (ponto de mudança)',
  taxa_variacao: 'Taxa de variação',
  flatline: 'Sensor congelado',
};

function renderAnomalias(dado) {
  const a = dado.anomalias || {};
  const linhas = Object.entries(a.resumo_por_metodo || {}).map(([nome, info]) => `
    <tr>
      <td>${esc(ROTULOS_METODO[nome] || nome)}</td>
      <td class="mono">${info.aplicavel ? info.encontrados : '—'}</td>
      <td class="mono ${info.aplicavel ? 'ok' : 'inativo'}">${info.aplicavel ? 'aplicado' : (info.motivo || 'dados insuficientes')}</td>
    </tr>`).join('');

  document.getElementById('bloco-anomalias').innerHTML = `
    <div class="resumo-anomalias">
      <div class="metrica"><div class="metrica-rotulo">Pontos marcados</div><div class="metrica-valor">${a.total ?? 0}</div></div>
      <div class="metrica"><div class="metrica-rotulo">Alta confiança</div><div class="metrica-valor destaque">${a.alta_confianca ?? 0}</div></div>
      <div class="metrica"><div class="metrica-rotulo">Método principal</div><div class="metrica-valor pequeno">${esc(ROTULOS_METODO[a.metodo_principal] || '—')}</div></div>
    </div>
    <table class="tabela-dist">
      <thead><tr><th>Detector</th><th>Encontrou</th><th>Situação</th></tr></thead>
      <tbody>${linhas}</tbody>
    </table>
    <div class="interpretacao">
      "Alta confiança" = ponto marcado por dois ou mais detectores independentes.
      Cada detector encontra um tipo diferente de falha, por isso os números divergem entre eles.
    </div>`;
}

/* ---------- Gráfico com anomalias destacadas ---------- */

function renderGrafico(dado) {
  const serie = dado.serie || { timestamps: [], valores: [] };
  const pontos = serie.timestamps.map((t, i) => ({ x: t * 1000, y: serie.valores[i] }));
  const anomalos = (dado.anomalias?.pontos || []).map(p => ({ x: p.timestamp * 1000, y: p.valor, votos: p.votos }));

  const ctx = document.getElementById('grafico-analise').getContext('2d');
  if (grafico) grafico.destroy();

  const d = dado.descritivas || {};
  const ic = dado.intervalo_confianca;

  const datasets = [
    {
      label: dado.sensor?.nome || 'Valor',
      data: pontos,
      borderColor: '#35D6A8',
      backgroundColor: 'rgba(53,214,168,0.06)',
      borderWidth: 1.5, pointRadius: 0, tension: 0.2, fill: true, order: 3,
    },
    {
      label: 'Anomalias',
      data: anomalos,
      borderColor: '#E5565A',
      backgroundColor: '#E5565A',
      pointRadius: 4, pointStyle: 'circle', showLine: false, order: 1,
    },
  ];

  if (d.mediana !== undefined && pontos.length) {
    const extremos = [{ x: pontos[0].x, y: d.mediana }, { x: pontos[pontos.length - 1].x, y: d.mediana }];
    datasets.push({
      label: 'Mediana', data: extremos,
      borderColor: 'rgba(139,147,163,0.7)', borderDash: [6, 4],
      borderWidth: 1, pointRadius: 0, fill: false, order: 2,
    });
  }

  grafico = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: {
          type: 'linear',
          ticks: {
            color: '#8B93A3', maxRotation: 0, autoSkip: true, maxTicksLimit: 8,
            font: { family: 'IBM Plex Mono', size: 11 },
            callback: v => new Date(v).toLocaleString('pt-BR', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }),
          },
          grid: { color: '#2A3240' },
        },
        y: { ticks: { color: '#8B93A3', font: { family: 'IBM Plex Mono', size: 11 } }, grid: { color: '#2A3240' } },
      },
      plugins: {
        legend: { labels: { color: '#8B93A3', font: { family: 'IBM Plex Sans', size: 12 }, boxWidth: 12, usePointStyle: true } },
        tooltip: {
          callbacks: {
            title: itens => itens.length ? new Date(itens[0].parsed.x).toLocaleString('pt-BR') : '',
            afterLabel: item => {
              const p = anomalos[item.dataIndex];
              return (item.datasetIndex === 1 && p) ? `Confirmado por ${p.votos} detector(es)` : '';
            },
          },
        },
      },
    },
  });
}

carregarSensores();

/* ---------- Previsão ARIMA ---------- */

let graficoPrevisao = null;

const elBtnPrever = document.getElementById('btn-prever');
const elBlocoPrev = document.getElementById('bloco-previsao');
const elWrapPrev = document.getElementById('wrap-previsao');

elBtnPrever.addEventListener('click', carregarPrevisao);

async function carregarPrevisao() {
  if (!sensorSelecionado) return;

  elBtnPrever.classList.add('btn-carregando');
  elBtnPrever.textContent = 'Ajustando modelo…';
  elBlocoPrev.innerHTML = '<div class="empty-state">Ajustando o modelo e calculando a banda de confiança…</div>';

  let dado;
  try {
    dado = await api(`/api/analise/${sensorSelecionado}/previsao?${paramsPeriodo().toString()}&passos=12`);
  } catch (e) {
    elBlocoPrev.innerHTML = `<div class="empty-state">Não consegui gerar a previsão: ${esc(e.message)}</div>`;
    return;
  } finally {
    elBtnPrever.classList.remove('btn-carregando');
    elBtnPrever.innerHTML = '<i class="ti ti-refresh"></i> Recalcular';
  }

  renderPrevisao(dado);
}

const NOMES_MODELO = {
  arima: 'ARIMA', holt: 'Suavização de Holt',
  ingenuo: 'Banda ingênua', constante: 'Série constante',
};

function renderPrevisao(dado) {
  const p = dado.previsao || {};
  const bt = dado.backtest || {};

  if (!p.disponivel) {
    elBlocoPrev.innerHTML = `<div class="empty-state">${esc(p.motivo || 'Previsão indisponível.')}</div>`;
    elWrapPrev.style.display = 'none';
    return;
  }

  const alerta = dado.alerta;
  let blocoAlerta = '';
  if (alerta) {
    const jaFora = alerta.situacao === 'atual';
    const suave = !jaFora && alerta.certeza === 'possível';
    const sub = jaFora
      ? `Limite configurado: ${num(alerta.limite)} · o valor já está fora da faixa, não é uma projeção.`
      : `Valor previsto ${num(alerta.valor_previsto)} · limite ${num(alerta.limite)} · previsto para ${formatarHora(alerta.timestamp)}`;
    blocoAlerta = `
      <div class="alerta-previsao ${suave ? 'possivel' : ''}">
        <div class="alerta-icone">${suave ? '⚠' : '⬤'}</div>
        <div>
          <div class="alerta-texto">${esc(alerta.mensagem)}</div>
          <div class="alerta-sub">${sub}</div>
        </div>
      </div>`;
  }

  const limites = dado.limites || {};
  const semLimites = (limites.minimo === null || limites.minimo === undefined) &&
                     (limites.maximo === null || limites.maximo === undefined);

  const metricas = [
    ['Modelo', NOMES_MODELO[p.modelo] || p.modelo],
    ...(p.ordem ? [['Ordem (p,d,q)', `(${p.ordem.join(', ')})`]] : []),
    ['Confiança', `${(p.confianca * 100).toFixed(0)}%`],
    ['Passos previstos', p.passos],
    ...(bt.disponivel ? [
      ['Fora da banda', `${bt.pontos_fora_banda} / ${bt.pontos_avaliados}`],
      ['RMSE', num(bt.rmse, 3)],
    ] : []),
  ];

  elBlocoPrev.innerHTML = `
    ${blocoAlerta}
    ${p.aviso ? `<div class="aviso-modelo">${esc(p.aviso)}</div>` : ''}
    <div class="metricas-grid">
      ${metricas.map(([k, v]) => `<div class="metrica"><div class="metrica-rotulo">${k}</div><div class="metrica-valor pequeno">${esc(String(v))}</div></div>`).join('')}
    </div>
    <div class="interpretacao">
      A faixa sombreada é o intervalo onde o modelo espera que o valor caia.
      Pontos históricos fora dela são anomalias contextuais: levam em conta tendência
      e autocorrelação, não apenas o nível absoluto.
      ${semLimites ? ' Defina limites mínimo/máximo no cadastro do sensor para receber alerta antecipado de cruzamento.' : ''}
    </div>`;

  desenharGraficoPrevisao(dado);
}

function desenharGraficoPrevisao(dado) {
  const p = dado.previsao;
  const bt = dado.backtest || {};
  elWrapPrev.style.display = 'block';

  const datasets = [];

  // Banda histórica (backtest) — desenhada como duas linhas com preenchimento entre elas
  if (bt.disponivel && bt.banda?.length) {
    datasets.push({
      label: 'Banda histórica',
      data: bt.banda.map(b => ({ x: b.timestamp * 1000, y: b.limite_superior })),
      borderColor: 'rgba(91,141,239,0.25)', borderWidth: 1, pointRadius: 0,
      fill: '+1', backgroundColor: 'rgba(91,141,239,0.10)', order: 5,
    });
    datasets.push({
      label: '_inf_hist', data: bt.banda.map(b => ({ x: b.timestamp * 1000, y: b.limite_inferior })),
      borderColor: 'rgba(91,141,239,0.25)', borderWidth: 1, pointRadius: 0, fill: false, order: 5,
    });
  }

  // Série observada
  const serie = dado.serie || { timestamps: [], valores: [] };
  datasets.push({
    label: 'Observado',
    data: serie.timestamps.map((t, i) => ({ x: t * 1000, y: serie.valores[i] })),
    borderColor: '#35D6A8', borderWidth: 1.5, pointRadius: 0, tension: 0.2, fill: false, order: 3,
  });

  // Pontos fora da banda
  if (bt.fora_da_banda?.length) {
    datasets.push({
      label: 'Fora da banda',
      data: bt.fora_da_banda.map(f => ({ x: f.timestamp * 1000, y: f.valor })),
      borderColor: '#E5565A', backgroundColor: '#E5565A',
      pointRadius: 4, showLine: false, order: 1,
    });
  }

  // Banda de previsão futura
  datasets.push({
    label: 'Banda prevista',
    data: p.previsao.map(f => ({ x: f.timestamp * 1000, y: f.limite_superior })),
    borderColor: 'rgba(242,169,60,0.4)', borderWidth: 1, borderDash: [4, 3], pointRadius: 0,
    fill: '+1', backgroundColor: 'rgba(242,169,60,0.12)', order: 4,
  });
  datasets.push({
    label: '_inf_prev',
    data: p.previsao.map(f => ({ x: f.timestamp * 1000, y: f.limite_inferior })),
    borderColor: 'rgba(242,169,60,0.4)', borderWidth: 1, borderDash: [4, 3], pointRadius: 0, fill: false, order: 4,
  });

  // Linha central da previsão
  datasets.push({
    label: 'Previsão',
    data: p.previsao.map(f => ({ x: f.timestamp * 1000, y: f.valor })),
    borderColor: '#F2A93C', borderWidth: 2, borderDash: [6, 3], pointRadius: 0, fill: false, order: 2,
  });

  // Limites operacionais do sensor
  const lim = dado.limites || {};
  const todosX = [...(bt.banda || []).map(b => b.timestamp * 1000), ...p.previsao.map(f => f.timestamp * 1000)];
  if (todosX.length) {
    const x0 = Math.min(...todosX), x1 = Math.max(...todosX);
    [['maximo', lim.maximo], ['minimo', lim.minimo]].forEach(([nome, v]) => {
      if (v === null || v === undefined) return;
      datasets.push({
        label: `Limite ${nome}`,
        data: [{ x: x0, y: v }, { x: x1, y: v }],
        borderColor: 'rgba(229,86,90,0.65)', borderWidth: 1.5, borderDash: [10, 4],
        pointRadius: 0, fill: false, order: 6,
      });
    });
  }

  const ctx = document.getElementById('grafico-previsao').getContext('2d');
  if (graficoPrevisao) graficoPrevisao.destroy();
  graficoPrevisao = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      scales: {
        x: {
          type: 'linear',
          ticks: {
            color: '#8B93A3', maxRotation: 0, autoSkip: true, maxTicksLimit: 8,
            font: { family: 'IBM Plex Mono', size: 11 },
            callback: v => new Date(v).toLocaleString('pt-BR', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }),
          },
          grid: { color: '#2A3240' },
        },
        y: { ticks: { color: '#8B93A3', font: { family: 'IBM Plex Mono', size: 11 } }, grid: { color: '#2A3240' } },
      },
      plugins: {
        legend: {
          labels: {
            color: '#8B93A3', font: { family: 'IBM Plex Sans', size: 12 }, boxWidth: 12, usePointStyle: true,
            // esconde as linhas auxiliares de preenchimento da legenda
            filter: item => !item.text.startsWith('_'),
          },
        },
        tooltip: {
          filter: item => !item.dataset.label.startsWith('_'),
          callbacks: { title: itens => itens.length ? new Date(itens[0].parsed.x).toLocaleString('pt-BR') : '' },
        },
      },
    },
  });
}

/* ---------- Seleção por arrasto no gráfico ---------- */

/*
 * Converte a posição do mouse em instante de tempo usando a escala do
 * próprio Chart.js (`getValueForPixel`), em vez de calcular proporção na
 * mão: assim a seleção continua correta mesmo com a área do gráfico
 * mudando de tamanho (margens dos eixos, redimensionar a janela).
 */
(function habilitarSelecao() {
  const overlay = document.getElementById('selecao-overlay');
  const wrap = document.getElementById('wrap-serie');
  if (!overlay || !wrap) return;

  let arrastando = false;
  let xInicio = 0;
  let retangulo = null;

  const MIN_PIXELS = 8;   // abaixo disso é clique, não seleção

  function posicaoX(evento) {
    return evento.clientX - overlay.getBoundingClientRect().left;
  }

  function tempoEm(px) {
    if (!grafico) return null;
    const escala = grafico.scales.x;
    // O canvas tem margens (área dos eixos); fora delas não há tempo válido
    const limitado = Math.max(escala.left, Math.min(escala.right, px + overlay.offsetLeft));
    return escala.getValueForPixel(limitado);
  }

  overlay.addEventListener('mousedown', (e) => {
    if (!grafico || e.button !== 0) return;
    arrastando = true;
    xInicio = posicaoX(e);

    const antigo = wrap.querySelector('.selecao-retangulo');
    if (antigo) antigo.remove();

    retangulo = document.createElement('div');
    retangulo.className = 'selecao-retangulo';
    retangulo.style.left = xInicio + 'px';
    retangulo.style.width = '0px';
    wrap.appendChild(retangulo);
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (!arrastando || !retangulo) return;
    const xAtual = posicaoX(e);
    retangulo.style.left = Math.min(xInicio, xAtual) + 'px';
    retangulo.style.width = Math.abs(xAtual - xInicio) + 'px';
  });

  window.addEventListener('mouseup', (e) => {
    if (!arrastando) return;
    arrastando = false;

    const xFim = posicaoX(e);
    if (Math.abs(xFim - xInicio) < MIN_PIXELS) {
      if (retangulo) retangulo.remove();
      retangulo = null;
      return;
    }

    const t1 = tempoEm(Math.min(xInicio, xFim));
    const t2 = tempoEm(Math.max(xInicio, xFim));
    if (t1 == null || t2 == null || !(t2 > t1)) {
      if (retangulo) retangulo.remove();
      retangulo = null;
      return;
    }

    recorte = { inicio: new Date(t1), fim: new Date(t2) };

    // O atalho de período deixa de valer enquanto houver recorte —
    // dois períodos ativos ao mesmo tempo seria ambíguo.
    elChipRow.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));

    atualizarDica();
    carregarAnalise();
  });

  // Toque: mesma lógica, para uso em tablet/TV com tela sensível
  overlay.addEventListener('touchstart', (e) => {
    if (!grafico || e.touches.length !== 1) return;
    overlay.dispatchEvent(new MouseEvent('mousedown', { clientX: e.touches[0].clientX, button: 0 }));
  }, { passive: true });

  overlay.addEventListener('touchmove', (e) => {
    if (e.touches.length !== 1) return;
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: e.touches[0].clientX }));
  }, { passive: true });

  overlay.addEventListener('touchend', (e) => {
    const toque = e.changedTouches[0];
    if (toque) window.dispatchEvent(new MouseEvent('mouseup', { clientX: toque.clientX }));
  });
})();
