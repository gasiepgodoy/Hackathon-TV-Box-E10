"""Render synthetic setup states; never read real credentials or write fb0."""
import argparse
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'display'))
from panel_renderer import render_panel, wifi_payload, qr_tile

parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
sample = {'ssid': 'ForgeOS • Configuração', 'password': 'BemVindo2026',
          'target_ssid': 'Laboratório MultiForge', 'ip': '192.168.1.120'}
for mode in ['ap_solo', 'peer', 'applying', 'connected', 'failed']:
    image = render_panel(mode, sample, logo_path=BASE / 'web/logo.png')
    assert image.size == (1920, 1080)
    image.save(args.output / f'startup-{mode}.png')
    print(f'PASS render {mode}')

special = {'ssid': 'Lab; A:B, "C"\\D', 'password': 'a;b:c,d"e\\f'}
assert wifi_payload(**special) == 'WIFI:T:WPA;S:Lab\\; A\\:B\\, \\"C\\"\\\\D;P:a\\;b\\:c\\,d\\"e\\\\f;;'
assert wifi_payload('Aberta', '') == 'WIFI:T:nopass;S:Aberta;P:;;'
qr_tile(wifi_payload(**special)).save(args.output / 'qr-special.png')
qr_tile(wifi_payload('Aberta', '')).save(args.output / 'qr-open.png')
long = dict(sample, ssid='R' * 32, password='S' * 63)
render_panel('ap_solo', long, logo_path=BASE / 'web/logo.png').save(args.output / 'startup-long-values.png')
print('PASS escaped/open network payloads and long credentials')
