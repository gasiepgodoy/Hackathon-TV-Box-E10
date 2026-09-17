"""Simple RNN for fixed-horizon EdgeBox forecasting."""

from __future__ import annotations

import torch
from torch import nn

from .common import INPUT_SIZE, OUTPUT_SIZE, run_model_cli, validate_model_input


class RNNForecaster(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.recurrent = nn.RNN(input_size=INPUT_SIZE, hidden_size=32, num_layers=1, batch_first=True)
        self.output = nn.Linear(32, OUTPUT_SIZE)

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        validate_model_input(inputs)
        _, hidden = self.recurrent(inputs)
        return self.output(hidden[-1])


def build_model() -> RNNForecaster:
    return RNNForecaster()


if __name__ == "__main__":
    run_model_cli("rnn", build_model, hidden_size=32, num_layers=1)
