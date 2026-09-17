"""Linear baseline for fixed-horizon EdgeBox forecasting."""

from __future__ import annotations

import torch
from torch import nn

from .common import INPUT_SIZE, INPUT_WINDOW, OUTPUT_SIZE, run_model_cli, validate_model_input


class LinearForecaster(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.output = nn.Linear(INPUT_WINDOW * INPUT_SIZE, OUTPUT_SIZE)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        validate_model_input(inputs)
        return self.output(torch.flatten(inputs, start_dim=1))


def build_model() -> LinearForecaster:
    return LinearForecaster()


if __name__ == "__main__":
    run_model_cli("linear", build_model, hidden_size=None, num_layers=None)
