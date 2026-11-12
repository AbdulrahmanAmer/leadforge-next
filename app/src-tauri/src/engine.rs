//! The one place in the core that starts a program: the bundled LeadForge engine.
//!
//! Three rules hold here and permission-check/tests/permissions.rs checks the first by reading the source:
//! 1. `Command::new` appears once in the crate, in [`spawn_engine`].
//! 2. The program is a fixed path: the engine inside the app's own resources (release) or the worktree's
//!    `.venv` (debug builds only). Nothing the window sends ever reaches the path.
//! 3. The arguments come only from [`EngineCommand`], a closed enum. The window names a Tauri command; the core
//!    maps it to a variant. No string from the window becomes an argument.

use std::ffi::OsString;
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;

/// Every engine command the core can run. The next slice (L11) adds variants here, each with typed fields that
/// the core turns into arguments, for example `NewCampaign { niche: Niche, town: Town }` (validated newtypes),
/// `Run { campaign: CampaignId }` (streamed: every `LF_PROGRESS` line relayed as an event),
/// `Results { campaign: CampaignId }`, `People { campaign: CampaignId }`, `Forget { lead: LeadId }`,
/// `Suppress { address: EmailAddress }`, `Purge { campaign: CampaignId }`, `RetentionGet`,
/// `RetentionSet { days: u16 }`, `KeysStatus`. There is no send command (C14).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EngineCommand {
    /// `leadforge --json version`: prints `leadforge X.Y.Z` and the `LF_DIGEST` line.
    Version,
}

impl EngineCommand {
    /// The engine's arguments for this command. Built only from the variant and its typed fields.
    pub fn args(self) -> Vec<OsString> {
        match self {
            EngineCommand::Version => vec!["--json".into(), "version".into()],
        }
    }

    /// The longest the engine may take before the core stops it.
    pub fn timeout(self) -> Duration {
        match self {
            EngineCommand::Version => Duration::from_secs(60),
        }
    }
}

/// Where the engine lives and how it is started. Fixed at build time; see [`EngineProgram::locate`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineProgram {
    /// The interpreter (or frozen engine) the core starts.
    pub program: PathBuf,
    /// Arguments that always come first (interpreter flags and the module), never from the window.
    pub prefix: Vec<OsString>,
    /// `bundled` or `dev-venv`, reported to the window.
    pub origin: &'static str,
}

/// The interpreter flags: UTF-8 I/O, isolated mode (no PYTHON* variables, no user site, no current folder on the
/// import path), then the engine module.
fn python_prefix() -> Vec<OsString> {
    ["-X", "utf8", "-I", "-m", "leadforge"]
        .iter()
        .map(OsString::from)
        .collect()
}

impl EngineProgram {
    /// The engine in a release build: python.org's embeddable Python inside the app's resources
    /// (`<resources>/engine/python/python.exe`, the engine's packages beside it; docs/slices/L10-shell.md item 4).
    pub fn bundled(resource_dir: &Path) -> Self {
        EngineProgram {
            program: resource_dir
                .join("engine")
                .join("python")
                .join("python.exe"),
            prefix: python_prefix(),
            origin: "bundled",
        }
    }

    /// The engine in a debug build: the worktree's `.venv`, made the way CI makes it. Compiled into debug builds only.
    #[cfg(debug_assertions)]
    pub fn dev_venv() -> Self {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("..");
        EngineProgram {
            program: root.join(".venv").join("Scripts").join("python.exe"),
            prefix: python_prefix(),
            origin: "dev-venv",
        }
    }

    /// Debug builds use the dev venv; release builds only ever use the bundled engine.
    pub fn locate(resource_dir: Option<&Path>) -> Result<Self, EngineError> {
        #[cfg(debug_assertions)]
        {
            let _ = resource_dir;
            Ok(Self::dev_venv())
        }
        #[cfg(not(debug_assertions))]
        {
            resource_dir.map(Self::bundled).ok_or_else(|| {
                EngineError::new("not_found", "the app's resource folder is unknown")
            })
        }
    }
}

/// What the window receives when the engine could not answer.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EngineError {
    /// One of: `not_found`, `busy`, `start_failed`, `timeout`, `failed`, `bad_output`.
    pub kind: &'static str,
    pub message: String,
}

impl EngineError {
    pub fn new(kind: &'static str, message: impl Into<String>) -> Self {
        EngineError {
            kind,
            message: message.into(),
        }
    }
}

/// What one finished engine run produced.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineOutput {
    pub code: Option<i32>,
    pub stdout_lines: Vec<String>,
    pub stderr_tail: String,
    pub elapsed: Duration,
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
const MAX_LINES: usize = 20_000;
const MAX_LINE_BYTES: usize = 64 * 1024;
const STDERR_TAIL_BYTES: usize = 4 * 1024;

/// The only `Command::new` in the crate.
fn spawn_engine(
    engine: &EngineProgram,
    cmd: EngineCommand,
    workdir: &Path,
) -> Result<std::process::Child, EngineError> {
    if !engine.program.is_file() {
        return Err(EngineError::new(
            "not_found",
            format!("engine not found at {}", engine.program.display()),
        ));
    }
    let mut c = Command::new(&engine.program);
    c.args(&engine.prefix)
        .args(cmd.args())
        .current_dir(workdir)
        .env_clear()
        .stdin(Stdio::null())
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
    c.spawn()
        .map_err(|e| EngineError::new("start_failed", format!("engine did not start: {e}")))
}

/// Run one engine command to its end (or its timeout). `on_line` sees every stdout line as it arrives, which is
/// how the next slice relays `LF_PROGRESS` lines to the window as events.
pub fn run(
    engine: &EngineProgram,
    cmd: EngineCommand,
    workdir: &Path,
    mut on_line: impl FnMut(&str),
) -> Result<EngineOutput, EngineError> {
    let started = Instant::now();
    let mut child = spawn_engine(engine, cmd, workdir)?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| EngineError::new("start_failed", "no stdout pipe"))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| EngineError::new("start_failed", "no stderr pipe"))?;

    let (tx, rx) = mpsc::channel::<String>();
    let out_reader = thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut buf = Vec::new();
        loop {
            buf.clear();
            match reader
                .by_ref()
                .take(MAX_LINE_BYTES as u64)
                .read_until(b'\n', &mut buf)
            {
                Ok(0) | Err(_) => break,
                Ok(_) => {
                    let line = String::from_utf8_lossy(&buf)
                        .trim_end_matches(['\r', '\n'])
                        .to_string();
                    if tx.send(line).is_err() {
                        break;
                    }
                }
            }
        }
    });
    let err_reader = thread::spawn(move || {
        let mut all = Vec::new();
        let _ = BufReader::new(stderr).read_to_end(&mut all);
        let start = all.len().saturating_sub(STDERR_TAIL_BYTES);
        String::from_utf8_lossy(&all[start..]).into_owned()
    });

    let deadline = started + cmd.timeout();
    let mut lines = Vec::new();
    let mut timed_out = false;
    let status = loop {
        while let Ok(line) = rx.try_recv() {
            on_line(&line);
            if lines.len() < MAX_LINES {
                lines.push(line);
            }
        }
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if Instant::now() >= deadline => {
                timed_out = true;
                let _ = child.kill();
                break child.wait().ok();
            }
            Ok(None) => thread::sleep(Duration::from_millis(20)),
            Err(e) => {
                return Err(EngineError::new(
                    "failed",
                    format!("waiting on the engine failed: {e}"),
                ))
            }
        }
    };
    let _ = out_reader.join();
    for line in rx.try_iter() {
        on_line(&line);
        if lines.len() < MAX_LINES {
            lines.push(line);
        }
    }
    let stderr_tail = err_reader.join().unwrap_or_default();
    if timed_out {
        return Err(EngineError::new(
            "timeout",
            format!("engine stopped after {:?}", cmd.timeout()),
        ));
    }
    Ok(EngineOutput {
        code: status.and_then(|s| s.code()),
        stdout_lines: lines,
        stderr_tail,
        elapsed: started.elapsed(),
    })
}

/// The engine's version as the window sees it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct EngineVersion {
    /// For example `0.7.3`.
    pub version: String,
    /// `bundled` or `dev-venv`.
    pub origin: &'static str,
    /// How long the engine took, start to exit.
    pub millis: u64,
}

/// Read the version out of `leadforge --json version`: the `leadforge X.Y.Z` line, confirmed by an `ok` digest.
pub fn parse_version(out: &EngineOutput) -> Result<String, EngineError> {
    if out.code != Some(0) {
        return Err(EngineError::new(
            "failed",
            format!(
                "engine exited with {:?}: {}",
                out.code,
                out.stderr_tail.trim()
            ),
        ));
    }
    let digest_ok = out
        .stdout_lines
        .iter()
        .rev()
        .find_map(|l| l.strip_prefix("LF_DIGEST "))
        .is_some_and(|json| {
            serde_json::from_str::<serde_json::Value>(json)
                .map(|v| v["ok"] == serde_json::Value::Bool(true) && v["cmd"] == "version")
                .unwrap_or(false)
        });
    if !digest_ok {
        return Err(EngineError::new(
            "bad_output",
            "no ok LF_DIGEST line for version",
        ));
    }
    let version = out
        .stdout_lines
        .iter()
        .find_map(|l| l.strip_prefix("leadforge "))
        .map(str::trim)
        .filter(|v| is_version(v))
        .ok_or_else(|| EngineError::new("bad_output", "no `leadforge X.Y.Z` line"))?;
    Ok(version.to_string())
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

    fn out(code: Option<i32>, lines: &[&str]) -> EngineOutput {
        EngineOutput {
            code,
            stdout_lines: lines.iter().map(|s| s.to_string()).collect(),
            stderr_tail: String::new(),
            elapsed: Duration::ZERO,
        }
    }

    #[test]
    fn version_args_are_fixed() {
        assert_eq!(
            EngineCommand::Version.args(),
            vec![OsString::from("--json"), OsString::from("version")]
        );
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
        assert_eq!(p.prefix.last(), Some(&OsString::from("leadforge")));
    }

    #[test]
    fn parses_a_good_reply() {
        let o = out(
            Some(0),
            &[
                "leadforge 0.7.3",
                r#"LF_DIGEST {"ok": true, "cmd": "version", "counts": {}}"#,
            ],
        );
        assert_eq!(parse_version(&o).unwrap(), "0.7.3");
    }

    #[test]
    fn refuses_a_failed_digest() {
        let o = out(
            Some(0),
            &[
                "leadforge 0.7.3",
                r#"LF_DIGEST {"ok": false, "cmd": "version"}"#,
            ],
        );
        assert_eq!(parse_version(&o).unwrap_err().kind, "bad_output");
    }

    #[test]
    fn refuses_a_nonzero_exit() {
        let o = out(
            Some(2),
            &[
                "leadforge 0.7.3",
                r#"LF_DIGEST {"ok": true, "cmd": "version"}"#,
            ],
        );
        assert_eq!(parse_version(&o).unwrap_err().kind, "failed");
    }

    #[test]
    fn refuses_a_strange_version() {
        for bad in [
            "leadforge <script>",
            "leadforge 1.2",
            "leadforge 1.2.x",
            "leadforge 1.2.3 rm",
        ] {
            let o = out(
                Some(0),
                &[bad, r#"LF_DIGEST {"ok": true, "cmd": "version"}"#],
            );
            assert_eq!(parse_version(&o).unwrap_err().kind, "bad_output", "{bad}");
        }
        assert!(is_version("0.12.0rc1+local.2"));
    }

    #[test]
    fn missing_engine_is_not_found() {
        let p = EngineProgram {
            program: PathBuf::from("Z:/nowhere/python.exe"),
            prefix: vec![],
            origin: "test",
        };
        let e = run(&p, EngineCommand::Version, Path::new("."), |_| {}).unwrap_err();
        assert_eq!(e.kind, "not_found");
    }
}
