use crate::error::AppError;

const SERVICE: &str = "maodie-desktop-pet";

fn entry(provider_id: &str) -> Result<keyring::Entry, AppError> {
    if provider_id.trim().is_empty() || provider_id.len() > 64 {
        return Err(AppError::new("invalid_provider", "Provider 标识无效"));
    }
    keyring::Entry::new(SERVICE, provider_id)
        .map_err(|_| AppError::new("credential_store", "无法访问系统安全凭据存储"))
}

pub fn read_api_key(provider_id: &str) -> Result<String, AppError> {
    entry(provider_id)?
        .get_password()
        .map_err(|_| AppError::new("api_key_missing", "尚未配置 API Key"))
}

#[tauri::command]
pub async fn save_api_key(provider_id: String, api_key: String) -> Result<(), AppError> {
    let trimmed = api_key.trim();
    if trimmed.is_empty() || trimmed.len() > 8_192 {
        return Err(AppError::new("invalid_api_key", "API Key 为空或过长"));
    }
    entry(&provider_id)?
        .set_password(trimmed)
        .map_err(|_| AppError::new("credential_store", "API Key 无法写入系统安全凭据存储"))
}

#[tauri::command]
pub async fn delete_api_key(provider_id: String) -> Result<(), AppError> {
    match entry(&provider_id)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(_) => Err(AppError::new("credential_store", "无法清除 API Key")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invalid_provider_does_not_echo_secret() {
        let secret = "sk-never-print-this";
        let error = entry("").unwrap_err();
        assert!(!format!("{error:?}").contains(secret));
    }
}
