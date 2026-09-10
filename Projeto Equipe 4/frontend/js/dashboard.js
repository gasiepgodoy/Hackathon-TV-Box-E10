/*
 * Dashboard: um cartão e um gráfico por sensor.
 *
 * Optamos por um gráfico por sensor em vez de um gráfico único com todos:
 * sensores medem grandezas diferentes (°C, %, hPa) em escalas diferentes,
 * e sobrepô-los num eixo Y comum achata os de menor amplitude até virarem
 * linhas retas. Separado, cada série usa a escala que lhe cabe.
 */

let sensores = [];
let rangeAtual = '-1h';
const graficos = {};        // sensor_id -> instância do Chart
const coresPorSensor = {};

const PALETA_CORES = ['#35D6A8', '#F2A93C', '#5B8DEF', '#E5565A', '#B279DB', '#4FD1E8', '#E88BC5', '#8BE86B'];

const elGrid = document.getElementById('sensor-grid');
const elGraficos = document.getElementById('graficos-grid');
const elChipRow = document.getElementById('chip-row');
const elCampoInicio = document.getElementById('campo-inicio');
const elCampoFim = document.getElementById('campo-fim');
const elInputInicio = document.getElementById('input-inicio');
const elInputFim = document.getElementById('input-fim');
const elWsDot = document.getElementById('ws-dot');
const elWsLabel = document.getElementById('ws-label');

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}

function corDoSensor(sensorId) {
  if (!coresPorSensor[sensorId]) {
    const i = Object.keys(coresPorSensor).length % PALETA_CORES.length;
    coresPorSensor[sensorId] = PALETA_CORES[i];
  }
  return coresPorSensor[sensorId];
}

/* ---------- Carga inicial ---------- */

async function carregarSensores() {
  try {
    sensores = await api('/api/sensores');
  } catch (e) {
    mostrarToast('Não consegui carregar os sensores: ' + e.message, 'error');
    sensores = [];
  }
  await carregarUltimasLeituras();
  renderizarGrid();
}

/**
 * Busca a última leitura de cada sensor. Sem isso os cartões ficam com
 * "—" até chegar uma leitura nova pelo WebSocket, o que num sensor de
 * baixa frequência faz a tela parecer quebrada logo após abrir.
 */
async function carregarUltimasLeituras() {
  if (!sensores.length) return;
  try {
    const ultimas = await api('/api/dados/ultimas?janela=-7d');
    sensores.forEach(s => {
      const u = ultimas[s.id];
      if (u) {
        s._ultimoValor = u.valor;
        s._ultimoTimestamp = new Date(u.timestamp).getTime() / 1000;
      }
    });
  } catch (e) {
    // Falhar aqui não impede o dashboard de funcionar: os cartões apenas
    // ficam sem valor até a primeira leitura chegar pelo WebSocket.
    console.warn('Não consegui carregar as últimas leituras:', e.message);
  }
}

/* ---------- Cartões ---------- */

function renderizarGrid() {
  if (!sensores.length) {
    elGrid.innerHTML = '<div class="empty-state">Nenhum sensor cadastrado ainda. Vá em "Sensores" para adicionar o primeiro.</div>';
    elGraficos.innerHTML = '<div class="empty-state">Cadastre um sensor para ver o histórico.</div>';
    return;
  }
  elGrid.innerHTML = sensores.map(cardHtml).join('');
  sincronizarGraficos();
}

function idadeLeitura(ts) {
  if (!ts) return null;
  return (Date.now() / 1000) - ts;
}

function cardHtml(s) {
  const temValor = s._ultimoValor !== undefined && s._ultimoValor !== null;
  const idade = idadeLeitura(s._ultimoTimestamp);
  // "Recente" = menos de um minuto. Serve para distinguir um valor que
  // está chegando agora de um que ficou parado na tela desde ontem.
  const recente = idade !== null && idade < 60;

  return `
    <div class="sensor-card" data-id="${s.id}">
      <div class="sensor-card-top">
        <div>
          <div class="sensor-card-nome">${esc(s.nome)}</div>
          <div class="sensor-card-tipo">${esc(s.tipo)} · ${esc(s.protocolo)}</div>
        </div>
        <span class="badge-status ${s.status}">${s.status}</span>
      </div>
      <div class="sensor-card-valor" style="color:${corDoSensor(s.id)}">
        ${temValor ? s._ultimoValor : '—'}<span class="unidade">${esc(s.unidade || '')}</span>
      </div>
      <div class="sensor-card-tempo ${recente ? 'recente' : ''}">
        <span class="rotulo-tempo">${recente ? 'agora' : 'às'}</span>${s._ultimoTimestamp ? formatarHora(s._ultimoTimestamp) : '—'}
      </div>
    </div>`;
}

function atualizarCard(s) {
  const antigo = elGrid.querySelector(`.sensor-card[data-id="${s.id}"]`);
  if (antigo) antigo.outerHTML = cardHtml(s);
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
    if (!personalizado) carregarTodosGraficos();
  });
});

document.getElementById('btn-atualizar').addEventListener('click', () => {
  carregarSensores().then(carregarTodosGraficos);
});

document.getElementById('btn-csv').addEventListener('click', () => {
  const p = paramsPeriodo();
  const url = `${window.API_BASE || ''}/api/dados/csv?${p.toString()}`;
  const a = document.createElement('a');
  a.href = url; a.download = '';
  document.body.appendChild(a); a.click(); a.remove();
});

function paramsPeriodo(sensorId) {
  const p = new URLSearchParams();
  if (sensorId) p.set('sensor_id', sensorId);
  if (rangeAtual === 'custom') {
    if (elInputInicio.value) p.set('inicio', new Date(elInputInicio.value).toISOString());
    if (elInputFim.value) p.set('fim', new Date(elInputFim.value).toISOString());
  } else {
    p.set('inicio', rangeAtual);
  }
  return p;
}

/* ---------- Gráficos ---------- */

function sincronizarGraficos() {
  const idsAtuais = sensores.map(s => s.id);

  // Remove gráficos de sensores que saíram do cadastro
  Object.keys(graficos).forEach(id => {
    if (!idsAtuais.includes(id)) {
      graficos[id].destroy();
      delete graficos[id];
    }
  });

  const existentes = new Set([...elGraficos.querySelectorAll('.grafico-card')].map(el => el.dataset.id));
  const faltando = sensores.filter(s => !existentes.has(s.id));
  if (existentes.size === 0) elGraficos.innerHTML = '';

  faltando.forEach(s => {
    const card = document.createElement('div');
    card.className = 'grafico-card';
    card.dataset.id = s.id;
    card.innerHTML = `
      <div class="grafico-card-topo">
        <div class="grafico-card-nome">${esc(s.nome)}</div>
        <div class="grafico-card-meta">${esc(s.tipo)}${s.unidade ? ' · ' + esc(s.unidade) : ''}</div>
      </div>
      <div class="grafico-card-corpo">
        <canvas></canvas>
        <div class="grafico-card-vazio">carregando…</div>
      </div>`;
    elGraficos.appendChild(card);
  });
}

async function carregarTodosGraficos() {
  if (!sensores.length) return;
  sincronizarGraficos();
  // Sequencial de propósito: numa CPU de borda, disparar N consultas ao
  // InfluxDB de uma vez atrasa todas em vez de acelerar o conjunto.
  for (const s of sensores) {
    await carregarGraficoSensor(s);
  }
}

async function carregarGraficoSensor(sensor) {
  const card = elGraficos.querySelector(`.grafico-card[data-id="${sensor.id}"]`);
  if (!card) return;
  const canvas = card.querySelector('canvas');
  const vazio = card.querySelector('.grafico-card-vazio');

  let pontos = [];
  try {
    pontos = await api(`/api/dados?${paramsPeriodo(sensor.id).toString()}`);
  } catch (e) {
    vazio.textContent = 'erro ao carregar: ' + e.message;
    vazio.style.display = 'flex';
    return;
  }

  vazio.style.display = pontos.length ? 'none' : 'flex';
  if (!pontos.length) vazio.textContent = 'sem dados no período';

  const dados = pontos.map(p => ({ x: new Date(p.timestamp).getTime(), y: p.valor }));
  const cor = corDoSensor(sensor.id);

  if (graficos[sensor.id]) graficos[sensor.id].destroy();
  graficos[sensor.id] = new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: {
      datasets: [{
        label: sensor.nome,
        data: dados,
        borderColor: cor,
        backgroundColor: cor + '14',
        borderWidth: 1.8,
        pointRadius: 0,
        tension: 0.25,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          type: 'linear',
          ticks: {
            color: '#8B93A3', maxRotation: 0, autoSkip: true, maxTicksLimit: 5,
            font: { family: 'IBM Plex Mono', size: 10 },
            callback: v => new Date(v).toLocaleString('pt-BR', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }),
          },
          grid: { color: '#2A3240' },
        },
        y: {
          ticks: { color: '#8B93A3', font: { family: 'IBM Plex Mono', size: 10 } },
          grid: { color: '#2A3240' },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: itens => itens.length ? new Date(itens[0].parsed.x).toLocaleString('pt-BR') : '',
            label: item => `${item.parsed.y}${sensor.unidade ? ' ' + sensor.unidade : ''}`,
          },
        },
      },
    },
  });
}

/* ---------- Tempo real ---------- */

function aoReceberLeitura(dado) {
  const sensor = sensores.find(s => s.id === dado.sensor_id);
  if (!sensor) return;

  sensor._ultimoValor = dado.valor;
  sensor._ultimoTimestamp = dado.timestamp;
  atualizarCard(sensor);

  // Só empurra no gráfico se o período exibido inclui "agora"
  const emTempoReal = rangeAtual !== 'custom' && ['-1h', '-24h'].includes(rangeAtual);
  const g = graficos[dado.sensor_id];
  if (g && emTempoReal) {
    const ds = g.data.datasets[0];
    ds.data.push({ x: dado.timestamp * 1000, y: dado.valor });
    if (ds.data.length > 600) ds.data.shift();
    g.update('none');
    const vazio = elGraficos.querySelector(`.grafico-card[data-id="${dado.sensor_id}"] .grafico-card-vazio`);
    if (vazio) vazio.style.display = 'none';
  }
}

conectarWebSocket(aoReceberLeitura, (conectado) => {
  elWsDot.className = 'ws-dot ' + (conectado ? 'on' : 'off');
  elWsLabel.textContent = conectado ? 'ao vivo' : 'reconectando…';
});

carregarSensores().then(carregarTodosGraficos);

// Mantém status dos sensores em dia; os gráficos seguem pelo WebSocket.
setInterval(async () => {
  await carregarSensores();
}, 30000);

// Reavalia o rótulo "agora" dos cartões mesmo sem leitura nova chegando
setInterval(() => sensores.forEach(atualizarCard), 20000);
