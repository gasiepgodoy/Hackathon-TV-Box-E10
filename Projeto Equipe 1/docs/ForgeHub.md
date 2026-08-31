# 🔌 ForgeHub (Absorvido no ForgeOS)

> **Nota Arquitetural (29/08/2026):**  
> O conceito do **ForgeHub** foi integrado diretamente ao **ForgeOS** como a funcionalidade **Module Hub** (aba *Módulos* no Portal Web e endpoints `/rest/modules` e `/api/modules/*`).

## Justificativa da Consolidação
Em dispositivos de recursos limitados (como a TV Box BTV E10 com 2GB RAM e 8GB eMMC), manter um serviço de marketplace externo ou containers adicionais de gerenciamento gerava sobrecarga desnecessária.

A funcionalidade foi absorvida pelo próprio **ForgeOS Portal**, consumindo os metadados declarativos unificados em **`ForgeDB/modules/`**.

Consulte:
* [Guia do ForgeOS](../ForgeOS/README.md) — Para operação e endpoints REST do Module Hub.
* [Guia do ForgeDB](../ForgeDB/README.md) — Para estrutura de manifestos e esquemas de módulos.
