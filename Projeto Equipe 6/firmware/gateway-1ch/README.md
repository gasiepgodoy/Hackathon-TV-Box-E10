# Gateway LoRaWAN de canal único

Roda na segunda placa **Heltec WiFi LoRa 32 V2**, que fica fora da TV Box: recebe
o rádio dos nós e repassa os pacotes por Wi-Fi, no protocolo Semtech UDP
(*packet forwarder*), para o ChirpStack Gateway Bridge da box.

> Um gateway de canal único **não é um gateway LoRaWAN de verdade**: escuta uma
> frequência e um spreading factor só, e os downlinks são pouco confiáveis. Foi o
> que usamos porque é o rádio que tínhamos. Num gateway real (RAK2287, Mikrotik
> wAP LR8, qualquer concentrador SX1302) **nada desta pasta é necessário** — e o
> software da TV Box não muda.

## Procedência

**Projeto original:** [things4u/ESP-1ch-Gateway](https://github.com/things4u/ESP-1ch-Gateway)
— de **Maarten Westenberg**, licença MIT (cópia em
[`LICENSE-upstream.md`](LICENSE-upstream.md)). Partimos do commit `3b02352`,
versão 6.2.8.

Em [`ESP-sc-gway/`](ESP-sc-gway/) estão **os quatro arquivos que alteramos**, na
forma exata em que foram compilados e gravados na placa — só a linha da senha do
Wi-Fi está redigida. Os outros ~16 arquivos do projeto não foram tocados e
continuam no repositório do autor; não os copiamos para cá para não esconder de
quem é o trabalho nem manter um fork desatualizado.

O arquivo [`alteracoes.patch`](alteracoes.patch) é o diff completo contra o
upstream, se você quiser ver só o que mudou.

### Como montar o sketch

```bash
git clone https://github.com/things4u/ESP-1ch-Gateway
cd ESP-1ch-Gateway
cp -r src ESP-sc-gway                       # a pasta tem que ter o nome do .ino
cp /caminho/firmware/gateway-1ch/ESP-sc-gway/* ESP-sc-gway/
```

Depois preencha o `wpa[]` em `configNode.h` e abra `ESP-sc-gway/ESP-sc-gway.ino`
na Arduino IDE, placa **Heltec WiFi LoRa 32 (V2)**.

## O que alteramos, e por quê

São sete mudanças em quatro arquivos. As quatro primeiras são configuração
esperada; as três últimas são correções que só aparecem quando o conjunto
começa a rodar.

### Configuração — `configGway.h`

| Upstream | Nossa versão | Por quê |
|---|---|---|
| `#define EU863_870 1` | `#define AU925_928 1` | O Brasil usa LA915, derivado do AU915. A tabela de frequências do upstream para `AU925_928` começa em 916,8 MHz, que no plano AU915 é o canal 8 — **sub-banda 2**. É por isso que o ChirpStack tem que estar na região `au915_1`. |
| `#define _SPREADING SF9` | `#define _SPREADING SF7` | Tem que ser igual ao `_SF_TRABALHO` do nó. Gateway de canal único só recebe se frequência **e** spreading factor baterem. |
| `#define _PIN_OUT 1` | `#define _PIN_OUT 4` | `4` é o mapa de pinos Heltec/TTGO ESP32. |
| `_TTNSERVER "eu1.cloud.thethings.network"` | `"192.168.4.1"`, porta 1700 | O destino não é mais o TTN: é o ChirpStack Gateway Bridge rodando na box. Quem publica no MQTT é o Bridge, já dentro da box. |

### Horário — `configGway.h`

| Upstream | Nossa versão | Por quê |
|---|---|---|
| `NTP_TIMESERVER "nl.pool.ntp.org"` | `"192.168.4.1"` | Em campo não há internet, então não há como alcançar um pool NTP público. O relógio vem da própria box. |
| `NTP_TIMEZONES 2` | `-3` | O `2` era da Holanda, do autor original. |

Estes dois andam junto com o `_TTNSERVER`: **se a box mudar de rede, são dois
lugares para alterar**, não um.

### Identificação — `configNode.h`

`_DESCRIPTION`, `_EMAIL`, `_PLATFORM`, `_LAT`, `_LON` e `_ALT` vinham com os
dados do autor original (Holanda). Eles sobem no pacote de status e aparecem na
ficha do gateway no ChirpStack, então trocamos pelos nossos. As coordenadas são
aproximadas de Sorocaba — só afetam o pino no mapa, não o rádio.

A linha do `wpa[]` (SSID e senha do Wi-Fi, em texto puro) está **redigida** neste
repositório. No fork ela está protegida por `.gitignore`, com a ressalva de que
`.gitignore` não tem efeito sobre arquivo que o git já rastreia.

### Correção — `ESP-sc-gway.ino`: `WiFiManager` compilava mesmo desligado

O `#include <WiFiManager.h>` estava fora de qualquer guarda, então a biblioteca
era compilada mesmo com `_WIFIMANAGER 0`. No core ESP32 2.x isso **quebra a
compilação**: a assinatura de `WiFi.onEvent` mudou. Envolvemos o include em
`#if _WIFIMANAGER==1`. Com as credenciais fixas no `wpa[]`, o portal de
configuração não faz falta.

### Correção — `_txRx.ino`: 916.8 MHz virava 916.799987

Esta é a mais difícil de achar. O upstream formata a frequência do uplink com
`ftoa()`, que recebe um **float de 32 bits** — e float de 32 bits não representa
916,8 com precisão suficiente. O valor chegava ao servidor como `916799987`, e o
ChirpStack recusava o pacote com:

```
No channel found for frequency: 916799987
```

O uplink era recebido pelo rádio, aparecia no serial do gateway, e **morria no
servidor** por 13 Hz de diferença. Trocamos por `snprintf` com aritmética
inteira, dividindo e tirando o resto sobre o valor em hertz, sem nunca passar por
ponto flutuante.

### Documentação — `configGway.h`: como o Gateway EUI é formado

Não há `#define` para o EUI, e isso não está dito em lugar nenhum do upstream.
Ele é montado em tempo de execução a partir do MAC da placa, com **dois bytes
inseridos no meio** (`_udpSemtech.ino`, em `sendPullData()` e `sendstat()`):

```
MAC 3c:71:bf:6b:8d:c4   ->   EUI 3c71bf FFFF 6b8dc4
```

⚠️ **Este fork usa `FF FF` de enchimento.** A convenção mais comum na literatura
LoRaWAN é `FF FE`. Se você registrar `3c71bfFFFE6b8dc4` no ChirpStack, o gateway
associa no Wi-Fi, transmite, mostra tudo certo no display — e o servidor descarta
cada pacote em silêncio, por EUI desconhecido. O protocolo Semtech UDP não tem
resposta negativa para gateway não cadastrado, então **não aparece erro em lugar
nenhum**.

Confira sempre o EUI da placa que está na mesa: abra o Monitor Serial a 115200 no
boot e procure a linha `Gateway ID:`.

## ⚠️ O servidor tem que estar na mesma rede em que o gateway associou

O outro erro que custa uma tarde, pelo mesmo motivo: **falha em silêncio**. O
gateway sobe, associa, mostra "conectado" — e nenhum uplink chega. O sintoma é
idêntico ao de um nó fora de alcance.

| Se o gateway associa em… | `_TTNSERVER` e `NTP_TIMESERVER` devem ser |
|---|---|
| `hub-campo` (o AP da própria box) | `192.168.4.1` |
| uma rede Wi-Fi existente | o IP da box **nessa** rede |

Os arquivos aqui estão na primeira linha da tabela, que é a topologia de campo.
Se você mudar o SSID no `configNode.h`, confira os dois IPs no `configGway.h` —
cada um sozinho parece correto.

## Registrar o gateway no ChirpStack

Em **Gateways → Add gateway**, com a EUI que a placa imprime no serial (veja a
armadilha do `FFFF` acima) e região `au915_1`. Sem isso o Gateway Bridge recebe
os pacotes UDP e o ChirpStack os descarta como vindos de gateway desconhecido.
