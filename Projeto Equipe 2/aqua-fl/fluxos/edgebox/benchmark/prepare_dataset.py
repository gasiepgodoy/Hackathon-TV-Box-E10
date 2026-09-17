"""Prepare an isolated, time-aware forecasting dataset from EdgeBox JSONL."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from config import EDGEBOX_DATA_DIR

FEATURES = [
    "cpu_percent",
    "ram_percent",
    "temperature_c",
    "disk_percent",
    "latency_ms",
    "load1",
]

DEFAULT_SAMPLING_SECONDS = 10
DEFAULT_GAP_TOLERANCE_SECONDS = 20
DEFAULT_WINDOW = 60
DEFAULT_HORIZON = 60
DEFAULT_OUTPUT = EDGEBOX_DATA_DIR / "processed" / "forecast_w60_h60"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria datasets temporais de forecasting sem alterar o JSONL de producao."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=EDGEBOX_DATA_DIR / "edgebox_metrics.jsonl",
        help="JSONL de origem (nao e alterado).",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=EDGEBOX_DATA_DIR / "raw",
        help="Diretorio para o snapshot do JSONL.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Diretorio de saida; por padrao usa forecast_w{window}_h{horizon}.",
    )
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    parser.add_argument(
        "--gap-tolerance-seconds",
        type=float,
        default=DEFAULT_GAP_TOLERANCE_SECONDS,
    )
    parser.add_argument(
        "--sampling-seconds",
        type=float,
        default=DEFAULT_SAMPLING_SECONDS,
    )
    parser.add_argument(
        "--missing-strategy",
        choices=("train_median",),
        default="train_median",
    )
    parser.add_argument(
        "--outlier-strategy",
        choices=("clip", "flag", "none"),
        default="clip",
        help="Detecta outliers com IQR do treino; clip tambem limita os valores.",
    )
    parser.add_argument(
        "--normalization",
        choices=("standard", "minmax", "none"),
        default="standard",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Limita registros lidos, util para teste controlado.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp ausente ou nao textual")
    normalized = value.strip().replace("Z", "+00:00")
    timestamp = datetime.fromisoformat(normalized)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    return timestamp


def numeric_value(record: dict[str, Any], feature: str) -> float | None:
    value = record.get(feature)
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def snapshot_source(source: Path, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = raw_dir / f"edgebox_metrics_{stamp}.jsonl"
    with source.open("rb") as source_file, snapshot.open("wb") as snapshot_file:
        shutil.copyfileobj(source_file, snapshot_file, length=1024 * 1024)
    return snapshot


def first_pass(
    snapshot: Path,
    cleaned_file,
    sampling_seconds: float,
    gap_tolerance_seconds: float,
    max_records: int | None,
) -> dict[str, Any]:
    counters = {
        "discarded_invalid_json": 0,
        "discarded_invalid_timestamp": 0,
        "discarded_duplicates": 0,
        "discarded_out_of_order": 0,
        "discarded_due_to_gaps": 0,
        "missing_values_detected": {feature: 0 for feature in FEATURES},
    }
    valid_records = 0
    segment_id = 0
    previous_timestamp: datetime | None = None
    seen_timestamps: set[str] = set()

    with snapshot.open("r", encoding="utf-8") as source_file:
        for line_number, line in enumerate(source_file, start=1):
            if max_records is not None and line_number > max_records:
                break
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                counters["discarded_invalid_json"] += 1
                continue
            if not isinstance(record, dict):
                counters["discarded_invalid_json"] += 1
                continue

            try:
                timestamp = parse_timestamp(record.get("timestamp"))
            except (TypeError, ValueError):
                counters["discarded_invalid_timestamp"] += 1
                continue

            timestamp_key = timestamp.isoformat(timespec="seconds")
            if timestamp_key in seen_timestamps:
                counters["discarded_duplicates"] += 1
                continue
            if previous_timestamp is not None and timestamp <= previous_timestamp:
                counters["discarded_out_of_order"] += 1
                segment_id += 1
                previous_timestamp = None
                continue

            if previous_timestamp is not None:
                delta = (timestamp - previous_timestamp).total_seconds()
                if delta > gap_tolerance_seconds:
                    segment_id += 1

            for feature in FEATURES:
                if numeric_value(record, feature) is None:
                    counters["missing_values_detected"][feature] += 1

            clean_record = {
                "timestamp": timestamp.isoformat(timespec="seconds"),
                "segment_id": segment_id,
                **{feature: record.get(feature) for feature in FEATURES},
            }
            cleaned_file.write(json.dumps(clean_record, ensure_ascii=False) + "\n")
            valid_records += 1
            seen_timestamps.add(timestamp_key)
            previous_timestamp = timestamp

    counters["valid_records"] = valid_records
    counters["segments"] = segment_id + (1 if valid_records else 0)
    counters["gap_tolerance_seconds"] = gap_tolerance_seconds
    counters["sampling_seconds"] = sampling_seconds
    return counters


def split_cleaned(cleaned_path: Path, temp_dir: Path, valid_records: int) -> dict[str, Path]:
    paths = {
        "train": temp_dir / "train.jsonl",
        "validation": temp_dir / "validation.jsonl",
        "test": temp_dir / "test.jsonl",
    }
    files = {name: path.open("w", encoding="utf-8") for name, path in paths.items()}
    try:
        for index, line in enumerate(cleaned_path.open("r", encoding="utf-8")):
            ratio = index / max(valid_records, 1)
            split = "train" if ratio < 0.70 else "validation" if ratio < 0.85 else "test"
            files[split].write(line)
    finally:
        for file in files.values():
            file.close()
    return paths


def read_feature_values(path: Path) -> np.ndarray:
    rows = []
    with path.open("r", encoding="utf-8") as source_file:
        for line in source_file:
            record = json.loads(line)
            rows.append([numeric_value(record, feature) for feature in FEATURES])
    values = np.full((len(rows), len(FEATURES)), np.nan, dtype=np.float64)
    for row_index, row in enumerate(rows):
        for feature_index, value in enumerate(row):
            if value is not None:
                values[row_index, feature_index] = value
    return values


def percentile(values: np.ndarray, fraction: float, fallback: float) -> float:
    finite = values[np.isfinite(values)]
    return float(np.percentile(finite, fraction * 100)) if finite.size else fallback


def calculate_parameters(train_values: np.ndarray, normalization: str) -> dict[str, Any]:
    medians = np.array(
        [percentile(train_values[:, index], 0.50, 0.0) for index in range(len(FEATURES))],
        dtype=np.float64,
    )
    filled_train = np.where(np.isnan(train_values), medians, train_values)
    q1 = np.percentile(filled_train, 25, axis=0)
    q3 = np.percentile(filled_train, 75, axis=0)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    params: dict[str, Any] = {
        "imputation_medians": dict(zip(FEATURES, medians.tolist())),
        "outlier_method": "iqr",
        "outlier_lower": dict(zip(FEATURES, lower.tolist())),
        "outlier_upper": dict(zip(FEATURES, upper.tolist())),
        "method": normalization,
    }
    if normalization == "standard":
        mean = filled_train.mean(axis=0)
        std = filled_train.std(axis=0)
        std[std == 0] = 1.0
        params["mean"] = dict(zip(FEATURES, mean.tolist()))
        params["std"] = dict(zip(FEATURES, std.tolist()))
    elif normalization == "minmax":
        minimum = filled_train.min(axis=0)
        maximum = filled_train.max(axis=0)
        scale = maximum - minimum
        scale[scale == 0] = 1.0
        params["min"] = dict(zip(FEATURES, minimum.tolist()))
        params["max"] = dict(zip(FEATURES, maximum.tolist()))
    return params


def transform_values(
    values: np.ndarray,
    params: dict[str, Any],
    outlier_strategy: str,
) -> tuple[np.ndarray, dict[str, int], dict[str, int]]:
    medians = np.array([params["imputation_medians"][feature] for feature in FEATURES])
    missing = np.isnan(values)
    imputed_counts = dict(zip(FEATURES, missing.sum(axis=0).astype(int).tolist()))
    transformed = np.where(missing, medians, values.copy())

    lower = np.array([params["outlier_lower"][feature] for feature in FEATURES])
    upper = np.array([params["outlier_upper"][feature] for feature in FEATURES])
    outlier_mask = (transformed < lower) | (transformed > upper)
    outlier_counts = dict(zip(FEATURES, outlier_mask.sum(axis=0).astype(int).tolist()))
    if outlier_strategy == "clip":
        transformed = np.clip(transformed, lower, upper)

    if params["method"] == "standard":
        mean = np.array([params["mean"][feature] for feature in FEATURES])
        std = np.array([params["std"][feature] for feature in FEATURES])
        transformed = (transformed - mean) / std
    elif params["method"] == "minmax":
        minimum = np.array([params["min"][feature] for feature in FEATURES])
        maximum = np.array([params["max"][feature] for feature in FEATURES])
        transformed = (transformed - minimum) / (maximum - minimum)

    return transformed.astype(np.float32), imputed_counts, outlier_counts


def build_windows(
    path: Path,
    params: dict[str, Any],
    outlier_strategy: str,
    window: int,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, int], dict[str, int], int]:
    inputs: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    imputed_total = dict(zip(FEATURES, [0] * len(FEATURES)))
    outlier_total = dict(zip(FEATURES, [0] * len(FEATURES)))
    discarded_due_to_gaps = 0
    previous_segment: int | None = None
    buffer: deque[np.ndarray] = deque()
    required = window + horizon

    with path.open("r", encoding="utf-8") as source_file:
        for line in source_file:
            record = json.loads(line)
            segment = int(record["segment_id"])
            if previous_segment is not None and segment != previous_segment:
                if len(buffer) < required:
                    discarded_due_to_gaps += 1
                buffer.clear()
            previous_segment = segment
            raw = np.array(
                [[numeric_value(record, feature) for feature in FEATURES]], dtype=np.float64
            )
            values, imputed, outliers = transform_values(raw, params, outlier_strategy)
            for feature in FEATURES:
                imputed_total[feature] += imputed[feature]
                outlier_total[feature] += outliers[feature]
            buffer.append(values[0])
            if len(buffer) >= required:
                sequence = np.asarray(buffer, dtype=np.float32)
                inputs.append(sequence[:window])
                targets.append(sequence[window + horizon - 1])
                buffer.popleft()

    if not inputs:
        return (
            np.empty((0, window, len(FEATURES)), dtype=np.float32),
            np.empty((0, len(FEATURES)), dtype=np.float32),
            imputed_total,
            outlier_total,
            discarded_due_to_gaps,
        )
    return np.stack(inputs), np.stack(targets), imputed_total, outlier_total, discarded_due_to_gaps


def write_npz(path: Path, x: np.ndarray, y: np.ndarray) -> None:
    np.savez_compressed(path, X=x.astype(np.float32), y=y.astype(np.float32))


def main() -> None:
    args = parse_args()
    if args.window <= 0 or args.horizon <= 0:
        raise SystemExit("--window e --horizon devem ser positivos")
    if not args.source.exists():
        raise SystemExit(f"Fonte nao encontrada: {args.source}")

    output_dir = args.output_dir or EDGEBOX_DATA_DIR / "processed" / f"forecast_w{args.window}_h{args.horizon}"
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_source(args.source, args.raw_dir)
    process_start = datetime.now()

    with tempfile.TemporaryDirectory(prefix="prepare_dataset_") as temp_name:
        temp_dir = Path(temp_name)
        cleaned_path = temp_dir / "cleaned.jsonl"
        with cleaned_path.open("w", encoding="utf-8") as cleaned_file:
            counters = first_pass(
                snapshot,
                cleaned_file,
                args.sampling_seconds,
                args.gap_tolerance_seconds,
                args.max_records,
            )

        if counters["valid_records"] == 0:
            raise SystemExit("Nenhum registro valido foi encontrado")
        split_paths = split_cleaned(cleaned_path, temp_dir, counters["valid_records"])
        train_values = read_feature_values(split_paths["train"])
        params = calculate_parameters(train_values, args.normalization)

        split_arrays = {}
        imputed_total = dict(zip(FEATURES, [0] * len(FEATURES)))
        outlier_total = dict(zip(FEATURES, [0] * len(FEATURES)))
        discarded_due_to_gaps = counters["discarded_due_to_gaps"]
        for split, path in split_paths.items():
            x, y, imputed, outliers, gap_discards = build_windows(
                path, params, args.outlier_strategy, args.window, args.horizon
            )
            split_arrays[split] = (x, y)
            discarded_due_to_gaps += gap_discards
            for feature in FEATURES:
                imputed_total[feature] += imputed[feature]
                outlier_total[feature] += outliers[feature]

    write_npz(output_dir / "train.npz", *split_arrays["train"])
    write_npz(output_dir / "validation.npz", *split_arrays["validation"])
    write_npz(output_dir / "test.npz", *split_arrays["test"])

    counters["discarded_due_to_gaps"] = int(discarded_due_to_gaps)
    metadata = {
        "features": FEATURES,
        "sampling_seconds": args.sampling_seconds,
        "input_window": args.window,
        "forecast_horizon": args.horizon,
        "forecast_type": "point",
        "target_definition": "features exactly horizon steps after the last input sample",
        "dtype": "float32",
        "split": {"train": 0.70, "validation": 0.15, "test": 0.15},
        "source_snapshot": str(snapshot.relative_to(Path.cwd())) if snapshot.is_relative_to(Path.cwd()) else str(snapshot),
        "created_at": now_iso(),
        "gap_tolerance_seconds": args.gap_tolerance_seconds,
        "missing_strategy": args.missing_strategy,
        "missing_values_detected": counters["missing_values_detected"],
        "missing_values_imputed": imputed_total,
        "outliers_detected": outlier_total,
        "outlier_strategy": args.outlier_strategy,
        "normalization": params,
        "train_samples": int(split_arrays["train"][0].shape[0]),
        "validation_samples": int(split_arrays["validation"][0].shape[0]),
        "test_samples": int(split_arrays["test"][0].shape[0]),
        "discarded_invalid_json": counters["discarded_invalid_json"],
        "discarded_invalid_timestamp": counters["discarded_invalid_timestamp"],
        "discarded_duplicates": counters["discarded_duplicates"],
        "discarded_out_of_order": counters["discarded_out_of_order"],
        "discarded_due_to_gaps": counters["discarded_due_to_gaps"],
        "valid_records": counters["valid_records"],
        "segments": counters["segments"],
        "processing_seconds": (datetime.now() - process_start).total_seconds(),
        "max_records": args.max_records,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    try:
        import resource

        peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except (ImportError, AttributeError):
        peak_rss_mb = None
    print(f"Snapshot: {snapshot}")
    print(f"Saida: {output_dir}")
    print(f"train X={split_arrays['train'][0].shape} y={split_arrays['train'][1].shape}")
    print(f"validation X={split_arrays['validation'][0].shape} y={split_arrays['validation'][1].shape}")
    print(f"test X={split_arrays['test'][0].shape} y={split_arrays['test'][1].shape}")
    print(f"RAM de pico aproximada do processo: {peak_rss_mb:.1f} MB" if peak_rss_mb else "RAM de pico: indisponivel")


if __name__ == "__main__":
    main()
