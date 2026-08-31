#!/bin/bash
# ForgeOS AP stack — wpa_supplicant mode=2 (RTL8189FTV) + dnsmasq portal + captive NAT
# Idempotent: safe to run repeatedly.
set -u
BASE=/opt/forgeos
STATE=$BASE/state

log() { echo "[$(date '+%H:%M:%S')] [AP] $*"; }

# 0. NetworkManager must not manage wlan0 (appliance mode)
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/forge-unmanaged.conf <<'EOF'
[keyfile]
unmanaged-devices=interface-name:wlan0
EOF
nmcli dev set wlan0 managed no >/dev/null 2>&1 || true

# 1. Driver: kill any client or AP instances, dhclient, and flush IP
pkill -9 hostapd 2>/dev/null || true
pkill -f 'wpa_supplicant.*client.conf' 2>/dev/null || true
pkill -f 'wpa_supplicant.*wpa_ap.conf' 2>/dev/null || true
pkill -f 'dhclient.*wlan0' 2>/dev/null || true
pkill -f 'udhcpc.*wlan0' 2>/dev/null || true
ip link set wlan0 down 2>/dev/null || true
ip addr flush dev wlan0 2>/dev/null || true
rm -f "$STATE/applying" "$STATE/result.json" 2>/dev/null || true

if ! lsmod | grep -q '^8189fs '; then
    modprobe 8189fs rtw_power_mgnt=0 rtw_ips_mode=0 rtw_lps_level=0 2>/dev/null \
      || insmod /lib/modules/$(uname -r)/kernel/drivers/net/wireless/8189fs.ko \
           rtw_power_mgnt=0 rtw_ips_mode=0 rtw_lps_level=0 2>/dev/null || true
fi
sleep 1
ip link set wlan0 up
ip addr add 192.168.4.1/24 dev wlan0

# 2. AP via wpa_supplicant mode=2 (hostapd is broken on this driver)
wpa_supplicant -B -i wlan0 -c "$BASE/network/wpa_ap.conf" \
    -P /run/forge-ap.pid 2>/dev/null
sleep 2

# 3. DHCP/DNS captive portal
pkill -f 'dnsmasq -C /etc/dnsmasq_ap.conf' 2>/dev/null || true
pkill -f 'dnsmasq.*dnsmasq_portal.conf' 2>/dev/null || true
dnsmasq -C "$BASE/network/dnsmasq_portal.conf"

# 4. Routing/NAT: share eth0 uplink if present; force HTTP->portal
sysctl -w net.ipv4.ip_forward=1 >/dev/null
WAN_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -n1)
iptables -t nat -C PREROUTING -i wlan0 -p tcp --dport 80 -j DNAT --to-destination 192.168.4.1:8080 2>/dev/null || \
    iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 -j DNAT --to-destination 192.168.4.1:8080
if [ -n "${WAN_IF:-}" ]; then
    log "uplink detectado em $WAN_IF — habilitando MASQUERADE"
    iptables -t nat -C POSTROUTING -o "$WAN_IF" -j MASQUERADE 2>/dev/null || \
        iptables -t nat -A POSTROUTING -o "$WAN_IF" -j MASQUERADE
    iptables -C FORWARD -i wlan0 -o "$WAN_IF" -j ACCEPT 2>/dev/null || \
        iptables -A FORWARD -i wlan0 -o "$WAN_IF" -j ACCEPT
    iptables -C FORWARD -i "$WAN_IF" -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
        iptables -A FORWARD -i "$WAN_IF" -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
fi

echo '{"mode":"ap","ts":'$(date +%s)'}' > "$STATE/ap_state.json"
log "AP ativo: RTL8189FTV_AP @ 192.168.4.1 (portal :8080)"
