import json
import time
import shutil
import socket
import subprocess
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque
from glob import glob

from config import EDGEBOX_DATA_DIR, WEB_DIR

DATASET_PATH = EDGEBOX_DATA_DIR / "edgebox_metrics.jsonl"
LATEST_PATH = EDGEBOX_DATA_DIR / "edgebox_latest.json"
MODEL_PATH = EDGEBOX_DATA_DIR / "edgebox_model_update.json"
GLOBAL_MODEL_PATH = EDGEBOX_DATA_DIR / "edgebox_global_model.json"
STATE_PATH = EDGEBOX_DATA_DIR / "edgebox_state.json"
INDEX_PATH = WEB_DIR / "legacy.html"
LIVE_PATH = WEB_DIR / "edgebox_live.json"
HISTORY_PATH = WEB_DIR / "edgebox_history.json"

AUTOENCODER_START = "<!-- AUTOENCODER_BLOCK_START -->"
AUTOENCODER_END = "<!-- AUTOENCODER_BLOCK_END -->"

NODE_ID = socket.gethostname()
UPDATE_INTERVAL_SECONDS = 10


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def read_text(path, default=""):
    try:
        return Path(path).read_text().strip()
    except Exception:
        return default


def read_cpu_usage():
    def read_cpu_line():
        line = Path("/proc/stat").read_text().splitlines()[0]
        parts = [int(x) for x in line.split()[1:]]
        idle = parts[3] + parts[4]
        total = sum(parts)
        return total, idle

    try:
        total1, idle1 = read_cpu_line()
        time.sleep(0.25)
        total2, idle2 = read_cpu_line()

        total_delta = total2 - total1
        idle_delta = idle2 - idle1

        if total_delta <= 0:
            return 0.0

        usage = 100.0 * (1.0 - idle_delta / total_delta)
        return max(0.0, min(100.0, usage))
    except Exception:
        return 0.0


def read_loadavg():
    try:
        parts = Path("/proc/loadavg").read_text().split()
        return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception:
        return 0.0, 0.0, 0.0


def read_memory():
    try:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            info[key] = int(value.strip().split()[0])

        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        used = total - available

        percent = (used / total * 100.0) if total else 0.0

        return {
            "total_mb": round(total / 1024, 1),
            "used_mb": round(used / 1024, 1),
            "available_mb": round(available / 1024, 1),
            "percent": round(percent, 1),
        }
    except Exception:
        return {
            "total_mb": 0,
            "used_mb": 0,
            "available_mb": 0,
            "percent": 0,
        }


def read_disk():
    try:
        usage = shutil.disk_usage("/")
        percent = usage.used / usage.total * 100.0

        return {
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "percent": round(percent, 1),
        }
    except Exception:
        return {
            "total_gb": 0,
            "used_gb": 0,
            "free_gb": 0,
            "percent": 0,
        }


def read_temperature():
    temps = []

    for path in glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            raw = float(Path(path).read_text().strip())
            temp = raw / 1000.0 if raw > 200 else raw

            if 0 <= temp <= 120:
                temps.append(temp)
        except Exception:
            pass

    if not temps:
        return None

    return round(max(temps), 1)


def read_uptime():
    try:
        seconds = float(Path("/proc/uptime").read_text().split()[0])
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)

        return {
            "seconds": int(seconds),
            "human": f"{days}d {hours}h {minutes}min",
        }
    except Exception:
        return {
            "seconds": 0,
            "human": "0d 0h 0min",
        }


def read_network_counters():
    rx = 0
    tx = 0

    try:
        lines = Path("/proc/net/dev").read_text().splitlines()[2:]

        for line in lines:
            iface, data = line.split(":", 1)
            iface = iface.strip()

            if iface == "lo":
                continue

            parts = data.split()
            rx += int(parts[0])
            tx += int(parts[8])
    except Exception:
        pass

    return rx, tx


def read_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def write_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def read_network_speed():
    current_rx, current_tx = read_network_counters()
    current_time = time.time()

    state = read_state()

    previous_rx = state.get("rx_bytes")
    previous_tx = state.get("tx_bytes")
    previous_time = state.get("timestamp")

    rx_kbps = 0.0
    tx_kbps = 0.0

    if previous_rx is not None and previous_tx is not None and previous_time is not None:
        dt = max(current_time - previous_time, 1)

        rx_kbps = ((current_rx - previous_rx) * 8) / dt / 1000
        tx_kbps = ((current_tx - previous_tx) * 8) / dt / 1000

        rx_kbps = max(0.0, rx_kbps)
        tx_kbps = max(0.0, tx_kbps)

    state["rx_bytes"] = current_rx
    state["tx_bytes"] = current_tx
    state["timestamp"] = current_time
    write_state(state)

    return {
        "rx_kbps": round(rx_kbps, 2),
        "tx_kbps": round(tx_kbps, 2),
        "rx_mb_total": round(current_rx / (1024 ** 2), 2),
        "tx_mb_total": round(current_tx / (1024 ** 2), 2),
    }


def read_latency(host="8.8.8.8"):
    try:
        output = subprocess.check_output(
            ["ping", "-c", "1", "-W", "1", host],
            stderr=subprocess.DEVNULL,
            text=True,
        )

        match = re.search(r"time[=<]([0-9.]+)", output)

        if match:
            return round(float(match.group(1)), 1)

        return None
    except Exception:
        return None


def get_ips():
    try:
        output = subprocess.check_output(["hostname", "-I"], text=True).strip()
        return output
    except Exception:
        return ""


def normalize_metrics(metrics):
    temp = metrics["temperature_c"]
    latency = metrics["latency_ms"]

    temp_norm = 0.0 if temp is None else max(0.0, min(1.0, (temp - 35.0) / 45.0))
    latency_norm = 1.0 if latency is None else max(0.0, min(1.0, latency / 300.0))
    load_norm = max(0.0, min(1.0, metrics["load1"] / 4.0))

    return [
        1.0,
        metrics["cpu_percent"] / 100.0,
        metrics["ram_percent"] / 100.0,
        temp_norm,
        metrics["disk_percent"] / 100.0,
        latency_norm,
        load_norm,
    ]


def heuristic_risk(metrics):
    temp = metrics["temperature_c"]
    latency = metrics["latency_ms"]

    cpu_score = metrics["cpu_percent"] / 100.0
    ram_score = metrics["ram_percent"] / 100.0
    disk_score = metrics["disk_percent"] / 100.0
    load_score = max(0.0, min(1.0, metrics["load1"] / 4.0))

    if temp is None:
        temp_score = 0.2
    else:
        temp_score = max(0.0, min(1.0, (temp - 35.0) / 45.0))

    if latency is None:
        latency_score = 0.8
    else:
        latency_score = max(0.0, min(1.0, latency / 300.0))

    risk = (
        0.25 * cpu_score +
        0.22 * ram_score +
        0.22 * temp_score +
        0.12 * disk_score +
        0.10 * latency_score +
        0.09 * load_score
    )

    return max(0.0, min(1.0, risk))


def status_from_risk(risk):
    if risk >= 0.75:
        return "CRÍTICO"
    if risk >= 0.55:
        return "ALERTA"
    if risk >= 0.35:
        return "ATENÇÃO"
    return "ESTÁVEL"


def read_recent_samples(limit=300):
    if not DATASET_PATH.exists():
        return []

    samples = deque(maxlen=limit)

    try:
        with DATASET_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line:
                    continue

                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return list(samples)


def read_history(days, max_points):
    cutoff = datetime.now() - timedelta(days=days)
    buckets = {}

    if not DATASET_PATH.exists():
        return []

    try:
        with DATASET_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    sample = json.loads(line)
                    timestamp = datetime.fromisoformat(sample["timestamp"])
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue

                if timestamp < cutoff:
                    continue

                bucket_seconds = max(60, int(days * 86400 / max_points))
                bucket_start = int(timestamp.timestamp() // bucket_seconds) * bucket_seconds
                bucket = buckets.setdefault(bucket_start, [])
                bucket.append(sample)
    except OSError:
        return []

    result = []
    for bucket_start in sorted(buckets):
        bucket = buckets[bucket_start]
        numeric = {}
        for sample in bucket:
            for key, value in sample.items():
                if key == "timestamp":
                    continue
                try:
                    numeric.setdefault(key, []).append(float(value))
                except (TypeError, ValueError):
                    continue

        point = {
            "timestamp": datetime.fromtimestamp(bucket_start).isoformat(timespec="seconds")
        }
        for key, values in numeric.items():
            if not values:
                continue
            point[key] = round(sum(values) / len(values), 4)
        result.append(point)

    return result[-max_points:]


def train_local_model(samples):
    """
    Modelo linear local extremamente leve.
    Ele aprende a aproximar a função de risco heurística usando os dados históricos do próprio nó.
    Em uma versão federada real, cada TV Box enviaria estes pesos para um agregador FedAvg.
    """

    if not samples:
        return [0.0] * 7

    weights = [0.0] * 7
    learning_rate = 0.05
    epochs = 40

    for _ in range(epochs):
        for sample in samples:
            x = normalize_metrics(sample)
            y = sample.get("target_risk", heuristic_risk(sample))

            pred = sum(w * xi for w, xi in zip(weights, x))
            error = pred - y

            for i in range(len(weights)):
                weights[i] -= learning_rate * error * x[i]

    return [round(w, 6) for w in weights]


def infer_with_model(weights, metrics):
    x = normalize_metrics(metrics)
    pred = sum(w * xi for w, xi in zip(weights, x))
    return max(0.0, min(1.0, pred))


def collect_metrics():
    memory = read_memory()
    disk = read_disk()
    load1, load5, load15 = read_loadavg()
    network = read_network_speed()
    uptime = read_uptime()

    metrics = {
        "timestamp": now_iso(),
        "node_id": NODE_ID,
        "node_role": "edge_node",
        "cpu_percent": round(read_cpu_usage(), 1),
        "ram_percent": memory["percent"],
        "ram_used_mb": memory["used_mb"],
        "ram_total_mb": memory["total_mb"],
        "disk_percent": disk["percent"],
        "disk_used_gb": disk["used_gb"],
        "disk_total_gb": disk["total_gb"],
        "temperature_c": read_temperature(),
        "load1": round(load1, 2),
        "load5": round(load5, 2),
        "load15": round(load15, 2),
        "latency_ms": read_latency(),
        "rx_kbps": network["rx_kbps"],
        "tx_kbps": network["tx_kbps"],
        "rx_mb_total": network["rx_mb_total"],
        "tx_mb_total": network["tx_mb_total"],
        "uptime_seconds": uptime["seconds"],
        "uptime_human": uptime["human"],
        "ip_addresses": get_ips(),
    }

    metrics["target_risk"] = round(heuristic_risk(metrics), 4)

    return metrics


def append_dataset(metrics):
    with DATASET_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + "\n")


def make_svg_chart(samples, key, title, suffix="", width=900, height=260):
    """
    Gráfico SVG didático e interativo.
    Mostra escala, linhas de referência, valor atual, média e tooltip nos pontos.
    """
    import html as _html

    chart_config = {
        "cpu_percent": {
            "min": 0,
            "max": 100,
            "unit": "%",
            "good": 50,
            "attention": 75,
            "help": "Uso da CPU. Quanto menor, melhor.",
        },
        "ram_percent": {
            "min": 0,
            "max": 100,
            "unit": "%",
            "good": 60,
            "attention": 80,
            "help": "Uso da memória RAM. Valores altos indicam pouca folga.",
        },
        "temperature_c": {
            "min": 20,
            "max": 90,
            "unit": " °C",
            "good": 55,
            "attention": 70,
            "help": "Temperatura interna da TV Box.",
        },
        "inferred_risk": {
            "min": 0,
            "max": 1,
            "unit": "",
            "good": 0.35,
            "attention": 0.55,
            "help": "Risco operacional do nó. Quanto mais próximo de 1, pior.",
        },
    }

    cfg = chart_config.get(key, {
        "min": 0,
        "max": 100,
        "unit": suffix,
        "good": 50,
        "attention": 75,
        "help": "Histórico da métrica coletada.",
    })

    unit = cfg["unit"]

    data = []

    for sample in samples[-40:]:
        value = sample.get(key)

        if value is None:
            continue

        try:
            value = float(value)
        except Exception:
            continue

        data.append({
            "value": value,
            "label": str(sample.get("timestamp", "sem horário")),
        })

    if len(data) < 2:
        return f"""
        <div class="chart">
            <h3>{title}</h3>
            <p class="small">Coletando dados suficientes para montar o gráfico...</p>
        </div>
        """

    y_min = cfg["min"]
    y_max = cfg["max"]

    plot_x = 70
    plot_y = 22
    plot_w = width - 100
    plot_h = height - 70

    def clamp(v):
        return max(y_min, min(y_max, v))

    def x_pos(i):
        return plot_x + i * (plot_w / (len(data) - 1))

    def y_pos(v):
        v = clamp(v)
        return plot_y + plot_h - ((v - y_min) / (y_max - y_min)) * plot_h

    values = [item["value"] for item in data]
    last = values[-1]
    first = values[0]
    avg_value = sum(values) / len(values)

    if last >= cfg["attention"]:
        level = "ALERTA"
        line_color = "#fb7185"
    elif last >= cfg["good"]:
        level = "ATENÇÃO"
        line_color = "#facc15"
    else:
        level = "NORMAL"
        line_color = "#38bdf8"

    points = []
    circles = ""

    for i, item in enumerate(data):
        value = item["value"]
        label = item["label"]

        x = x_pos(i)
        y = y_pos(value)

        points.append(f"{x:.1f},{y:.1f}")

        tooltip = f"{title}\nHorário: {label}\nValor: {value:.2f}{unit}"

        circles += f"""
            <circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" class="data-point">
                <title>{_html.escape(tooltip)}</title>
            </circle>
        """

    ticks = [y_min + (y_max - y_min) * index / 4 for index in range(5)]

    grid = ""
    labels_y = ""

    for tick in ticks:
        y = y_pos(tick)
        label = f"{tick:.2f}" if key == "inferred_risk" else f"{tick:.1f}{unit}"

        grid += f"""
            <line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_w}" y2="{y:.1f}" class="grid-line" />
        """

        labels_y += f"""
            <text x="{plot_x - 10}" y="{y + 4:.1f}" class="axis-label" text-anchor="end">{label}</text>
        """

    good_y = y_pos(cfg["good"])
    attention_y = y_pos(cfg["attention"])

    refs = f"""
        <line x1="{plot_x}" y1="{good_y:.1f}" x2="{plot_x + plot_w}" y2="{good_y:.1f}" class="ref-line attention-line" />
        <text x="{plot_x + plot_w - 5}" y="{good_y - 6:.1f}" class="ref-label" text-anchor="end">atenção</text>

        <line x1="{plot_x}" y1="{attention_y:.1f}" x2="{plot_x + plot_w}" y2="{attention_y:.1f}" class="ref-line alert-line" />
        <text x="{plot_x + plot_w - 5}" y="{attention_y - 6:.1f}" class="ref-label" text-anchor="end">alerta</text>
    """

    def relative_time(timestamp):
        try:
            current = datetime.fromisoformat(data[-1]["label"])
            point = datetime.fromisoformat(timestamp)
            total_minutes = max(0, int((current - point).total_seconds() // 60))
        except (TypeError, ValueError):
            return ""

        if total_minutes >= 1440:
            return f"-{total_minutes // 1440}d"
        if total_minutes >= 60:
            return f"-{total_minutes // 60}h"
        if total_minutes > 0:
            return f"-{total_minutes}min"
        return "agora"

    mid = len(data) // 2

    x_labels = f"""
        <text x="{x_pos(0):.1f}" y="{plot_y + plot_h + 30}" class="axis-label" text-anchor="middle">{relative_time(data[0]["label"])}</text>
        <text x="{x_pos(mid):.1f}" y="{plot_y + plot_h + 30}" class="axis-label" text-anchor="middle">{relative_time(data[mid]["label"])}</text>
        <text x="{x_pos(len(data)-1):.1f}" y="{plot_y + plot_h + 30}" class="axis-label" text-anchor="middle">agora</text>
    """

    last_x = x_pos(len(data) - 1)
    last_y = y_pos(last)

    chips = ""

    for item in data[-5:]:
        chips += f"""
        <span style="display:inline-block;background:#334155;color:#e5e7eb;padding:6px 9px;margin:4px;border-radius:999px;font-weight:bold;">
            {item["value"]:.2f}{unit}
        </span>
        """

    return f"""
    <div class="chart live-chart" data-key="{key}" data-min="{y_min}" data-max="{y_max}" data-unit="{_html.escape(unit)}">
        <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:12px;">
            <div>
                <h3>{title}</h3>
                <p class="small">{cfg["help"]}</p>
                <p class="small">Escala Y: {y_min:.2f}{unit} a {y_max:.2f}{unit}</p>
            </div>

            <div style="text-align:right;min-width:150px;">
                <div class="live-current" style="font-size:28px;font-weight:bold;">{last:.2f}{unit}</div>
                <div class="live-level" style="font-weight:bold;">{level}</div>
            </div>
        </div>

        <svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="width:100%;height:280px;background:#020617;border-radius:12px;">
            <style>
                .grid-line {{
                    stroke: #334155;
                    stroke-width: 1;
                }}

                .ref-line {{
                    stroke-width: 2;
                    stroke-dasharray: 7 7;
                }}

                .attention-line {{
                    stroke: #facc15;
                }}

                .alert-line {{
                    stroke: #fb7185;
                }}

                .ref-label {{
                    fill: #cbd5e1;
                    font-size: 16px;
                    font-weight: bold;
                }}

                .axis-label {{
                    fill: #cbd5e1;
                    font-size: 15px;
                }}

                .metric-line {{
                    fill: none;
                    stroke: {line_color};
                    stroke-width: 5;
                    stroke-linecap: round;
                    stroke-linejoin: round;
                }}

                .data-point {{
                    fill: #0f172a;
                    stroke: {line_color};
                    stroke-width: 4;
                    cursor: pointer;
                }}

                .data-point:hover {{
                    fill: #ffffff;
                    stroke: #ffffff;
                }}

                .last-point {{
                    fill: #ffffff;
                    stroke: {line_color};
                    stroke-width: 5;
                }}

                .last-label {{
                    fill: #ffffff;
                    font-size: 17px;
                    font-weight: bold;
                }}
            </style>

            {grid}
            {labels_y}
            {refs}

            <line x1="{plot_x}" y1="{plot_y}" x2="{plot_x}" y2="{plot_y + plot_h}" class="grid-line" />
            <line x1="{plot_x}" y1="{plot_y + plot_h}" x2="{plot_x + plot_w}" y2="{plot_y + plot_h}" class="grid-line" />

            <polyline points="{' '.join(points)}" class="metric-line" />

            {circles}

            <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="8" class="last-point">
                <title>Valor atual: {last:.2f}{unit}</title>
            </circle>

            <text x="{last_x - 10:.1f}" y="{last_y - 14:.1f}" class="last-label" text-anchor="end">
                {last:.2f}{unit}
            </text>

            {x_labels}
        </svg>

        <div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:10px;margin-bottom:8px;color:#dbeafe;">
            <span style="background:#0f172a;padding:8px 10px;border-radius:10px;">Primeiro: <b>{first:.2f}{unit}</b></span>
            <span style="background:#0f172a;padding:8px 10px;border-radius:10px;">Média: <b>{avg_value:.2f}{unit}</b></span>
            <span style="background:#0f172a;padding:8px 10px;border-radius:10px;">Atual: <b>{last:.2f}{unit}</b></span>
        </div>

        <div class="small live-chips">
            Últimos valores: {chips}
        </div>
    </div>
    """

def save_model_files(weights, samples_count):
    update = {
        "created_at": now_iso(),
        "node_id": NODE_ID,
        "model_type": "linear_regression_lightweight",
        "federated_method_ready": "FedAvg",
        "features": [
            "bias",
            "cpu_percent",
            "ram_percent",
            "temperature_c",
            "disk_percent",
            "latency_ms",
            "load1",
        ],
        "samples": samples_count,
        "weights": weights,
        "note": "Este arquivo representa a atualização local que poderia ser enviada para um agregador federado.",
    }

    MODEL_PATH.write_text(json.dumps(update, indent=2, ensure_ascii=False), encoding="utf-8")

    global_model = {
        "created_at": now_iso(),
        "aggregation": "single_node_now__future_fedavg_multi_node",
        "nodes": [NODE_ID],
        "global_weights": weights,
        "note": "No protótipo atual há apenas um nó físico. Com várias TV Boxes, este arquivo seria resultado da média federada dos modelos locais.",
    }

    GLOBAL_MODEL_PATH.write_text(json.dumps(global_model, indent=2, ensure_ascii=False), encoding="utf-8")


def save_dashboard(metrics, samples, weights, inferred_risk):
    status = status_from_risk(inferred_risk)

    if status == "ESTÁVEL":
        status_class = "stable"
    elif status == "ATENÇÃO":
        status_class = "attention"
    elif status == "ALERTA":
        status_class = "alert"
    else:
        status_class = "critical"

    temp = "N/A" if metrics["temperature_c"] is None else f"{metrics['temperature_c']:.1f} °C"
    latency = "falha" if metrics["latency_ms"] is None else f"{metrics['latency_ms']:.1f} ms"

    chart_cpu = make_svg_chart(samples, "cpu_percent", "Histórico de CPU", "%")
    chart_ram = make_svg_chart(samples, "ram_percent", "Histórico de RAM", "%")
    chart_temp = make_svg_chart(samples, "temperature_c", "Histórico de Temperatura", " °C")
    chart_risk = make_svg_chart(samples, "inferred_risk", "Histórico de Risco do Nó", "")

    LIVE_PATH.write_text(
        json.dumps({"updated_at": metrics["timestamp"], "samples": samples[-40:]}, ensure_ascii=False),
        encoding="utf-8",
    )
    HISTORY_PATH.write_text(
        json.dumps(
            {
                "updated_at": metrics["timestamp"],
                "today": read_history(1, 288),
                "week": read_history(7, 336),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="{UPDATE_INTERVAL_SECONDS}">
    <title>EdgeBox FL - Nó de Borda</title>
    <style>
        body {{
            margin: 0;
            padding: 28px;
            background: #0f172a;
            color: #e5e7eb;
            font-family: Arial, sans-serif;
        }}

        h1 {{
            margin: 0;
            font-size: 42px;
            text-align: center;
        }}

        .subtitle {{
            text-align: center;
            color: #cbd5e1;
            margin-top: 8px;
            margin-bottom: 24px;
        }}

        .status {{
            max-width: 900px;
            margin: 0 auto 24px auto;
            padding: 20px;
            border-radius: 18px;
            text-align: center;
            font-size: 24px;
            font-weight: bold;
        }}

        .stable {{ background: #14532d; }}
        .attention {{ background: #854d0e; }}
        .alert {{ background: #9a3412; }}
        .critical {{ background: #7f1d1d; }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 16px;
            margin-bottom: 26px;
        }}

        .card {{
            background: #1e293b;
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.25);
        }}

        .card h2 {{
            margin-top: 0;
            font-size: 16px;
            color: #93c5fd;
        }}

        .value {{
            font-size: 28px;
            font-weight: bold;
        }}

        .small {{
            color: #cbd5e1;
            font-size: 14px;
        }}

        .section {{
            background: #111827;
            border-radius: 18px;
            padding: 22px;
            margin-bottom: 26px;
        }}

        .section h2 {{
            margin-top: 0;
        }}

        .chart {{
            background: #1e293b;
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 16px;
        }}

        .chart h3 {{
            margin-top: 0;
            color: #bfdbfe;
        }}

        svg {{
            width: 100%;
            height: 160px;
            background: #020617;
            border-radius: 10px;
        }}

        polyline {{
            fill: none;
            stroke: #38bdf8;
            stroke-width: 4;
        }}

        code {{
            color: #86efac;
        }}

        .footer {{
            text-align: center;
            color: #94a3b8;
            font-size: 14px;
            margin-top: 28px;
        }}
    </style>
</head>
<body>
    <h1>EdgeBox FL</h1>
    <p class="subtitle">
        Validação de TV Box reaproveitada como nó de coleta, processamento local e inteligência de borda
    </p>

    <div class="status {status_class}">
        Status do nó: {status} | Risco operacional: {inferred_risk:.2f}
    </div>

    <div class="grid">
        <div class="card">
            <h2>Nó</h2>
            <div class="value">{NODE_ID}</div>
            <p class="small">Função: edge node</p>
        </div>

        <div class="card">
            <h2>CPU</h2>
            <div class="value">{metrics['cpu_percent']:.1f}%</div>
            <p class="small">Uso instantâneo do processador</p>
        </div>

        <div class="card">
            <h2>Memória RAM</h2>
            <div class="value">{metrics['ram_percent']:.1f}%</div>
            <p class="small">{metrics['ram_used_mb']:.0f} MB / {metrics['ram_total_mb']:.0f} MB</p>
        </div>

        <div class="card">
            <h2>Temperatura</h2>
            <div class="value">{temp}</div>
            <p class="small">Leitura interna do SoC</p>
        </div>

        <div class="card">
            <h2>Disco</h2>
            <div class="value">{metrics['disk_percent']:.1f}%</div>
            <p class="small">{metrics['disk_used_gb']:.2f} GB / {metrics['disk_total_gb']:.2f} GB</p>
        </div>

        <div class="card">
            <h2>Latência</h2>
            <div class="value">{latency}</div>
            <p class="small">Teste ICMP para 8.8.8.8</p>
        </div>

        <div class="card">
            <h2>Rede</h2>
            <div class="value">{metrics['rx_kbps']:.1f} kbps</div>
            <p class="small">RX atual | TX: {metrics['tx_kbps']:.1f} kbps</p>
        </div>

        <div class="card">
            <h2>Uptime</h2>
            <div class="value">{metrics['uptime_human']}</div>
            <p class="small">Tempo ligado sem reiniciar</p>
        </div>
    </div>

    <div class="section">
        <h2>Pipeline validado</h2>
        <p>
            Este nó coleta dados internos da TV Box, salva histórico local, processa os dados,
            roda um modelo leve de inferência e gera uma atualização de modelo que pode ser enviada
            a um servidor agregador federado.
        </p>
        <p>
            <b>Coleta → armazenamento → modelo local → inferência → atualização federada → dashboard</b>
        </p>
    </div>

    <div class="section">
        <h2>Modelo local</h2>
        <p>
            Modelo: <b>regressão linear leve</b> treinada localmente com os dados do próprio nó.
        </p>
        <p>
            Amostras locais utilizadas: <b>{len(samples)}</b>
        </p>
        <p>
            Pesos locais exportados em: <code>edgebox_model_update.json</code>
        </p>
        <p>
            Pesos atuais: <code>{[round(w, 4) for w in weights]}</code>
        </p>
    </div>

    <div class="section">
        <h2>Histórico recente</h2>
        <div class="history-controls" style="display:flex;gap:10px;margin-bottom:16px;">
            <button type="button" class="history-period active" data-period="live">Ao vivo</button>
            <button type="button" class="history-period" data-period="today">Hoje</button>
            <button type="button" class="history-period" data-period="week">7 dias</button>
        </div>
        {chart_cpu}
        {chart_ram}
        {chart_temp}
        {chart_risk}
    </div>

    <div class="section">
        <h2>Caminho de expansão</h2>
        <p>
            Depois de validar que a TV Box consegue operar como nó confiável de borda,
            a mesma arquitetura pode receber sensores externos: temperatura, umidade,
            chuva, nível da água, qualidade do ar, ruído, presença e dados comunitários.
        </p>
        <p>
            Assim, antes de espalhar sensores pela cidade, o projeto valida se a infraestrutura
            computacional realmente aguenta operar de forma contínua.
        </p>
    </div>

    <div class="footer">
        Última atualização: {metrics['timestamp']} |
        IPs: {metrics['ip_addresses']} |
        Atualização automática a cada {UPDATE_INTERVAL_SECONDS}s
    </div>
    <script src="/live_charts.js"></script>
</body>
</html>
"""

    autoencoder_block = ""
    dashboard_path = WEB_DIR / "dashboard.html"
    for path in (INDEX_PATH, dashboard_path):
        try:
            existing = path.read_text(encoding="utf-8")
        except Exception:
            continue

        if AUTOENCODER_START in existing and AUTOENCODER_END in existing:
            autoencoder_block = existing.split(AUTOENCODER_START, 1)[1].split(
                AUTOENCODER_END, 1
            )[0]
            autoencoder_block = (
                AUTOENCODER_START + autoencoder_block + AUTOENCODER_END
            )
            break

    if autoencoder_block and '<div class="footer">' in html:
        html = html.replace(
            '<div class="footer">',
            autoencoder_block + '\n\n        <div class="footer">',
            1,
        )

    INDEX_PATH.write_text(html, encoding="utf-8")


def main():
    metrics = collect_metrics()

    inferred_risk = heuristic_risk(metrics)
    metrics["inferred_risk"] = round(inferred_risk, 4)
    metrics["status"] = status_from_risk(inferred_risk)

    append_dataset(metrics)

    payload = json.dumps(metrics, indent=2, ensure_ascii=False)
    LATEST_PATH.write_text(payload, encoding="utf-8")
    LIVE_PATH.write_text(payload, encoding="utf-8")

    try:
        samples = read_recent_samples(60)
        (WEB_DIR / "edgebox_history.json").write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        pass

    print(f"[{metrics['timestamp']}] EdgeBox atualizado (fast) | risco={inferred_risk:.2f} | status={metrics['status']}")


if __name__ == "__main__":
    main()
