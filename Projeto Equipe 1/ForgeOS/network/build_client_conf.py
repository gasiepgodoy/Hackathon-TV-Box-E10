#!/usr/bin/env python3
"""Gera wpa_supplicant client conf a partir do provision.json do portal.

Suporta WPA-PSK e WPA-EAP (PEAP/TTLS — eduroam/802.1X).
Uso: build_client_conf.py <provision.json> <saida.conf>
"""
import json
import sys


def esc(s):
    """Escape para string entre aspas no formato wpa_supplicant."""
    return s.replace('\\', '\\\\').replace('"', '\\"')


def psk_value(p):
    if all(c in "0123456789abcdefABCDEF" for c in p) and len(p) == 64:
        return p
    return f'"{esc(p)}"'


def main():
    prov_path, out_path = sys.argv[1], sys.argv[2]
    with open(prov_path) as f:
        d = json.load(f)

    lines = [
        'ctrl_interface=/var/run/wpa_supplicant-client',
        'ap_scan=1',
        '',
        'network={',
        f'    ssid="{esc(d["ssid"])}"',
    ]

    if d.get("mode") == "psk":
        lines.append(f'    psk={psk_value(d["password"])}')
        lines.append('    key_mgmt=WPA-PSK')
    elif d.get("mode") == "eap":
        method = d.get("method", "PEAP")
        phase2 = d.get("phase2", "MSCHAPV2")
        lines += [
            '    key_mgmt=WPA-EAP',
            '    eap=' + method,
            f'    identity="{esc(d["identity"])}"',
            f'    password="{esc(d["password"])}"',
        ]
        if method == "PEAP":
            lines.append('    phase1="peapver=0 peaplabel=0"')
        phase2_map = {"MSCHAPV2": "auth=MSCHAPV2", "PAP": "auth=PAP"}
        lines.append(f'    phase2="{phase2_map[phase2]}"')
        if d.get("anonymous_identity"):
            lines.append(f'    anonymous_identity="{esc(d["anonymous_identity"])}"')
        if d.get("domain"):
            dom = esc(d["domain"].lstrip("."))
            lines.append(f'    altsubject_match="DNS:{dom};DNS:.{dom}"')

    lines += ['    scan_ssid=1', '']
    lines.append('}')

    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[BUILD-CONF] {out_path} ({d.get('mode')} -> {d.get('ssid')})")


if __name__ == "__main__":
    main()
