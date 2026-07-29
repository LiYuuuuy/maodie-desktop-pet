use crate::commands::secrets::read_api_key;
use crate::error::AppError;
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::Arc;
use tauri::{AppHandle, Emitter, State};
use tokio::sync::Mutex;
use tokio_util::sync::CancellationToken;
use url::Url;

const SYSTEM_PROMPT: &str = include_str!("../../../src/skills/maodie.system.md");

#[derive(Clone, Default)]
pub struct ChatState {
    cancellations: Arc<Mutex<HashMap<String, CancellationToken>>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PublicProviderConfig {
    provider: String,
    base_url: String,
    model: String,
    temperature: f32,
    max_output_tokens: u32,
    timeout_ms: u64,
    api_key_ref: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ChatMessage {
    role: String,
    content: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ChatRequest {
    messages: Vec<ChatMessage>,
    config: PublicProviderConfig,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ValidationResult {
    valid: bool,
    message: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct StreamPayload {
    request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    delta: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    message: Option<String>,
}

fn validate_public_config(config: &PublicProviderConfig) -> Result<Url, AppError> {
    if config.provider != "openai-compatible" {
        return Err(AppError::new(
            "unsupported_provider",
            "当前仅支持 OpenAI-compatible Provider",
        ));
    }
    let base = Url::parse(&config.base_url)
        .map_err(|_| AppError::new("invalid_base_url", "Base URL 格式无效"))?;
    if base.scheme() != "https" && !(cfg!(debug_assertions) && base.scheme() == "http") {
        return Err(AppError::new(
            "insecure_base_url",
            "Base URL 必须使用 HTTPS",
        ));
    }
    if config.model.trim().is_empty() {
        return Err(AppError::new("invalid_model", "模型名称不能为空"));
    }
    if !(0.0..=2.0).contains(&config.temperature)
        || config.max_output_tokens == 0
        || !(1_000..=300_000).contains(&config.timeout_ms)
    {
        return Err(AppError::new(
            "invalid_config",
            "Temperature、输出长度或超时设置无效",
        ));
    }
    Ok(base)
}

fn endpoint(base: &Url, path: &str) -> Result<Url, AppError> {
    let value = base.as_str().trim_end_matches('/');
    Url::parse(&format!("{value}/{path}"))
        .map_err(|_| AppError::new("invalid_base_url", "无法构造 Provider 请求地址"))
}

#[tauri::command]
pub async fn validate_llm_config(
    config: PublicProviderConfig,
) -> Result<ValidationResult, AppError> {
    let base = validate_public_config(&config)?;
    let key_ref = config.api_key_ref.as_deref().unwrap_or("openai-compatible");
    let key = read_api_key(key_ref)?;
    let response = reqwest::Client::new()
        .get(endpoint(&base, "models")?)
        .bearer_auth(key)
        .timeout(std::time::Duration::from_millis(config.timeout_ms))
        .send()
        .await
        .map_err(|_| AppError::new("network_error", "无法连接到模型服务"))?;
    if response.status().is_success() {
        Ok(ValidationResult {
            valid: true,
            message: "连接成功".into(),
        })
    } else {
        Ok(ValidationResult {
            valid: false,
            message: format!("服务返回 HTTP {}", response.status().as_u16()),
        })
    }
}

fn emit(
    app: &AppHandle,
    event: &str,
    request_id: &str,
    delta: Option<String>,
    message: Option<String>,
) {
    let _ = app.emit_to(
        "chat",
        event,
        StreamPayload {
            request_id: request_id.to_owned(),
            delta,
            message,
        },
    );
}

async fn run_stream(
    app: AppHandle,
    state: ChatState,
    request_id: String,
    request: ChatRequest,
    token: CancellationToken,
) {
    let result = async {
        let base = validate_public_config(&request.config)?;
        let key_ref = request
            .config
            .api_key_ref
            .as_deref()
            .unwrap_or("openai-compatible");
        let key = read_api_key(key_ref)?;
        let mut messages = vec![json!({ "role": "system", "content": SYSTEM_PROMPT })];
        messages.extend(
            request
                .messages
                .into_iter()
                .map(|message| json!({ "role": message.role, "content": message.content })),
        );
        let response = reqwest::Client::new()
            .post(endpoint(&base, "chat/completions")?)
            .bearer_auth(key)
            .timeout(std::time::Duration::from_millis(request.config.timeout_ms))
            .json(&json!({
                "model": request.config.model,
                "messages": messages,
                "temperature": request.config.temperature,
                "max_tokens": request.config.max_output_tokens,
                "stream": true
            }))
            .send()
            .await
            .map_err(|_| AppError::new("network_error", "无法连接到模型服务"))?;
        if !response.status().is_success() {
            return Err(AppError::new(
                if response.status().as_u16() == 401 { "authentication" } else { "provider_error" },
                format!("模型服务返回 HTTP {}", response.status().as_u16()),
            ));
        }
        let mut stream = response.bytes_stream();
        let mut buffer = String::new();
        loop {
            tokio::select! {
                _ = token.cancelled() => {
                    emit(&app, "chat://cancelled", &request_id, None, None);
                    return Ok(());
                }
                chunk = stream.next() => {
                    let Some(chunk) = chunk else { break };
                    let bytes = chunk.map_err(|_| AppError::new("stream_error", "流式响应中断"))?;
                    buffer.push_str(&String::from_utf8_lossy(&bytes));
                    while let Some(boundary) = buffer.find("\n\n") {
                        let event = buffer[..boundary].to_owned();
                        buffer.drain(..boundary + 2);
                        for line in event.lines().filter_map(|line| line.strip_prefix("data: ")) {
                            if line == "[DONE]" {
                                emit(&app, "chat://complete", &request_id, None, None);
                                return Ok(());
                            }
                            if let Ok(value) = serde_json::from_str::<Value>(line) {
                                if let Some(delta) = value["choices"][0]["delta"]["content"].as_str() {
                                    emit(&app, "chat://delta", &request_id, Some(delta.to_owned()), None);
                                }
                            }
                        }
                    }
                }
            }
        }
        emit(&app, "chat://complete", &request_id, None, None);
        Ok::<(), AppError>(())
    }
    .await;
    if let Err(error) = result {
        emit(&app, "chat://error", &request_id, None, Some(error.message));
    }
    state.cancellations.lock().await.remove(&request_id);
}

#[tauri::command]
pub async fn start_chat_stream(
    app: AppHandle,
    state: State<'_, ChatState>,
    request: ChatRequest,
) -> Result<String, AppError> {
    validate_public_config(&request.config)?;
    if request.messages.is_empty() || request.messages.len() > 50 {
        return Err(AppError::new("invalid_messages", "对话消息数量无效"));
    }
    let request_id = uuid::Uuid::new_v4().to_string();
    let token = CancellationToken::new();
    let owned_state = state.inner().clone();
    owned_state
        .cancellations
        .lock()
        .await
        .insert(request_id.clone(), token.clone());
    tauri::async_runtime::spawn(run_stream(
        app,
        owned_state,
        request_id.clone(),
        request,
        token,
    ));
    Ok(request_id)
}

#[tauri::command]
pub async fn cancel_chat_stream(
    state: State<'_, ChatState>,
    request_id: String,
) -> Result<(), AppError> {
    if let Some(token) = state.cancellations.lock().await.get(&request_id) {
        token.cancel();
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> PublicProviderConfig {
        PublicProviderConfig {
            provider: "openai-compatible".into(),
            base_url: "https://example.com/v1".into(),
            model: "test".into(),
            temperature: 0.5,
            max_output_tokens: 100,
            timeout_ms: 10_000,
            api_key_ref: None,
        }
    }

    #[test]
    fn validates_safe_configuration() {
        assert!(validate_public_config(&config()).is_ok());
    }

    #[test]
    fn rejects_insecure_and_invalid_configuration() {
        let mut value = config();
        value.base_url = "http://example.com/v1".into();
        if !cfg!(debug_assertions) {
            assert_eq!(
                validate_public_config(&value).unwrap_err().code,
                "insecure_base_url"
            );
        }
        value.temperature = 4.0;
        assert_eq!(
            validate_public_config(&value).unwrap_err().code,
            "invalid_config"
        );
    }
}
