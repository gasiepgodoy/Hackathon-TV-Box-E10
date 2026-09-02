# EdgeBox FL

## Infraestrutura distribuída de borda com TV Boxes reaproveitadas

O **EdgeBox FL** é uma prova de conceito que propõe o reaproveitamento de **TV Boxes** como nós de borda para uma futura infraestrutura urbana inteligente.

A proposta principal é validar se uma TV Box de baixo custo consegue operar continuamente, coletar dados, armazenar histórico, processar informações localmente, executar modelos leves e preparar atualizações para uma arquitetura de aprendizado federado.

Antes de acoplar sensores externos em campo, o projeto valida se a própria TV Box consegue funcionar como nó computacional confiável.

---

## Objetivo do projeto

O objetivo é verificar se uma TV Box reaproveitada pode atuar como um nó de borda capaz de:

- Coletar dados internos do sistema;
- Armazenar dados localmente;
- Executar inferência com modelos leves;
- Detectar anomalias operacionais;
- Exibir dados em um painel web;
- Enviar médias ou atualizações para um computador central;
- Servir como base futura para uma rede urbana de sensores.

---

## Motivação

Projetos de cidades inteligentes normalmente dependem de sensores, gateways e servidores dedicados, o que pode aumentar o custo e dificultar a implantação em larga escala.

O EdgeBox FL propõe uma alternativa de baixo custo: reutilizar TV Boxes como pequenos computadores de borda.

A ideia é validar primeiro a infraestrutura computacional. Se a TV Box conseguir operar de forma estável, ela poderá futuramente receber sensores externos, como sensores de temperatura, umidade, chuva, qualidade do ar, ruído, presença ou nível da água.

---

## Arquitetura geral

```text
TV Box
  ↓
Coleta de métricas internas
  ↓
Armazenamento local
  ↓
Modelo de risco operacional
  ↓
Autoencoder para detecção de anomalias
  ↓
Dashboard web
  ↓
Futura agregação federada
```

---

## Hardware utilizado

- TV Box com processador Amlogic;
- 2 GB de RAM;
- Debian GNU/Linux ARM64;
- Armazenamento local;
- Acesso via SSH;
- Acesso remoto via Tailscale.

---

## Dados coletados

A própria TV Box é usada como fonte de dados nesta primeira etapa.

As métricas coletadas são:

| Métrica | Descrição |
|---|---|
| CPU | Uso do processador |
| RAM | Uso da memória |
| Temperatura | Temperatura interna do dispositivo |
| Disco | Espaço utilizado no armazenamento |
| Latência | Tempo de resposta da rede |
| Load average | Carga média do sistema |
| Rede | Tráfego de entrada e saída |
| Uptime | Tempo ligado sem reiniciar |

---

## Armazenamento dos dados

Os dados são armazenados localmente na própria TV Box.

Principais arquivos:

```text
/root/aqua-fl/edgebox_metrics.jsonl
/root/aqua-fl/edgebox.db
/root/aqua-fl/edgebox_latest.json
```

O arquivo `edgebox_metrics.jsonl` armazena o histórico bruto das coletas.

O arquivo `edgebox.db` é o banco SQLite local, usado para armazenar os dados de forma estruturada.

---

## Banco de dados

O projeto utiliza SQLite.

Principais tabelas:

| Tabela | Função |
|---|---|
| `metrics` | Armazena as métricas coletadas da TV Box |
| `model_updates` | Armazena atualizações do modelo linear |
| `autoencoder_results` | Armazena inferências do Autoencoder |
| `autoencoder_models` | Armazena modelos Autoencoder treinados |
| `autoencoder_updates` | Armazena atualizações federadas do Autoencoder |

Exemplo de consulta:

```bash
sqlite3 /root/aqua-fl/edgebox.db "SELECT timestamp, cpu_percent, ram_percent, temperature_c, inferred_risk, status FROM metrics ORDER BY id DESC LIMIT 10;"
```

---

## Modelo de risco operacional

O primeiro modelo calcula um **risco operacional** da TV Box.

Esse risco não representa risco de alagamento ou risco ambiental. Ele representa a saúde operacional do nó de borda.

O cálculo considera:

- CPU;
- RAM;
- Temperatura;
- Disco;
- Latência;
- Carga do sistema.

A fórmula base usa uma média ponderada:

```text
Risco =
0,25 × CPU
+ 0,22 × RAM
+ 0,22 × temperatura
+ 0,12 × disco
+ 0,10 × latência
+ 0,09 × carga do sistema
```

Classificação:

```text
0,00 a 0,35 → Estável
0,35 a 0,55 → Atenção
0,55 a 0,75 → Alerta
0,75 a 1,00 → Crítico
```

---

## Autoencoder para detecção de anomalias

Além do modelo de risco operacional, o projeto implementa um **Autoencoder leve** para detecção de anomalias.

O Autoencoder aprende o padrão normal de funcionamento da TV Box. Depois, ele tenta reconstruir os dados atuais. Se a reconstrução fica muito diferente da entrada, o erro aumenta e o sistema identifica uma possível anomalia.

Arquitetura usada:

```text
6 entradas → 3 neurônios → 6 saídas
```

Entradas do modelo:

- CPU;
- RAM;
- Temperatura;
- Disco;
- Latência;
- Carga do sistema.

Saídas:

- Reconstrução das mesmas variáveis.

O modelo calcula:

```text
erro de reconstrução = diferença entre entrada real e saída reconstruída
```

Se o erro passar do limite aprendido durante o treinamento, o sistema indica anomalia.

---

## Aprendizado federado

O EdgeBox FL foi pensado para evoluir para uma arquitetura de **aprendizado federado**.

Em uma rede com várias TV Boxes:

```text
TV Box 1 → treina modelo local
TV Box 2 → treina modelo local
TV Box 3 → treina modelo local
        ↓
Enviam apenas pesos, médias ou atualizações
        ↓
Computador central agrega os modelos
```

A principal vantagem é que os dados brutos permanecem em cada nó local. O sistema compartilha apenas o aprendizado, como pesos do modelo, limiares e estatísticas.

---

## Dashboard web

O projeto possui um painel web local para visualização dos dados.

Acesso na rede local:

```text
http://IP_DA_TVBOX:8080
```

Exemplo:

```text
http://192.168.3.63:8080
```

O painel mostra:

- Status do nó;
- CPU;
- RAM;
- Temperatura;
- Disco;
- Latência;
- Uptime;
- Risco operacional;
- Histórico em gráficos;
- Resultado do Autoencoder;
- Dados do modelo local.

---

## Serviços systemd

O sistema utiliza serviços do Debian para rodar automaticamente.

Principais serviços:

| Serviço | Função |
|---|---|
| `aquafl-web.service` | Mantém o dashboard web online |
| `edgebox-update.service` | Coleta dados e atualiza o painel |
| `edgebox-autoencoder.service` | Executa inferência do Autoencoder |
| `tailscaled.service` | Permite acesso remoto via Tailscale |

Verificar status:

```bash
systemctl status aquafl-web --no-pager
systemctl status edgebox-update --no-pager
systemctl status edgebox-autoencoder --no-pager
systemctl status tailscaled --no-pager
```

---

## Instalação básica

Instalar dependências:

```bash
apt update
apt install -y python3 python3-numpy sqlite3 iputils-ping git
```

Rodar coleta manual:

```bash
python3 edgebox_node.py
```

Treinar Autoencoder:

```bash
python3 edgebox_autoencoder.py train
```

Executar inferência:

```bash
python3 edgebox_autoencoder.py infer
```

---

## Estrutura do projeto

```text
edgebox-fl
├── src/
│   ├── edgebox_node.py
│   ├── edgebox_autoencoder.py
│   ├── edgebox_db_sync.py
│   └── edgebox_site_autoencoder.py
│
├── scripts/
│   ├── edgebox_loop.sh
│   └── edgebox_autoencoder_loop.sh
│
├── systemd/
│   ├── aquafl-web.service
│   ├── edgebox-update.service
│   └── edgebox-autoencoder.service
│
├── data_samples/
│   ├── metrics_last_1000.csv
│   ├── autoencoder_last_1000.csv
│   └── edgebox_metrics_sample.jsonl
│
├── docs/
├── README.md
├── requirements.txt
└── .gitignore
```

---

## Arquivos que não devem ser enviados ao GitHub

Alguns arquivos são gerados localmente e podem ficar muito grandes. Por isso, não devem ser enviados diretamente ao repositório.

Exemplos:

```text
edgebox.db
edgebox_metrics.jsonl
*.log
*.tar.gz
backups/
tokens
chaves SSH
arquivos do Tailscale
```

Para o GitHub, recomenda-se enviar apenas amostras dos dados em `data_samples/`.

---

## Aplicações futuras

Depois da validação da TV Box como nó de borda, a arquitetura pode ser expandida para sensores externos e aplicações urbanas, como:

- Monitoramento de alagamentos;
- Qualidade do ar;
- Ruído urbano;
- Temperatura e umidade;
- Presença;
- Mobilidade urbana;
- Dados comunitários;
- Redes distribuídas de sensores.

---

## Estado atual do projeto

Atualmente, o projeto já possui:

- TV Box com Linux funcionando;
- Coleta automática de métricas internas;
- Dashboard web;
- Banco SQLite local;
- Modelo de risco operacional;
- Autoencoder para anomalias;
- Serviços automáticos com systemd;
- Acesso remoto via Tailscale;
- Repositório GitHub para versionamento.

---

## Conclusão

O EdgeBox FL não é apenas um painel de monitoramento. Ele é uma prova de conceito para validar TV Boxes reaproveitadas como nós inteligentes de borda.

A proposta prepara o caminho para uma infraestrutura urbana distribuída, de baixo custo, escalável e capaz de utilizar aprendizado federado em aplicações futuras.
Líder da equipe deve contatar a [organização do evento](eduardo.godoy@unesp.br) para cadastro de colaborador da pasta para edição.
