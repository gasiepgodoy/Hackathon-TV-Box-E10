# Device Tree Source e Blobs (Amlogic S905X2 / BTV Express E10)

Codigos-fonte (.dts) e binarios compilados (.dtb) do Device Tree para a TV Box BTV Express E10 (SoC Amlogic S905X2 / Meson G12A).

---

## Arquivos

| Arquivo | Descricao |
|---|---|
| `meson-g12a-btv-e10-enterprise.dts` | Codigo-fonte DTS com ajustes para o hardware BTV E10 |
| `meson-g12a-btv-e10-enterprise.dtb` | Binario compilado de producao (77.1 KB) utilizado na imagem oficial |
| `meson-g12a-sei510.dts` | DTS de referencia descompilado da base Armbian |
| `meson-g12a-sei510.dtb` | DTB base original |

---

## Modificações no DTS Enterprise

### 1. Memória Contígua CMA (`linux,cma`)
- **Nó:** `reserved-memory -> linux,cma`
- **Configuracao:** `size = <0x00 0x04000000>;` (64 MB, em vez dos 256 MB padrao).
- **Resultado:** Liberacao de 192 MB de memoria RAM fisica para os processos de usuario.

### 2. Estabilização do Barramento SDIO Wi-Fi (`mmc@ffe03000`)
- **Nó:** `soc -> mmc@ffe03000`
- **Configuracao:** `max-frequency = <0x17d7840>;` (25 MHz) e desativacao de `cap-sd-highspeed`.
- **Resultado:** Elimina erros de CRC e perda de sincronismo do chip Realtek RTL8189FTV no modo Ponto de Acesso.

### 3. Identificação do Rádio Wi-Fi e Desativação de Periféricos Inexistentes
- **Nó:** `wifi@1` e `bluetooth`
- **Configuracao:**
  ```dts
  compatible = "realtek,rtl8189fs", "realtek,rtl8189ftv", "generic-sdio";
  
  bluetooth {
      compatible = "brcm,bcm43438-bt";
      status = "disabled";
  };
  ```
- **Resultado:** Evita tentativas desnecessarias de probe de Bluetooth inexistente na UART.

### 4. Watchdog de Hardware (`watchdog@f0d0`)
- **Nó:** `soc -> bus@ff800000 -> watchdog@f0d0`
- **Configuracao:** `status = "okay";` no nó `amlogic,meson-gxbb-wdt`.
- **Resultado:** Habilita o dispositivo `/dev/watchdog` para reinicializacao automatica em caso de travamento do kernel.

### 5. Identificação do Modelo
- **Nó:** `/`
- **Configuracao:**
  ```dts
  compatible = "btv,e10", "seirobotics,sei510", "amlogic,g12a";
  model = "BTV Express E10 (Amlogic S905X2)";
  ```

### 6. Controlador Ethernet RMII
- **Nó:** `soc -> ethernet@ff3f0000`
- **Configuracao:** Parametros `amlogic,tx-delay-ns` e `amlogic,rx-delay-ns` calibrados para evitar descarte de pacotes no barramento RMII.

---

## Compilação Manual

Para recompilar o arquivo DTS para binario DTB:

```bash
dtc -I dts -O dtb -o meson-g12a-btv-e10-enterprise.dtb meson-g12a-btv-e10-enterprise.dts
```

Para descompilar um DTB existente de volta para DTS:

```bash
dtc -I dtb -O dts -o meson-g12a-btv-e10-enterprise.dts meson-g12a-btv-e10-enterprise.dtb
```
