#!/bin/bash
# Vigia do Wi-Fi interno (rtl8189fs).
#
# O que acontece nesta instalação: a box fica na borda da cobertura (~-70 dBm)
# de dois APs do mesmo SSID que estão em sub-redes diferentes. Ao trocar de AP,
# a associação continua de pé mas o IP passa a pertencer à sub-rede do AP
# anterior — endereço inválido, rota morta, nada passa. O conserto certo é
# reativar o perfil, que força concessão DHCP nova.
#
# Daí o formato da escada: insiste no barato (reconectar) antes de qualquer
# coisa destrutiva. Recarregar o módulo sorteia MAC novo e recria as duas vifs,
# e no histórico foi seguido de outra queda em ~45 s — é remédio pior que a
# doença aqui, e por isso ficou lá atrás na fila.
set -u

IFACE=${IFACE:-wlan1}
PROFILE=${PROFILE:-wifi-interna}
MODULE=${MODULE:-8189fs}
INTERVAL=10        # segundos entre checagens
FAILS_TO_ACT=3     # falhas seguidas antes de agir (~30 s de queda)
SETTLE=20          # espera depois de cada tentativa, antes de checar de novo
MIN_UPTIME=900     # não reiniciar a box nos primeiros 15 min (evita laço)
MIN_EPISODE=600    # nem por uma queda que ainda não passou de 10 min
LOG=/var/log/wifi-guard.log

log() {
    printf '%s %s\n' "$(date '+%F %T')" "$*" >> "$LOG"
    # O journal desta box é volátil e este script pode causar reboot: o
    # histórico das quedas precisa sobreviver ao reinício. Corta para não
    # crescer sem fim no cartão.
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

brief() {
    # Uma linha por queda. Com quedas frequentes, despejar o diagnóstico
    # completo toda vez afogaria o log justamente na série temporal que
    # queremos ler. Estes quatro campos já separam os casos: BSSID diferente do
    # anterior = roaming; sem ip/rota com BSSID igual = concessão perdida;
    # sem BSSID = desassociou de vez.
    local bssid sig ip gw
    bssid=$(iw dev "$IFACE" link 2>/dev/null | awk '/Connected to/{print $3}')
    sig=$(iw dev "$IFACE" link 2>/dev/null | awk '/signal:/{print $2$3}')
    ip=$(ip -4 -br addr show dev "$IFACE" 2>/dev/null | awk '{print $3}')
    gw=$(ip route show default dev "$IFACE" 2>/dev/null | awk '{print $3; exit}')
    log "queda: bssid=${bssid:-nenhum} sinal=${sig:-?} ip=${ip:-nenhum} rota=${gw:-nenhuma}"
}

snapshot() {
    # Diagnóstico completo, só quando o barato não resolveu — aí sim é um caso
    # diferente do de sempre e vale o custo em linhas de log.
    {
        echo "    --- reconectar não resolveu, estado completo ---"
        echo "    [iw]";    iw dev "$IFACE" link 2>&1 | sed 's/^/        /'
        echo "    [nmcli]"; nmcli -t -f DEVICE,STATE,CONNECTION dev status 2>&1 \
                              | grep -E "^$IFACE" | sed 's/^/        /'
        echo "    [addr]";  ip -br addr show dev "$IFACE" 2>&1 | sed 's/^/        /'
        echo "    [rota]";  ip route show dev "$IFACE" 2>&1 | sed 's/^/        /'
        echo "    [sinal]"; grep -E "^ *$IFACE" /proc/net/wireless 2>/dev/null | sed 's/^/        /'
        # Se o chip sumiu do barramento, o problema é o SDIO e não o 802.11 —
        # é a diferença entre "caiu do AP" e "o rádio morreu".
        echo "    [sdio]";  ls /sys/bus/sdio/devices/ 2>&1 | sed 's/^/        /'
        echo "    [modulo]"; lsmod 2>/dev/null | grep -E '^8189fs' | sed 's/^/        /'
        echo "    [netdev]"; ls -d "/sys/class/net/$IFACE" 2>&1 | sed 's/^/        /'
        echo "    [dmesg]"; dmesg | grep -iE 'RTW|8189|mmc2' | tail -20 | sed 's/^/        /'
    } >> "$LOG" 2>&1
    return 0
}

step_reconnect() {
    # O conserto certo para o caso comum: reativar o perfil força DHCP novo e
    # devolve endereço e rota coerentes com o AP em que a box está agora.
    log "  reconectando o perfil $PROFILE"
    nmcli connection up "$PROFILE" >/dev/null 2>&1
}

step_bounce() {
    log "  derrubando e subindo a $IFACE"
    ip link set "$IFACE" down; sleep 3
    ip link set "$IFACE" up;   sleep 2
    nmcli connection up "$PROFILE" >/dev/null 2>&1
}

step_reload() {
    # Último recurso antes do reboot. Recria as duas vifs e sorteia MAC novo
    # (o efuse não tem MAC gravado), então só entra quando nada mais resolveu.
    log "  recarregando o módulo $MODULE"
    nmcli device disconnect "$IFACE" >/dev/null 2>&1
    sleep 2
    modprobe -r "$MODULE" 2>>"$LOG" || { log "    rmmod falhou (módulo preso)"; return 1; }
    sleep 3
    modprobe "$MODULE"    2>>"$LOG" || { log "    modprobe falhou"; return 1; }
    for _ in $(seq 20); do [ -e "/sys/class/net/$IFACE" ] && break; sleep 1; done
    sleep 3
    nmcli connection up "$PROFILE" >/dev/null 2>&1
}

step_reboot() {
    local up ep
    up=$(cut -d. -f1 /proc/uptime)
    ep=$(( $(date +%s) - down_since ))
    if [ "$up" -lt "$MIN_UPTIME" ]; then
        log "  reboot adiado: só ${up}s de uptime, seria laço de reinício"
        return 1
    fi
    # A box grava vídeo o tempo todo: reiniciar corta a gravação e custa mais
    # que ficar alguns minutos sem rede. Só vale se a queda já for longa.
    if [ "$ep" -lt "$MIN_EPISODE" ]; then
        log "  reboot adiado: queda com ${ep}s, ainda pode voltar sozinha"
        return 1
    fi
    log "  nada resolveu em ${ep}s — reiniciando a box"
    sync
    systemctl reboot
}

notify() {
    # Registra no histórico do app. Com queda a cada poucos minutos, publicar
    # todas afogaria os eventos que importam (movimento, câmera offline) — daí
    # só as demoradas ou as que precisaram de mais que reconectar.
    [ "$1" -ge 4 ] || [ "$2" -ge 120 ] || return 0
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
            log "rede de volta após ${down}s (nível $level)"
            notify "$level" "$down"
        fi
        fails=0; level=0; down_since=0
    else
        [ "$down_since" -eq 0 ] && down_since=$(date +%s)
        fails=$((fails + 1))
        # Anota na 2ª falha seguida: pula o soluço de uma checagem só e ainda
        # acontece antes de qualquer ação, que começa na 3ª.
        if [ "$fails" -eq 2 ] && [ "$level" -eq 0 ]; then
            brief
        fi
        if [ "$fails" -ge "$FAILS_TO_ACT" ]; then
            level=$((level + 1))
            case "$level" in
                1|2|3) step_reconnect ;;
                4)     snapshot; step_bounce ;;
                5)     step_reconnect ;;
                6)     step_reload ;;
                # Se o reboot for adiado, volta para o 5 e segue alternando
                # reconectar / recarregar / tentar de novo, em vez de desistir.
                *)     step_reboot; level=5 ;;
            esac
            fails=0
            sleep "$SETTLE"
            continue
        fi
    fi
    sleep "$INTERVAL"
done
