# Pipeline de Build de Distro (Amlogic S905X2 / BTV E10)

Pipeline de compilacao, otimizacao de kernel e empacotamento de imagens oficiais (.img.xz) para dispositivos Amlogic S905X2.

---

## Arquitetura da Imagem

A distribuicao ForgeOS utiliza como base o Armbian Minimal ARM64 (Debian 13 Trixie), aplicando a arvore de dispositivos Enterprise e a stack de provisionamento:

1. **Base:** Armbian Minimal Debian 13 ARM64 (Kernel 6.18.44-ophub).
2. **Device Tree:** `meson-g12a-btv-e10-enterprise.dtb` (SDIO 25 MHz, 64 MB CMA, Watchdog nativo).
3. **Pilha On-Boot:** Modulos de rede, servidor HTTP e renderizador HDMI instalados em `/opt/forgeos/`.
4. **Servicos Systemd:** Unidades ativadas para modo AP, portal web cativo, display HDMI e watchdog de contingencia.
5. **Compressao:** Arquivo final gerado via `xz -T0 -9` acompanhado de manifesto SHA-256.

---

## Otimizações de Kernel e Subsistemas

| Componente | Configuracao | Efeito |
|------------|--------------|--------|
| MGLRU | `CONFIG_LRU_GEN=y` | Gestao multigeracional de memoria em ambientes de 2GB de RAM |
| ZRAM ZSTD | `PERCENT=50` | Alocacao de 925 MB de swap compactado em RAM sem desgaste de eMMC |
| Fast-Path | `CONFIG_NETFILTER_XT_TARGET_FLOWOFFLOAD=y` | Roteamento com bypass de pilha para conexoes de rede |
| Scheduler | `CONFIG_SCHED_BORE=y` | Priorizacao de tarefas interativas sob carga elevada de CPU |
| TCP BBRv3 | `net.ipv4.tcp_congestion_control = bbr` | Controle de congestionamento com alta vazao e baixa latencia |
| DTB Enterprise | `meson-g12a-btv-e10-enterprise.dtb` | Clock SDIO 25 MHz, 64 MB CMA (+192 MB RAM) e Watchdog de hardware |

---

## Instruções de Compilação

### Compilação em Nuvem (Google Cloud Spot VM)

Execucao automatizada com provisionamento efemero de VM, compilacao, download dos artefatos e auto-destruicao da instancia:

```powershell
python ForgeOS/distro/gcp-spot-launcher.py --project=stt-465818 --zone=us-central1-a
```

### Compilação em Ambiente Local (Linux / WSL2)

```bash
sudo ./ForgeOS/distro/build-image.sh
```

---

## Artefatos Gerados

- `distro_output/ForgeOS_BTV_E10_v1.0.0.img.xz`
- `distro_output/ForgeOS_BTV_E10_v1.0.0.img.xz.sha256`
