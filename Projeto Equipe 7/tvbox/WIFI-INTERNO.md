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
nenhum pacote passa.

### A causa (confirmada)

São duas, somadas, e nenhuma tem a ver com o driver:

**1. Duas vifs do mesmo rádio associadas à mesma rede.** O Makefile liga
`CONFIG_CONCURRENT_MODE` incondicionalmente (`ccflags-y`, sem opção), então o
driver **sempre** cria duas interfaces — e os dois nomes saem do mesmo molde:

```c
char *ifname  = "wlan%d";   /* primeira */
char *if2name = "wlan%d";   /* segunda  */
```

Viram `wlan0` e `wlan1`, com MACs derivados um do outro (`3c:…:e2:9b` /
`3e:…:e0:9b` — o segundo com o bit de "administrado localmente" ligado). Se o
NetworkManager tiver perfil para as duas, **as duas associam ao mesmo AP** e
disputam o único caminho de TX do rádio. O resultado no `dmesg`:

```
RTW: cfg80211_rtw_scan (wlan0) : scan abort!! buddy_intf under survey
RTW: rtw_sctx_wait timeout: dump_mgntframe_and_wait_ack_timeout
RTW: rtl8188f_sreset_xmit_status_check REG_TXDMA_STATUS:0x00000010
```

O modo concorrente existe para STA + P2P/AP, não para dois STA no mesmo AP.

**2. Roaming entre APs em sub-redes diferentes.** O SSID é servido por mais de
um AP, e eles não estão no mesmo segmento IP:

```
default via 186.217.145.33 dev wlan0 src 186.217.145.56    ← rede .32/27
default via 186.217.145.97 dev wlan1 src 186.217.145.110   ← rede .96/27
```

Com a box na borda da cobertura (−70 dBm), ela troca de AP; a associação
continua de pé, mas o IP passa a pertencer à sub-rede do AP anterior. Endereço
inválido, rota morta — e o `iw` continua dizendo "Connected", que é o que torna
o sintoma confuso. O conserto certo é **reativar o perfil**, que força
concessão DHCP nova.

Isso é configuração da rede, não da box: um SSID servido por APs em sub-redes
distintas, sem suporte de mobilidade. Quem administra a rede resolve na origem.

**As correções:**

```bash
# 1) uma vif só: apague os perfis órfãos e tire a segunda do NetworkManager
nmcli connection delete "<perfil-orfao>"
nmcli device set wlan0 managed no      # runtime; ver abaixo como persistir

# 2) sem roaming no meio da sessão: um perfil por AP, com prioridade
nmcli connection modify wifi-interna 802-11-wireless.bssid <BSSID-melhor> \
                                     connection.autoconnect-priority 10
nmcli connection clone wifi-interna wifi-interna-alt
nmcli connection modify wifi-interna-alt 802-11-wireless.bssid <BSSID-outro> \
                                         connection.autoconnect-priority 5
```

Com BSSID fixo o NM não troca de AP no meio da sessão — só troca quando a
conexão cai de verdade, e ativar outro perfil dispara DHCP novo.

> **Para persistir**, não basta o `nmcli device set … managed no`, que é
> runtime. E não dá para amarrar a regra a "wlan0" enquanto as duas interfaces
> se chamarem `wlan%d`, porque os nomes podem trocar numa recarga do módulo e
> a regra acabaria desligando a interface boa. Dê nomes distintos primeiro:
>
> ```
> options 8189fs ifname=wlan1 if2name=wlanaux rtw_initmac=<MAC-FIXO>
> ```
>
> e só então `unmanaged-devices=interface-name:wlanaux` em
> `/etc/NetworkManager/conf.d/`. O `rtw_initmac` importa porque o efuse não tem
> MAC: sem ele cada recarga sorteia um novo, muda a identidade DHCP e invalida
> as reservas do roteador.

### Descartado: power save

O primeiro palpite em driver `rtl8189` é sempre **gerenciamento de energia**, e
a leitura do fonte reforça: com `CONFIG_POWER_SAVING = y` (padrão do Makefile),
o `autoconf.h` liga `CONFIG_LPS_LCLK` **só no caminho SDIO** —

```c
#if defined(CONFIG_LPS) && (defined(CONFIG_GSPI_HCI) || defined(CONFIG_SDIO_HCI))
    #define CONFIG_LPS_LCLK          /* LPS com clock gating */
#endif
```

— e o `os_intfs.c` dá `rtw_lps_level = RTW_LPS_MODE - 1` para SDIO, contra
`LPS_NORMAL` fixo para USB. Ou seja: trocar o dongle pelo chip interno **troca o
caminho de código**, e o novo faz clock gating no mesmo barramento que já
precisou cair para 25 MHz. Encaixa perfeitamente no sintoma.

**Só que não era isso.** Conferindo antes de mexer:

```bash
grep . /sys/module/8189fs/parameters/rtw_power_mgnt \
       /sys/module/8189fs/parameters/rtw_lps_level \
       /sys/module/8189fs/parameters/rtw_ips_mode
```

Nesta box veio `0 / 1 / 0`, e não o `2 / 1 / 1` que os defaults do fonte
produziriam. Com `rtw_power_mgnt = 0` (`PS_MODE_ACTIVE`), o driver faz
`bLeisurePs = (PS_MODE_ACTIVE != power_mgnt)` → falso, e **nunca entra em LPS**;
o `rtw_lps_level` só escolhe qual nível usar *quando* entra, então fica inerte.
Com `rtw_ips_mode = 0` junto, IPS e LPS já estavam ambos desligados durante as
quedas.

> **Fica a lição:** leia os parâmetros em `/sys/module/` antes de "desligar" o
> que talvez já esteja desligado. O default do fonte não é necessariamente o
> que está rodando.

Se na sua box os valores vierem diferentes, aí sim vale desligar e observar —
não custa nada, já que a box vive na tomada e economia de rádio não compra
disponibilidade:

```bash
printf 'options 8189fs rtw_power_mgnt=0 rtw_lps_level=0 rtw_ips_mode=0\n' \
  > /etc/modprobe.d/8189fs.conf
nmcli connection modify wifi-interna 802-11-wireless.powersave 2   # 2 = desligado
reboot
```

A linha do NetworkManager não é redundante: o driver implementa
`cfg80211_rtw_set_power_mgmt` e, ao receber "desabilitado", dispara
`LPS_CTRL_LEAVE_CFG80211_PWRMGMT`. O parâmetro de módulo impede de entrar; o do
NM força a sair.

> ⚠️ Antes de sobrescrever o `8189fs.conf`, veja o que já existe
> (`grep -r . /etc/modprobe.d/ | grep -i 8189`): se houver um `rtw_initmac`, ele
> precisa ser preservado na mesma linha, senão cada recarga do módulo volta a
> gerar MAC aleatório, o DHCP entrega outro IP e as reservas do roteador param
> de valer.

### Descartado: o `blacklist` esquecido da época do dongle

Quando o Wi-Fi interno ainda não funcionava, era comum ter isto para impedir o
driver meio pronto de subir:

```
/etc/modprobe.d/disable-wifi-interno.conf:  blacklist 8189fs
```

Depois que o chip interno passou a ser **o** rádio, esse arquivo vira armadilha.
Ele não impede o [`rtl8189fs.service`](systemd/rtl8189fs.service) de carregar o
módulo — `blacklist` só bloqueia a carga automática **por alias**, e o serviço
chama `modprobe 8189fs` pelo nome. Por isso tudo parece normal no boot.

O problema aparece depois: se o módulo for descarregado ou o dispositivo SDIO
for reenumerado em runtime, o udev tenta recarregar pelo alias
(`sdio:c00v024Cdf179`) e o `blacklist` **barra**. O rádio não volta sozinho — e
o único caminho de volta é o `modprobe` explícito, que só roda no boot. Ou
seja: uma queda que só termina com reinício.

```bash
grep -r . /etc/modprobe.d/ /lib/modprobe.d/ /run/modprobe.d/ 2>/dev/null | grep -i 8189
mv /etc/modprobe.d/disable-wifi-interno.conf ~/disable-wifi-interno.conf.bak
depmod -a
```

O serviço pode continuar: ele resolve o timing de boot, e agora a carga por
alias serve de rede de segurança em runtime.

Outra causa que vale descartar cedo, se houver **um só** ponto de acesso:
roaming. Procurar outro AP é motivo de queda, não de cura.

```bash
BSSID=$(iw dev wlan1 link | awk '/Connected to/{print $3}')
nmcli connection modify wifi-interna wifi.bssid "$BSSID"
```

> Com mesh ou repetidor, pule — você estaria proibindo o roaming legítimo.

### Depois, o vigia

[`wifi-guard.sh`](wifi-guard.sh) é a rede de segurança para quando a causa não
morre de todo. Ele testa o **gateway** (não a internet — se quem caiu foi o
provedor, mexer no rádio não ajuda) a cada 10 s e, após ~30 s sem resposta,
escala:

| Nível | Ação | Por quê nesta ordem |
|---|---|---|
| 1–3 | `nmcli connection up wifi-interna` | é o conserto certo do caso comum (DHCP novo); insiste três vezes |
| 4 | diagnóstico completo + `ip link` down/up | reconectar falhou: caso incomum, vale registrar |
| 5 | `nmcli connection up` de novo | depois do bounce a reativação costuma pegar |
| 6 | `modprobe -r 8189fs` + `modprobe` | recria as duas vifs e **sorteia MAC novo** — remédio caro |
| 7 | `systemctl reboot` | último recurso |

A ordem não é acidental. No histórico desta box, recarregar o módulo foi
seguido de outra queda em ~45 s: ele troca o MAC, recria as vifs e faz o NM
correr atrás de tudo de novo. Por isso ficou lá atrás, e reconectar — que é o
que de fato resolve — ganhou três tentativas.

O reboot tem duas travas: não acontece nos primeiros 15 min de uptime (para
falha permanente não virar laço) nem enquanto a queda não passar de 10 min (a
box grava vídeo 24/7, e reiniciar corta a gravação — custa mais que ficar
alguns minutos sem rede).

Ao voltar publica `devices/{id}/rede/event` (`wifi_recovered`), mas só nas
quedas acima de 2 min ou que precisaram de mais que reconectar: com queda a
cada poucos minutos, publicar todas afogaria os eventos que importam.

```bash
install -Dm755 wifi-guard.sh /opt/secbox/wifi-guard.sh
cp systemd/wifi-guard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wifi-guard
```

Na segunda checagem falha ele registra **uma linha** com BSSID, sinal, IP e
rota. Esses quatro campos separam os casos sem afogar o log: BSSID diferente do
episódio anterior é roaming; BSSID igual e sem IP é concessão perdida; sem
BSSID é desassociação.

O **diagnóstico completo** (`iw`, `nmcli`, rota, `/sys/bus/sdio/devices/`,
`lsmod`, `dmesg` filtrado) sai só no nível 4, quando reconectar três vezes não
resolveu — aí sim é um caso diferente do de sempre e vale o custo em linhas. A
linha `[sdio]` é a que separa os mundos: se o dispositivo sumiu do barramento,
o problema é o SDIO e não o 802.11.

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
