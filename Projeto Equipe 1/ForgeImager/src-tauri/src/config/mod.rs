//! Centralized hard-coded values, URLs, and configuration options.
//! Allows dead_code: some consts are only referenced under platform cfg blocks.

#![allow(dead_code)]

/// Application metadata
pub mod app {
    /// Application name used for cache directories
    pub const NAME: &str = "forge-imager";

    /// User agent for HTTP requests
    pub const USER_AGENT: &str = "Forge-Imager/1.0";
}

/// API endpoints and URLs
pub mod urls {
    /// GitHub repository identifier (e.g., "multi-forge/multi-forge").
    /// Overridable at runtime via `FORGE_GITHUB_REPO`.
    pub fn github_repo() -> String {
        std::env::var("FORGE_GITHUB_REPO").unwrap_or_else(|_| "multi-forge/multi-forge".to_string())
    }

    /// GitHub releases API base for the project.
    /// Overridable at runtime via `FORGE_API_BASE` for custom setups.
    pub fn api_base() -> String {
        std::env::var("FORGE_API_BASE").unwrap_or_else(|_| format!("https://api.github.com/repos/{}", github_repo()))
    }

    /// Connectivity probe: GitHub API root — always reachable, no auth, no server needed.
    pub fn health() -> String {
        "https://api.github.com".to_string()
    }

    /// GitHub releases API endpoint.
    pub fn releases() -> String {
        format!("{}/releases", api_base())
    }

    /// GitHub releases API — latest release.
    pub fn latest_release() -> String {
        format!("{}/releases/latest", api_base())
    }

    /// GitHub releases API for a specific tag.
    pub fn release_by_tag(tag: &str) -> String {
        format!("{}/releases/tags/{}", api_base(), tag)
    }

    /// Raw GitHub content base URL.
    pub fn raw_repo_base() -> String {
        format!("https://raw.githubusercontent.com/{}/main", github_repo())
    }

    /// Remote manifest URL in repository.
    pub fn manifest_url() -> String {
        format!("{}/forge-images.json", raw_repo_base())
    }

    /// Alternative remote manifest URL.
    pub fn manifest_url_alt() -> String {
        format!("{}/Forge-images.json", raw_repo_base())
    }

    /// Base URL for board images (placeholder — swap for your CDN/GitHub raw URL).
    pub const BOARD_IMAGES_BASE: &str = "https://raw.githubusercontent.com/multi-forge/multi-forge/main/images/boards/";

    /// Default image size label (kept for compatibility).
    pub const BOARD_IMAGE_SIZE: &str = "480";

    /// Base URL for vendor logos (placeholder — swap for your CDN/GitHub raw URL).
    pub const VENDOR_IMAGES_BASE: &str = "https://raw.githubusercontent.com/multi-forge/multi-forge/main/images/vendors/480/";

    /// QDL blob base (not used without a server; kept to avoid compile errors).
    pub fn qdl_blob_base() -> String {
        format!("{}/qdl/blob/", api_base())
    }
}

/// Download and decompression settings
pub mod download {
    /// Decompression buffer size (8 MB)
    pub const DECOMPRESS_BUFFER_SIZE: usize = 8 * 1024 * 1024;

    /// Chunk size for streaming writes (4 MB)
    pub const CHUNK_SIZE: usize = 4 * 1024 * 1024;
}

/// Flash operation settings
pub mod flash {
    /// Write chunk size (4 MB)
    pub const CHUNK_SIZE: usize = 4 * 1024 * 1024;

    /// Quick erase size - zeros written before flashing (10 MB)
    pub const QUICK_ERASE_SIZE: usize = 10 * 1024 * 1024;

    /// Erase chunk size (1 MB)
    pub const ERASE_CHUNK_SIZE: usize = 1024 * 1024;

    /// Delay after unmount before writing (milliseconds)
    pub const UNMOUNT_DELAY_MS: u64 = 500;
}

/// Log file management settings
pub mod log_files {
    /// Maximum number of log files to retain (oldest are deleted)
    pub const MAX_LOG_FILES: usize = 10;
}

/// Progress logging intervals
pub mod logging {
    /// SHA256 calculation buffer size
    pub const SHA_BUFFER_SIZE: usize = 8192;

    /// Download progress log interval (MB)
    pub const DOWNLOAD_LOG_INTERVAL_MB: u64 = 10;

    /// Write progress log interval (MB)
    pub const WRITE_LOG_INTERVAL_MB: u64 = 512;

    /// Decompression progress log interval (MB)
    pub const DECOMPRESS_LOG_INTERVAL_MB: u64 = 100;

    /// Linux sync interval for flush operations
    pub const LINUX_SYNC_INTERVAL: u64 = 32 * 1024 * 1024;
}

/// Log paste service settings
pub mod paste {
    /// Maximum log file size to upload (5 MB)
    pub const MAX_LOG_SIZE: u64 = 5 * 1024 * 1024;

    /// Maximum log lines to process
    pub const MAX_LOG_LINES: usize = 10_000;
}

/// HTTP client settings
pub mod http {
    /// Connection timeout in seconds
    pub const CONNECT_TIMEOUT_SECS: u64 = 30;

    /// Request timeout in seconds
    pub const REQUEST_TIMEOUT_SECS: u64 = 300;

    /// Short timeout for quick requests like board info (10 seconds)
    pub const SHORT_TIMEOUT_SECS: u64 = 10;

    /// Client identification header name for the Forge API
    pub const CLIENT_HEADER_NAME: &str = "X-Forge-Client";

    /// Client identification header value for Forge Imager
    pub const CLIENT_HEADER_VALUE: &str = "forge-imager";
}

/// Image filtering constants
pub mod images {
    /// Filter value for empty preinstalled application
    pub const EMPTY_FILTER: &str = "__EMPTY__";

    /// Temporary download file suffix
    pub const DOWNLOAD_SUFFIX: &str = ".downloading";
}

/// Cache management settings
pub mod cache {
    /// Default maximum cache size (20 GB)
    pub const DEFAULT_MAX_SIZE: u64 = 20 * 1024 * 1024 * 1024;
}
