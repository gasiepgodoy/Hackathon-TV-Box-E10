const REFRESH_MS = 5000;
const API = "";

const charts = {};

function initCharts() {
  const common = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: true, labels: { color: "#e8edf4" } } },
    scales: {
      x: { ticks: { color: "#8b9cb3", maxTicksLimit: 8 } },
      y: { ticks: { color: "#8b9cb3" } },
    },
  };

  charts.temperature = new Chart(document.getElementById("chart-temperature"), {
    type: "line",
    data: { labels: [], datasets: [{ label: "Aulas Ativas", data: [], borderColor: "#3b82f6", tension: 0.3 }] },
    options: common,
  });

  charts.wind = new Chart(document.getElementById("chart-wind"), {
    type: "line",
    data: { labels: [], datasets: [{ label: "Eventos Acadêmicos", data: [], borderColor: "#22c55e", tension: 0.3 }] },
    options: common,
  });

  charts.humidity = new Chart(document.getElementById("chart-humidity"), {
    type: "line",
    data: { labels: [], datasets: [{ label: "Notícias do Portal", data: [], borderColor: "#f59e0b", tension: 0.3 }] },
    options: common,
  });
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

function formatTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function setConnectionStatus(online) {
  const el = document.getElementById("connection-status");
  el.innerHTML = online
    ? '<span class="dot dot--online"></span><span>Online</span>'
    : '<span class="dot dot--offline"></span><span>Offline</span>';
}

async function fetchJSON(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function updateMetrics(data) {
  if (!data) return;
  const m = data.metrics || {};
  document.getElementById("metric-temperature").textContent =
    m.temperature ? m.temperature.value.toFixed(0) : "—";
  document.getElementById("metric-wind").textContent =
    m.wind_speed ? m.wind_speed.value.toFixed(0) : "—";
  document.getElementById("metric-humidity").textContent =
    m.humidity ? m.humidity.value.toFixed(0) : "—";
  document.getElementById("metric-updated").textContent = formatDate(data.recorded_at);
}

function updateStatus(statusData) {
  const collector = statusData.collector || {};
  const badge = document.getElementById("collector-badge");
  badge.textContent = collector.is_running ? "Ativo" : "Parado";
  badge.className = `badge badge--${collector.is_running ? "running" : "stopped"}`;

  document.getElementById("stat-records").textContent =
    statusData.database?.total_records ?? collector.total_records ?? 0;
  document.getElementById("stat-success").textContent = formatDate(collector.last_success_at);
  document.getElementById("stat-error").textContent =
    collector.last_error_message || formatDate(collector.last_error_at) || "Nenhum";
}

function updateCharts(records) {
  const sorted = [...records].reverse();
  const labels = sorted.map((r) => formatTime(r.recorded_at));

  charts.temperature.data.labels = labels;
  charts.temperature.data.datasets[0].data = sorted.map((r) => r.metrics?.temperature?.value ?? null);
  charts.temperature.update("none");

  charts.wind.data.labels = labels;
  charts.wind.data.datasets[0].data = sorted.map((r) => r.metrics?.wind_speed?.value ?? null);
  charts.wind.update("none");

  charts.humidity.data.labels = labels;
  charts.humidity.data.datasets[0].data = sorted.map((r) => r.metrics?.humidity?.value ?? null);
  charts.humidity.update("none");
}

async function refreshDashboard() {
  try {
    const [status, current, recent] = await Promise.all([
      fetchJSON("/status"),
      fetchJSON("/dados-atuais"),
      fetchJSON("/ultimas-atualizacoes?hours=2"),
    ]);

    setConnectionStatus(true);
    updateStatus(status);
    updateMetrics(current.data);
    updateCharts(recent.records || []);
  } catch (err) {
    console.error("Erro ao atualizar dashboard:", err);
    setConnectionStatus(false);
  }
}

function addMessage(text, type) {
  const container = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.className = `message message--${type}`;
  div.textContent = text;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

async function handleChatSubmit(e) {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const question = input.value.trim();
  if (!question) return;

  addMessage(question, "user");
  input.value = "";

  try {
    const res = await fetch(`${API}/agente/perguntar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pergunta: question }),
    });
    const data = await res.json();
    addMessage(data.resposta || "Sem resposta.", "bot");
  } catch (err) {
    addMessage("Erro ao consultar o agente.", "bot");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  refreshDashboard();
  setInterval(refreshDashboard, REFRESH_MS);
  document.getElementById("chat-form").addEventListener("submit", handleChatSubmit);
});
