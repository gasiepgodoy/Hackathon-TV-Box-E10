# ForgeDB

Base de dados centralizada e declarativa contendo metadados de hardware, definicoes de arvore de dispositivos (Device Tree), metodos de gravacao e catalogo de modulos do ecossistema MultiForge.

---

## Estrutura do Repositório

```text
ForgeDB/
|-- devices/             # Metadados de placas e SBCs homologadas
|   `-- btv/
|       `-- e10/
|           |-- device.yaml    # Especificacao completa de hardware e boot
|           `-- dtb/           # Binarios de arvore de dispositivos associados
|-- modules/             # Catalogo e manifestos de aplicacoes
|   |-- catalog.yaml     # Indice central de modulos disponiveis
|   |-- totem/
|   |   `-- module.yaml  # Manifesto do modulo Mina AI Totem
|   `-- web-scraping/
|       `-- module.yaml  # Manifesto do modulo Coletor / RAG
`-- schemas/             # Validadores formais JSON Schema (Draft 2020-12)
    |-- device.schema.json  # Schema para validacao de device.yaml
    `-- module.schema.json  # Schema para validacao de module.yaml
```

---

## Especificação de Dispositivos (`device.yaml`)

Cada dispositivo cadastrado contem identificacao completa de pinout, SoC, perifericos de rede e particionamento:

```yaml
id: btv-e10
name: BTV Express E10
vendor: BTV
soc:
  family: Amlogic
  model: S905X2
  architecture: aarch64
  cores: 4
  frequency_max_mhz: 1800
memory:
  ram_mb: 2048
  type: LPDDR4
storage:
  type: eMMC
  size_gb: 8
connectivity:
  wifi:
    chipset: Realtek RTL8189FTV
    bus: SDIO
    max_frequency_hz: 25000000
  ethernet:
    chipset: Realtek RTL8211F
    speed_mbps: 100
boot:
  dtb: meson-g12a-btv-e10-enterprise.dtb
  uenv_cmdline: "root=LABEL=ROOTFS rootflags=data=writeback rw console=ttyAML0,115200n8 console=tty0 video=HDMI-A-1:1920x1080@60e"
```

---

## Especificação de Módulos (`module.yaml`)

Manifesto declarativo contendo requisitos de execucao, dependencias e comandos de ciclo de vida:

```yaml
id: totem
name: Mina - Assistente Virtual Acadêmica
version: 1.0.0
category: ai
requirements:
  min_ram_mb: 512
  min_storage_mb: 200
  python: ">=3.9"
  system_packages:
    - portaudio19-dev
    - python3-pyqt5
lifecycle:
  install: "python install.py --headless"
  start: "python main_cli.py"
  stop: "pkill -f main_cli.py"
  healthcheck: "pgrep -f main_cli.py"
  systemd_unit: "forge-totem.service"
```

---

## Validação Automatizada

Para validar a integridade de todos os arquivos contra os schemas JSON:

```bash
# Validacao de dispositivos:
python -c "import yaml, json, jsonschema; jsonschema.validate(yaml.safe_load(open('devices/btv/e10/device.yaml')), json.load(open('schemas/device.schema.json'))); print('device.yaml valido.')"

# Validacao de modulos:
python -c "import yaml, json, jsonschema; jsonschema.validate(yaml.safe_load(open('modules/totem/module.yaml')), json.load(open('schemas/module.schema.json'))); print('module.yaml valido.')"
```
