import json
import random
import urllib.request
from urllib.parse import urlencode
from datetime import datetime
from pathlib import Path

from config import CLIMATE_DATA_DIR, WEB_DIR

BASE_DIR = CLIMATE_DATA_DIR

NODES = [
    {
        "id": "NO-01",
        "name": "Parque das Águas",
        "lat": -23.5062,
        "lon": -47.4559,
        "rain_factor": 1.00,
        "humidity_offset": 0,
        "wind_factor": 1.00,
        "water_base": 32,
        "vulnerability": 1.00,
    },
    {
        "id": "NO-02",
        "name": "Marginal Dom Aguirre",
        "lat": -23.5010,
        "lon": -47.4620,
        "rain_factor": 1.18,
        "humidity_offset": 4,
        "wind_factor": 0.92,
        "water_base": 48,
        "vulnerability": 1.25,
    },
    {
        "id": "NO-03",
        "name": "Jardim Abaeté",
        "lat": -23.5120,
        "lon": -47.4480,
        "rain_factor": 0.86,
        "humidity_offset": -3,
        "wind_factor": 1.12,
        "water_base": 25,
        "vulnerability": 0.85,
    },
]


def fetch_weather(node):
    params = {
        "latitude": node["lat"],
        "longitude": node["lon"],
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,shortwave_radiation",
        "forecast_days": 2,
        "timezone": "America/Sao_Paulo",
    }

    url = "https://api.open-meteo.com/v1/forecast?" + urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        h = data["hourly"]
        rows = []

        for i in range(len(h["time"])):
            rows.append({
                "time": h["time"][i],
                "temperature": h["temperature_2m"][i] or 0,
                "humidity": h["relative_humidity_2m"][i] or 0,
                "rain": h["precipitation"][i] or 0,
                "wind": h["wind_speed_10m"][i] or 0,
                "solar": h["shortwave_radiation"][i] or 0,
            })

        return rows

    except Exception as e:
        print(f"[AVISO] Falha na API para {node['name']}: {e}")
        return fake_weather()


def fake_weather():
    rows = []
    for i in range(48):
        rows.append({
            "time": f"simulado-hora-{i}",
            "temperature": random.gauss(24, 3),
            "humidity": min(100, max(40, random.gauss(78, 12))),
            "rain": max(0, random.gauss(2.0, 4.0)),
            "wind": max(0, random.gauss(10, 4)),
            "solar": max(0, random.gauss(450, 250)),
        })
    return rows


def apply_microclimate(rows, node):
    """
    Simula diferenças locais entre os nós.
    Na versão real, isso seria substituído por sensores físicos.
    """
    minute_seed = int(datetime.now().strftime("%Y%m%d%H%M"))
    random.seed(node["id"] + str(minute_seed))

    adjusted = []

    for i, row in enumerate(rows):
        local_rain_noise = random.uniform(0, 2.5)
        local_temp_noise = random.uniform(-0.8, 0.8)
        local_humidity_noise = random.uniform(-2, 2)
        local_wind_noise = random.uniform(-1.0, 1.0)

        rain = (row["rain"] * node["rain_factor"]) + local_rain_noise
        humidity = row["humidity"] + node["humidity_offset"] + local_humidity_noise
        temp = row["temperature"] + local_temp_noise
        wind = (row["wind"] * node["wind_factor"]) + local_wind_noise
        solar = row["solar"]

        humidity = min(100, max(0, humidity))
        wind = max(0, wind)
        rain = max(0, rain)

        water_level = (
            node["water_base"]
            + rain * 3.8
            + max(0, humidity - 80) * 0.45
            + random.uniform(-2.5, 2.5)
        )

        adjusted.append({
            "time": row["time"],
            "temperature": temp,
            "humidity": humidity,
            "rain": rain,
            "wind": wind,
            "solar": solar,
            "water_level": max(0, water_level),
            "vulnerability": node["vulnerability"],
        })

    return adjusted


def normalize(row):
    return [
        1.0,
        row["temperature"] / 45.0,
        row["humidity"] / 100.0,
        min(row["rain"], 50.0) / 50.0,
        min(row["wind"], 80.0) / 80.0,
        min(row["solar"], 1000.0) / 1000.0,
        min(row["water_level"], 120.0) / 120.0,
        row["vulnerability"] / 1.5,
    ]


def risk_label(row):
    rain_score = min(row["rain"] / 15.0, 1.0)
    humidity_score = row["humidity"] / 100.0
    water_score = min(row["water_level"] / 100.0, 1.0)
    wind_score = min(row["wind"] / 50.0, 1.0)
    low_solar_score = 1.0 - min(row["solar"] / 800.0, 1.0)
    vulnerability = min(row["vulnerability"] / 1.5, 1.0)

    risk = (
        0.30 * rain_score +
        0.20 * humidity_score +
        0.30 * water_score +
        0.10 * wind_score +
        0.05 * low_solar_score +
        0.05 * vulnerability
    )

    return min(max(risk, 0.0), 1.0)


def train_local_model(rows, epochs=80, lr=0.08):
    weights = [0.0] * 8

    for _ in range(epochs):
        for row in rows:
            x = normalize(row)
            y = risk_label(row)

            pred = sum(w * xi for w, xi in zip(weights, x))
            error = pred - y

            for j in range(len(weights)):
                weights[j] -= lr * error * x[j]

    return weights


def fedavg(local_models):
    total_samples = sum(m["samples"] for m in local_models)
    global_weights = [0.0] * len(local_models[0]["weights"])

    for model in local_models:
        factor = model["samples"] / total_samples
        for i, weight in enumerate(model["weights"]):
            global_weights[i] += factor * weight

    return global_weights


def predict(weights, row):
    x = normalize(row)
    pred = sum(w * xi for w, xi in zip(weights, x))
    return min(max(pred, 0.0), 1.0)


def risk_level(score):
    if score >= 0.75:
        return "VERMELHO - risco crítico experimental"
    if score >= 0.55:
        return "LARANJA - risco elevado experimental"
    if score >= 0.35:
        return "AMARELO - atenção experimental"
    return "VERDE - normal experimental"


def save_dashboard(results, global_weights):
    cards = ""

    for r in results:
        cards += f"""
        <div class="card">
            <h2>{r['node_name']}</h2>
            <p><b>Nó:</b> {r['node_id']}</p>
            <p><b>Temperatura:</b> {r['current']['temperature']:.1f} °C</p>
            <p><b>Umidade:</b> {r['current']['humidity']:.1f}%</p>
            <p><b>Chuva local:</b> {r['current']['rain']:.2f} mm</p>
            <p><b>Nível da água:</b> {r['current']['water_level']:.1f} cm</p>
            <p><b>Vento:</b> {r['current']['wind']:.1f} km/h</p>
            <p><b>Radiação solar:</b> {r['current']['solar']:.1f} W/m²</p>
            <p class="score"><b>Risco:</b> {r['risk_score']:.2f}</p>
            <p class="level">{r['risk_level']}</p>
        </div>
        """

    updated_at = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="60">
        <title>AquaFL - Cluster Federado</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #101820;
                color: #f2f2f2;
                margin: 0;
                padding: 30px;
            }}
            h1 {{
                text-align: center;
                font-size: 42px;
            }}
            .subtitle {{
                text-align: center;
                margin-bottom: 10px;
                color: #c9d6df;
            }}
            .updated {{
                text-align: center;
                margin-bottom: 30px;
                color: #88c0d0;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 20px;
            }}
            .card {{
                background: #1f2d3a;
                padding: 22px;
                border-radius: 14px;
                box-shadow: 0 0 20px rgba(0,0,0,0.25);
            }}
            .score {{
                font-size: 24px;
            }}
            .level {{
                font-size: 18px;
                font-weight: bold;
                padding: 12px;
                background: #30475e;
                border-radius: 8px;
            }}
            .footer {{
                margin-top: 30px;
                font-size: 14px;
                color: #c9d6df;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <h1>AquaFL</h1>
        <p class="subtitle">
            Cluster federado para análise climática e risco experimental de alagamento
        </p>
        <p class="updated">
            Última atualização: {updated_at} | Atualização automática a cada 60 segundos
        </p>

        <div class="grid">
            {cards}
        </div>

        <div class="footer">
            <p><b>Modelo global federado:</b> {[round(w, 4) for w in global_weights]}</p>
            <p>
                Demonstração experimental. Os dados locais usam API climática + simulação de microclima.
                Na versão real, cada nó usaria sensores físicos próprios.
            </p>
            <p>
                Este sistema não é alerta oficial de Defesa Civil.
            </p>
        </div>
    </body>
    </html>
    """

    (WEB_DIR / "dashboard.html").write_text(html, encoding="utf-8")
    (WEB_DIR / "index.html").write_text(html, encoding="utf-8")


def main():
    local_models = []
    node_data = {}

    print("\n=== AquaFL V2 - Demonstração Federada ===\n")

    for node in NODES:
        print(f"[1] Buscando dados climáticos: {node['name']}")
        rows = fetch_weather(node)

        print(f"[2] Aplicando microclima local: {node['name']}")
        rows = apply_microclimate(rows, node)

        dataset_path = BASE_DIR / f"dataset_{node['id']}.json"
        dataset_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"[3] Treinando modelo local: {node['name']}")
        weights = train_local_model(rows)

        model = {
            "node_id": node["id"],
            "node_name": node["name"],
            "samples": len(rows),
            "weights": weights,
        }

        local_models.append(model)
        node_data[node["id"]] = rows

        model_path = BASE_DIR / f"modelo_local_{node['id']}.json"
        model_path.write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")

    print("[4] Agregando modelos com FedAvg")
    global_weights = fedavg(local_models)

    global_model = {
        "created_at": datetime.now().isoformat(),
        "method": "FedAvg simplificado",
        "weights": global_weights,
        "nodes": [m["node_id"] for m in local_models],
    }

    (BASE_DIR / "modelo_global.json").write_text(
        json.dumps(global_model, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    results = []

    print("[5] Gerando predições por nó")

    for node in NODES:
        current = node_data[node["id"]][0]
        score = predict(global_weights, current)

        results.append({
            "node_id": node["id"],
            "node_name": node["name"],
            "current": current,
            "risk_score": score,
            "risk_level": risk_level(score),
        })

    (BASE_DIR / "resultado.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    save_dashboard(results, global_weights)

    print("\n=== Finalizado ===")
    print("Dashboard atualizado: http://IP_DA_TVBOX:8080")


if __name__ == "__main__":
    main()
