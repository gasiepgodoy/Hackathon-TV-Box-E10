#!/usr/bin/env bash
# ==============================================================================
# MultiForge — ForgeOS Distro Builder for BTV Express E10 (Amlogic S905X2)
# ==============================================================================
# Pipeline de compilação e empacotamento de imagem oficial bootável (.img.xz)
# Inclui: DTB Enterprise (25MHz RTL8189FTV + 64MB CMA), Provisioning Stack On-Boot,
# Sysctl & ZRAM Performance Tweaks, Framebuffer QR Screen e Captive Portal HTTP.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORK_DIR="/tmp/forgeos_distro_build"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/distro_output}"
DISTRO_NAME="ForgeOS_BTV_E10_v1.1.0"
BASE_IMG_URL="https://github.com/ophub/amlogic-s9xxx-armbian/releases/download/Armbian_trixie_arm64_server_2026.08/Armbian_26.08.0_amlogic_s905x2_trixie_6.18.44_server_2026.08.15.img.gz"

log() { echo -e "\033[1;34m[BUILDER]\033[0m $*"; }
ok()  { echo -e "\033[1;32m[BUILDER OK]\033[0m $*"; }
err() { echo -e "\033[1;31m[BUILDER ERROR]\033[0m $*" >&2; }

# Otimizações de Compilação & Hardware
NPROC=$(nproc)
export CCACHE_DIR=/root/.ccache
export USE_CCACHE=1
export MAKEFLAGS="-j$NPROC"

mkdir -p "$WORK_DIR" "$OUTPUT_DIR"

# Se houver mais de 12GB de RAM, monta WORK_DIR em RAM-Disk (tmpfs) com 0ms I/O latency
FREE_RAM_MB=$(free -m | awk '/^Mem:/{print $2}' 2>/dev/null || echo 0)
if [ "$FREE_RAM_MB" -gt 12000 ]; then
    log "RAM Total Alta ($FREE_RAM_MB MB detectada). Montando WORK_DIR em RAM-Disk (tmpfs 16GB) para I/O instantâneo..."
    mount -t tmpfs -o size=16G tmpfs "$WORK_DIR" 2>/dev/null || true
fi

cd "$WORK_DIR"

log "1. Instalando dependências de empacotamento & ferramentas paralelas ($NPROC vCPUs)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    qemu-user-static binfmt-support util-linux parted dosfstools \
    e2fsprogs xz-utils curl wget ca-certificates gzip pigz pixz ccache zstd pv device-tree-compiler

log "2. Obtendo imagem base minimal Armbian S905X2..."
BASE_IMG_GZ="$WORK_DIR/base_image.img.gz"
RAW_IMG="$WORK_DIR/${DISTRO_NAME}.img"

if [[ ! -f "$BASE_IMG_GZ" && ! -f "$RAW_IMG" ]]; then
    log "Baixando base image Armbian Trixie G12A..."
    if ! curl -fsSL -m 180 "$BASE_IMG_URL" -o "$BASE_IMG_GZ"; then
        log "URL direta indisponível, buscando release mais recente do Ophub..."
        LATEST_URL=$(curl -fsSL https://api.github.com/repos/ophub/amlogic-s9xxx-armbian/releases/latest | grep "browser_download_url.*s905x2.*\.img\.gz" | head -n 1 | cut -d '"' -f 4 || true)
        if [[ -n "$LATEST_URL" ]]; then
            curl -fsSL "$LATEST_URL" -o "$BASE_IMG_GZ"
        else
            err "Falha ao obter imagem base do Amlogic S905X2."
            exit 1
        fi
    fi
fi

if [[ -f "$BASE_IMG_GZ" && ! -f "$RAW_IMG" ]]; then
    log "Descompactando imagem base com pigz paralelo ($NPROC threads)..."
    pigz -dc "$BASE_IMG_GZ" > "$RAW_IMG" || gzip -dc "$BASE_IMG_GZ" > "$RAW_IMG"
fi

log "3. Configurando loop devices e partições..."
LOOP_DEV=$(losetup -Pf --show "$RAW_IMG")
log "Loop device mapeado: $LOOP_DEV"

BOOT_PART="${LOOP_DEV}p1"
ROOT_PART="${LOOP_DEV}p2"

MOUNT_ROOT="$WORK_DIR/mnt_root"
MOUNT_BOOT="$WORK_DIR/mnt_boot"
mkdir -p "$MOUNT_ROOT" "$MOUNT_BOOT"

mount "$ROOT_PART" "$MOUNT_ROOT"
mount "$BOOT_PART" "$MOUNT_ROOT/boot" || mount "$BOOT_PART" "$MOUNT_BOOT"

ROOT_UUID=$(blkid -s UUID -o value "$ROOT_PART")
log "Rootfs UUID: $ROOT_UUID"

log "4. Injetando DTB Enterprise BTV E10 no /boot/dtb/amlogic/..."
DTB_SRC="$REPO_ROOT/ForgeDB/devices/btv/e10/dtb/meson-g12a-btv-e10-enterprise.dtb"
if [[ ! -f "$DTB_SRC" ]]; then
    err "DTB Enterprise não encontrado em $DTB_SRC! Compilando do DTS..."
    dtc -I dts -O dtb "$REPO_ROOT/ForgeDB/devices/btv/e10/dtb/meson-g12a-btv-e10-enterprise.dts" -o "$DTB_SRC"
fi

mkdir -p "$MOUNT_ROOT/boot/dtb/amlogic"
cp -f "$DTB_SRC" "$MOUNT_ROOT/boot/dtb/amlogic/meson-g12a-btv-e10-enterprise.dtb"
cp -f "$DTB_SRC" "$MOUNT_ROOT/boot/dtb/amlogic/meson-g12a-sei510.dtb"

log "5. Configurando Bootloader uEnv.txt com parâmetros de vídeo e DTB Enterprise..."
cat <<EOF > "$MOUNT_ROOT/boot/uEnv.txt"
LINUX=/zImage
INITRD=/uInitrd
FDT=/dtb/amlogic/meson-g12a-btv-e10-enterprise.dtb
APPEND=root=UUID=${ROOT_UUID} rootflags=data=writeback rw rootwait rootfstype=ext4 console=ttyAML0,115200n8 console=tty0 no_console_suspend consoleblank=0 fsck.fix=yes fsck.repair=yes net.ifnames=0 max_loop=128 cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory swapaccount=1 video=HDMI-A-1:1920x1080@60e plymouth.enable=0
EOF

log "6. Injetando Stack de Provisionamento ForgeOS em /opt/forgeos/..."
mkdir -p "$MOUNT_ROOT/opt/forgeos"/{bin,network,web,display,state,tests}
cp -r "$REPO_ROOT/ForgeOS/bin/."        "$MOUNT_ROOT/opt/forgeos/bin/"
cp -r "$REPO_ROOT/ForgeOS/network/."    "$MOUNT_ROOT/opt/forgeos/network/"
cp -r "$REPO_ROOT/ForgeOS/web/."        "$MOUNT_ROOT/opt/forgeos/web/"
cp -r "$REPO_ROOT/ForgeOS/display/."    "$MOUNT_ROOT/opt/forgeos/display/"
cp -r "$REPO_ROOT/ForgeOS/tests/."      "$MOUNT_ROOT/opt/forgeos/tests/"
cp -r "$REPO_ROOT/ForgeOS/systemd/."    "$MOUNT_ROOT/etc/systemd/system/"

chmod +x "$MOUNT_ROOT"/opt/forgeos/bin/*.sh \
         "$MOUNT_ROOT"/opt/forgeos/network/*.py \
         "$MOUNT_ROOT"/opt/forgeos/display/*.py \
         "$MOUNT_ROOT"/opt/forgeos/web/server.py 2>/dev/null || true

log "7. Injetando otimizações de Sysctl, ZRAM e Módulo RTL8189FTV..."
cp -f "$SCRIPT_DIR/config/sysctl-performance.conf" "$MOUNT_ROOT/etc/sysctl.d/99-forgeos-performance.conf"
cp -f "$SCRIPT_DIR/config/8189fs-performance.conf" "$MOUNT_ROOT/etc/modprobe.d/8189fs.conf"

# Configura ZRAM 50% de RAM compactado com ZSTD
cat <<EOF > "$MOUNT_ROOT/etc/default/zramswap"
ALGO=zstd
PERCENT=50
PRIORITY=100
EOF

log "8. Executando customização via Chroot ARM64 (QEMU User Static)..."
cp /usr/bin/qemu-aarch64-static "$MOUNT_ROOT/usr/bin/" 2>/dev/null || true

chroot "$MOUNT_ROOT" /bin/bash -c "
    export DEBIAN_FRONTEND=noninteractive
    
    # Habilita os serviços do ForgeOS e SSH no boot
    systemctl daemon-reload 2>/dev/null || true
    systemctl enable forge-ap.service forge-portal.service forge-display.service forge-watchdog.service forge-fbcon-disable.service ssh sshd 2>/dev/null || true
    
    # Configura SSH com PermitRootLogin ativo
    mkdir -p /etc/ssh /etc/ssh/sshd_config.d
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config 2>/dev/null || true
    echo 'PermitRootLogin yes' > /etc/ssh/sshd_config.d/01-root-login.conf 2>/dev/null || true
    
    # Desativa serviços conflitantes de rede comercial
    systemctl disable NetworkManager wpa_supplicant hostapd 2>/dev/null || true
    
    # Define hostname oficial
    echo 'forgeos-btv' > /etc/hostname
    sed -i 's/127.0.1.1.*/127.0.1.1\tforgeos-btv/' /etc/hosts 2>/dev/null || true
    
    # Define senhas padrão 'forge' para root e kali
    echo 'root:forge' | chpasswd 2>/dev/null || true
    echo 'kali:forge' | chpasswd 2>/dev/null || true
    
    # Limpa caches de pacotes e logs
    apt-get clean 2>/dev/null || true
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /var/log/*.log
"

rm -f "$MOUNT_ROOT/usr/bin/qemu-aarch64-static"

log "9. Desmontando e verificando integridade do filesystem..."
umount "$MOUNT_ROOT/boot" 2>/dev/null || umount "$MOUNT_BOOT" 2>/dev/null || true
umount "$MOUNT_ROOT"
losetup -d "$LOOP_DEV"

e2fsck -fy "$ROOT_PART" 2>/dev/null || true

log "10. Comprimindo imagem com XZ multi-core (-T0 / -T32)..."
FINAL_XZ="$OUTPUT_DIR/${DISTRO_NAME}.img.xz"
rm -f "$FINAL_XZ"
xz -T0 -9 -c "$RAW_IMG" > "$FINAL_XZ"

log "11. Gerando SHA256 Checksum..."
cd "$OUTPUT_DIR"
sha256sum "$(basename "$FINAL_XZ")" > "${FINAL_XZ}.sha256"

ok "===================================================================="
ok "Build Concluído com Sucesso!"
ok "Arquivo da Distro: $FINAL_XZ"
ok "SHA256:            ${FINAL_XZ}.sha256"
ok "===================================================================="
