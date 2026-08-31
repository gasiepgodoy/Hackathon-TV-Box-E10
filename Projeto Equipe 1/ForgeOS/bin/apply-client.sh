#!/bin/bash
# Aplica credenciais de rede coletadas pelo portal e testa conectividade.
# Sucesso  -> modo cliente (portal/AP derrubados, rádio único)
# Falha    -> rollback automático para o AP
set -u
BASE=/opt/forgeos
STATE=$BASE/state
PROV="${1:-$STATE/provision.json}"
CONF=$BASE/network/client.conf
TIMEOUT=75

log() { echo "[$(date '+%H:%M:%S')] [APPLY] $*"; }

cleanup() { rm -f "$STATE/applying"; }
trap cleanup EXIT

[ -f "$PROV" ] || { log "provision.json ausente"; exit 1; }

SSID=$(python3 -c "import json;print(json.load(open('$PROV'))['ssid'])")
log "iniciando provisionamento para '$SSID'"

# 1. Gera config wpa_supplicant cliente
python3 "$BASE/network/build_client_conf.py" "$PROV" "$CONF" || {
    echo "{\"status\":\"failed\",\"reason\":\"conf\",\"ts\":$(date +%s)}" > "$STATE/result.json"
    exit 1
}

# 2. Derruba o stack do AP (rádio único)
systemctl stop forge-portal.service forge-display.service 2>/dev/null
pkill -f 'dnsmasq.*dnsmasq_portal.conf' 2>/dev/null || true
pkill -f 'wpa_supplicant.*wpa_ap.conf' 2>/dev/null || true
sleep 1
ip addr flush dev wlan0
ip link set wlan0 up

# 3. Conecta em modo cliente
wpa_supplicant -B -i wlan0 -c "$CONF" -P /run/forge-client.pid
echo "{\"mode\":\"client\",\"ssid\":\"$SSID\",\"ts\":$(date +%s)}" > "$STATE/ap_state.json"

ASSOC=0
for i in $(seq 1 20); do
    if wpa_cli -p /var/run/wpa_supplicant-client -i wlan0 status 2>/dev/null | grep -qE '^wpa_state=COMPLETED'; then
        ASSOC=1; break
    fi
    sleep 2
done

if [ "$ASSOC" -ne 1 ]; then
    log "falhou: não associou ao SSID"
    echo "{\"status\":\"failed\",\"ssid\":\"$SSID\",\"reason\":\"assoc\",\"ts\":$(date +%s)}" > "$STATE/result.json"
    bash "$BASE/bin/start-ap.sh"
    systemctl start forge-portal.service forge-display.service 2>/dev/null || true
    exit 1
fi

# 4. DHCP no cliente
dhclient -1 -q -pf /run/forge-dhclient.pid -lf /var/lib/dhcp/forge.leases wlan0 2>/dev/null \
    || udhcpc -i wlan0 -n -q -t 8 >/dev/null 2>&1 \
    || true

IP=$(ip -4 addr show wlan0 | awk '/inet/{print $2}' | cut -d/ -f1 | head -n1)
if [ -z "${IP:-}" ]; then
    log "falhou: sem IP via DHCP"
    echo "{\"status\":\"failed\",\"ssid\":\"$SSID\",\"reason\":\"dhcp\",\"ts\":$(date +%s)}" > "$STATE/result.json"
    bash "$BASE/bin/start-ap.sh"
    systemctl start forge-portal.service forge-display.service 2>/dev/null || true
    exit 1
fi

# 5. Teste de internet AMARRADO à wlan0 (eth0 pode ter rota default)
NET=0
for i in $(seq 1 $((TIMEOUT / 5))); do
    if ping -c 1 -W 3 -I wlan0 1.1.1.1 >/dev/null 2>&1; then NET=1; break; fi
    sleep 4
done

if [ "$NET" -eq 1 ]; then
    log "CONECTADO: $SSID via $IP — internet ok"
    echo "{\"status\":\"connected\",\"ssid\":\"$SSID\",\"ip\":\"$IP\",\"internet\":true,\"ts\":$(date +%s)}" > "$STATE/result.json"
    systemctl start forge-portal.service forge-display.service 2>/dev/null || true
else
    if ping -c 1 -W 3 -I wlan0 "$IP" >/dev/null 2>&1 || ip route show default | grep -q wlan0; then
        log "conectado à LAN ($SSID via $IP) mas SEM internet — mantendo modo cliente"
        echo "{\"status\":\"connected\",\"ssid\":\"$SSID\",\"ip\":\"$IP\",\"internet\":false,\"ts\":$(date +%s)}" > "$STATE/result.json"
        systemctl start forge-portal.service forge-display.service 2>/dev/null || true
    else
        log "falhou: sem rota válida"
        echo "{\"status\":\"failed\",\"ssid\":\"$SSID\",\"reason\":\"route\",\"ts\":$(date +%s)}" > "$STATE/result.json"
        bash "$BASE/bin/start-ap.sh"
        systemctl start forge-portal.service forge-display.service 2>/dev/null || true
    fi
fi
