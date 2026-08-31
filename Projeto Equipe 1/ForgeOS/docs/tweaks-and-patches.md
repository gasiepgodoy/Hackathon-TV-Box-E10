# Manual de Tweaks, Patches e Otimizações do ForgeOS

Documento tecnico de referencia dos patches de kernel, arvore de dispositivos, gerenciamento de memoria, pilha de rede e drivers integrados na distribuicao do ForgeOS para processadores Amlogic S905X2 (BTV Express E10).

---

## Sumário de Otimizações

| Ajuste / Patch | Subsistema | Efeito Pratico |
|----------------|------------|----------------|
| MGLRU (Multi-Gen LRU) | Memoria Virtual | Maior resiliencia a pressoes de memoria (anti-OOM) |
| ZRAM (ZSTD Multi-stream) | Swap Compactado | +925 MB de memoria util sem desgaste de eMMC |
| Reducao do CMA (64 MB) | Driver DRM/VPU | +192 MB de memoria RAM fisica livre |
| TCP BBRv3 + FQ | Pilha de Rede | Menor latencia e maior throughput sob perda de pacotes |
| Anti-Sleep RTL8189FTV | Driver Wi-Fi | Eliminacao de latencias no modo Ponto de Acesso |
| Protecao de I/O em Flash | Parametros do Kernel | Minimizacao de travamentos de I/O em cartoes SD |
| SDIO Bus Fix (25 MHz) | Device Tree | Eliminacao de erros de CRC e queda de sinal Wi-Fi |

---

## 1. Camada de Árvore de Dispositivos (Device Tree)

Arquivo: `ForgeOS/dtb/meson-g12a-btv-e10-enterprise.dts`

### Redução do Buffer de Vídeo (`linux,cma`)
- **Configuração:** `size = <0x00 0x04000000>;` (64 MB).
- **Motivação:** A alocacao padrao de 256 MB foi projetada para reproducao de video 4K HDR. Para sistemas embarcados e quiosques, 64 MB sao suficientes para acomodar framebuffers Full HD 1080p, devolvendo 192 MB de memoria RAM fisica para o sistema operacional.

### Estabilização do Barramento SDIO (`mmc@ffe03000`)
- **Configuração:** `max-frequency = <0x17d7840>;` (25 MHz).
- **Motivação:** O chip Realtek RTL8189FTV conectado via SDIO sofre com erros de CRC e perda de sincronismo se operado em frequencias elevadas em placas de consumo sem isolamento de sinal de alta precisao. Limitar o clock a 25 MHz assegura throughput estavel de ate 12.5 MB/s sem instabilidades eletromagneticas.

### Watchdog de Hardware (`watchdog@f0d0`)
- **Configuração:** `status = "okay";` no nó `amlogic,meson-gxbb-wdt`.
- **Motivação:** Permite que o daemon do sistema interaja com `/dev/watchdog` para reinicializacao automatica em caso de congelamento critico do kernel.

---

## 2. Driver Wi-Fi Realtek RTL8189FTV

Arquivo de configuracao: `/etc/modprobe.d/8189fs.conf`

Parametros aplicados:
```ini
options 8189fs rtw_power_mgnt=0 rtw_enusbss=0 rtw_hwpdn_mode=2 rtw_lowrate_two_xmit=1
```

- `rtw_power_mgnt=0`: Desativa a economia de energia agressiva que causava desligamento do estagio de radio frequencia durante ociosidade.
- `rtw_lowrate_two_xmit=1`: Duplica a transmissao de quadros de gerenciamento (Beacons) em taxas basicas (1-2 Mbps) para melhorar a descoberta da rede por dispositivos moveis.

---

## 3. Gerenciamento de Memória (MGLRU e ZRAM)

Arquivo de configuracao: `/etc/sysctl.d/99-forgeos-performance.conf`

### MGLRU (Multi-Gen LRU)
```ini
vm.page_lock_unfairness = 1
```
O algoritmo Multi-Gen LRU organiza as paginas de memoria em geracoes geracionais, reduzindo drasticamente o uso de CPU durante escaneamento de memoria sob carga pesada e evitando ativacao desnecessaria do Out-Of-Memory (OOM) Killer.

### Swap Compactado em RAM (ZRAM ZSTD)
- O modulo `zram0` e criado com tamanho correspondente a 50% da memoria fisica (~925 MB).
- Utiliza o compressor de alta vazao ZSTD com prioridade maxima de swap (`pri=32767`).
- Atinge taxa de compressao tipica de 3:1, permitindo que a TV Box comporte servicos que requerem ate ~2.8 GB de memoria de trabalho combinada.

---

## 4. Pilha de Rede TCP BBRv3

```ini
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
```
Substitui o algoritmo tradicional Cubic pelo Google BBRv3 (Bottleneck Bandwidth and RTT) associado ao escalonador Fair Queueing (`fq`), maximizando o throughput em conexoes com perda de pacotes e reduzindo o bufferbloat.

---

## 5. Proteção de I/O para Memória Flash

```ini
vm.dirty_background_ratio = 5
vm.dirty_ratio = 10
vm.vfs_cache_pressure = 50
```
Garante que os dados pendentes de escrita sejam sincronizados gradualmente para o cartao MicroSD ou eMMC, impedindo acúmulo de buffers e eliminando congelamentos do sistema operacional causados por lentidao na memoria flash.
