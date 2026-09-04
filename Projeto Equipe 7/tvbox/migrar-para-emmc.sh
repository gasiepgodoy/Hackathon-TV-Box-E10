#!/bin/bash
# FASE 1 da migração: copia o sistema do cartão SD para a eMMC interna.
#
# Motivo da migração: a box grava vídeo o tempo todo, e escrita contínua é o
# que mata cartão SD — um já morreu neste projeto. Levando o sistema para a
# eMMC e deixando o cartão só com a gravação, o componente que sofre desgaste
# passa a ser o descartável, e a morte dele deixa de derrubar a box.
#
# ESTE SCRIPT NÃO TOCA NO CARTÃO. Ao terminar, o cartão continua intacto e
# bootável. O teste de boot pela eMMC (fase 2) é feito removendo o cartão
# fisicamente — e se a eMMC não subir, basta recolocá-lo e tudo volta ao que
# era. É isso que torna a operação aceitável: até a fase 3, o desfazer é
# encaixar o cartão de volta.
#
# Por que não precisa mexer em bootloader: o bootscript desta box deriva a raiz
# do dispositivo em que ele mesmo arrancou —
#     test "${devtype}" = 'mmc' && setenv root /dev/mmcblk${devnum}p2
# — então, arrancando da eMMC, ele monta mmcblk1p2 sozinho. E o kernel a
# carregar vem de release= no boot.config, que é copiado junto.
set -u

SD_ROOT=/dev/mmcblk0p2
EMMC_ROOT=/dev/mmcblk1p2
EMMC_BOOT=/dev/mmcblk1p1
EMMC_ROOT_UUID=4a37d879-536b-4a8b-9c75-99d739f36437
EMMC_BOOT_UUID=B607-3DAC

MR=/mnt/migra-root
MB=/mnt/migra-boot
SERVICOS="mediamtx secbox-motion secbox-clip"

limpar() {
    umount "$MB" 2>/dev/null
    umount "$MR" 2>/dev/null
    rmdir "$MB" "$MR" 2>/dev/null
    return 0
}
falhar() { echo "ERRO: $*" >&2; limpar; systemctl start $SERVICOS 2>/dev/null; exit 1; }

echo "== travas de segurança =="
[ "$(id -u)" = 0 ] || falhar "precisa ser root"
raiz=$(findmnt -n -o SOURCE /)
[ "$raiz" = "$SD_ROOT" ] || falhar "a raiz é $raiz, esperava $SD_ROOT — este script só roda a partir do cartão"
[ "$(cat /sys/block/mmcblk1/device/type 2>/dev/null)" = "MMC" ] \
    || falhar "mmcblk1 não se identifica como eMMC — recusando por segurança"
[ -b "$EMMC_ROOT" ] || falhar "$EMMC_ROOT não existe"
[ -b "$EMMC_BOOT" ] || falhar "$EMMC_BOOT não existe"
echo "  origem:  $raiz (cartão SD)"
echo "  destino: $EMMC_ROOT (eMMC interna)"

# Cabe? Mede o que vai ser copiado antes de apagar qualquer coisa.
echo "== conferindo espaço =="
usado_kb=$(df -k --output=used / | tail -1 | tr -dc '0-9')
rec_kb=$(du -sk /opt/mediamtx/rec 2>/dev/null | cut -f1); rec_kb=${rec_kb:-0}
cache_kb=$(du -sk /opt/secbox-clip/cache 2>/dev/null | cut -f1); cache_kb=${cache_kb:-0}
precisa_kb=$(( usado_kb - rec_kb - cache_kb ))
# blockdev e não df: a partição está DESMONTADA, e o df sobre o caminho de um
# dispositivo responde sobre o sistema de arquivos que contém /dev — mediu 781 MB
# de devtmpfs e reprovou uma cópia que cabia.
destino_kb=$(( $(blockdev --getsize64 "$EMMC_ROOT") / 1024 ))
echo "  sistema a copiar: $(( precisa_kb / 1024 )) MB (excluindo gravação e cache)"
echo "  partição destino: $(( destino_kb / 1024 )) MB"
[ "$precisa_kb" -lt "$(( destino_kb * 85 / 100 ))" ] \
    || falhar "não cabe com folga: $(( precisa_kb / 1024 ))MB para $(( destino_kb / 1024 ))MB"

echo "== parando os serviços que escrevem =="
systemctl stop $SERVICOS
sleep 2
sync

echo "== montando a eMMC =="
mkdir -p "$MR" "$MB"
mount "$EMMC_ROOT" "$MR" || falhar "não montou $EMMC_ROOT"
mount "$EMMC_BOOT" "$MB" || falhar "não montou $EMMC_BOOT"
# Confere ANTES de apagar: um mount que falhou em silêncio apagaria a raiz viva.
[ "$(findmnt -n -o SOURCE "$MR")" = "$EMMC_ROOT" ] || falhar "montagem inesperada em $MR"
[ "$(findmnt -n -o SOURCE "$MB")" = "$EMMC_BOOT" ] || falhar "montagem inesperada em $MB"

echo "== limpando o Debian antigo da eMMC =="
find "$MR" -mindepth 1 -maxdepth 1 ! -name 'lost+found' -exec rm -rf {} + \
    || falhar "não consegui limpar $MR"

echo "== copiando o sistema (leva alguns minutos) =="
# --one-file-system dispensa excluir /proc, /sys, /dev, /run, /tmp e /boot:
# todos são montagens separadas e o tar não desce neles. Restam as duas
# exclusões que importam — gravação e cache vão para o cartão na fase 3.
tar -C / --one-file-system -S --xattrs -cf - \
    --exclude=./opt/mediamtx/rec \
    --exclude=./opt/secbox-clip/cache \
    . 2>/dev/null | tar -C "$MR" --xattrs -xf - || falhar "a cópia falhou"

echo "== recriando os pontos de montagem =="
mkdir -p "$MR"/{proc,sys,dev,run,mnt,boot} \
         "$MR"/opt/mediamtx/rec "$MR"/opt/secbox-clip/cache "$MR"/tmp
chmod 1777 "$MR/tmp"

echo "== escrevendo o fstab da eMMC =="
cat > "$MR/etc/fstab" <<FSTAB
# Sistema na eMMC interna (mmcblk1). Por UUID e não por LABEL de propósito: o
# cartão e a eMMC têm rótulos idênticos (BOOT/ROOTFS), e por rótulo a montagem
# seria ambígua — poderia calhar de montar o dispositivo errado.
UUID=$EMMC_ROOT_UUID  /      ext4   defaults,noatime,nodiratime,commit=180,errors=remount-ro  0  1
UUID=$EMMC_BOOT_UUID  /boot  vfat   nosuid,nodev,noexec,nofail,gid=0,uid=0,umask=177          0  2
proc                  /proc  proc   defaults                                                  0  0
tmpfs                 /tmp   tmpfs  defaults,nosuid,nodev                                     0  0
# A montagem do cartão (gravação + cache) entra na fase 3, e sempre com nofail:
# cartão morto não pode impedir a box de dar boot — esse é o motivo da migração.
FSTAB

echo "== copiando o /boot (kernel 6.18.29 por cima do 6.12.37 antigo) =="
# Preserva o que é da fábrica e não veio do nosso /boot.
find "$MB" -mindepth 1 -maxdepth 1 \
     ! -iname 'Android' ! -iname 'LOST.DIR' ! -iname 'aml_auto.env' \
     -exec rm -rf {} + 2>/dev/null
cp -r /boot/. "$MB"/ || falhar "a cópia do /boot falhou"
sync

echo
echo "== conferência final =="
echo "  copiado:  $(du -sh --exclude=lost+found "$MR" 2>/dev/null | cut -f1)"
echo "  espaço:   $(df -h "$MR" | tail -1 | awk '{print $3" usados, "$4" livres ("$5")"}')"
echo "  kernel:   $(cd "$MB" && ls vmlinuz-* 2>/dev/null)"
echo "  dtb:      $(cd "$MB" && ls -d dtb-* 2>/dev/null)"
echo "  $(grep -a '^release=' "$MB/boot.config" 2>/dev/null)"
echo "  init:     $(test -x "$MR/sbin/init" -o -L "$MR/sbin/init" && echo ok || echo AUSENTE)"
echo "  secbox:   $(ls "$MR/opt/secbox/" 2>/dev/null | wc -l) arquivos em /opt/secbox"
echo "  fstab:"
grep -vE '^#|^$' "$MR/etc/fstab" | sed 's/^/    /'

limpar
systemctl start $SERVICOS
echo
echo "FASE 1 PRONTA. O cartão não foi tocado e continua bootável."
echo "Fase 2: desligue, remova o cartão, ligue. Deve subir o SecBox pela eMMC."
echo "Se não subir, recoloque o cartão — tudo volta ao que era."
