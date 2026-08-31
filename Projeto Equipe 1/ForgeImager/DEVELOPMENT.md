# Guia de Desenvolvimento

Guia completo para configuração, compilação e contribuição para o Forge Imager.

## Sumário

1. [Início Rápido](#início-rápido)
2. [Pré-requisitos](#pré-requisitos)
3. [Configuração Passo a Passo](#configuração-passo-a-passo)
4. [Fluxo de Trabalho de Desenvolvimento](#fluxo-de-trabalho-de-desenvolvimento)
5. [Compilando para Distribuição](#compilando-para-distribuição)
6. [Estrutura do Projeto](#estrutura-do-projeto)
7. [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
8. [Tecnologias Utilizadas](#tecnologias-utilizadas)
9. [Fontes de Dados](#fontes-de-dados)
10. [Verificações de Qualidade](#verificações-de-qualidade)
11. [Solução de Problemas](#solução-de-problemas)

---

## Início Rápido

```bash
git clone https://github.com/multi-forge/multi-forge.git && cd imager
# No diretório correto do projeto:
bash scripts/setup/install.sh
npm install
npm run tauri:dev
```

---

## Pré-requisitos

| Requisito | Versão Mínima | Link |
|-----------|---------------|------|
| Node.js | 20.19.0 | [nodejs.org](https://nodejs.org) |
| Rust | 1.77.2 | [rustup.rs](https://rustup.rs) |
| npm | 10+ | Incluído com o Node.js |

### Dependências por Plataforma

**Linux:** `libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev`

**macOS:** Xcode Command Line Tools (Ferramentas de Linha de Comando do Xcode)

**Windows:** Visual Studio Build Tools 2022 + WebView2 Runtime

---

## Configuração Passo a Passo

### 1. Clonar o Repositório

```bash
git clone https://github.com/multi-forge/multi-forge.git
cd imager
```

### 2. Instalar Dependências do Sistema

**Automatizado (Recomendado):**
```bash
bash scripts/setup/install.sh
```

### 3. Verificar Pré-requisitos

```bash
node --version    # deve ser >= 20.19.0
rustc --version   # deve ser >= 1.77.2
```

### 4. Instalar e Executar

```bash
npm install
npm run tauri:dev
```

---

## Fluxo de Trabalho de Desenvolvimento

### Scripts Disponíveis

| Comando | Descrição |
|---------|-----------|
| `npm run dev` | Apenas Frontend (servidor de desenvolvimento Vite) |
| `npm run tauri:dev` | Aplicativo completo com hot reload (frontend + Rust) |
| `npm run build` | Compilação de produção do frontend |
| `npm run build:dev` | Compilação de desenvolvimento do frontend |
| `npm run tauri:build` | Distribuição final de produção |
| `npm run tauri:build:dev` | Compilação de depuração (debug) com símbolos |
| `npm run lint` | Executa o ESLint |
| `npm run clean` | Limpa todos os artefatos temporários (node_modules, dist, target) |

### Fluxo Diário

1. `npm run tauri:dev` - Iniciar servidor de desenvolvimento
2. Modificar arquivos em [`src/`](src/) ou [`src-tauri/src/`](src-tauri/src/) - Atualização automática
3. Testar as alterações
4. Executar as verificações de qualidade antes de fazer o commit (veja [Verificações de Qualidade](#verificações-de-qualidade))

---

## Compilando para Distribuição

### Única Plataforma

```bash
./scripts/build/build-macos.sh      # macOS universal (ARM64 + x64)
./scripts/build/build-linux.sh      # Linux (x64 + ARM64 via Docker)
npm run tauri:build                  # Plataforma atual
```

### Todas as Plataformas

```bash
./scripts/build/build-all.sh
```

### Opções de Compilação

```bash
./scripts/build/build-macos.sh --clean        # Compilação limpa
./scripts/build/build-macos.sh --dev          # Com símbolos de depuração
./scripts/build/build-linux.sh --x64          # Apenas Linux x64
./scripts/build/build-linux.sh --arm64        # Apenas Linux ARM64
./scripts/build/build-all.sh --macos --linux  # Plataformas específicas
```

### Saída (Builds)

| Plataforma | Formato | Diretório de Saída |
|------------|---------|--------------------|
| macOS | .dmg, .app | `src-tauri/target/{arch}/release/bundle/` |
| Linux | .deb, .AppImage | `src-tauri/target/{arch}/release/bundle/` |
| Windows | .msi, .nsis | `src-tauri/target/{arch}/release/bundle/` |

---

## Estrutura do Projeto

```
forge-imager/
├── src/                              # Frontend React 19
│   ├── App.tsx                       # App principal + máquina de estados de seleção
│   ├── main.tsx                      # Ponto de entrada (i18n, tema, montagem)
│   ├── i18n.ts                       # Configuração de i18n com carregamento dinâmico de idiomas
│   │
│   ├── components/
│   │   ├── flash/                    # UI do progresso de gravação
│   │   │   ├── FlashProgress.tsx     # Apresentação (usa o hook useFlashOperation)
│   │   │   ├── FlashActions.tsx      # Botões de cancelar/repetir/concluído
│   │   │   └── FlashStageIcon.tsx    # Ícones de estágio + chaves de tradução
│   │   ├── modals/                   # Assistente de seleção em 4 passos
│   │   │   ├── Modal.tsx             # Modal base (animações, controle de saída)
│   │   │   ├── ManufacturerModal.tsx # Passo 1: Seleção de fabricante
│   │   │   ├── BoardModal.tsx        # Passo 2: Seleção de placa (grade de imagens)
│   │   │   ├── ImageModal.tsx        # Passo 3: Seleção de imagem de SO (filtros)
│   │   │   ├── DeviceModal.tsx       # Passo 4: Seleção de dispositivo (detecção)
│   │   │   └── ForgeBoardModal.tsx   # Detecção automática ao rodar sob Forge
│   │   ├── settings/                 # Modal de configurações de 5 abas
│   │   │   ├── SettingsModal.tsx     # Container com barra lateral de navegação
│   │   │   ├── AppearanceSection.tsx # Tema + idioma
│   │   │   ├── PreferencesSection.tsx# MOTD, pular verificação, detecção de placas
│   │   │   ├── StorageSection.tsx    # Gerenciamento de cache
│   │   │   ├── DeveloperSection.tsx  # Modo dev + visualizador de logs
│   │   │   ├── AboutSection.tsx      # Versão, créditos, links
│   │   │   ├── CacheManagerModal.tsx # Navegador de imagens em cache com opção de exclusão
│   │   │   └── LogsModal.tsx         # Visualizador de logs + envio para paste.forge.dev
│   │   ├── layout/
│   │   │   ├── Header.tsx            # Cabeçalho da aplicação com indicadores de passos
│   │   │   └── HomePage.tsx          # Botões de seleção principal / tela de gravação
│   │   └── shared/                   # Componentes de UI reutilizáveis
│   │       ├── BoardBadges.tsx       # Badges de nível de suporte da placa
│   │       ├── ConfirmationDialog.tsx# Avisos de perda de dados / imagens instáveis
│   │       ├── ErrorDisplay.tsx      # Erro com botão de tentar novamente + envio de logs
│   │       ├── MarqueeText.tsx       # Texto em rolagem horizontal (Marquee)
│   │       ├── MotdTip.tsx           # Dicas rotativas da API do Forge
│   │       ├── SearchBox.tsx         # Input de filtro de busca para os modais
│   │       ├── SkeletonCard.tsx      # Loaders em efeito skeleton
│   │       ├── Toast.tsx             # Notificações de sucesso/erro
│   │       ├── UpdateModal.tsx       # Dialog de atualização do aplicativo
│   │       └── ChangelogModal.tsx    # Exibição das notas de versão (release notes)
│   │
│   ├── hooks/                        # Custom Hooks do React
│   │   ├── useTauri.ts              # Wrappers de comandos IPC do Tauri (26+ comandos)
│   │   ├── useAsyncData.ts          # Busca assíncrona genérica (proteção contra race-conditions)
│   │   ├── useFlashOperation.ts     # Orquestração do ciclo de vida da gravação
│   │   ├── useVendorLogos.ts        # Pré-carregamento de logos + agrupamento por fabricante
│   │   ├── useSettings.ts           # Get/set para o plugin Tauri Store (20+ configurações)
│   │   ├── useSettingsGroup.ts      # Carregamento paralelo em lote de configurações
│   │   ├── useSkeletonLoading.ts    # Exibição de skeleton com duração mínima
│   │   ├── useModalExitAnimation.ts # Animação de saída de 200ms com proteção de disparo duplo
│   │   ├── useDeviceMonitor.ts      # Monitoramento de conexões de dispositivos
│   │   └── useToasts.tsx            # Contexto global de notificações toast
│   │
│   ├── contexts/
│   │   └── ThemeContext.tsx          # Tema claro/escuro/auto com preferência do sistema
│   │
│   ├── config/
│   │   ├── constants.ts             # Polling, timings, cache, UI, chaves de configurações
│   │   ├── badges.ts                # Cores de badges de ambientes desktop + kernel
│   │   ├── os-info.ts               # Logos de SO, logos de apps, mapeamento de versões
│   │   ├── deviceColors.ts          # Esquema de cores por tipo de dispositivo
│   │   └── i18n.ts                  # Configuração de idiomas suportados + metadados
│   │
│   ├── styles/                       # CSS com Design Tokens
│   │   ├── theme.css                # Propriedades customizadas (cores, espaçamento, cantos)
│   │   ├── base.css                 # Reset, barras de rolagem, spinners e estados
│   │   ├── layout.css               # Layout e containers das páginas
│   │   ├── components.css           # Botões, badges, cards, inputs
│   │   ├── modal.css                # Animações de modais e UI de configurações
│   │   ├── flash.css                # Barra de progresso, ícones de estágio e erros
│   │   └── responsive.css           # Responsividade e Breakpoints (600-1400px)
│   │
│   ├── types/index.ts               # Interfaces BoardInfo, ImageInfo, BlockDevice, etc.
│   ├── utils/index.ts               # formatFileSize, parseForgeFilename, etc.
│   ├── utils/deviceUtils.ts         # isDeviceConnected, getDeviceType
│   ├── locales/                     # Arquivos JSON de tradução (18 idiomas)
│   └── assets/                      # Imagens de marcas e distribuições
│
├── src-tauri/                        # Backend Rust (Tauri 2)
│   ├── src/
│   │   ├── main.rs                  # Setup do aplicativo, plugins e comandos
│   │   ├── download.rs              # Streaming HTTP + cálculo de SHA256 + logs de mirrors
│   │   ├── decompress.rs            # Descompressão XZ (multithreaded), GZ, BZ2, ZST
│   │   ├── cache.rs                 # Cache LRU com limite configurável de tamanho
│   │   │
│   │   ├── commands/                # Comandos Tauri IPC (54 no total)
│   │   │   ├── board_queries.rs     # get_boards, get_images_for_board, get_block_devices
│   │   │   ├── operations.rs        # download_image, flash_image, delete, cleanup
│   │   │   ├── progress.rs          # get_download/flash_progress, cancel_operation
│   │   │   ├── custom_image.rs      # select, decompress, detecção de placa pelo nome do arquivo
│   │   │   ├── scraping.rs          # get_cached_board_image, get_cached_vendor_logo
│   │   │   ├── settings.rs          # Comandos get/set de configurações (25+ comandos)
│   │   │   ├── system.rs            # open_url, locale, logs de frontend, detecção de Forge
│   │   │   ├── update.rs            # get_github_release, is_app_in_applications
│   │   │   └── state.rs             # AppState (JSON cacheado, estados de download/gravação)
│   │   │
│   │   ├── devices/                 # Detecção de dispositivos por plataforma
│   │   │   ├── types.rs             # Estrutura BlockDevice, normalize_bus_type, detect_sd
│   │   │   ├── linux.rs             # Leitura do lsblk JSON + checagem de sysfs
│   │   │   ├── macos.rs             # Framework DiskArbitration nativo (~50ms, filtros APFS)
│   │   │   └── windows.rs           # IOCTLs de Win32 (PhysicalDrive0-31)
│   │   │
│   │   ├── flash/                   # Operações de gravação por plataforma
│   │   │   ├── verify.rs            # Lógica compartilhada de verificação byte a byte
│   │   │   ├── linux/
│   │   │   │   ├── writer.rs        # Abertura de UDisks2 descriptor + direct I/O
│   │   │   │   └── privileges.rs    # Autorização via polkit
│   │   │   ├── macos/
│   │   │   │   ├── writer.rs        # authopen -> escritas brutas em `/dev/rdisk*` (alinhado)
│   │   │   │   ├── authorization.rs # Security.framework + suporte a Touch ID
│   │   │   │   └── bindings.rs      # Bindings FFI
│   │   │   └── windows.rs           # Bloqueio de volume Win32 + DeviceIoControl
│   │   │
│   │   ├── images/                  # Processamento de dados da API
│   │   │   ├── models.rs            # Structs BoardInfo, ImageInfo
│   │   │   └── filters.rs           # Extração e filtragem de placas/imagens
│   │   │
│   │   ├── logging/mod.rs           # Logs estruturados (arquivo + console colorido)
│   │   ├── paste/upload.rs          # Upload de log para paste.forge.dev
│   │   ├── config/mod.rs            # Constantes gerais (URLs, buffers, timeouts, etc.)
│   │   └── utils/
│   │       ├── format.rs            # parse_forge_filename, normalize_slug, format_size
│   │       ├── path.rs              # validate_cache_path, get_cache_dir
│   │       ├── progress.rs          # ProgressTracker com limite de frequência de escrita
│   │       └── system.rs            # Contagem de CPU, sugestão de threads
│   │
│   ├── Cargo.toml                   # Dependências do Rust
│   ├── tauri.conf.json              # Configurações do Tauri (janelas, bundle, atualizador)
│   └── icons/                       # Ícones da aplicação para todas as plataformas
│
├── scripts/
│   ├── build/
│   │   ├── build-all.sh             # Orquestrador de compilação multiplataforma
│   │   ├── build-macos.sh           # Executável universal para macOS (ARM64 + x64)
│   │   └── build-linux.sh           # Compilação Linux via Docker (x64 + ARM64)
│   ├── setup/
│   │   ├── install.sh               # Instalador multiplataforma (auto-detecta o SO)
│   │   ├── install-linux.sh         # Dependências Linux (Ubuntu/Debian/Fedora/Arch)
│   │   ├── install-macos.sh         # Dependências macOS (Homebrew + Rust)
│   │   └── install-windows.ps1      # Dependências Windows (PowerShell)
│   └── locales/
│       └── sync-locales.js          # Sincronização de traduções via IA (API OpenAI)
│
├── .github/workflows/
│   ├── maintenance-pr-check.yml     # Validação de PRs (lint, tipos, build, segurança)
│   ├── maintenance-build.yml        # Builds manuais multiplataforma
│   ├── maintenance-release.yml      # Builds de lançamento assinado + notarização
│   └── ...                          # Sincronização de labels, locales, etc.
│
├── eslint.config.js                 # Configuração do ESLint (regras estritas de TS)
│   ├── tsconfig.json                # Configuração root do TypeScript
│   ├── vite.config.ts               # Configuração do build Vite
│   └── package.json                 # Dependências e scripts Node
```

---

## Visão Geral da Arquitetura

### Fluxo de Seleção e Máquina de Estados

O aplicativo usa um assistente linear em 4 etapas: **Fabricante -> Placa -> Imagem -> Dispositivo**

O estado é gerenciado no arquivo `App.tsx` com invalidação em cascata — alterar a seleção em uma etapa N zera todas as seleções posteriores (N+1, N+2, etc.) por meio do método `resetSelectionsFrom()`.

### Comunicação Frontend -> Backend

Cinquenta e quatro comandos Tauri IPC conectam o frontend React ao backend Rust:

```
Componente React
  -> Hook (useTauri.ts)
    -> invoke('nome_do_comando', { parametros })
      -> Handler #[tauri::command] do Rust
        -> Lógica específica de plataforma
          -> Progresso via consulta (polling) de estado atômico
            -> Atualização da UI React
```

O progresso é monitorado via **polling** (e não via eventos): o frontend solicita `getDownloadProgress()` / `getFlashProgress()` a cada 250ms, lendo os estados atômicos expostos pelo backend Rust.

### Arquitetura de Hooks Principais

| Hook | Finalidade |
|------|------------|
| `useFlashOperation` | Orquestra todo o ciclo de vida da gravação (autorização -> download -> descompressão -> gravação -> verificação) controlando falhas, monitoramento de conexões e limpeza de temporários. |
| `useAsyncData` / `useAsyncDataWhen` | Carregamento assíncrono seguro contra race-conditions com gerenciamento nativo de estados de erro/carregamento. |
| `useSkeletonLoading` | Evita piscadas (flicker) na UI, forçando uma exibição mínima de 300ms dos skeletons de carregamento. |
| `useVendorLogos` | Pré-carrega logos dos fabricantes, agrupando falhas sob a categoria "outros" e ordenando pelo nível de tier. |
| `useSettings` | Conjunto de 20+ funções getter/setter para ler/gravar usando o plugin Tauri Store. |
| `useModalExitAnimation` | Controla animações de saída de 200ms, protegendo contra disparos repetidos acidentais. |

### Detecção de Dispositivos por Plataforma

| Plataforma | Método | Latência | Detecção de Disco de Sistema |
|------------|--------|----------|------------------------------|
| Linux | `lsblk` em formato JSON + sysfs | ~100-200ms | Mapeamento `findmnt` + `lsblk PKNAME` |
| macOS | DiskArbitration (FFI nativa) | ~50ms | `diskutil info /` (cacheado via `OnceLock`) |
| Windows | Win32 IOCTL (PhysicalDrive0-31) | ~200ms | Mapeamento da letra de unidade "C:" |

### Gravação por Plataforma

| Plataforma | Modelo de Privilégios | Método de Escrita | Estratégia de Verificação |
|------------|-----------------------|-------------------|---------------------------|
| Linux | polkit (transparente) | File descriptor UDisks2 / direct I/O | Invalidação de cache via `posix_fadvise` |
| macOS | Security.framework + Touch ID | `authopen` -> `/dev/rdisk*` (escrita direta, alinhada) | Uso de BufReader alinhado ao setor do disco |
| Windows | Exige privilégio Administrador | `CreateFileW` + flag `FILE_FLAG_WRITE_THROUGH` | Reabertura com flag `FILE_FLAG_NO_BUFFERING` |

Todas as plataformas executam uma limpeza rápida (escreve 64MB de zeros) antes de gravar a imagem, chamam `fsync` após a escrita e compartilham a mesma lógica byte a byte de validação final.

### Download e Descompressão

1. **Checagem de cache** - Retorna imediatamente a imagem se ela já estiver baixada (cache LRU, padrão de 20GB).
2. **Download** - Streaming HTTP para um arquivo temporário com sufixo `.downloading`, reportando progresso.
3. **Log de Mirrors** - Registra no log de depuração o destino final da URL (após redirecionamento do `dl.forge.dev`).
4. **Validação SHA256** - Compara o hash do arquivo baixado; em caso de `[SHA_UNAVAILABLE]`, o usuário pode optar por prosseguir sem verificação.
5. **Descompressão** - Processamento XZ multi-thread via `lzma-rust2` com fallback para `liblzma` do sistema, com suporte adicional a GZ, BZ2 e ZST.
6. **Exclusão de cache corrompido** - Remove automaticamente do cache imagens locais após 3 falhas seguidas de gravação do mesmo arquivo.

### Sistema de Estilo (Design Tokens)

O arquivo `theme.css` define os Design Tokens de toda a interface:

- **Cores semânticas**: `--color-success`, `--color-warning`, `--color-error`, `--color-info` (e suas variantes escuras e de contraste)
- **Espaçamento**: De `--space-xs` (4px) até `--space-4xl` (48px)
- **Cantos arredondados**: De `--radius-sm` (4px) até `--radius-full` (50%)
- **Sombras**: Sistema de 3 níveis (sm, md, lg) com variações claras/escuras
- **Temas**: Classes CSS `.theme-light` / `.theme-dark` integradas ao modo automático baseado em `prefers-color-scheme`.

---

## Tecnologias Utilizadas

### Frontend

| Tecnologia | Versão | Objetivo |
|------------|---------|----------|
| React | 19.2 | Framework de UI |
| TypeScript | 5.9 | Tipagem estática rigorosa (strict mode) |
| Vite | 7.2 | Compilador e Servidor Dev |
| i18next | 25.7 | Internacionalização e traduções |
| Lucide React | 0.560 | Biblioteca de ícones vetoriais |
| Tauri API | 2.9 | Comunicação IPC |

### Backend

| Tecnologia | Versão | Objetivo |
|------------|---------|----------|
| Rust | Edição 2021 | Linguagem de programação de sistemas |
| Tauri | 2.x | Framework desktop híbrido |
| Tokio | 1.x | Executor assíncrono (runtime) |
| Reqwest | 0.12 | Cliente HTTP com suporte a rustls-tls |
| lzma-rust2 | 0.15 | Descompressão multithreaded XZ |
| SHA2 | 0.10 | Verificação criptográfica SHA256 |

### Plugins do Tauri

| Plugin | Objetivo |
|--------|----------|
| `tauri-plugin-store` | Configurações persistentes em arquivos JSON |
| `tauri-plugin-shell` | Abertura de URLs externas no navegador nativo |
| `tauri-plugin-dialog` | Modais e seletores nativos de arquivos |
| `tauri-plugin-updater` | Atualizações automáticas usando o GitHub Releases |
| `tauri-plugin-process` | Controle de reinício/encerramento do processo |

### Por que Tauri e não Electron?

| Métrica | Tauri | Electron |
|---------|-------|----------|
| Tamanho do Instalador | ~15 MB | 150-200 MB |
| Consumo de RAM | ~50 MB | 200-400 MB |
| Tempo de Inicialização | < 1s | 2-5s |
| Webview | Nativo do SO (Edge/Safari/Webkit) | Chromium embutido |

---

## Fontes de Dados

| Informação | URL / Origem |
|------------|--------------|
| Lista de Placas e Imagens | [github.com/multi-forge/multi-forge/Forge-images.json](https://github.com/multi-forge/multi-forge/Forge-images.json) |
| Fotos das Placas | [cache.forge.dev/images/272/{slug}.png](https://cache.forge.dev/images/) |
| Logos de Fabricantes | [cache.forge.dev/images/vendors/150/{vendor}.png](https://cache.forge.dev/images/vendors/150/) |
| Dicas do MOTD | [github.com/Forge/os/main/motd.json](https://raw.githubusercontent.com/Forge/os/main/motd.json) |
| Envio de Logs | [paste.forge.dev](https://paste.forge.dev) |
| Atualizações do App | [GitHub Releases](https://github.com/multi-forge/multi-forge/releases/latest/download/latest.json) |

---

## Verificações de Qualidade

Execute **todas as verificações** antes de criar seus commits:

### Frontend

```bash
npm run lint           # ESLint (strict: bloqueia any, exige === e const)
npx tsc --noEmit       # Validação de tipos do TypeScript
```

### Backend

```bash
cd src-tauri
cargo fmt              # Formatação de código Rust (não deve gerar diferenças)
cargo clippy --all-targets --all-features -- -D warnings  # Linter sem avisos
```

### Pipeline de Integração Contínua (CI/CD)

Os PRs são validados de forma automatizada via GitHub Actions:
1. Validação e lint no frontend
2. Formatação (`fmt`) e linter (`clippy`) no Rust
3. Teste de compilação em todas as 3 plataformas (Linux, macOS, Windows)
4. Auditoria de segurança (`npm audit` + `cargo audit`)

---

## Solução de Problemas

### Problemas Comuns

| Sintoma | Solução |
|---------|---------|
| `cargo metadata failed` | Execute `bash scripts/setup/install.sh` ou instale o [Rust](https://rustup.rs) |
| `glib-2.0 not found` (Linux) | Execute `sudo bash scripts/setup/install-linux.sh` |
| Erro de Xcode Command Line Tools (macOS) | Execute `xcode-select --install` |
| Erro de VS Build Tools (Windows) | Execute `scripts/setup/install-windows.ps1` com privilégios de Administrador |
| Falha ao instalar módulos Node | Certifique-se de usar Node.js >= 20.19.0, então execute `rm -rf node_modules && npm install` |
| Erro de incompatibilidade de versão | Sincronize a versão nos arquivos `package.json`, `Cargo.toml` e `tauri.conf.json` |

### Obtendo Ajuda

1. Procure nas [Issues do GitHub](https://github.com/multi-forge/multi-forge/issues)
2. Consulte o [Fórum da Comunidade Forge](https://github.com/multi-forge/multi-forge/discussions)
3. Crie uma nova issue contendo: versão do seu SO, saída do comando `node --version`, `rustc --version` e o log de erro completo.

---

## Contribuindo

Contribuições são muito bem-vindas! Veja os detalhes no guia [CONTRIBUTING.md](CONTRIBUTING.md).

### Dicas Importantes

- Crie commits focados e atômicos.
- Teste suas alterações em múltiplos sistemas operacionais se forem ligadas a recursos de gravação ou drivers.
- Execute todas as verificações de qualidade localmente antes de enviar.
- Se alterar chaves de textos traduzidos, atualize os 18 arquivos de localização em `src/locales/`.
- Siga os padrões estabelecidos de nomenclatura, hooks e variáveis de tema.

### Processo de Envio

1. Faça o fork do repositório
2. Crie sua branch: `git checkout -b feature/recurso-incrivel`
3. Implemente as alterações e rode os testes e verificações locais
4. Envie a branch: `git push origin feature/recurso-incrivel`
5. Abra o Pull Request (as builds no CI serão geradas de forma automatizada)

---

## Agradecimentos

- [Raspberry Pi Imager](https://github.com/raspberrypi/rpi-imager) — Projeto inspirador
- [Tauri](https://tauri.app/) — Framework de desenvolvimento
- [i18next](https://www.i18next.com/) — Internacionalização
- [Lucide](https://lucide.dev/) — Ícones
- [Comunidade Forge](https://github.com/multi-forge/multi-forge/discussions) — Suporte a placas de desenvolvimento e testes
