# Firmware das placas Heltec

Esta pasta guarda o código que rodou nas **placas ESP32 Heltec** usadas para
testar o EdgeVision: o nó que mede e transmite, e o gateway que recebe o rádio e
repassa para a TV Box.

> **Leia isto antes de qualquer outra coisa.**
>
> Este firmware existe para **validar o sistema com o hardware que tínhamos**.
> Ele não é parte do produto, e o hub na TV Box não depende dele.
>
> O hub recebe dados do **ChirpStack**, por MQTT. Qualquer coisa que entregue
> uplinks ao ChirpStack serve — inclusive, e preferencialmente, **um gateway
> LoRaWAN de verdade** (um concentrador de 8 canais como o RAK2287 ou o
> Mikrotik wAP LR8). Com um gateway real o software da box continua **idêntico**:
> some a necessidade de fixar canal e spreading factor no nó, o OTAA volta a
> funcionar e os nós podem se mover entre canais livremente. A troca é de
> hardware; nenhuma linha de Python muda.
>
> Da mesma forma, o nó aqui é um exemplo. Qualquer dispositivo LoRaWAN
> registrado no ChirpStack que envie JSON é aceito pelo hub, com o sensor que
> for.

## O que tem aqui

| Pasta | O que é |
|---|---|
| [`no-lora/`](no-lora/) | firmware do nó sensor (Heltec V2 + BME280) e o codec do ChirpStack |
| [`gateway-1ch/`](gateway-1ch/) | **só documentação** — o código é de terceiros, veja abaixo |

## Créditos

O firmware do nó parte do **material da disciplina de Redes de Comunicação**, do
professor **Eduardo Paciência Godoy** (UNESP Sorocaba). Dele vêm o esqueleto
LMIC, o tratamento de downlink com controle do LED e o uso do display OLED.

O que a Equipe 6 acrescentou:

- leitura do **BME280** num segundo barramento I2C (`Wire1`), para não disputar
  o barramento com o display;
- payload **JSON com chaves de uma letra**, e o sinal de erro `{"err":"bme280"}`
  quando o sensor não responde;
- modo **ABP** e fixação de canal/SF, necessários por causa do gateway de canal
  único;
- amostragem em **modo forçado** com filtro IIR desligado, porque o modo
  contínuo auto-aquece o sensor em ~1 °C — inaceitável para detectar geada.

O gateway é um fork de projeto de terceiros; os créditos estão em
[`gateway-1ch/README.md`](gateway-1ch/README.md).

## ⚠️ As chaves foram removidas

O `.ino` publicado aqui tem `DEVADDR`, `NWKSKEY`, `APPSKEY` e `APPKEY`
**zerados**. São credenciais da rede LoRaWAN: quem as tem consegue forjar
uplinks e decifrar o tráfego do nó. Elas não entram em repositório público.

Para compilar, gere as suas:

1. no ChirpStack, crie o **Device Profile** com região `au915_1`, MAC 1.0.3,
   **OTAA desligado** (o nó usa ABP) e **validação de contador de quadro
   desligada** — em ABP o `fCnt` volta a zero a cada reinício, e o ChirpStack
   descarta o que parece repetição **sem registrar nada** no log do device, o
   que é indistinguível de "dispositivo não cadastrado";
2. crie o device, abra a aba **Activation** e gere `DevAddr`, `NwkSKey` e
   `AppSKey`;
3. copie os três para o `.ino`, byte a byte, na mesma ordem em que aparecem na
   tela;
4. no Device Profile, aba **Codec**, cole
   [`no-lora/codec-chirpstack.js`](no-lora/codec-chirpstack.js). É opcional — o
   hub decodifica o base64 sozinho se o codec não estiver lá.

O nome que você der ao device no ChirpStack vira o nome do sensor no banco da
box, então vale escolher algo legível (`estufa_norte`, não `device-01`).

## A tríade que precisa bater

É a causa número um de "tudo parece certo e nenhum pacote chega". Os três têm
que concordar, e quando não concordam **nada** aparece em lugar nenhum:

| | nó (`.ino`) | gateway (`configGway.h`) | ChirpStack |
|---|---|---|---|
| Frequência | canal 8 = 916,8 MHz | `AU925_928` | região `au915_1` |
| Spreading factor | `_SF_TRABALHO DR_SF7` | `_SPREADING SF7` | — |
| Sub-banda | canal 8 → sub-banda 2 | idem | sub-banda 2 |

## Ligação do BME280

`VCC → 3V3`, `GND → GND`, `SDA → GPIO21`, `SCL → GPIO22`, endereço `0x76`
(alguns módulos genéricos usam `0x77`; o firmware tenta os dois).

Na Heltec V2 o GPIO21 também é a linha de controle do Vext. Funciona como SDA
porque este firmware não liga o Vext — mas se você alimentar o sensor pelo Vext
em vez do 3V3 fixo, mude o pino.

## Compilar

Arduino IDE, placa **Heltec WiFi LoRa 32 (V2)**. Bibliotecas:

- `MCCI LoRaWAN LMIC library` — com `lmic_project_config.h` definindo `CFG_au915`
- `ArduinoJson`
- `ESP8266 and ESP32 OLED driver for SSD1306`
- `Adafruit BME280 Library`, `Adafruit Unified Sensor` e **`Adafruit BusIO`**

A BusIO é esquecida com frequência. Sem ela o erro é
`Adafruit_I2CDevice.h: No such file or directory`, que não menciona a BusIO em
lugar nenhum.
