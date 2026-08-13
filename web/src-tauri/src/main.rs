#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{AppHandle, Manager};

struct BackendState(Mutex<Option<Child>>);

fn backend_port() -> u16 {
    std::env::var("OPS_AGENT_BACKEND_PORT")
        .ok()
        .and_then(|v| v.parse::<u16>().ok())
        .unwrap_or(8000)
}

fn is_backend_up(port: u16) -> bool {
    TcpStream::connect(("127.0.0.1", port)).is_ok()
}

fn backend_command_path(app: &AppHandle) -> PathBuf {
    if cfg!(debug_assertions) {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
        return root.join("..").join("scripts").join("start_backend_dev.sh");
    }

    #[cfg(target_os = "windows")]
    let bin_name = "ops-agent-backend.exe";
    #[cfg(not(target_os = "windows"))]
    let bin_name = "ops-agent-backend";

    app.path()
        .resource_dir()
        .expect("resource dir unavailable")
        .join("bin")
        .join(bin_name)
}

async fn wait_backend_ready(port: u16) -> bool {
    for _ in 0..80 {
        if is_backend_up(port) {
            return true;
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }
    false
}

fn start_backend(app: &AppHandle) -> Option<Child> {
    let port = backend_port();
    if is_backend_up(port) {
        return None;
    }

    let cmd_path = backend_command_path(app);
    eprintln!("starting backend from {}", cmd_path.display());
    let mut cmd = if cfg!(debug_assertions) {
        #[cfg(target_os = "windows")]
        {
            let mut c = Command::new("bash");
            c.arg(&cmd_path);
            c
        }
        #[cfg(not(target_os = "windows"))]
        {
            Command::new(&cmd_path)
        }
    } else {
        Command::new(&cmd_path)
    };

    cmd.env("OPS_AGENT_BACKEND_PORT", port.to_string())
        .env("OPS_AGENT_RELOAD", "false")
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());

    match cmd.spawn() {
        Ok(child) => Some(child),
        Err(error) => {
            eprintln!("failed to start backend from {}: {error}", cmd_path.display());
            None
        }
    }
}

#[tauri::command]
async fn backend_base_url() -> Result<String, String> {
    let port = backend_port();
    if !wait_backend_ready(port).await {
        return Err(format!("backend did not become ready on port {port}"));
    }
    Ok(format!("http://127.0.0.1:{port}"))
}

#[tokio::main]
async fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(BackendState(Mutex::new(None)))
        .setup(|app| {
            let app_handle = app.handle().clone();
            let child = start_backend(&app_handle);
            if let Some(process) = child {
                let state = app.state::<BackendState>();
                *state.0.lock().expect("backend state poisoned") = Some(process);
            }

            let port = backend_port();
            tauri::async_runtime::spawn(async move {
                if !wait_backend_ready(port).await {
                    eprintln!("backend did not become ready on port {port}");
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_base_url])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.app_handle().state::<BackendState>();
                let child = {
                    let mut guard = state.0.lock().expect("backend state poisoned");
                    guard.take()
                };
                if let Some(mut child) = child {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri app");
}
