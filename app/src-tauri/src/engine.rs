//! The one place in the core that starts a program: the bundled LeadForge engine.
//!
//! Rules (permission-check/tests/permissions.rs checks the first by reading the source):
//! 1. `Command::new` appears once in the crate, in [`spawn_engine`].
//! 2. The program is a fixed path: the engine inside the app's own resources (release) or the worktree's `.venv`
//!    (debug builds only). Nothing the window sends ever reaches the path.
//! 3. The argv is fixed per [`EngineCommand`], a closed enum: `window <name>` (or `--json version`). The window's
//!    arguments travel only as one JSON document on the engine's stdin, never in argv.
//! 4. The core never interprets a result: a good answer goes back to the window as the engine wrote it.

use std::ffi::OsString;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::Value;

/// While the real `leadforge window` commands do not exist yet, the core starts the stand-in engine
/// (`test-resources/standin/leadforge_window_standin.py`) with the same interpreter, flags, argv tail, stdin and
/// stdout. THE SWITCH: set this to `false` (tests/standin_switch.rs then requires the stand-in's line out of
/// tauri.bundle.conf.json, so it is no longer shipped).
pub const STAND_IN: bool = true;

/// Every engine command the core can run. The window's 21 commands, plus `Version` for the core's own use.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum EngineCommand {
    Version,
    CampaignCreate,
    RunStart,
    RunStop,
    RunStatus,
    CampaignsList,
    SheetExport,
    SheetOpen,
    PeopleList,
    PersonForget,
    AddressSuppress,
    PurgeReport,
    PurgeApply,
    PurgeEverything,
    RetentionGet,
    RetentionSet,
    KeysList,
    KeySave,
    KeyRemove,
    SettingsGet,
    SettingsSet,
    About,
}

impl EngineCommand {
    /// The 21 window commands, in the order of the seam (app/ui/src/engine.ts).
    pub const WINDOW: [EngineCommand; 21] = [
        Self::CampaignCreate,
        Self::RunStart,
        Self::RunStop,
        Self::RunStatus,
        Self::CampaignsList,
        Self::SheetExport,
        Self::SheetOpen,
        Self::PeopleList,
        Self::PersonForget,
        Self::AddressSuppress,
        Self::PurgeReport,
        Self::PurgeApply,
        Self::PurgeEverything,
        Self::RetentionGet,
        Self::RetentionSet,
        Self::KeysList,
        Self::KeySave,
        Self::KeyRemove,
        Self::SettingsGet,
        Self::SettingsSet,
        Self::About,
    ];

    /// The name: the Tauri command, the engine's `window <name>` and the log's `cmd=`.
    pub fn name(self) -> &'static str {
        match self {
            Self::Version => "version",
            Self::CampaignCreate => "campaign_create",
            Self::RunStart => "run_start",
            Self::RunStop => "run_stop",
            Self::RunStatus => "run_status",
            Self::CampaignsList => "campaigns_list",
            Self::SheetExport => "sheet_export",
            Self::SheetOpen => "sheet_open",
            Self::PeopleList => "people_list",
            Self::PersonForget => "person_forget",
            Self::AddressSuppress => "address_suppress",
            Self::PurgeReport => "purge_report",
            Self::PurgeApply => "purge_apply",
            Self::PurgeEverything => "purge_everything",
            Self::RetentionGet => "retention_get",
            Self::RetentionSet => "retention_set",
            Self::KeysList => "keys_list",
            Self::KeySave => "key_save",
            Self::KeyRemove => "key_remove",
            Self::SettingsGet => "settings_get",
            Self::SettingsSet => "settings_set",
            Self::About => "about",
        }
    }

    /// The engine's argv after the interpreter prefix. Fixed per variant; nothing from the window.
    pub fn args(self) -> Vec<OsString> {
        match self {
            Self::Version => vec!["--json".into(), "version".into()],
            other => vec!["window".into(), other.name().into()],
        }
    }

    /// The longest the engine may take before the core stops it. Four classes; `timeouts_are_pinned_per_command`
    /// lists every command's class.
    pub fn timeout(self) -> Duration {
        let secs = match self {
            Self::RunStart => 12 * 60 * 60,
            Self::RunStop | Self::RunStatus | Self::About | Self::Version => 30,
            Self::SheetExport
            | Self::PurgeReport
            | Self::PurgeApply
            | Self::PurgeEverything
            | Self::PersonForget => 600,
            _ => 120,
        };
        Duration::from_secs(secs)
    }

    /// May run beside a running `run_start` (its own engine process); every other command waits its turn.
    pub fn beside_a_run(self) -> bool {
        matches!(self, Self::RunStop | Self::RunStatus)
    }

    /// `run_start` answers in JSON lines until the run ends; every other command answers one JSON document.
    pub fn streams(self) -> bool {
        self == Self::RunStart
    }
}

/// The interpreter flags: UTF-8 I/O and isolated mode (no PYTHON* variables, no user site, no current folder on
/// the import path).
fn interpreter_flags() -> Vec<OsString> {
    ["-X", "utf8", "-I"].iter().map(OsString::from).collect()
}

/// Where the engine lives and how it is started. Fixed at build time; see [`EngineProgram::locate`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineProgram {
    /// The interpreter the core starts.
    pub program: PathBuf,
    /// Arguments that always come first: interpreter flags and the entry (`-m leadforge` or the stand-in script).
    pub prefix: Vec<OsString>,
    /// `bundled` or `dev-venv`, for the log.
    pub origin: &'static str,
}

impl EngineProgram {
    fn with_entry(program: PathBuf, standin: Option<PathBuf>, origin: &'static str) -> Self {
        let mut prefix = interpreter_flags();
        match standin {
            Some(script) => prefix.push(script.into_os_string()),
            None => prefix.extend(["-m", "leadforge"].map(OsString::from)),
        }
        EngineProgram {
            program,
            prefix,
            origin,
        }
    }

    /// The engine in a release build: python.org's embeddable Python inside the app's resources.
    pub fn bundled(resource_dir: &Path) -> Self {
        let engine = resource_dir.join("engine");
        let standin = STAND_IN.then(|| engine.join("standin").join("leadforge_window_standin.py"));
        Self::with_entry(engine.join("python").join("python.exe"), standin, "bundled")
    }

    /// The engine in a debug build: the worktree's `.venv`. Compiled into debug builds (and tests) only.
    #[cfg(debug_assertions)]
    pub fn dev_venv() -> Self {
        let here = Path::new(env!("CARGO_MANIFEST_DIR"));
        let standin = STAND_IN.then(|| {
            here.join("test-resources")
                .join("standin")
                .join("leadforge_window_standin.py")
        });
        let program = here
            .join("..")
            .join("..")
            .join(".venv")
            .join("Scripts")
            .join("python.exe");
        Self::with_entry(program, standin, "dev-venv")
    }

    /// The real engine module, whatever [`STAND_IN`] says (the core's own `Version`).
    pub fn real(&self) -> Self {
        let mut prefix = interpreter_flags();
        prefix.extend(["-m", "leadforge"].map(OsString::from));
        EngineProgram {
            program: self.program.clone(),
            prefix,
            origin: self.origin,
        }
    }

    /// Debug builds use the dev venv; release builds only ever use the bundled engine.
    pub fn locate(resource_dir: Option<&Path>) -> Result<Self, WindowError> {
        #[cfg(debug_assertions)]
        {
            let _ = resource_dir;
            Ok(Self::dev_venv())
        }
        #[cfg(not(debug_assertions))]
        {
            resource_dir.map(Self::bundled).ok_or_else(|| {
                WindowError::new("environment", "The app's resource folder is unknown.")
            })
        }
    }
}

/// The error object the window receives when the core itself could not get an answer:
/// `{ kind, message, details, next }`, the same shape the engine writes on a non-zero exit.
/// Never holds the window's arguments.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct WindowError {
    pub kind: &'static str,
    pub message: String,
    pub details: Vec<String>,
    pub next: Option<String>,
}

impl WindowError {
    pub fn new(kind: &'static str, message: impl Into<String>) -> Self {
        WindowError {
            kind,
            message: message.into(),
            details: Vec::new(),
            next: None,
        }
    }

    pub fn to_value(&self) -> Value {
        serde_json::to_value(self).unwrap_or(Value::Null)
    }
}

/// The window's arguments as the engine's stdin: one JSON document. Its `Debug` never shows the bytes
/// (`key_save` carries a key's value).
pub struct EngineInput(Vec<u8>);

/// The largest arguments document the core passes on (1 MiB).
pub const MAX_INPUT_BYTES: usize = 1024 * 1024;
/// The largest one-document answer the core reads (8 MiB); past it the engine is stopped.
pub const MAX_OUTPUT_BYTES: usize = 8 * 1024 * 1024;
/// The longest line of a `run_start` stream (64 KiB); longer lines are not relayed.
pub const MAX_LINE_BYTES: usize = 64 * 1024;
const STDERR_TAIL_BYTES: usize = 4 * 1024;

impl EngineInput {
    /// The arguments object, `{}` when there are none. Anything but an object is refused.
    pub fn from_args(args: &Value) -> Result<Self, WindowError> {
        let doc = match args {
            Value::Null => Value::Object(Default::default()),
            Value::Object(_) => args.clone(),
            _ => {
                return Err(WindowError::new(
                    "usage",
                    "The window sent arguments that are not an object.",
                ))
            }
        };
        let bytes = serde_json::to_vec(&doc)
            .map_err(|_| WindowError::new("usage", "The arguments are not JSON."))?;
        if bytes.len() > MAX_INPUT_BYTES {
            return Err(WindowError::new(
                "usage",
                "The arguments are larger than 1 MiB.",
            ));
        }
        Ok(EngineInput(bytes))
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

impl std::fmt::Debug for EngineInput {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "EngineInput(<{} bytes>)", self.0.len())
    }
}

/// How an engine process came to its end.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EndedBy {
    /// It exited by itself.
    Exit,
    /// The core ended it: the wait after `run_stop` ran out, a refused start's wait ran out, or the window closed.
    Core,
    /// The command's time limit ([`EngineCommand::timeout`]) ran out and the core ended it.
    Timeout,
}

/// What one finished engine run produced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineOutput {
    /// The exit code; `None` when the core ended the process (the code would be the core's, not the engine's).
    pub code: Option<i32>,
    /// The whole stdout of a one-document command; empty for a stream (its lines went to `on_line`).
    pub stdout: String,
    pub stderr_tail: String,
    pub elapsed: Duration,
    /// Stream lines that were not one JSON document or were too long, so not relayed.
    pub dropped_lines: usize,
    pub ended_by: EndedBy,
    /// A stream's last non-blank line was over [`MAX_LINE_BYTES`] (so it was not relayed).
    pub last_line_too_long: bool,
    /// A one-document answer was over [`MAX_OUTPUT_BYTES`] (so it was not read).
    pub too_big: bool,
}

/// The process and what the core decided about its end. Behind one lock, so a deadline set from another thread
/// (`run_stop`) and the run loop's poll never race.
struct Proc {
    child: Child,
    /// The core ends the process at this moment if it has not ended by then.
    end_at: Option<Instant>,
    /// The core ended it (not the engine, not the time limit).
    by_core: bool,
}

/// Stops a running engine from another thread (`run_stop`, the window closing).
#[derive(Clone)]
pub struct KillHandle(Arc<Mutex<Proc>>);

impl KillHandle {
    /// Ends the engine now (the window closing). A process that already ended is left as it was.
    pub fn kill(&self) {
        if let Ok(mut p) = self.0.lock() {
            if matches!(p.child.try_wait(), Ok(None)) {
                p.by_core = true;
            }
            let _ = p.child.kill();
            let _ = p.child.wait();
        }
    }

    /// The engine may run for at most `wait` from now; then the run loop ends it. An earlier deadline stays.
    pub fn end_within(&self, wait: Duration) {
        if let Ok(mut p) = self.0.lock() {
            let at = Instant::now() + wait;
            p.end_at = Some(p.end_at.map_or(at, |e| e.min(at)));
        }
    }

    /// Whether the engine has ended.
    pub fn ended(&self) -> bool {
        self.0
            .lock()
            .map(|mut p| !matches!(p.child.try_wait(), Ok(None)))
            .unwrap_or(true)
    }
}

/// After `run_stop` answered ok, the run's engine gets this long to write its end event; then the core ends it.
/// The engine checks its stop flag once per business, and one business can take more than a minute; a stop that
/// is waited for is clean and can be continued, an ended process is not. Tests pass a short wait to [`after_stop`].
pub const STOP_WAIT: Duration = Duration::from_secs(90);

/// After a refused start (line 1 not a run handle), the engine gets this long to end by itself; then it is ended.
pub const REFUSAL_WAIT: Duration = Duration::from_secs(5);

/// After `run_stop`: if it answered ok and the run's engine is still going, give it `wait` to end by itself
/// (the core ends it then). Returns whether a wait was set. The app passes [`STOP_WAIT`].
pub fn after_stop(stop: &Result<String, Value>, run: Option<&KillHandle>, wait: Duration) -> bool {
    match (stop, run) {
        (Ok(_), Some(h)) if !h.ended() => {
            h.end_within(wait);
            true
        }
        _ => false,
    }
}

/// One stdout line of a stream, as the reader saw it.
enum Item {
    Json(String),
    NotJson,
    TooLong,
    Blank,
}

/// Environment variables the engine inherits; everything else is dropped.
const ENV_KEEP: &[&str] = &[
    "SYSTEMROOT",
    "WINDIR",
    "SYSTEMDRIVE",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "COMPUTERNAME",
    "USERNAME",
    "HOMEDRIVE",
    "HOMEPATH",
];

/// The only `Command::new` in the crate.
fn spawn_engine(
    engine: &EngineProgram,
    cmd: EngineCommand,
    workdir: &Path,
) -> Result<Child, WindowError> {
    if !engine.program.is_file() {
        let mut e = WindowError::new("environment", "The bundled engine is missing.");
        e.next = Some("Reinstall LeadForge.".into());
        return Err(e);
    }
    let mut c = Command::new(&engine.program);
    c.args(&engine.prefix)
        .args(cmd.args())
        .current_dir(workdir)
        .env_clear()
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    for key in ENV_KEEP {
        if let Some(v) = std::env::var_os(key) {
            c.env(key, v);
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        c.creation_flags(CREATE_NO_WINDOW);
    }
    // The OS error names no argument (arguments never travel in argv).
    c.spawn()
        .map_err(|e| WindowError::new("environment", format!("The engine did not start: {e}")))
}

/// Run one engine command to its end, its timeout or a kill. The input goes to stdin and stdin is closed.
/// A stream (`run_start`) hands every stdout line that is one JSON document to `on_line` as it arrives;
/// a one-document command collects stdout up to [`MAX_OUTPUT_BYTES`]. `on_spawn` receives the kill handle.
/// A timeout or an answer over the limit is the core's error.
pub fn run(
    engine: &EngineProgram,
    cmd: EngineCommand,
    input: &EngineInput,
    workdir: &Path,
    mut on_line: impl FnMut(&str),
    on_spawn: impl FnOnce(KillHandle),
) -> Result<EngineOutput, WindowError> {
    let out = run_raw(
        engine,
        cmd,
        input,
        workdir,
        cmd.timeout(),
        |item| {
            if let Item::Json(line) = item {
                on_line(&line);
            }
        },
        on_spawn,
    )?;
    if out.ended_by == EndedBy::Timeout {
        let mut e = WindowError::new(
            "failed",
            format!(
                "The engine did not answer within {} s and was stopped.",
                cmd.timeout().as_secs()
            ),
        );
        e.next = Some("Try again; if it keeps happening, the workspace may be very large.".into());
        return Err(e);
    }
    if out.too_big {
        return Err(WindowError::new(
            "failed",
            "The engine's answer was larger than 8 MiB and was not read.",
        ));
    }
    Ok(out)
}

/// The engine run itself: every stream line goes to `on_item` in order (blank, not JSON and too long ones too),
/// and the output says how the process ended instead of turning a timeout into an error.
fn run_raw(
    engine: &EngineProgram,
    cmd: EngineCommand,
    input: &EngineInput,
    workdir: &Path,
    limit: Duration,
    mut on_item: impl FnMut(Item),
    on_spawn: impl FnOnce(KillHandle),
) -> Result<EngineOutput, WindowError> {
    let started = Instant::now();
    let mut child = spawn_engine(engine, cmd, workdir)?;
    let stdin = child.stdin.take();
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let (Some(mut stdin), Some(stdout), Some(stderr)) = (stdin, stdout, stderr) else {
        let _ = child.kill();
        return Err(WindowError::new(
            "failed",
            "The engine's pipes did not open.",
        ));
    };
    let handle = KillHandle(Arc::new(Mutex::new(Proc {
        child,
        end_at: None,
        by_core: false,
    })));
    on_spawn(handle.clone());

    // stdin in its own thread, so a large answer can never block on a full input pipe
    let bytes = input.0.clone();
    let writer = thread::spawn(move || {
        let _ = stdin.write_all(&bytes);
        // dropping stdin closes it: the engine sees the end of its one document
    });

    let streams = cmd.streams();
    let (tx, rx) = mpsc::channel::<Item>();
    let out_reader = thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        if streams {
            let mut buf = Vec::new();
            loop {
                buf.clear();
                match reader
                    .by_ref()
                    .take(MAX_LINE_BYTES as u64 + 1)
                    .read_until(b'\n', &mut buf)
                {
                    Ok(0) | Err(_) => break,
                    Ok(n) => {
                        let too_long = n > MAX_LINE_BYTES && !buf.ends_with(b"\n");
                        if too_long {
                            // skip the rest of the long line
                            let mut rest = Vec::new();
                            let _ = reader.read_until(b'\n', &mut rest);
                            let _ = tx.send(Item::TooLong);
                            continue;
                        }
                        let line = String::from_utf8_lossy(&buf).trim().to_string();
                        let item = if line.is_empty() {
                            Item::Blank
                        } else if serde_json::from_str::<Value>(&line).is_ok() {
                            Item::Json(line)
                        } else {
                            Item::NotJson
                        };
                        if tx.send(item).is_err() {
                            break;
                        }
                    }
                }
            }
            (String::new(), false)
        } else {
            let mut all = Vec::new();
            let n = reader
                .by_ref()
                .take(MAX_OUTPUT_BYTES as u64 + 1)
                .read_to_end(&mut all)
                .unwrap_or(0);
            let too_big = n > MAX_OUTPUT_BYTES;
            (String::from_utf8_lossy(&all).into_owned(), too_big)
        }
    });
    let err_reader = thread::spawn(move || {
        let mut all = Vec::new();
        let _ = BufReader::new(stderr)
            .take(64 * 1024 * 1024)
            .read_to_end(&mut all);
        let start = all.len().saturating_sub(STDERR_TAIL_BYTES);
        String::from_utf8_lossy(&all[start..]).into_owned()
    });

    let deadline = started + limit;
    let mut dropped = 0usize;
    let mut last_too_long = false;
    let mut take = |item: Item| {
        match &item {
            Item::Json(_) => last_too_long = false,
            Item::NotJson => {
                dropped += 1;
                last_too_long = false;
            }
            Item::TooLong => {
                dropped += 1;
                last_too_long = true;
            }
            Item::Blank => {}
        }
        on_item(item);
    };
    let mut ended_by = EndedBy::Exit;
    let code = loop {
        while let Ok(item) = rx.try_recv() {
            take(item);
        }
        let Ok(mut p) = handle.0.lock() else {
            handle.kill();
            return Err(WindowError::new("failed", "Waiting on the engine failed."));
        };
        let now = Instant::now();
        match p.child.try_wait() {
            Ok(Some(status)) => {
                // the window closing ends the process from another thread: it ended, but by the core
                if p.by_core {
                    ended_by = EndedBy::Core;
                    break None;
                }
                break status.code();
            }
            Ok(None) if now >= deadline || p.end_at.is_some_and(|t| now >= t) => {
                ended_by = if now >= deadline {
                    EndedBy::Timeout
                } else {
                    EndedBy::Core
                };
                p.by_core = true;
                let _ = p.child.kill();
                let _ = p.child.wait();
                break None;
            }
            Ok(None) => {
                drop(p);
                thread::sleep(Duration::from_millis(20));
            }
            Err(_) => {
                drop(p);
                handle.kill();
                return Err(WindowError::new("failed", "Waiting on the engine failed."));
            }
        }
    };
    let _ = writer.join();
    let (stdout, too_big) = out_reader.join().unwrap_or_default();
    for item in rx.try_iter() {
        take(item);
    }
    let stderr_tail = err_reader.join().unwrap_or_default();
    Ok(EngineOutput {
        code,
        stdout,
        stderr_tail,
        elapsed: started.elapsed(),
        dropped_lines: dropped,
        ended_by,
        last_line_too_long: last_too_long,
        too_big,
    })
}

/// The shell's own last message on a run's channel when the stream ended without an engine end event
/// (`finished`, `stopped` or `failed`). Not an engine event: `StreamClosed` in app/ui/src/engine.ts.
pub fn stream_closed(code: Option<i32>, reason: &str) -> Value {
    serde_json::json!({"type": "stream-closed", "exitCode": code, "reason": reason})
}

/// Why a stream ended without an end event: the time limit, the core, a last line over the cap, or the exit.
pub fn closed_reason(ended_by: EndedBy, last_line_too_long: bool) -> &'static str {
    match ended_by {
        EndedBy::Timeout => "timeout",
        EndedBy::Core => "ended-by-core",
        EndedBy::Exit if last_line_too_long => "line-too-long",
        EndedBy::Exit => "exit",
    }
}

/// Line 1 of `run_start` is the run handle only if it is a JSON object with a non-empty string `runId`.
pub fn is_run_handle(v: &Value) -> bool {
    v.get("runId")
        .and_then(Value::as_str)
        .is_some_and(|id| !id.is_empty())
}

/// `finished`, `stopped` or `failed`: the engine's last event of a run.
fn is_end_event(line: &str) -> bool {
    serde_json::from_str::<Value>(line).is_ok_and(|v| {
        matches!(
            v.get("type").and_then(Value::as_str),
            Some("finished" | "stopped" | "failed")
        )
    })
}

/// What one `run_start` came to, for the core's log.
#[derive(Debug, Clone, PartialEq)]
pub struct StreamSummary {
    /// Line 1 was a run handle and went back as the command's answer.
    pub started: bool,
    /// Lines relayed after the handle (the handle counted too when `started`), not counting `stream-closed`.
    pub lines: usize,
    pub dropped: usize,
    pub code: Option<i32>,
    /// The `reason` of the `stream-closed` message the core sent, if it sent one.
    pub closed: Option<&'static str>,
    /// What the command was rejected with, when it was.
    pub rejected: Option<Value>,
}

/// `run_start`, the whole contract (docs/window-actions.md, "The seam's contract"):
/// - line 1 is the handle only if it is a JSON object with a non-empty string `runId`: `answer(Ok(line))`, untouched;
/// - a JSON object with `kind` on line 1 is the engine's refusal: the engine gets [`REFUSAL_WAIT`] to end, then
///   `answer(Err(that document))`, untouched; anything else on line 1 (not JSON, blank, too long, the end of the
///   stream) is `answer(Err(the core's own error))` once the process has ended (same bounded wait);
/// - after the handle every JSON line goes to `relay` as it arrives; if the stream ends without a `finished`,
///   `stopped` or `failed` line, the core relays exactly one [`stream_closed`] message after the last line.
///
/// `answer` is called exactly once. Nothing is sent to `relay` for a rejected start.
pub fn run_stream(
    engine: &EngineProgram,
    input: &EngineInput,
    workdir: &Path,
    answer: impl FnOnce(Result<String, Value>),
    relay: impl FnMut(String),
    on_spawn: impl FnOnce(KillHandle),
) -> StreamSummary {
    run_stream_limited(
        engine,
        input,
        workdir,
        EngineCommand::RunStart.timeout(),
        answer,
        relay,
        on_spawn,
    )
}

fn run_stream_limited(
    engine: &EngineProgram,
    input: &EngineInput,
    workdir: &Path,
    limit: Duration,
    answer: impl FnOnce(Result<String, Value>),
    mut relay: impl FnMut(String),
    on_spawn: impl FnOnce(KillHandle),
) -> StreamSummary {
    let not_a_handle = |why: &str| {
        WindowError::new(
            "failed",
            format!("The engine did not start the run: {why}."),
        )
        .to_value()
    };
    let mut answer = Some(answer);
    let mut started = false;
    // what the command is rejected with, once the process has ended
    let mut rejected: Option<Value> = None;
    let mut lines = 0usize;
    let mut saw_end = false;
    let handle: std::cell::RefCell<Option<KillHandle>> = std::cell::RefCell::new(None);
    let result = run_raw(
        engine,
        EngineCommand::RunStart,
        input,
        workdir,
        limit,
        |item| {
            if started {
                if let Item::Json(line) = item {
                    saw_end |= is_end_event(&line);
                    lines += 1;
                    relay(line);
                }
                return;
            }
            if rejected.is_some() {
                return; // a refused start: nothing after line 1 is read
            }
            let doc = match item {
                Item::Json(line) => {
                    let v: Value = serde_json::from_str(&line).unwrap_or(Value::Null);
                    if is_run_handle(&v) {
                        started = true;
                        lines += 1;
                        // the handle goes back at once, untouched: the screen shows the run while the lines follow
                        if let Some(a) = answer.take() {
                            a(Ok(line));
                        }
                        return;
                    }
                    if v.is_object() && v.get("kind").is_some() {
                        v // the engine's own refusal, passed on untouched
                    } else {
                        not_a_handle("its first line was not a run handle")
                    }
                }
                Item::TooLong => not_a_handle("its first line was longer than 64 KiB"),
                Item::NotJson | Item::Blank => not_a_handle("its first line was not a run handle"),
            };
            rejected = Some(doc);
            if let Some(h) = handle.borrow().as_ref() {
                h.end_within(REFUSAL_WAIT);
            }
        },
        |h| {
            handle.borrow_mut().replace(h.clone());
            on_spawn(h);
        },
    );
    let out = match result {
        Ok(out) => out,
        Err(e) => {
            // the engine did not start (missing, pipes): the core's own error
            let doc = e.to_value();
            if let Some(a) = answer.take() {
                a(Err(doc.clone()));
            }
            return StreamSummary {
                started: false,
                lines: 0,
                dropped: 0,
                code: None,
                closed: None,
                rejected: Some(doc),
            };
        }
    };
    let mut closed = None;
    if started {
        if !saw_end {
            let reason = closed_reason(out.ended_by, out.last_line_too_long);
            relay(stream_closed(out.code, reason).to_string());
            closed = Some(reason);
        }
    } else {
        let doc = rejected.take().unwrap_or_else(|| {
            let what = match (out.ended_by, out.code) {
                (EndedBy::Timeout, _) => "it gave no first line within the time limit".to_string(),
                (EndedBy::Core, _) => "it was ended before its first line".to_string(),
                (EndedBy::Exit, Some(c)) => {
                    format!("it ended with exit code {c} before its first line")
                }
                (EndedBy::Exit, None) => "it ended before its first line".to_string(),
            };
            not_a_handle(&what)
        });
        if let Some(a) = answer.take() {
            a(Err(doc.clone()));
        }
        rejected = Some(doc);
    }
    StreamSummary {
        started,
        lines,
        dropped: out.dropped_lines,
        code: out.code,
        closed,
        rejected,
    }
}

/// A one-document command's answer for the window: the engine's JSON text untouched on exit 0, the engine's
/// error object untouched on a non-zero exit, or the core's own error object when the engine broke the contract.
pub fn answer(out: &EngineOutput) -> Result<String, Value> {
    let text = out.stdout.trim();
    let doc = serde_json::from_str::<Value>(text).ok();
    match (out.code, doc) {
        (Some(0), Some(_)) => Ok(text.to_string()),
        (Some(0), None) => Err(WindowError::new(
            "failed",
            "The engine's answer was not one JSON document.",
        )
        .to_value()),
        (_, Some(err)) if is_error_object(&err) => Err(err),
        (code, _) => {
            let what = code.map_or_else(
                || "was stopped".to_string(),
                |c| format!("ended with exit code {c}"),
            );
            Err(
                WindowError::new("failed", format!("The engine {what} without an answer."))
                    .to_value(),
            )
        }
    }
}

/// `{"kind": string, "message": string, ...}`: the engine's error object (passed on as it is).
pub fn is_error_object(v: &Value) -> bool {
    v.get("kind").is_some_and(Value::is_string) && v.get("message").is_some_and(Value::is_string)
}

/// Read the version out of `leadforge --json version`: the `leadforge X.Y.Z` line, confirmed by an `ok` digest.
pub fn parse_version(out: &EngineOutput) -> Result<String, WindowError> {
    if out.code != Some(0) {
        return Err(WindowError::new(
            "failed",
            format!("version: the engine exited with {:?}", out.code),
        ));
    }
    let lines: Vec<&str> = out.stdout.lines().map(str::trim).collect();
    let digest_ok = lines
        .iter()
        .rev()
        .find_map(|l| l.strip_prefix("LF_DIGEST "))
        .is_some_and(|json| {
            serde_json::from_str::<Value>(json)
                .map(|v| v["ok"] == Value::Bool(true) && v["cmd"] == "version")
                .unwrap_or(false)
        });
    if !digest_ok {
        return Err(WindowError::new("failed", "version: no ok LF_DIGEST line"));
    }
    lines
        .iter()
        .find_map(|l| l.strip_prefix("leadforge "))
        .map(str::trim)
        .filter(|v| is_version(v))
        .map(str::to_string)
        .ok_or_else(|| WindowError::new("failed", "version: no `leadforge X.Y.Z` line"))
}

/// `X.Y.Z` with an optional tail of letters, digits, `.`, `+` or `-`; at most 40 characters.
fn is_version(v: &str) -> bool {
    let mut parts = v.splitn(3, '.');
    let (Some(a), Some(b), Some(c)) = (parts.next(), parts.next(), parts.next()) else {
        return false;
    };
    let num = |s: &str| !s.is_empty() && s.bytes().all(|x| x.is_ascii_digit());
    let digits_end = c.bytes().take_while(u8::is_ascii_digit).count();
    v.len() <= 40
        && num(a)
        && num(b)
        && digits_end > 0
        && c[digits_end..]
            .bytes()
            .all(|x| x.is_ascii_alphanumeric() || b".+-".contains(&x))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn out(code: Option<i32>, stdout: &str) -> EngineOutput {
        EngineOutput {
            code,
            stdout: stdout.to_string(),
            stderr_tail: String::new(),
            elapsed: Duration::ZERO,
            dropped_lines: 0,
            ended_by: EndedBy::Exit,
            last_line_too_long: false,
            too_big: false,
        }
    }

    /// Every one of the 21 commands in its time-limit class, written out so a change to the list is a change here.
    #[test]
    fn timeouts_are_pinned_per_command() {
        use EngineCommand as C;
        let table: [(C, u64); 21] = [
            (C::CampaignCreate, 120),
            (C::RunStart, 12 * 60 * 60),
            (C::RunStop, 30),
            (C::RunStatus, 30),
            (C::CampaignsList, 120),
            (C::SheetExport, 600),
            (C::SheetOpen, 120),
            (C::PeopleList, 120),
            (C::PersonForget, 600),
            (C::AddressSuppress, 120),
            (C::PurgeReport, 600),
            (C::PurgeApply, 600),
            (C::PurgeEverything, 600),
            (C::RetentionGet, 120),
            (C::RetentionSet, 120),
            (C::KeysList, 120),
            (C::KeySave, 120),
            (C::KeyRemove, 120),
            (C::SettingsGet, 120),
            (C::SettingsSet, 120),
            (C::About, 30),
        ];
        let listed: Vec<C> = table.iter().map(|(c, _)| *c).collect();
        assert_eq!(
            listed,
            EngineCommand::WINDOW,
            "the table lists the 21 commands in order"
        );
        for (cmd, secs) in table {
            assert_eq!(
                cmd.timeout(),
                Duration::from_secs(secs),
                "{}: time-limit class",
                cmd.name()
            );
        }
    }

    #[test]
    fn the_stop_wait_is_ninety_seconds() {
        assert_eq!(STOP_WAIT, Duration::from_secs(90));
    }

    #[test]
    fn a_closed_stream_names_why() {
        assert_eq!(closed_reason(EndedBy::Exit, false), "exit");
        assert_eq!(closed_reason(EndedBy::Exit, true), "line-too-long");
        assert_eq!(closed_reason(EndedBy::Core, true), "ended-by-core");
        assert_eq!(closed_reason(EndedBy::Timeout, false), "timeout");
        assert_eq!(
            stream_closed(Some(3), "exit"),
            serde_json::json!({"type": "stream-closed", "exitCode": 3, "reason": "exit"})
        );
        assert_eq!(stream_closed(None, "timeout")["exitCode"], Value::Null);
    }

    #[test]
    fn line_one_is_a_handle_only_with_a_non_empty_run_id() {
        assert!(is_run_handle(&serde_json::json!({"runId": "r-1"})));
        assert!(!is_run_handle(&serde_json::json!({"runId": ""})));
        assert!(!is_run_handle(&serde_json::json!({"runId": 7})));
        assert!(!is_run_handle(
            &serde_json::json!({"kind": "input", "message": "No."})
        ));
        assert!(!is_run_handle(&serde_json::json!(["runId"])));
        assert!(is_end_event(r#"{"type":"stopped","status":{}}"#));
        assert!(!is_end_event(r#"{"type":"progress"}"#));
        assert!(!is_end_event(r#"{"type":"stream-closed"}"#));
    }

    /// The time limit, end to end on a run that ignores everything: `stream-closed` says `timeout`.
    #[test]
    fn a_run_past_its_time_limit_closes_the_stream_with_timeout() {
        let p = EngineProgram::dev_venv();
        let dir =
            std::env::temp_dir().join(format!("lf-window-unit-timeout-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let input = EngineInput::from_args(
            &serde_json::json!({"args": {"campaign": "standin-ignores-stop", "resume": false}}),
        )
        .unwrap();
        let mut answered = None;
        let mut relayed = Vec::new();
        let s = run_stream_limited(
            &p,
            &input,
            &dir,
            Duration::from_secs(3),
            |a| answered = Some(a),
            |l| relayed.push(l),
            |_| {},
        );
        assert!(answered.expect("answered once").is_ok(), "the run started");
        let last: Value = serde_json::from_str(relayed.last().unwrap()).unwrap();
        assert_eq!(last, stream_closed(None, "timeout"));
        assert_eq!(s.closed, Some("timeout"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn argv_is_fixed_per_command() {
        assert_eq!(
            EngineCommand::Version.args(),
            vec![OsString::from("--json"), OsString::from("version")]
        );
        assert_eq!(
            EngineCommand::KeySave.args(),
            vec![OsString::from("window"), OsString::from("key_save")]
        );
        let names: Vec<&str> = EngineCommand::WINDOW.iter().map(|c| c.name()).collect();
        assert_eq!(names.len(), 21);
        let mut unique = names.clone();
        unique.sort();
        unique.dedup();
        assert_eq!(unique.len(), 21, "names are unique");
    }

    #[test]
    fn only_stop_and_status_run_beside_a_run() {
        let beside: Vec<&str> = EngineCommand::WINDOW
            .iter()
            .filter(|c| c.beside_a_run())
            .map(|c| c.name())
            .collect();
        assert_eq!(beside, ["run_stop", "run_status"]);
        assert!(EngineCommand::RunStart.streams());
        assert!(EngineCommand::RunStart.timeout() >= Duration::from_secs(3600));
    }

    #[test]
    fn interpreter_runs_isolated() {
        let p = EngineProgram::bundled(Path::new("R"));
        assert_eq!(
            p.program,
            Path::new("R")
                .join("engine")
                .join("python")
                .join("python.exe")
        );
        assert!(p.prefix.contains(&OsString::from("-I")));
        let real = p.real();
        assert_eq!(real.prefix.last(), Some(&OsString::from("leadforge")));
    }

    #[test]
    fn a_good_answer_passes_untouched() {
        let text = r#"{ "months": 12, "min": 1,  "max": 12 }"#;
        assert_eq!(answer(&out(Some(0), &format!("{text}\n"))).unwrap(), text);
    }

    #[test]
    fn an_error_object_passes_untouched() {
        let err = r#"{"kind":"usage","message":"No.","details":["a"],"next":null,"extra":1}"#;
        let got = answer(&out(Some(2), err)).unwrap_err();
        assert_eq!(got, serde_json::from_str::<Value>(err).unwrap());
    }

    #[test]
    fn a_broken_contract_becomes_the_cores_error() {
        assert_eq!(
            answer(&out(Some(0), "hello")).unwrap_err()["kind"],
            "failed"
        );
        assert_eq!(
            answer(&out(Some(0), "{} {}")).unwrap_err()["kind"],
            "failed"
        );
        let e = answer(&out(Some(3), "Traceback ...")).unwrap_err();
        assert_eq!(
            e["message"],
            "The engine ended with exit code 3 without an answer."
        );
        assert_eq!(e["details"], serde_json::json!([]));
        assert_eq!(e["next"], Value::Null);
    }

    #[test]
    fn input_is_an_object_and_capped() {
        assert_eq!(EngineInput::from_args(&Value::Null).unwrap().0, b"{}");
        assert!(EngineInput::from_args(&serde_json::json!([1])).is_err());
        let big = serde_json::json!({ "v": "x".repeat(MAX_INPUT_BYTES) });
        assert!(EngineInput::from_args(&big).is_err());
        let i = EngineInput::from_args(&serde_json::json!({"value": "secret-ish"})).unwrap();
        assert_eq!(
            format!("{i:?}"),
            format!("EngineInput(<{} bytes>)", i.len())
        );
    }

    #[test]
    fn parses_a_good_version() {
        let o = out(
            Some(0),
            "leadforge 0.7.3\nLF_DIGEST {\"ok\": true, \"cmd\": \"version\"}\n",
        );
        assert_eq!(parse_version(&o).unwrap(), "0.7.3");
        assert!(is_version("0.12.0rc1+local.2"));
        assert!(!is_version("1.2.3 rm"));
    }

    #[test]
    fn missing_engine_is_an_environment_error() {
        let p = EngineProgram {
            program: PathBuf::from("Z:/nowhere/python.exe"),
            prefix: vec![],
            origin: "test",
        };
        let input = EngineInput::from_args(&Value::Null).unwrap();
        let e = run(
            &p,
            EngineCommand::About,
            &input,
            Path::new("."),
            |_| {},
            |_| {},
        )
        .unwrap_err();
        assert_eq!(e.kind, "environment");
    }
}
