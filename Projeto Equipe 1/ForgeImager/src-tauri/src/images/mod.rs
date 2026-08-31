//! Fetching board, image, and vendor data from GitHub Releases and Forge REST/Manifest APIs,
//! with on-disk caching of responses for offline and fast usage.

#![allow(dead_code)]

mod filters;
mod models;

pub use filters::{map_board, map_images};
pub use models::{
    ApiBoardSummary, ApiDownloadInfo, ApiImage, ApiQdl, ApiVendor, BoardInfo, ForgeManifest,
    GhRelease, ImageInfo,
};

use crate::config;
use crate::utils::assets_dir;
use crate::{log_debug, log_error, log_info, log_warn};

use once_cell::sync::Lazy;
use reqwest::header::{HeaderMap, HeaderValue, ACCEPT, AUTHORIZATION};
use std::collections::HashMap;
use std::path::PathBuf;

/// Shared HTTP client for JSON API endpoints (15s timeout).
static API_CLIENT: Lazy<reqwest::Client> = Lazy::new(|| {
    let mut headers = HeaderMap::new();
    headers.insert(
        config::http::CLIENT_HEADER_NAME,
        HeaderValue::from_static(config::http::CLIENT_HEADER_VALUE),
    );
    headers.insert(
        ACCEPT,
        HeaderValue::from_static("application/vnd.github.v3+json, application/json, text/plain, */*"),
    );

    reqwest::Client::builder()
        .default_headers(headers)
        .user_agent(config::app::USER_AGENT)
        .connect_timeout(std::time::Duration::from_secs(
            config::http::CONNECT_TIMEOUT_SECS,
        ))
        .timeout(std::time::Duration::from_secs(
            config::http::SHORT_TIMEOUT_SECS + 5,
        ))
        .build()
        .expect("Failed to create API HTTP client")
});

/// Helper to build a GET request with optional GitHub token authorization
fn build_get_request(url: &str) -> reqwest::RequestBuilder {
    let mut req = API_CLIENT.get(url);
    if let Ok(token) = std::env::var("FORGE_GITHUB_TOKEN").or_else(|_| std::env::var("GITHUB_TOKEN")) {
        let trimmed = token.trim();
        if !trimmed.is_empty() {
            let auth_val = if trimmed.starts_with("ghp_") || trimmed.starts_with("github_pat_") || trimmed.starts_with("Bearer ") {
                if trimmed.starts_with("Bearer ") {
                    trimmed.to_string()
                } else {
                    format!("Bearer {}", trimmed)
                }
            } else {
                format!("token {}", trimmed)
            };
            if let Ok(val) = HeaderValue::from_str(&auth_val) {
                req = req.header(AUTHORIZATION, val);
            }
        }
    }
    req
}

/// Get the path for a named cache file inside the assets directory
fn get_cache_path(name: &str) -> PathBuf {
    assets_dir().join(format!("{}.json", name))
}

/// Save data to a cache file atomically via a uniquely-named temp file + rename.
fn save_cache(name: &str, data: &str) {
    let path = get_cache_path(name);
    let data = data.to_string();
    tokio::task::spawn_blocking(move || {
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        // pid+timestamp tmp name keeps concurrent writers from clobbering.
        let pid = std::process::id();
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let tmp_path = path.with_extension(format!("json.{}.{}.tmp", pid, nanos));
        if let Err(e) = std::fs::write(&tmp_path, &data) {
            log_warn!("images", "Failed to write cache temp file: {}", e);
            return;
        }
        if let Err(e) = std::fs::rename(&tmp_path, &path) {
            log_warn!("images", "Failed to rename cache file: {}", e);
            let _ = std::fs::remove_file(&tmp_path);
        } else {
            log_debug!("images", "Saved cache to {}", path.display());
        }
    });
}

/// Load data from a cache file
async fn load_cache(name: &str) -> Result<String, String> {
    let path = get_cache_path(name);
    if !path.exists() {
        return Err(format!(
            "No cached {} data available (first launch while offline)",
            name
        ));
    }

    let data = tokio::fs::read_to_string(&path).await.map_err(|e| {
        log_error!("images", "Failed to read {} cache: {}", name, e);
        format!("Failed to read cached data: {}", e)
    })?;

    log_debug!(
        "images",
        "Loaded {} data from local cache ({})",
        name,
        path.display()
    );
    Ok(data)
}

/// Delete the pre-migration API cache file.
pub fn cleanup_legacy_cache() {
    let legacy_path = assets_dir().join("api-images.json");
    if legacy_path.exists() {
        let _ = std::fs::remove_file(&legacy_path);
    }
}

/// Check if a release asset name looks like a flashable OS image
fn is_image_asset(name: &str) -> bool {
    let lower = name.to_lowercase();
    // Exclude checksums, signatures, logs, and package installers
    if lower.ends_with(".sha256")
        || lower.ends_with(".sha")
        || lower.ends_with(".sha256sum")
        || lower.ends_with(".sha512")
        || lower.ends_with(".md5")
        || lower.ends_with(".asc")
        || lower.ends_with(".sig")
        || lower.ends_with(".txt")
        || lower.ends_with(".json")
        || lower.ends_with(".yaml")
        || lower.ends_with(".yml")
        || lower.ends_with(".exe")
        || lower.ends_with(".msi")
        || lower.ends_with(".deb")
        || lower.ends_with(".dmg")
        || lower.ends_with(".appimage")
        || lower.ends_with(".rpm")
    {
        return false;
    }

    lower.ends_with(".img.xz")
        || lower.ends_with(".img.gz")
        || lower.ends_with(".img.zst")
        || lower.ends_with(".img.bz2")
        || lower.ends_with(".img")
        || lower.ends_with(".iso")
        || lower.ends_with(".raw.xz")
        || lower.ends_with(".tar.xz")
        || lower.ends_with(".qdl.zip")
        || (lower.ends_with(".zip") && (lower.contains("image") || lower.contains("forge") || lower.contains("os")))
}

/// Parsed metadata extracted from an image asset name
struct ParsedAssetMeta {
    board_slug: String,
    board_name: String,
    vendor_slug: String,
    vendor_name: String,
    soc: Option<String>,
    arch: Option<String>,
    distro: String,
    variant: String,
    kernel_branch: String,
    kernel_version: String,
    application: Option<String>,
    format: String,
}

/// Parse asset filename and release into image and board properties
fn parse_image_asset_name(filename: &str, _tag: &str) -> ParsedAssetMeta {
    let lower = filename.to_lowercase();

    // 1. Board detection
    let (board_slug, board_name, vendor_slug, vendor_name, soc, arch) = if lower.contains("btv-e10") || lower.contains("btve10") || lower.contains("btv_e10") || lower.contains("btv") {
        ("btv-e10".to_string(), "BTV E10".to_string(), "btv".to_string(), "BTV".to_string(), Some("Amlogic S905X2".to_string()), Some("arm64".to_string()))
    } else {
        // Dynamic fallback: extract clean name from filename
        let clean = filename
            .trim_end_matches(".xz")
            .trim_end_matches(".gz")
            .trim_end_matches(".zst")
            .trim_end_matches(".bz2")
            .trim_end_matches(".img")
            .trim_end_matches(".iso")
            .trim_end_matches(".zip");
        let slug = clean.replace('_', "-").to_lowercase();
        let display_name = clean
            .split(&['-', '_'][..])
            .map(|w| {
                let mut c = w.chars();
                match c.next() {
                    None => String::new(),
                    Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
                }
            })
            .collect::<Vec<_>>()
            .join(" ");
        (slug, display_name, "multi-forge".to_string(), "Multi-Forge".to_string(), None, Some("arm64".to_string()))
    };

    // 2. Distro
    let distro = if lower.contains("alpine") {
        "Alpine".to_string()
    } else if lower.contains("ubuntu") {
        "Ubuntu".to_string()
    } else if lower.contains("debian") || lower.contains("bookworm") || lower.contains("bullseye") {
        "Debian".to_string()
    } else if lower.contains("arch") {
        "Arch Linux".to_string()
    } else if lower.contains("kali") {
        "Kali Linux".to_string()
    } else if lower.contains("openmediavault") || lower.contains("omv") {
        "OpenMediaVault".to_string()
    } else {
        "ForgeOS".to_string()
    };

    // 3. Variant
    let variant = if lower.contains("desktop") || lower.contains("xfce") || lower.contains("gnome") || lower.contains("kde") {
        "desktop".to_string()
    } else if lower.contains("minimal") || lower.contains("server") || lower.contains("cli") || lower.contains("lite") {
        "minimal".to_string()
    } else if lower.contains("iot") {
        "iot".to_string()
    } else {
        "standard".to_string()
    };

    // 4. Kernel
    let kernel_branch = if lower.contains("edge") {
        "edge".to_string()
    } else if lower.contains("legacy") {
        "legacy".to_string()
    } else {
        "current".to_string()
    };

    let kernel_version = if lower.contains("6.6") {
        "6.6.y".to_string()
    } else if lower.contains("6.1") {
        "6.1.y".to_string()
    } else if lower.contains("5.15") {
        "5.15.y".to_string()
    } else {
        "6.x".to_string()
    };

    // 5. Application
    let application = if lower.contains("totem") || lower.contains("totem-ai") {
        Some("totem-ai".to_string())
    } else if lower.contains("gateway") || lower.contains("iot-gateway") {
        Some("iot-gateway".to_string())
    } else {
        None
    };

    let format = if lower.contains("qdl") {
        "qdl".to_string()
    } else {
        "sd".to_string()
    };

    ParsedAssetMeta {
        board_slug,
        board_name,
        vendor_slug,
        vendor_name,
        soc,
        arch,
        distro,
        variant,
        kernel_branch,
        kernel_version,
        application,
        format,
    }
}

/// Fallback built-in catalog if network is offline and no cache exists
fn get_builtin_catalog() -> (Vec<ApiBoardSummary>, Vec<ApiImage>, Vec<ApiVendor>) {
    let boards = vec![
        ApiBoardSummary {
            slug: "btv-e10".to_string(),
            name: "BTV E10".to_string(),
            vendor_slug: "btv".to_string(),
            vendor_name: "BTV".to_string(),
            support_tier: "platinum".to_string(),
            image_count: 1,
            has_desktop: true,
            promoted: true,
            image_url: None,
            soc: Some("Amlogic S905X2".to_string()),
            architecture: Some("arm64".to_string()),
            summary: Some("2GB LPDDR4, 8GB eMMC, Realtek RTL8189FTV Wi-Fi AP 25MHz.".to_string()),
            qdl: None,
        },
    ];

    let images = vec![
        ApiImage {
            id: "btv-e10-desktop".to_string(),
            board_slug: "btv-e10".to_string(),
            variant: "desktop".to_string(),
            distribution: "ForgeOS".to_string(),
            release: "v1.0.0".to_string(),
            kernel_branch: "current".to_string(),
            kernel_version: "6.1.y".to_string(),
            application: Some("totem-ai".to_string()),
            promoted: true,
            stability: "stable".to_string(),
            format: "sd".to_string(),
            storage: None,
            companions: vec![],
            display_variants: vec![],
            download: ApiDownloadInfo {
                file_url: "https://github.com/multi-forge/multi-forge/releases/download/v1.0.0/forgeos-btv-e10.img.xz".to_string(),
                direct_url: "https://github.com/multi-forge/multi-forge/releases/download/v1.0.0/forgeos-btv-e10.img.xz".to_string(),
                sha_url: Some("https://github.com/multi-forge/multi-forge/releases/download/v1.0.0/forgeos-btv-e10.img.xz.sha256".to_string()),
                asc_url: None,
                torrent_url: None,
                size_bytes: 891_289_600,
                updated_at: Some("2026-08-20".to_string()),
            },
        },
    ];

    let vendors = vec![
        ApiVendor {
            slug: "btv".to_string(),
            name: "BTV".to_string(),
            logo_url: None,
            website: Some("https://github.com/multi-forge/multi-forge".to_string()),
            description: Some("Amlogic S905X2 and TV box platforms".to_string()),
            board_count: 1,
            partner_tier: Some("platinum".to_string()),
        },
    ];

    (boards, images, vendors)
}

/// Fetch all catalog data from GitHub Releases and/or remote manifest
async fn fetch_catalog_from_github() -> Result<(Vec<ApiBoardSummary>, Vec<ApiImage>, Vec<ApiVendor>), String> {
    let releases_url = if let Ok(tag) = std::env::var("FORGE_RELEASE_TAG") {
        if !tag.is_empty() {
            config::urls::release_by_tag(&tag)
        } else {
            config::urls::releases()
        }
    } else {
        config::urls::releases()
    };

    log_info!("images", "Fetching releases from {}", releases_url);

    let mut board_map: HashMap<String, ApiBoardSummary> = HashMap::new();
    let mut vendor_map: HashMap<String, ApiVendor> = HashMap::new();
    let mut image_list: Vec<ApiImage> = Vec::new();

    // 1. Try to fetch GitHub releases
    let releases_resp = build_get_request(&releases_url).send().await;

    match releases_resp {
        Ok(resp) => {
            if resp.status().is_success() {
                let body_text = resp.text().await.unwrap_or_default();
                let releases: Vec<GhRelease> = if let Ok(rels) = serde_json::from_str::<Vec<GhRelease>>(&body_text) {
                    rels
                } else if let Ok(single_rel) = serde_json::from_str::<GhRelease>(&body_text) {
                    vec![single_rel]
                } else {
                    log_warn!("images", "Failed to deserialize GitHub releases JSON");
                    vec![]
                };

                log_info!("images", "Found {} GitHub releases", releases.len());

                for release in &releases {
                    let tag = &release.tag_name;
                    let is_pre = release.prerelease.unwrap_or(false);

                    // A. Check if release contains a manifest asset (e.g. forge-images.json or manifest.json)
                    for asset in &release.assets {
                        let a_lower = asset.name.to_lowercase();
                        if a_lower == "forge-images.json" || a_lower == "manifest.json" || a_lower == "images.json" || a_lower == "boards.json" {
                            log_info!("images", "Found manifest asset {} in release {}", asset.name, tag);
                            if let Ok(m_resp) = build_get_request(&asset.browser_download_url).send().await {
                                if let Ok(manifest) = m_resp.json::<ForgeManifest>().await {
                                    for b in manifest.boards {
                                        board_map.insert(b.slug.clone(), b);
                                    }
                                    for v in manifest.vendors {
                                        vendor_map.insert(v.slug.clone(), v);
                                    }
                                    for img in manifest.images {
                                        image_list.push(img);
                                    }
                                }
                            }
                        }
                    }

                    // B. Scan all image assets in the release
                    let mut sha_map: HashMap<String, String> = HashMap::new();
                    for asset in &release.assets {
                        let a_lower = asset.name.to_lowercase();
                        if a_lower.ends_with(".sha256") || a_lower.ends_with(".sha") || a_lower.ends_with(".sha256sum") {
                            let base_target = asset.name
                                .trim_end_matches(".sha256")
                                .trim_end_matches(".sha")
                                .trim_end_matches(".sha256sum");
                            sha_map.insert(base_target.to_string(), asset.browser_download_url.clone());
                        }
                    }

                    for asset in &release.assets {
                        if !is_image_asset(&asset.name) {
                            continue;
                        }

                        let parsed = parse_image_asset_name(&asset.name, tag);
                        let sha_url = sha_map.get(&asset.name).cloned();

                        let img_id = format!("{}-{}-{}", parsed.board_slug, parsed.variant, tag);
                        let is_desktop = parsed.variant == "desktop";

                        let image_entry = ApiImage {
                            id: img_id,
                            board_slug: parsed.board_slug.clone(),
                            variant: parsed.variant.clone(),
                            distribution: parsed.distro.clone(),
                            release: tag.clone(),
                            kernel_branch: parsed.kernel_branch.clone(),
                            kernel_version: parsed.kernel_version.clone(),
                            application: parsed.application.clone(),
                            promoted: is_desktop,
                            stability: if is_pre { "edge".to_string() } else { "stable".to_string() },
                            format: parsed.format.clone(),
                            storage: None,
                            companions: vec![],
                            display_variants: vec![],
                            download: ApiDownloadInfo {
                                file_url: asset.browser_download_url.clone(),
                                direct_url: asset.browser_download_url.clone(),
                                sha_url,
                                asc_url: None,
                                torrent_url: None,
                                size_bytes: asset.size,
                                updated_at: asset.updated_at.clone(),
                            },
                        };

                        image_list.push(image_entry);

                        // Update or insert board
                        let entry = board_map.entry(parsed.board_slug.clone()).or_insert_with(|| ApiBoardSummary {
                            slug: parsed.board_slug.clone(),
                            name: parsed.board_name.clone(),
                            vendor_slug: parsed.vendor_slug.clone(),
                            vendor_name: parsed.vendor_name.clone(),
                            support_tier: "platinum".to_string(),
                            image_count: 0,
                            has_desktop: is_desktop,
                            promoted: is_desktop,
                            image_url: None,
                            soc: parsed.soc.clone(),
                            architecture: parsed.arch.clone(),
                            summary: Some(format!("{} image for {}", parsed.distro, parsed.board_name)),
                            qdl: None,
                        });
                        entry.image_count += 1;
                        if is_desktop {
                            entry.has_desktop = true;
                        }

                        // Update or insert vendor
                        vendor_map.entry(parsed.vendor_slug.clone()).or_insert_with(|| ApiVendor {
                            slug: parsed.vendor_slug.clone(),
                            name: parsed.vendor_name.clone(),
                            logo_url: None,
                            website: Some(config::urls::raw_repo_base()),
                            description: Some(format!("Manufacturer {}", parsed.vendor_name)),
                            board_count: 1,
                            partner_tier: Some("platinum".to_string()),
                        });
                    }
                }
            } else {
                log_warn!("images", "GitHub releases API returned status {}", resp.status());
            }
        }
        Err(e) => {
            log_warn!("images", "Failed to query GitHub releases API: {}", e);
        }
    }

    // 2. Try fetching raw manifest from main branch (forge-images.json)
    let raw_manifest_url = config::urls::manifest_url();
    if let Ok(resp) = build_get_request(&raw_manifest_url).send().await {
        if resp.status().is_success() {
            if let Ok(manifest) = resp.json::<ForgeManifest>().await {
                log_info!("images", "Loaded remote manifest from {}", raw_manifest_url);
                for b in manifest.boards {
                    board_map.insert(b.slug.clone(), b);
                }
                for v in manifest.vendors {
                    vendor_map.insert(v.slug.clone(), v);
                }
                for img in manifest.images {
                    image_list.push(img);
                }
            }
        }
    }

    // If we obtained data, cache it to disk and return
    if !board_map.is_empty() && !image_list.is_empty() {
        let boards: Vec<ApiBoardSummary> = board_map.into_values().collect();
        let vendors: Vec<ApiVendor> = vendor_map.into_values().collect();

        if let Ok(b_json) = serde_json::to_string(&boards) {
            save_cache("releases_boards", &b_json);
        }
        if let Ok(i_json) = serde_json::to_string(&image_list) {
            save_cache("releases_images", &i_json);
        }
        if let Ok(v_json) = serde_json::to_string(&vendors) {
            save_cache("releases_vendors", &v_json);
        }

        log_info!(
            "images",
            "Catalog ready: {} boards, {} images, {} vendors",
            boards.len(),
            image_list.len(),
            vendors.len()
        );
        return Ok((boards, image_list, vendors));
    }

    // 3. Fallback to cached releases if offline or rate-limited
    if let (Ok(b_data), Ok(i_data), Ok(v_data)) = (
        load_cache("releases_boards").await,
        load_cache("releases_images").await,
        load_cache("releases_vendors").await,
    ) {
        if let (Ok(boards), Ok(images), Ok(vendors)) = (
            serde_json::from_str::<Vec<ApiBoardSummary>>(&b_data),
            serde_json::from_str::<Vec<ApiImage>>(&i_data),
            serde_json::from_str::<Vec<ApiVendor>>(&v_data),
        ) {
            log_info!("images", "Loaded catalog from local cache");
            return Ok((boards, images, vendors));
        }
    }

    // 4. Default built-in catalog fallback
    log_info!("images", "Using built-in default catalog");
    Ok(get_builtin_catalog())
}

/// Fetch all boards from GitHub Releases / cache
pub async fn fetch_boards() -> Result<Vec<ApiBoardSummary>, String> {
    let (boards, _, _) = fetch_catalog_from_github().await?;
    Ok(boards)
}

/// Fetch images for a specific board from GitHub Releases / cache
pub async fn fetch_images_for_board(
    slug: &str,
    _variant: Option<&str>,
    _distribution: Option<&str>,
    _branch: Option<&str>,
    _promoted: Option<bool>,
) -> Result<Vec<ApiImage>, String> {
    let (_, images, _) = fetch_catalog_from_github().await?;
    let filtered: Vec<ApiImage> = images.into_iter().filter(|img| img.board_slug == slug).collect();
    Ok(filtered)
}

/// Fetch all vendors from GitHub Releases / cache
pub async fn fetch_vendors() -> Result<Vec<ApiVendor>, String> {
    let (_, _, vendors) = fetch_catalog_from_github().await?;
    Ok(vendors)
}

/// Fetch a single board's QDL block (if available)
pub async fn fetch_board_qdl(_slug: &str) -> Option<ApiQdl> {
    None
}
