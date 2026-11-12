//! LeadForge window: the Rust core. It starts the bundled engine and relays what the engine returns; nothing more.
//! The window has one command today, `engine_version`. It cannot start a program, read a file or reach the network.
#![forbid(unsafe_code)]

pub mod engine;

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::async_runtime::Mutex;
use tauri::{AppHandle, Manager, State};

use engine::{EngineCommand, EngineError, EngineProgram, EngineVersion};

/// One engine run at a time: the engine alone touches the data, and only one copy of it runs.
/// An async mutex: its guard is held across the await on the engine's thread.
#[derive(Default)]
struct EngineGate(Mutex<()>);

/// `--smoke` on the app's own command line: exit a few seconds after the window's first `engine_version` call.
struct Smoke(bool);

/// Append one line to `<app log dir>/core.log` and to stderr (visible in debug builds).
fn log_line(app: &AppHandle, msg: &str) {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let line = format!("{secs} leadforge-core: {msg}");
    eprintln!("{line}");
    if let Ok(dir) = app.path().app_log_dir() {
        if fs::create_dir_all(&dir).is_ok() {
            if let Ok(mut f) = OpenOptions::new()
                .create(true)
                .append(true)
                .open(dir.join("core.log"))
            {
                let _ = writeln!(f, "{line}");
            }
        }
    }
}

/// The engine's working folder: the app's own local data folder, never the folder the app was started from.
fn workdir(app: &AppHandle) -> Result<PathBuf, EngineError> {
    let dir = app
        .path()
        .app_local_data_dir()
        .map_err(|e| EngineError::new("not_found", format!("no local data folder: {e}")))?
        .join("workspace");
    fs::create_dir_all(&dir).map_err(|e| {
        EngineError::new("not_found", format!("cannot make {}: {e}", dir.display()))
    })?;
    Ok(dir)
}

/// The window's only command. Takes no input; replies with the engine's version or an `EngineError`.
#[tauri::command]
async fn engine_version(
    app: AppHandle,
    gate: State<'_, EngineGate>,
    smoke: State<'_, Smoke>,
) -> Result<EngineVersion, EngineError> {
    let _held = gate
        .0
        .try_lock()
        .map_err(|_| EngineError::new("busy", "the engine is already running"))?;
    let program = EngineProgram::locate(app.path().resource_dir().ok().as_deref())?;
    let dir = workdir(&app)?;
    let origin = program.origin;
    let result = tauri::async_runtime::spawn_blocking(move || {
        engine::run(&program, EngineCommand::Version, &dir, |_| {})
            .and_then(|out| engine::parse_version(&out).map(|v| (v, out.elapsed)))
    })
    .await
    .map_err(|e| EngineError::new("failed", format!("engine task failed: {e}")))?;

    let reply = match result {
        Ok((version, elapsed)) => {
            let millis = u64::try_from(elapsed.as_millis()).unwrap_or(u64::MAX);
            log_line(
                &app,
                &format!("engine_version ok: version={version} origin={origin} millis={millis}"),
            );
            Ok(EngineVersion {
                version,
                origin,
                millis,
            })
        }
        Err(e) => {
            log_line(
                &app,
                &format!(
                    "engine_version error: kind={} message={}",
                    e.kind, e.message
                ),
            );
            Err(e)
        }
    };
    if smoke.0 {
        let handle = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(4));
            log_line(&handle, "smoke: exiting");
            handle.exit(0);
        });
    }
    reply
}

pub fn run() {
    let smoke = std::env::args().any(|a| a == "--smoke");
    tauri::Builder::default()
        .manage(EngineGate::default())
        .manage(Smoke(smoke))
        .setup(move |app| {
            let handle = app.handle().clone();
            log_line(&handle, &format!("started (smoke={smoke})"));
            if smoke {
                // A smoke run that never hears from the window is a failure, not a hang.
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(90));
                    log_line(&handle, "smoke: no engine_version call within 90 s");
                    handle.exit(1);
                });
            }
            Ok(())
        })
        .on_page_load(|webview, payload| {
            log_line(
                webview.app_handle(),
                &format!("page {:?}: {}", payload.event(), payload.url()),
            );
        })
        .invoke_handler(tauri::generate_handler![engine_version])
        .run(tauri::generate_context!())
        .expect("error while running the LeadForge window");
}
