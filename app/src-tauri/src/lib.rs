//! LeadForge window: the Rust core. It starts the bundled engine and relays what the engine returns; nothing more.
//! The window has the 21 commands of the seam (app/ui/src/engine.ts, docs/window-actions.md). Each starts the engine
//! as `window <name>` with the window's arguments as one JSON document on stdin, and returns the engine's JSON as
//! it is. The window cannot start a program, read a file or reach the network.
#![forbid(unsafe_code)]

pub mod engine;
mod instance;
mod selftest;

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::sync::{Arc, Mutex as StdMutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde_json::Value;
use tauri::async_runtime::{channel, Mutex};
use tauri::ipc::{Channel, InvokeBody, InvokeResponseBody, Request, Response};
use tauri::{AppHandle, Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder, WindowEvent};

use engine::{EngineCommand, EngineInput, EngineProgram, KillHandle, WindowError};

/// The identifier in tauri.conf.json: the app's folders are `%LOCALAPPDATA%\<this>` and `%APPDATA%\<this>`.
pub const IDENTIFIER: &str = "app.leadforge.window";

/// The core's state: one engine at a time (`gate`), one side process beside a run (`side`), the run's engine, every
/// engine started (so closing the window stops them all), and the log file.
pub struct Core {
    gate: Arc<Mutex<()>>,
    side: Arc<Mutex<()>>,
    run: StdMutex<Option<KillHandle>>,
    children: StdMutex<Vec<KillHandle>>,
    log: StdMutex<Option<PathBuf>>,
}

impl Core {
    fn new() -> Self {
        Core {
            gate: Arc::new(Mutex::new(())),
            side: Arc::new(Mutex::new(())),
            run: StdMutex::new(None),
            children: StdMutex::new(Vec::new()),
            log: StdMutex::new(None),
        }
    }

    fn run_active(&self) -> bool {
        self.run
            .lock()
            .map(|r| r.as_ref().is_some_and(|h| !h.ended()))
            .unwrap_or(false)
    }

    fn register(&self, h: KillHandle) {
        if let Ok(mut all) = self.children.lock() {
            all.retain(|c| !c.ended());
            all.push(h);
        }
    }

    /// Stops every engine the core started. Called when the window closes and when the app exits.
    fn stop_all(&self) {
        if let Ok(all) = self.children.lock() {
            for c in all.iter() {
                c.kill();
            }
        }
    }

    fn log(&self, msg: &str) {
        let secs = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let line = format!("{secs} leadforge-core: {msg}");
        eprintln!("{line}");
        let path = self.log.lock().ok().and_then(|p| p.clone());
        if let Some(path) = path {
            if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
                let _ = writeln!(f, "{line}");
            }
        }
    }
}

/// The error kinds the log names; anything else from the engine is logged as `other` (the log never copies the
/// engine's free text, so a value the window sent cannot reach it).
const LOGGED_KINDS: &[&str] = &[
    "failed",
    "usage",
    "environment",
    "input",
    "source",
    "keyring",
    "missing",
];

/// The one log line per command. Sizes, time and the outcome's kind: never arguments, never answers.
pub fn log_entry(
    cmd: EngineCommand,
    origin: &str,
    outcome: &Result<usize, Value>,
    input_bytes: usize,
    ms: u128,
) -> String {
    let result = match outcome {
        Ok(out_bytes) => format!("ok out={out_bytes}B"),
        Err(e) => {
            let kind = e.get("kind").and_then(Value::as_str).unwrap_or("?");
            let kind = if LOGGED_KINDS.contains(&kind) {
                kind
            } else {
                "other"
            };
            format!("error kind={kind}")
        }
    };
    format!(
        "cmd={} origin={origin} in={input_bytes}B ms={ms} {result}",
        cmd.name()
    )
}

fn busy() -> Value {
    let mut e = WindowError::new(
        "failed",
        "A run is going on; this can be done when it ends or is stopped.",
    );
    e.next = Some("Stop the run on the Run screen, or wait for it to finish.".into());
    e.to_value()
}

/// The engine's working folder: the app's own local data folder, never the folder the app was started from.
fn workdir(app: &AppHandle) -> Result<PathBuf, Value> {
    let dir = app
        .path()
        .app_local_data_dir()
        .map_err(|_| {
            WindowError::new("environment", "The app's local data folder is unknown.").to_value()
        })?
        .join("workspace");
    fs::create_dir_all(&dir).map_err(|_| {
        WindowError::new("environment", "The app's workspace folder cannot be made.").to_value()
    })?;
    Ok(dir)
}

fn program(app: &AppHandle) -> Result<EngineProgram, Value> {
    EngineProgram::locate(app.path().resource_dir().ok().as_deref()).map_err(|e| e.to_value())
}

/// The arguments object exactly as the window sent it.
fn args_of(request: &Request<'_>) -> Result<Value, Value> {
    match request.body() {
        InvokeBody::Json(v) => Ok(v.clone()),
        InvokeBody::Raw(_) => {
            Err(WindowError::new("usage", "The window sent bytes instead of JSON.").to_value())
        }
    }
}

/// Holds the gate (or, beside a run, the side lock) for the life of one engine process.
struct Held(#[allow(dead_code)] Box<dyn Send>);

async fn take_turn(core: &Core, cmd: EngineCommand) -> Result<Held, Value> {
    if core.run_active() {
        if cmd.beside_a_run() {
            return core
                .side
                .clone()
                .try_lock_owned()
                .map(|g| Held(Box::new(g)))
                .map_err(|_| busy());
        }
        return Err(busy());
    }
    Ok(Held(Box::new(core.gate.clone().lock_owned().await)))
}

/// Every one-document command: the engine as `window <name>`, the arguments on stdin, the answer untouched.
async fn one_shot(
    app: &AppHandle,
    core: &Core,
    cmd: EngineCommand,
    args: Value,
) -> Result<Response, Value> {
    let input = EngineInput::from_args(&args).map_err(|e| e.to_value())?;
    drop(args);
    let held = take_turn(core, cmd).await?;
    let engine = program(app)?;
    let dir = workdir(app)?;
    let origin = engine.origin;
    let in_len = input.len();
    let started = Instant::now();
    let (htx, hrx) = std::sync::mpsc::channel::<KillHandle>();
    let task = tauri::async_runtime::spawn_blocking(move || {
        engine::run(
            &engine,
            cmd,
            &input,
            &dir,
            |_| {},
            |h| {
                let _ = htx.send(h);
            },
        )
    });
    if let Ok(h) = hrx.recv_timeout(Duration::from_secs(10)) {
        core.register(h);
    }
    let result = task
        .await
        .map_err(|_| WindowError::new("failed", "The engine task failed.").to_value())
        .and_then(|r| r.map_err(|e| e.to_value()))
        .and_then(|out| engine::answer(&out));
    drop(held);
    let outcome = result.as_ref().map(String::len).map_err(Clone::clone);
    core.log(&log_entry(
        cmd,
        origin,
        &outcome,
        in_len,
        started.elapsed().as_millis(),
    ));
    if cmd == EngineCommand::RunStop {
        let app = app.clone();
        let _ = tauri::async_runtime::spawn_blocking(move || {
            end_run_within(&app.state::<Core>(), Duration::from_secs(10));
        })
        .await;
    }
    result.map(Response::new)
}

/// After `run_stop`: the run's engine gets this long to end by itself, then the core ends it.
fn end_run_within(core: &Core, grace: Duration) {
    let handle = core.run.lock().ok().and_then(|r| r.clone());
    if let Some(h) = handle {
        let until = Instant::now() + grace;
        while !h.ended() && Instant::now() < until {
            std::thread::sleep(Duration::from_millis(50));
        }
        if !h.ended() {
            core.log("cmd=run_stop: the run's engine did not end within 10 s; the core ended it");
            h.kill();
        }
    }
}

/// `run_start`: line 1 of the engine's stdout is the run handle (the command's answer); every later line is one
/// RunEvent, relayed through `events` as it arrives. Nothing in a line is read by the core.
#[tauri::command]
async fn run_start(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
    events: Channel,
) -> Result<Response, Value> {
    let mut args = args_of(&request)?;
    if let Value::Object(map) = &mut args {
        map.remove("events");
    }
    let cmd = EngineCommand::RunStart;
    let input = EngineInput::from_args(&args).map_err(|e| e.to_value())?;
    drop(args);
    let held = take_turn(&core, cmd).await?;
    let engine = program(&app)?;
    let dir = workdir(&app)?;
    let origin = engine.origin;
    let in_len = input.len();
    let started = Instant::now();
    let (first_tx, mut first_rx) = channel::<Result<String, Value>>(1);
    let (htx, hrx) = std::sync::mpsc::channel::<KillHandle>();
    let app2 = app.clone();
    std::thread::spawn(move || {
        let _held = held; // the gate stays held until the run's engine has ended
        let mut first = Some(first_tx.clone());
        let mut lines = 0usize;
        let result = engine::run(
            &engine,
            cmd,
            &input,
            &dir,
            |line| {
                lines += 1;
                if let Some(tx) = first.take() {
                    let _ = tx.blocking_send(Ok(line.to_string()));
                } else {
                    let _ = events.send(InvokeResponseBody::Json(line.to_string()));
                }
            },
            |h| {
                let _ = htx.send(h);
            },
        );
        let core = app2.state::<Core>();
        let outcome: Result<usize, Value> = match &result {
            Ok(out) if out.code == Some(0) => Ok(lines),
            Ok(out) => Err(engine::answer(out).err().unwrap_or(Value::Null)),
            Err(e) => Err(e.to_value()),
        };
        if first.is_some() {
            // no handle line: the engine refused the run (its error object) or broke the contract
            let answer = match &result {
                Ok(out) => engine::answer(out).and_then(|_| {
                    Err(WindowError::new("failed", "The engine started no run.").to_value())
                }),
                Err(e) => Err(e.to_value()),
            };
            let _ = first_tx.blocking_send(answer);
        }
        let dropped = result.as_ref().map(|o| o.dropped_lines).unwrap_or(0);
        core.log(&format!(
            "{} lines={lines} dropped={dropped}",
            log_entry(cmd, origin, &outcome, in_len, started.elapsed().as_millis())
        ));
        let cleared = core.run.lock().map(|mut r| *r = None);
        drop(cleared);
    });
    if let Ok(h) = hrx.recv_timeout(Duration::from_secs(10)) {
        if let Ok(mut r) = core.run.lock() {
            *r = Some(h.clone());
        }
        core.register(h);
    }
    let first = first_rx.recv().await.unwrap_or_else(|| {
        Err(WindowError::new("failed", "The run ended without an answer.").to_value())
    })?;
    core.log("cmd=run_start handle relayed; events follow");
    Ok(Response::new(first))
}

// The 20 one-document commands. Written out one by one: the permission test reads this list and the handler list.
#[tauri::command]
async fn campaign_create(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(
        &app,
        &core,
        EngineCommand::CampaignCreate,
        args_of(&request)?,
    )
    .await
}
#[tauri::command]
async fn run_stop(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::RunStop, args_of(&request)?).await
}
#[tauri::command]
async fn run_status(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::RunStatus, args_of(&request)?).await
}
#[tauri::command]
async fn campaigns_list(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(
        &app,
        &core,
        EngineCommand::CampaignsList,
        args_of(&request)?,
    )
    .await
}
#[tauri::command]
async fn sheet_export(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::SheetExport, args_of(&request)?).await
}
#[tauri::command]
async fn sheet_open(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::SheetOpen, args_of(&request)?).await
}
#[tauri::command]
async fn people_list(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::PeopleList, args_of(&request)?).await
}
#[tauri::command]
async fn person_forget(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::PersonForget, args_of(&request)?).await
}
#[tauri::command]
async fn address_suppress(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(
        &app,
        &core,
        EngineCommand::AddressSuppress,
        args_of(&request)?,
    )
    .await
}
#[tauri::command]
async fn purge_report(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::PurgeReport, args_of(&request)?).await
}
#[tauri::command]
async fn purge_apply(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::PurgeApply, args_of(&request)?).await
}
#[tauri::command]
async fn purge_everything(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(
        &app,
        &core,
        EngineCommand::PurgeEverything,
        args_of(&request)?,
    )
    .await
}
#[tauri::command]
async fn retention_get(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::RetentionGet, args_of(&request)?).await
}
#[tauri::command]
async fn retention_set(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::RetentionSet, args_of(&request)?).await
}
#[tauri::command]
async fn keys_list(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::KeysList, args_of(&request)?).await
}
#[tauri::command]
async fn key_save(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::KeySave, args_of(&request)?).await
}
#[tauri::command]
async fn key_remove(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::KeyRemove, args_of(&request)?).await
}
#[tauri::command]
async fn settings_get(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::SettingsGet, args_of(&request)?).await
}
#[tauri::command]
async fn settings_set(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::SettingsSet, args_of(&request)?).await
}
#[tauri::command]
async fn about(
    app: AppHandle,
    core: State<'_, Core>,
    request: Request<'_>,
) -> Result<Response, Value> {
    one_shot(&app, &core, EngineCommand::About, args_of(&request)?).await
}

pub fn run() {
    let selftest = std::env::args().any(|a| a == "--selftest");
    // A second copy asks the first to come to the front and exits before it opens a window or starts an engine.
    let Some(instance) = instance::claim(IDENTIFIER) else {
        return;
    };
    let app = tauri::Builder::default()
        .manage(Core::new())
        .setup(move |app| {
            let handle = app.handle().clone();
            let core = handle.state::<Core>();
            if let Ok(dir) = handle.path().app_log_dir() {
                if fs::create_dir_all(&dir).is_ok() {
                    if let Ok(mut l) = core.log.lock() {
                        *l = Some(dir.join("core.log"));
                    }
                }
            }
            core.log(&format!(
                "started (selftest={selftest}, stand-in engine={})",
                engine::STAND_IN
            ));
            let mut builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("LeadForge")
                .inner_size(1180.0, 760.0)
                .min_inner_size(900.0, 600.0);
            if selftest {
                builder = builder.initialization_script(selftest::PROBE);
            }
            builder.build()?;
            instance.watch_for_focus(handle.clone());
            if selftest {
                selftest::start(handle.clone());
            }
            Ok(())
        })
        .on_page_load(|webview, payload| {
            webview.app_handle().state::<Core>().log(&format!(
                "page {:?}: {}",
                payload.event(),
                payload.url()
            ));
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } | WindowEvent::Destroyed = event {
                let core = window.app_handle().state::<Core>();
                core.stop_all();
            }
        })
        .invoke_handler(tauri::generate_handler![
            campaign_create,
            run_start,
            run_stop,
            run_status,
            campaigns_list,
            sheet_export,
            sheet_open,
            people_list,
            person_forget,
            address_suppress,
            purge_report,
            purge_apply,
            purge_everything,
            retention_get,
            retention_set,
            keys_list,
            key_save,
            key_remove,
            settings_get,
            settings_set,
            about
        ])
        .build(tauri::generate_context!())
        .expect("error while building the LeadForge window");
    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            let core = handle.state::<Core>();
            core.stop_all();
            core.log("exit: every engine stopped");
        }
    });
}

/// Logs a line from the self-test and the instance guard (they live in their own modules).
pub(crate) fn core_log(app: &AppHandle, msg: &str) {
    app.state::<Core>().log(msg);
}
