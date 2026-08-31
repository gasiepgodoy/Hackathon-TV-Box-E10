#!/bin/bash
# Watchdog ForgeOS:
#  1. Rollback: tentativa de cliente travada > 5 min  -> restaura AP
#  2. Guardião do AP: dnsmasq/portal caídos           -> reinicia serviços
BASE=/opt/forgeos
STATE=$BASE/state
FAIL_LIMIT=${FAIL_LIMIT:-20}   # 20 x 15s = 5 min sem internet em modo cliente
fails=0

while true; do
    # --- rollback de provisionamento travado ---
    if [ -f "$STATE/applying" ]; then
        AGE=$(( $(date +%s) - $(stat -c %Y "$STATE/applying" 2>/dev/null || date +%s) ))
        if [ "$AGE" -gt 300 ]; then
            logger -t forge-watchdog "aplicando rollback após ${AGE}s"
            pkill -f 'wpa_supplicant.*client.conf' 2>/dev/null || true
            rm -f "$STATE/applying"
            bash "$BASE/bin/start-ap.sh" >> /var/log/forge-ap.log 2>&1
            systemctl start forge-portal.service forge-display.service 2>/dev/null
        fi
    fi

    # --- guardião do AP (ignora durante provisionamento legítimo) ---
    if [ ! -f "$STATE/applying" ] && ! pgrep -f 'wpa_supplicant.*wpa_ap.conf' >/dev/null 2>&1; then
        RESULT=$(cat "$STATE/result.json" 2>/dev/null || echo '{}')
        if ! echo "$RESULT" | grep -q '"status":"connected"'; then
            logger -t forge-watchdog "AP ausente em modo provisionamento — restaurando"
            bash "$BASE/bin/start-ap.sh" >> /var/log/forge-ap.log 2>&1
            systemctl start forge-portal.service forge-display.service 2>/dev/null
        fi
    fi

    systemctl is-active --quiet forge-portal.service || \
        [ "$(cat "$STATE/ap_state.json" 2>/dev/null | grep -o client)" = "client" ] || \
        systemctl start forge-portal.service 2>/dev/null

    # --- limpa resultado obsoleto (AP ativo + connected = estado pós-boot inválido) ---
    if pgrep -f 'wpa_supplicant.*wpa_ap.conf' >/dev/null 2>&1 && \
       grep -q '"status": *"connected"' "$STATE/result.json" 2>/dev/null && \
       [ ! -f "$STATE/applying" ]; then
        rm -f "$STATE/result.json"
        logger -t forge-watchdog "result.json obsoleto pós-boot limpo"
    fi

    # --- fallback: em modo cliente sem internet por FAIL_LIMIT ciclos -> AP ---
    if grep -q '"status": *"connected"' "$STATE/result.json" 2>/dev/null; then
        if ping -c 1 -W 3 -I wlan0 1.1.1.1 >/dev/null 2>&1; then
            fails=0
        else
            fails=$((fails + 1))
            if [ "$fails" -ge "$FAIL_LIMIT" ]; then
                logger -t forge-watchdog "sem internet via wlan0 por $((FAIL_LIMIT * 15))s — voltando ao AP"
                fails=0
                pkill -f 'wpa_supplicant.*client.conf' 2>/dev/null || true
                rm -f "$STATE/result.json"
                bash "$BASE/bin/start-ap.sh" >> /var/log/forge-ap.log 2>&1
                systemctl start forge-portal.service forge-display.service 2>/dev/null
            fi
        fi
    else
        fails=0
    fi

    sleep 15
done
