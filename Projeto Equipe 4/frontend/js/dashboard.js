/* Estado da página de dashboard */
let sensores = [];
let sensorSelecionado = '';   // '' = todos
let rangeAtual = '-1h';
let grafico = null;

const elGrid = document.getElementById('sensor-grid');
const elSelect = document.getElementById('select-sensor');
const elChipRow = document.getElementById('chip-row');
const elCampoInicio = document.getElementById('campo-inicio');
const elCampoFim = document.getElementById('campo-fim');
const elInputInicio = document.getElementById('input-inicio');
const elInputFim = document.getElementById('input-fim');
const elChartEmpty = document.getElementById('chart-empty');
const elWsDot = document.getElementById('ws-dot');
const elWsLabel = document.getElementById('ws-label');

async function carregarSensores() {
  try {
    sensores = await api('/api/sensores');
  } catch (e) {
    mostrarToast('Não consegui carregar os sensores: ' + e.message, 'error');
    sensores = [];
  }
  renderizarGrid();
  renderizarSelect();
}

function renderizarSelect() {
  const atual = elSelect.value;
  elSelect.innerHTML = '<option value="">Todos os sensores</option>' +
    sensores.map(s => `<option value="${s.id}">${escapeHtml(s.nome)} (${escapeHtml(s.tipo)})</option>`).join('');
  elSelect.value = atual;
}

function renderizarGrid() {
  if (sensores.length === 0) {
    elGrid.innerHTML = '<div class="empty-state">Nenhum sensor cadastrado ainda. Vá em "Sensores" para adicionar o primeiro.</div>';
    return;
  }
  elGrid.innerHTML = sensores.map(s => cardHtml(s)).join('');
  elGrid.querySelectorAll('.sensor-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = card.dataset.id;
      sensorSelecionado = sensorSelecionado === id ? '' : id;
      elSelect.value = sensorSelecionado;
      atualizarSelecaoVisual();
      carregarGrafico();
    });
  });
  atualizarSelecaoVisual();
}

function cardHtml(s) {
  const valor = s._ultimoValor !== undefined ? s._ultimoValor : null;
  const hora = s._ultimoTimestamp ? formatarHora(s._ultimoTimestamp) : '—';
  return `
    <div class="sensor-card" data-id="${s.id}">
      <div class="sensor-card-top">
        <div>
          <div class="sensor-card-nome">${escapeHtml(s.nome)}</div>
          <div class="sensor-card-tipo">${escapeHtml(s.tipo)} · ${escapeHtml(s.protocolo)}</div>
        </div>
        <span class="badge-status ${s.status}">${s.status}</span>
      </div>
      <div class="sensor-card-valor">${valor !== null ? valor : '—'}<span class="unidade">${s.unidade || ''}</span></div>
      <div class="sensor-card-tempo">${hora}</div>
    </div>`;
}

function atualizarSelecaoVisual() {
  elGrid.querySelectorAll('.sensor-card').forEach(card => {
    card.classList.toggle('selected', card.dataset.id === sensorSelecionado);
  });
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}

/* ---------- Período ---------- */

elChipRow.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    elChipRow.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    rangeAtual = chip.dataset.range;
    const personalizado = rangeAtual === 'custom';
    elCampoInicio.style.display = personalizado ? 'flex' : 'none';
    elCampoFim.style.display = personalizado ? 'flex' : 'none';
    if (!personalizado) carregarGrafico();
  });
});

elSelect.addEventListener('change', () => {
  sensorSelecionado = elSelect.value;
  atualizarSelecaoVisual();
  carregarGrafico();
});

document.getElementById('btn-atualizar').addEventListener('click', carregarGrafico);

document.getElementById('btn-csv').addEventListener('click', () => {
  const params = paramsAtuais();
  const url = `${window.API_BASE || ''}/api/dados/csv?${params.toString()}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
});

function paramsAtuais() {
  const params = new URLSearchParams();
  if (sensorSelecionado) params.set('sensor_id', sensorSelecionado);
  if (rangeAtual === 'custom') {
    if (elInputInicio.value) params.set('inicio', new Date(elInputInicio.value).toISOString());
    if (elInputFim.value) params.set('fim', new Date(elInputFim.value).toISOString());
  } else {
    params.set('inicio', rangeAtual);
  }
  return params;
}

/* ---------- Gráfico ---------- */

const PALETA_CORES = ['#35D6A8', '#F2A93C', '#5B8DEF', '#E5565A', '#B279DB', '#4FD1E8', '#E88BC5', '#8BE86B'];
const coresPorSensor = {};

function corDoSensor(sensorId) {
  if (!coresPorSensor[sensorId]) {
    const indice = Object.keys(coresPorSensor).length % PALETA_CORES.length;
    coresPorSensor[sensorId] = PALETA_CORES[indice];
  }
  return coresPorSensor[sensorId];
}

function nomeDoSensor(sensorId) {
  return sensores.find(s => s.id === sensorId)?.nome || `sensor ${sensorId.slice(0, 8)}`;
}

function agruparPorSensor(pontos) {
  const grupos = {};
  for (const p of pontos) {
    (grupos[p.sensor_id] ||= []).push({ x: new Date(p.timestamp).getTime(), y: p.valor });
  }
  return grupos;
}

function montarDatasets(grupos) {
  const ids = Object.keys(grupos);
  const umSoSensor = ids.length === 1;
  return ids.map(sensorId => ({
    sensorId,
    label: nomeDoSensor(sensorId),
    data: grupos[sensorId].sort((a, b) => a.x - b.x),
    borderColor: corDoSensor(sensorId),
    backgroundColor: corDoSensor(sensorId) + '14',
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.25,
    fill: umSoSensor, // preenchimento só faz sentido visual com uma linha só
  }));
}

async function carregarGrafico() {
  const params = paramsAtuais();
  let pontos = [];
  try {
    pontos = await api(`/api/dados?${params.toString()}`);
  } catch (e) {
    mostrarToast('Não consegui carregar os dados do gráfico: ' + e.message, 'error');
  }

  elChartEmpty.style.display = pontos.length ? 'none' : 'flex';

  const grupos = agruparPorSensor(pontos);
  const datasets = montarDatasets(grupos);

  if (grafico) grafico.destroy();
  const ctx = document.getElementById('grafico').getContext('2d');
  grafico = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          type: 'linear',
          ticks: {
            color: '#8B93A3',
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8,
            font: { family: 'IBM Plex Mono', size: 11 },
            callback: (valor) => new Date(valor).toLocaleString('pt-BR', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }),
          },
          grid: { color: '#2A3240' },
        },
        y: {
          ticks: { color: '#8B93A3', font: { family: 'IBM Plex Mono', size: 11 } },
          grid: { color: '#2A3240' },
        },
      },
      plugins: {
        legend: {
          display: datasets.length > 0,
          labels: { color: '#8B93A3', font: { family: 'IBM Plex Sans', size: 12 }, boxWidth: 12 },
        },
        tooltip: {
          callbacks: {
            title: (itens) => itens.length ? new Date(itens[0].parsed.x).toLocaleString('pt-BR') : '',
          },
        },
      },
    },
  });
}

/* ---------- WebSocket ao vivo ---------- */

function aoReceberLeitura(dado) {
  const sensor = sensores.find(s => s.id === dado.sensor_id);
  if (sensor) {
    sensor._ultimoValor = dado.valor;
    sensor._ultimoTimestamp = dado.timestamp;
    const card = elGrid.querySelector(`.sensor-card[data-id="${dado.sensor_id}"]`);
    if (card) card.outerHTML = cardHtml(sensor);
    atualizarSelecaoVisual();
    // religa o listener de clique do card recém-substituído
    const novoCard = elGrid.querySelector(`.sensor-card[data-id="${dado.sensor_id}"]`);
    if (novoCard) {
      novoCard.addEventListener('click', () => {
        sensorSelecionado = sensorSelecionado === dado.sensor_id ? '' : dado.sensor_id;
        elSelect.value = sensorSelecionado;
        atualizarSelecaoVisual();
        carregarGrafico();
      });
    }
  }

  // se o gráfico ativo é "tempo real" e o sensor está no escopo do filtro atual, atualiza incrementalmente
  const noEscopo = !sensorSelecionado || sensorSelecionado === dado.sensor_id;
  if (grafico && noEscopo && rangeAtual !== 'custom' && rangeAtual !== '-30d' && rangeAtual !== '-7d') {
    let dataset = grafico.data.datasets.find(ds => ds.sensorId === dado.sensor_id);
    if (!dataset) {
      const umSoSensor = grafico.data.datasets.length === 0;
      dataset = {
        sensorId: dado.sensor_id,
        label: nomeDoSensor(dado.sensor_id),
        data: [],
        borderColor: corDoSensor(dado.sensor_id),
        backgroundColor: corDoSensor(dado.sensor_id) + '14',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25,
        fill: umSoSensor,
      };
      grafico.data.datasets.push(dataset);
    }
    dataset.data.push({ x: dado.timestamp * 1000, y: dado.valor });
    if (dataset.data.length > 300) dataset.data.shift();
    grafico.update('none');
    elChartEmpty.style.display = 'none';
  }
}

conectarWebSocket(aoReceberLeitura, (conectado) => {
  elWsDot.className = 'ws-dot ' + (conectado ? 'on' : 'off');
  elWsLabel.textContent = conectado ? 'ao vivo' : 'reconectando…';
});

carregarSensores().then(carregarGrafico);
setInterval(carregarSensores, 30000); // mantém status/lista de sensores em dia
