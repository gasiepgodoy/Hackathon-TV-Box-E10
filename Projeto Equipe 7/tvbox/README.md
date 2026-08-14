# Borda — TV Box (Linux, ARM)

Software do equipamento: câmera (ao vivo + gravação), agente MQTT, detecção de
movimento, remux de clipes e LEDs de status.

## Conteúdo

| Arquivo | Onde vai | Função |
|---|---|---|
| [`mediamtx.yml`](mediamtx.yml) | `/opt/mediamtx/` | Captura da webcam, WebRTC/RTSP, gravação e playback. |
| [`agent.py`](agent.py) | `/opt/secbox/` | Cliente MQTT: comandos, eventos e **modo pareamento** (QR + Wi-Fi). |
| [`motion.py`](motion.py) | `/opt/secbox/` | Detecção de movimento → publica `alarme`. |
| [`leds.py`](leds.py) | `/opt/secbox/` | LEDs de status (GPIO/libgpiod). |
| [`clip-server.py`](clip-server.py) | `/opt/secbox-clip/` | Clipes em MP4 (com cache), câmeras, armazenamento e ajustes (porta 9997). |
| [`gen-cameras.py`](gen-cameras.py) | `/opt/secbox/` | Detecta as câmeras e gera o `mediamtx.yml` conforme qualidade/retenção. |
| [`clear-rec.sh`](clear-rec.sh) | `/opt/mediamtx/` | Apaga todas as gravações. |
| [`sd-guard.sh`](sd-guard.sh) | `/opt/mediamtx/` | Limpa gravações antigas por espaço livre. |
| [`wifi-guard.sh`](wifi-guard.sh) | `/opt/secbox/` | Detecta a queda do Wi-Fi interno e recupera sem intervenção (reconecta → recarrega o driver → reinicia). |
| [`config.example.json`](config.example.json) | `/opt/secbox/config.json` | Modelo de configuração (broker, RTSP, limiar de movimento). |
| [`systemd/`](systemd/) | `/etc/systemd/system/` | Serviços (habilitar com `systemctl enable --now`). |
| [`WIFI-INTERNO.md`](WIFI-INTERNO.md) | (documentação) | Ativar o Wi-Fi interno (RTL8189FTV) e liberar a porta USB do dongle. |

## Identidade do dispositivo

Cada TV box tem um `/opt/secbox/device.json` gerado uma vez (o `secret` vira o
QR de fábrica):

```json
{ "device_id": "TVB-XXXXXX", "secret": "..." }
```

## Dependências (Debian/Ubuntu ARM)

```bash
apt install -y ffmpeg v4l-utils zbar-tools python3 python3-paho-mqtt python3-libgpiod
# MediaMTX: baixar o binário arm64 do projeto bluenviron/mediamtx
```

## Instalar os serviços

```bash
cp systemd/*.service systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now mediamtx secbox-agent secbox-motion secbox-clip secbox-leds sd-guard.timer
# se estiver usando o Wi-Fi interno, some o vigia da rede:
systemctl enable --now wifi-guard
```

> **Nota de hardware:** webcams USB "gulosas" (ex.: Logitech C920) podem cair do
> barramento na porta da TV box — use um **hub USB com fonte própria**. Se a câmera
> voltar com outro `/dev/videoN`, aponte o `mediamtx.yml` para um caminho estável
> em `/dev/v4l/by-id/`.

## Wi-Fi interno (opcional)

Para liberar a porta USB ocupada por um dongle Wi-Fi, dá para ativar o **Wi-Fi
interno** (chip RTL8189FTV) da TV box — inclusive no kernel 6.18, com o driver
compilado e um ajuste de *device tree*. Passo a passo (com backup e reversão) em
[`WIFI-INTERNO.md`](WIFI-INTERNO.md). O serviço [`systemd/rtl8189fs.service`](systemd/rtl8189fs.service)
carrega o módulo no boot.
