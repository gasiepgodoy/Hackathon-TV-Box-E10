# ForgeImager

Ferramenta desktop oficial do ecossistema MultiForge para download, parametrização e gravação de sistemas operacionais em computadores de placa única (SBCs) e TV Boxes (Amlogic, Rockchip, Allwinner).

Desenvolvido em **Tauri v2, React 19 e Rust**, combinando backend nativo de alta performance com interface gráfica responsiva.

---

## Recursos Implementados

- **Injeção Userspace em Ext4 (`crates/forge-write-conf`):** Injeta credenciais de Wi-Fi, usuários e parâmetros de primeiro boot diretamente na partição ext4 do dispositivo de destino sem necessidade de montagem (`mount`) ou privilégios de root no host.
- **Catálogo Dinâmico via GitHub Releases:** Integração com manifestos remotos (`release_assets/forge-images.json`) para download de imagens oficiais com validação de hash SHA-256.
- **Gravação Segura e Streaming:** Suporte a descompressão multithread (`.xz`, `.gz`, `.zst`, `.bz2`) com verificação de integridade bloco a bloco.
- **Recuperação de Emergência Qualcomm EDL / QDL:** Protocolo Sahara/Firehose integrado (`VID 0x05C6`) para gravação em modo MaskROM.
- **Compilações Nativas Multiplataforma:** Suporte a Linux, Windows e macOS (x86_64 e ARM64).
- **Internacionalização:** Suporte a 18 idiomas com detecção automática do sistema operacional.

---

## Compatibilidade de Plataformas

| Plataforma | Arquitetura | Detalhes |
|------------|-------------|----------|
| Windows | x86_64 / ARM64 | Executável `.exe` e instalador `.msi` (requer privilégios de Administrador) |
| Linux | x86_64 / ARM64 | Pacotes `.deb` e binários independentes `.AppImage` (integração com UDisks2/Polkit) |
| macOS | Intel / Apple Silicon | Pacotes `.dmg` e `.app` com suporte a autenticação biométrica |

---

## Desenvolvimento e Compilação

### Dependências
- Node.js >= 18 e pnpm >= 9
- Rust Toolchain (cargo, rustc >= 1.77)
- Build Essentials (no Linux: `libwebkit2gtk-4.1-dev`, `libayatana-appindicator3-dev`)

### Comandos de Compilação

```bash
cd ForgeImager

# Instalação de dependências:
pnpm install

# Execução em modo de desenvolvimento (com hot-reload):
pnpm tauri dev

# Geração de pacotes de produção:
pnpm tauri build
```

---

## Créditos e Licença

- Baseado na arquitetura do Armbian Imager
- Framework Tauri (v2)
- Licença MIT (consulte o arquivo LICENSE na raiz do repositório)
