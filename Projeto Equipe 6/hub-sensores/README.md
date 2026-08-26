# Hub de sensores para áreas isoladas

Transforma uma TV Box descaracterizada em um **gateway multiprotocolo de borda**:
concentra sensores próximos por Zigbee e sensores distantes por LoRaWAN, guarda
tudo num banco local, processa na própria borda e sincroniza com um servidor
central quando houver conectividade.

O ponto central é a **resiliência**: se o enlace de saída cair, nada se perde —
os dados se acumulam numa fila e sobem quando a comunicação voltar.

## Arquitetura

```
   Sensores Zigbee                          Nós LoRaWAN
   (dezenas de metros)                      (quilômetros)
   Tuya TS0201                              Heltec V2 + BME280
   temperatura · umidade                    temp · umidade · pressão
          │                                        │
          │ 2,4 GHz                                │ 915 MHz (AU915)
          ▼                                        ▼
   ┌──────────────────────────────────────────────────────┐
   │                  TV BOX (hub de borda)               │
   │                                                      │
   │   dongle CC2652          concentrador LoRa           │
   │        │                        │                    │
   │   Zigbee2MQTT            gateway LoRaWAN             │
   │        └──────────┬─────────────┘                    │
   │                   ▼                                  │
   │                 MQTT                                 │
   │                   ▼                                  │
   │        coletor ──▶ SQLite ──▶ agregador · eventos    │
   │                       │                              │
   │                       ▼                              │
   │                  fila de saída                       │
   └───────────────────────┬──────────────────────────────┘
                           │ backhaul intermitente
                           │ (Wi-Fi · 4G · LoRa p/ emergência)
                           ▼
                    servidor central
```

A escolha de dois protocolos é econômica: sensores Zigbee são baratos porque não
carregam rádio de longo alcance, e cobrem bem uma área concentrada. Onde a
distância inviabiliza o Zigbee, entram nós LoRaWAN — mais caros por unidade, mas
poucos e cobrindo quilômetros. A TV Box concentra os dois.

**Por que o gateway fica na box.** Em campo, a área monitorada costuma ser
isolada, mas o ponto onde se instala o hub geralmente não é — uma propriedade
rural tem a sede com energia e alguma conectividade, enquanto os talhões ficam a
quilômetros. Colocar o gateway LoRaWAN junto ao hub é a topologia usada em
implantações comerciais de agricultura. Detalhes e alternativas descartadas em
[docs/arquitetura.md](docs/arquitetura.md).

## Hardware

| Papel | Equipamento |
|---|---|
| Hub de borda | TV Box BTV E10 (Amlogic S905X2, 1,8 GB RAM), Debian 13 arm64 |
| Coordenador Zigbee | Dongle USB CC2652 (Z-Stack 3.x.0), conversor CH340 |
| Sensores Zigbee | Tuya TS0201 — temperatura e umidade, a pilha |
| Nós LoRa | Heltec WiFi LoRa 32 V2 (915 MHz) + BME280 |

## Por que SQLite

Roda dentro do próprio processo, sem daemon consumindo a RAM escassa da box, e o
banco inteiro é um arquivo — backup é copiar. O volume é pequeno: mesmo com
dezenas de sensores em intervalos curtos, fica na casa de poucas centenas de MB
por ano, algo trivial para o SQLite.

## O que sobe pelo backhaul

| O quê | Quando sobe |
|---|---|
| Eventos (geada, sensor mudo, bateria) | Imediatamente, por prioridade |
| Agregados por janela | Após o fechamento da janela |
| Leituras brutas | Só se houver banda sobrando |

Com backhaul IP (Wi-Fi/4G) não há limite rígido de payload, mas a agregação
continua valendo: em link 4G tarifado ela reduz custo, e se o backhaul cair por
dias a fila não explode. O empacotamento binário de 14 bytes por agregado
permanece implementado para a **rota de emergência por LoRa**, usada quando o
backhaul principal está fora e só os alertas críticos precisam sair.

Os agregados guardam **mínimo e máximo**, não só a média: uma geada de 20 minutos
desaparece numa média horária, e é exatamente o evento que o projeto quer captar.

## Sobre a frequência dos sensores

Os dois tipos de sensor têm características opostas, e isso afeta a configuração:

**Tuya TS0201 (Zigbee) — intervalo fixo, não configurável.** A definição no
Zigbee2MQTT tem `toZigbee: []` e um `configure` que só envia o *magic packet*,
sem `configureReporting`. Não há canal para alterar o intervalo; ele está cravado
no firmware. O sensor reporta por mudança de valor e periodicamente — o que ajuda
em eventos rápidos, mas produz poucas amostras em ambiente estável.

**BME280 (LoRa) — intervalo configurável no firmware do nó.** Aqui você decide a
cadência, equilibrando resolução contra autonomia de bateria e tempo de ar.

Como consequência, **a janela de agregação deve ser ajustada por origem**. Meça o
intervalo real antes de definir:

```sql
SELECT ts - LAG(ts) OVER (ORDER BY ts) AS segundos
FROM leituras WHERE sensor_id = 1 ORDER BY ts DESC LIMIT 20;
```

Ajuste `janela_s` para que cada janela contenha ao menos 6 amostras. Se um sensor
reportar mais devagar que isso, agregá-lo não traz ganho — envie as leituras
direto.

## Instalação

Requer apenas Python 3 e `mosquitto-clients` — nenhuma dependência via pip.

```bash
sudo cp -r . /opt/hub-sensores
sudo mkdir -p /etc/hub /var/lib/hub
sudo cp config/hub.example.ini /etc/hub/hub.ini
sudo cp systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hub-coletor.service hub-ciclo.timer hub-purga.timer
```

⚠️ A TV Box vem **sem swap**. Antes de instalar o gateway LoRaWAN, crie uma área
de troca — sem ela, qualquer pico de memória aciona o OOM killer sem aviso:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Uso

```bash
export PYTHONPATH=/opt/hub-sensores/src HUB_CONFIG=/etc/hub/hub.ini

python3 -m hub.cli status          # visão geral
python3 -m hub.cli leituras -n 20  # últimas leituras
python3 -m hub.cli pendentes       # fila aguardando sincronização
python3 -m hub.cli espiar          # diagnóstico: o que passa no MQTT e por quê é aceito
python3 -m hub.cli nomear sensor_01 "Estufa Norte" --local "Setor A"
```

O `espiar` é a ferramenta de depuração principal: mostra cada mensagem que chega
ao broker e, quando descartada, **o motivo exato**.

## Demonstração

Sem esperar horas de dados reais:

```bash
export HUB_DB=/tmp/demo.db PYTHONPATH=src

python3 -m hub.simular --horas 12        # gera histórico com uma geada
python3 -m hub.ciclo                     # agrega, detecta eventos, envia
python3 -m hub.cli pendentes

# A prova de resiliência: derruba o enlace, mostra a fila crescendo, religa
python3 -m hub.simular --horas 2
python3 -m hub.ciclo --transporte offline   # nada sobe, nada se perde
python3 -m hub.cli pendentes
python3 -m hub.ciclo --max 100              # enlace volta: a fila esvazia
```

## Testes

```bash
python3 tests/test_hub.py
```

## Cuidados com o cartão SD

Cartões SD morrem por escrita, e banco de dados escreve o tempo todo. As
proteções aplicadas:

- **WAL + `synchronous=NORMAL`** — menos escrita física, mantendo durabilidade
  contra queda de processo;
- **gravação em lote** — as leituras se acumulam em memória e vão ao disco a cada
  20 registros ou 5 minutos, o que reduz de milhares para centenas as escritas
  diárias (o buffer é descarregado no desligamento, então nada se perde);
- **retenção** — leituras brutas com mais de 90 dias são apagadas; agregados são
  mantidos para sempre, pois são muito menores.

Se for rodar o ChirpStack completo na box, considere que o PostgreSQL escreve
bem mais que o SQLite — outra razão para preferir a pilha leve.

## Estrutura

```
sql/schema.sql        esquema e índices
src/hub/coletor.py    MQTT → banco (serviço contínuo)
src/hub/agregador.py  leituras → resumos por janela
src/hub/eventos.py    processamento de borda (geada, sensor mudo, bateria)
src/hub/enviador.py   fila e empacotamento binário
src/hub/ciclo.py      agregação + eventos + envio (timer)
src/hub/cli.py        inspeção, diagnóstico e manutenção
src/hub/simular.py    dados sintéticos para teste e demonstração
docs/arquitetura.md   decisões de arquitetura e alternativas descartadas
```

## Integração do transporte

O envio é plugável. Hoje existem `TransporteLog`, `TransporteMQTT` e
`TransporteIndisponivel` (que simula queda, para a demonstração). Para o backhaul
real, implemente `TransporteHTTP` ou `TransporteSerial` em `enviador.py` — o
resto do sistema não muda.

## Limitações conhecidas

- **Gateway de canal único.** Com uma Heltec como concentrador, os nós precisam
  ficar fixos em um canal e usar ABP em vez de OTAA, e os downlinks são pouco
  confiáveis. Uma implantação real usaria um concentrador de 8 canais (SX1302).
  A troca é de hardware; a arquitetura de software não muda.
- **`enviado` marca transmissão, não recepção.** Sem downlink confiável não há
  ACK fim a fim. Com backhaul IP isso deixa de ser problema.
- **Intervalo dos TS0201 não é ajustável** (ver seção acima).
