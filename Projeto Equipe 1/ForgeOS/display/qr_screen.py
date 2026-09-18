#!/usr/bin/env python3
"""ForgeOS Kiosk Display — Minimalist shared panels (1920x1080 fb0).

Audited according to 10-foot UI guidelines, pairing state machine, and ISO/IEC 18004.
Supports dynamic state transitions: Pairing (AP) -> Applying -> Connected -> Failed -> Status.
"""
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FB = "/dev/fb0"
LINE_LEN = 7680
BPP = 4
BASE = os.environ.get("FORGEOS_BASE", "/opt/forgeos" if os.path.exists("/opt/forgeos") else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(BASE, "state")
FONTS = os.path.join(BASE, "display", "fonts")
WEB = os.path.join(BASE, "web")

# ---- PALETA DE CORES PRO (Design System 10-Foot UI) ----
BG = (10, 14, 23)             # #0A0E17 - Fundo profundo
GRID = (22, 30, 48)           # Pontos sutis do grid
CARD_BG = (17, 24, 39)        # #111827 - Superfície do Card elegante
CARD_BORDER = (38, 48, 71)    # #263047 - Borda nítida
CHIP_BG = (11, 16, 28)        # #0B101C - Fundo do chip de dados
CHIP_BORDER = (30, 41, 59)    # #1E293B

ACCENT_BLUE = (43, 154, 243)  # #2B9AF3 - Azul Principal
ACCENT_GREEN = (34, 197, 94)  # #22C55E - Verde Sucesso
ACCENT_ORANGE = (249, 115, 22)# #F97316 - Laranja Destaque
ACCENT_YELLOW = (234, 179, 8) # #EAB308 - Amarelo Atenção
ACCENT_RED = (239, 68, 68)    # #EF4444 - Vermelho Erro

TXT_TITLE = (255, 255, 255)   # #FFFFFF
TXT_BODY = (241, 245, 249)    # #F1F5F9
TXT_MUTED = (156, 171, 196)   # #9CABC4
TXT_HINT = (107, 122, 148)    # #6B7A94
FOOT_BG = (8, 11, 18)         # #080B12 - Barra de rodapé

AP_SSID = "RTL8189FTV_AP"
AP_PASS = "tvbox12345"
PORTAL_AP_URL = "http://192.168.4.1:8080"


def F(name, size):
    """Carrega fonte TrueType com fallback de segurança."""
    p = os.path.join(FONTS, name)
    if Path(p).exists():
        return ImageFont.truetype(p, size)
    for fallback in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if "Bold" in name else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
    ):
        if Path(fallback).exists():
            return ImageFont.truetype(fallback, size)
    return ImageFont.load_default()


def get_mac():
    try:
        return open("/sys/class/net/wlan0/address").read().strip().upper()
    except Exception:
        return "3C:7A:AA:39:F6:C2"


def get_eth_ip():
    try:
        out = subprocess.run(["ip", "-4", "addr", "show", "eth0"], capture_output=True, text=True, timeout=2)
        m = re.search(r'inet\s+([\d.]+)', out.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def get_wlan_ip():
    try:
        out = subprocess.run(["ip", "-4", "addr", "show", "wlan0"], capture_output=True, text=True, timeout=2)
        m = re.search(r'inet\s+([\d.]+)', out.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def get_device_state():
    """Detecta estado real da máquina de estados do appliance."""
    # 1. Checa se está aplicando provisionamento
    if os.path.exists(os.path.join(STATE, "applying")):
        prov_file = os.path.join(STATE, "provision.json")
        target_ssid = "Wi-Fi"
        if os.path.exists(prov_file):
            try:
                target_ssid = json.load(open(prov_file)).get("ssid", "Wi-Fi")
            except Exception:
                pass
        return "applying", target_ssid, None

    # 2. Checa se client wpa_supplicant está ativo com IP válido
    wlan_ip = get_wlan_ip()
    eth_ip = get_eth_ip()

    try:
        out = subprocess.run(["pgrep", "-f", "wpa_supplicant.*client.conf"], capture_output=True, text=True)
        if out.returncode == 0 and wlan_ip and wlan_ip != "192.168.4.1":
            prov_file = os.path.join(STATE, "provision.json")
            ssid = "Rede Wi-Fi"
            if os.path.exists(prov_file):
                try:
                    ssid = json.load(open(prov_file)).get("ssid", "Rede Wi-Fi")
                except Exception:
                    pass
            return "connected", ssid, wlan_ip
    except Exception:
        pass

    # 3. Checa se houve falha recente registrada
    res_file = os.path.join(STATE, "result.json")
    if os.path.exists(res_file):
        try:
            r = json.load(open(res_file))
            if r.get("status") == "failed":
                return "failed", r.get("ssid", "Wi-Fi"), None
        except Exception:
            pass

    # Advance from the Wi-Fi QR to the portal QR when a phone joins the AP.
    try:
        stations = subprocess.run(["iw", "dev", "wlan0", "station", "dump"],
                                  capture_output=True, text=True, timeout=2)
        if stations.returncode == 0 and any(line.startswith("Station ") for line in stations.stdout.splitlines()):
            return "peer", AP_SSID, "192.168.4.1"
    except (OSError, subprocess.TimeoutExpired):
        pass

    # 4. Modo padrão: Ponto de Acesso Ativo (Pairing / Setup)
    return "ap", AP_SSID, (eth_ip or "192.168.4.1")


def get_hardware_telemetry():
    """Coleta métricas reais do hardware S905X2 para o modo operacional."""
    temp_c = 40.0
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp_c = round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        pass

    ram_str = "485 MB / 1.98 GB"
    try:
        with open("/proc/meminfo") as f:
            mem_tot, mem_av = 1980, 1500
            for line in f:
                if line.startswith("MemTotal:"): mem_tot = int(line.split()[1]) // 1024
                elif line.startswith("MemAvailable:"): mem_av = int(line.split()[1]) // 1024
            ram_str = f"{mem_tot - mem_av} MB / {round(mem_tot/1024, 2)} GB"
    except Exception:
        pass

    up_str = "1h 24m"
    try:
        with open("/proc/uptime") as f:
            sec = int(float(f.read().split()[0]))
            h = sec // 3600
            m = (sec % 3600) // 60
            up_str = f"{h}h {m}m"
    except Exception:
        pass

    return temp_c, ram_str, up_str


def render(shift_x=0, shift_y=0):
    """Use the shared panel while preserving the original state and push loop."""
    from panel_renderer import render_panel
    state_mode, state_ssid, state_ip = get_device_state()
    info = {"ssid": AP_SSID, "password": AP_PASS,
            "target_ssid": state_ssid, "ip": state_ip}
    temp, ram, uptime = get_hardware_telemetry()
    info.update(temp=temp, ram=ram, up=uptime)
    # Read the configured AP credentials rather than baking values into the QR.
    conf = Path(BASE) / "network" / "wpa_ap.conf"
    if conf.exists():
        for line in conf.read_text().splitlines():
            key, separator, value = line.strip().partition("=")
            if separator and key in ("ssid", "psk"):
                info["ssid" if key == "ssid" else "password"] = value.strip().strip('"')
    logo_path = os.path.join(WEB, "logo.png")
    image = render_panel(state_mode, info, shift_x, shift_y, logo_path)
    out = os.path.join(tempfile.gettempdir(), "forge_display_render.png")
    image.save(out)
    return out, 978 + shift_y


def push(png):
    data = Image.open(png).convert("RGBA").tobytes("raw", "BGRA")
    with open(FB, "wb") as f:
        f.write(data)
        f.write(b"\x00" * (1080 * LINE_LEN))


def main():
    try:
        open("/sys/class/vtconsole/vtcon1/bind", "w").write("0")
    except Exception:
        pass
    subprocess.run("setterm -cursor off > /dev/tty1 2>&1 || true", shell=True)

    last_state = ""
    tick = 0

    while True:
        shift_x = (tick // 60) % 3 - 1
        shift_y = (tick // 120) % 3 - 1

        cur_state = str(get_device_state())
        if cur_state != last_state or (tick % 30 == 0):
            last_state = cur_state
            png, fy = render(shift_x, shift_y)
            push(png)

        time.sleep(1.0)
        tick += 1


if __name__ == "__main__":
    main()
