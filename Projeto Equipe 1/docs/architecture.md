# Arquitetura do MultiForge

Descricao da arquitetura geral do ecossistema MultiForge e do modelo de cooperacao entre os 4 componentes principais para identificacao, gravacao, provisionamento e execucao de aplicacoes em hardware ARM legado.

---

## Estrutura dos Componentes

```text
+---------------------------------------------------------+
|                     ForgeImager                         |
|   (Gravador desktop Tauri v2 + React 19 + Rust)         |
+----------------------------+----------------------------+
                             |
                             v (grava eMMC/SD e injeta ext4)
+---------------------------------------------------------+
|                       ForgeOS                           |
|   (Pilha On-Device: AP Cativo, Kiosk HDMI e Module Hub) |
+----------------------------+----------------------------+
                             |
         +-------------------+-------------------+
         |                                       |
         v                                       v
+----------------------------+       +----------------------------+
|          ForgeDB           |       |        ForgeModules        |
|   (Metadados de hardware   |       |   (Aplicacoes de borda:    |
|   e catalogo de modulos)   |       |    Totem AI e Web Scraping)|
+----------------------------+       +----------------------------+
```

---

## 1. ForgeDB
Fonte unica de metadados para hardware e aplicacoes:
- **Dispositivos (`devices/`):** Mapeia especificacoes de SoCs (Amlogic, Rockchip, Allwinner), adaptadores Wi-Fi, arvores de dispositivos (DTBs) e particularidades de boot.
- **Modulos (`modules/`):** Catalogo central (`catalog.yaml`) e manifestos declarativos (`module.yaml`) com definicoes de requisitos de memoria, pacotes de sistema e comandos de ciclo de vida.
- **Schemas (`schemas/`):** Validadores JSON Schema (Draft 2020-12) para assegurar conformidade no pipeline de CI/CD.

---

## 2. ForgeImager
Aplicacao desktop multiplataforma desenvolvida em Tauri v2, React 19 e Rust:
- Selecao de imagens a partir de manifestos remotos de releases do GitHub com checagem de integridade SHA-256.
- **Injecao Userspace em Ext4 (`crates/forge-write-conf`):** Gravacao de credenciais de rede e parametros de primeiro boot diretamente no sistema de arquivos ext4 sem necessidade de montagem ou privilegios de root no host.
- **Protocolo Sahara/EDL:** Gravacao de baixo nivel para recuperacao de processadores Qualcomm em modo MaskROM (`VID 0x05C6`).

---

## 3. ForgeOS
Distribuicao Linux customizada e stack de provisionamento on-device:
- **Ponto de Acesso Resiliente:** Opera em `192.168.4.1` via `wpa_supplicant` mode=2 para contornar limitacoes do driver Realtek RTL8189FTV.
- **Portal Web e REST API:** Interface de configuracao de rede com suporte a WPA2-PSK e 802.1X EAP (Eduroam), alem de compatibilidade com endpoints convencionados (`/rest/*`).
- **Module Hub:** Gerenciamento local do ciclo de vida das aplicacoes instaladas.
- **Kiosk HDMI Framebuffer (`/dev/fb0`):** Renderizacao grafica em 1080p sem necessidade de servidor X11 ou Wayland, reduzindo consumo de memoria.
- **Watchdog de Rede:** Monitor em segundo plano com rollback automatico para modo AP em caso de falha de conexao (tempo limite de 75 segundos).

---

## 4. ForgeModules
Aplicacoes modulares executadas sobre o ForgeOS:
- **Totem (Mina AI):** Assistente virtual para quiosques com processamento de voz offline (Sherpa-ONNX), interface PyQt5 e classificador de intencoes local.
- **Coletor Acadêmico & RAG:** Servico assincrono de coleta de dados com FastAPI e LangChain RAG, com opcoes de execucao local (SQLite) ou em container (PostgreSQL).
