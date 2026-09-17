"""CPU-only tests for the supervised EdgeBox forecasting models."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from fluxos.edgebox.models.common import FEATURES, count_parameters, run_experiment
from fluxos.edgebox.models.gru import build_model as build_gru
from fluxos.edgebox.models.linear import build_model as build_linear
from fluxos.edgebox.models.lstm import build_model as build_lstm
from fluxos.edgebox.models.mlp import build_model as build_mlp
from fluxos.edgebox.models.rnn import build_model as build_rnn


MODEL_CASES = {
    "linear": (build_linear, 2_166, None, None),
    "mlp": (build_mlp, 25_382, None, None),
    "rnn": (build_rnn, 1_478, 32, 1),
    "gru": (build_gru, 4_038, 32, 1),
    "lstm": (build_lstm, 5_318, 32, 1),
}


class ForecastModelTests(unittest.TestCase):
    def test_forward_backward_state_dict_parameters_and_cpu(self) -> None:
        inputs = torch.randn(8, 60, 6, device="cpu")
        targets = torch.randn(8, 6, device="cpu")

        with tempfile.TemporaryDirectory(prefix="aquafl_model_test_") as temp_name:
            temp_dir = Path(temp_name)
            for model_name, (factory, expected_parameters, _, _) in MODEL_CASES.items():
                with self.subTest(model=model_name):
                    model = factory()
                    self.assertTrue(all(parameter.device.type == "cpu" for parameter in model.parameters()))
                    predictions = model(inputs)
                    self.assertEqual(tuple(predictions.shape), (8, 6))
                    torch.nn.functional.mse_loss(predictions, targets).backward()
                    self.assertTrue(any(parameter.grad is not None for parameter in model.parameters()))
                    self.assertEqual(count_parameters(model), expected_parameters)

                    weights_path = temp_dir / f"{model_name}.pt"
                    torch.save(model.state_dict(), weights_path)
                    restored = factory()
                    restored.load_state_dict(
                        torch.load(weights_path, map_location="cpu", weights_only=True)
                    )
                    for key, value in model.state_dict().items():
                        self.assertTrue(torch.equal(value, restored.state_dict()[key]))

    def test_one_epoch_smoke_training_for_every_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aquafl_training_test_") as temp_name:
            temp_dir = Path(temp_name)
            dataset_dir = temp_dir / "dataset"
            dataset_dir.mkdir()
            generator = np.random.default_rng(42)
            counts = {"train": 12, "validation": 8, "test": 8}
            for split, samples in counts.items():
                inputs = generator.normal(size=(samples, 60, 6)).astype(np.float32)
                targets = generator.normal(size=(samples, 6)).astype(np.float32)
                np.savez_compressed(dataset_dir / f"{split}.npz", X=inputs, y=targets)

            metadata = {
                "features": FEATURES,
                "sampling_seconds": 10,
                "input_window": 60,
                "forecast_horizon": 60,
                "forecast_type": "point",
                "dtype": "float32",
                "train_samples": counts["train"],
                "validation_samples": counts["validation"],
                "test_samples": counts["test"],
            }
            (dataset_dir / "metadata.json").write_text(
                json.dumps(metadata), encoding="utf-8"
            )

            for model_name, (factory, expected_parameters, hidden_size, num_layers) in MODEL_CASES.items():
                with self.subTest(model=model_name):
                    output_dir = temp_dir / "outputs" / model_name
                    model_metadata, metrics = run_experiment(
                        model_name,
                        factory,
                        hidden_size=hidden_size,
                        num_layers=num_layers,
                        epochs=1,
                        batch_size=4,
                        learning_rate=0.001,
                        seed=42,
                        dataset_dir=dataset_dir,
                        output_dir=output_dir,
                    )
                    self.assertEqual(model_metadata["device"], "cpu")
                    self.assertEqual(model_metadata["parameter_count"], expected_parameters)
                    self.assertEqual(set(metrics["test_mae_per_feature"]), set(FEATURES))
                    self.assertTrue((output_dir / "model.pt").is_file())
                    self.assertTrue((output_dir / "model.json").is_file())
                    self.assertTrue((output_dir / "metrics.json").is_file())


if __name__ == "__main__":
    unittest.main()
