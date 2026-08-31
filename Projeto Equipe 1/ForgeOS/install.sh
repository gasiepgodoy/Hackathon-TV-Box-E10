#!/bin/bash
# ForgeOS Provisioner — instalador na BTV E10 (Armbian)
set -e
BASE_SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/forgeos

echo "[INSTALL] garantindo dependências..."
command -v dhclient >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq isc-dhcp-client
command -v qrencode >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qrencode
dpkg -s python3-pil >/dev/null 2>&1 || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-pil

echo "[INSTALL] ForgeOS Provisioner → $DEST"

systemctl stop forge-portal.service forge-display.service 2>/dev/null || true

mkdir -p "$DEST"/{bin,network,web/static/css,display,state,tests} /var/log
cp -r "$BASE_SRC/bin/."        "$DEST/bin/"
cp -r "$BASE_SRC/network/."    "$DEST/network/"
cp -r "$BASE_SRC/web/."        "$DEST/web/"
cp -r "$BASE_SRC/display/."    "$DEST/display/"
cp -r "$BASE_SRC/tests/."      "$DEST/tests/"
cp -r "$BASE_SRC/systemd/."    /etc/systemd/system/
chmod +x "$DEST"/bin/*.sh "$DEST"/network/*.py "$DEST"/display/*.py "$DEST"/web/server.py "$DEST"/tests/*.sh

# Neutraliza autostart antigo que briga pelo rádio (hostapd/NM)
if grep -q 'start_wifi_ap.sh' /etc/rc.local 2>/dev/null; then
    sed -i 's|^\(.*start_wifi_ap.sh.*\)$|#& # disabled by ForgeOS|' /etc/rc.local
    echo "[INSTALL] rc.local: start_wifi_ap.sh desativado"
fi
crontab -l 2>/dev/null | sed 's|^\(.*start_wifi_ap.sh.*\)$|# \1 # disabled by ForgeOS|' | crontab - || true

# Console não pode escrever no framebuffer (kiosk)
systemctl enable forge-fbcon-disable.service >/dev/null 2>&1 || true

systemctl daemon-reload
systemctl enable --now forge-ap.service forge-portal.service forge-display.service forge-watchdog.service

sleep 4
if curl -fsS http://127.0.0.1:8080/api/status >/dev/null 2>&1; then
    echo "[INSTALL] OK — portal respondendo em :8080"
else
    echo "[INSTALL] AVISO: portal ainda não respondeu (ver journalctl -u forge-portal)"
fi
echo "[INSTALL] concluído"
