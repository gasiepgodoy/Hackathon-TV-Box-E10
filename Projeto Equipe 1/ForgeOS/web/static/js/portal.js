/* ==========================================================================
   HIGH-PERFORMANCE CLIENT TELEMETRY & EVENT LOOP ENGINE
   ========================================================================== */
let currentNetworks = [];
let currentServices = [];
let currentSvcFilter = 'all';
let currentProvMode = 'psk';
let isTickerBusy = false;
let currentClientSsid = null;

// Ring Buffers for Sparklines (60 points)
const HISTORY_LENGTH = 60;
const cpuHistory = new Float32Array(HISTORY_LENGTH);
const ramHistory = new Float32Array(HISTORY_LENGTH);
const netHistory = new Float32Array(HISTORY_LENGTH);
let historyIndex = 0;

// Logs Engine
let currentLogs = [];
let currentLogLevel = 'all';
let isLogFollowActive = true;
let pendingActionCallback = null;

// Command Palette Actions
const COMMANDS = [
  { name: 'Ir para Visão Geral', tab: 'overview', icon: '📊' },
  { name: 'Ir para Logs do Sistema', tab: 'logs', icon: '📜' },
  { name: 'Ir para Serviços & Recursos', tab: 'services', icon: '⚙️' },
  { name: 'Ir para Wi-Fi & Ponto de Acesso', tab: 'networking', icon: '📶' },
  { name: 'Ir para Interfaces Físicas', tab: 'interfaces', icon: '🔌' },
  { name: 'Ir para ForgeHub (Arsenal)', tab: 'modules', icon: '📦' },
  { name: 'Restaurar Ponto de Acesso (AP)', action: () => disconnectWifi(), icon: '🔄' },
  { name: 'Alternar Modo Escuro / Claro', action: () => toggleTheme(), icon: '🌓' },
  { name: 'Limpar Logs do Journal', action: () => confirmClearLogs(), icon: '🧹' }
];

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  setupNavigation();
  setupPasswordToggles();
  setupCommandPalette();
  loadServices();
  loadModulesHub();
  loadSystemLogs();
  tickRealtime();
  scanWifi();
  setInterval(() => { if (!document.hidden) tickRealtime(); }, 5000);
});

// Toast System
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast-item ${type}`;
  toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 200);
  }, 4000);
}

// Confirmation Modal
function showConfirmDialog(title, message, btnText, isDestructive, onConfirm) {
  document.getElementById('confirm-modal-title').textContent = title;
  document.getElementById('confirm-modal-body').textContent = message;
  const btn = document.getElementById('confirm-modal-btn');
  btn.textContent = btnText;
  btn.className = isDestructive ? 'pf-btn pf-btn-danger' : 'pf-btn pf-btn-primary';
  pendingActionCallback = onConfirm;
  document.getElementById('confirm-modal').classList.add('open');
}
function closeConfirmModal() {
  document.getElementById('confirm-modal').classList.remove('open');
  pendingActionCallback = null;
}
function executeConfirmedAction() {
  if (pendingActionCallback) {
    pendingActionCallback();
  }
  closeConfirmModal();
}

// Theme
function initTheme() {
  const saved = localStorage.getItem('forge_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  updateThemeIcons(saved);
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('forge_theme', next);
  updateThemeIcons(next);
}
function updateThemeIcons(theme) {
  const sun = document.getElementById('theme-icon-sun');
  const moon = document.getElementById('theme-icon-moon');
  if (sun && moon) {
    sun.style.display = theme === 'dark' ? 'none' : 'block';
    moon.style.display = theme === 'dark' ? 'block' : 'none';
  }
}

// Navigation
function setupNavigation() {
  window.addEventListener('hashchange', handleHash);
  handleHash();

  document.getElementById('sidebar-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('sidebar-backdrop').classList.toggle('open');
  });
  document.getElementById('sidebar-backdrop').addEventListener('click', () => {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebar-backdrop').classList.remove('open');
  });
  document.getElementById('btn-quick-reset').addEventListener('click', () => disconnectWifi());
  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
}

function handleHash() {
  const hash = window.location.hash.replace('#', '') || 'overview';
  showTab(['overview', 'logs', 'services', 'networking', 'interfaces', 'modules'].includes(hash) ? hash : 'overview');
}

function showTab(tabId) {
  const validTabs = ['overview', 'logs', 'services', 'networking', 'interfaces', 'modules'];
  if (!validTabs.includes(tabId)) tabId = 'overview';
  if (location.hash !== '#' + tabId) history.replaceState(null, '', '#' + tabId);
  document.querySelectorAll('.pf-nav-link').forEach(link => {
    if (link.dataset.tab === tabId) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  document.querySelectorAll('.tab-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.pf-nav-link').forEach(l => l.classList.remove('active'));

  const targetSec = document.getElementById(`view-${tabId}`);
  if (targetSec) targetSec.classList.add('active');

  const activeLink = document.querySelector(`.pf-nav-link[data-tab="${tabId}"]`);
  if (activeLink) activeLink.classList.add('active');

  const titles = {
    overview: ['Visão geral', 'Tudo pronto para dar o próximo passo.'],
    logs: ['Logs do sistema', 'Registro de eventos do kernel e serviços (journalctl RFC 5424).'],
    services: ['Serviços & recursos', 'Gerenciador de daemons do sistema e especificações do hardware.'],
    networking: ['Wi-Fi & ponto de acesso', 'Configuração de redes sem fio e portal cativo.'],
    interfaces: ['Interfaces físicas', 'Diagnóstico de conexões cabeada Gigabit e rádio SDIO.'],
    modules: ['Aplicações', 'Explore novas possibilidades para seu dispositivo.']
  };

  const [t, sub] = titles[tabId] || ['ForgeOS Cockpit', 'Painel de gerenciamento do appliance.'];
  document.getElementById('page-banner-title').textContent = t;
  document.getElementById('page-banner-subtitle').textContent = sub;

  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-backdrop').classList.remove('open');

  if (tabId === 'logs') {
    document.documentElement.classList.add('logs-active-mode');
    document.body.classList.add('logs-active-mode');
    loadSystemLogs();
  } else {
    document.documentElement.classList.remove('logs-active-mode');
    document.body.classList.remove('logs-active-mode');
  }
  if (tabId === 'services') loadServices();
  if (tabId === 'modules') loadModulesHub();
  if (tabId === 'networking') scanWifi();
}

// Password Eye Toggles
function setupPasswordToggles() {
  const toggleAP = document.getElementById('btn-toggle-ap-pass');
  const inputAP = document.getElementById('ap-cfg-pass');
  if (toggleAP && inputAP) {
    toggleAP.addEventListener('click', () => {
      inputAP.type = inputAP.type === 'password' ? 'text' : 'password';
    });
    inputAP.addEventListener('input', () => {
      document.getElementById('ap-pass-counter').textContent = `${inputAP.value.length}/63`;
    });
  }

  const toggleProv = document.getElementById('btn-toggle-prov-pass');
  const inputProv = document.getElementById('prov-password');
  if (toggleProv && inputProv) {
    toggleProv.addEventListener('click', () => {
      inputProv.type = inputProv.type === 'password' ? 'text' : 'password';
    });
    inputProv.addEventListener('input', () => {
      document.getElementById('prov-pass-counter').textContent = `${inputProv.value.length}/63`;
    });
  }
}

// Command Palette
function setupCommandPalette() {
  document.getElementById('btn-open-cmd').addEventListener('click', openCommandPalette);
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      openCommandPalette();
    }
    if (e.key === 'Escape') {
      closeCommandPalette();
      closeModal();
      closeConfirmModal();
    }
  });

  const cmdInput = document.getElementById('cmd-input');
  cmdInput.addEventListener('input', () => {
    const q = cmdInput.value.toLowerCase();
    renderCommandList(COMMANDS.filter(c => c.name.toLowerCase().includes(q)));
  });
}
function openCommandPalette() {
  document.getElementById('cmd-modal').classList.add('open');
  const input = document.getElementById('cmd-input');
  input.value = '';
  input.focus();
  renderCommandList(COMMANDS);
}
function closeCommandPalette() {
  document.getElementById('cmd-modal').classList.remove('open');
}
function renderCommandList(list) {
  const container = document.getElementById('cmd-list');
  container.innerHTML = list.map(c => `
    <button type="button" class="cmd-palette-item" onclick="executeCommand('${c.name}')">
      <span>${c.icon} ${escapeHtml(c.name)}</span>
      <span style="font-size:0.68rem; color:var(--pf-text-muted);">↵ Executar</span>
    </button>
  `).join('');
}
function executeCommand(name) {
  const item = COMMANDS.find(c => c.name === name);
  closeCommandPalette();
  if (item) {
    if (item.tab) {
      window.location.hash = item.tab;
    } else if (item.action) {
      item.action();
    }
  }
}

// Sparklines Rendering (Normalized 0-100 SVG path)
function renderSparkline(svgId, dataArray, maxVal = 100) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const path = svg.querySelector('path');
  if (!path) return;

  const len = dataArray.length;
  let d = '';
  for (let i = 0; i < len; i++) {
    const idx = (historyIndex + i) % len;
    const val = dataArray[idx];
    const x = (i / (len - 1)) * 100;
    const y = 30 - Math.min(30, Math.max(0, (val / maxVal) * 30));
    d += (i === 0 ? `M ${x.toFixed(1)} ${y.toFixed(1)}` : ` L ${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  path.setAttribute('d', d);
}

// Real-time Telemetry
async function tickRealtime(force = false) {
  if (isTickerBusy) return;
  isTickerBusy = true;

  try {
    const res = await fetch('/rest/metrics', { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error('Telemetria indisponível');
    const m = await res.json();
    // Missing measurements must never look like real, healthy hardware values.
    const required = ['cpu_pct', 'ram_used_mb', 'ram_total_mb', 'disk_used_gb', 'disk_total_gb'];
    if (required.some(key => !Number.isFinite(m[key])) || m.ram_total_mb <= 0 || m.disk_total_gb <= 0) {
      throw new Error('Telemetria incompleta');
    }

    // 1. CPU & Thermal
    const cpuVal = m.cpu_pct !== undefined ? m.cpu_pct : 0;
    document.getElementById('dash-cpu-val').textContent = `${cpuVal.toFixed(1)}%`;
    
    // Thermal Zone
    const tempVal = m.cpu_temp;
    const tempPill = document.getElementById('dash-temp-pill');
    if (tempPill) {
      tempPill.textContent = Number.isFinite(tempVal) ? `${tempVal.toFixed(1)}°C` : '—';
      tempPill.className = tempVal > 85 ? 'pf-pill danger' : (tempVal > 70 ? 'pf-pill warning' : 'pf-pill success');
    }

    const loadStr = m.load_avg ? m.load_avg.map(x => x.toFixed(2)).join(', ') : '—';
    document.getElementById('dash-cpu-sub').textContent = `Carga do sistema: ${loadStr}`;

    // 2. RAM
    const ramUsed = m.ram_used_mb;
    const ramTotal = m.ram_total_mb;
    const ramPct = m.ram_pct ?? ((ramUsed / ramTotal) * 100);
    const ramFreeGb = ((ramTotal - ramUsed) / 1024).toFixed(2);
    document.getElementById('dash-mem-val').textContent = `${ramUsed} MB / ${(ramTotal/1024).toFixed(2)} GB`;
    document.getElementById('dash-mem-sub').textContent = `${ramPct.toFixed(1)}% em uso (${ramFreeGb} GB livre)`;

    // 3. Storage
    const diskUsed = m.disk_used_gb;
    const diskTotal = m.disk_total_gb;
    const diskPct = ((diskUsed / diskTotal) * 100).toFixed(1);
    document.getElementById('dash-disk-val').textContent = `${diskUsed} GB / ${diskTotal} GB`;
    document.getElementById('dash-disk-sub').textContent = `${diskPct}% em uso · Ext4 Rootfs`;
    const diskBar = document.getElementById('dash-disk-bar');
    if (diskBar) diskBar.style.width = `${diskPct}%`;

    // 4. Network I/O
    const rx = m.rx_kbs || 0.0;
    const tx = m.tx_kbs || 0.0;
    document.getElementById('dash-net-val').textContent = `↓ ${rx.toFixed(1)} KB/s · ↑ ${tx.toFixed(1)} KB/s`;
    document.getElementById('eth-traffic-rate').textContent = `RX: ${rx.toFixed(1)} KB/s · TX: ${tx.toFixed(1)} KB/s`;

    // Update Sparkline Buffers
    cpuHistory[historyIndex] = cpuVal;
    ramHistory[historyIndex] = ramPct;
    netHistory[historyIndex] = rx + tx;
    historyIndex = (historyIndex + 1) % HISTORY_LENGTH;

    renderSparkline('sparkline-cpu', cpuHistory, 100);
    renderSparkline('sparkline-ram', ramHistory, 100);
    renderSparkline('sparkline-net', netHistory, 50);

    // Render Top 5 Processes
    const procs = m.top_processes || [];
    const procTable = document.getElementById('dash-top-processes');
    if (procTable && procs.length > 0) {
      procTable.innerHTML = procs.map(p => `
        <tr>
          <td class="pf-table-mono" style="color:var(--pf-text-muted);">${p.pid}</td>
          <td style="font-weight:600; color:var(--pf-text-primary);">${escapeHtml(p.name)}</td>
          <td style="color:var(--pf-blue-light); font-weight:600;">${p.cpu}%</td>
          <td>${p.mem}%</td>
        </tr>
      `).join('');
    }

    setConnectionState(true);
    // Refresh Dynamic Status
    await updateStatus();
  } catch (err) {
    setConnectionState(false);
  } finally {
    isTickerBusy = false;
  }
}

// Status & Network State Engine
async function updateStatus() {
  try {
    const res = await fetch('/api/status');
    const s = await res.json();

    const badgeText = document.getElementById('top-status-text');
    const badgeEl = document.getElementById('top-status-badge');
    const wifiBanner = document.getElementById('wifi-active-conn-banner');
    const wifiTitle = document.getElementById('wifi-status-title');
    const wifiSubtitle = document.getElementById('wifi-status-subtitle');
    const wlanIpEl = document.getElementById('wlan-table-ip');
    const wlanStatusEl = document.getElementById('wlan-table-status');
    const wifiBannerActions = document.getElementById('wifi-banner-actions');

    if (s.provisioning) {
      badgeText.textContent = 'Conectando ao Wi-Fi...';
      badgeEl.className = 'status-badge warn';
    } else if (s.client_connected) {
      currentClientSsid = s.client_ssid;
      badgeText.textContent = `Wi-Fi: ${s.client_ssid} (${s.client_ip})`;
      badgeEl.className = 'status-badge';

      if (wifiBanner) {
        wifiBanner.style.display = 'block';
        if (wifiTitle) wifiTitle.innerHTML = `<span class="status-dot-sm live-pulse" style="background:var(--pf-green-light); display:inline-block; margin-right:6px;"></span>Conectado à Rede: <strong style="color:var(--pf-green-light);">${escapeHtml(s.client_ssid)}</strong>`;
        if (wifiSubtitle) wifiSubtitle.textContent = `Endereço IP: ${s.client_ip || 'Indisponível'}`;
        if (wifiBannerActions) wifiBannerActions.innerHTML = `<button class="pf-btn pf-btn-danger pf-btn-sm" onclick="disconnectWifi()">Restaurar Modo Ponto de Acesso</button>`;
      }

      if (wlanIpEl) wlanIpEl.textContent = s.client_ip;
      if (wlanStatusEl) wlanStatusEl.innerHTML = `<span class="pf-pill success"><span class="status-dot-sm live-pulse"></span>Conectado: ${escapeHtml(s.client_ssid)}</span>`;
      document.getElementById('dash-mode-sub').textContent = `${s.client_ssid} (${s.client_ip})`;
    } else {
      currentClientSsid = null;
      badgeText.textContent = 'AP: 192.168.4.1';
      badgeEl.className = 'status-badge info';

      if (wifiBanner) {
        wifiBanner.style.display = 'block';
        if (wifiTitle) wifiTitle.innerHTML = `<span class="status-dot-sm live-pulse" style="background:var(--pf-blue-light); display:inline-block; margin-right:6px;"></span>Modo Ponto de Acesso: <strong style="color:var(--pf-blue-light);">${escapeHtml(s.ssid || 'RTL8189FTV_AP')}</strong>`;
        if (wifiSubtitle) wifiSubtitle.textContent = `Endereço IP: 192.168.4.1 · Servidor DHCP dnsmasq Ativo · Portal Cativo`;
        if (wifiBannerActions) wifiBannerActions.innerHTML = `<button class="pf-btn pf-btn-secondary pf-btn-sm" onclick="showTab('networking')">Configurar AP</button>`;
      }

      if (wlanIpEl) wlanIpEl.textContent = '192.168.4.1';
      if (wlanStatusEl) wlanStatusEl.innerHTML = `<span class="pf-pill info"><span class="status-dot-sm live-pulse" style="background:var(--pf-blue-light);"></span>AP Ativo</span>`;
      document.getElementById('dash-mode-sub').textContent = s.ap_active ? (s.ssid + ' (192.168.4.1)') : 'Sem IP';
    }

    // Ethernet IP Check
    const ethRes = await fetch('/rest/ethernetStatus');
    const eth = await ethRes.json();
    if (eth.local_ip) {
      document.getElementById('eth-table-ip').textContent = eth.local_ip;
      document.getElementById('eth-table-mac').textContent = eth.mac_address;
      document.getElementById('sidebar-footer-ip').textContent = eth.local_ip;
    }
  } catch (err) {}
}

// Disconnect / Restore AP
function disconnectWifi() {
  showConfirmDialog(
    'Restaurar Modo Ponto de Acesso',
    'Deseja desconectar da rede Wi-Fi e reativar o Ponto de Acesso (RTL8189FTV_AP em 192.168.4.1)?',
    'Restaurar AP',
    true,
    async () => {
      try {
        await fetch('/api/reset', { method: 'POST' });
        showToast('Ponto de acesso restaurado com sucesso! (192.168.4.1)', 'success');
        setTimeout(updateStatus, 2000);
      } catch (err) {
        showToast('Erro ao restaurar modo AP', 'error');
      }
    }
  );
}

// Wi-Fi Scan & Provisioning
async function scanWifi() {
  const container = document.getElementById('wifi-networks-container');
  const dashContainer = document.getElementById('dash-wifi-list');
  if (container) container.innerHTML = '<p style="color:var(--pf-text-muted); font-size:0.75rem; padding:0.5rem 0;">Escaneando espectro Wi-Fi...</p>';

  try {
    const res = await fetch('/api/scan');
    const data = await res.json();
    currentNetworks = data.networks || [];
    renderWifiNetworks();
  } catch (err) {
    if (container) container.innerHTML = '<p style="color:var(--pf-red-light); font-size:0.75rem;">Erro ao escanear redes Wi-Fi.</p>';
  }
}

function renderWifiNetworks() {
  const container = document.getElementById('wifi-networks-container');
  const dashContainer = document.getElementById('dash-wifi-list');
  const filter = (document.getElementById('wifi-filter-input')?.value || '').toLowerCase();

  const filtered = currentNetworks.filter(n => n.ssid.toLowerCase().includes(filter));
  document.getElementById('badge-wifi-count').textContent = `${filtered.length} Redes`;

  const html = filtered.map(n => {
    const isConn = currentClientSsid && n.ssid === currentClientSsid;
    const isEap = n.encryption === 'eap' || (n.flags || '').includes('EAP');
    const encPill = isEap 
      ? '<span class="pf-pill warning">802.1X EAP</span>' 
      : (n.encryption === 'open' ? '<span class="pf-pill">Aberta</span>' : '<span class="pf-pill">WPA2-PSK</span>');

    return `
      <div style="display:flex; justify-content:space-between; align-items:center; padding:0.5rem 0.6rem; border-bottom:1px solid var(--pf-border-subtle); background:${isConn ? 'var(--pf-green-surface)' : 'transparent'}; border-radius:var(--pf-radius);">
        <div>
          <div style="font-weight:700; color:var(--pf-text-primary); font-size:0.8rem; display:flex; align-items:center; gap:0.4rem;">
            ${escapeHtml(n.ssid)}
            ${isConn ? '<span class="pf-pill success"><span class="status-dot-sm live-pulse"></span>Conectada</span>' : ''}
          </div>
          <div style="font-size:0.68rem; color:var(--pf-text-muted); margin-top:2px;">
            Sinal: <strong>${n.rssi} dBm</strong> · Canal ${n.channel} · ${encPill}
          </div>
        </div>
        <div>
          ${isConn 
            ? '<button class="pf-btn pf-btn-danger pf-btn-sm" onclick="disconnectWifi()">Desconectar</button>'
            : `<button class="pf-btn pf-btn-primary pf-btn-sm" data-connect-ssid="${escapeHtml(n.ssid)}" data-encryption="${escapeHtml(isEap ? 'eap' : n.encryption)}">Conectar</button>`
          }
        </div>
      </div>
    `;
  }).join('');

  if (container) container.innerHTML = html || '<p style="color:var(--pf-text-muted); padding:0.5rem 0;">Nenhuma rede encontrada.</p>';
  if (dashContainer) dashContainer.innerHTML = html || '<p style="color:var(--pf-text-muted); padding:0.5rem 0;">Nenhuma rede encontrada.</p>';
}

document.getElementById('wifi-filter-input')?.addEventListener('input', renderWifiNetworks);
document.getElementById('btn-refresh-scan')?.addEventListener('click', scanWifi);
document.getElementById('btn-manual-network')?.addEventListener('click', () => openConnectModal('', 'psk'));

// Connect Modal
function openConnectModal(ssid, encryption) {
  document.getElementById('prov-ssid').value = ssid;
  document.getElementById('prov-password').value = '';
  document.getElementById('modal-network-title').textContent = ssid ? `Conectar à rede: ${ssid}` : 'Conectar à Rede Oculta';

  const isEap = encryption === 'eap';
  document.getElementById('group-prov-psk').style.display = isEap ? 'none' : 'block';
  document.getElementById('group-prov-eap').style.display = isEap ? 'block' : 'none';
  currentProvMode = isEap ? 'eap' : 'psk';

  document.getElementById('connect-modal').classList.add('open');
}
function closeModal() {
  document.getElementById('connect-modal').classList.remove('open');
}

// Provisioning Form Submit
document.getElementById('form-connect-wifi')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const ssid = document.getElementById('prov-ssid').value.trim();
  const btn = document.getElementById('btn-submit-provision');
  btn.textContent = 'Conectando...';
  btn.disabled = true;

  const payload = {
    ssid: ssid,
    mode: currentProvMode,
    password: currentProvMode === 'psk' ? document.getElementById('prov-password').value : document.getElementById('prov-eap-password').value,
    identity: currentProvMode === 'eap' ? document.getElementById('prov-eap-identity').value : undefined
  };

  try {
    const res = await fetch('/api/provision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast(`Tentativa de conexão a '${ssid}' enviada com watchdog de 75s!`, 'success');
      closeModal();
      setTimeout(updateStatus, 3000);
    } else {
      const err = await res.json();
      showToast(err.error || 'Falha ao iniciar provisionamento.', 'error');
    }
  } catch (err) {
    showToast('Erro de comunicação com o servidor.', 'error');
  } finally {
    btn.textContent = 'Conectar à Rede';
    btn.disabled = false;
  }
});

// AP Config Submit
document.getElementById('form-ap-config')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const ssid = document.getElementById('ap-cfg-ssid').value.trim();
  const pass = document.getElementById('ap-cfg-pass').value.trim();
  const ch = document.getElementById('ap-cfg-channel').value;

  showConfirmDialog(
    'Salvar Configuração do AP',
    `Deseja aplicar o SSID '${ssid}' no canal ${ch}? A interface sem fio será reiniciada.`,
    'Salvar e Reiniciar',
    true,
    async () => {
      try {
        const res = await fetch('/api/ap', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ssid, password: pass, channel: parseInt(ch) })
        });
        if (res.ok) {
          showToast('Configurações do Ponto de Acesso salvas e reiniciadas!', 'success');
          setTimeout(updateStatus, 2500);
        } else {
          showToast('Erro ao salvar AP.', 'error');
        }
      } catch (err) {
        showToast('Erro de comunicação.', 'error');
      }
    }
  );
});

// Services Management Engine
async function loadServices() {
  try {
    const res = await fetch('/api/services');
    const data = await res.json();
    currentServices = data.services || [];
    renderServicesTable();
  } catch (err) {
    showToast('Erro ao carregar serviços systemd.', 'error');
  }
}

function filterServices(category) {
  currentSvcFilter = category;
  document.querySelectorAll('[id^="svc-filter-"]').forEach(b => b.classList.remove('active'));
  document.getElementById(`svc-filter-${category}`)?.classList.add('active');
  renderServicesTable();
}

function renderServicesTable() {
  const container = document.getElementById('services-table-body');
  if (!container) return;

  const search = (document.getElementById('services-search-input')?.value || '').toLowerCase();
  const filtered = currentServices.filter(s => {
    const matchCat = (currentSvcFilter === 'all') || (s.category === currentSvcFilter);
    const matchSearch = s.unit.toLowerCase().includes(search) || s.desc.toLowerCase().includes(search);
    return matchCat && matchSearch;
  });

  document.getElementById('badge-services-count').textContent = `${currentServices.length}`;

  container.innerHTML = filtered.map(s => {
    let statePill = '<span class="pf-pill">Inativo</span>';
    if (s.state === 'active') {
      statePill = '<span class="pf-pill success"><span class="status-dot-sm live-pulse"></span>Ativo (running)</span>';
    } else if (s.state === 'failed') {
      statePill = '<span class="pf-pill danger" style="font-weight:700;"><span class="status-dot-sm live-pulse" style="background:var(--pf-red-light);"></span>Falhado</span>';
    } else if (s.state === 'activating') {
      statePill = '<span class="pf-pill warning"><span class="status-dot-sm live-pulse"></span>Iniciando...</span>';
    }

    const bootPill = s.enabled !== false
      ? '<span style="color:var(--pf-green-light); font-size:0.72rem; font-weight:600;">Habilitado</span>'
      : '<span style="color:var(--pf-text-muted); font-size:0.72rem;">Desabilitado</span>';

    return `
      <tr>
        <td class="pf-table-mono" style="font-weight:700; color:var(--pf-text-primary);">${escapeHtml(s.unit)}</td>
        <td class="col-category"><span class="pf-pill">${s.category.toUpperCase()}</span></td>
        <td>${escapeHtml(s.desc)}</td>
        <td>${statePill}</td>
        <td>${bootPill}</td>
        <td style="text-align:right;">
          <div style="display:inline-flex; gap:0.25rem;">
            ${s.active 
              ? `<button class="pf-btn pf-btn-secondary pf-btn-sm" onclick="serviceActionConfirm('${s.unit}', 'restart')">Reiniciar</button>
                 <button class="pf-btn pf-btn-danger pf-btn-sm" onclick="serviceActionConfirm('${s.unit}', 'stop')">Parar</button>`
              : `<button class="pf-btn pf-btn-primary pf-btn-sm" onclick="serviceActionConfirm('${s.unit}', 'start')">Iniciar</button>`
            }
            <button class="pf-btn pf-btn-secondary pf-btn-sm" onclick="viewServiceLogs('${s.unit}')" title="Ver logs desta unidade">Logs</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

document.getElementById('services-search-input')?.addEventListener('input', renderServicesTable);

function serviceActionConfirm(unit, action) {
  const actionsPt = { start: 'Iniciar', stop: 'Parar', restart: 'Reiniciar' };
  showConfirmDialog(
    `${actionsPt[action] || action} Serviço`,
    `Tem certeza que deseja executar '${action}' em '${unit}'? Isso pode afetar o funcionamento dos módulos em execução.`,
    `${actionsPt[action] || action}`,
    action === 'stop' || action === 'restart',
    async () => {
      try {
        const res = await fetch(`/api/services/${unit}/${action}`, { method: 'POST' });
        if (res.ok) {
          showToast(`Comando '${action}' enviado para ${unit}!`, 'success');
          setTimeout(loadServices, 1500);
        } else {
          showToast(`Falha ao executar ${action} em ${unit}.`, 'error');
        }
      } catch (err) {
        showToast('Erro de comunicação.', 'error');
      }
    }
  );
}

function viewServiceLogs(unit) {
  window.location.hash = 'logs';
  const sel = document.getElementById('log-unit-select');
  if (sel) {
    sel.value = unit;
    loadSystemLogs();
  }
}

// Module Hub Loader & Actions
function getModuleSvgIcon(category, id) {
  const cat = (category || '').toLowerCase();
  const modId = (id || '').toLowerCase();
  if (cat === 'ai' || modId.includes('totem') || modId.includes('mina')) {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>`;
  }
  if (cat === 'data' || modId.includes('scraping')) {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>`;
  }
  if (cat === 'display' || modId.includes('kiosk') || modId.includes('framebuffer')) {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`;
  }
  return `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>`;
}

async function loadModulesHub() {
  const container = document.getElementById('modules-container');
  if (!container) return;

  try {
    const res = await fetch('/rest/modules');
    const data = await res.json();
    const modules = data.modules || [];

    document.getElementById('badge-modules-count').textContent = `${modules.length + 1} Apps`;

    container.innerHTML = modules.map(m => {
      const state = (m.status && m.status.state) || 'available';
      const isRunning = state === 'running';
      const isInstalled = state === 'installed' || isRunning;

      let statusPill = '<span class="pf-pill">Disponível</span>';
      if (isRunning) {
        statusPill = '<span class="pf-pill success"><span class="status-dot-sm live-pulse"></span>Rodando</span>';
      } else if (isInstalled) {
        statusPill = '<span class="pf-pill info">Instalado</span>';
      }

      const req = m.requirements || {};
      const minRam = req.min_ram_mb ? `${req.min_ram_mb} MB RAM` : '32 MB MIN';

      let actionButtons = '';
      if (!isInstalled) {
        actionButtons = `
          <button class="pf-btn pf-btn-primary pf-btn-sm" style="flex:1;" onclick="moduleAction('${m.id}', 'install')">Instalar Módulo</button>
        `;
      } else {
        actionButtons = `
          <button class="pf-btn pf-btn-primary pf-btn-sm" style="flex:1;" onclick="moduleAction('${m.id}', 'start')">Iniciar</button>
          <button class="pf-btn pf-btn-danger pf-btn-sm" onclick="moduleAction('${m.id}', 'uninstall')">Desinstalar</button>
        `;
      }

      return `
        <div class="pf-card" style="justify-content:space-between; min-height:220px;">
          <div>
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.5rem;">
              <div style="background:var(--pf-bg-inset); padding:0.45rem; border-radius:var(--pf-radius); border:1px solid var(--pf-border-subtle); display:flex; align-items:center; justify-content:center;">
                ${getModuleSvgIcon(m.category, m.id)}
              </div>
              ${statusPill}
            </div>

            <h3 style="font-size:0.92rem; font-weight:700; color:var(--pf-text-primary); margin-bottom:0.15rem;">
              ${escapeHtml(m.name)}
            </h3>
            <div style="font-size:0.68rem; color:var(--pf-text-muted); margin-bottom:0.45rem;">
              ID: <code>${m.id}</code> · v${m.version || '1.0'}
            </div>

            <p style="font-size:0.75rem; color:var(--pf-text-secondary); line-height:1.35; margin-bottom:0.65rem;">
              ${escapeHtml(m.description)}
            </p>

            <div style="display:flex; gap:0.3rem; flex-wrap:wrap; margin-bottom:0.65rem;">
              <span class="pf-pill">${minRam}</span>
              <span class="pf-pill">${m.category ? m.category.toUpperCase() : 'APP'}</span>
              <span class="pf-pill">ARM64</span>
            </div>
          </div>

          <div style="display:flex; gap:0.4rem; padding-top:0.55rem; border-top:1px solid var(--pf-border-subtle);">
            ${actionButtons}
          </div>
        </div>
      `;
    }).join('');

    // Built-in Kiosk Slot
    container.innerHTML += `
      <div class="pf-card" style="justify-content:space-between; min-height:220px;">
        <div>
          <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.5rem;">
            <div style="background:var(--pf-bg-inset); padding:0.45rem; border-radius:var(--pf-radius); border:1px solid var(--pf-border-subtle); display:flex; align-items:center; justify-content:center;">
              ${getModuleSvgIcon('display', 'kiosk-display')}
            </div>
            <span class="pf-pill success"><span class="status-dot-sm live-pulse"></span>Rodando</span>
          </div>

          <h3 style="font-size:0.92rem; font-weight:700; color:var(--pf-text-primary); margin-bottom:0.15rem;">
            Kiosk HDMI Framebuffer
          </h3>
          <div style="font-size:0.68rem; color:var(--pf-text-muted); margin-bottom:0.45rem;">
            ID: <code>kiosk-display</code> · Integrado (/dev/fb0)
          </div>

          <p style="font-size:0.75rem; color:var(--pf-text-secondary); line-height:1.35; margin-bottom:0.65rem;">
            Renderizador gráfico 1080p sem flicker em /dev/fb0 com Dual QR Code e telemetria de hardware ao vivo.
          </p>

          <div style="display:flex; gap:0.3rem; flex-wrap:wrap; margin-bottom:0.65rem;">
            <span class="pf-pill">32 MB RAM</span>
            <span class="pf-pill">DISPLAY</span>
            <span class="pf-pill">NATIVO</span>
          </div>
        </div>

        <div style="display:flex; gap:0.4rem; padding-top:0.55rem; border-top:1px solid var(--pf-border-subtle);">
          <button class="pf-btn pf-btn-secondary" style="width:100%;" onclick="showToast('Controlador HDMI ativo em /dev/fb0.', 'info')">Configurar Display</button>
        </div>
      </div>
    `;
  } catch (err) {
    showToast('Falha ao consultar catálogo de módulos.', 'error');
  }
}

async function moduleAction(id, action) {
  const actionsPt = { install: 'Instalar', start: 'Iniciar', stop: 'Pausar', uninstall: 'Desinstalar' };
  showConfirmDialog(
    `${actionsPt[action] || action} Módulo`,
    `Deseja executar '${action}' no módulo '${id}'?`,
    `${actionsPt[action] || action}`,
    action === 'uninstall',
    async () => {
      try {
        const res = await fetch(`/api/modules/${id}/${action}`, { method: 'POST' });
        if (res.ok) {
          showToast(`Módulo '${id}': ação '${action}' concluída!`, 'success');
          setTimeout(loadModulesHub, 1000);
        } else {
          showToast('Erro na ação do módulo.', 'error');
        }
      } catch (err) {
        showToast('Erro de comunicação.', 'error');
      }
    }
  );
}

// Log Viewer System (RFC 5424)
async function loadSystemLogs() {
  const selUnit = document.getElementById('log-unit-select')?.value || 'all';
  const url = `/api/logs?unit=${encodeURIComponent(selUnit)}&level=${currentLogLevel}&lines=120`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentLogs = data.logs || [];
    renderLogLines();
  } catch (err) {
    console.warn('Erro ao consultar /api/logs:', err);
    const container = document.getElementById('log-container');
    if (container && currentLogs.length === 0) {
      container.innerHTML = `
        <div style="padding: 2.5rem 1rem; text-align: center; color: var(--pf-text-muted);">
          <div style="font-size: 0.85rem; font-weight: 600; color: var(--pf-orange-warning);">Aviso de conexão com o coletor de logs</div>
          <div style="font-size: 0.74rem; margin-top: 0.3rem;">Sincronizando com o daemon do sistema... (${escapeHtml(err.message)})</div>
        </div>
      `;
    }
  }
}

function filterLogLevel(lvl) {
  currentLogLevel = lvl;
  document.querySelectorAll('.log-chip').forEach(c => {
    c.classList.toggle('active', c.getAttribute('data-lvl') === lvl);
  });
  loadSystemLogs();
}

function filterLogsRealtime() {
  renderLogLines();
}

function renderLogLines() {
  const container = document.getElementById('log-container');
  if (!container) return;

  const search = (document.getElementById('log-search-input')?.value || '').toLowerCase();
  const filtered = currentLogs.filter(l => {
    const matchSearch = !search || (l.raw && l.raw.toLowerCase().includes(search)) || (l.message && l.message.toLowerCase().includes(search));
    const matchLevel = (currentLogLevel === 'all') || (l.level === currentLogLevel);
    return matchSearch && matchLevel;
  });

  if (filtered.length === 0) {
    if (currentLogs.length === 0) {
      container.innerHTML = `
        <div style="padding: 3rem 1rem; text-align: center; color: var(--pf-text-muted);">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin: 0 auto 0.6rem; opacity: 0.5;"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
          <div style="font-size: 0.85rem; font-weight: 600; color: var(--pf-text-secondary);">Aguardando telemetria de logs da TV Box</div>
          <div style="font-size: 0.74rem; margin-top: 0.3rem;">Os logs do journald ou syslog serão exibidos automaticamente assim que forem gerados.</div>
        </div>
      `;
    } else {
      container.innerHTML = `
        <div style="padding: 2.5rem 1rem; text-align: center; color: var(--pf-text-muted);">
          <div style="font-size: 0.85rem; font-weight: 600; color: var(--pf-text-secondary);">Nenhum evento corresponde aos filtros selecionados</div>
          <div style="font-size: 0.74rem; margin-top: 0.3rem;">Tente selecionar o filtro "Todos" ou limpar a barra de busca.</div>
        </div>
      `;
    }
    return;
  }

  container.innerHTML = filtered.map(l => `
    <div class="log-row log-${l.level}">
      <span class="log-time">${l.time}</span>
      <span class="log-unit">[${escapeHtml(l.unit)}]</span>
      <span class="log-msg">${escapeHtml(l.message)}</span>
    </div>
  `).join('');

  if (isLogFollowActive) {
    container.scrollTop = container.scrollHeight;
  }
}

// Follow / Tail & Scroll Detection & Isolated Terminal Scrolling
const logContainer = document.getElementById('log-container');
if (logContainer) {
  logContainer.addEventListener('scroll', () => {
    const atBottom = logContainer.scrollHeight - logContainer.scrollTop - logContainer.clientHeight < 30;
    const floatingBtn = document.getElementById('floating-scroll-btn');
    if (floatingBtn) {
      floatingBtn.style.display = atBottom ? 'none' : 'flex';
    }
  });

  // Prevent scroll chaining to parent window / document body
  logContainer.addEventListener('wheel', (e) => {
    const delta = e.deltaY;
    const up = delta < 0;
    const scrollHeight = logContainer.scrollHeight;
    const clientHeight = logContainer.clientHeight;
    const scrollTop = logContainer.scrollTop;
    const atTop = scrollTop <= 0;
    const atBottom = scrollTop + clientHeight >= scrollHeight - 1;

    if ((up && atTop) || (!up && atBottom)) {
      e.preventDefault();
    }
    e.stopPropagation();
  }, { passive: false });
}

function toggleLogFollow() {
  isLogFollowActive = !isLogFollowActive;
  const btn = document.getElementById('btn-toggle-follow');
  if (btn) {
    btn.classList.toggle('active', isLogFollowActive);
    btn.textContent = isLogFollowActive ? '● Seguir (Tail)' : '○ Pausado';
  }
  if (isLogFollowActive) scrollToLogBottom();
}

function scrollToLogBottom() {
  const container = document.getElementById('log-container');
  if (container) {
    container.scrollTop = container.scrollHeight;
    document.getElementById('floating-scroll-btn').style.display = 'none';
  }
}

function copyLogsToClipboard() {
  const lines = currentLogs.map(l => l.raw).join('\n');
  navigator.clipboard.writeText(lines).then(() => {
    showToast(`${currentLogs.length} linhas de log copiadas para a área de transferência!`, 'success');
  });
}

function exportLogsToFile() {
  const lines = currentLogs.map(l => l.raw).join('\n');
  const blob = new Blob([lines], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `forgeos_journal_${Date.now()}.log`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('Arquivo de logs exportado com sucesso!', 'success');
}

function confirmClearLogs() {
  showConfirmDialog(
    'Limpar Logs do Journal',
    'Isso irá arquivar e rotacionar os logs do journalctl no sistema (journalctl --vacuum-time=1d). Recomendado exportar antes.',
    'Limpar Logs',
    true,
    async () => {
      try {
        const res = await fetch('/api/logs/vacuum', { method: 'POST' });
        if (res.ok) {
          showToast('Logs rotacionados com sucesso!', 'success');
          setTimeout(loadSystemLogs, 1000);
        } else {
          showToast('Erro ao limpar logs.', 'error');
        }
      } catch (err) {
        showToast('Erro de comunicação.', 'error');
      }
    }
  );
}

function toggleLogSearchBar() {
  const wrapper = document.querySelector('.log-search-wrapper');
  const btn = document.getElementById('btn-toggle-log-search');
  if (!wrapper) return;
  const isHidden = window.getComputedStyle(wrapper).display === 'none';
  if (isHidden) {
    wrapper.style.display = 'flex';
    btn?.classList.add('active');
    document.getElementById('log-search-input')?.focus();
  } else {
    wrapper.style.display = 'none';
    btn?.classList.remove('active');
    const input = document.getElementById('log-search-input');
    if (input && input.value) {
      input.value = '';
      filterLogsRealtime();
    }
  }
}

function toggleSvcSearchBar() {
  const wrapper = document.querySelector('.services-search-wrapper');
  const btn = document.getElementById('btn-toggle-svc-search');
  if (!wrapper) return;
  const isHidden = window.getComputedStyle(wrapper).display === 'none';
  if (isHidden) {
    wrapper.style.display = 'flex';
    btn?.classList.add('active');
    document.getElementById('services-search-input')?.focus();
  } else {
    wrapper.style.display = 'none';
    btn?.classList.remove('active');
    const input = document.getElementById('services-search-input');
    if (input && input.value) {
      input.value = '';
      renderServicesTable();
    }
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text ?? '';
  return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function setConnectionState(connected) {
  const notice = document.getElementById('connection-notice');
  notice.hidden = connected;
  if (!connected) notice.textContent = 'Sem conexão com o dispositivo. Os dados podem estar desatualizados. Tentaremos novamente automaticamente.';
  document.querySelectorAll('#live-indicator, .sidebar-footer-card .pf-pill').forEach(el => {
    el.textContent = connected ? 'Atualizado · 5 s' : 'Sem conexão';
    el.className = connected ? 'pf-pill success' : 'pf-pill warning';
  });
}
document.addEventListener('click', event => {
  const button = event.target.closest('[data-connect-ssid]');
  if (button) openConnectModal(button.dataset.connectSsid, button.dataset.encryption);
});
