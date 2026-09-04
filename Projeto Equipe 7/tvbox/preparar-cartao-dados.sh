#!/bin/bash
# FASE 3 da migração: transforma o cartão SD em disco de dados puro.
#
# APAGA O CARTÃO INTEIRO. Só rode depois que a box já estiver bootando pela
# eMMC — enquanto o cartão ainda for o sistema de boot, ele é a rede de
# segurança da migração e não pode ser tocado.
#
# O que fica no cartão: a gravação de vídeo e o cache de clipes. Os dois são
# escrita pesada e descartável, que é exatamente o desgaste que se quer longe
# da eMMC. O sistema, que é quase só leitura, fica na eMMC.
#
# O ponto que dá sentido a tudo isto é o "nofail" das montagens: com cartão
# morto, ausente ou ilegível, a box ainda dá boot, sobe os túneis e responde —
# só não grava. Antes desta migração, cartão ruim era box fora do ar.
set -u

SD=/dev/mmcblk0
SDP=/dev/mmcblk0p1          # a única partição, criada aqui
EMMC_ROOT=/dev/mmcblk1p2
DADOS=/mnt/dados
REC=/opt/mediamtx/rec
CACHE=/opt/secbox-clip/cache
SERVICOS="mediamtx secbox-clip secbox-motion"

falhar() { echo "ERRO: $*" >&2; exit 1; }

echo "== travas de segurança =="
[ "$(id -u)" = 0 ] || falhar "precisa ser root"
# Uma ferramenta por vez: "command -v a b c" devolve sucesso sem conferir
# todas, e foi assim que um sfdisk ausente só apareceu no meio da execução,
# com o cartão já zerado.
for t in parted wipefs partprobe blockdev mkfs.ext4 chattr; do
    command -v "$t" >/dev/null 2>&1 || falhar "ferramenta ausente: $t"
done
raiz=$(findmnt -n -o SOURCE /)
# A trava mais importante do script: se a raiz ainda estiver no cartão, este
# script apagaria o sistema que está rodando.
[ "$raiz" = "$EMMC_ROOT" ] \
    || falhar "a raiz é $raiz, esperava $EMMC_ROOT — a box ainda não está na eMMC, recusando"
[ -b "$SD" ] || falhar "$SD não existe — o cartão está inserido?"
[ "$(cat /sys/block/mmcblk0/device/type 2>/dev/null)" = "SD" ] \
    || falhar "mmcblk0 não se identifica como cartão SD — recusando por segurança"
tam_gb=$(( $(blockdev --getsize64 "$SD") / 1000000000 ))
echo "  raiz: $raiz (eMMC, correto)"
echo "  alvo: $SD — ${tam_gb} GB, será APAGADO"

echo "== desmontando o que estiver no cartão =="
for m in $(findmnt -rn -o TARGET -S "$SD"p1 2>/dev/null) \
         $(findmnt -rn -o TARGET -S "$SD"p2 2>/dev/null); do
    echo "  desmontando $m"
    umount "$m" || falhar "não consegui desmontar $m"
done

echo "== apagando o início do cartão =="
# Os primeiros megabytes carregam o u-boot e a tabela de partições. Zerando,
# o cartão deixa de ser bootável — que é o que garante que todo boot daqui
# em diante vá para a eMMC, mesmo com o cartão encaixado.
dd if=/dev/zero of="$SD" bs=1M count=8 conv=fsync 2>/dev/null || falhar "dd falhou"
wipefs -a "$SD" >/dev/null 2>&1
partprobe "$SD" 2>/dev/null; sleep 2

echo "== criando uma partição única =="
# parted e não sfdisk/fdisk: esta imagem do Debian não os traz. A mensagem de
# erro fica visível de propósito -- na primeira versão eu mandei a saída para
# /dev/null e o "command not found" ficou escondido atrás de um erro genérico.
saida=$(parted -s "$SD" mklabel msdos 2>&1) || falhar "mklabel: $saida"
saida=$(parted -s -a optimal "$SD" mkpart primary ext4 1MiB 100% 2>&1) \
    || falhar "mkpart: $saida"
partprobe "$SD" 2>/dev/null || partx -u "$SD" 2>/dev/null
sleep 2
[ -b "$SDP" ] || falhar "$SDP não apareceu depois de particionar"

echo "== formatando para vídeo =="
# -m 0    : sem os 5% reservados para root; num disco de dados isso é 1,4 GB
#           parado à toa.
# -T largefile : um inode por MB em vez do padrão. Os arquivos aqui são
#           segmentos de vídeo de ~11 MB, então o padrão desperdiçaria centenas
#           de MB só em tabela de inodes.
mkfs.ext4 -q -m 0 -T largefile -L SECBOX_DADOS "$SDP" || falhar "mkfs falhou"
uuid=$(blkid -s UUID -o value "$SDP")
[ -n "$uuid" ] || falhar "não consegui ler o UUID da partição nova"
echo "  UUID: $uuid"

echo "== parando os serviços que escrevem =="
systemctl stop $SERVICOS

echo "== limpando e protegendo os pontos de montagem na eMMC =="
# O que ficou gravado na eMMC durante o teste de boot sem cartão sai agora.
rm -rf "${REC:?}"/* "${CACHE:?}"/* 2>/dev/null
mkdir -p "$REC" "$CACHE" "$DADOS"
# Imutável: com o cartão fora, a montagem falha (nofail) e estes diretórios
# ficam à mostra. Sem esta trava o MediaMTX gravaria vídeo direto na eMMC até
# enchê-la — trocaria "não grava" por "box travada", que é bem pior. Imutável,
# a escrita falha na hora e o problema aparece no log em vez de no espaço.
chattr +i "$REC" "$CACHE" 2>/dev/null \
    && echo "  proteção imutável aplicada" \
    || echo "  AVISO: não consegui aplicar chattr +i (siga, mas o disco fica exposto)"

echo "== montando =="
mount "$SDP" "$DADOS" || falhar "não montei $SDP em $DADOS"
mkdir -p "$DADOS/rec" "$DADOS/cache"

echo "== escrevendo o fstab =="
# Remove entradas antigas do cartão, se houver, e reescreve.
sed -i '/mnt\/dados/d; /opt\/mediamtx\/rec/d; /opt\/secbox-clip\/cache/d' /etc/fstab
cat >> /etc/fstab <<FSTAB

# Cartão SD: só dados (gravação e cache). NOFAIL EM TODAS AS TRÊS LINHAS, de
# propósito — este é o motivo da migração para a eMMC. Cartão morto ou ausente
# não pode impedir o boot; a box tem de subir, conectar e avisar que está sem
# gravação, em vez de simplesmente não ligar.
UUID=$uuid  $DADOS  ext4  defaults,noatime,nofail,x-systemd.device-timeout=15  0  2
$DADOS/rec    $REC    none  bind,nofail  0  0
$DADOS/cache  $CACHE  none  bind,nofail  0  0
FSTAB

systemctl daemon-reload
mount "$REC" 2>/dev/null || mount --bind "$DADOS/rec" "$REC" || falhar "bind da gravação falhou"
mount "$CACHE" 2>/dev/null || mount --bind "$DADOS/cache" "$CACHE" || falhar "bind do cache falhou"

echo "== religando os serviços =="
systemctl start $SERVICOS

echo
echo "== conferência =="
findmnt -n -o TARGET,SOURCE,FSTYPE "$DADOS" "$REC" "$CACHE" 2>/dev/null | sed 's/^/  /'
echo "  espaço de gravação: $(df -h "$REC" | tail -1 | awk '{print $4" livres de "$2}')"
echo "  eMMC:               $(df -h / | tail -1 | awk '{print $4" livres de "$2}')"
echo
echo "FASE 3 PRONTA. Sistema na eMMC, cartão só com vídeo."
echo "Teste que vale fazer um dia: tire o cartão com a box ligada, reinicie e"
echo "confirme que ela sobe mesmo assim. É a garantia que esta migração comprou."
