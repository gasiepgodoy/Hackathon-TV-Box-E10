#!/usr/bin/env python3
# Detecção de movimento leve: lê o RTSP do MediaMTX em baixa resolução (cinza),
# faz diferença entre quadros e publica um evento de alarme quando muda além do
# limiar. Sem OpenCV (Python puro). Configuração em /opt/secbox/config.json.
import json, time, subprocess
import paho.mqtt.client as mqtt

BASE = "/opt/secbox"
dev = json.load(open(f"{BASE}/device.json"))
cfg = json.load(open(f"{BASE}/config.json"))
DEVICE_ID = dev["device_id"]
TOPIC = f"devices/{DEVICE_ID}/alarme/event"
RTSP = cfg.get("rtsp_url", "rtsp://localhost:8554/cam")
THRESH = cfg.get("motion_threshold", 12)
COOLDOWN = cfg.get("motion_cooldown", 30)

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"motion-{DEVICE_ID}")
except (AttributeError, TypeError):
    client = mqtt.Client(client_id=f"motion-{DEVICE_ID}")
client.username_pw_set(cfg["broker_user"], cfg["broker_pass"])
client.connect_async(cfg["broker_host"], int(cfg["broker_port"]), keepalive=60)
client.loop_start()

W, H = 160, 90
FS = W * H
cmd = ["ffmpeg", "-loglevel", "quiet", "-rtsp_transport", "tcp", "-i", RTSP,
       "-vf", f"fps=3,scale={W}:{H},format=gray", "-f", "rawvideo", "pipe:1"]

prev = None
last = 0
print("Deteccao de movimento iniciada (thresh %s)" % THRESH)
while True:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    while True:
        buf = p.stdout.read(FS)
        if len(buf) < FS:
            break
        if prev is not None:
            s = n = 0
            for i in range(0, FS, 7):
                d = buf[i] - prev[i]
                s += d if d >= 0 else -d
                n += 1
            score = s / n
            now = time.time()
            if score > THRESH and now - last > COOLDOWN:
                last = now
                client.publish(TOPIC, json.dumps({"type": "movimento", "score": round(score, 1)}), qos=1)
                print("Movimento! score", round(score, 1))
        prev = buf
    try: p.terminate()
    except Exception: pass
    time.sleep(2)
