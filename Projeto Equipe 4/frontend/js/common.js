/*
 * Helpers compartilhados entre dashboard.html e sensores.html.
 * Não usa build step de propósito — é servido direto pelo Nginx na TV box.
 */

// Se o frontend for servido pelo mesmo Nginx que faz proxy do backend,
// deixa em branco (usa caminho relativo /api, /ws). Se precisar apontar
// pra outro host, defina window.API_BASE antes de carregar esse script.
const API_BASE = window.API_BASE || '';

async function api(caminho, opcoes = {}) {
  const resp = await fetch(`${API_BASE}${caminho}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opcoes,
  });
  if (!resp.ok) {
    let detalhe = resp.statusText;
    try { detalhe = (await resp.json()).detail || detalhe; } catch (_) {}
    throw new Error(detalhe);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

function mostrarToast(mensagem, tipo = 'default') {
  const area = document.getElementById('toast-area');
  if (!area) return;
  const el = document.createElement('div');
  el.className = `toast ${tipo}`;
  el.textContent = mensagem;
  area.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function formatarHora(timestampOuIso) {
  const data = typeof timestampOuIso === 'number'
    ? new Date(timestampOuIso * 1000)
    : new Date(timestampOuIso);
  return data.toLocaleString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit', day: '2-digit', month: '2-digit' });
}

/**
 * Abre (ou reabre) a conexão WebSocket e chama `onLeitura` para cada
 * nova leitura recebida. `onStatus` é chamado com true/false conforme
 * a conexão sobe ou cai. Reconecta sozinho se cair.
 */
function conectarWebSocket(onLeitura, onStatus) {
  const protocolo = location.protocol === 'https:' ? 'wss' : 'ws';
  const base = API_BASE ? API_BASE.replace(/^http/, protocolo === 'wss' ? 'https' : 'http') : `${protocolo}://${location.host}`;
  const wsUrl = API_BASE ? base.replace(/^http/, protocolo) + '/ws' : `${protocolo}://${location.host}/ws`;

  let ws;
  let tentativas = 0;

  function conectar() {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      tentativas = 0;
      onStatus(true);
    };

    ws.onmessage = (evento) => {
      try {
        const dado = JSON.parse(evento.data);
        if (dado.tipo_evento === 'leitura') onLeitura(dado);
      } catch (_) { /* ignora mensagens malformadas */ }
    };

    ws.onclose = () => {
      onStatus(false);
      tentativas += 1;
      const espera = Math.min(1000 * 2 ** tentativas, 15000);
      setTimeout(conectar, espera);
    };

    ws.onerror = () => ws.close();
  }

  conectar();
}
