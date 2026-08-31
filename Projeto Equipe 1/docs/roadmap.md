# Roadmap do MultiForge

Planejamento estrategico e etapas de maturidade do projeto MultiForge:

---

## Fase 1 - Piloto e Prova de Conceito (Concluída)

- **Objetivo:** Validacao da arquitetura funcional na plataforma piloto BTV Express E10 (Amlogic S905X2).
- **Entregas Concluidas:**
  - Base de dados declarativa ForgeDB com schemas JSON formais (Draft 2020-12).
  - Aplicativo ForgeImager capaz de gravar discos e injetar configuracoes em particoes ext4 via `forge-write-conf`.
  - Stack ForgeOS com Ponto de Acesso resiliente, portal web cativo e watchdog de contingencia.
  - Distribuicao Linux otimizada com DTB Enterprise compilado (SDIO 25 MHz, 64 MB CMA e Watchdog).
  - Integracao dos modulos de aplicacao Totem (Mina AI) e Web Scraping (RAG).

---

## Fase 2 - Expansão e Multi-Hardware (Em Andamento)

- **Objetivo:** Expansao do catalogo de hardware e ferramentas de conformidade automatizadas.
- **Metas:**
  - Inclusao de novos modelos de TV Box no ForgeDB (familias Amlogic S905W/S905X3/S912, Rockchip RK3328/RK3566, Allwinner H6/H616).
  - Ferramenta CLI `forge-agent` para deteccao automatica de barramentos e geracao de manifestos `device.yaml`.
  - Integracao de pipeline de compilacao e testes continuos para os modulos do ecossistema.
  - Conexao do executor em segundo plano no portal web para instalacao automatizada de modulos.

---

## Fase 3 - Ecossistema de Produção e Atualizações

- **Objetivo:** Operacao em escala e gerenciamento de frotas de dispositivos.
- **Metas:**
  - Mecanismo de atualizacao Over-The-Air (OTA) para kernel, device trees e aplicacoes.
  - Painel de gerenciamento centralizado para inventario de nos em rede local e remota.
  - Integracao de novos templates de aplicacoes para automacao e sinalizacao digital.
