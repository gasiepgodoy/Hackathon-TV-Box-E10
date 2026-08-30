let sensores = [];
let editandoId = null;

const elTabela = document.getElementById('tabela-corpo');
const elBackdrop = document.getElementById('modal-backdrop');
const elForm = document.getElementById('form-sensor');
const elModalTitulo = document.getElementById('modal-titulo');
const elFormError = document.getElementById('form-error');

async function carregarSensores() {
  try {
    sensores = await api('/api/sensores');
  } catch (e) {
    mostrarToast('Não consegui carregar os sensores: ' + e.message, 'error');
    sensores = [];
  }
  renderizarTabela();
}

function renderizarTabela() {
  if (sensores.length === 0) {
    elTabela.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum sensor cadastrado ainda.</td></tr>';
    return;
  }
  elTabela.innerHTML = sensores.map(s => `
    <tr>
      <td>${escapeHtml(s.nome)}</td>
      <td class="mono">${escapeHtml(s.tipo)}</td>
      <td class="mono">${escapeHtml(s.protocolo)}</td>
      <td>${escapeHtml(s.local || '—')}</td>
      <td><span class="badge-status ${s.status}">${s.status}</span></td>
      <td>
        <div class="row-actions">
          <button data-acao="alternar" data-id="${s.id}">${s.ativo ? 'Pausar' : 'Ativar'}</button>
          <button data-acao="editar" data-id="${s.id}">Editar</button>
          <button data-acao="remover" data-id="${s.id}" class="danger-outline">Remover</button>
        </div>
      </td>
    </tr>
  `).join('');

  elTabela.querySelectorAll('button[data-acao]').forEach(btn => {
    btn.addEventListener('click', () => handleAcao(btn.dataset.acao, btn.dataset.id));
  });
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str ?? '';
  return d.innerHTML;
}

async function handleAcao(acao, id) {
  if (acao === 'editar') return abrirModalEdicao(id);

  if (acao === 'remover') {
    if (!confirm('Remover este sensor? Os dados já gravados no InfluxDB não são apagados.')) return;
    try {
      await api(`/api/sensores/${id}`, { method: 'DELETE' });
      mostrarToast('Sensor removido.', 'success');
      carregarSensores();
    } catch (e) {
      mostrarToast('Erro ao remover: ' + e.message, 'error');
    }
    return;
  }

  if (acao === 'alternar') {
    try {
      await api(`/api/sensores/${id}/alternar`, { method: 'POST' });
      carregarSensores();
    } catch (e) {
      mostrarToast('Erro ao alternar status: ' + e.message, 'error');
    }
  }
}

/* ---------- Modal ---------- */

document.getElementById('btn-abrir-modal').addEventListener('click', () => abrirModalNovo());
document.getElementById('btn-cancelar').addEventListener('click', fecharModal);
elBackdrop.addEventListener('click', (e) => { if (e.target === elBackdrop) fecharModal(); });

document.getElementById('campo-protocolo').addEventListener('change', atualizarCamposProtocolo);

function atualizarCamposProtocolo() {
  const protocolo = document.getElementById('campo-protocolo').value;
  document.querySelectorAll('.protocol-config').forEach(bloco => {
    bloco.style.display = bloco.dataset.protocolo === protocolo ? 'flex' : 'none';
  });
}

function abrirModalNovo() {
  editandoId = null;
  elModalTitulo.textContent = 'Adicionar sensor';
  elForm.reset();
  document.getElementById('campo-protocolo').value = 'mqtt';
  atualizarCamposProtocolo();
  elFormError.classList.remove('show');
  elBackdrop.classList.add('open');
}

function abrirModalEdicao(id) {
  const s = sensores.find(x => x.id === id);
  if (!s) return;
  editandoId = id;
  elModalTitulo.textContent = 'Editar sensor';
  elFormError.classList.remove('show');

  document.getElementById('campo-nome').value = s.nome;
  document.getElementById('campo-tipo').value = s.tipo;
  document.getElementById('campo-unidade').value = s.unidade || '';
  document.getElementById('campo-protocolo').value = s.protocolo;
  document.getElementById('campo-local').value = s.local || '';
  document.getElementById('campo-limite-min').value = s.limite_min ?? '';
  document.getElementById('campo-limite-max').value = s.limite_max ?? '';
  atualizarCamposProtocolo();

  const cfg = s.config || {};
  if (s.protocolo === 'mqtt') {
    document.getElementById('mqtt-host').value = cfg.broker_host || '';
    document.getElementById('mqtt-port').value = cfg.broker_port || 1883;
    document.getElementById('mqtt-topico').value = cfg.topico || '';
    document.getElementById('mqtt-qos').value = cfg.qos ?? 0;
    document.getElementById('mqtt-campo-valor').value = cfg.campo_valor || 'valor';
    document.getElementById('mqtt-intervalo-esperado').value = cfg.intervalo_esperado_s ?? '';
  } else if (s.protocolo === 'opcua') {
    document.getElementById('opcua-endpoint').value = cfg.endpoint_url || '';
    document.getElementById('opcua-node').value = cfg.node_id || '';
    document.getElementById('opcua-intervalo').value = cfg.intervalo_ms || 1000;
  } else if (s.protocolo === 'http') {
    document.getElementById('http-url').value = cfg.url || '';
    document.getElementById('http-metodo').value = cfg.metodo || 'GET';
    document.getElementById('http-intervalo').value = cfg.intervalo_segundos ?? 10;
    document.getElementById('http-campo-valor').value = cfg.campo_valor || 'valor';
  } else if (s.protocolo === 'modbus') {
    document.getElementById('modbus-host').value = cfg.host || '';
    document.getElementById('modbus-porta').value = cfg.porta ?? 502;
    document.getElementById('modbus-device-id').value = cfg.device_id ?? 1;
    document.getElementById('modbus-registrador').value = cfg.registrador ?? 0;
    document.getElementById('modbus-tipo-registrador').value = cfg.tipo_registrador || 'holding';
    document.getElementById('modbus-tipo-dado').value = cfg.tipo_dado || 'uint16';
    document.getElementById('modbus-escala').value = cfg.escala ?? 1;
    document.getElementById('modbus-offset').value = cfg.offset ?? 0;
    document.getElementById('modbus-ordem').value = cfg.ordem_palavras || 'big';
    document.getElementById('modbus-intervalo').value = cfg.intervalo_segundos ?? 5;
  } else if (s.protocolo === 'simulado') {
    document.getElementById('sim-min').value = cfg.valor_min ?? 18;
    document.getElementById('sim-max').value = cfg.valor_max ?? 28;
    document.getElementById('sim-intervalo').value = cfg.intervalo_segundos ?? 5;
  }

  elBackdrop.classList.add('open');
}

function fecharModal() {
  elBackdrop.classList.remove('open');
}

function montarConfig(protocolo) {
  if (protocolo === 'mqtt') {
    return {
      broker_host: document.getElementById('mqtt-host').value.trim(),
      broker_port: Number(document.getElementById('mqtt-port').value || 1883),
      topico: document.getElementById('mqtt-topico').value.trim(),
      qos: Number(document.getElementById('mqtt-qos').value || 0),
      campo_valor: document.getElementById('mqtt-campo-valor').value.trim() || 'valor',
      ...(document.getElementById('mqtt-intervalo-esperado').value !== ''
        ? { intervalo_esperado_s: Number(document.getElementById('mqtt-intervalo-esperado').value) }
        : {}),
    };
  }
  if (protocolo === 'opcua') {
    return {
      endpoint_url: document.getElementById('opcua-endpoint').value.trim(),
      node_id: document.getElementById('opcua-node').value.trim(),
      intervalo_ms: Number(document.getElementById('opcua-intervalo').value || 1000),
    };
  }
  if (protocolo === 'http') {
    return {
      url: document.getElementById('http-url').value.trim(),
      metodo: document.getElementById('http-metodo').value,
      intervalo_segundos: Number(document.getElementById('http-intervalo').value || 10),
      campo_valor: document.getElementById('http-campo-valor').value.trim() || 'valor',
    };
  }
  if (protocolo === 'modbus') {
    return {
      host: document.getElementById('modbus-host').value.trim(),
      porta: Number(document.getElementById('modbus-porta').value || 502),
      device_id: Number(document.getElementById('modbus-device-id').value || 1),
      registrador: Number(document.getElementById('modbus-registrador').value || 0),
      tipo_registrador: document.getElementById('modbus-tipo-registrador').value,
      tipo_dado: document.getElementById('modbus-tipo-dado').value,
      escala: Number(document.getElementById('modbus-escala').value || 1),
      offset: Number(document.getElementById('modbus-offset').value || 0),
      ordem_palavras: document.getElementById('modbus-ordem').value,
      intervalo_segundos: Number(document.getElementById('modbus-intervalo').value || 5),
    };
  }
  return {
    valor_min: Number(document.getElementById('sim-min').value || 0),
    valor_max: Number(document.getElementById('sim-max').value || 100),
    intervalo_segundos: Number(document.getElementById('sim-intervalo').value || 5),
  };
}

function validarConfig(protocolo, cfg) {
  if (protocolo === 'mqtt' && (!cfg.broker_host || !cfg.topico)) {
    return 'Preencha o endereço do broker e o tópico MQTT.';
  }
  if (protocolo === 'opcua' && (!cfg.endpoint_url || !cfg.node_id)) {
    return 'Preencha o endpoint e o node ID do OPC UA.';
  }
  if (protocolo === 'http' && !cfg.url) {
    return 'Preencha a URL do endpoint HTTP.';
  }
  if (protocolo === 'modbus') {
    if (!cfg.host) return 'Informe o endereço do equipamento Modbus.';
    if (cfg.escala === 0) return 'A escala não pode ser zero — ela multiplica o valor lido.';
    if (cfg.intervalo_segundos <= 0) return 'O intervalo de leitura deve ser maior que zero.';
    return null;
  }
  if (protocolo === 'simulado' && cfg.valor_min >= cfg.valor_max) {
    return 'O valor mínimo do simulador deve ser menor que o máximo.';
  }
  return null;
}

elForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  elFormError.classList.remove('show');

  const protocolo = document.getElementById('campo-protocolo').value;
  const config = montarConfig(protocolo);
  const erro = validarConfig(protocolo, config);
  if (erro) {
    elFormError.textContent = erro;
    elFormError.classList.add('show');
    return;
  }

  const payload = {
    nome: document.getElementById('campo-nome').value.trim(),
    tipo: document.getElementById('campo-tipo').value.trim(),
    unidade: document.getElementById('campo-unidade').value.trim() || null,
    protocolo,
    local: document.getElementById('campo-local').value.trim() || null,
    limite_min: document.getElementById('campo-limite-min').value === '' ? null : Number(document.getElementById('campo-limite-min').value),
    limite_max: document.getElementById('campo-limite-max').value === '' ? null : Number(document.getElementById('campo-limite-max').value),
    config,
    ativo: true,
  };

  try {
    if (editandoId) {
      await api(`/api/sensores/${editandoId}`, { method: 'PUT', body: JSON.stringify(payload) });
      mostrarToast('Sensor atualizado.', 'success');
    } else {
      await api('/api/sensores', { method: 'POST', body: JSON.stringify(payload) });
      mostrarToast('Sensor adicionado.', 'success');
    }
    fecharModal();
    carregarSensores();
  } catch (e2) {
    elFormError.textContent = e2.message;
    elFormError.classList.add('show');
  }
});

carregarSensores();
