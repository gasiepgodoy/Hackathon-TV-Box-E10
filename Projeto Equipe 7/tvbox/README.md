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
| [`alarm.py`](alarm.py) | `/opt/secbox/` | Sirene do alarme por MQTT (`alarme/command`), com tempo máximo. |
| [`gen-sirene.py`](gen-sirene.py) | `/opt/secbox/` | Gera o WAV da sirene localmente, sem depender de download. |
| [`enable-av-audio.py`](enable-av-audio.py) | (ferramenta) | Liga a saída de áudio analógica (jack AV) no device tree. |
| [`clip-server.py`](clip-server.py) | `/opt/secbox-clip/` | Clipes em MP4 (com cache), câmeras, armazenamento e ajustes (porta 9997, **com token**). |
| [`gen-cameras.py`](gen-cameras.py) | `/opt/secbox/` | Detecta as câmeras e gera o `mediamtx.yml` conforme qualidade/retenção. |
| [`clear-rec.sh`](clear-rec.sh) | `/opt/mediamtx/` | Apaga todas as gravações. |
| [`sd-guard.sh`](sd-guard.sh) | `/opt/mediamtx/` | Limpa gravações antigas por espaço livre. |
| [`wifi-guard.sh`](wifi-guard.sh) | `/opt/secbox/` | Detecta a queda do Wi-Fi interno e recupera sem intervenção (reconecta → recarrega o driver → reinicia). |
| [`config.example.json`](config.example.json) | `/opt/secbox/config.json` | Modelo de configuração (broker, RTSP, movimento, sirene, token da 9997). |
| [`systemd/`](systemd/) | `/etc/systemd/system/` | Serviços (habilitar com `systemctl enable --now`). |
| [`WIFI-INTERNO.md`](WIFI-INTERNO.md) | (documentação) | Ativar o Wi-Fi interno (RTL8189FTV) e liberar a porta USB do dongle. |
| [`ALARME.md`](ALARME.md) | (documentação) | Sirene por MQTT — e por que o jack AV não toca com o DTB genérico. |

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
# alarme sonoro (precisa de uma saida de audio funcional, ver ALARME.md):
systemctl enable --now secbox-alarm
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

## Autenticação da porta 9997

O `clip-server` lê `api_token` do `config.json`. Com o token definido, toda rota
(menos `/health`) exige `Authorization: Bearer <token>` ou `?token=` na URL — o
segundo existe porque o player baixa o clipe pela URL, sem lugar para cabeçalho.

**Sem `api_token` o serviço fica aberto**, que era o comportamento do piloto
atrás da Tailscale. Ele avisa no log ao subir, e `/health` responde
`{"ok":true,"auth":false}` — é assim que o monitoramento descobre que a porta
está publicada sem proteção. Isso precisa estar ligado **antes** de expor a box
à internet: `/settings` não apenas lê, **escreve** a configuração das câmeras.

```bash
# gerar e gravar o token na box, sem ele passar por lugar nenhum
python3 - <<'PY'
import json, secrets
p = "/opt/secbox/config.json"
c = json.load(open(p))
c["api_token"] = secrets.token_urlsafe(32)
json.dump(c, open(p, "w"), indent=2)
print("token gravado; leia com: jq -r .api_token", p)
PY
systemctl restart secbox-clip
curl -s http://localhost:9997/health   # deve dizer "auth": true
```
