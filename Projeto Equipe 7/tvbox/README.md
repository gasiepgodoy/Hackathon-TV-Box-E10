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
| [`clip-server.py`](clip-server.py) | `/opt/secbox-clip/` | Remux de gravações para MP4 navegável (porta 9997). |
| [`clear-rec.sh`](clear-rec.sh) | `/opt/mediamtx/` | Apaga todas as gravações. |
| [`sd-guard.sh`](sd-guard.sh) | `/opt/mediamtx/` | Limpa gravações antigas por espaço livre. |
| [`config.example.json`](config.example.json) | `/opt/secbox/config.json` | Modelo de configuração (broker, RTSP, limiar de movimento). |
| [`systemd/`](systemd/) | `/etc/systemd/system/` | Serviços (habilitar com `systemctl enable --now`). |

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
```

> **Nota de hardware:** webcams USB "gulosas" (ex.: Logitech C920) podem cair do
> barramento na porta da TV box — use um **hub USB com fonte própria**. Se a câmera
> voltar com outro `/dev/videoN`, aponte o `mediamtx.yml` para um caminho estável
> em `/dev/v4l/by-id/`.
