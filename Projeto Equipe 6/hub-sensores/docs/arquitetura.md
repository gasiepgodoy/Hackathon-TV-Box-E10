# Decisões de arquitetura

Este documento registra **por que** o sistema é como é, incluindo as alternativas
que foram consideradas e descartadas. A intenção é que outra equipe (ou nós
mesmos daqui a alguns meses) consiga entender os trade-offs sem repetir a
investigação.

## O problema

Monitorar dados climáticos e eventos em áreas isoladas, com dois requisitos em
tensão: **cobrir uma área grande** e **manter o custo por sensor baixo**.

Rádios de longo alcance encarecem cada ponto de medição. Rádios baratos não
alcançam. A solução é hierarquizar: usar o rádio barato onde os sensores estão
concentrados e o caro apenas onde a distância obriga.

## Topologia escolhida: a box como gateway multiprotocolo

```
Sensores Zigbee (~100 m)  ──┐
                             ├──▶  TV Box  ──▶ backhaul ──▶ servidor central
Nós LoRaWAN (~km)  ─────────┘
```

A TV Box acumula três papéis: coordenador Zigbee, gateway LoRaWAN e computador de
borda com banco local.

**Por que o gateway fica na box, e não no servidor remoto.** O isolamento, na
prática, é geográfico e desigual: a área monitorada não tem infraestrutura, mas o
ponto onde se instala o hub geralmente tem. Uma propriedade rural tem a sede com
energia e alguma conectividade — via rádio, 4G ou satélite — enquanto os talhões,
a mata e os açudes ficam a quilômetros de qualquer coisa. Colocar o gateway junto
ao hub, na sede, é exatamente como funcionam as implantações comerciais de
LoRaWAN em agricultura.

## Alternativas descartadas

### LoRa como backhaul (box transmitindo para um gateway distante)

Foi o desenho inicial. Descartado como caminho principal por vazão: o LoRa
transporta dezenas de bytes por mensagem, com limites de tempo de ar. Para
escoar dados concentrados de vários sensores, é pouco — enquanto 4G ou Wi-Fi
resolvem o mesmo com ordens de grandeza mais banda e custo menor.

**Mas não foi abandonado.** Permanece como **rota de emergência**: se o backhaul
principal cair, os eventos de prioridade alta (geada, sensor mudo) ainda saem por
um uplink LoRa curto. Poucos bytes, raros — exatamente o que o LoRa faz bem. É
por isso que o empacotamento binário de 14 bytes por agregado continua no código.

### Gateway transmitindo dados de aplicação para um cliente

Considerado após a inversão da topologia: se a box tem o gateway, poderia ela
usar o transmissor do gateway para enviar dados a um cliente remoto?

Tecnicamente é possível — na classe A o cliente envia um uplink e o gateway
responde na janela de recepção seguinte; na classe C o cliente escuta
continuamente e pode receber a qualquer momento. Descartado por três razões:

1. **Papel invertido.** No LoRaWAN o gateway é um repetidor de camada física, não
   uma fonte de dados de aplicação.
2. **Competição por tempo de ar.** O mesmo rádio precisa reservar capacidade para
   as tarefas da rede — aceitar joins, confirmar recebimentos, ajustar taxas.
   Gastar esse tempo com dados de aplicação degrada o serviço a todos os nós.
3. **Vazão.** Continua sendo LoRa: dezenas de bytes, poucas mensagens por hora.

Se a box precisar mesmo empurrar dados por LoRa, o correto é usar um **rádio de
nó separado**, não o gateway.

### PostgreSQL, TimescaleDB ou InfluxDB

Descartados por peso. São projetados para escala e concorrência que este projeto
não tem, e cobram isso em RAM — o recurso mais escasso numa box de 1,8 GB que
também roda Zigbee2MQTT. O SQLite roda em processo, sem daemon, e dá conta do
volume com folga.

## A fila de saída

É a peça que sustenta a promessa de resiliência. Três tabelas carregam uma flag
`enviado` com índice parcial (`WHERE enviado = 0`), de forma que o índice contém
apenas o que está pendente e encolhe conforme os dados sobem.

A ordem de saída é deliberada:

1. **Eventos** — raros, urgentes, pequenos. Uma geada precisa sair em minutos.
2. **Agregados** — resumos por janela, após o fechamento.
3. **Leituras brutas** — só se houver banda sobrando.

O desenho original mirava o gargalo do LoRa. Com backhaul IP a restrição de
tamanho relaxa, mas a fila continua igualmente necessária: conectividade
intermitente é a regra em campo, não a exceção.

## Por que guardar mínimo e máximo

Uma média horária esconde eventos curtos. Uma geada de 20 minutos entre leituras
de 10 °C produz uma média que não dispara alarme nenhum — e é justamente esse
evento que o projeto existe para capturar. Por isso os agregados carregam
`temp_min` e `temp_max`, e a detecção de eventos observa a leitura mais recente,
não a média.

## Heterogeneidade dos sensores

Os dois tipos têm características opostas, e o sistema precisa acomodar ambos:

| | Tuya TS0201 (Zigbee) | Heltec + BME280 (LoRa) |
|---|---|---|
| Grandezas | temperatura, umidade | temperatura, umidade, pressão |
| Intervalo | fixo, **não configurável** | configurável no firmware |
| Energia | pilha, longa duração | bateria maior ou alimentação |
| Alcance | dezenas de metros | quilômetros |

A impossibilidade de configurar o TS0201 foi verificada na definição do
Zigbee2MQTT: `toZigbee: []` (nenhum comando pode ser enviado ao dispositivo) e
`configure: tuya.configureMagicPacket`, que apenas desperta o sensor sem
configurar relatórios. O intervalo está cravado no firmware.

Consequência prática: **a janela de agregação precisa ser calibrada pela origem**.
Um sensor que reporta a cada hora não se beneficia de agregação horária — nesse
caso é melhor enviar a leitura direto.

## Proteção do cartão SD

Restrição séria: cartões SD morrem por escrita, e o projeto já perdeu um cartão
por corrupção durante o desenvolvimento (além de dois cartões novos que vieram
defeituosos de fábrica, aceitando escrita sem reter dados).

As mitigações estão descritas no README. A mais relevante é a **gravação em
lote**: acumular leituras em memória e gravar a cada 20 registros ou 5 minutos
reduz as escritas diárias de milhares para centenas. O buffer é descarregado no
desligamento, então não há perda.

Isso é também um argumento contra rodar o ChirpStack completo na box: o
PostgreSQL escreve muito mais que o SQLite.

## Limite do protótipo

Uma Heltec como concentrador é um **gateway de canal único**: os nós precisam
ficar fixos em um canal e spreading factor, o join OTAA normalmente não funciona
(o JoinAccept é um downlink) e é preciso usar ABP com chaves fixas.

Numa implantação real usa-se um concentrador de 8 canais (SX1302, como RAK2287),
que elimina todas essas restrições. **A troca é de hardware — a arquitetura de
software permanece idêntica.** Vale explicitar isso: saber onde está o protótipo
e onde está o produto é parte do projeto.
