# ForgeOS

Sistema operacional customizado e stack de provisionamento on-device para TV Boxes e computadores de placa única (SBCs) baseados na arquitetura ARM64 (Amlogic, Allwinner, Rockchip).

---

## Especificações do Hardware Piloto

- **Dispositivo:** BTV Express E10
- **Processador (SoC):** Amlogic S905X2 (Meson G12A), 4x Cortex-A53 @ 1.80 GHz
- **GPU:** ARM Mali-G31 MP2
- **Memória RAM:** 2 GB LPDDR4 (1.85 GB visíveis ao kernel)
- **Armazenamento:** 8 GB eMMC 5.1 Flash + leitor de cartão MicroSD
- **Interface Wi-Fi:** Realtek RTL8189FTV (SDIO 1-bit / 4-bit, 2.4 GHz 802.11b/g/n)
- **Ethernet:** Realtek RTL8211F (RMII 10/100 Mbps)
- **Saída de Vídeo:** HDMI 2.0a (1080p @ 60Hz com sincronismo forçado)
- **Kernel Base:** Linux 6.18.44-ophub (ARM64)
- **Espaço de Usuário:** Armbian Linux 26.08 Trixie (Debian 13 Minimal)

---

## Camadas de Otimização e Tweaks

A distribuição inclui patches estruturais em nível de kernel, árvore de dispositivos (Device Tree), rede e gerenciamento de memória:

### 1. Device Tree Blob (DTB) Enterprise
- **Arquivo:** `dtb/meson-g12a-btv-e10-enterprise.dtb`
- **Barramento SDIO do Wi-Fi:** Frequência travada em 25 MHz (`max-frequency = <25000000>`) e modo cap-sd-highspeed desativado para eliminar erros de CRC e perdas de firmware no chip RTL8189FTV.
- **Redução do Buffer CMA:** Buffer de vídeo contíguo reduzido de 256 MB para 64 MB (`cma = <0x04000000>`), liberando 192 MB de memória RAM para processos de usuário.
- **Watchdog de Silício:** Ativação do módulo `/dev/watchdog` nativo do SoC Amlogic (`meson-gxbb-wdt`).
- **Controlador Ethernet:** Compatibilidade estrita `amlogic,meson-g12a-dwmac` com delays calibrados para TX/RX no barramento RMII.

### 2. Gerenciamento de Memória e I/O
- **MGLRU (Multi-Gen LRU):** Escalonador de memória ativado com suporte a múltiplos geradores de reclaim.
- **ZRAM com Compressão ZSTD:** Swap comprimido em RAM alocado em 50% do total (925 MB), atingindo taxa média de compressão de 3:1 e eliminando desgaste de escrita na flash eMMC.
- **Proteção de Escrita Flash:** `vm.dirty_background_ratio = 5` e `vm.dirty_ratio = 10` para prevenir travamentos de I/O em cartões MicroSD classe 10.
- **Pilha de Rede:** Algoritmo de controle de congestionamento Google BBRv3 com enfileiramento `fq`.

---

## Estrutura do Diretório

```text
ForgeOS/
|-- bin/
|   |-- start-ap.sh          # Inicializacao do ponto de acesso via wpa_supplicant mode=2
|   |-- apply-sta.sh         # Aplicacao de credenciais cliente e validacao de gateway
|   |-- watchdog.sh          # Monitoramento de conectividade e rollback automatico (75s)
|   `-- install.sh           # Instalador do sistema e configuracao de servicos systemd
|-- web/
|   |-- server.py            # Servidor HTTP REST (Python 3 standard library)
|   |-- index.html           # Interface web SPA responsiva (Dark/Light mode)
|   `-- static/              # Ativos estaticos e manifestos PWA
|-- display/
|   |-- display_manager.py   # Renderizacao de tela HDMI via framebuffer Linux (/dev/fb0)
|   `-- assets/              # Tipografia e recursos visuais
|-- dtb/
|   |-- meson-g12a-btv-e10-enterprise.dts  # Codigo-fonte do Device Tree
|   |-- meson-g12a-btv-e10-enterprise.dtb  # Blob compilado pronto para boot
|   `-- README.md            # Documentacao de registradores e instrucoes de compilacao
|-- distro/
|   |-- build-image.sh       # Pipeline de construcao de imagem rootfs/boot
|   |-- gcp-spot-launcher.py # Script de compilacao automatizada em instancia Spot no GCP
|   `-- README.md            # Guia de geracao de imagens
|-- docs/
|   `-- tweaks-and-patches.md # Manual tecnico detalhado dos patches aplicados
`-- tests/
    |-- test_server.py       # Testes da API REST
    |-- test_dtb.py          # Validacao de integridade e nos do DTB
    `-- run_all.sh           # Script de execucao de toda a suite de testes
```

---

## Serviços do Systemd

| Unidade | Tipo | Funcao |
|---------|------|--------|
| `forge-ap.service` | oneshot | Configura interface wlan0, gateway 192.168.4.1 e inicia dnsmasq |
| `forge-portal.service` | simple | Executa o servidor HTTP na porta 8080 (e 80 redirecionada) |
| `forge-display.service` | simple | Inicializa renderizacao grafica do kiosk no `/dev/fb0` |
| `forge-watchdog.service` | simple | Monitor de conectividade com rollback em 75s |
| `forge-fbcon-disable.service` | oneshot | Desativa cursor de terminal e blanking de tela no HDMI |

---

## Referência da API REST

### Estado e Provisionamento

- **`GET /api/status`**
  Retorna o estado operacional atual (modo AP ou modo Cliente).
  ```json
  {
    "ap_active": true,
    "ssid": "ForgeOS-Setup-E10",
    "provisioning": false,
    "client_connected": false,
    "client_ssid": null,
    "client_ip": null
  }
  ```

- **`GET /api/scan`**
  Executa varredura de redes Wi-Fi proximas com medicao de RSSI e tipo de criptografia (WPA2-PSK ou 802.1X EAP).

- **`POST /api/provision`**
  Aplica configuracao de rede Wi-Fi recebida via JSON e aciona teste de conectividade.

- **`POST /api/reset`**
  Reverte imediatamente o adaptador de rede para o modo Ponto de Acesso.

### Telemetria e Módulos

- **`GET /api/telemetry`** ou **`GET /rest/systemStatus`**
  Retorna telemetria de hardware (temperatura da CPU em graus Celsius, frequencia dos nucleos, uso de memoria RAM, taxa de swap ZRAM e espaco em disco).

- **`GET /rest/modules`**
  Retorna a lista de modulos de aplicacao cadastrados no catalogo do ForgeDB e seu estado local de instalacao.

---

## Compilação e Testes

### Execução de Testes Unitários

```bash
cd ForgeOS
python -m unittest discover -s tests -p "test_*.py" -v
```

### Compilação do Device Tree

```bash
cd ForgeOS/dtb
dtc -I dts -O dtb -o meson-g12a-btv-e10-enterprise.dtb meson-g12a-btv-e10-enterprise.dts
```
