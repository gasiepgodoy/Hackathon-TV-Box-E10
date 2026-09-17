# Revisão de arquitetura e benchmark para AquaFL / EdgeBox

## Resumo executivo

Este projeto combina dois fluxos distintos:

1. O fluxo operacional de coleta da TV Box, que escreve métricas em JSONL e alimenta dashboard e banco SQLite.
2. O fluxo experimental de benchmark, que deve operar em paralelo, usando snapshots e datasets processados sem alterar a produção em funcionamento.

A arquitetura proposta é segura e coerente com o contexto do equipamento: recursos limitados, coleta contínua, banco SQLite em crescimento, e necessidade de medir qualidade, tempo, memória e estabilidade dos modelos sem interromper a operação principal.

A etapa atual implementada foi a preparação do dataset benchmark, mantendo a coleta de produção intacta e criando um pipeline isolado em `dados/edgebox/processed/` e `dados/edgebox/raw/`.

---

## Contexto do sistema atual

O fluxo operacional atual funciona como segue:

- coleta de métricas da TV Box;
- gravação em `dados/edgebox/edgebox_metrics.jsonl`;
- sincronização para SQLite;
- atualização dos JSONs do modelo atual;
- renderização do dashboard;
- uso do autoencoder e do modelo global/local.

Esse fluxo é essencial e deve continuar funcionando sem depender do benchmark.

A parte experimental deve ser separada em um pipeline paralelo:

- snapshot de dados em `raw/`;
- validação/ordenação/limpeza;
- criação de Janelas temporais;
- divisão por tempo em treino/validação/teste;
- salvamento em `processed/` com arrays NumPy;
- treinamento de modelos benchmark em ambiente isolado;
- coleta de métricas e resultados em `benchmarks/`.

---

## Risco principal da arquitetura

O risco central não é o algoritmo, mas a perturbação do ambiente de produção. A TV Box possui memória limitada e o histórico em JSONL cresce continuamente. Qualquer mudança no fluxo principal, no formato do JSONL, no código de treino, ou na estrutura de diretórios pode quebrar dashboards, sincronização SQLite e execução dos loops. Por isso, a regra de ouro foi:

> benchmark paralelo e isolado, sem alterar o fluxo atual.

Essa regra está correta e deve ser preservada.

---

## Arquitetura recomendada

### 1. Produção

```text
coleta
  -> dados/edgebox/edgebox_metrics.jsonl
  -> edgebox_db_sync.py
  -> JSONs de modelo/resultado
  -> dashboard
```

Essa parte deve continuar sendo a fonte de verdade operacional.

### 2. Benchmark

```text
snapshot raw
  -> dados/edgebox/raw/
  -> prepare_dataset.py
  -> dados/edgebox/processed/
  -> treinamento de benchmark
  -> dados/edgebox/models/<tipo>/
  -> resultados em dados/edgebox/benchmarks/
```

A separação entre produção e benchmark é o ponto mais importante da proposta.

---

## Validação do dataset preparador

A implementação atual de `fluxos/edgebox/benchmark/prepare_dataset.py` atende ao objetivo inicial de criar um dataset benchmark seguro e temporalmente consistente.

### O que foi feito corretamente

- leitura de um snapshot dos dados de produção;
- validação de JSON e timestamps;
- ordenação temporal;
- detecção de registros duplicados e inválidos;
- tratamento de valores ausentes com base no conjunto de treino;
- padronização de features usando somente estatísticas do treino;
- divisão temporal sem embaralhamento;
- criação de janelas por histórico e horizonte;
- salvamento de `train`, `validation` e `test` em `.npz`;
- geração de metadados de preparação.

### Por que isso é importante

Esse comportamento evita vazamento de informação e respeita a natureza temporal dos dados. Em problemas de series temporais, o embaralhamento aleatório de observações pode tornar a validação artificialmente otimista e invalidar o benchmark.

---

## Critérios de qualidade da preparação

A limpeza e o processamento devem garantir:

- ausência de dados inválidos no conjunto treinável;
- ordenação temporal correta;
- separação estrita de treino/validação/teste;
- uso de estatísticas do conjunto de treino para imputação e normalização;
- janelas consistentes com a frequência de coleta;
- persistência dos dados em arquivos separados da produção.

---

## Cenário real da TV Box

A arquitetura deve considerar as condições do ambiente:

- memória total bem limitada;
- processamento leve preferencialmente;
- coleta cada ~10 segundos;
- histórico grande em JSONL;
- risco de saturação de CPU e temperatura.

Isso sugere que o benchmark inicial deve seguir uma abordagem conservadora:

- janela curta: 60 amostras;
- horizonte curto: 60 amostras;
- amostra inicial limitada para validar o pipeline;
- crescimento gradual conforme memória e tempo permitirem.

A configuração escolhida de 60/60 é sensata e bem alinhada com o intervalo de coleta.

---

## Ordem dos modelos sugerida

A proposta de avaliação progressiva é boa e razoável:

1. baseline linear/autoregressivo;
2. autoencoder;
3. MLP;
4. RNN;
5. GRU;
6. LSTM;
7. modelos maiores em stress test.

Isso permite entender primeiro o limite mínimo da tarefa e depois escalar. Não faz sentido saltar para modelos complexos sem validar a base do problema e o comportamento do dado.

---

## Observações críticas

### 1. O benchmark não deve depender da execução do fluxo principal

Essa é a premissa central. O código de benchmark deve poder ser executado em um snapshot, sem risco de bloquear ou sobrescrever arquivos usados em produção.

### 2. O pipeline de dados deve ser reprodutível

Metadados, seed, janelas e estatísticas devem ser salvos para permitir reuso e comparação entre execuções.

### 3. A memória exige disciplina

Carregar todo o histórico em memória pode ser inviável. Melhor criar snapshots, processar em chunks ou limitar registros por execução experimental.

### 4. Os resultados devem ser comparáveis

Cada execução de benchmark deve registrar:

- arquitetura;
- janela;
- horizonte;
- número de amostras;
- métricas;
- tempo de execução;
- consumo de RAM/CPU;
- temperatura;
- hash do snapshot usado.

---

## Conclusão

A proposta e a implementação atual estão bem alinhadas com a realidade do projeto. A separação entre fluxo operacional e fluxo de benchmark é a decisão correta. A parte de preparação do dataset já está em um bom estágio e representa uma base segura para os próximos passos experimentais.

A próxima etapa recomendada é continuar com modelos simples e controlados, usando o dataset preparado como entrada. Isso permitirá medir real performance, custo computacional e estabilidade do equipamento antes de avançar para arquiteturas mais complexas.

Em resumo: a arquitetura está correta, a abordagem é segura, e a etapa atual de preparação do dataset é uma base adequada para evolução responsável do projeto.

---

## Pergunta para GPT

Com base nesta arquitetura, você acha que a estratégia atual de benchmark está bem desenhada para uma TV Box com memória e CPU limitados? O que eu deveria ajustar antes de avançar para modelos mais complexos?
