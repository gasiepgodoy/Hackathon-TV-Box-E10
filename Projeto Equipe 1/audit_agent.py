import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
import yaml
import cv2
import requests

REPO_DIR = Path(r"C:\Users\Aluno\Hackathon-TV-Box-E10\Projeto Equipe 1")
APPLIANCE_HOST = "100.112.237.10"
APPLIANCE_PORT = 8080
BASE_URL = f"http://{APPLIANCE_HOST}:{APPLIANCE_PORT}"

def log(msg, tag="INFO"):
    print(f"[{tag}] {msg}")

def test_port(host, port, timeout=2.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        s.close()
        return True
    except Exception:
        return False

# 1. INDEXAÇÃO E INVENTÁRIO DE SERVIÇOS
def index_services():
    log("Indexando arquivos de manifesto e serviços do repositório...")
    inventory = []

    # Manifestos YAML
    for yaml_path in REPO_DIR.glob("**/module.yaml"):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            svc_id = data.get("id", yaml_path.parent.name)
            name = data.get("name", svc_id)
            rel_path = str(yaml_path.relative_to(REPO_DIR)).replace("\\", "/")
            
            # Portas e variantes
            ports = []
            deps = []
            if "variants" in data:
                for v in data["variants"]:
                    if "services" in v:
                        for s in v["services"]:
                            if "port" in s:
                                ports.append(str(s["port"]))
                            deps.append(s.get("name", ""))
            if not ports:
                # Verificar se tem portas em requirements ou lifecycle
                if "gui" in str(data.get("lifecycle", {})).lower():
                    ports.append("Display HDMI /dev/fb0")
                else:
                    ports.append("Interno / IPC")
            
            reqs = data.get("requirements", {})
            if "pip_packages" in reqs:
                deps.append(f"{len(reqs['pip_packages'])} pacotes Python")
            if "system_packages" in reqs:
                deps.append(f"{len(reqs['system_packages'])} pacotes de sistema")

            inventory.append({
                "servico": name,
                "manifesto": rel_path,
                "porta": ", ".join(ports) if ports else "N/A",
                "dependencias": ", ".join(deps[:3]) if deps else "Nenhuma",
                "status_esperado": "Ativo / Pronto para Execução"
            })
        except Exception as e:
            log(f"Erro ao ler {yaml_path}: {e}", "WARN")

    # Catálogo ForgeDB
    cat_path = REPO_DIR / "ForgeDB" / "modules" / "catalog.yaml"
    if cat_path.exists():
        inventory.append({
            "servico": "ForgeDB Catalog Registry",
            "manifesto": "ForgeDB/modules/catalog.yaml",
            "porta": "N/A (Repositório)",
            "dependencias": "JSON Schema Draft 2020-12",
            "status_esperado": "Validado em CI"
        })

    # Serviços Systemd
    systemd_dir = REPO_DIR / "ForgeOS" / "systemd"
    for unit_path in sorted(systemd_dir.glob("*.service")):
        unit_name = unit_path.name
        rel_path = str(unit_path.relative_to(REPO_DIR)).replace("\\", "/")
        port = "8080" if "portal" in unit_name else ("67 UDP, 53 UDP" if "ap" in unit_name else "Framebuffer /dev/fb0")
        dep = "wlan0, dnsmasq" if "ap" in unit_name else ("forge-ap.service" if "portal" in unit_name else "local-fs.target")
        inventory.append({
            "servico": unit_name,
            "manifesto": rel_path,
            "porta": port,
            "dependencias": dep,
            "status_esperado": "Ativo (systemd)"
        })

    # Daemon Principal ForgeHub
    inventory.append({
        "servico": "ForgeHub Daemon & Web UI",
        "manifesto": "ForgeOS/web/server.py (e /opt/forgehub/forgehub)",
        "porta": "8080 TCP",
        "dependencias": "Linux Kernel 6.18, BBolt, wpa_supplicant",
        "status_esperado": "Executando (Ativo)"
    })

    return inventory

# 2. VALIDAÇÃO DE QR CODES
def scan_qr_codes():
    log("Iniciando varredura e decodificação de QR codes com OpenCV...")
    img_dir = REPO_DIR / "imagens"
    detector = cv2.QRCodeDetector()
    results = []

    for img_path in sorted(img_dir.glob("*.png")):
        name = img_path.name
        if "qr" in name.lower() or "hdmi" in name.lower() or "07" in name.lower():
            t0 = time.perf_counter()
            img = cv2.imread(str(img_path))
            if img is None:
                continue

            ok, decoded_info, points, _ = detector.detectAndDecodeMulti(img)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            payload = None
            if ok:
                non_empty = [t for t in decoded_info if t]
                if non_empty:
                    payload = non_empty[0]
            if not payload:
                val, _, _ = detector.detectAndDecode(img)
                if val:
                    payload = val

            status = "Pass" if payload else ("N/A (Barra de Progresso)" if "aplicando" in name.lower() else "Fail")
            results.append({
                "arquivo": name,
                "status": status,
                "tempo_ms": round(elapsed_ms, 2),
                "payload": payload or ("Nenhum QR presente (Design intencional: etapa de transição)" if "aplicando" in name.lower() else "Não detectado")
            })

    return results

# 3. TESTES DE API & ENDPOINTS
def test_api_endpoints():
    log("Executando bateria de testes em endpoints HTTP...")
    endpoints = [
        ("Início / Web UI", "GET", "/", 200, "HTML do ForgeHub"),
        ("Sistema - Info do Host", "GET", "/api/system/info", 200, "JSON do Hostname/OS"),
        ("Sistema - Estatísticas", "GET", "/api/system/stats", 200, "JSON de CPU/RAM/Disco"),
        ("Hardware - Telemetria", "GET", "/api/hardware/telemetry", 200, "JSON com temp/núcleos"),
        ("Módulos - Catálogo & Estado", "GET", "/api/modules", 200, "Lista de manifestos"),
        ("Rede - Status Wi-Fi", "GET", "/api/wifi/status", 200, "Estado wlan0 / AP"),
        ("Rede - Varredura Wi-Fi", "GET", "/api/wifi/scan", 200, "Scan de SSIDs e RSSI"),
        ("Logs - Stream RFC 5424", "GET", "/api/logs?limit=25", 200, "Logs estruturados"),
        ("Legado - Status", "GET", "/api/status", 200, "Compatibilidade v1"),
        ("Legado - Telemetria", "GET", "/api/telemetry", 200, "Compatibilidade v1")
    ]

    results = []
    for name, method, path, expected_code, desc in endpoints:
        url = f"{BASE_URL}{path}"
        t0 = time.perf_counter()
        try:
            res = requests.request(method, url, timeout=4)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            passed = (res.status_code == expected_code)
            results.append({
                "servico": "ForgeHub API",
                "teste": f"{method} {path}",
                "resultado": "Pass" if passed else "Fail",
                "status_code": res.status_code,
                "tempo_ms": round(elapsed_ms, 1),
                "bytes": len(res.content),
                "detalhes": f"Retornou {res.status_code} ({desc})"
            })
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            results.append({
                "servico": "ForgeHub API",
                "teste": f"{method} {path}",
                "resultado": "Fail",
                "status_code": 0,
                "tempo_ms": round(elapsed_ms, 1),
                "bytes": 0,
                "detalhes": f"Erro de conexão: {str(e)}"
            })

    return results

# 4. TESTES DE PORTAS E REDE
def test_ports():
    log("Testando conectividade de portas no appliance...")
    ports_to_test = [
        ("SSH Server", APPLIANCE_HOST, 22),
        ("ForgeHub Web Portal", APPLIANCE_HOST, 8080),
        ("Web-Scraping API (Docker/Uvicorn)", APPLIANCE_HOST, 8000),
        ("PostgreSQL (Docker)", APPLIANCE_HOST, 5432),
        ("Redis (Docker)", APPLIANCE_HOST, 6379),
    ]

    port_results = []
    for svc_name, host, port in ports_to_test:
        t0 = time.perf_counter()
        is_open = test_port(host, port)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        port_results.append({
            "servico": svc_name,
            "porta": port,
            "aberta": is_open,
            "tempo_ms": round(elapsed_ms, 1)
        })
    return port_results

# 5. EXECUÇÃO GERAL
def main():
    start_time = time.time()
    log("=========================================================")
    log("  AGENTE DE AUDITORIA AUTOMATIZADA — MULTI-FORGE / FORGEOS")
    log("=========================================================")

    inventory = index_services()
    qr_results = scan_qr_codes()
    api_results = test_api_endpoints()
    port_results = test_ports()

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_servicos_indexados": len(inventory),
        "total_qr_testados": len(qr_results),
        "total_api_testadas": len(api_results),
        "api_pass": sum(1 for r in api_results if r["resultado"] == "Pass"),
        "api_fail": sum(1 for r in api_results if r["resultado"] == "Fail"),
        "tempo_total_s": round(time.time() - start_time, 2),
        "inventario": inventory,
        "qr_codes": qr_results,
        "api_endpoints": api_results,
        "portas": port_results
    }

    out_json = REPO_DIR / "audit_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    log(f"Auditoria concluída com sucesso em {summary['tempo_total_s']}s!")
    log(f"Resultados salvos em {out_json}")

if __name__ == "__main__":
    main()
