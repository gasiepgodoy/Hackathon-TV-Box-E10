#!/usr/bin/env python3
"""ForgeOS Provisioning Portal v2.1 — REST API + SvelteKit SPA.

Single-radio appliance: serves the captive portal UI on :8080 and
orchestrates client-mode provisioning via apply-client.sh.

Backend compatible with ESP32-sveltekit frontend conventions:
  /rest/*  → REST API (features, systemStatus, wifiStatus, etc.)
  /ws/*    → WebSocket stubs (SSE fallback)
  /api/*   → ForgeOS provisioning API
  /_app/*  → SvelteKit build assets
"""
import json
import mimetypes
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import yaml
except ImportError:
    yaml = None

BASE = os.environ.get("FORGEOS_BASE", "/opt/forgeos" if os.path.exists("/opt/forgeos") else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(BASE, "web")
STATE = os.path.join(BASE, "state")
NETWORK = os.path.join(BASE, "network")
APPLY = os.path.join(BASE, "bin", "apply-client.sh")
PORT = 8080

os.makedirs(STATE, exist_ok=True)
mimetypes.init()


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def ap_active():
    try:
        out = subprocess.run(
            ["pgrep", "-f", "wpa_supplicant.*wpa_ap.conf"],
            capture_output=True, text=True)
        return out.returncode == 0
    except Exception:
        return False


def get_ap_config():
    conf_path = os.path.join(NETWORK, "wpa_ap.conf")
    config = {
        "ssid": "RTL8189FTV_AP",
        "password": "",
        "channel": 6,
        "ip": "192.168.4.1",
        "hidden": False
    }
    if os.path.exists(conf_path):
        try:
            with open(conf_path) as f:
                content = f.read()
                m_ssid = re.search(r'ssid="([^"]+)"', content)
                m_psk = re.search(r'psk="([^"]+)"', content)
                m_freq = re.search(r'frequency=([0-9]+)', content)
                if m_ssid:
                    config["ssid"] = m_ssid.group(1)
                if m_psk:
                    config["password"] = m_psk.group(1)
                if m_freq:
                    freq = int(m_freq.group(1))
                    config["channel"] = (freq - 2407) // 5 if freq < 3000 else (freq - 5000) // 5
        except Exception:
            pass
    return config


def status_payload():
    # 1. Query real wlan0 IPv4 address dynamically
    wlan_ips = []
    try:
        out = subprocess.run(
            ["ip", "-4", "addr", "show", "wlan0"],
            capture_output=True, text=True, timeout=2)
        wlan_ips = re.findall(r'inet\s+([\d.]+)', out.stdout)
    except Exception:
        pass

    # 2. Check if client wpa_supplicant is running
    is_client_proc = False
    try:
        out = subprocess.run(
            ["pgrep", "-f", "wpa_supplicant.*client.conf"],
            capture_output=True, text=True)
        is_client_proc = (out.returncode == 0)
    except Exception:
        pass

    # 3. Check if AP wpa_supplicant is running
    is_ap_proc = False
    try:
        out = subprocess.run(
            ["pgrep", "-f", "wpa_supplicant.*wpa_ap.conf"],
            capture_output=True, text=True)
        is_ap_proc = (out.returncode == 0)
    except Exception:
        pass

    result = read_json(os.path.join(STATE, "result.json"))
    prov = read_json(os.path.join(STATE, "provision.json"))
    applying = os.path.exists(os.path.join(STATE, "applying"))

    # Determine real state
    # Client is active if client process is running and wlan0 has an assigned non-AP IP
    client_ip = None
    for ip in wlan_ips:
        if ip != "192.168.4.1":
            client_ip = ip
            break

    client_connected = bool(is_client_proc and client_ip)
    client_ssid = None
    if client_connected:
        if prov and prov.get("ssid"):
            client_ssid = prov.get("ssid")
        elif result and result.get("ssid"):
            client_ssid = result.get("ssid")
        else:
            client_ssid = "Wi-Fi Conectado"

    # AP is truly active if AP process is running and NOT in client connected state
    ap_active_state = bool(is_ap_proc and not client_connected and ("192.168.4.1" in wlan_ips))

    return {
        "ap_active": ap_active_state,
        "ssid": get_ap_config()["ssid"] if ap_active_state else None,
        "provisioning": applying,
        "client_connected": client_connected,
        "client_ssid": client_ssid,
        "client_ip": client_ip,
        "last_failed": bool(result and result.get("status") == "failed"),
        "last_result": result,
        "attempt": prov or {}
    }


def get_real_scan():
    # Windows local dev Wi-Fi scan fallback
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                capture_output=True, text=True, timeout=5, encoding="cp850", errors="replace")
            lines = out.stdout.splitlines()
            networks = []
            cur_ssid = None
            cur_auth = "psk"
            cur_bssid = None
            cur_signal = -60
            seen = set()

            for line in lines:
                line_s = line.strip()
                if line_s.startswith("SSID "):
                    parts = line_s.split(":", 1)
                    if len(parts) == 2:
                        cur_ssid = parts[1].strip()
                elif "Autentica" in line_s or "Authentication" in line_s:
                    if "Enterprise" in line_s or "802.1X" in line_s:
                        cur_auth = "eap"
                    elif "Open" in line_s or "Abrir" in line_s or "Nenhum" in line_s:
                        cur_auth = "open"
                    else:
                        cur_auth = "psk"
                elif line_s.startswith("BSSID "):
                    parts = line_s.split(":", 1)
                    if len(parts) == 2:
                        cur_bssid = parts[1].strip()
                elif "Sinal" in line_s or "Signal" in line_s:
                    m = re.search(r'(\d+)%', line_s)
                    if m:
                        cur_signal = int(m.group(1)) // 2 - 100
                elif "Canal" in line_s or "Channel" in line_s:
                    m = re.search(r'(\d+)', line_s)
                    if m:
                        cur_channel = int(m.group(1))
                        if cur_ssid and cur_ssid not in seen:
                            seen.add(cur_ssid)
                            networks.append({
                                "ssid": cur_ssid,
                                "bssid": cur_bssid or "",
                                "rssi": cur_signal,
                                "channel": cur_channel,
                                "encryption": cur_auth,
                                "flags": f"[{cur_auth.upper()}]"
                            })
            networks.sort(key=lambda x: x["rssi"], reverse=True)
            return networks
        except Exception as e:
            print(f"[SCAN-WIN] Error: {e}")
            return []

    try:
        ctrl = "/var/run/wpa_supplicant-ap"
        if not os.path.exists(os.path.join(ctrl, "wlan0")):
            ctrl = "/var/run/wpa_supplicant-client"
        if not os.path.exists(os.path.join(ctrl, "wlan0")):
            ctrl = "/var/run/wpa_supplicant"

        subprocess.run(
            ["wpa_cli", "-p", ctrl, "-i", "wlan0", "scan"],
            capture_output=True, text=True, timeout=5)
        time.sleep(3)
        out = subprocess.run(
            ["wpa_cli", "-p", ctrl, "-i", "wlan0", "scan_results"],
            capture_output=True, text=True, timeout=5)
        lines = out.stdout.strip().split("\n")
        networks = []
        seen = set()
        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) >= 5:
                bssid, freq, signal, flags, ssid = parts[0], parts[1], parts[2], parts[3], parts[4]
                ssid = ssid.strip()
                if not ssid or ssid in seen:
                    continue
                seen.add(ssid)
                enc = "psk"
                if "EAP" in flags or "802.1X" in flags:
                    enc = "eap"
                elif "ESS" in flags and "WPA" not in flags:
                    enc = "open"
                try:
                    f = int(freq)
                    ch = (f - 2407) // 5 if f < 3000 else (f - 5000) // 5
                except ValueError:
                    ch = 6
                networks.append({
                    "ssid": ssid,
                    "bssid": bssid,
                    "rssi": int(signal),
                    "channel": ch,
                    "encryption": enc,
                    "flags": flags
                })
        networks.sort(key=lambda x: x["rssi"], reverse=True)
        return networks
    except Exception as e:
        print(f"[SCAN] Error: {e}")
        return []


# --- ESP32-sveltekit compatibility layer ---

def esp32_features():
    return {
        "project": "ForgeOS",
        "version": "2.1.0",
        "firmware_version": "2.1.0",
        "device": "BTV-E10",
        "features": {
            "security": False,
            "mqtt": False,
            "ntp": True,
            "ota": False,
            "upload_firmware": False,
            "wifi": True
        }
    }


# --- Real-time Metrics Engine (Cockpit style) ---
_last_cpu_times = None
_last_net_bytes = None
_last_metrics_time = 0.0

def get_realtime_metrics():
    global _last_cpu_times, _last_net_bytes, _last_metrics_time
    now = time.time()
    dt = max(now - _last_metrics_time, 0.1) if _last_metrics_time > 0 else 1.0
    _last_metrics_time = now

    # 1. CPU Usage %
    cpu_pct = 0.0
    try:
        with open("/proc/stat") as f:
            line = f.readline()
            if line.startswith("cpu "):
                fields = [float(x) for x in line.split()[1:]]
                idle_time = fields[3] + fields[4]
                total_time = sum(fields)
                if _last_cpu_times is not None:
                    prev_idle, prev_total = _last_cpu_times
                    diff_idle = idle_time - prev_idle
                    diff_total = total_time - prev_total
                    if diff_total > 0:
                        cpu_pct = round(max(0.0, min(100.0, (1.0 - diff_idle / diff_total) * 100.0)), 1)
                _last_cpu_times = (idle_time, total_time)
    except Exception:
        # Windows fallback or synthetic jitter
        import random
        cpu_pct = round(random.uniform(2.5, 12.0), 1)

    # 2. RAM Usage
    mem_total = 1980
    mem_avail = 1620
    mem_free = 1400
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0] == "MemTotal:":
                    mem_total = int(parts[1]) // 1024
                elif parts[0] == "MemAvailable:":
                    mem_avail = int(parts[1]) // 1024
                elif parts[0] == "MemFree:":
                    mem_free = int(parts[1]) // 1024
    except Exception:
        pass

    ram_used = max(0, mem_total - mem_avail)
    ram_pct = round((ram_used / max(mem_total, 1)) * 100.0, 1)

    # 3. Network Throughput (RX / TX KB/s)
    rx_rate_kbs = 0.0
    tx_rate_kbs = 0.0
    try:
        cur_rx = 0
        cur_tx = 0
        with open("/proc/net/dev") as f:
            for line in f:
                if ":" in line:
                    iface, stats = line.split(":", 1)
                    iface = iface.strip()
                    if iface in ("eth0", "wlan0"):
                        vals = stats.split()
                        cur_rx += int(vals[0])
                        cur_tx += int(vals[8])
        if _last_net_bytes is not None:
            prev_rx, prev_tx = _last_net_bytes
            rx_rate_kbs = round(max(0.0, (cur_rx - prev_rx) / (dt * 1024.0)), 1)
            tx_rate_kbs = round(max(0.0, (cur_tx - prev_tx) / (dt * 1024.0)), 1)
        _last_net_bytes = (cur_rx, cur_tx)
    except Exception:
        pass

    # 4. Uptime
    uptime_sec = 0
    try:
        with open("/proc/uptime") as f:
            uptime_sec = int(float(f.read().split()[0]))
    except Exception:
        uptime_sec = int(time.time() - 1756500000)

    # 5. Disk Usage
    disk_total_gb = 29.0
    disk_used_gb = 3.5
    try:
        st = os.statvfs("/")
        disk_total_gb = round((st.f_blocks * st.f_frsize) / (1024**3), 1)
        disk_free_gb = round((st.f_bavail * st.f_frsize) / (1024**3), 1)
        disk_used_gb = round(disk_total_gb - disk_free_gb, 1)
    except Exception:
        pass

    # 6. Real-time CPU Frequency (MHz)
    cpu_cur_freq_mhz = 1400
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq") as f:
            cpu_cur_freq_mhz = int(f.read().strip()) // 1000
    except Exception:
        pass

    # 7. Real-time CPU Temperature (°C) - S905X2 Thermal Zone
    cpu_temp = 42.0
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            cpu_temp = round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        pass

    # 8. Load Average (1m, 5m, 15m)
    load_avg = [0.10, 0.05, 0.05]
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            load_avg = [float(parts[0]), float(parts[1]), float(parts[2])]
    except Exception:
        pass

    # 9. Top 5 Processes by Memory/CPU
    top_procs = []
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%mem"],
            capture_output=True, text=True, timeout=2)
        lines = out.stdout.strip().split("\n")[1:6]
        for l in lines:
            p = l.split()
            if len(p) >= 4:
                top_procs.append({
                    "pid": p[0],
                    "name": p[1],
                    "cpu": p[2],
                    "mem": p[3]
                })
    except Exception:
        pass

    return {
        "timestamp": now,
        "cpu_pct": cpu_pct,
        "cpu_freq_mhz": cpu_cur_freq_mhz,
        "cpu_temp": cpu_temp,
        "load_avg": load_avg,
        "ram_used_mb": ram_used,
        "ram_total_mb": mem_total,
        "ram_pct": ram_pct,
        "rx_kbs": rx_rate_kbs,
        "tx_kbs": tx_rate_kbs,
        "uptime": uptime_sec,
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "top_processes": top_procs
    }


def get_hardware_info():
    model = "BTV Express E10 (SEI510)"
    try:
        with open("/proc/device-tree/model", "rb") as f:
            raw = f.read().decode('utf-8', errors='ignore').strip('\x00\n\r ')
            if raw:
                model = f"{raw} (BTV Express E10)"
    except Exception:
        pass

    os_name = "Armbian GNU/Linux"
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    os_name = line.split("=", 1)[1].strip('"\n')
                    break
    except Exception:
        pass

    kernel = "Linux 6.18-ophub"
    try:
        kernel = os.uname().release
    except Exception:
        pass

    cores = os.cpu_count() or 4
    
    # Disk /boot
    boot_used_mb = 170
    boot_total_mb = 510
    try:
        st = os.statvfs("/boot")
        boot_total_mb = round((st.f_blocks * st.f_frsize) / (1024**2))
        boot_free_mb = round((st.f_bavail * st.f_frsize) / (1024**2))
        boot_used_mb = boot_total_mb - boot_free_mb
    except Exception:
        pass

    return {
        "device_model": model,
        "os_name": os_name,
        "kernel": kernel,
        "cpu_arch": "aarch64 (ARMv8-A)",
        "cpu_soc": "Amlogic S905X2",
        "cpu_cores": cores,
        "dtb": "meson-g12a-btv-e10-enterprise.dtb",
        "boot_used_mb": boot_used_mb,
        "boot_total_mb": boot_total_mb
    }


def esp32_system_status():
    m = get_realtime_metrics()
    return {
        "esp_platform": "linux-aarch64",
        "firmware_version": "2.1.0",
        "max_alloc_heap": (m["ram_total_mb"] - m["ram_used_mb"]) * 1048576,
        "free_heap": (m["ram_total_mb"] - m["ram_used_mb"]) * 1048576,
        "total_heap": m["ram_total_mb"] * 1048576,
        "cpu_pct": m["cpu_pct"],
        "rx_kbs": m["rx_kbs"],
        "tx_kbs": m["tx_kbs"],
        "sketch_size": 0,
        "free_sketch_space": 0,
        "sdk_version": "Armbian",
        "flash_chip_size": 0,
        "cpu_freq_mhz": 1800,
        "cpu_type": "Amlogic S905X2",
        "cpu_cores": 4,
        "uptime": m["uptime"]
    }



def esp32_wifi_status():
    ap = ap_active()
    status = {
        "status": 3 if ap else 0,
        "local_ip": "192.168.4.1" if ap else "",
        "mac_address": "",
        "rssi": 0,
        "ssid": "",
        "bssid": "",
        "channel": 6,
        "subnet_mask": "255.255.255.0",
        "gateway_ip": "192.168.4.1",
        "dns_ip_1": "192.168.4.1"
    }
    try:
        out = subprocess.run(["ip", "link", "show", "wlan0"],
                             capture_output=True, text=True, timeout=3)
        m = re.search(r'link/ether\s+([\da-f:]+)', out.stdout)
        if m:
            status["mac_address"] = m.group(1).upper()
    except Exception:
        pass
    if not ap:
        s = status_payload()
        if s.get("client_ip"):
            status["local_ip"] = s["client_ip"]
        if s.get("client_ssid"):
            status["ssid"] = s["client_ssid"]
        status["status"] = 3 if s.get("client_connected") else 6
    return status


def esp32_ethernet_status():
    result = {
        "status": 0,
        "local_ip": "",
        "mac_address": "",
        "connected": False
    }
    try:
        out = subprocess.run(["ip", "-4", "addr", "show", "eth0"],
                             capture_output=True, text=True, timeout=3)
        m_ip = re.search(r'inet\s+([\d.]+)', out.stdout)
        if m_ip:
            result["local_ip"] = m_ip.group(1)
            result["connected"] = True
            result["status"] = 3
        out2 = subprocess.run(["ip", "link", "show", "eth0"],
                              capture_output=True, text=True, timeout=3)
        m_mac = re.search(r'link/ether\s+([\da-f:]+)', out2.stdout)
        if m_mac:
            result["mac_address"] = m_mac.group(1).upper()
    except Exception:
        pass
    return result


def esp32_ap_status():
    cfg = get_ap_config()
    return {
        "status": 1 if ap_active() else 0,
        "ip_address": "192.168.4.1",
        "mac_address": "",
        "station_num": 0,
        "provision_mode": 1,
        "ssid": cfg["ssid"],
        "password": cfg["password"],
        "channel": cfg["channel"],
        "ssid_hidden": cfg.get("hidden", False),
        "max_clients": 4,
        "local_ip": "192.168.4.1"
    }


def esp32_scan():
    nets = get_real_scan()
    return {
        "networks": [
            {
                "ssid": n["ssid"],
                "bssid": n.get("bssid", ""),
                "rssi": n["rssi"],
                "channel": n["channel"],
                "encryption_type": 4 if n.get("encryption") == "psk" else (5 if n.get("encryption") == "eap" else 0)
            }
            for n in nets
        ]
    }


def find_repo_root():
    candidates = [
        os.path.dirname(BASE),
        "/opt/multi-forge",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    ]
    for c in candidates:
        if c and os.path.exists(os.path.join(c, "ForgeDB", "modules", "catalog.yaml")):
            return c
    return None


def get_modules_catalog():
    repo_root = find_repo_root()
    catalog_file = os.path.join(repo_root, "ForgeDB", "modules", "catalog.yaml") if repo_root else None

    if catalog_file and os.path.exists(catalog_file) and yaml:
        try:
            with open(catalog_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            modules = data.get("modules", [])
            for m in modules:
                mod_id = m.get("id")
                mod_yaml_path = os.path.join(repo_root, "ForgeDB", "modules", mod_id, "module.yaml")
                if os.path.exists(mod_yaml_path):
                    with open(mod_yaml_path, encoding="utf-8") as mf:
                        m_detail = yaml.safe_load(mf) or {}
                        m["requirements"] = m_detail.get("requirements", {})
                        m["variants"] = m_detail.get("variants", [])
                        m["author"] = m_detail.get("author", "")
                        m["license"] = m_detail.get("license", "")

                status_file = os.path.join(STATE, f"module_{mod_id}.json")
                if os.path.exists(status_file):
                    m["status"] = read_json(status_file) or {"state": "installed"}
                else:
                    m["status"] = {"state": "available"}
            return {"modules": modules, "total": len(modules)}
        except Exception as e:
            print(f"[MODULES] Error reading catalog: {e}")

    # Fallback default catalog
    return {
        "modules": [
            {
                "id": "totem",
                "name": "Mina — Assistente Virtual Acadêmica",
                "version": "1.0.0",
                "category": "ai",
                "icon": "ai",
                "description": "Quiosque de voz inteligente com PyQt5, Picovoice Porcupine wake-word, STT/TTS e classificador MABI.",
                "source_path": "ForgeModules/totem",
                "tier": "stable",
                "promoted": True,
                "author": "G.E.R.A — UNESP Sorocaba",
                "license": "MIT",
                "requirements": {"min_ram_mb": 512, "min_storage_mb": 300, "python": ">=3.9"},
                "status": {"state": "available"}
            },
            {
                "id": "web-scraping",
                "name": "Coletor Acadêmico & RAG Agent",
                "version": "1.0.0",
                "category": "data",
                "icon": "data",
                "description": "Pipeline assíncrono de coleta de dados universitários com FastAPI, LangChain RAG, PostgreSQL e Redis.",
                "source_path": "ForgeModules/sub-modulos/web-scraping",
                "tier": "beta",
                "promoted": False,
                "author": "G.E.R.A — UNESP Sorocaba",
                "license": "MIT",
                "requirements": {"min_ram_mb": 1024, "min_storage_mb": 500, "python": ">=3.12"},
                "status": {"state": "available"}
            }
        ],
        "total": 2
    }


def get_module_detail(mod_id):
    repo_root = find_repo_root()
    if repo_root and yaml:
        mod_yaml_path = os.path.join(repo_root, "ForgeDB", "modules", mod_id, "module.yaml")
        if os.path.exists(mod_yaml_path):
            try:
                with open(mod_yaml_path, encoding="utf-8") as f:
                    detail = yaml.safe_load(f) or {}
                status_file = os.path.join(STATE, f"module_{mod_id}.json")
                detail["status"] = read_json(status_file) if os.path.exists(status_file) else {"state": "available"}
                return detail
            except Exception as e:
                print(f"[MODULES] Error loading module {mod_id}: {e}")
    catalog = get_modules_catalog()
    for m in catalog.get("modules", []):
        if m.get("id") == mod_id:
            return m
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "ForgePortal/2.1"

    def log_message(self, fmt, *args):
        print(f"[PORTAL] {self.address_string()} {fmt % args}", flush=True)

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _guess_type(self, path):
        mt, _ = mimetypes.guess_type(path)
        return mt or "application/octet-stream"

    def _serve_file(self, full, ctype=None):
        if ctype is None:
            ctype = self._guess_type(full)
        try:
            with open(full, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if "/_app/immutable/" in full:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            else:
                self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            return self._send(404, {"error": "not found"})

    def do_GET(self):
        path = self.path.split("?")[0]

        # --- SvelteKit SPA: serve _app/* assets ---
        if path.startswith("/_app/"):
            rel = os.path.normpath(path[1:])
            full = os.path.join(WEB, rel)
            if os.path.isfile(full) and full.startswith(WEB):
                return self._serve_file(full)
            return self._send(404, {"error": "not found"})

        # --- Static assets ---
        if path.startswith("/static/"):
            rel = os.path.normpath(path[len("/static/"):]).lstrip("/\\")
            full = os.path.join(WEB, "static", rel)
            if os.path.isfile(full) and full.startswith(os.path.join(WEB, "static")):
                return self._serve_file(full)
            return self._send(404, {"error": "not found"})

        # --- Direct file serving (favicon, logo, manifest, etc.) ---
        if path in ("/favicon.png", "/logo.png", "/manifest.json"):
            full = os.path.join(WEB, path.lstrip("/"))
            if os.path.isfile(full):
                return self._serve_file(full)

        # --- Systemd Services Management (Cockpit style) ---
        if path == "/api/services":
            services_list = [
                {"unit": "forge-portal.service", "desc": "Servidor Web & API REST", "category": "forgeos"},
                {"unit": "forge-ap.service", "desc": "Ponto de Acesso Wi-Fi & dnsmasq", "category": "forgeos"},
                {"unit": "forge-display.service", "desc": "Renderizador HDMI FB0 Dual QR", "category": "forgeos"},
                {"unit": "forge-watchdog.service", "desc": "Watchdog de Contingência 75s", "category": "forgeos"},
                {"unit": "forge-fbcon-disable.service", "desc": "Desabilitar Cursor Framebuffer", "category": "forgeos"},
                {"unit": "ssh.service", "desc": "Servidor SSH OpenSSH", "category": "system"},
                {"unit": "systemd-journald.service", "desc": "Coletor de Logs do Kernel", "category": "system"},
                {"unit": "systemd-timesyncd.service", "desc": "Sincronização de Relógio NTP", "category": "system"}
            ]
            for s in services_list:
                try:
                    out = subprocess.run(["systemctl", "is-active", s["unit"]], capture_output=True, text=True, timeout=2)
                    st = out.stdout.strip()
                    s["active"] = (st == "active")
                    s["state"] = st  # active, inactive, failed, activating
                    
                    en_out = subprocess.run(["systemctl", "is-enabled", s["unit"]], capture_output=True, text=True, timeout=2)
                    s["enabled"] = (en_out.stdout.strip() == "enabled")
                except Exception:
                    s["active"] = True
                    s["state"] = "active"
                    s["enabled"] = True
            return self._send(200, {"services": services_list})

        # --- System Logs API (journalctl RFC 5424) ---
        if path == "/api/logs":
            query_str = self.path.split("?")[1] if "?" in self.path else ""
            params = urllib.parse.parse_qs(query_str)
            unit = params.get("unit", [""])[0].strip()
            level = params.get("level", ["all"])[0].strip()
            search = params.get("search", [""])[0].strip()
            lines_cnt = int(params.get("lines", [120])[0])

            cmd = ["journalctl", "-n", str(lines_cnt), "--no-pager", "-o", "short-iso"]
            if unit and unit != "all":
                if unit == "kernel":
                    cmd.append("-k")
                else:
                    cmd.extend(["-u", unit])
            if level in ("emerg", "alert", "crit", "err", "warning", "notice", "info", "debug"):
                cmd.extend(["-p", level])

            log_entries = []
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                for line in out.stdout.splitlines():
                    m = re.match(r'^\S+T(\d{2}:\d{2}:\d{2})\S*\s+\S+\s+([^:\[]+)(?:\[\d+\])?:\s+(.*)$', line)
                    if m:
                        t_str, u_name, msg = m.group(1), m.group(2).strip(), m.group(3).strip()
                    else:
                        t_str, u_name, msg = "--:--:--", "system", line.strip()

                    l_val = "info"
                    lower_msg = msg.lower()
                    if any(k in lower_msg for k in ("err", "fail", "fatal", "crit", "error", "emerg", "oops", "corrupt")):
                        l_val = "err"
                    elif any(k in lower_msg for k in ("warn", "warning", "denied", "retry")):
                        l_val = "warning"
                    elif "debug" in lower_msg:
                        l_val = "debug"

                    if search and search.lower() not in line.lower():
                        continue

                    log_entries.append({
                        "time": t_str,
                        "unit": u_name,
                        "level": l_val,
                        "message": msg,
                        "raw": line
                    })
            except Exception as e:
                log_entries = [{
                    "time": time.strftime("%H:%M:%S"),
                    "unit": "journald",
                    "level": "err",
                    "message": f"Erro ao consultar journalctl: {e}",
                    "raw": str(e)
                }]

            return self._send(200, {"logs": log_entries, "total": len(log_entries)})

        # --- ESP32-sveltekit REST compat ---
        if path in ("/rest/metrics", "/api/telemetry"):
            return self._send(200, get_realtime_metrics())
        if path in ("/api/hardware", "/api/systemInfo"):
            return self._send(200, get_hardware_info())
        if path == "/rest/features":
            return self._send(200, esp32_features())
        if path == "/rest/systemStatus":
            return self._send(200, esp32_system_status())
        if path == "/rest/wifiStatus":
            return self._send(200, esp32_wifi_status())
        if path == "/rest/ethernetStatus":
            return self._send(200, esp32_ethernet_status())
        if path == "/rest/apStatus":
            return self._send(200, esp32_ap_status())
        if path == "/rest/wifiScan":
            return self._send(200, esp32_scan())

        # --- WebSocket stub (SSE) ---
        if path == "/ws/events":
            return self._send(200, {"type": "ping"})

        # --- ForgeOS API ---
        if path == "/api/status":
            return self._send(200, status_payload())
        if path == "/api/scan":
            nets = get_real_scan()
            return self._send(200, {"networks": nets})
        if path == "/api/ap":
            return self._send(200, get_ap_config())

        # --- Module Hub API ---
        if path in ("/rest/modules", "/api/modules"):
            return self._send(200, get_modules_catalog())
        if path.startswith("/rest/modules/") or path.startswith("/api/modules/"):
            mod_id = path.rstrip("/").split("/")[-1]
            detail = get_module_detail(mod_id)
            if detail:
                return self._send(200, detail)
            return self._send(404, {"error": f"module '{mod_id}' not found"})

        # --- SPA fallback: any unmatched route → index.html ---
        return self._serve_file(os.path.join(WEB, "index.html"), "text/html")

    def do_POST(self):
        path = self.path.split("?")[0]

        if path.startswith("/api/modules/") or path.startswith("/rest/modules/"):
            parts = path.rstrip("/").split("/")
            if len(parts) >= 4:
                mod_id = parts[-2]
                action = parts[-1]
                status_file = os.path.join(STATE, f"module_{mod_id}.json")
                if action == "install":
                    with open(status_file, "w") as sf:
                        json.dump({"state": "installed", "installed_at": int(time.time()), "active": True}, sf)
                    return self._send(200, {"ok": True, "message": f"Módulo '{mod_id}' instalado", "status": {"state": "installed", "active": True}})
                elif action == "start":
                    with open(status_file, "w") as sf:
                        json.dump({"state": "running", "started_at": int(time.time()), "active": True}, sf)
                    return self._send(200, {"ok": True, "message": f"Módulo '{mod_id}' iniciado", "status": {"state": "running", "active": True}})
                elif action == "stop":
                    with open(status_file, "w") as sf:
                        json.dump({"state": "stopped", "stopped_at": int(time.time()), "active": False}, sf)
                    return self._send(200, {"ok": True, "message": f"Módulo '{mod_id}' pausado", "status": {"state": "stopped", "active": False}})
                elif action == "uninstall":
                    try:
                        os.remove(status_file)
                    except OSError:
                        pass
        if path.startswith("/api/services/"):
            parts = path.rstrip("/").split("/")
            if len(parts) >= 4:
                unit = parts[-2]
                action = parts[-1]
                if action in ("restart", "start", "stop"):
                    try:
                        subprocess.Popen(["systemctl", action, unit])
                        return self._send(200, {"ok": True, "message": f"Serviço '{unit}' comando: {action}"})
                    except Exception as e:
                        return self._send(500, {"error": str(e)})

        if path in ("/api/logs/vacuum", "/api/logs/clear"):
            try:
                subprocess.run(["journalctl", "--vacuum-time=1d"], timeout=5)
                return self._send(200, {"ok": True, "message": "Logs arquivados e rotacionados com sucesso!"})
            except Exception as e:
                return self._send(500, {"error": str(e)})

        if path == "/api/reset":
            for f in ("result.json", "attempt.json", "provision.json", "applying"):
                try:
                    os.remove(os.path.join(STATE, f))
                except OSError:
                    pass
            if not status_payload()["ap_active"]:
                subprocess.Popen(["bash", os.path.join(BASE, "bin", "start-ap.sh")],
                                 stdout=open("/var/log/forge-ap.log", "a"),
                                 stderr=subprocess.STDOUT)
            return self._send(200, {"ok": True, "message": "Modo AP restaurado"})

        if path == "/api/ap":
            length = min(int(self.headers.get("Content-Length", 0)), 4096)
            try:
                data = json.loads(self.rfile.read(length))
                ssid = data.get("ssid", "RTL8189FTV_AP").strip()
                psk = data.get("password", "").strip()
                ch = int(data.get("channel", 6))
                freq = 2412 + (ch - 1) * 5
                key_mgmt = "WPA-PSK" if psk else "NONE"
                psk_line = '    psk="' + psk + '"\n' if psk else ""
                conf = (
                    "ctrl_interface=/var/run/wpa_supplicant-ap\n"
                    "ap_scan=1\n\n"
                    "network={\n"
                    '    ssid="' + ssid + '"\n'
                    "    mode=2\n"
                    "    key_mgmt=" + key_mgmt + "\n"
                    + psk_line +
                    "    frequency=" + str(freq) + "\n"
                    "}\n"
                )
                with open(os.path.join(NETWORK, "wpa_ap.conf"), "w") as f:
                    f.write(conf)
                subprocess.Popen(["bash", os.path.join(BASE, "bin", "start-ap.sh")],
                                 stdout=open("/var/log/forge-ap.log", "a"),
                                 stderr=subprocess.STDOUT)
                subprocess.run(["systemctl", "restart", "forge-display.service"], timeout=5)
                return self._send(200, {"ok": True, "message": "AP atualizado"})
            except Exception as e:
                return self._send(400, {"error": str(e)})

        if path == "/rest/wifiScan":
            return self._send(200, esp32_scan())

        if path != "/api/provision":
            return self._send(404, {"error": "not found"})

        if status_payload()["provisioning"]:
            return self._send(409, {"error": "provisionamento em andamento"})

        length = min(int(self.headers.get("Content-Length", 0)), 8192)
        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            return self._send(400, {"error": "json invalido"})

        err = validate(data)
        if err:
            return self._send(400, {"error": err})

        prov_path = os.path.join(STATE, "provision.json")
        with open(prov_path, "w") as f:
            json.dump(data, f)

        open(os.path.join(STATE, "applying"), "w").close()
        log = open("/var/log/forge-apply.log", "a")
        subprocess.Popen(["bash", APPLY, prov_path],
                         stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True)
        return self._send(200, {"ok": True, "message": "testando conexao"})


def validate(d):
    ssid = d.get("ssid", "")
    if not isinstance(ssid, str) or not (0 < len(ssid) <= 32):
        return "SSID invalido"
    if any(c in ssid for c in '"\n\r\t'):
        return "SSID contem caracteres invalidos"
    if d.get("mode") == "psk":
        p = d.get("password", "")
        if p and (not isinstance(p, str) or len(p) < 8 or len(p) > 63):
            return "senha PSK deve ter 8-63 caracteres"
        return None
    if d.get("mode") == "eap":
        if not d.get("identity"):
            return "identidade obrigatoria"
        if not d.get("password"):
            return "senha obrigatoria"
        if d.get("method") not in ("PEAP", "TTLS", "PWD", "TLS"):
            return "metodo EAP invalido"
        if d.get("phase2") not in ("MSCHAPV2", "PAP", "GTC"):
            return "phase2 invalido"
        for k in ("anonymous_identity", "domain"):
            v = d.get(k, "")
            if v and any(c in v for c in '"\n\r\t'):
                return k + " invalido"
        return None
    return "modo invalido"


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("[PORTAL] ForgeOS portal v2.1 on :" + str(PORT), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
