# Wi-Fi interno (RTL8189FTV / rtl8189fs)

Como ativar o **Wi-Fi interno** da TV box e liberar a porta USB que antes era
ocupada por um dongle Wi-Fi. Testado em **Amlogic S905X2 (g12a)**, kernel
**6.18-meson64** (Armbian/ophub, bootando de cartão SD).

> Chip interno: **RTL8189FTV**, SDIO `024c:f179` (enumera como `mmc2`).
> No kernel 6.18 não há driver in-tree nem pacote `apt` — é preciso compilar.

## ⚠️ Faça backup antes

A Parte 2 edita o *device tree* — um `.dtb` inválido impede o boot. Como o
sistema roda do **cartão SD**, faça uma **imagem completa do cartão** no PC
(ex.: Win32DiskImager → *Read*) antes de começar. Se algo der errado, regrave a
imagem ou coloque o cartão num leitor e restaure o `.dtb.orig`.

## Parte 1 — Compilar o driver

Fonte mantida para kernels recentes (`rtl8189ES_linux` do jwrdegoede, branch
`rtl8189fs`). O fork antigo `ap17/rtl8189fs` **não** compila no 6.18.

```bash
cd /usr/src
git clone --depth 1 -b rtl8189fs https://github.com/jwrdegoede/rtl8189ES_linux.git rtl8189fs
cd rtl8189fs
# Plataforma nativa arm64 (o padrão vem como Allwinner 32-bit):
sed -i 's/^CONFIG_PLATFORM_I386_PC = n/CONFIG_PLATFORM_I386_PC = y/' Makefile
sed -i 's/^CONFIG_PLATFORM_ARM_SUN8I = y/CONFIG_PLATFORM_ARM_SUN8I = n/' Makefile
# O kbuild do kernel 6.x ignora EXTRA_CFLAGS (causa "drv_types.h: No such file"):
sed -i 's/EXTRA_CFLAGS/ccflags-y/g' Makefile
make -j"$(nproc)" ARCH=arm64 CROSS_COMPILE= KSRC=/lib/modules/$(uname -r)/build
ls -l 8189fs.ko    # deve existir (~2,9 MB)
```

## Parte 2 — Ajustar o device tree (SDIO a 25 MHz)

Carregando o driver assim, dá `RTW: ... FAIL!(-110)` (timeout SDIO): o
controlador do Wi-Fi está a **100 MHz SDR50**, rápido demais para o chip. O
chip enumera em baixa velocidade, mas falha ao ler registradores em alta.
A correção é baixar a frequência do **nó SDIO do Wi-Fi** e remover o modo UHS.

Descubra qual `.dtb` o box carrega (no nosso caso `box=s905x2_generic` em
`/boot/boot.config` → `meson-g12a-u2xx-generic.dtb`) e edite **somente** o nó
`mmc@ffe03000` (o SDIO do Wi-Fi — **não** o do cartão SD `mmc@ffe05000` nem o
da eMMC `mmc@ffe07000`):

```bash
D=/boot/dtb-<versao>/amlogic/<seu-dtb>.dtb
cp -n "$D" "$D.orig"                                   # backup do DTB
dtc -I dtb -O dts -o /tmp/wifi.dts "$D.orig"
# 100 MHz (0x5f5e100) -> 25 MHz (0x17d7840), casando SÓ max-frequency:
sed -i 's/max-frequency = <0x5f5e100>/max-frequency = <0x17d7840>/' /tmp/wifi.dts
sed -i '/sd-uhs-sdr50;/d' /tmp/wifi.dts                # remove o modo UHS
dtc -I dts -O dtb -o "$D" /tmp/wifi.dts
reboot
```

> **Cuidado:** `0x5f5e100` também aparece como `assigned-clock-rates` (deixe
> intacto) — por isso casamos apenas `max-frequency = <0x5f5e100>`, que é único
> do nó Wi-Fi.

Progressão observada: 100→50 MHz mata o `-110`, mas o `sdio_power_on_check`
ainda falha (`cmd52 ≠ cmd53`, teste `0x1B8`); **50→25 MHz** resolve
(`FirmwareDownload success`, `drv_open ... bup=1`).

## Parte 3 — Deixar permanente

Instale o módulo e carregue no boot via serviço systemd (o `modules-load.d`
sozinho não pegou, por timing de boot):

```bash
KVER=$(uname -r)
install -Dm644 /usr/src/rtl8189fs/8189fs.ko \
  "/lib/modules/$KVER/kernel/drivers/net/wireless/8189fs.ko"
depmod -a
cp systemd/rtl8189fs.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable rtl8189fs.service
```

Conecte pelo NetworkManager com um perfil **dedicado à `wlan1`** (para não
conflitar com o perfil do dongle na `wlan0`):

```bash
nmcli connection add type wifi ifname wlan1 con-name wifi-interna \
  ssid "SUA_REDE" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "SUA_SENHA"
nmcli connection up wifi-interna
```

Reinicie e confirme que a `wlan1` sobe e conecta sozinha:

```bash
lsmod | grep 8189
nmcli -t -f DEVICE,STATE,CONNECTION dev status | grep wlan1
```

## Parte 4 — Quedas de rede: causa e rede de segurança

Depois de trocar o dongle pelo chip interno, aparecem **quedas que não se
recuperam sozinhas** — para o NetworkManager a `wlan1` continua conectada, mas
nenhum pacote passa, e só o reboot devolvia a rede.

### Primeiro, tente matar a causa

O suspeito número um nos drivers da família `rtl8189` é o **gerenciamento de
energia**: o rádio entra em economia e não acorda direito. Desligue nos dois
níveis e observe por alguns dias.

```bash
# 1) no driver
cat > /etc/modprobe.d/8189fs.conf <<'EOF'
options 8189fs rtw_power_mgnt=0 rtw_ips_mode=0
EOF

# 2) no NetworkManager (2 = desligado)
nmcli connection modify wifi-interna 802-11-wireless.powersave 2

# 3) sem roaming: com um AP só, procurar outro é motivo de queda e não de cura
BSSID=$(iw dev wlan1 link | awk '/Connected to/{print $3}')
nmcli connection modify wifi-interna wifi.bssid "$BSSID"

reboot
```

> A `wifi.bssid` só faz sentido se houver **um** ponto de acesso. Com mesh ou
> repetidor, pule esse passo — você estaria proibindo o roaming legítimo.

Vale também fixar o MAC (`rtw_initmac`, ver Notas): sem isso cada recarga do
módulo gera um MAC novo, o DHCP entrega outro IP e as reservas do roteador
param de valer — o que faz a recuperação parecer pior do que é.

### Depois, o vigia

[`wifi-guard.sh`](wifi-guard.sh) é a rede de segurança para quando a causa não
morre de todo. Ele testa o **gateway** (não a internet — se quem caiu foi o
provedor, mexer no rádio não ajuda) a cada 20 s e, após ~1 min sem resposta,
escala:

| Nível | Ação | Custo |
|---|---|---|
| 1 | `nmcli connection up wifi-interna` | segundos, nada mais cai |
| 2 | `ip link` down/up + reconectar | idem |
| 3 | `modprobe -r 8189fs` + `modprobe 8189fs` | ~20 s, o rádio renasce |
| 4 | `systemctl reboot` | último recurso |

Cada nível só entra se o anterior não resolveu. O reboot é bloqueado nos
primeiros 15 min de uptime, para uma falha permanente não virar laço de
reinício. Ao voltar, publica `devices/{id}/rede/event` (`wifi_recovered`, com
quanto tempo ficou fora e em que nível resolveu) — evento comum, sem push, que
serve para medir a frequência real do problema.

```bash
install -Dm755 wifi-guard.sh /opt/secbox/wifi-guard.sh
cp systemd/wifi-guard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wifi-guard
```

O histórico fica em `/var/log/wifi-guard.log` — em arquivo de propósito, já que
o journal desta box é volátil e o próprio vigia pode causar o reboot que
apagaria a evidência.

## Notas

- **MAC aleatório:** o efuse do módulo pode não ter MAC gravado; o driver gera
  um aleatório a cada boot. Não impede funcionar. Para fixar, use
  `options 8189fs rtw_initmac=<MAC>` em `/etc/modprobe.d/8189fs.conf`.
- **Throughput:** a 25 MHz o SDIO é mais lento, mas sobra folga para o stream
  das câmeras (~1,5 Mbps no total).
- **Interfaces:** o driver cria `wlan1` (estação) e `wlan2` (virtual).
- **Reverter:** restaure `"$D.orig"` sobre o `.dtb`, remova o serviço
  (`systemctl disable rtl8189fs`) e volte ao dongle USB.
