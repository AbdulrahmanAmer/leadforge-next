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

    /// The longest the engine may take before the core stops it.
    pub fn timeout(self) -> Duration {
        let secs = match self {
            Self::RunStart => 12 * 60 * 60,
            Self::RunStop | Self::RunStatus | Self::About | Self::Version => 30,
            Self::SheetExport | Self::PurgeApply | Self::PurgeEverything | Self::PersonForget => {
                600
            }
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

/// What one finished engine run produced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineOutput {
    pub code: Option<i32>,
    /// The whole stdout of a one-document command; empty for a stream (its lines went to `on_line`).
    pub stdout: String,
    pub stderr_tail: String,
    pub elapsed: Duration,
    /// Stream lines that were not one JSON document or were too long, so not relayed.
    pub dropped_lines: usize,
}

/// Stops a running engine from another thread (`run_stop`, the window closing).
#[derive(Clone)]
pub struct KillHandle(Arc<Mutex<Child>>);

impl KillHandle {
    pub fn kill(&self) {
        if let Ok(mut c) = self.0.lock() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }

    /// Whether the engine has ended.
    pub fn ended(&self) -> bool {
        self.0
            .lock()
            .map(|mut c| !matches!(c.try_wait(), Ok(None)))
            .unwrap_or(true)
    }
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
pub fn run(
    engine: &EngineProgram,
    cmd: EngineCommand,
    input: &EngineInput,
    workdir: &Path,
    mut on_line: impl FnMut(&str),
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
    let handle = KillHandle(Arc::new(Mutex::new(child)));
    on_spawn(handle.clone());

    // stdin in its own thread, so a large answer can never block on a full input pipe
    let bytes = input.0.clone();
    let writer = thread::spawn(move || {
        let _ = stdin.write_all(&bytes);
        // dropping stdin closes it: the engine sees the end of its one document
    });

    let streams = cmd.streams();
    let (tx, rx) = mpsc::channel::<Result<String, ()>>();
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
                            let _ = tx.send(Err(()));
                            continue;
                        }
                        let line = String::from_utf8_lossy(&buf).trim().to_string();
                        if line.is_empty() {
                            continue;
                        }
                        let ok = serde_json::from_str::<Value>(&line).is_ok();
                        if tx.send(if ok { Ok(line) } else { Err(()) }).is_err() {
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

    let deadline = started + cmd.timeout();
    let mut dropped = 0usize;
    let mut timed_out = false;
    let code = loop {
        while let Ok(item) = rx.try_recv() {
            match item {
                Ok(line) => on_line(&line),
                Err(()) => dropped += 1,
            }
        }
        let polled = handle.0.lock().map(|mut c| c.try_wait());
        match polled {
            Ok(Ok(Some(status))) => break status.code(),
            Ok(Ok(None)) if Instant::now() >= deadline => {
                timed_out = true;
                handle.kill();
                break None;
            }
            Ok(Ok(None)) => thread::sleep(Duration::from_millis(20)),
            _ => {
                handle.kill();
                return Err(WindowError::new("failed", "Waiting on the engine failed."));
            }
        }
    };
    let _ = writer.join();
    let (stdout, too_big) = out_reader.join().unwrap_or_default();
    for item in rx.try_iter() {
        match item {
            Ok(line) => on_line(&line),
            Err(()) => dropped += 1,
        }
    }
    let stderr_tail = err_reader.join().unwrap_or_default();
    if timed_out {
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
    if too_big {
        return Err(WindowError::new(
            "failed",
            "The engine's answer was larger than 8 MiB and was not read.",
        ));
    }
    Ok(EngineOutput {
        code,
        stdout,
        stderr_tail,
        elapsed: started.elapsed(),
        dropped_lines: dropped,
    })
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
        }
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
