"""Shared training utilities for the EdgeBox forecasting models."""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


DATASET_NAME = "forecast_w60_h60"
INPUT_WINDOW = 60
FORECAST_HORIZON = 60
INPUT_SIZE = 6
OUTPUT_SIZE = 6
FEATURES = [
    "cpu_percent",
    "ram_percent",
    "temperature_c",
    "disk_percent",
    "latency_ms",
    "load1",
]


@dataclass(frozen=True)
class DatasetBundle:
    """Arrays and metadata loaded once for a complete experiment."""

    train_x: np.ndarray
    train_y: np.ndarray
    validation_x: np.ndarray
    validation_y: np.ndarray
    test_x: np.ndarray
    test_y: np.ndarray
    metadata: dict[str, Any]


def project_root() -> Path:
    """Resolve the repository root without depending on the current directory."""

    source = Path(__file__).resolve()
    for candidate in source.parents:
        if (candidate / "config.py").is_file() and (candidate / "fluxos").is_dir():
            return candidate
    raise RuntimeError(f"Could not resolve the AquaFL project root from {source}")


def default_dataset_dir() -> Path:
    return project_root() / "dados" / "edgebox" / "processed" / DATASET_NAME


def default_output_dir(model_type: str) -> Path:
    return project_root() / "dados" / "edgebox" / "models" / model_type / "w60_h60"


def set_seed(seed: int) -> None:
    """Seed all RNGs used by this CPU-only training pipeline."""

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def cpu_device() -> torch.device:
    """Return the only device supported by this benchmark."""

    return torch.device("cpu")


def validate_model_input(inputs: torch.Tensor) -> None:
    expected = (INPUT_WINDOW, INPUT_SIZE)
    if inputs.ndim != 3 or tuple(inputs.shape[1:]) != expected:
        raise ValueError(
            f"Expected input shape (batch, {INPUT_WINDOW}, {INPUT_SIZE}), "
            f"received {tuple(inputs.shape)}"
        )


def _read_metadata(dataset_dir: Path) -> dict[str, Any]:
    path = dataset_dir / "metadata.json"
    if not path.is_file():
        raise FileNotFoundError(f"Dataset metadata not found: {path}")
    with path.open("r", encoding="utf-8") as source:
        metadata = json.load(source)
    if not isinstance(metadata, dict):
        raise ValueError(f"Dataset metadata must be a JSON object: {path}")
    return metadata


def _load_split(dataset_dir: Path, split: str) -> tuple[np.ndarray, np.ndarray]:
    path = dataset_dir / f"{split}.npz"
    if not path.is_file():
        raise FileNotFoundError(f"Dataset split not found: {path}")
    with np.load(path, allow_pickle=False) as archive:
        missing = {"X", "y"}.difference(archive.files)
        if missing:
            raise ValueError(f"{path} is missing arrays: {sorted(missing)}")
        inputs = np.asarray(archive["X"], dtype=np.float32)
        targets = np.asarray(archive["y"], dtype=np.float32)
    _validate_split(split, inputs, targets)
    return inputs, targets


def _validate_split(split: str, inputs: np.ndarray, targets: np.ndarray) -> None:
    expected_x_tail = (INPUT_WINDOW, INPUT_SIZE)
    if inputs.ndim != 3 or tuple(inputs.shape[1:]) != expected_x_tail:
        raise ValueError(
            f"{split}.npz X must have shape (N, {INPUT_WINDOW}, {INPUT_SIZE}); "
            f"received {inputs.shape}"
        )
    if targets.ndim != 2 or targets.shape[1] != OUTPUT_SIZE:
        raise ValueError(
            f"{split}.npz y must have shape (N, {OUTPUT_SIZE}); received {targets.shape}"
        )
    if inputs.shape[0] != targets.shape[0]:
        raise ValueError(
            f"{split}.npz has different sample counts: X={inputs.shape[0]}, y={targets.shape[0]}"
        )
    if inputs.shape[0] == 0:
        raise ValueError(f"{split}.npz contains no samples")


def _validate_metadata(metadata: dict[str, Any], bundle: DatasetBundle) -> None:
    expected = {
        "input_window": INPUT_WINDOW,
        "forecast_horizon": FORECAST_HORIZON,
        "forecast_type": "point",
        "features": FEATURES,
        "dtype": "float32",
    }
    for key, expected_value in expected.items():
        if metadata.get(key) != expected_value:
            raise ValueError(
                f"metadata.json field {key!r} must be {expected_value!r}; "
                f"received {metadata.get(key)!r}"
            )

    counts = {
        "train_samples": bundle.train_x.shape[0],
        "validation_samples": bundle.validation_x.shape[0],
        "test_samples": bundle.test_x.shape[0],
    }
    for key, actual in counts.items():
        if key in metadata and metadata[key] != actual:
            raise ValueError(
                f"metadata.json field {key!r} is {metadata[key]!r}, but the split contains {actual}"
            )


def load_dataset(dataset_dir: Path | None = None) -> DatasetBundle:
    """Load and validate all splits exactly once."""

    resolved = (dataset_dir or default_dataset_dir()).resolve()
    metadata = _read_metadata(resolved)
    train_x, train_y = _load_split(resolved, "train")
    validation_x, validation_y = _load_split(resolved, "validation")
    test_x, test_y = _load_split(resolved, "test")
    bundle = DatasetBundle(
        train_x=train_x,
        train_y=train_y,
        validation_x=validation_x,
        validation_y=validation_y,
        test_x=test_x,
        test_y=test_y,
        metadata=metadata,
    )
    _validate_metadata(metadata, bundle)
    return bundle


def numpy_to_torch(inputs: np.ndarray, targets: np.ndarray) -> TensorDataset:
    """Create a zero-copy CPU TensorDataset when arrays are already float32."""

    return TensorDataset(torch.from_numpy(inputs), torch.from_numpy(targets))


def create_data_loaders(
    bundle: DatasetBundle,
    batch_size: int,
    seed: int,
) -> dict[str, DataLoader]:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    common = {"batch_size": batch_size, "num_workers": 0, "pin_memory": False}
    return {
        "train": DataLoader(
            numpy_to_torch(bundle.train_x, bundle.train_y),
            shuffle=True,
            generator=generator,
            **common,
        ),
        "validation": DataLoader(
            numpy_to_torch(bundle.validation_x, bundle.validation_y),
            shuffle=False,
            **common,
        ),
        "test": DataLoader(
            numpy_to_torch(bundle.test_x, bundle.test_y),
            shuffle=False,
            **common,
        ),
    }


def count_parameters(model: nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def calculate_metrics(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    per_feature: bool = False,
) -> dict[str, Any]:
    """Calculate sample-weighted regression metrics without retaining predictions."""

    model.eval()
    squared_error = 0.0
    absolute_error = 0.0
    element_count = 0
    feature_absolute_error = torch.zeros(OUTPUT_SIZE, dtype=torch.float64)
    sample_count = 0

    with torch.inference_mode():
        for inputs, targets in loader:
            inputs = inputs.to(device=device, dtype=torch.float32)
            targets = targets.to(device=device, dtype=torch.float32)
            predictions = model(inputs)
            errors = predictions - targets
            squared_error += errors.square().sum().item()
            absolute_error += errors.abs().sum().item()
            element_count += errors.numel()
            sample_count += errors.shape[0]
            if per_feature:
                feature_absolute_error += errors.abs().sum(dim=0, dtype=torch.float64).cpu()

    if element_count == 0:
        raise ValueError("Cannot calculate metrics for an empty DataLoader")
    mse = squared_error / element_count
    result: dict[str, Any] = {
        "mse": mse,
        "mae": absolute_error / element_count,
        "rmse": math.sqrt(mse),
    }
    if per_feature:
        result["mae_per_feature"] = {
            feature: float(value / sample_count)
            for feature, value in zip(FEATURES, feature_absolute_error.tolist())
        }
    return result


def train_model(
    model: nn.Module,
    loaders: dict[str, DataLoader],
    epochs: int,
    learning_rate: float,
    device: torch.device,
) -> tuple[list[dict[str, float]], float]:
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    history: list[dict[str, float]] = []
    started = time.perf_counter()

    for epoch in range(1, epochs + 1):
        model.train()
        loss_sum = 0.0
        sample_count = 0
        for inputs, targets in loaders["train"]:
            inputs = inputs.to(device=device, dtype=torch.float32)
            targets = targets.to(device=device, dtype=torch.float32)
            optimizer.zero_grad(set_to_none=True)
            predictions = model(inputs)
            loss = criterion(predictions, targets)
            loss.backward()
            optimizer.step()
            loss_sum += loss.item() * inputs.shape[0]
            sample_count += inputs.shape[0]

        validation = calculate_metrics(model, loaders["validation"], device)
        epoch_metrics = {
            "epoch": epoch,
            "train_loss": loss_sum / sample_count,
            "validation_mse": validation["mse"],
        }
        history.append(epoch_metrics)
        print(
            f"epoch={epoch}/{epochs} train_mse={epoch_metrics['train_loss']:.6f} "
            f"validation_mse={epoch_metrics['validation_mse']:.6f}",
            flush=True,
        )

    return history, time.perf_counter() - started


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_experiment(
    model_type: str,
    model_factory: Callable[[], nn.Module],
    *,
    hidden_size: int | None,
    num_layers: int | None,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    seed: int,
    dataset_dir: Path | None = None,
    output_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Train, evaluate and serialize one forecasting model."""

    set_seed(seed)
    device = cpu_device()
    bundle = load_dataset(dataset_dir)
    loaders = create_data_loaders(bundle, batch_size=batch_size, seed=seed)
    model = model_factory().to(device)
    parameter_count = count_parameters(model)
    history, training_seconds = train_model(
        model,
        loaders,
        epochs=epochs,
        learning_rate=learning_rate,
        device=device,
    )

    train_metrics = calculate_metrics(model, loaders["train"], device)
    validation_metrics = calculate_metrics(model, loaders["validation"], device)
    test_metrics = calculate_metrics(model, loaders["test"], device, per_feature=True)
    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    model_metadata = {
        "model_type": model_type,
        "dataset": DATASET_NAME,
        "input_window": INPUT_WINDOW,
        "forecast_horizon": FORECAST_HORIZON,
        "input_size": INPUT_SIZE,
        "output_size": OUTPUT_SIZE,
        "hidden_size": hidden_size,
        "num_layers": num_layers,
        "features": FEATURES,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "seed": seed,
        "optimizer": "Adam",
        "loss": "MSELoss",
        "parameter_count": parameter_count,
        "torch_version": torch.__version__,
        "numpy_version": np.__version__,
        "device": str(device),
        "trained_at": trained_at,
    }
    metrics = {
        "model_type": model_type,
        "dataset": DATASET_NAME,
        "train_samples": bundle.train_x.shape[0],
        "validation_samples": bundle.validation_x.shape[0],
        "test_samples": bundle.test_x.shape[0],
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "optimizer": "Adam",
        "loss": "MSELoss",
        "train_mse": train_metrics["mse"],
        "train_mae": train_metrics["mae"],
        "train_rmse": train_metrics["rmse"],
        "validation_mse": validation_metrics["mse"],
        "validation_mae": validation_metrics["mae"],
        "validation_rmse": validation_metrics["rmse"],
        "test_mse": test_metrics["mse"],
        "test_mae": test_metrics["mae"],
        "test_rmse": test_metrics["rmse"],
        "test_mae_per_feature": test_metrics["mae_per_feature"],
        "training_seconds": training_seconds,
        "parameter_count": parameter_count,
        "trained_at": trained_at,
        "history": history,
    }

    destination = (output_dir or default_output_dir(model_type)).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), destination / "model.pt")
    write_json(destination / "model.json", model_metadata)
    write_json(destination / "metrics.json", metrics)
    print(f"saved={destination}", flush=True)
    return model_metadata, metrics


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return parsed


def parse_training_args(model_type: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Train the EdgeBox {model_type} forecaster on CPU.")
    parser.add_argument("--epochs", type=_positive_int, default=25)
    parser.add_argument("--batch-size", type=_positive_int, default=32)
    parser.add_argument("--learning-rate", type=_positive_float, default=0.001)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def run_model_cli(
    model_type: str,
    model_factory: Callable[[], nn.Module],
    *,
    hidden_size: int | None,
    num_layers: int | None,
) -> None:
    args = parse_training_args(model_type)
    run_experiment(
        model_type,
        model_factory,
        hidden_size=hidden_size,
        num_layers=num_layers,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )
