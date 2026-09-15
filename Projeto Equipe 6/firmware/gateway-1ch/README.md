# Gateway LoRaWAN de canal único

O código **não está neste repositório**, e é de propósito: ele é de terceiros, e
nossas alterações cabem em 25 linhas. Copiar o projeto inteiro para cá esconderia
de quem é o trabalho e nos obrigaria a manter um fork desatualizado.

**Projeto original:** [things4u/ESP-1ch-Gateway](https://github.com/things4u/ESP-1ch-Gateway)
— gateway LoRaWAN de canal único para ESP8266/ESP32, de Maarten Westenberg.

Rodamos na segunda placa **Heltec WiFi LoRa 32 V2**, que fica fora da TV Box:
recebe o rádio dos nós e repassa os pacotes por Wi-Fi, no protocolo Semtech UDP
(*packet forwarder*), para o ChirpStack Gateway Bridge da box.

> Um gateway de canal único **não é um gateway LoRaWAN de verdade**: escuta uma
> frequência e um spreading factor só, e os downlinks são pouco confiáveis. Foi o
> que usamos porque é o rádio que tínhamos. Num gateway real (RAK2287, Mikrotik
> wAP LR8, qualquer concentrador SX1302) nada disto aqui é necessário — e o
> software da TV Box não muda.

## O que alteramos

Três arquivos, a partir do `master` do upstream:

### `src/configGway.h`

| Linha original | Nossa versão | Por quê |
|---|---|---|
| `#define EU863_870 1` | `#define AU925_928 1` | O Brasil usa LA915, derivado do AU915. A tabela de frequências do upstream para `AU925_928` começa em 916,8 MHz, que no plano AU915 é o canal 8 — **sub-banda 2**. É por isso que o ChirpStack tem que estar na região `au915_1`. |
| `#define _SPREADING SF9` | `#define _SPREADING SF7` | Tem que ser igual ao `_SF_TRABALHO` do nó. Gateway de canal único só recebe se frequência **e** spreading factor baterem. |
| `#define _PIN_OUT 1` | `#define _PIN_OUT 4` | `4` é o mapa de pinos Heltec/TTGO ESP32. |
| `_TTNSERVER "eu1.cloud.thethings.network"` | IP da TV Box | O destino não é mais o TTN: é o ChirpStack Gateway Bridge rodando na box, na porta UDP 1700. Quem publica no MQTT é o Bridge, já dentro da box. |

### `src/configNode.h`

Uma linha, no array `wpa[]`: o SSID e a senha da rede em que o gateway entra.
**Não publicamos essa linha** — é a senha do Wi-Fi em texto puro. No repositório
do fork ela está protegida por `.gitignore`, com a ressalva de que `.gitignore`
não tem efeito sobre arquivo que o git já rastreia.

```c
wpas wpa[] = {
    { "SEU-SSID",  "SUA-SENHA" },
};
```

## ⚠️ O endereço do servidor precisa estar na mesma rede do gateway

Este é o erro que custa uma tarde, porque **falha em silêncio**: o gateway sobe,
associa no Wi-Fi, mostra "conectado" no serial e no display — e nenhum uplink
chega ao ChirpStack. O sintoma é idêntico ao de um nó fora de alcance.

O `_TTNSERVER` tem que ser o IP da box **na mesma rede em que o gateway
associou**:

| Se o gateway associa em… | `_TTNSERVER` deve ser |
|---|---|
| `hub-campo` (o AP da própria box) | `192.168.4.1` |
| uma rede Wi-Fi existente | o IP da box nessa rede |

Na topologia de campo o gateway entra no AP da box, então o valor certo é
`192.168.4.1`. Confira sempre os dois juntos — o SSID no `configNode.h` e o IP no
`configGway.h` —, porque cada um sozinho parece correto.

## Registrar o gateway no ChirpStack

Em **Gateways → Add gateway**, com a EUI que a placa imprime no serial ao subir
e região `au915_1`. Sem isso o Gateway Bridge recebe os pacotes UDP e o
ChirpStack os descarta como vindos de gateway desconhecido.
