# AquaFL

## Benchmark de Edge AI em TV Boxes para Monitoramento Ambiental Distribuído

O **AquaFL** investiga o uso de TV Boxes de baixo custo como nós de computação de borda capazes de coletar dados, armazenar histórico, executar modelos de inteligência artificial e realizar treinamento local.

Nesta etapa, a própria TV Box é utilizada como fonte de dados para validar a infraestrutura computacional antes da integração com sensores ambientais externos.

O objetivo é avaliar desempenho, consumo de recursos e limites operacionais do hardware, verificando se TV Boxes reaproveitadas podem ser utilizadas como nós distribuídos de Edge AI e, futuramente, de aprendizado federado.

---

## Objetivo

O projeto busca avaliar se uma TV Box ARM64 de baixo custo pode:

- coletar métricas continuamente;
- armazenar dados localmente;
- executar inferência em tempo real;
- detectar anomalias;
- treinar modelos de aprendizado de máquina;
- executar modelos temporais leves;
- disponibilizar telemetria em um dashboard web;
- atuar futuramente como nó de uma arquitetura de aprendizado federado.

---

## Arquitetura atual

```text
TV Box
   ↓
Coleta de métricas do sistema
   ↓
Histórico local
   ↓
┌──────────────────────────────┐
│ Monitoramento operacional    │
│ Heurística de risco          │
└──────────────────────────────┘
   ↓
┌──────────────────────────────┐
│ Detecção de anomalias        │
│ Autoencoder                  │
└──────────────────────────────┘
   ↓
┌──────────────────────────────┐
│ Benchmark de previsão        │
│ Linear / MLP / RNN / GRU     │
│ / LSTM                       │
└──────────────────────────────┘
   ↓
Dashboard Web
```

---

## Hardware utilizado

A implementação atual utiliza uma TV Box com:

- arquitetura ARM64;
- processador Cortex-A53 quad-core;
- aproximadamente 2 GB de RAM;
- Debian GNU/Linux;
- armazenamento local;
- acesso via SSH;
- acesso remoto através do Tailscale.

---

## Métricas coletadas

A própria TV Box funciona como fonte de dados nesta fase do projeto.

As principais métricas são:

| Métrica | Descrição |
| --- | --- |
| CPU | Utilização do processador |
| RAM | Utilização da memória |
| Temperatura | Temperatura interna do dispositivo |
| Disco | Percentual de armazenamento utilizado |
| Latência | Tempo de resposta da rede |
| Load Average | Carga média do sistema |
| Rede | Tráfego de entrada e saída |
| Uptime | Tempo de funcionamento |

Os dados são armazenados localmente e utilizados tanto pelo dashboard quanto pelos experimentos de aprendizado de máquina.

---

## Risco operacional

O dashboard apresenta um indicador de risco operacional da TV Box.

Esse valor **não representa risco de enchente ou risco ambiental**. Ele representa apenas o estado computacional do nó.

A implementação atual utiliza uma heurística ponderada baseada em:

```text
25% CPU
22% RAM
22% Temperatura
12% Disco
10% Latência
 9% Load Average
```

O valor resultante é utilizado para classificar o estado operacional do dispositivo.

---

## Detecção de anomalias

O projeto também utiliza um Autoencoder leve para detectar comportamentos anormais da TV Box.

Arquitetura atual:

```text
6 entradas
   ↓
3 neurônios
   ↓
6 saídas
```

As entradas correspondem às principais métricas operacionais.

O modelo aprende o comportamento normal do sistema e utiliza o erro de reconstrução para identificar possíveis anomalias.

---

## Benchmark de modelos

Uma das principais etapas do AquaFL é avaliar a capacidade da TV Box de realizar treinamento local.

Atualmente são avaliadas as seguintes arquiteturas supervisionadas:

- Regressão linear;
- MLP;
- RNN;
- GRU;
- LSTM.

Os modelos recebem janelas temporais de métricas da TV Box e realizam previsão de estados futuros.

O benchmark busca comparar:

- erro de previsão;
- tempo de treinamento;
- tempo de inferência;
- consumo de memória;
- uso de CPU;
- temperatura do dispositivo;
- número de parâmetros;
- tamanho do modelo.

A finalidade não é apenas identificar qual modelo apresenta menor erro, mas avaliar quais arquiteturas são viáveis em hardware de baixo custo.

---

## Dashboard

O AquaFL possui um dashboard web para acompanhamento do nó.

O painel apresenta, entre outras informações:

- CPU;
- RAM;
- temperatura;
- disco;
- latência;
- uptime;
- risco operacional;
- histórico recente;
- resultados dos benchmarks;
- métricas dos modelos treinados.

---

## Estrutura do projeto

O código da Equipe 2 está localizado em:

```text
Projeto Equipe 2/
├── readme.md
└── aqua-fl/
```

Dentro de `aqua-fl/`:

```text
aqua-fl/
├── dados/
│   ├── clima/
│   └── edgebox/
│
├── fluxos/
│   ├── clima/
│   └── edgebox/
│       ├── benchmark/
│       └── models/
│
├── scripts/
├── tests/
├── web/
├── config.py
├── server.py
├── edgebox_loop.sh
└── requirements-benchmark.txt
```

---

## Modelos supervisionados

Os modelos utilizados no benchmark estão em:

```text
fluxos/edgebox/models/
```

Atualmente:

```text
linear.py
mlp.py
rnn.py
gru.py
lstm.py
common.py
```

Os resultados dos experimentos podem ser armazenados em:

```text
dados/edgebox/models/
```

---

## Execução na TV Box

A instalação utilizada durante o desenvolvimento considera o projeto localizado em:

```text
/root/aqua-fl
```

Alguns scripts operacionais ainda utilizam esse caminho absoluto.

Para reproduzir exatamente o ambiente atual da TV Box, copie ou clone o conteúdo da pasta `aqua-fl` para:

```bash
/root/aqua-fl
```

Exemplo:

```bash
cd /root
git clone <repositorio>
cp -a "<repositorio>/Projeto Equipe 2/aqua-fl" /root/aqua-fl
cd /root/aqua-fl
```

---

## Dependências para benchmark

O ambiente utilizado para os modelos supervisionados utiliza Python e PyTorch em CPU.

Exemplo:

```bash
python3 -m venv .venv-benchmark
source .venv-benchmark/bin/activate
pip install numpy
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

---

## Arquivos que não são versionados

Arquivos gerados durante a operação podem atingir centenas de megabytes ou gigabytes e não fazem parte do repositório.

Entre eles:

```text
*.db
*.log
__pycache__/
dados/edgebox/raw/
dados/edgebox/processed/
dados/edgebox/edgebox_metrics.jsonl
```

Esses arquivos são criados ou utilizados localmente na TV Box.

---

## Aprendizado federado

O aprendizado federado representa a próxima evolução da arquitetura.

A proposta futura é utilizar múltiplas TV Boxes:

```text
TV Box 1 ─┐
TV Box 2 ─┼── treinamento local
TV Box 3 ─┘
      ↓
atualizações dos modelos
      ↓
agregação federada
      ↓
modelo global
```

Dessa forma, diferentes nós poderão colaborar no treinamento sem necessidade de centralizar todos os dados brutos.

---

## Aplicação ambiental futura

Após validar a TV Box como plataforma de Edge AI, o AquaFL pretende integrar sensores ambientais externos.

Possíveis aplicações incluem:

- monitoramento de chuva;
- nível de rios e córregos;
- enchentes e alagamentos;
- temperatura e umidade;
- qualidade do ar;
- redes distribuídas de sensores urbanos.

A arquitetura também permite explorar transferência de aprendizado entre regiões com diferentes quantidades de dados históricos.

---

## Estado atual

Atualmente o AquaFL possui:

- TV Box ARM64 executando Debian;
- coleta contínua de métricas;
- armazenamento local;
- dashboard web;
- indicador de risco operacional;
- benchmark supervisionado;
- modelos Linear, MLP, RNN, GRU e LSTM;
- treinamento local na própria TV Box;
- acesso remoto através de Tailscale;
- estrutura preparada para expansão futura para aprendizado federado.

---

## Próximas etapas

- ampliar os benchmarks de desempenho;
- avaliar limites de CPU, RAM e temperatura;
- comparar diferentes janelas e horizontes de previsão;
- integrar sensores ambientais;
- testar múltiplas TV Boxes;
- implementar agregação federada;
- avaliar transferência de aprendizado entre diferentes regiões.

---

## Visão do projeto

O AquaFL busca demonstrar que equipamentos baratos e reaproveitados podem funcionar como nós inteligentes de borda.

A proposta combina **reutilização de hardware, Edge AI, monitoramento distribuído e aprendizado federado** para criar uma infraestrutura acessível e escalável para aplicações ambientais.
