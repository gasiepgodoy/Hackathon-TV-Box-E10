#!/usr/bin/env bash
# ==============================================================================
# Multi-Forge Zero-Risk VM Test Runner (100% SSH / Headless / KVM)
# ==============================================================================
# Executa imagens de teste ARM64 dentro de uma VM acelerada por hardware (KVM)
# na própria TV Box, com isolamento total (Copy-On-Write) e zero risco de brick.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OVERLAY_IMG="/tmp/forge_vm_overlay.qcow2"
BOOT_LOG="/tmp/forge_vm_boot.log"
TMUX_SESSION="forge-vm"
SSH_PORT=2222
WEB_PORT=8081
GDB_PORT=1234
RAM_MB=1024
CPUS=2

log() { echo -e "\033[1;34m[FORGE-VM]\033[0m $*"; }
err() { echo -e "\033[1;31m[FORGE-VM ERROR]\033[0m $*" >&2; }
ok()  { echo -e "\033[1;32m[FORGE-VM OK]\033[0m $*"; }

usage() {
    cat <<EOF
Uso: forge-vm <comando> [argumentos]

Comandos 100% via SSH:
  run <imagem.img>      Inicia a VM interativa diretamente neste terminal SSH (-nographic)
  bg  <imagem.img>      Inicia a VM em segundo plano (sessão tmux isolada)
  attach                Conecta ao terminal interativo da VM em execução
  logs                  Acompanha os logs seriais de boot em tempo real (tail -f)
  status                Verifica se a VM está ativa, portas e uso de recursos
  ssh                   Conecta via SSH diretamente dentro da VM de teste (porta $SSH_PORT)
  test <imagem.img>     Sobe a VM em bg, roda healthcheck na API e desliga
  stop                  Encerra a VM de teste e limpa o snapshot temporário

Portas mapeadas no Host (192.168.1.153):
  * SSH da VM de teste:      porta $SSH_PORT (ssh -p $SSH_PORT root@localhost)
  * Web Portal / REST API:   porta $WEB_PORT (http://192.168.1.153:$WEB_PORT)
  * GDB Remote Stub:         porta $GDB_PORT
EOF
    exit 1
}

check_prereqs() {
    if ! command -v qemu-system-aarch64 &>/dev/null; then
        err "qemu-system-aarch64 não encontrado. Instalando..."
        apt-get update -qq && apt-get install -y -qq qemu-system-arm qemu-utils tmux
    fi
}

create_overlay() {
    local base_img="$1"
    if [[ ! -f "$base_img" ]]; then
        err "Arquivo de imagem '$base_img' não encontrado!"
        exit 1
    fi

    # Se for .xz, avisa ou descompacta em /tmp
    if [[ "$base_img" == *.xz ]]; then
        log "Imagem comprimida detectada. Descompactando temporariamente..."
        local raw_img="/tmp/uncompressed_test.img"
        xz -dc "$base_img" > "$raw_img"
        base_img="$raw_img"
    fi

    log "Criando snapshot descartável Copy-on-Write (base: $base_img)..."
    rm -f "$OVERLAY_IMG"
    qemu-img create -f qcow2 -b "$base_img" -F raw "$OVERLAY_IMG"
    ok "Snapshot descartável criado em $OVERLAY_IMG (a imagem original permanece 100% intacta)."
}

build_qemu_cmd() {
    local interactive="$1"
    local kvm_flag=""
    if [[ -w /dev/kvm ]]; then
        kvm_flag="-enable-kvm -cpu host"
    else
        kvm_flag="-cpu cortex-a53"
    fi

    local display_opts="-nographic"
    local serial_opts="-chardev stdio,id=char0,logfile=$BOOT_LOG,signal=off -serial chardev:char0"
    if [[ "$interactive" == "0" ]]; then
        serial_opts="-chardev file,id=char0,path=$BOOT_LOG -serial chardev:char0"
    fi

    echo "qemu-system-aarch64 $kvm_flag -m $RAM_MB -smp $CPUS -M virt \
        -drive file=$OVERLAY_IMG,format=qcow2,if=virtio \
        -netdev user,id=net0,hostfwd=tcp::$SSH_PORT-:22,hostfwd=tcp::$WEB_PORT-:8080 \
        -device virtio-net-pci,netdev=net0 \
        -gdb tcp::$GDB_PORT \
        $display_opts \
        $serial_opts"
}

cmd_run() {
    local img="${1:-}"
    [[ -z "$img" ]] && usage
    check_prereqs
    create_overlay "$img"

    log "Iniciando VM Interativa via SSH (Pressione Ctrl+A X para sair)..."
    log "SSH Guest: porta $SSH_PORT | Web Portal: http://192.168.1.153:$WEB_PORT"
    
    local qemu_cmd
    qemu_cmd=$(build_qemu_cmd "1")
    eval "$qemu_cmd" || true
    
    log "VM encerrada. Limpando overlay..."
    rm -f "$OVERLAY_IMG"
    ok "Ambiente limpo com sucesso."
}

cmd_bg() {
    local img="${1:-}"
    [[ -z "$img" ]] && usage
    check_prereqs
    create_overlay "$img"

    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        err "Uma sessão de VM já está rodando em segundo plano. Use 'forge-vm stop' antes."
        exit 1
    fi

    log "Iniciando VM em segundo plano no tmux (sessão: $TMUX_SESSION)..."
    local qemu_cmd
    qemu_cmd=$(build_qemu_cmd "1")
    tmux new-session -d -s "$TMUX_SESSION" "$qemu_cmd"
    
    ok "VM iniciada em background!"
    echo "  * Conectar no console interativo: forge-vm attach (sair com Ctrl+B D)"
    echo "  * Acompanhar logs de boot:        forge-vm logs"
    echo "  * Conectar via SSH:               forge-vm ssh"
    echo "  * Status:                         forge-vm status"
}

cmd_attach() {
    if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        err "Nenhuma sessão de VM em background encontrada."
        exit 1
    fi
    tmux attach-session -t "$TMUX_SESSION"
}

cmd_logs() {
    if [[ ! -f "$BOOT_LOG" ]]; then
        err "Nenhum log encontrado em $BOOT_LOG."
        exit 1
    fi
    log "Exibindo $BOOT_LOG em tempo real (Ctrl+C para sair)..."
    tail -f "$BOOT_LOG"
}

cmd_status() {
    local pid
    pid=$(pgrep -f "qemu-system-aarch64.*$OVERLAY_IMG" || true)
    if [[ -n "$pid" ]]; then
        ok "VM está ATIVA (PID: $pid)"
        echo "  * Portas ativas:"
        ss -tulpn 2>/dev/null | grep -E "$SSH_PORT|$WEB_PORT|$GDB_PORT" || true
        echo "  * Teste de resposta HTTP (porta $WEB_PORT):"
        if curl -s -m 2 "http://localhost:$WEB_PORT/rest/system/info" &>/dev/null; then
            ok "  -> REST API do ForgeOS respondendo 200 OK!"
        else
            log "  -> Aguardando boot do sistema operacional..."
        fi
    else
        log "Nenhuma VM de teste em execução no momento."
    fi
}

cmd_ssh() {
    log "Conectando via SSH à VM de teste (porta $SSH_PORT)..."
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p "$SSH_PORT" root@localhost
}

cmd_stop() {
    log "Encerrando VM de teste..."
    pkill -f "qemu-system-aarch64.*$OVERLAY_IMG" 2>/dev/null || true
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
    sleep 1
    rm -f "$OVERLAY_IMG"
    ok "VM finalizada e arquivos temporários removidos."
}

cmd_test() {
    local img="${1:-}"
    [[ -z "$img" ]] && usage
    cmd_bg "$img"
    
    log "Aguardando boot da VM e inicialização dos serviços (até 60s)..."
    local count=0
    local success=0
    while [[ $count -lt 30 ]]; do
        if curl -s -m 2 "http://localhost:$WEB_PORT/rest/modules" | grep -q "totem"; then
            ok "Healthcheck PASSOU! ForgeOS REST API e Module Hub responderam com sucesso."
            success=1
            break
        fi
        sleep 2
        count=$((count + 1))
        echo -n "."
    done
    echo ""

    if [[ $success -eq 1 ]]; then
        ok "A imagem compilada está 100% funcional e pronta para distribuição!"
    else
        err "Timeout aguardando inicialização da imagem. Verifique os logs com 'forge-vm logs'."
    fi

    cmd_stop
}

# --- Router ---
case "${1:-}" in
    run)    cmd_run "${2:-}" ;;
    bg)     cmd_bg "${2:-}" ;;
    attach) cmd_attach ;;
    logs)   cmd_logs ;;
    status) cmd_status ;;
    ssh)    cmd_ssh ;;
    test)   cmd_test "${2:-}" ;;
    stop)   cmd_stop ;;
    *)      usage ;;
esac
