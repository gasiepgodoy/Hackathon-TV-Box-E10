"""Multilayer perceptron for fixed-horizon EdgeBox forecasting."""

from __future__ import annotations

import torch
from torch import nn

from .common import INPUT_SIZE, INPUT_WINDOW, OUTPUT_SIZE, run_model_cli, validate_model_input


class MLPForecaster(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Flatten(),
            nn.Linear(INPUT_WINDOW * INPUT_SIZE, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, OUTPUT_SIZE),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        validate_model_input(inputs)
        return self.network(inputs)


def build_model() -> MLPForecaster:
    return MLPForecaster()


if __name__ == "__main__":
    run_model_cli("mlp", build_model, hidden_size=None, num_layers=None)
