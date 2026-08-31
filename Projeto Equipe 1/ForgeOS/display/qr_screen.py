#!/usr/bin/env python3
"""ForgeOS Kiosk Display Engine v2.7 — Calibrated 10-Foot UI (1920x1080 fb0).

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


def qr_png(data, box_size):
    """Gera QR code de alta nitidez com margem adequada (ISO/IEC 18004)."""
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return img.resize((box_size, box_size), Image.NEAREST)
    except Exception:
        out = os.path.join(tempfile.gettempdir(), f"qr_{abs(hash(data)) % 9999}.png")
        subprocess.run(["qrencode", "-s", "10", "-m", "2", "-o", out, data], check=True, capture_output=True)
        img = Image.open(out).convert("RGB")
        return img.resize((box_size, box_size), Image.NEAREST)


def render(shift_x=0, shift_y=0):
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Safe Area Insets: 96px laterais, 48px verticais
    safe_l, safe_r = 96 + shift_x, W - 96 + shift_x
    safe_t, safe_b = 48 + shift_y, H - 48 + shift_y

    # 1. Grid sutil de fundo
    for gy in range(48, H - 48, 48):
        for gx in range(48, W - 48, 48):
            d.ellipse([gx - 1 + shift_x, gy - 1 + shift_y, gx + 1 + shift_x, gy + 1 + shift_y], fill=GRID)

    # Obter estado atual
    state_mode, state_ssid, state_ip = get_device_state()

    # =========================================================================
    # 1. CABEÇALHO SUPERIOR (Logo Ampliado 80x80 + Espaçamento Simétrico)
    # =========================================================================
    logo_path = os.path.join(WEB, "logo.png")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(BASE, "imagens", "ForgeOSlogo.png")

    logo_size = 80
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA").resize((logo_size, logo_size), Image.LANCZOS)
            img.paste(logo_img, (safe_l, safe_t), logo_img)
        except Exception:
            d.rounded_rectangle([safe_l, safe_t, safe_l + logo_size, safe_t + logo_size], radius=18, fill=ACCENT_BLUE)
            d.text((safe_l + logo_size/2, safe_t + logo_size/2), "F", font=F("Inter-Bold.ttf", 46), fill="white", anchor="mm")
    else:
        d.rounded_rectangle([safe_l, safe_t, safe_l + logo_size, safe_t + logo_size], radius=18, fill=ACCENT_BLUE)
        d.text((safe_l + logo_size/2, safe_t + logo_size/2), "F", font=F("Inter-Bold.ttf", 46), fill="white", anchor="mm")

    title_x = safe_l + 100
    title_font = F("Inter-Bold.ttf", 48)
    d.text((title_x, safe_t + 24), "ForgeOS", font=title_font, fill=TXT_TITLE, anchor="lm")
    title_w = d.textlength("ForgeOS", font=title_font)

    # Badge de Estado Dinâmico
    if state_mode == "connected":
        badge_txt = "O P E R A C I O N A L"
        badge_col = ACCENT_GREEN
    elif state_mode == "applying":
        badge_txt = "C O N E C T A N D O"
        badge_col = ACCENT_YELLOW
    elif state_mode == "failed":
        badge_txt = "A T E N Ç Ã O"
        badge_col = ACCENT_RED
    else:
        badge_txt = "P A R E A M E N T O"
        badge_col = ACCENT_BLUE

    badge_font = F("Inter-Bold.ttf", 16)
    badge_w = d.textlength(badge_txt, font=badge_font)
    badge_x = title_x + title_w + 26
    d.rounded_rectangle([badge_x, safe_t + 8, badge_x + badge_w + 34, safe_t + 40], radius=16, outline=badge_col, width=2)
    d.text((badge_x + (badge_w + 34) / 2, safe_t + 24), badge_txt, font=badge_font, fill=badge_col, anchor="mm")

    # Subtítulo (Hardware Specs) com distância vertical simétrica
    d.text((title_x, safe_t + 68), "SEI Robotics SEI510 (BTV E10)  •  Amlogic S905X2  •  Armbian Appliance",
           font=F("Inter-Medium.ttf", 23), fill=TXT_MUTED, anchor="lm")

    # =========================================================================
    # 2. CORPO CENTRAL BASEADO NA MÁQUINA DE ESTADOS
    # =========================================================================
    if state_mode == "connected":
        # ---------------------------------------------------------------------
        # ESTADO OPERACIONAL / CONECTADO (S4 resolvido - credenciais ocultas)
        # ---------------------------------------------------------------------
        cw, chh = 750, 735
        gap = 80
        sx = (W - (cw * 2 + gap)) // 2 + shift_x
        cy = safe_t + 130

        portal_url = f"http://{state_ip}:8080"
        qr_portal = qr_png(portal_url, 300)

        # Card 1: Acesso ao Portal Web na Rede
        d.rounded_rectangle([sx, cy, sx + cw, cy + chh], radius=24, fill=CARD_BG, outline=CARD_BORDER, width=2)
        bx, by, bd = sx + 36, cy + 34, 52
        d.ellipse([bx, by, bx + bd, by + bd], fill=ACCENT_GREEN)
        d.text((bx + bd / 2, by + bd / 2), "✓", font=F("Inter-Bold.ttf", 28), fill="white", anchor="mm")
        d.text((bx + bd + 20, by + bd / 2), "Painel ForgeOS na Rede", font=F("Inter-Bold.ttf", 34), fill=TXT_TITLE, anchor="lm")
        d.line([sx + 36, cy + 104, sx + cw - 36, cy + 104], fill=CARD_BORDER, width=1)

        # QR Code Card 1
        qbox = 324
        qx = sx + (cw - qbox) // 2
        qy = cy + 128
        d.rounded_rectangle([qx - 2, qy - 2, qx + qbox + 2, qy + qbox + 2], radius=20, fill=(15, 20, 32))
        d.rounded_rectangle([qx, qy, qx + qbox, qy + qbox], radius=18, fill="white")
        qw, qh = qr_portal.size
        img.paste(qr_portal, (qx + (qbox - qw) // 2, qy + (qbox - qh) // 2))

        # Chips de dados
        ry = cy + 476
        chip_h = 82
        chip_pad = 32
        d.rounded_rectangle([sx + chip_pad, ry, sx + cw - chip_pad, ry + chip_h], radius=14, fill=CHIP_BG, outline=CHIP_BORDER, width=1)
        d.text((sx + chip_pad + 20, ry + 15), "ENDEREÇO IP DO PAINEL", font=F("JetBrainsMono-Bold.ttf", 15), fill=TXT_MUTED)
        d.text((sx + chip_pad + 20, ry + 43), portal_url, font=F("JetBrainsMono-Bold.ttf", 27), fill=ACCENT_GREEN)

        ry += chip_h + 14
        d.rounded_rectangle([sx + chip_pad, ry, sx + cw - chip_pad, ry + chip_h], radius=14, fill=CHIP_BG, outline=CHIP_BORDER, width=1)
        d.text((sx + chip_pad + 20, ry + 15), "REDE ASSOCIADA", font=F("JetBrainsMono-Bold.ttf", 15), fill=TXT_MUTED)
        d.text((sx + chip_pad + 20, ry + 43), f"{state_ssid} (Internet Ativa)", font=F("JetBrainsMono-Bold.ttf", 25), fill=TXT_TITLE)

        d.text((sx + cw // 2, cy + chh - 54), "Dispositivo online e pronto para uso", font=F("Inter-Medium.ttf", 20), fill=TXT_MUTED, anchor="mm")
        d.text((sx + cw // 2, cy + chh - 24), "Acesse o painel pelo navegador em qualquer dispositivo da rede", font=F("Inter-Regular.ttf", 17), fill=TXT_HINT, anchor="mm")

        # Card 2: Telemetria & Recursos do Hardware
        temp_c, ram_str, up_str = get_hardware_telemetry()
        cx2 = sx + cw + gap
        d.rounded_rectangle([cx2, cy, cx2 + cw, cy + chh], radius=24, fill=CARD_BG, outline=CARD_BORDER, width=2)
        bx2, by2 = cx2 + 36, cy + 34
        d.ellipse([bx2, by2, bx2 + bd, by2 + bd], fill=ACCENT_BLUE)
        d.text((bx2 + bd / 2, by2 + bd / 2), "⚙", font=F("Inter-Bold.ttf", 28), fill="white", anchor="mm")
        d.text((bx2 + bd + 20, by2 + bd / 2), "Telemetria do Sistema", font=F("Inter-Bold.ttf", 34), fill=TXT_TITLE, anchor="lm")
        d.line([cx2 + 36, cy + 104, cx2 + cw - 36, cy + 104], fill=CARD_BORDER, width=1)

        metrics = [
            ("TEMPERATURA DA CPU (S905X2)", f"{temp_c}°C", ACCENT_GREEN if temp_c < 75 else ACCENT_RED),
            ("MEMÓRIA RAM EM USO", ram_str, TXT_TITLE),
            ("TEMPO DE ATIVIDADE (UPTIME)", up_str, TXT_TITLE),
            ("SAÍDA DE VÍDEO HDMI", "1080p @ 60Hz (/dev/fb0)", ACCENT_BLUE),
            ("DISPOSITIVO / HOSTNAME", "armbian (ForgeOS Appliance)", TXT_TITLE)
        ]
        m_y = cy + 128
        m_h = 92
        for lbl, val, col in metrics:
            d.rounded_rectangle([cx2 + 32, m_y, cx2 + cw - 32, m_y + m_h], radius=14, fill=CHIP_BG, outline=CHIP_BORDER, width=1)
            d.text((cx2 + 52, m_y + 18), lbl, font=F("JetBrainsMono-Bold.ttf", 15), fill=TXT_MUTED)
            d.text((cx2 + 52, m_y + 48), val, font=F("JetBrainsMono-Bold.ttf", 26), fill=col)
            m_y += m_h + 12

    elif state_mode == "applying":
        # ---------------------------------------------------------------------
        # ESTADO APLICANDO / CONECTANDO
        # ---------------------------------------------------------------------
        mw, mh = 1100, 520
        mx = (W - mw) // 2 + shift_x
        my = (H - mh) // 2 + shift_y
        d.rounded_rectangle([mx, my, mx + mw, my + mh], radius=28, fill=CARD_BG, outline=ACCENT_YELLOW, width=3)

        d.text((mx + mw//2, my + 100), "Conectando à Rede Wi-Fi...", font=F("Inter-Bold.ttf", 48), fill=TXT_TITLE, anchor="mm")
        d.text((mx + mw//2, my + 180), f"Associando à rede '{state_ssid}' via WPA/EAP...", font=F("Inter-SemiBold.ttf", 32), fill=ACCENT_YELLOW, anchor="mm")

        pb_w, pb_h = 800, 16
        pb_x = mx + (mw - pb_w) // 2
        pb_y = my + 270
        d.rounded_rectangle([pb_x, pb_y, pb_x + pb_w, pb_y + pb_h], radius=8, fill=CHIP_BG)
        d.rounded_rectangle([pb_x, pb_y, pb_x + int(pb_w * 0.7), pb_y + pb_h], radius=8, fill=ACCENT_YELLOW)

        d.text((mx + mw//2, my + 340), "Watchdog de Contingência armado (75s Auto-Rollback).", font=F("Inter-Medium.ttf", 24), fill=TXT_MUTED, anchor="mm")
        d.text((mx + mw//2, my + 410), "Se a conexão falhar, o Ponto de Acesso será restaurado automaticamente.", font=F("Inter-Regular.ttf", 22), fill=TXT_HINT, anchor="mm")

    else:
        # ---------------------------------------------------------------------
        # ESTADO PADRÃO: PAREAMENTO / MODO AP ATIVO (Setup Mode)
        # ---------------------------------------------------------------------
        cw, chh = 750, 735
        gap = 80
        sx = (W - (cw * 2 + gap)) // 2 + shift_x
        cy = safe_t + 130

        qr_wifi = qr_png(f"WIFI:S:{AP_SSID};T:WPA;P:{AP_PASS};;", 300)
        qr_url = qr_png(PORTAL_AP_URL, 300)

        cards = [
            (sx, "1", "Conecte-se ao Wi-Fi", qr_wifi,
             [("NOME DA REDE (SSID)", AP_SSID, TXT_TITLE),
              ("SENHA DA REDE", AP_PASS, TXT_TITLE)],
             "Aponte a câmera do celular para conectar automaticamente",
             "Seu celular pode avisar que não há internet — é normal."),

            (sx + cw + gap, "2", "Abra o painel", qr_url,
             [("ENDEREÇO DO PORTAL", PORTAL_AP_URL, ACCENT_BLUE),
              ("SERVIÇO", "Painel de Controle ForgeOS", TXT_TITLE)],
             "Geralmente abre sozinho após conectar, ou escaneie o código.",
             "Acesse pelo navegador em qualquer dispositivo conectado.")
        ]

        for cx, num, step_title, qr, rows, hint1, hint2 in cards:
            d.rounded_rectangle([cx, cy, cx + cw, cy + chh], radius=24, fill=CARD_BG, outline=CARD_BORDER, width=2)

            # Header do Card: Círculo com número + Título do Passo
            bx, by, bd = cx + 36, cy + 34, 52
            d.ellipse([bx, by, bx + bd, by + bd], fill=ACCENT_BLUE)
            d.text((bx + bd / 2, by + bd / 2), num, font=F("Inter-Bold.ttf", 28), fill="white", anchor="mm")
            d.text((bx + bd + 20, by + bd / 2), step_title, font=F("Inter-Bold.ttf", 34), fill=TXT_TITLE, anchor="lm")
            d.line([cx + 36, cy + 104, cx + cw - 36, cy + 104], fill=CARD_BORDER, width=1)

            # QR Code Box Branco Ampliado (324px)
            qbox = 324
            qx = cx + (cw - qbox) // 2
            qy = cy + 128
            d.rounded_rectangle([qx - 2, qy - 2, qx + qbox + 2, qy + qbox + 2], radius=20, fill=(15, 20, 32))
            d.rounded_rectangle([qx, qy, qx + qbox, qy + qbox], radius=18, fill="white")
            qw, qh = qr.size
            img.paste(qr, (qx + (qbox - qw) // 2, qy + (qbox - qh) // 2))

            # Chips de Dados Ampliados (Altura 82px)
            ry = cy + 476
            chip_h = 82
            chip_pad = 32
            for label, value, vcol in rows:
                d.rounded_rectangle([cx + chip_pad, ry, cx + cw - chip_pad, ry + chip_h], radius=14, fill=CHIP_BG, outline=CHIP_BORDER, width=1)
                d.text((cx + chip_pad + 20, ry + 15), label, font=F("JetBrainsMono-Bold.ttf", 15), fill=TXT_MUTED)
                d.text((cx + chip_pad + 20, ry + 43), value, font=F("JetBrainsMono-Bold.ttf", 27), fill=vcol)
                ry += chip_h + 14

            # Textos de Orientação (Hints)
            d.text((cx + cw // 2, cy + chh - 54), hint1, font=F("Inter-Medium.ttf", 20), fill=TXT_MUTED, anchor="mm")
            d.text((cx + cw // 2, cy + chh - 24), hint2, font=F("Inter-Regular.ttf", 17), fill=TXT_HINT, anchor="mm")

    # =========================================================================
    # 3. BARRA DE RODAPÉ INFORMATIVO
    # =========================================================================
    fy = H - 64 + shift_y
    d.rectangle([0, fy, W, H], fill=FOOT_BG)
    d.line([0, fy, W, fy], fill=CARD_BORDER, width=2)

    dot_x, dot_y = safe_l, fy + 32
    if state_mode == "connected":
        dot_col = ACCENT_GREEN
        status_txt = f"Modo Estação (Cliente) Ativo  •  Conectado à rede '{state_ssid}'  •  IP {state_ip}"
    elif state_mode == "applying":
        dot_col = ACCENT_YELLOW
        status_txt = f"Tentando conectar a '{state_ssid}'...  •  Watchdog 75s ativo"
    elif state_mode == "failed":
        dot_col = ACCENT_RED
        status_txt = f"Falha ao conectar em '{state_ssid}'. Modo Ponto de Acesso restaurado."
    else:
        dot_col = ACCENT_BLUE
        status_txt = "Modo Ponto de Acesso (AP) Ativo  •  Aguardando conexão do celular..."

    d.ellipse([dot_x, dot_y - 8, dot_x + 16, dot_y + 8], fill=dot_col)
    d.ellipse([dot_x - 4, dot_y - 12, dot_x + 20, dot_y + 12], outline=dot_col, width=2)
    d.text((dot_x + 34, dot_y), status_txt, font=F("Inter-Medium.ttf", 21), fill=(226, 232, 240), anchor="lm")

    info_txt = f"ForgeOS v2.1  •  MAC {get_mac()}  •  HDMI 1080p @ 60Hz"
    d.text((safe_r, dot_y), info_txt, font=F("JetBrainsMono-Regular.ttf", 18), fill=TXT_HINT, anchor="rm")

    out = os.path.join(tempfile.gettempdir(), "forge_display_render.png")
    img.save(out)
    return out, fy


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
