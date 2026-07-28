#!/usr/bin/env python3
# LEDs de status (GPIO via libgpiod). Deriva o estado sozinho:
#   power (AO_11, bicolor): verde = MediaMTX + camera conectada/gravando / vermelho = problema
#   net   (AO_4,  bicolor): verde = conectado ao broker / vermelho = sem conexao
#   ir    (GPIOH_5, vermelho, active-high): aceso = internet / apagado = sem internet / piscando = lendo QR (pareamento)
# Ajuste os CHIP/linhas conforme o mapeamento de GPIO da sua TV box.
import json, time, os, socket, subprocess
import gpiod
from gpiod.line import Direction, Value
import paho.mqtt.client as mqtt

BASE = "/opt/secbox"
dev = json.load(open(f"{BASE}/device.json"))
cfg = json.load(open(f"{BASE}/config.json"))
DEVICE_ID = dev["device_id"]
CLAIMED = f"{BASE}/claimed"
CAMERAS = f"{BASE}/cameras.json"

# LEDs bicolor no banco AO (active-low: 1 = verde, 0 = vermelho)
CHIP_AO = "/dev/gpiochip1"
NET, POWER = 4, 11
GREEN, RED = Value.ACTIVE, Value.INACTIVE
# LED vermelho no banco periphs (GPIOH_5, active-high: 1 = aceso, 0 = apagado)
CHIP_P = "/dev/gpiochip0"
IR = 21
IR_ON, IR_OFF = Value.ACTIVE, Value.INACTIVE

req_ao = gpiod.request_lines(
    CHIP_AO, consumer="secbox-leds",
    config={
        NET: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=RED),
        POWER: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=RED),
    },
)
req_ir = gpiod.request_lines(
    CHIP_P, consumer="secbox-leds",
    config={IR: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=IR_OFF)},
)

state = {"connected": False}

def on_connect(c, u, f, rc):
    state["connected"] = (rc == 0)

def on_disconnect(c, u, rc):
    state["connected"] = False

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"leds-{DEVICE_ID}")
except (AttributeError, TypeError):
    client = mqtt.Client(client_id=f"leds-{DEVICE_ID}")
client.username_pw_set(cfg["broker_user"], cfg["broker_pass"])
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.connect_async(cfg["broker_host"], int(cfg["broker_port"]), keepalive=30)
client.loop_start()

# Checagens "lentas" (camera + internet) a cada 5s, fora do loop rapido dos LEDs.
slow = {"cam": False, "inet": False, "t": 0.0}

def has_internet():
    try:
        s = socket.create_connection(("1.1.1.1", 443), timeout=2)
        s.close()
        return True
    except OSError:
        return False

def camera_ok():
    try:
        c = json.load(open(CAMERAS))
        if c.get("connected", 0) < 1:
            return False
    except Exception:
        return False
    return subprocess.run(["systemctl", "is-active", "--quiet", "mediamtx"]).returncode == 0

def refresh_slow():
    now = time.time()
    if now - slow["t"] < 5:
        return
    slow["t"] = now
    slow["cam"] = camera_ok()
    slow["inet"] = has_internet()

blink = False
while True:
    blink = not blink
    refresh_slow()
    # power: camera conectada e gravando
    req_ao.set_value(POWER, GREEN if slow["cam"] else RED)
    # net: conexao com o servidor (broker)
    req_ao.set_value(NET, GREEN if state["connected"] else RED)
    # ir: piscando = lendo QR (pareamento) / aceso = internet / apagado = sem internet
    if not os.path.exists(CLAIMED):
        req_ir.set_value(IR, IR_ON if blink else IR_OFF)
    else:
        req_ir.set_value(IR, IR_ON if slow["inet"] else IR_OFF)
    time.sleep(0.3)
