# EdgeBox forecasting models

All models use the same normalized `forecast_w60_h60` dataset and run explicitly on CPU.
From the repository root, train them with:

```bash
python -m fluxos.edgebox.models.linear --epochs 25 --batch-size 32 --learning-rate 0.001
python -m fluxos.edgebox.models.mlp --epochs 25 --batch-size 32 --learning-rate 0.001
python -m fluxos.edgebox.models.rnn --epochs 25 --batch-size 32 --learning-rate 0.001
python -m fluxos.edgebox.models.gru --epochs 25 --batch-size 32 --learning-rate 0.001
python -m fluxos.edgebox.models.lstm --epochs 25 --batch-size 32 --learning-rate 0.001
```

The optional `--seed` argument defaults to `42`. Outputs are written to
`dados/edgebox/models/<model>/w60_h60/` as `model.pt`, `model.json`, and
`metrics.json`. The weights file contains only the model `state_dict`.

`requirements-benchmark.txt` is platform-neutral. On the Linux ARM64 TV Box,
install the CPU wheel explicitly before installing the remaining requirements:

```bash
pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-benchmark.txt
```

No CUDA device is selected or required.
