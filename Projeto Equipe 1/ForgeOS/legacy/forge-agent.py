#!/usr/bin/env python3
"""
ForgeOS Agent & First Boot Provisioning Daemon v1.8
Unmanages wlan0 from NetworkManager so wpa_supplicant mode=2 AP and dnsmasq can bind natively.
"""
import os
import sys
import time
import subprocess
import glob
from pathlib import Path

BOOT_FORGE_DIR = Path('/boot/forge')
NETWORK_YAML = BOOT_FORGE_DIR / 'network.yaml'
MINA_YAML = BOOT_FORGE_DIR / 'mina.yaml'

def get_hdmi_status():
    drm_paths = glob.glob('/sys/class/drm/*HDMI*/status')
    for path in drm_paths:
        try:
            with open(path, 'r') as f:
                status = f.read().strip()
                if status:
                    return status
        except Exception:
            pass
    return 'disconnected'

def run_cmd_safe(cmd, shell=False, timeout=10):
    cmd_str = cmd if shell else " ".join(cmd)
    print(f"[FORGE-AGENT] Executing: {cmd_str}", flush=True)
    try:
        res = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0:
            print(f"[FORGE-AGENT WARNING] Command returned code {res.returncode}: {res.stderr}", flush=True)
        return res
    except Exception as e:
        print(f"[FORGE-AGENT ERROR] Failed to execute {cmd_str}: {e}", flush=True)
        return None

def setup_wifi_hardware():
    print("[FORGE-AGENT] Unmanaging wlan0 from NetworkManager & initializing Realtek 8189fs...", flush=True)
    run_cmd_safe('nmcli dev set wlan0 managed no 2>/dev/null', shell=True)
    run_cmd_safe('rfkill unblock all 2>/dev/null', shell=True)
    run_cmd_safe('modprobe 8189fs 2>/dev/null', shell=True)
    run_cmd_safe('ip link set wlan0 up 2>/dev/null', shell=True)

def kill_stale_port_processes():
    print("[FORGE-AGENT] Cleaning up stale processes...", flush=True)
    run_cmd_safe('fuser -k 80/tcp 8080/tcp 2>/dev/null', shell=True)
    run_cmd_safe("pkill -9 -f 'captive-portal/server.py' 2>/dev/null", shell=True)
    run_cmd_safe('pkill -9 hostapd 2>/dev/null', shell=True)
    run_cmd_safe('pkill -9 wpa_supplicant 2>/dev/null', shell=True)
    run_cmd_safe('pkill -9 dnsmasq 2>/dev/null', shell=True)

def start_captive_portal():
    print('[FORGE-AGENT] Starting Hotspot AP (SSID: ForgeOS) & Captive Portal Mode...', flush=True)
    
    kill_stale_port_processes()
    setup_wifi_hardware()

    # 1. Generate wpa_supplicant mode=2 AP config for Realtek 8189fs
    wpa_ap_conf = """ctrl_interface=/var/run/wpa_supplicant
ap_scan=1

network={
    ssid="ForgeOS"
    mode=2
    key_mgmt=WPA-PSK
    psk="forgeos123"
    frequency=2437
}
"""
    try:
        with open('/tmp/wpa_ap.conf', 'w') as f:
            f.write(wpa_ap_conf)
    except Exception as e:
        print(f"[FORGE-AGENT WARNING] Failed to write wpa_ap.conf: {e}", flush=True)

    dnsmasq_conf = """interface=wlan0
except-interface=lo
bind-interfaces
dhcp-range=192.168.4.10,192.168.4.250,12h
address=/#/192.168.4.1
"""
    try:
        with open('/tmp/dnsmasq.conf', 'w') as f:
            f.write(dnsmasq_conf)
    except Exception as e:
        print(f"[FORGE-AGENT WARNING] Failed to write dnsmasq.conf: {e}", flush=True)

    # 2. Launch wpa_supplicant AP mode
    print('[FORGE-AGENT] Launching wpa_supplicant AP mode...', flush=True)
    run_cmd_safe(['wpa_supplicant', '-B', '-i', 'wlan0', '-c', '/tmp/wpa_ap.conf'])

    time.sleep(2)
    run_cmd_safe('ip addr add 192.168.4.1/24 dev wlan0 2>/dev/null', shell=True)
    run_cmd_safe('ip link set wlan0 up 2>/dev/null', shell=True)

    # 3. Launch dnsmasq DHCP/DNS server
    print('[FORGE-AGENT] Launching dnsmasq DHCP server...', flush=True)
    run_cmd_safe(['dnsmasq', '-C', '/tmp/dnsmasq.conf'])

    # 4. Apply iptables NAT redirect for HTTP 80
    run_cmd_safe(['iptables', '-t', 'nat', '-A', 'PREROUTING', '-i', 'wlan0', '-p', 'tcp', '--dport', '80', '-j', 'DNAT', '--to-destination', '192.168.4.1:80'])
    run_cmd_safe(['iptables', '-A', 'FORWARD', '-i', 'wlan0', '-p', 'tcp', '--dport', '80', '-j', 'ACCEPT'])

    # 5. Check HDMI status & render dual QR Code setup screen
    hdmi = get_hdmi_status()
    print(f'[FORGE-AGENT] HDMI Status: {hdmi}', flush=True)

    wifi_qr_payload = "WIFI:S:ForgeOS;T:WPA;P:forgeos123;;"
    url_qr_payload = "http://192.168.4.1"

    if hdmi == 'connected':
        print('[FORGE-AGENT] HDMI Connected. Rendering Fullscreen Dual QR Code Kiosk on DRM/KMS Framebuffer...', flush=True)
        run_cmd_safe('python3 /usr/bin/forge-display-qr', shell=True)
    else:
        print('[FORGE-AGENT] Headless Mode (No HDMI). Rendering Dual ANSI QR Codes on TTY1 console...', flush=True)
        run_cmd_safe('echo "\n--- 1. CONECTAR À REDE WI-FI ---" > /dev/tty1', shell=True)
        run_cmd_safe(f'qrencode -t UTF8 "{wifi_qr_payload}" > /dev/tty1 2>/dev/null', shell=True)
        run_cmd_safe('echo "\n--- 2. ABRIR PORTAL CAPTIVO ---" > /dev/tty1', shell=True)
        run_cmd_safe(f'qrencode -t UTF8 "{url_qr_payload}" > /dev/tty1 2>/dev/null', shell=True)

    # 6. Launch Captive Portal HTTP Server via Popen (Non-blocking)
    print('[FORGE-AGENT] Launching Captive Portal Web Server on port 80...', flush=True)
    server_proc = subprocess.Popen(['python3', '/opt/forgeos/captive-portal/server.py', '80'])
    print(f'[FORGE-AGENT SUCCESS] Captive Portal HTTP Server active (PID: {server_proc.pid})!', flush=True)
    server_proc.wait()

def apply_provisioning():
    print('[FORGE-AGENT] Checking provisioning files in /boot/forge/...', flush=True)
    if NETWORK_YAML.exists() and MINA_YAML.exists():
        print('[FORGE-AGENT] Provisioning files found. Applying configurations...', flush=True)
        ssid, passphrase = '', ''
        try:
            with open(NETWORK_YAML, 'r') as f:
                for line in f:
                    if 'ssid:' in line:
                        ssid = line.split(':', 1)[1].strip().strip("'")
                    elif 'passphrase:' in line:
                        passphrase = line.split(':', 1)[1].strip().strip("'")
        except Exception as e:
            print(f"[FORGE-AGENT ERROR] Failed to parse network.yaml: {e}", flush=True)

        if ssid:
            print(f'[FORGE-AGENT] Connecting to Wi-Fi SSID: {ssid}...', flush=True)
            run_cmd_safe(['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', passphrase])

        window_mode = '-g right'
        try:
            with open(MINA_YAML, 'r') as f:
                for line in f:
                    if 'window_mode:' in line:
                        window_mode = line.split(':', 1)[1].strip().strip("'")
        except Exception as e:
            print(f"[FORGE-AGENT WARNING] Failed to parse mina.yaml: {e}", flush=True)

        print(f'[FORGE-AGENT] Launching Mina Assistant with window mode: {window_mode}...', flush=True)
        mina_cmd = ['python3', '/root/Mina-a-Assistente-Virtual/main_cli.py'] + window_mode.split()
        run_cmd_safe(mina_cmd, timeout=None)
    else:
        print('[FORGE-AGENT] Provisioning files NOT found. Falling back to Captive Portal...', flush=True)
        start_captive_portal()

if __name__ == '__main__':
    apply_provisioning()
