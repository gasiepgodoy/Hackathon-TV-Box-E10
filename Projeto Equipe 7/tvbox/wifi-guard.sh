#!/bin/bash
# Vigia do Wi-Fi interno (rtl8189fs). O rádio cai sozinho e não volta: para o
# NetworkManager a interface segue "conectada", mas nenhum pacote passa — só o
# reboot resolvia. Aqui a recuperação escala do mais barato ao mais caro, para
# não reiniciar a box por um soluço de dois segundos.
set -u

IFACE=${IFACE:-wlan1}
PROFILE=${PROFILE:-wifi-interna}
MODULE=${MODULE:-8189fs}
INTERVAL=20        # segundos entre checagens
FAILS_TO_ACT=3     # falhas seguidas antes de agir (~1 min de queda)
SETTLE=25          # espera depois de cada tentativa, antes de checar de novo
MIN_UPTIME=900     # não reiniciar a box nos primeiros 15 min (evita laço)
LOG=/var/log/wifi-guard.log

log() {
    printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$LOG"
    # O journal desta box é volátil e este script pode causar reboot: o
    # histórico das quedas precisa sobreviver ao reinício. Corta para não
    # crescer sem fim no cartão.
    # Folgado de propósito: cada queda gera ~35 linhas de diagnóstico, e
    # perder episódios antigos é perder justamente a série que queremos ler.
    if [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt 4000 ]; then
        tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
    fi
    return 0
}

link_ok() {
    # O alvo é o gateway, e não a internet, de propósito: se quem caiu foi o
    # provedor, mexer no rádio não resolve nada e ainda derruba o que estava
    # funcionando na rede local.
    ip -4 addr show dev "$IFACE" 2>/dev/null | grep -q 'inet ' || return 1
    local gw
    gw=$(ip route show default dev "$IFACE" 2>/dev/null | awk '{print $3; exit}')
    [ -z "$gw" ] && gw=$(ip route show dev "$IFACE" 2>/dev/null | awk '/via/{print $3; exit}')
    [ -z "$gw" ] && return 1
    ping -I "$IFACE" -c 2 -W 3 "$gw" >/dev/null 2>&1
}

snapshot() {
    # Fotografia do estado no instante da queda, ANTES de mexer em qualquer
    # coisa: a partir do nível 1 o vigia começa a alterar o que quisermos
    # observar, e no nível 3 a recarga do módulo zera o rastro de vez.
    {
        echo "    --- estado no momento da queda ---"
        echo "    [iw]";    iw dev "$IFACE" link 2>&1 | sed 's/^/        /'
        echo "    [nmcli]"; nmcli -t -f DEVICE,STATE,CONNECTION dev status 2>&1 \
                              | grep -E "^$IFACE" | sed 's/^/        /'
        echo "    [addr]";  ip -br addr show dev "$IFACE" 2>&1 | sed 's/^/        /'
        echo "    [rota]";  ip route show dev "$IFACE" 2>&1 | sed 's/^/        /'
        echo "    [sinal]"; grep -E "^ *$IFACE" /proc/net/wireless 2>/dev/null | sed 's/^/        /'
        # Se o chip sumiu do barramento, o problema é o SDIO e não o 802.11 —
        # é a diferença entre "caiu do AP" e "o rádio morreu".
        echo "    [sdio]";  ls /sys/bus/sdio/devices/ 2>&1 | sed 's/^/        /'
        # E se o próprio módulo saiu de cena, o rádio não volta sozinho: um
        # "blacklist 8189fs" em /etc/modprobe.d impede o recarregamento
        # automático por alias, e só o modprobe explícito traz de volta.
        echo "    [modulo]"; lsmod 2>/dev/null | grep -E '^8189fs' | sed 's/^/        /'
        echo "    [netdev]"; ls -d "/sys/class/net/$IFACE" 2>&1 | sed 's/^/        /'
        echo "    [dmesg]"; dmesg | grep -iE 'RTW|8189|mmc2' | tail -20 | sed 's/^/        /'
    } >> "$LOG" 2>&1
    return 0
}

step_reconnect() {
    log "1/4 reconectando o perfil $PROFILE"
    nmcli connection up "$PROFILE" >/dev/null 2>&1
}

step_bounce() {
    log "2/4 derrubando e subindo a $IFACE"
    ip link set "$IFACE" down; sleep 3
    ip link set "$IFACE" up;   sleep 2
    nmcli connection up "$PROFILE" >/dev/null 2>&1
}

step_reload() {
    # Recarregar o módulo é o que de fato ressuscita o rádio quando o SDIO
    # trava. O disconnect antes evita que o rmmod fique preso com a interface
    # em uso pelo NetworkManager.
    log "3/4 recarregando o módulo $MODULE"
    nmcli device disconnect "$IFACE" >/dev/null 2>&1
    sleep 2
    modprobe -r "$MODULE" 2>>"$LOG" || { log "    rmmod falhou (módulo preso)"; return 1; }
    sleep 3
    modprobe "$MODULE"    2>>"$LOG" || { log "    modprobe falhou"; return 1; }
    # o driver leva alguns segundos para recriar a interface
    for _ in $(seq 20); do [ -e "/sys/class/net/$IFACE" ] && break; sleep 1; done
    sleep 3
    nmcli connection up "$PROFILE" >/dev/null 2>&1
}

step_reboot() {
    local up
    up=$(cut -d. -f1 /proc/uptime)
    if [ "$up" -lt "$MIN_UPTIME" ]; then
        log "4/4 reboot adiado: só ${up}s de uptime, seria laço de reinício"
        return 1
    fi
    log "4/4 nada resolveu — reiniciando a box"
    sync
    systemctl reboot
}

notify() {
    # Registra a queda no histórico do app (depois de voltar, naturalmente).
    # Vira um evento comum na tabela events; o flow de push só olha alarme e
    # camera, então isso não gera notificação — é para diagnóstico.
    command -v mosquitto_pub >/dev/null 2>&1 || return 0
    [ -r /opt/secbox/config.json ] && [ -r /opt/secbox/device.json ] || return 0
    python3 - "$1" "$2" <<'PY' 2>>"$LOG"
import json, sys, subprocess
cfg = json.load(open('/opt/secbox/config.json'))
dev = json.load(open('/opt/secbox/device.json'))
body = json.dumps({"type": "wifi_recovered",
                   "level": int(sys.argv[1]), "down_s": int(sys.argv[2])})
subprocess.run(["mosquitto_pub",
                "-h", str(cfg["broker_host"]), "-p", str(cfg["broker_port"]),
                "-u", str(cfg["broker_user"]), "-P", str(cfg["broker_pass"]),
                "-t", f"devices/{dev['device_id']}/rede/event",
                "-m", body, "-q", "1"], timeout=15)
PY
    return 0
}

fails=0
level=0
down_since=0
log "wifi-guard iniciado (iface=$IFACE perfil=$PROFILE modulo=$MODULE)"

while true; do
    if link_ok; then
        if [ "$level" -gt 0 ]; then
            down=$(( $(date +%s) - down_since ))
            log "rede de volta após ${down}s (resolvido no nível $level)"
            notify "$level" "$down"
        fi
        fails=0; level=0; down_since=0
    else
        [ "$down_since" -eq 0 ] && down_since=$(date +%s)
        fails=$((fails + 1))
        # Fotografa na 2ª falha seguida: pula o soluço de uma checagem só e
        # ainda acontece antes de qualquer ação, que começa na 3ª. O teste de
        # level garante uma foto por episódio, e não uma a cada escalada.
        if [ "$fails" -eq 2 ] && [ "$level" -eq 0 ]; then
            log "queda detectada em $IFACE"
            snapshot
        fi
        if [ "$fails" -ge "$FAILS_TO_ACT" ]; then
            level=$((level + 1))
            case "$level" in
                1) step_reconnect ;;
                2) step_bounce ;;
                3) step_reload ;;
                # Se o reboot for adiado por uptime baixo, volta para o nível 2
                # e segue alternando recarga do módulo e nova tentativa de
                # reboot, em vez de desistir.
                *) step_reboot; level=2 ;;
            esac
            fails=0
            sleep "$SETTLE"
            continue
        fi
    fi
    sleep "$INTERVAL"
done
