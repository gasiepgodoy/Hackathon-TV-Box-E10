#!/usr/bin/env python3
# Detecção de movimento por câmera: lê o RTSP de cada uma em baixa resolução
# (cinza), compara quadros consecutivos e publica um evento quando a diferença
# passa do limiar. Sem OpenCV (Python puro).
#
# Cada câmera tem seu liga/desliga e sua sensibilidade em camera-settings.json;
# um supervisor acompanha cameras.json e sobe/derruba os detectores conforme as
# câmeras aparecem, somem ou mudam de configuração.
import json
from urllib.parse import quote, time, subprocess, threading
import paho.mqtt.client as mqtt

BASE = "/opt/secbox"
dev = json.load(open(f"{BASE}/device.json"))
cfg = json.load(open(f"{BASE}/config.json"))
DEVICE_ID = dev["device_id"]
TOPIC = f"devices/{DEVICE_ID}/alarme/event"
CAMERAS_JSON = f"{BASE}/cameras.json"
SETTINGS_JSON = f"{BASE}/camera-settings.json"
_MTX_PASS = (cfg.get("mtx_internal_pass") or "").strip()
_base = cfg.get("rtsp_base", "rtsp://localhost:8554")
# O MediaMTX exige credencial até de dentro da box: não há exceção por IP,
# porque o túnel faria todo tráfego externo parecer local.
RTSP_BASE = (_base.replace("://", "://box:%s@" % quote(_MTX_PASS, safe=""), 1)
             if _MTX_PASS else _base)
COOLDOWN = cfg.get("motion_cooldown", 30)
SENS = {"alta": 8, "media": 12, "baixa": 20}  # limiar: menor = mais sensível
W, H = 160, 90
FS = W * H

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1,
                         client_id=f"motion-{DEVICE_ID}")
except (AttributeError, TypeError):
    client = mqtt.Client(client_id=f"motion-{DEVICE_ID}")
client.username_pw_set(cfg["broker_user"], cfg["broker_pass"])
client.connect_async(cfg["broker_host"], int(cfg["broker_port"]), keepalive=60)
client.loop_start()


def load_settings():
    try:
        s = json.load(open(SETTINGS_JSON))
    except Exception:
        s = {}
    if "cameras" not in s:  # formato antigo: o arquivo todo era o mapa
        s = {"cameras": s}
    s.setdefault("cameras", {})
    s.setdefault("notify", {})
    return s


def detect(path, name, thresh, stop):
    cmd = ["ffmpeg", "-loglevel", "quiet", "-rtsp_transport", "tcp",
           "-i", f"{RTSP_BASE}/{path}",
           "-vf", f"fps=3,scale={W}:{H},format=gray", "-f", "rawvideo", "pipe:1"]
    prev, last = None, 0.0
    while not stop.is_set():
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
        while not stop.is_set():
            buf = p.stdout.read(FS)
            if len(buf) < FS:  # fluxo caiu: sai e tenta de novo
                break
            if prev is not None:
                s = n = 0
                for i in range(0, FS, 7):  # amostra 1 de cada 7 pixels
                    d = buf[i] - prev[i]
                    s += d if d >= 0 else -d
                    n += 1
                score = s / n
                now = time.time()
                if score > thresh and now - last > COOLDOWN:
                    last = now
                    client.publish(TOPIC, json.dumps(
                        {"type": "movimento", "camera": path, "name": name,
                         "score": round(score, 1)}), qos=1)
                    print("Movimento em %s (score %.1f)" % (name, score),
                          flush=True)
            prev = buf
        try:
            p.terminate()
        except Exception:
            pass
        prev = None
        if not stop.is_set():
            time.sleep(2)


def wanted():
    # Quais detectores deveriam estar rodando agora: path -> (nome, limiar).
    st = load_settings()
    if not st["notify"].get("motion", True):
        return {}
    try:
        cams = json.load(open(CAMERAS_JSON)).get("cameras", [])
    except Exception:
        return {}
    out = {}
    for c in cams:
        cs = st["cameras"].get(c.get("id", ""), {})
        if not cs.get("motion", True):
            continue
        out[c["path"]] = (c.get("name", c["path"]),
                          SENS.get(cs.get("sensitivity", "media"), 12))
    return out


workers = {}  # path -> (stop_event, assinatura)
print("Deteccao de movimento iniciada", flush=True)
while True:
    want = wanted()
    for path, (stop, sig) in list(workers.items()):
        if want.get(path) != sig:  # saiu, foi desligada ou mudou o limiar
            stop.set()
            del workers[path]
            print("Detector parado: %s" % path, flush=True)
    for path, sig in want.items():
        if path not in workers:
            stop = threading.Event()
            threading.Thread(target=detect, args=(path, sig[0], sig[1], stop),
                             daemon=True).start()
            workers[path] = (stop, sig)
            print("Detector ativo: %s (limiar %d)" % (sig[0], sig[1]), flush=True)
    time.sleep(10)
