"""Pure Pillow renderer shared by the ForgeOS and installed ForgeHub kiosks.

No network calls, credential discovery, framebuffer writes or service changes.
The caller supplies the current state and configuration.
"""
import io
import os
from functools import lru_cache
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 1920, 1080
BG = '#101414'
SURFACE = '#1a2020'
BORDER = '#303b36'
TEXT = '#f0f4f2'
MUTED = '#bcc8c3'
ACCENT = '#9ce0bd'
AMBER = '#efce8e'
RED = '#ffaaa2'
ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=24)
def font(size, bold=False):
    name = 'Inter-SemiBold.ttf' if bold else 'Inter-Regular.ttf'
    for candidate in [ROOT / 'fonts' / name,
                      Path('/usr/share/fonts/truetype/dejavu') /
                      ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')]:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


def wifi_payload(ssid, password):
    def escape(value):
        return ''.join('\\' + char if char in '\\;,:"' else char for char in str(value))
    security = 'WPA' if password else 'nopass'
    return f'WIFI:T:{security};S:{escape(ssid)};P:{escape(password)};;'


@lru_cache(maxsize=4)
def qr_tile(payload, size=368):
    """Four-module quiet zone and integer scaling; no logo over the QR matrix."""
    try:
        import qrcode
    except ImportError:
        # qrencode is already installed on the appliance. Read PNG from stdout;
        # never save credentials in named temporary files or shell commands.
        result = subprocess.run(['qrencode', '-t', 'PNG', '-s', '1', '-m', '4',
                                 '-l', 'M', '-o', '-'], input=payload.encode(),
                                capture_output=True, check=True, timeout=5)
        matrix = Image.open(io.BytesIO(result.stdout)).convert('RGBA').convert('RGB')
    else:
        qr = qrcode.QRCode(box_size=1, border=4,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(payload)
        qr.make(fit=True)
        matrix = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    factor = size // matrix.width
    if factor < 1:
        raise ValueError('QR payload exceeds the available panel size')
    matrix = matrix.resize((matrix.width * factor, matrix.height * factor), Image.Resampling.NEAREST)
    canvas = Image.new('RGB', (size, size), 'white')
    canvas.paste(matrix, ((size - matrix.width) // 2, (size - matrix.height) // 2))
    return canvas


def lines(draw, text, x, y, width, size=30, color=TEXT, bold=False):
    """Wrap even unbroken SSIDs/passwords without truncating credentials."""
    face = font(size, bold)
    line = ''
    for char in str(text):
        if char == '\n' or (line and draw.textlength(line + char, font=face) > width):
            draw.text((x, y), line, font=face, fill=color)
            y += size + 12
            line = ''
        if char != '\n':
            line += char
    if line:
        draw.text((x, y), line, font=face, fill=color)
        y += size + 12
    return y


def brand(image, draw, x, y, logo_path):
    if logo_path and Path(logo_path).is_file():
        with Image.open(logo_path) as source:
            logo = ImageOps.contain(source.convert('RGBA'), (64, 64), Image.Resampling.LANCZOS)
            image.paste(logo, (x + (64-logo.width)//2, y + (64-logo.height)//2), logo)
    else:
        draw.rounded_rectangle((x, y, x+60, y+60), radius=14, outline=ACCENT, width=2)
        draw.text((x+30, y+29), 'F', font=font(32, True), fill=ACCENT, anchor='mm')
    draw.text((x+84, y-2), 'ForgeOS', font=font(32, True), fill=TEXT)
    draw.text((x+85, y+41), 'M U L T I F O R G E', font=font(14), fill=MUTED)


def render_panel(mode, info, sx=0, sy=0, logo_path=None):
    mode = {'ap': 'ap_solo'}.get(mode, mode)
    if mode not in ('ap_solo', 'peer', 'applying', 'connected', 'failed'):
        mode = 'ap_solo'
    image = Image.new('RGB', (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    left, right = 96+sx, 1824+sx
    brand(image, draw, left, 65+sy, logo_path)
    active = 0 if mode in ('ap_solo', 'failed') else 1 if mode in ('peer', 'applying') else 2
    for index, label in enumerate(['Conectar', 'Configurar', 'Usar']):
        x = 1170 + index * 226 + sx
        draw.ellipse((x, 79+sy, x+34, 113+sy), fill=ACCENT if index == active else SURFACE)
        draw.text((x+17, 96+sy), str(index+1), font=font(17, True), fill=BG if index == active else MUTED, anchor='mm')
        draw.text((x+48, 96+sy), label, font=font(23), fill=TEXT if index == active else MUTED, anchor='lm')
    heading, sub, label, accent = {
        'ap_solo': ('Sua TV Box. Novas possibilidades.', 'Comece pelo celular. São apenas dois passos para configurar.', 'VAMOS COMEÇAR', ACCENT),
        'peer': ('Tudo certo. Vamos configurar.', 'Seu celular foi detectado. Agora abra o painel no navegador.', 'CELULAR CONECTADO', ACCENT),
        'applying': ('Estamos conectando sua TV Box.', 'Aguarde enquanto a configuração de rede é aplicada.', 'CONEXÃO EM ANDAMENTO', AMBER),
        'connected': ('Pronto para um novo propósito.', 'Acesse suas aplicações e acompanhe o dispositivo pelo painel.', 'CONECTADO À REDE', ACCENT),
        'failed': ('Vamos tentar novamente.', 'Não foi possível concluir a conexão. Reconecte-se para revisar a configuração.', 'CONEXÃO NÃO CONCLUÍDA', RED),
    }[mode]
    draw.text((left, 173+sy), label, font=font(17, True), fill=accent)
    draw.text((left, 211+sy), heading, font=font(51, True), fill=TEXT)
    draw.text((left, 283+sy), sub, font=font(26), fill=MUTED)
    draw.rounded_rectangle((left, 352+sy, right, 924+sy), radius=28, fill=SURFACE, outline=BORDER, width=1)
    x, y = left+48, 400+sy
    ssid = str(info.get('ssid', ''))
    password = str(info.get('password', ''))
    target = str(info.get('target_ssid', 'Rede Wi-Fi'))
    portal = info.get('portal_url', 'http://192.168.4.1:8080')

    if mode == 'applying':
        draw.text((x, y), 'A configuração está em andamento', font=font(37, True), fill=TEXT)
        draw.text((x, y+82), 'REDE SELECIONADA', font=font(18, True), fill=MUTED)
        lines(draw, target, x, y+119, 1430, 36)
        draw.line((x, y+231, right-48, y+231), fill=BORDER, width=1)
        draw.text((x, y+272), 'Mantenha a TV Box ligada.', font=font(32, True), fill=AMBER)
        lines(draw, 'Se a conexão não for concluída, o ponto de acesso será restaurado\npara que você possa tentar novamente.', x, y+331, 1500, 27, MUTED)
    else:
        wifi = mode in ('ap_solo', 'failed')
        title = 'Conecte seu celular ao Wi-Fi' if wifi else 'Abra o painel no celular'
        draw.text((x, y), title, font=font(36, True), fill=TEXT)
        lines(draw, 'Aponte a câmera para o QR code ao lado.' if wifi else 'Escaneie o QR code ou digite o endereço abaixo.', x, y+64, 1020, 27, MUTED)
        draw.line((x, y+126, left+1078, y+126), fill=BORDER, width=1)
        if wifi:
            draw.text((x, y+159), 'NOME DA REDE', font=font(18, True), fill=MUTED)
            next_y = lines(draw, ssid, x, y+193, 1010, 32, TEXT, True)
            next_y = max(next_y+24, y+280)
            draw.text((x, next_y), 'SENHA' if password else 'REDE ABERTA', font=font(18, True), fill=MUTED)
            lines(draw, password or 'Não é necessário digitar uma senha.', x, next_y+34, 1010, 28)
            payload = wifi_payload(ssid, password)
            hint = 'Sem internet neste passo? É normal. Continue conectado.'
        else:
            if mode == 'connected':
                portal = info.get('portal_url') or f"http://{info.get('ip', '192.168.4.1')}:8080"
            draw.text((x, y+159), 'ENDEREÇO DO PAINEL', font=font(18, True), fill=MUTED)
            lines(draw, portal, x, y+198, 1010, 36, ACCENT, True)
            draw.text((x, y+294), 'PRÓXIMO PASSO' if mode == 'peer' else 'REDE CONECTADA', font=font(18, True), fill=MUTED)
            lines(draw, 'Escolha a rede Wi-Fi que sua TV Box vai utilizar.' if mode == 'peer' else target, x, y+330, 1010, 28)
            payload = portal
            hint = 'Use um celular ou computador conectado à mesma rede.'
        # High-contrast QR island; brand and captions remain outside its quiet zone.
        qx, qy = 1352+sx, 414+sy
        draw.rounded_rectangle((qx-20, qy-20, qx+388, qy+388), radius=22, fill='white')
        image.paste(qr_tile(payload), (qx, qy))
        draw.text((qx+184, 850+sy), 'CÂMERA DO CELULAR', font=font(17, True), fill=MUTED, anchor='mm')
        draw.text((x, 868+sy), hint, font=font(24), fill=MUTED)
    draw.line((left, 978+sy, right, 978+sy), fill=BORDER, width=1)
    telemetry = []
    if info.get('temp') is not None:
        telemetry.append(f"CPU {info['temp']}°C")
    if info.get('ram'):
        telemetry.append(f"RAM {info['ram']}")
    if info.get('up'):
        telemetry.append(f"Atividade {info['up']}")
    footer = '   ·   '.join(telemetry) or 'Tecnologia reaproveitada. Novas possibilidades.'
    lines(draw, footer, left, 1007+sy, 1400, 19, MUTED)
    draw.text((right, 1007+sy), 'MULTIFORGE  /  TV BOX', font=font(18, True), fill=MUTED, anchor='ra')
    return image
