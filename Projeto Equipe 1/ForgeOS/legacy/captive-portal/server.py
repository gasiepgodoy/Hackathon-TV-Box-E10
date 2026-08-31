#!/usr/bin/env python3
"""
ForgeOS Captive Portal & Provisioning Backend
Adapted WiFiProvisioner & Dev Telemetry Server for BTV E10 (Amlogic S905X2).
Includes socket reuse, fallback ports, and dynamic SVG QR Code endpoint.
"""
import http.server
import socketserver
import json
import os
import sys
import subprocess
from pathlib import Path

PORT = 80
STATIC_DIR = Path(__file__).parent.resolve()

API_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1"
}

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

class CaptivePortalHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self):
        path = self.path

        if path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            status_data = {
                "soc": "Amlogic S905X2 (G12A)",
                "kernel": "Linux 6.18.29-meson64",
                "ram_free_mb": 1588,
                "ram_total_mb": 2048,
                "emmc_free_gb": 6.2,
                "emmc_total_gb": 8.0,
                "drm_status": "connected",
                "wifi_chip": "Realtek RTL8189FTV",
                "temp_c": 47.5
            }
            self.wfile.write(json.dumps(status_data).encode('utf-8'))
            return

        if path == '/api/qrcode':
            try:
                res = subprocess.run(['qrencode', '-t', 'SVG', 'http://192.168.4.1'], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/svg+xml')
                    self.end_headers()
                    self.wfile.write(res.stdout.encode('utf-8'))
                    return
            except Exception as e:
                print(f"[FORGEOS ERROR] SVG QR generation error: {e}")
            
            self.send_error(500, "Failed to generate QR Code")
            return

        if path == '/api/wifi/scan':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            networks = []
            if os.name == 'posix':
                try:
                    res = subprocess.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi'], capture_output=True, text=True, timeout=5)
                    lines = res.stdout.strip().splitlines()
                    seen = set()
                    for line in lines:
                        parts = line.split(':')
                        if len(parts) >= 2 and parts[0] and parts[0] not in seen:
                            seen.add(parts[0])
                            sig = int(parts[1]) if parts[1].isdigit() else 70
                            rssi = -100 + (sig // 2)
                            sec = parts[2] if len(parts) > 2 and parts[2] else 'WPA2'
                            networks.append({
                                "ssid": parts[0],
                                "rssi": rssi,
                                "signal_desc": "Excelente" if rssi >= -60 else ("Bom" if rssi >= -75 else "Regular"),
                                "security": sec
                            })
                except Exception:
                    pass

            if not networks:
                networks = [
                    {"ssid": "UNESP-Academica", "rssi": -52, "signal_desc": "Excelente", "security": "WPA2/WPA3"},
                    {"ssid": "Lab-GASI-5G", "rssi": -68, "signal_desc": "Bom", "security": "WPA2-PSK"},
                    {"ssid": "Rede-Hospitalar-SUS", "rssi": -78, "signal_desc": "Regular", "security": "WPA2 Enterprise"},
                    {"ssid": "NATEL-IoT-Net", "rssi": -82, "signal_desc": "Fraco", "security": "WPA2-PSK"}
                ]

            self.wfile.write(json.dumps({"networks": networks}).encode('utf-8'))
            return

        if not path.startswith('/api') and not (STATIC_DIR / path.lstrip('/')).exists():
            self.send_response(302)
            self.send_header('Location', f'http://192.168.4.1:{PORT}/')
            self.end_headers()
            return

        super().do_GET()

    def do_POST(self):
        if self.path == '/api/provision':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                config = json.loads(post_data.decode('utf-8'))
                print(f"[FORGEOS PROVISION] Config received: {config}")

                provider = config.get('apiProvider', 'groq')
                base_url = API_BASE_URLS.get(provider, API_BASE_URLS['groq'])

                forge_boot = Path('/boot/forge')
                if os.name == 'posix':
                    forge_boot.mkdir(parents=True, exist_ok=True)
                    
                    with open(forge_boot / 'network.yaml', 'w', encoding='utf-8') as f:
                        f.write(f"ssid: '{config.get('wifiSSID', '')}'\n")
                        f.write(f"passphrase: '{config.get('wifiPass', '')}'\n")
                        f.write(f"dhcp: {str(config.get('dhcp', True)).lower()}\n")

                    with open(forge_boot / 'mina.yaml', 'w', encoding='utf-8') as f:
                        f.write(f"api_provider: '{provider}'\n")
                        f.write(f"api_base_url: '{base_url}'\n")
                        f.write(f"api_key: '{config.get('apiKey', '')}'\n")
                        f.write(f"window_mode: '{config.get('windowMode', '-g right')}'\n")

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Provisioned successfully"}).encode('utf-8'))

            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            return

        self.send_error(404, "Endpoint Not Found")

def main():
    requested_port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    fallback_ports = [requested_port, 80, 8080, 8081, 8888]
    
    for port in fallback_ports:
        try:
            with ReusableTCPServer(("", port), CaptivePortalHandler) as httpd:
                print(f"[FORGEOS] Captive Portal Server running at http://0.0.0.0:{port}/")
                httpd.serve_forever()
                break
        except OSError as e:
            print(f"[FORGEOS WARNING] Port {port} unavailable ({e}). Trying fallback port...")
    else:
        print("[FORGEOS ERROR] All fallback ports unavailable.")

if __name__ == '__main__':
    main()
