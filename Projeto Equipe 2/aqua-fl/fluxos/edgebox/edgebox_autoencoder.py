import json
import sys
from pathlib import Path
from datetime import datetime

import numpy as np

from config import EDGEBOX_DATA_DIR, WEB_DIR

DATASET_PATH = EDGEBOX_DATA_DIR / "edgebox_metrics.jsonl"
LATEST_PATH = EDGEBOX_DATA_DIR / "edgebox_latest.json"

MODEL_PATH = EDGEBOX_DATA_DIR / "edgebox_autoencoder_model.json"
UPDATE_PATH = EDGEBOX_DATA_DIR / "edgebox_autoencoder_update.json"
LATEST_AE_PATH = EDGEBOX_DATA_DIR / "edgebox_autoencoder_latest.json"
DASHBOARD_PATH = WEB_DIR / "autoencoder.html"

FEATURES = [
    "cpu_percent",
    "ram_percent",
    "temperature_c",
    "disk_percent",
    "latency_ms",
    "load1",
]

FEATURE_LABELS = {
    "cpu_percent": "CPU",
    "ram_percent": "RAM",
    "temperature_c": "Temperatura",
    "disk_percent": "Disco",
    "latency_ms": "Latência",
    "load1": "Carga do sistema",
}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def clip(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def normalize_sample(sample):
    cpu = clip(float(sample.get("cpu_percent", 0)) / 100.0)
    ram = clip(float(sample.get("ram_percent", 0)) / 100.0)

    temp = sample.get("temperature_c")
    if temp is None:
        temp_norm = 0.0
    else:
        temp_norm = clip((float(temp) - 20.0) / 70.0)

    disk = clip(float(sample.get("disk_percent", 0)) / 100.0)

    latency = sample.get("latency_ms")
    if latency is None:
        latency_norm = 1.0
    else:
        latency_norm = clip(float(latency) / 300.0)

    load = clip(float(sample.get("load1", 0)) / 4.0)

    return np.array([cpu, ram, temp_norm, disk, latency_norm, load], dtype=np.float64)


def load_samples(limit=1200):
    samples = []

    if not DATASET_PATH.exists():
        return samples

    lines = DATASET_PATH.read_text(encoding="utf-8").splitlines()

    for line in lines[-limit:]:
        try:
            sample = json.loads(line)
            samples.append(sample)
        except Exception:
            pass

    return samples


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def forward(model, x):
    W1 = np.array(model["W1"], dtype=np.float64)
    b1 = np.array(model["b1"], dtype=np.float64)
    W2 = np.array(model["W2"], dtype=np.float64)
    b2 = np.array(model["b2"], dtype=np.float64)

    z1 = x @ W1 + b1
    h = np.tanh(z1)

    z2 = h @ W2 + b2
    y = sigmoid(z2)

    return h, y


def reconstruction_error(x, y):
    return float(np.mean((x - y) ** 2))


def init_model(input_size=6, hidden_size=3, seed=42):
    rng = np.random.default_rng(seed)

    return {
        "model_type": "lightweight_autoencoder",
        "input_size": input_size,
        "hidden_size": hidden_size,
        "features": FEATURES,
        "W1": rng.normal(0, 0.15, size=(input_size, hidden_size)).tolist(),
        "b1": np.zeros(hidden_size).tolist(),
        "W2": rng.normal(0, 0.15, size=(hidden_size, input_size)).tolist(),
        "b2": np.zeros(input_size).tolist(),
        "threshold": 0.01,
        "created_at": now_iso(),
    }


def train_autoencoder(samples, epochs=250, lr=0.04):
    X = np.array([normalize_sample(s) for s in samples], dtype=np.float64)

    model = init_model(input_size=X.shape[1], hidden_size=3)

    W1 = np.array(model["W1"], dtype=np.float64)
    b1 = np.array(model["b1"], dtype=np.float64)
    W2 = np.array(model["W2"], dtype=np.float64)
    b2 = np.array(model["b2"], dtype=np.float64)

    rng = np.random.default_rng(123)

    for epoch in range(epochs):
        order = rng.permutation(len(X))
        total_loss = 0.0

        for idx in order:
            x = X[idx]

            z1 = x @ W1 + b1
            h = np.tanh(z1)

            z2 = h @ W2 + b2
            y = sigmoid(z2)

            error = y - x
            loss = np.mean(error ** 2)
            total_loss += loss

            dy = (2.0 / len(x)) * error * y * (1.0 - y)

            dW2 = np.outer(h, dy)
            db2 = dy

            dh = dy @ W2.T
            dz1 = dh * (1.0 - h ** 2)

            dW1 = np.outer(x, dz1)
            db1 = dz1

            W2 -= lr * dW2
            b2 -= lr * db2
            W1 -= lr * dW1
            b1 -= lr * db1

        if epoch % 50 == 0:
            print(f"Época {epoch:03d} | perda média: {total_loss / len(X):.6f}")

    model["W1"] = W1.tolist()
    model["b1"] = b1.tolist()
    model["W2"] = W2.tolist()
    model["b2"] = b2.tolist()

    errors = []

    for x in X:
        _, y = forward(model, x)
        errors.append(reconstruction_error(x, y))

    mean_error = float(np.mean(errors))
    std_error = float(np.std(errors))
    p95 = float(np.percentile(errors, 95))

    threshold = max(mean_error + 3 * std_error, p95 * 1.2, 0.0005)

    model["trained_at"] = now_iso()
    model["samples"] = len(samples)
    model["train_error_mean"] = mean_error
    model["train_error_std"] = std_error
    model["train_error_p95"] = p95
    model["threshold"] = threshold
    model["federated_ready"] = True
    model["aggregation_method_future"] = "FedAvg"

    return model


def load_model():
    if not MODEL_PATH.exists():
        return None

    return json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def load_latest_sample():
    if LATEST_PATH.exists():
        return json.loads(LATEST_PATH.read_text(encoding="utf-8"))

    samples = load_samples(limit=1)

    if samples:
        return samples[-1]

    return None


def anomaly_status(score):
    if score >= 1.5:
        return "ANOMALIA CRÍTICA"
    if score >= 1.0:
        return "ANOMALIA"
    if score >= 0.7:
        return "ATENÇÃO"
    return "NORMAL"


def feature_rows(sample, x, y):
    rows = ""

    raw_values = {
        "cpu_percent": f"{sample.get('cpu_percent', 0):.1f}%",
        "ram_percent": f"{sample.get('ram_percent', 0):.1f}%",
        "temperature_c": "N/A" if sample.get("temperature_c") is None else f"{sample.get('temperature_c'):.1f} °C",
        "disk_percent": f"{sample.get('disk_percent', 0):.1f}%",
        "latency_ms": "falha" if sample.get("latency_ms") is None else f"{sample.get('latency_ms'):.1f} ms",
        "load1": f"{sample.get('load1', 0):.2f}",
    }

    for i, feature in enumerate(FEATURES):
        diff = abs(float(x[i]) - float(y[i]))
        width = min(100, diff * 400)

        rows += f"""
        <tr>
            <td>{FEATURE_LABELS[feature]}</td>
            <td>{raw_values[feature]}</td>
            <td>{x[i]:.3f}</td>
            <td>{y[i]:.3f}</td>
            <td>
                <div class="bar">
                    <div style="width:{width:.1f}%"></div>
                </div>
                {diff:.4f}
            </td>
        </tr>
        """

    return rows


def save_dashboard(result):
    status = result["status"]

    if "CRÍTICA" in status:
        status_class = "critical"
    elif status == "ANOMALIA":
        status_class = "alert"
    elif status == "ATENÇÃO":
        status_class = "attention"
    else:
        status_class = "stable"

    rows = feature_rows(
        result["sample"],
        np.array(result["input_vector"]),
        np.array(result["reconstruction"]),
    )

    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="10">
    <title>EdgeBox Autoencoder</title>
    <style>
        body {{
            margin: 0;
            padding: 28px;
            background: #0f172a;
            color: #e5e7eb;
            font-family: Arial, sans-serif;
        }}

        h1 {{
            text-align: center;
            font-size: 42px;
            margin-bottom: 5px;
        }}

        .subtitle {{
            text-align: center;
            color: #cbd5e1;
            margin-bottom: 24px;
        }}

        .status {{
            max-width: 900px;
            margin: 0 auto 26px auto;
            padding: 22px;
            border-radius: 18px;
            text-align: center;
            font-size: 26px;
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
            color: #93c5fd;
            font-size: 16px;
            margin-top: 0;
        }}

        .value {{
            font-size: 28px;
            font-weight: bold;
        }}

        .section {{
            background: #111827;
            border-radius: 18px;
            padding: 22px;
            margin-bottom: 26px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            background: #1e293b;
            border-radius: 12px;
            overflow: hidden;
        }}

        th, td {{
            padding: 12px;
            border-bottom: 1px solid #334155;
            text-align: left;
        }}

        th {{
            background: #020617;
            color: #93c5fd;
        }}

        .bar {{
            width: 180px;
            height: 14px;
            background: #334155;
            border-radius: 999px;
            overflow: hidden;
            display: inline-block;
            margin-right: 8px;
        }}

        .bar div {{
            height: 100%;
            background: #38bdf8;
        }}

        code {{
            color: #86efac;
        }}

        a {{
            color: #93c5fd;
            font-weight: bold;
        }}

        .footer {{
            text-align: center;
            color: #94a3b8;
            margin-top: 24px;
        }}
    </style>
</head>
<body>
    <h1>EdgeBox Autoencoder</h1>
    <p class="subtitle">
        Detecção de anomalias operacionais usando autoencoder leve na TV Box
    </p>

    <div class="status {status_class}">
        Status: {result["status"]} | Score de anomalia: {result["anomaly_score"]:.2f}
    </div>

    <div class="grid">
        <div class="card">
            <h2>Erro de reconstrução</h2>
            <div class="value">{result["reconstruction_error"]:.6f}</div>
        </div>

        <div class="card">
            <h2>Limite aprendido</h2>
            <div class="value">{result["threshold"]:.6f}</div>
        </div>

        <div class="card">
            <h2>Amostras de treino</h2>
            <div class="value">{result["model_samples"]}</div>
        </div>

        <div class="card">
            <h2>Modelo</h2>
            <div class="value">6-3-6</div>
            <p>Entrada → gargalo → reconstrução</p>
        </div>
    </div>

    <div class="section">
        <h2>Como funciona</h2>
        <p>
            O autoencoder aprende o padrão normal de funcionamento da TV Box.
            Ele recebe métricas como CPU, RAM, temperatura, disco, latência e carga do sistema.
            Depois tenta reconstruir esses mesmos valores.
        </p>
        <p>
            Se a reconstrução fica muito diferente da entrada, o erro aumenta.
            Quando o erro passa do limite aprendido no treino, o sistema marca como anomalia.
        </p>
    </div>

    <div class="section">
        <h2>Comparação entrada vs reconstrução</h2>
        <table>
            <tr>
                <th>Métrica</th>
                <th>Valor real</th>
                <th>Entrada normalizada</th>
                <th>Reconstrução</th>
                <th>Erro</th>
            </tr>
            {rows}
        </table>
    </div>

    <div class="section">
        <h2>Uso em aprendizado federado</h2>
        <p>
            Este modelo foi treinado localmente na TV Box.
            Em uma rede federada real, cada TV Box treinaria seu próprio autoencoder
            e enviaria apenas pesos, limite de anomalia e estatísticas para um agregador.
        </p>
        <p>
            Arquivo de atualização federada:
            <code>edgebox_autoencoder_update.json</code>
        </p>
    </div>

    <div class="footer">
        Última atualização: {result["created_at"]} |
        <a href="/">Voltar ao painel EdgeBox</a>
    </div>
</body>
</html>
"""

    DASHBOARD_PATH.write_text(html, encoding="utf-8")


def train_mode():
    samples = load_samples()

    if len(samples) < 20:
        print(f"Poucas amostras para treinar: {len(samples)}")
        print("Colete mais dados com o EdgeBox primeiro.")
        return

    print("=== Treinando Autoencoder EdgeBox ===")
    print(f"Amostras usadas: {len(samples)}")

    model = train_autoencoder(samples)

    MODEL_PATH.write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")

    update = {
        "created_at": now_iso(),
        "node_id": samples[-1].get("node_id", "tvbox"),
        "model_type": "lightweight_autoencoder",
        "features": FEATURES,
        "weights": {
            "W1": model["W1"],
            "b1": model["b1"],
            "W2": model["W2"],
            "b2": model["b2"],
        },
        "threshold": model["threshold"],
        "samples": model["samples"],
        "federated_ready": True,
        "note": "Atualização local do autoencoder. Em FL real, seria enviada ao agregador.",
    }

    UPDATE_PATH.write_text(json.dumps(update, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== Treino finalizado ===")
    print(f"Erro médio: {model['train_error_mean']:.6f}")
    print(f"Erro p95: {model['train_error_p95']:.6f}")
    print(f"Threshold: {model['threshold']:.6f}")
    print("Modelo salvo em edgebox_autoencoder_model.json")


def infer_mode():
    model = load_model()

    if model is None:
        print("Modelo não encontrado. Rode primeiro:")
        print("python3 -m fluxos.edgebox.edgebox_autoencoder train")
        return

    sample = load_latest_sample()

    if sample is None:
        print("Nenhuma amostra encontrada.")
        return

    x = normalize_sample(sample)
    _, y = forward(model, x)

    err = reconstruction_error(x, y)
    threshold = float(model.get("threshold", 0.01))

    anomaly_score = err / threshold if threshold > 0 else 0.0
    status = anomaly_status(anomaly_score)

    result = {
        "created_at": now_iso(),
        "node_id": sample.get("node_id", "tvbox"),
        "status": status,
        "reconstruction_error": err,
        "threshold": threshold,
        "anomaly_score": anomaly_score,
        "input_vector": x.tolist(),
        "reconstruction": y.tolist(),
        "features": FEATURES,
        "model_samples": model.get("samples", 0),
        "sample": sample,
    }

    LATEST_AE_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    save_dashboard(result)

    print(f"[{result['created_at']}] Autoencoder | erro={err:.6f} | score={anomaly_score:.2f} | status={status}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "infer"

    if mode == "train":
        train_mode()
    elif mode == "infer":
        infer_mode()
    else:
        print("Uso:")
        print("python3 edgebox_autoencoder.py train")
        print("python3 -m fluxos.edgebox.edgebox_autoencoder infer")


if __name__ == "__main__":
    main()
