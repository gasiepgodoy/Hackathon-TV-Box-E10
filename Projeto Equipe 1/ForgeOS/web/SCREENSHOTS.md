# 🎛️ Galeria Visual da Interface Cockpit // ForgeOS
> **Ambiente:** BTV Express E10 (SoC Amlogic S905X2 · 4x Cortex-A53 · 2GB RAM · Armbian Linux 6.18)  
> **Acesso Local:** `http://192.168.1.153:8080` | **Ponto de Acesso Cativo:** `http://192.168.4.1:8080`  
> **Design System:** Red Hat Cockpit / PatternFly Enterprise (Modo Escuro e Claro)  

---

## 📑 Sumário Executivo
Este documento reúne a galeria fotográfica completa da interface Web do **ForgeOS**, desenvolvida segundo as diretrizes de arquitetura do **Cockpit Project** da Red Hat. A interface conta com telemetria contínua a cada **1.0s**, gráficos em onda SVG (*sparklines*), gerenciamento de serviços *systemd*, provisionador de Wi-Fi doméstico e corporativo (802.1X EAP/Eduroam) e o catálogo modular **ForgeHub**.

---

## 🖥️ 1. Telas Principais no Desktop (1280x800)

### 📊 1.1 Visão Geral do Sistema (Dashboard com Telemetria em Tempo Real)
Monitoramento em tempo real dos 4 núcleos da CPU, memória RAM LPDDR4, tráfego de rede I/O (`eth0`/`wlan0`), tempo ativo (*uptime*), redes Wi-Fi próximas e especificações do hardware extraídas diretamente do kernel via `/proc/device-tree/model`.

![Cockpit Desktop Overview](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_01_overview.png)

> [!TIP]
> Os gráficos *sparklines* utilizam buffers estáticos de ponto flutuante (`Float32Array`) renderizados em 60 FPS com `requestAnimationFrame`, isolando o recálculo do layout através de `contain: layout style`.

---

### 📡 1.2 Rede & Conectividade Wi-Fi (Scanner RF e Configuração de AP)
Scanner de sinais de rádio com medidor de intensidade RSSI em dBm, suporte a redes abertas, WPA2-PSK e corporativas 802.1X EAP (Eduroam / UNESP), além de painel de configuração do Ponto de Acesso e parâmetros DHCP do `dnsmasq`.

![Cockpit Desktop Networking](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_02_networking.png)

---

### ⚙️ 1.3 Serviços do Sistema & Particionamento de Armazenamento
Gerenciador de unidades do *systemd* com filtros de categoria (`Todos`, `Daemons ForgeOS`, `Serviços Base`), botões de reinício instantâneo, especificações da árvore de dispositivos (DTB) e alocação de armazenamento eMMC (`/` e `/boot`).

![Cockpit Desktop Services](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_03_services.png)

---

### 🧩 1.4 Arsenal de Módulos (ForgeHub App Store)
Catálogo de aplicativos com gerenciamento de ciclo de vida (Instalar, Iniciar, Pausar, Desinstalar) para aplicações como a assistente de voz acadêmica **Mina**, coletor de dados **Web Scraping RAG** e renderizador HDMI framebuffer **Kiosk Display**.

![Cockpit Desktop Modules](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_04_modules.png)

---

### 📜 1.5 Terminal de Logs do Kernel & Daemons
Visualizador de eventos do `journalctl` e logs de contingência com botões de cópia para área de transferência e limpeza.

![Cockpit Desktop Logs](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_05_logs.png)

---

### ☀️ 1.6 Modo Claro (PatternFly Light Theme)
Tema claro de alto contraste para ambientes com alta luminosidade e conformidade com acessibilidade WCAG AAA.

![Cockpit Desktop Light Mode](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_06_light_mode.png)

---

## 📱 2. Telas no Smartphone (Mobile 360x740)

A versão mobile foi otimizada com **cards padronizados e ultracompactos**, gaveta lateral deslizante (*touch drawer*) e alinhamento milimétrico em telas pequenas.

| 📊 Visão Geral Compacta | 📡 Scanner de Rede Wi-Fi | 🧩 Catálogo de Módulos |
| :---: | :---: | :---: |
| ![Mobile Overview](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_mobile_01_overview.png) | ![Mobile Networking](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_mobile_02_networking.png) | ![Mobile Modules](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_mobile_03_modules.png) |

| ⚙️ Serviços & Hardware | 🔐 Modal de Conexão EAP | 🗂️ Menu Lateral (Drawer) |
| :---: | :---: | :---: |
| ![Mobile Services](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_mobile_05_services.png) | ![Mobile Modal](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_mobile_04_modal.png) | ![Mobile Drawer](https://raw.githubusercontent.com/multi-forge/multi-forge/main/docs/assets/cockpit_mobile_02_drawer.png) |

---

## 🛠️ 3. Tabela Resumo de Arquivos e Recursos

| Recurso | Caminho Local / Endpoint | Descrição |
| :--- | :--- | :--- |
| **Frontend Web SPA** | [`ForgeOS/web/index.html`](file:///C:/Users/Aluno/multi-forge/ForgeOS/web/index.html) | Interface Cockpit com CSS puro, SVG sparklines e JS assíncrono. |
| **Backend REST & Hardware** | [`ForgeOS/web/server.py`](file:///C:/Users/Aluno/multi-forge/ForgeOS/web/server.py) | Daemon Python HTTP multi-thread com extração via `/proc` e `/sys`. |
| **API Telemetria (1s)** | `GET /rest/metrics` | Retorna CPU (%), RAM (MB), Rede RX/TX (KB/s), Uptime e Disco. |
| **API Hardware Probe** | `GET /api/hardware` | Retorna SoC, Modelo da Placa, Kernel, DTB e partição `/boot`. |
| **API Serviços** | `GET /api/services` | Consulta status das unidades do *systemd* em tempo real. |
| **Pacote ZIP de Imagens** | [`ForgeOS_Provisioner_Screenshots.zip`](file:///C:/Users/Aluno/Documents/ForgeOS_Provisioner_Screenshots.zip) | Arquivo comprimido contendo todos os 12 screenshots em alta resolução. |
