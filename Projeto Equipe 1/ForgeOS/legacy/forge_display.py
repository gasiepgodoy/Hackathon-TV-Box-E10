#!/usr/bin/env python3
"""
ForgeOS 1:1 Pixel-Grid Native Kiosk Display Generator v1.6
Updated Wi-Fi Hotspot SSID to 'ForgeOS'.
Mapped 1-to-1 with BTV E10 Framebuffer (1024x768 32bpp) for zero blur, zero ghosting.
"""
import os
import sys
import subprocess
from pathlib import Path

def get_fb_resolution():
    try:
        with open('/sys/class/graphics/fb0/virtual_size', 'r') as f:
            w, h = map(int, f.read().strip().split(','))
            if w > 0 and h > 0:
                return w, h
    except Exception:
        pass
    return 1024, 768

def get_ttf_font(size, bold=False):
    font_paths = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    ]
    from PIL import ImageFont
    for path in font_paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def generate_display_image():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("[FORGE-DISPLAY WARNING] Pillow PIL not installed.")
        return False

    W, H = get_fb_resolution()
    print(f"[FORGE-DISPLAY] Native 1:1 Framebuffer Canvas: {W}x{H}")

    run_cmd = lambda cmd: subprocess.run(cmd, shell=True, capture_output=True)
    wifi_qr_data = "WIFI:S:ForgeOS;T:WPA;P:forgeos123;;"
    url_qr_data = "http://192.168.4.1"

    # Generate QR PNGs with exact module size
    run_cmd(f'qrencode -s 7 -o /tmp/qr_wifi.png "{wifi_qr_data}"')
    run_cmd(f'qrencode -s 7 -o /tmp/qr_url.png "{url_qr_data}"')

    if not Path('/tmp/qr_wifi.png').exists() or not Path('/tmp/qr_url.png').exists():
        print("[FORGE-DISPLAY ERROR] Failed to generate QR PNG files.")
        return False

    canvas = Image.new('RGB', (W, H), color='#0d1117')
    draw = ImageDraw.Draw(canvas)

    font_header = get_ttf_font(26, bold=True)
    font_sub = get_ttf_font(15, bold=False)
    font_card_title = get_ttf_font(18, bold=True)
    font_label_bold = get_ttf_font(15, bold=True)
    font_label_regular = get_ttf_font(14, bold=False)
    font_badge = get_ttf_font(14, bold=True)

    # Header
    draw.text((W // 2, 45), "ForgeOS — Kiosk de Configuração Inicial", fill="#ffffff", font=font_header, anchor="mm")
    draw.text((W // 2, 80), "Dispositivo: BTV E10 Express (Amlogic S905X2) | Distro: ForgeOS v1.2 Pro", fill="#8b949e", font=font_sub, anchor="mm")

    img_wifi = Image.open('/tmp/qr_wifi.png').convert('RGB')
    img_url = Image.open('/tmp/qr_url.png').convert('RGB')
    qr_w, qr_h = img_wifi.size

    card_w = 440
    card_h = 550
    card_y = 120

    # Card 1: Wi-Fi Auto-Connect QR
    c1_x = (W // 2) - card_w - 20
    draw.rounded_rectangle([c1_x, card_y, c1_x + card_w, card_y + card_h], radius=12, fill="#161b22", outline="#30363d", width=2)
    draw.text((c1_x + (card_w // 2), card_y + 35), "1. Conectar à Rede Wi-Fi", fill="#58a6ff", font=font_card_title, anchor="mm")

    qr1_x = c1_x + ((card_w - qr_w) // 2)
    qr1_y = card_y + 70
    canvas.paste(img_wifi, (qr1_x, qr1_y))

    t1_y = qr1_y + qr_h + 35
    draw.text((c1_x + (card_w // 2), t1_y), "Rede: ForgeOS", fill="#ffffff", font=font_label_bold, anchor="mm")
    draw.text((c1_x + (card_w // 2), t1_y + 30), "Senha: forgeos123", fill="#8b949e", font=font_label_regular, anchor="mm")
    draw.text((c1_x + (card_w // 2), t1_y + 75), "Escaneie para Conectar Automaticamente", fill="#3fb950", font=font_badge, anchor="mm")

    # Card 2: Captive Portal URL QR
    c2_x = (W // 2) + 20
    draw.rounded_rectangle([c2_x, card_y, c2_x + card_w, card_y + card_h], radius=12, fill="#161b22", outline="#30363d", width=2)
    draw.text((c2_x + (card_w // 2), card_y + 35), "2. Abrir Portal de Setup", fill="#58a6ff", font=font_card_title, anchor="mm")

    qr2_x = c2_x + ((card_w - qr_w) // 2)
    qr2_y = card_y + 70
    canvas.paste(img_url, (qr2_x, qr2_y))

    t2_y = qr2_y + qr_h + 35
    draw.text((c2_x + (card_w // 2), t2_y), "URL: http://192.168.4.1", fill="#ffffff", font=font_label_bold, anchor="mm")
    draw.text((c2_x + (card_w // 2), t2_y + 30), "Portal de Configuração Web", fill="#8b949e", font=font_label_regular, anchor="mm")
    draw.text((c2_x + (card_w // 2), t2_y + 75), "Escaneie para Abrir no Navegador", fill="#3fb950", font=font_badge, anchor="mm")

    # Footer
    draw.text((W // 2, H - 35), "Aguardando configuração inicial via smartphone ou PC...", fill="#6e7681", font=font_sub, anchor="mm")

    output_path = '/tmp/forge_setup_display.png'
    canvas.save(output_path, quality=100)
    print(f"[FORGE-DISPLAY SUCCESS] Rendered 1:1 native image ({W}x{H}) for SSID ForgeOS -> {output_path}")
    return True

def render_to_framebuffer():
    if generate_display_image():
        print("[FORGE-DISPLAY] Outputting 1:1 crisp native image to framebuffer...")
        subprocess.run('fbi -d /dev/fb0 -T 1 --noverbose /tmp/forge_setup_display.png 2>/dev/null', shell=True)

if __name__ == '__main__':
    render_to_framebuffer()
