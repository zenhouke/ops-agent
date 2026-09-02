#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Manager, State};
use uuid::Uuid;

struct BackendState {
    child: Mutex<Option<Child>>,
    port: u16,
    access_token: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendConfig {
    base_url: String,
    access_token: String,
}

fn requested_backend_port() -> Option<u16> {
    std::env::var("OPS_AGENT_BACKEND_PORT")
        .ok()
        .and_then(|v| v.parse::<u16>().ok())
}

fn select_backend_port() -> Result<u16, String> {
    if let Some(port) = requested_backend_port() {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Err(format!("requested backend port {port} is already in use"));
        }
        return Ok(port);
    }

    for _ in 0..32 {
        let listener = TcpListener::bind(("127.0.0.1", 0))
            .map_err(|error| format!("failed to allocate backend port: {error}"))?;
        let port = listener
            .local_addr()
            .map_err(|error| format!("failed to inspect backend port: {error}"))?
            .port();
        if port >= 30_000 {
            return Ok(port);
        }
    }
    Err("failed to allocate a backend port above 30000".to_string())
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

async fn wait_backend_ready(port: u16, access_token: &str) -> bool {
    let client = reqwest::Client::new();
    let verify_url = format!("http://127.0.0.1:{port}/api/auth/verify");
    for _ in 0..80 {
        if let Ok(response) = client
            .post(&verify_url)
            .bearer_auth(access_token)
            .send()
            .await
        {
            if response.status() == reqwest::StatusCode::NO_CONTENT {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }
    false
}

fn start_backend(app: &AppHandle, port: u16, access_token: &str) -> Result<Child, String> {
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
        .env("OPS_AGENT_AUTH_DISABLED", "false")
        .env("OPS_AGENT_API_TOKEN", access_token)
        .env("OPS_AGENT_DESKTOP", "true")
        .env("OPS_AGENT_RELOAD", "false")
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());

    if !cfg!(debug_assertions) {
        match app.path().app_data_dir() {
            Ok(data_dir) => {
                cmd.env("OPS_AGENT_DATA_DIR", data_dir);
            }
            Err(error) => {
                eprintln!("failed to resolve app data directory: {error}");
                return Err(format!("failed to resolve app data directory: {error}"));
            }
        }
    }

    cmd.spawn()
        .map_err(|error| format!("failed to start backend from {}: {error}", cmd_path.display()))
}

#[tauri::command]
async fn backend_config(state: State<'_, BackendState>) -> Result<BackendConfig, String> {
    if !wait_backend_ready(state.port, &state.access_token).await {
        let port = state.port;
        return Err(format!("backend did not become ready on port {port}"));
    }
    Ok(BackendConfig {
        base_url: format!("http://127.0.0.1:{}", state.port),
        access_token: state.access_token.clone(),
    })
}

#[tokio::main]
async fn main() {
    let port = select_backend_port().expect("unable to select secure backend port");
    let access_token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(BackendState {
            child: Mutex::new(None),
            port,
            access_token,
        })
        .setup(|app| {
            let app_handle = app.handle().clone();
            let state = app.state::<BackendState>();
            let child = start_backend(&app_handle, state.port, &state.access_token)
                .map_err(std::io::Error::other)?;
            *state.child.lock().expect("backend state poisoned") = Some(child);

            let port = state.port;
            let access_token = state.access_token.clone();
            tauri::async_runtime::spawn(async move {
                if !wait_backend_ready(port, &access_token).await {
                    eprintln!("backend did not become ready on port {port}");
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_config])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.app_handle().state::<BackendState>();
                let child = {
                    let mut guard = state.child.lock().expect("backend state poisoned");
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
