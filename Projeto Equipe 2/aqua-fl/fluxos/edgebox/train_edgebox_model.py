import json
import random
from pathlib import Path
from datetime import datetime

from config import EDGEBOX_DATA_DIR
from fluxos.edgebox.edgebox_node import (
    normalize_metrics,
    infer_with_model,
    status_from_risk,
    DATASET_PATH,
    MODEL_PATH,
    GLOBAL_MODEL_PATH,
)

TRAINED_PATH = EDGEBOX_DATA_DIR / "edgebox_trained_model.json"


def read_samples():
    samples = []

    if not DATASET_PATH.exists():
        return samples

    with DATASET_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                sample = json.loads(line)
            except Exception:
                continue

            if "target_risk" not in sample:
                continue

            samples.append(sample)

    return samples


def train_model(samples, epochs=180, learning_rate=0.04):
    weights = [0.0] * 7

    for epoch in range(epochs):
        random.shuffle(samples)

        total_error = 0.0

        for sample in samples:
            x = normalize_metrics(sample)
            y = float(sample["target_risk"])

            pred = sum(w * xi for w, xi in zip(weights, x))
            error = pred - y
            total_error += abs(error)

            for i in range(len(weights)):
                weights[i] -= learning_rate * error * x[i]

        if epoch % 30 == 0:
            mae = total_error / max(len(samples), 1)
            print(f"Época {epoch:03d} | erro médio: {mae:.4f}")

    return [round(w, 6) for w in weights]


def evaluate(weights, samples):
    if not samples:
        return {
            "mae": None,
            "count": 0,
        }

    errors = []

    for sample in samples:
        y = float(sample["target_risk"])
        pred = infer_with_model(weights, sample)
        errors.append(abs(pred - y))

    mae = sum(errors) / len(errors)

    return {
        "mae": round(mae, 5),
        "count": len(samples),
    }


def main():
    samples = read_samples()

    if len(samples) < 10:
        print("Poucas amostras para treinar. Colete mais dados primeiro.")
        print(f"Amostras encontradas: {len(samples)}")
        return

    random.seed(42)
    random.shuffle(samples)

    split = int(len(samples) * 0.8)

    train_samples = samples[:split]
    test_samples = samples[split:]

    if not test_samples:
        test_samples = train_samples

    print("=== Treinamento EdgeBox FL ===")
    print(f"Amostras totais: {len(samples)}")
    print(f"Amostras de treino: {len(train_samples)}")
    print(f"Amostras de teste: {len(test_samples)}")

    weights = train_model(train_samples)

    train_eval = evaluate(weights, train_samples)
    test_eval = evaluate(weights, test_samples)

    last = samples[-1]
    current_risk = infer_with_model(weights, last)
    current_status = status_from_risk(current_risk)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "node_id": last.get("node_id", "tvbox"),
        "model_type": "linear_regression_lightweight",
        "training_method": "local_training",
        "federated_ready": True,
        "aggregation_method_future": "FedAvg",
        "features": [
            "bias",
            "cpu_percent",
            "ram_percent",
            "temperature_c",
            "disk_percent",
            "latency_ms",
            "load1",
        ],
        "samples_total": len(samples),
        "samples_train": len(train_samples),
        "samples_test": len(test_samples),
        "train_mae": train_eval["mae"],
        "test_mae": test_eval["mae"],
        "weights": weights,
        "current_inferred_risk": round(current_risk, 4),
        "current_status": current_status,
        "note": "Modelo treinado localmente na TV Box. Em uma rede federada, estes pesos seriam enviados ao agregador central.",
    }

    TRAINED_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    MODEL_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    global_model = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "aggregation": "single_node_now__future_fedavg_multi_node",
        "nodes": [payload["node_id"]],
        "global_weights": weights,
        "test_mae": test_eval["mae"],
        "note": "No protótipo atual há apenas uma TV Box física. Com várias TV Boxes, este arquivo seria resultado da agregação FedAvg.",
    }

    GLOBAL_MODEL_PATH.write_text(json.dumps(global_model, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== Treinamento finalizado ===")
    print(f"Erro médio treino: {train_eval['mae']}")
    print(f"Erro médio teste: {test_eval['mae']}")
    print(f"Risco atual inferido: {current_risk:.4f}")
    print(f"Status atual: {current_status}")
    print("\nArquivos gerados:")
    print("- edgebox_trained_model.json")
    print("- edgebox_model_update.json")
    print("- edgebox_global_model.json")


if __name__ == "__main__":
    main()
