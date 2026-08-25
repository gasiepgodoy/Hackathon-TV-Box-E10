#!/usr/bin/env python3
# Agente da borda: cliente MQTT + modo pareamento (lê QR pela câmera,
# conecta Wi-Fi e reivindica o aparelho). Lê /opt/secbox/{device,config}.json.
import json, time, subprocess, threading, os
from urllib.parse import quote
import paho.mqtt.client as mqtt

BASE = "/opt/secbox"
dev = json.load(open(f"{BASE}/device.json"))
cfg = json.load(open(f"{BASE}/config.json"))

_MTX_PASS = (cfg.get("mtx_internal_pass") or "").strip()
# Mesma razão do motion.py: sem exceção por IP, todo consumidor se autentica.
RTSP_URL = (cfg["rtsp_url"].replace("://", "://box:%s@" % quote(_MTX_PASS, safe=""), 1)
            if _MTX_PASS else cfg["rtsp_url"])

DEVICE_ID    = dev["device_id"]
SECRET       = dev.get("secret","")
BASE_TOPIC   = f"devices/{DEVICE_ID}"
CMD_TOPIC    = f"{BASE_TOPIC}/+/command"
STATUS_TOPIC = f"{BASE_TOPIC}/status"
RESULT_TOPIC = f"{BASE_TOPIC}/provisioning/result"
CLAIM_TOPIC  = "provisioning/claim"
CLAIMED_FLAG = f"{BASE}/claimed"

def publish_event(client, module, etype, extra=None):
    body = {"type": etype}
    if extra: body.update(extra)
    client.publish(f"{BASE_TOPIC}/{module}/event", json.dumps(body), qos=1)

def take_snapshot(path="/tmp/snap.jpg"):
    subprocess.run(["ffmpeg","-y","-i",RTSP_URL,"-frames:v","1",path],
                   timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path

def scan_qr():
    subprocess.run(["ffmpeg","-y","-i",RTSP_URL,"-frames:v","1","/tmp/scan.jpg"],
                   timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        out = subprocess.run(["zbarimg","-q","--raw","/tmp/scan.jpg"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None

def connect_wifi(ssid, password):
    print("Conectando ao Wi-Fi:", ssid)
    try:
        r = subprocess.run(["nmcli","device","wifi","connect",ssid,"password",password],
                           capture_output=True, text=True, timeout=45)
        print("nmcli:", (r.stdout or r.stderr).strip())
        return r.returncode == 0
    except Exception as e:
        print("Erro Wi-Fi:", e)
        return False

def provisioning_loop(client):
    print("Modo pareamento: escaneando QR...")
    while not os.path.exists(CLAIMED_FLAG):
        data = scan_qr()
        if data:
            print("QR lido:", data)
            try: info = json.loads(data)
            except Exception: info = {"token": data}
            token = info.get("token")
            ssid = info.get("ssid")
            if ssid:
                connect_wifi(ssid, info.get("pass",""))
                for _ in range(30):
                    if client.is_connected(): break
                    time.sleep(1)
            if token:
                client.publish(CLAIM_TOPIC, json.dumps(
                    {"deviceId": DEVICE_ID, "secret": SECRET, "token": token}), qos=1)
                print("Claim enviado, token:", token)
        time.sleep(2)
    print("Pareado, saindo do modo pareamento.")

def handle_command(client, module, cmd):
    action = cmd.get("action")
    print("Comando:", module, action)
    if module == "camera":
        if action == "snapshot":
            take_snapshot(); publish_event(client,"camera","snapshot_taken")
        elif action == "clear_recordings":
            subprocess.run(["/opt/mediamtx/clear-rec.sh"])
            publish_event(client,"camera","recordings_cleared")

def on_connect(client, userdata, flags, rc):
    print("Conectado ao broker rc=", rc)
    client.subscribe(CMD_TOPIC, qos=1)
    client.subscribe(RESULT_TOPIC, qos=1)
    client.publish(STATUS_TOPIC,
        json.dumps({"online": True, "device_id": DEVICE_ID}), qos=1, retain=True)

def on_message(client, userdata, msg):
    topic = msg.topic
    try: data = json.loads(msg.payload.decode() or "{}")
    except Exception: data = {}
    if topic == RESULT_TOPIC:
        if data.get("result") == "ok":
            open(CLAIMED_FLAG, "w").write("ok")
            print("Pareamento confirmado pelo servidor.")
        return
    parts = topic.split("/")
    module = parts[2] if len(parts) > 2 else "?"
    handle_command(client, module, data)

def heartbeat(client):
    while True:
        client.publish(f"{BASE_TOPIC}/heartbeat",
                       json.dumps({"ts": int(time.time())}), qos=0)
        time.sleep(30)

def notify_enabled(key):
    try:
        s = json.load(open(f"{BASE}/camera-settings.json"))
        return bool(s.get("notify", {}).get(key, True))
    except Exception:
        return True

def camera_watch(client):
    # Avisa quando uma câmera some ou volta. A referência é o cameras.json, que
    # o gen-cameras.py reescreve a cada 30s com o que está de fato conectado.
    # Começa com known=None para não alarmar na primeira leitura (boot).
    known = None
    while True:
        try:
            cams = json.load(open(f"{BASE}/cameras.json")).get("cameras", [])
            cur = {c.get("id") or c["path"]: c.get("name", "Câmera") for c in cams}
        except Exception:
            time.sleep(15)
            continue
        if known is not None and cur != known and notify_enabled("camera_offline"):
            for cid, name in known.items():
                if cid not in cur:
                    publish_event(client, "camera", "camera_offline",
                                  {"camera": cid, "name": name})
                    print("Camera offline:", name, flush=True)
            for cid, name in cur.items():
                if cid not in known:
                    publish_event(client, "camera", "camera_online",
                                  {"camera": cid, "name": name})
                    print("Camera online:", name, flush=True)
        known = cur
        time.sleep(15)

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"agent-{DEVICE_ID}")
except (AttributeError, TypeError):
    client = mqtt.Client(client_id=f"agent-{DEVICE_ID}")

client.username_pw_set(cfg["broker_user"], cfg["broker_pass"])
client.will_set(STATUS_TOPIC,
    json.dumps({"online": False, "device_id": DEVICE_ID}), qos=1, retain=True)
client.on_connect = on_connect
client.on_message = on_message
client.connect_async(cfg["broker_host"], int(cfg["broker_port"]), keepalive=60)
threading.Thread(target=heartbeat, args=(client,), daemon=True).start()
threading.Thread(target=camera_watch, args=(client,), daemon=True).start()
if not os.path.exists(CLAIMED_FLAG):
    threading.Thread(target=provisioning_loop, args=(client,), daemon=True).start()
client.loop_forever(retry_first_connection=True)
