//! Asset caching: serves board images and vendor logos from the local picture
//! cache as base64 data URIs, downloading from the Forge API on first access.

use base64::Engine;
use crate::config;
use crate::picture_cache;

static EMBEDDED_BTV_BOARD: &[u8] = include_bytes!("../../../../images/boards/480/btv-e10.png");
static EMBEDDED_BTV_VENDOR: &[u8] = include_bytes!("../../../../images/vendors/480/btv.png");

/// Get a board image from cache as a `data:image/png;base64,...` URI, downloading
/// if needed. Returns embedded asset if btv-e10.
#[tauri::command]
pub async fn get_cached_board_image(board_slug: String) -> Result<Option<String>, String> {
    let slug_lower = board_slug.to_lowercase();
    if slug_lower == "btv-e10" || slug_lower == "btve10" || slug_lower.contains("btv") {
        let b64 = base64::engine::general_purpose::STANDARD.encode(EMBEDDED_BTV_BOARD);
        return Ok(Some(format!("data:image/png;base64,{}", b64)));
    }

    let url = format!(
        "{}{}/{}.png",
        config::urls::BOARD_IMAGES_BASE,
        config::urls::BOARD_IMAGE_SIZE,
        board_slug
    );

    let path = picture_cache::get_asset("boards", &board_slug, &url).await;
    match path {
        Some(p) => Ok(picture_cache::read_as_data_uri(&p).await),
        None => Ok(None),
    }
}

/// Get a vendor logo from cache as a `data:image/png;base64,...` URI, downloading
/// if needed. Returns embedded asset if btv.
#[tauri::command]
pub async fn get_cached_vendor_logo(vendor_slug: String) -> Result<Option<String>, String> {
    let slug_lower = vendor_slug.to_lowercase();
    if slug_lower == "btv" {
        let b64 = base64::engine::general_purpose::STANDARD.encode(EMBEDDED_BTV_VENDOR);
        return Ok(Some(format!("data:image/png;base64,{}", b64)));
    }

    let url = format!("{}{}.png", config::urls::VENDOR_IMAGES_BASE, vendor_slug);

    let path = picture_cache::get_asset("vendors", &vendor_slug, &url).await;
    match path {
        Some(p) => Ok(picture_cache::read_as_data_uri(&p).await),
        None => Ok(None),
    }
}
