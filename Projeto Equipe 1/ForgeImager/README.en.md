<h2 align="center">
  🔧 ForgeImager
  <br><br>
</h2>

### About

**ForgeImager** is the official desktop tool of the MultiForge ecosystem for downloading, configuring, and safely flashing operating system images to single-board computers (SBCs) and repurposed ARM TV Boxes (Amlogic, Rockchip, Allwinner).

Built with **Tauri v2 + React 19 + Rust**, it pairs a lightweight native Rust I/O backend with a responsive, modern UI featuring a 3D MultiForge design theme.

### 🌟 Key Features

- **Ext4 Direct Userspace Injection (`crates/forge-write-conf`):** Injects Wi-Fi credentials, first-boot scripts, and user settings directly into the target disk's ext4 partition without mounting or requiring host root privileges.
- **Dynamic Catalog via GitHub Releases:** Integrates with remote release manifests (`release_assets/forge-images.json`) for automated image downloads and SHA256 checksum verification.
- **Safe Streaming & Real-Time Verification:** Multithreaded on-the-fly decompression (`.xz`, `.gz`, `.zst`, `.bz2`) with block-by-block SHA-256 verification.
- **Qualcomm EDL / QDL Emergency Flashing:** Integrated Sahara/Firehose protocol (`VID 0x05C6`) for unbricking Qualcomm-based hardware.
- **3D MultiForge Visual Identity:** Industrial dark/light theme with automatic system sync.
- **Cross-Platform Native Builds:** Linux, Windows, and macOS (x64 and ARM64).
- **Multi-Language Interface:** 18 supported languages with automatic locale detection.

## 📦 Download

Prebuilt binaries are available in [Releases](https://github.com/multi-forge/multi-forge/releases).

| <a href="https://github.com/multi-forge/multi-forge/releases"><img src="https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/apple.svg" width="24"><br><strong>macOS</strong></a> | <a href="https://github.com/multi-forge/multi-forge/releases"><img src="https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/windows11.svg" width="24"><br><strong>Windows</strong></a> | <a href="https://github.com/multi-forge/multi-forge/releases"><img src="https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/linux.svg" width="24"><br><strong>Linux</strong></a> |
|:---:|:---:|:---:|
| Intel & Apple Silicon | x64 & ARM64 | x64 & ARM64 |
| <code>.dmg</code> / <code>.app.zip</code> | <code>.exe</code> / <code>.msi</code> | <code>.deb</code> / <code>.AppImage</code> |

## How It Works

1. **Pick a manufacturer.** Choose one of the supported SBC/TV box vendors, or load your own local image file.
2. **Pick a board.** Boards show photos and hardware metadata.
3. **Pick an image.** Select desktop or server, kernel branch, and stability tier.
4. **Flash.** The app downloads, decompresses, writes, injects autoconfig, and verifies for you.

## 🛠️ Development & Building

### Quick Scripts (Windows)
```bash
# Launch development mode with hot-reload (Frontend + Rust IPC):
.\start-dev.bat

# Build production installers (.msi / .exe):
.\build.bat

# Run compiled release binary:
.\start-app.bat
```

### Manual Build (Cross-platform)
```bash
# 1. Install frontend dependencies
pnpm install

# 2. Run in development mode
pnpm tauri dev

# 3. Build release bundles
pnpm tauri build
```

Setup, IPC architecture details, and environment prerequisites are documented in [DEVELOPMENT.md](DEVELOPMENT.md).

## Credits

- Based on [Armbian Imager](https://github.com/armbian/imager) — original project
- [Tauri](https://tauri.app/) — Framework
- [i18next](https://www.i18next.com/) — Internationalization
- [Lucide](https://lucide.dev/) — Icons

---

<p align="center">
  <sub>Made with ❤️ by the Forge community</sub>
</p>
