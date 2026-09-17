# Proposta de Benchmarking de Modelos AquaFL / EdgeBox

## Contexto

Projeto: AquaFL / EdgeBox  
Branch de desenvolvimento: `teste-modelos`  
Objetivo: testar modelos treinados diretamente na TV Box e descobrir o limite operacional do equipamento, sem alterar a `master` e sem quebrar o fluxo atual.

Esta proposta descreve uma integração segura para benchmarking. Nesta etapa, nenhum modelo novo deve ser implementado, nenhum dado existente deve ser movido e nenhum loop ou serviço automático deve ser alterado.

## Regras desta etapa

1. Não mover, renomear ou apagar arquivos atuais.
2. Não alterar a branch `master`.
3. Não alterar os loops automáticos existentes.
4. Não mudar contratos JSON atuais sem necessidade.
5. Todo código Python novo deve ficar em `fluxos/`.
6. Datasets, modelos e resultados novos devem ficar em `dados/`.
7. O fluxo atual deve continuar funcionando sem depender do benchmark.

## Estrutura de benchmark

```text
dados/edgebox/
├── raw/
├── processed/
├── benchmarks/
└── models/
    ├── linear/
    ├── autoencoder/
    ├── mlp/
    ├── rnn/
    ├── gru/
    └── lstm/

fluxos/edgebox/
├── models/
│   └── __init__.py
└── benchmark/
    └── __init__.py
```

Uso planejado:

- `raw/`: cópias ou snapshots dos dados brutos.
- `processed/`: datasets NumPy prontos para treinamento.
- `models/<tipo>/`: pesos e metadados de modelos benchmark.
- `benchmarks/`: resultados de cada execução.
- `fluxos/edgebox/benchmark/`: código de preparação, monitoramento e relatório.
- `fluxos/edgebox/models/`: implementações futuras dos modelos.

## Ambiente da TV Box

```text
Python: 3.13.5
NumPy: 2.2.4
CPU: aproximadamente 4 threads lógicas
RAM total: aproximadamente 1.86 GB
RAM disponível observada: aproximadamente 123 MB
Coleta atual: aproximadamente a cada 10 segundos
Histórico: aproximadamente 159 mil amostras
Tamanho do JSONL: aproximadamente 89 MB
Banco SQLite: aproximadamente 1.8 GB
```

A baixa memória disponível exige que os benchmarks usem janelas limitadas, leitura incremental ou datasets processados. Não é seguro carregar todo o histórico na memória sem medir o impacto.

## Fluxo atual que não deve ser alterado

```text
coleta da TV Box
    ↓
dados/edgebox/edgebox_metrics.jsonl
    ↓
treinamento/inferência atual
    ↓
JSONs atuais de modelo e resultado
    ↓
dashboard
    ↓
banco/edgebox.db
```

O benchmark deve ser paralelo e isolado:

```text
snapshot dos dados atuais
    ↓
dados/edgebox/raw/
    ↓
preparação
    ↓
dados/edgebox/processed/
    ↓
treinamento benchmark
    ↓
dados/edgebox/models/<tipo>/
    ↓
resultado e métricas
    ↓
dados/edgebox/benchmarks/
```

O benchmark não deve sobrescrever os arquivos de produção:

```text
dados/edgebox/edgebox_metrics.jsonl
dados/edgebox/edgebox_model_update.json
dados/edgebox/edgebox_global_model.json
dados/edgebox/edgebox_autoencoder_model.json
dados/edgebox/edgebox_autoencoder_update.json
```

## Features operacionais

O fluxo atual coleta:

```text
cpu_percent
ram_percent
temperature_c
disk_percent
latency_ms
load1
```

Existem dados faltantes em pequena quantidade. O pipeline de benchmark deve tratar:

- valores ausentes;
- linhas JSON inválidas;
- outliers;
- timestamps inválidos;
- amostras duplicadas;
- ordenação temporal.

O dataset bruto original não deve ser alterado durante esse tratamento.

## Horizonte de forecasting

Como a coleta ocorre a cada 10 segundos:

```text
60 amostras  = 10 minutos
180 amostras = 30 minutos
360 amostras = 1 hora
```

Configuração inicial recomendada:

```text
input_window: 60 amostras
forecast_horizon: 60 amostras
```

Interpretação:

```text
últimos 10 minutos → prever o estado daqui a 10 minutos
```

Para forecasting temporal, o conjunto de treino deve conter dados mais antigos e o conjunto de teste deve conter dados posteriores. Não é recomendável embaralhar todo o histórico antes da divisão, pois isso pode causar vazamento temporal.

## Modelos a avaliar

Ordem progressiva:

```text
1. baseline linear ou autoregressivo
2. autoencoder
3. MLP forecasting
4. RNN
5. GRU
6. LSTM
7. modelos maiores para stress test
```

Variações planejadas:

```text
janelas: 60, 180, 360 amostras
épocas: 10, 25, 50, 100
hidden size: pequeno, médio, grande
quantidade de amostras: 1.000, 5.000, 10.000 e máximo suportado
```

O objetivo não é apenas encontrar o menor erro. É descobrir o melhor compromisso entre qualidade, tempo, memória, temperatura e estabilidade.

## Módulos propostos

### `prepare_dataset.py`

Local:

```text
fluxos/edgebox/benchmark/prepare_dataset.py
```

Responsabilidades:

- ler um snapshot em `dados/edgebox/raw/`;
- validar e ordenar os registros;
- ignorar linhas inválidas sem interromper o pipeline;
- tratar missing values;
- tratar ou marcar outliers;
- normalizar as features;
- criar janelas temporais;
- separar treino, validação e teste por tempo;
- salvar datasets NumPy em `dados/edgebox/processed/`;
- salvar metadados da preparação.

Saídas sugeridas:

```text
dados/edgebox/processed/
├── dataset_metadata.json
├── train_X.npy
├── train_y.npy
├── validation_X.npy
├── validation_y.npy
├── test_X.npy
└── test_y.npy
```

O módulo não deve treinar modelos e não deve modificar o JSONL original.

### `system_monitor.py`

Local:

```text
fluxos/edgebox/benchmark/system_monitor.py
```

Responsabilidades:

- medir CPU do processo;
- medir CPU do sistema;
- medir RAM do processo;
- medir RAM disponível;
- medir temperatura;
- medir `load1`, `load5` e `load15`;
- medir duração do treinamento;
- registrar erros e interrupções;
- indicar possível OOM.

Formato sugerido de amostra:

```json
{
  "timestamp": "2026-09-11T12:00:00",
  "elapsed_seconds": 120.5,
  "cpu_percent_process": 85.2,
  "cpu_percent_system": 72.4,
  "ram_mb_process": 180.4,
  "ram_mb_available": 420.1,
  "temperature_c": 54.2,
  "load1": 2.1,
  "load5": 1.8,
  "load15": 1.4
}
```

O monitor deve ser independente do modelo para permitir comparação justa entre linear, autoencoder, MLP, RNN, GRU e LSTM.

### `benchmark_runner.py`

Local:

```text
fluxos/edgebox/benchmark/benchmark_runner.py
```

Responsabilidades:

- carregar datasets processados;
- selecionar o tipo de modelo;
- aplicar configuração de janela, horizonte e épocas;
- iniciar o monitoramento;
- medir tempo de treinamento;
- capturar erros, timeout e interrupção;
- executar treinamento;
- executar validação e teste;
- salvar pesos e metadados;
- produzir um resultado padronizado.

Cada execução deve ter uma pasta própria:

```text
dados/edgebox/benchmarks/2026-09-11_linear_window60/
├── config.json
├── metrics.jsonl
├── result.json
├── stdout.log
├── stderr.log
└── model/
```

Formato sugerido de `result.json`:

```json
{
  "run_id": "2026-09-11_linear_window60",
  "model_type": "linear",
  "input_window": 60,
  "forecast_horizon": 60,
  "samples": 10000,
  "epochs": 100,
  "status": "success",
  "duration_seconds": 12.4,
  "train_error": 0.021,
  "validation_error": 0.028,
  "test_error": 0.031,
  "cpu_avg_percent": 62.1,
  "cpu_max_percent": 94.2,
  "ram_start_mb": 310.5,
  "ram_peak_mb": 460.2,
  "temperature_start_c": 42.0,
  "temperature_avg_c": 49.1,
  "temperature_max_c": 55.4,
  "load_avg": 1.8,
  "load_max": 3.2,
  "interrupted": false,
  "error_type": null
}
```

Status possíveis:

```text
success
error
oom
interrupted
timeout
invalid_dataset
```

### `benchmark_report.py`

Local:

```text
fluxos/edgebox/benchmark/benchmark_report.py
```

Responsabilidades:

- ler resultados em `dados/edgebox/benchmarks/`;
- comparar modelos e configurações;
- ordenar por erro, tempo e RAM;
- identificar o melhor compromisso;
- gerar resumo JSON;
- gerar CSV;
- gerar relatório Markdown, HTML ou ambos.

Saídas sugeridas:

```text
dados/edgebox/benchmarks/summary.json
dados/edgebox/benchmarks/summary.csv
dados/edgebox/benchmarks/report.html
```

Comparações importantes:

```text
erro versus tempo
erro versus RAM
erro versus temperatura
erro versus tamanho do modelo
```

## Contratos atuais

### Modelo linear atual

O modelo operacional atual usa 7 pesos:

```text
bias
cpu_percent
ram_percent
temperature_c
disk_percent
latency_ms
load1
```

Arquivos atuais:

```text
dados/edgebox/edgebox_model_update.json
dados/edgebox/edgebox_global_model.json
dados/edgebox/edgebox_trained_model.json
```

O benchmark não deve substituir esses arquivos.

### Autoencoder atual

Features:

```text
cpu_percent
ram_percent
temperature_c
disk_percent
latency_ms
load1
```

Arquitetura atual:

```text
6 entradas → 3 neurônios ocultos → 6 saídas
```

Arquivos atuais:

```text
dados/edgebox/edgebox_autoencoder_model.json
dados/edgebox/edgebox_autoencoder_update.json
dados/edgebox/edgebox_autoencoder_latest.json
```

O benchmark deve salvar versões experimentais em:

```text
dados/edgebox/models/autoencoder/
```

sem sobrescrever o modelo usado pelo serviço.

## Riscos de compatibilidade

### Caminho do dataset

Atualmente o código usa:

```python
EDGEBOX_DATA_DIR / "edgebox_metrics.jsonl"
```

Mover esse arquivo para `raw/` exigiria alterações em:

```text
config.py
fluxos/edgebox/edgebox_node.py
fluxos/edgebox/edgebox_autoencoder.py
fluxos/edgebox/train_edgebox_model.py
fluxos/edgebox/edgebox_db_sync.py
```

### Caminho dos modelos

Mover modelos atuais para `models/<tipo>/` exigiria alterar:

```text
fluxos/edgebox/edgebox_node.py
fluxos/edgebox/edgebox_autoencoder.py
fluxos/edgebox/train_edgebox_model.py
fluxos/edgebox/edgebox_db_sync.py
```

Além disso, o loop possui um teste direto para:

```bash
/root/aqua-fl/dados/edgebox/edgebox_autoencoder_model.json
```

Como os loops não devem ser alterados agora, os arquivos de produção devem permanecer no lugar.

### Concorrência

Os serviços atuais continuam escrevendo nos JSONs, logs e banco. O benchmark deve:

- trabalhar com snapshot;
- usar arquivos próprios;
- nunca sobrescrever artefatos de produção;
- evitar escrever em `edgebox.db`;
- registrar seus próprios logs;
- ser executado fora dos loops automáticos.

### Memória

O histórico atual é grande para a memória disponível. O benchmark deve preferir:

- leitura incremental;
- janela limitada;
- agregação temporal;
- `.npy` processado;
- `float32` quando a precisão permitir;
- execução de um experimento por vez;
- medição de pico de RAM.

## Arquivos que não devem ser modificados nesta etapa

```text
fluxos/edgebox/edgebox_node.py
fluxos/edgebox/edgebox_autoencoder.py
fluxos/edgebox/edgebox_db_sync.py
fluxos/edgebox/train_edgebox_model.py
scripts/edgebox_loop.sh
scripts/edgebox_autoencoder_loop.sh
edgebox_loop.sh
edgebox_autoencoder_loop.sh
/etc/systemd/system/edgebox-update.service
/etc/systemd/system/edgebox-autoencoder.service
```

Também não devem ser movidos ou apagados:

```text
dados/edgebox/edgebox_metrics.jsonl
dados/edgebox/edgebox_latest.json
dados/edgebox/edgebox_model_update.json
dados/edgebox/edgebox_global_model.json
dados/edgebox/edgebox_state.json
dados/edgebox/edgebox_trained_model.json
dados/edgebox/edgebox_autoencoder_model.json
dados/edgebox/edgebox_autoencoder_update.json
dados/edgebox/edgebox_autoencoder_latest.json
```

## Arquivos novos planejados

Não implementar ainda, apenas avaliar a arquitetura:

```text
fluxos/edgebox/benchmark/prepare_dataset.py
fluxos/edgebox/benchmark/system_monitor.py
fluxos/edgebox/benchmark/benchmark_runner.py
fluxos/edgebox/benchmark/benchmark_report.py
```

Modelos futuros, quando aprovados:

```text
fluxos/edgebox/models/linear.py
fluxos/edgebox/models/autoencoder.py
fluxos/edgebox/models/mlp.py
fluxos/edgebox/models/rnn.py
fluxos/edgebox/models/gru.py
fluxos/edgebox/models/lstm.py
```

## Lista exata de modificações futuras

### Para adicionar benchmark isolado

Criar:

```text
fluxos/edgebox/benchmark/prepare_dataset.py
fluxos/edgebox/benchmark/system_monitor.py
fluxos/edgebox/benchmark/benchmark_runner.py
fluxos/edgebox/benchmark/benchmark_report.py
```

Opcionalmente criar:

```text
fluxos/edgebox/models/*.py
```

Criar artefatos apenas em:

```text
dados/edgebox/raw/
dados/edgebox/processed/
dados/edgebox/models/
dados/edgebox/benchmarks/
```

Nenhum arquivo atual precisa ser modificado para essa primeira integração.

### Para migrar produção posteriormente

Arquivos que provavelmente precisariam ser alterados:

```text
config.py
fluxos/edgebox/edgebox_node.py
fluxos/edgebox/edgebox_autoencoder.py
fluxos/edgebox/train_edgebox_model.py
fluxos/edgebox/edgebox_db_sync.py
fluxos/edgebox/edgebox_site_autoencoder.py
scripts/edgebox_loop.sh
scripts/edgebox_autoencoder_loop.sh
edgebox_loop.sh
edgebox_autoencoder_loop.sh
/etc/systemd/system/edgebox-update.service
/etc/systemd/system/edgebox-autoencoder.service
```

Essa migração deve ocorrer somente depois de testes e com compatibilidade temporária de caminhos.

## Proposta de primeira implementação

O primeiro passo seguro deve ser somente:

```text
prepare_dataset.py
```

Ele deve:

1. ler uma cópia do histórico atual;
2. salvar um snapshot em `dados/edgebox/raw/`;
3. validar JSON e timestamps;
4. tratar missing values e outliers;
5. criar janelas de 60 amostras;
6. separar treino e teste por tempo;
7. salvar `.npy` em `dados/edgebox/processed/`;
8. gerar `dataset_metadata.json`;
9. não treinar modelo;
10. não alterar os loops;
11. não alterar os contratos existentes;
12. não escrever no banco de produção.

## Checklist para avaliação

```text
[ ] O benchmark é isolado do fluxo atual?
[ ] Nenhum loop foi alterado?
[ ] Nenhum serviço foi alterado?
[ ] Nenhum JSON de produção é sobrescrito?
[ ] O dataset original permanece intacto?
[ ] A divisão treino/teste respeita o tempo?
[ ] Missing values são tratados?
[ ] Outliers são registrados?
[ ] RAM e temperatura são monitoradas?
[ ] O resultado identifica sucesso, erro, OOM e interrupção?
[ ] Cada execução possui um run_id único?
[ ] Os pesos e metadados são reproduzíveis?
[ ] O relatório compara qualidade e custo operacional?
```

## Conclusão

A integração mais segura é manter o fluxo atual exatamente como está e criar o benchmark como um pipeline paralelo:

```text
fluxo atual:
dados/edgebox/edgebox_metrics.jsonl

benchmark:
dados/edgebox/raw/
    ↓
dados/edgebox/processed/
    ↓
dados/edgebox/models/<tipo>/
    ↓
dados/edgebox/benchmarks/
```

A primeira implementação recomendada é o preparador de dataset. Modelos, runner e relatórios devem ser adicionados somente depois que o formato do dataset, o monitoramento e os critérios de avaliação forem aprovados.
