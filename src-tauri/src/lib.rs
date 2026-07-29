mod commands;
mod error;

use commands::llm::{cancel_chat_stream, start_chat_stream, validate_llm_config, ChatState};
use commands::secrets::{delete_api_key, save_api_key};
use commands::trash::move_paths_to_trash;
use tauri::menu::{CheckMenuItem, Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, Manager, WebviewWindow};

fn toggle(window: &WebviewWindow) {
    if window.is_visible().unwrap_or(false) {
        let _ = window.hide();
    } else {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[tauri::command]
fn toggle_chat_window(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("chat") {
        toggle(&window);
    }
}

#[tauri::command]
fn show_settings_window(app: tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("settings") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[tauri::command]
fn notify_chat_closed(app: tauri::AppHandle) {
    let _ = app.emit_to("pet", "chat://closed", ());
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::new().build())
        .manage(ChatState::default())
        .setup(|app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            let show = MenuItem::with_id(app, "show", "显示/隐藏桌宠", true, None::<&str>)?;
            let recall = MenuItem::with_id(app, "recall", "唤回到主显示器", true, None::<&str>)?;
            let settings = MenuItem::with_id(app, "settings", "设置…", true, None::<&str>)?;
            let top = CheckMenuItem::with_id(app, "top", "始终置顶", true, true, None::<&str>)?;
            let mute =
                CheckMenuItem::with_id(app, "mute", "静音（预留）", false, false, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &recall, &settings, &top, &mute, &quit])?;
            TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("pet") {
                            toggle(&window);
                        }
                    }
                    "recall" => {
                        if let Some(window) = app.get_webview_window("pet") {
                            let _ = window.center();
                            let _ = window.show();
                        }
                    }
                    "settings" => show_settings_window(app.clone()),
                    "top" => {
                        if let Some(window) = app.get_webview_window("pet") {
                            if let Ok(value) = window.is_always_on_top() {
                                let _ = window.set_always_on_top(!value);
                            }
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            move_paths_to_trash,
            save_api_key,
            delete_api_key,
            validate_llm_config,
            start_chat_stream,
            cancel_chat_stream,
            toggle_chat_window,
            show_settings_window,
            notify_chat_closed
        ])
        .run(tauri::generate_context!())
        .expect("failed to run maodie desktop pet");
}
