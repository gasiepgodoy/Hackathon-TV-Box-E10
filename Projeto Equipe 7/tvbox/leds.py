#!/usr/bin/env python3
# LEDs de status (bicolor, GPIO via libgpiod). Deriva o estado sozinho:
#   power: verde = conectado ao broker / vermelho = sem conexão
#   net:   verde = ocioso / vermelho = movimento (8s) / piscando = pareamento
# Ajuste CHIP/NET/POWER conforme o mapeamento de GPIO da sua TV box.
import json, time, os
import gpiod
from gpiod.line import Direction, Value
import paho.mqtt.client as mqtt

BASE = "/opt/secbox"
dev = json.load(open(f"{BASE}/device.json"))
cfg = json.load(open(f"{BASE}/config.json"))
DEVICE_ID = dev["device_id"]
CLAIMED = f"{BASE}/claimed"

CHIP = "/dev/gpiochip1"
NET, POWER = 4, 11
GREEN, RED = Value.ACTIVE, Value.INACTIVE   # 1 = verde, 0 = vermelho

req = gpiod.request_lines(
    CHIP, consumer="secbox-leds",
    config={
        NET: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=GREEN),
        POWER: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=RED),
    },
)

state = {"connected": False, "motion_until": 0.0}

def on_connect(c, u, f, rc):
    state["connected"] = (rc == 0)
    c.subscribe(f"devices/{DEVICE_ID}/alarme/event", qos=1)

def on_disconnect(c, u, rc):
    state["connected"] = False

def on_message(c, u, msg):
    state["motion_until"] = time.time() + 8

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"leds-{DEVICE_ID}")
except (AttributeError, TypeError):
    client = mqtt.Client(client_id=f"leds-{DEVICE_ID}")
client.username_pw_set(cfg["broker_user"], cfg["broker_pass"])
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.connect_async(cfg["broker_host"], int(cfg["broker_port"]), keepalive=30)
client.loop_start()

blink = False
while True:
    blink = not blink
    now = time.time()
    req.set_value(POWER, GREEN if state["connected"] else RED)
    if not os.path.exists(CLAIMED):
        req.set_value(NET, GREEN if blink else RED)   # pareamento
    elif now < state["motion_until"]:
        req.set_value(NET, RED)                        # movimento
    else:
        req.set_value(NET, GREEN)                      # ocioso
    time.sleep(0.3)
