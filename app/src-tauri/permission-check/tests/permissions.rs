//! THE PERMISSION TEST (`cargo test` in app/src-tauri/permission-check; it does not build the app, so it still runs
//! and fails when the app's own build would refuse the change first).
//! The window can do only what is listed here, and nothing that starts a program.
//! It reads the files that grant the window anything (capabilities/*.json, tauri.conf.json and its bundle overlay,
//! any app-defined permission under permissions/), plus the places a new command or plugin would enter
//! (build.rs, src/lib.rs, Cargo.toml), and fails on anything outside the short allow-list below.
//! Changing a list here is a security decision: say why in the slice file.

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::Value;

/// Every permission a capability may grant. Adding one is a reviewed change.
const ALLOWED_PERMISSIONS: &[&str] = &["allow-engine-version"];
/// Every app command the window may call.
const ALLOWED_COMMANDS: &[&str] = &["engine_version"];
/// The only windows a capability may name.
const ALLOWED_WINDOWS: &[&str] = &["main"];
/// Crates the core may depend on. No tauri-plugin-* at all.
const ALLOWED_DEPENDENCIES: &[&str] = &["tauri", "serde", "serde_json"];
const ALLOWED_BUILD_DEPENDENCIES: &[&str] = &["tauri-build"];
/// Words that mark a permission able to start a program or reach outside the window.
const PROGRAM_START_MARKS: &[&str] = &[
    "shell", "process", "execute", "exec", "spawn", "sidecar", "command", "opener", "open",
];

/// The app's folder (`app/src-tauri`), one above this crate.
fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn read(p: &Path) -> String {
    fs::read_to_string(p).unwrap_or_else(|e| panic!("cannot read {}: {e}", p.display()))
}

fn json(p: &Path) -> Value {
    serde_json::from_str(&read(p)).unwrap_or_else(|e| panic!("{} is not JSON: {e}", p.display()))
}

/// Every problem found, so one run names them all.
fn problems_in_permission(id: &str, place: &str) -> Vec<String> {
    let lower = id.to_ascii_lowercase();
    let mut out = Vec::new();
    if PROGRAM_START_MARKS.iter().any(|m| lower.contains(m)) && !ALLOWED_PERMISSIONS.contains(&id) {
        out.push(format!(
            "{place}: PROGRAM-START PERMISSION `{id}`: the window may not start a program"
        ));
    }
    if !ALLOWED_PERMISSIONS.contains(&id) {
        out.push(format!(
            "{place}: permission `{id}` is not on the allow-list {ALLOWED_PERMISSIONS:?}"
        ));
    }
    out
}

fn check_capability(cap: &Value, place: &str, problems: &mut Vec<String>) {
    let Some(obj) = cap.as_object() else {
        problems.push(format!("{place}: a capability must be an object"));
        return;
    };
    for key in obj.keys() {
        if ![
            "identifier",
            "description",
            "windows",
            "permissions",
            "$schema",
        ]
        .contains(&key.as_str())
        {
            // `remote` (remote URLs get IPC), `webviews`, `platforms`, `local`... are all outside the list.
            problems.push(format!("{place}: key `{key}` is outside the allow-list"));
        }
    }
    match obj.get("windows").and_then(Value::as_array) {
        Some(w) if !w.is_empty() => {
            for win in w {
                if !win.as_str().is_some_and(|s| ALLOWED_WINDOWS.contains(&s)) {
                    problems.push(format!(
                        "{place}: window `{win}` is not allowed (wildcards included)"
                    ));
                }
            }
        }
        _ => problems.push(format!("{place}: `windows` must list the windows by name")),
    }
    for p in obj
        .get("permissions")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        match p {
            Value::String(id) => problems.extend(problems_in_permission(id, place)),
            // The object form scopes a permission (`{ "identifier": ..., "allow": [...] }`): never needed here.
            Value::Object(o) => {
                let id = o.get("identifier").and_then(Value::as_str).unwrap_or("?");
                problems.extend(problems_in_permission(id, place));
                problems.push(format!(
                    "{place}: scoped permission `{id}` is outside the allow-list"
                ));
            }
            other => problems.push(format!("{place}: strange permission entry {other}")),
        }
    }
}

/// Keys whose name starts with `dangerous` anywhere in a config (dangerousDisableAssetCspModification, ...).
fn dangerous_keys(v: &Value, path: &str, out: &mut Vec<String>) {
    match v {
        Value::Object(o) => {
            for (k, child) in o {
                let p = format!("{path}.{k}");
                if k.to_ascii_lowercase().starts_with("dangerous") {
                    out.push(format!("tauri config: `{p}` is not allowed"));
                }
                dangerous_keys(child, &p, out);
            }
        }
        Value::Array(a) => a.iter().for_each(|c| dangerous_keys(c, path, out)),
        _ => {}
    }
}

fn check_csp(csp: &str, problems: &mut Vec<String>) {
    for bad in [
        "'unsafe-inline'",
        "'unsafe-eval'",
        "'wasm-unsafe-eval'",
        "'unsafe-hashes'",
        "*",
        "https:",
        "http:",
        "blob:",
    ] {
        if csp.split([' ', ';']).any(|tok| tok == bad) {
            problems.push(format!("csp: `{bad}` is not allowed"));
        }
    }
    for tok in csp.split([' ', ';']).filter(|t| t.contains("://")) {
        if tok != "http://ipc.localhost" {
            problems.push(format!("csp: remote origin `{tok}` is not allowed"));
        }
    }
    let directive = |name: &str| {
        csp.split(';')
            .map(str::trim)
            .find(|d| d.split(' ').next() == Some(name))
            .map(str::to_string)
    };
    if directive("default-src").as_deref() != Some("default-src 'self'") {
        problems.push("csp: `default-src 'self'` must be set".into());
    }
    if directive("script-src").as_deref() != Some("script-src 'self'") {
        problems.push("csp: `script-src 'self'` must be set, with nothing else".into());
    }
    if directive("object-src").as_deref() != Some("object-src 'none'") {
        problems.push("csp: `object-src 'none'` must be set".into());
    }
}

fn check_config(conf: &Value, place: &str, problems: &mut Vec<String>) {
    dangerous_keys(conf, place, problems);
    if conf
        .get("plugins")
        .is_some_and(|p| p.as_object().is_none_or(|o| !o.is_empty()))
    {
        problems.push(format!("{place}: `plugins` must be empty"));
    }
    let Some(app) = conf.get("app") else { return };
    let sec = &app["security"];
    match sec.get("csp") {
        Some(Value::String(csp)) => check_csp(csp, problems),
        Some(_) => problems.push(format!("{place}: csp must be one string")),
        None => problems.push(format!("{place}: app.security.csp must be set")),
    }
    if sec.get("devCsp").is_some() {
        problems.push(format!(
            "{place}: devCsp is not allowed (one policy for both)"
        ));
    }
    if sec.pointer("/assetProtocol/enable") == Some(&Value::Bool(true)) {
        problems.push(format!(
            "{place}: the asset protocol (file access from the window) is not allowed"
        ));
    }
    if let Some(caps) = sec.get("capabilities").and_then(Value::as_array) {
        for c in caps {
            match c {
                Value::String(id) if id == "main" => {}
                Value::String(id) => {
                    problems.push(format!("{place}: capability `{id}` is not on the list"))
                }
                inline => check_capability(inline, &format!("{place} inline capability"), problems),
            }
        }
    }
    for w in app
        .get("windows")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(url) = w.get("url").and_then(Value::as_str) {
            if url.contains("://") {
                problems.push(format!("{place}: window url `{url}` is remote content"));
            }
        }
    }
    if let Some(dev) = conf.pointer("/build/devUrl").and_then(Value::as_str) {
        let host = dev
            .split("://")
            .nth(1)
            .unwrap_or("")
            .split(['/', ':'])
            .next()
            .unwrap_or("");
        if !["localhost", "127.0.0.1"].contains(&host) {
            problems.push(format!("{place}: devUrl `{dev}` is not loopback"));
        }
    }
}

/// The names inside the first `marker ... ]` or `marker ... )` block of a source file.
fn listed_names(src: &str, marker: &str, close: char) -> Vec<String> {
    let start = src
        .find(marker)
        .unwrap_or_else(|| panic!("`{marker}` not found"));
    let rest = &src[start + marker.len()..];
    let end = rest.find(close).expect("unclosed list");
    rest[..end]
        .split(',')
        .map(|s| {
            s.trim_matches(|c: char| c.is_whitespace() || "&[]\"".contains(c))
                .to_string()
        })
        .filter(|s| !s.is_empty())
        .collect()
}

/// Every file below a folder (none if it does not exist).
fn files_under(dir: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut todo = vec![dir.to_path_buf()];
    while let Some(d) = todo.pop() {
        let Ok(entries) = fs::read_dir(&d) else {
            continue;
        };
        for e in entries {
            let p = e.unwrap().path();
            if p.is_dir() {
                todo.push(p);
            } else {
                out.push(p);
            }
        }
    }
    out.sort();
    out
}

fn dependency_names(cargo_toml: &str, section: &str) -> Vec<String> {
    let mut in_section = false;
    let mut out = Vec::new();
    for line in cargo_toml.lines().map(str::trim) {
        if line.starts_with('[') {
            in_section = line == section;
        } else if in_section && !line.is_empty() && !line.starts_with('#') {
            out.push(line.split(['=', ' ']).next().unwrap_or("").to_string());
        }
    }
    out
}

/// All problems in the shell as it is on disk.
fn all_problems() -> Vec<String> {
    let root = root();
    let mut problems = Vec::new();

    // 1. Capability files: every one, whatever its name or depth.
    let mut found = 0;
    for p in files_under(&root.join("capabilities")) {
        let place = format!(
            "capabilities/{}",
            p.strip_prefix(root.join("capabilities")).unwrap().display()
        );
        match p.extension().and_then(|e| e.to_str()) {
            Some("json") => {
                found += 1;
                let v = json(&p);
                check_capability(&v, &place, &mut problems);
                if v["identifier"] != "main" {
                    problems.push(format!("{place}: only the capability `main` may exist"));
                }
            }
            _ => problems.push(format!(
                "{place}: only .json capability files are read by this test; remove it"
            )),
        }
    }
    if found != 1 {
        problems.push(format!(
            "capabilities/: exactly one capability file expected, found {found}"
        ));
    }

    // 2. The configs: the main one and the bundle overlay.
    for name in ["tauri.conf.json", "tauri.bundle.conf.json"] {
        check_config(&json(&root.join(name)), name, &mut problems);
    }
    for entry in fs::read_dir(&root).unwrap() {
        let n = entry.unwrap().file_name().to_string_lossy().to_string();
        if n.starts_with("tauri.")
            && n.ends_with(".json")
            && n != "tauri.conf.json"
            && n != "tauri.bundle.conf.json"
        {
            problems.push(format!("{n}: an extra Tauri config is outside the list"));
        }
    }

    // 3. App-defined permissions (permissions/**, including the set tauri-build generates from build.rs):
    //    each one may only allow or deny a command on the list.
    for p in files_under(&root.join("permissions")) {
        let place = format!(
            "permissions/{}",
            p.strip_prefix(root.join("permissions")).unwrap().display()
        );
        for line in read(&p).lines().map(str::trim) {
            if let Some(list) = line
                .strip_prefix("commands.allow")
                .or_else(|| line.strip_prefix("commands.deny"))
            {
                for cmd in listed_names(&format!("{list}\n"), "=", '\n') {
                    if !ALLOWED_COMMANDS.contains(&cmd.as_str()) {
                        problems.push(format!(
                            "{place}: command `{cmd}` is not on the list {ALLOWED_COMMANDS:?}"
                        ));
                    }
                }
            } else if let Some(id) = line.strip_prefix("identifier") {
                let id = id.trim_matches(|c: char| c.is_whitespace() || c == '=' || c == '"');
                if !ALLOWED_PERMISSIONS.contains(&id) && !id.starts_with("deny-") {
                    problems.push(format!("{place}: permission `{id}` is not on the allow-list {ALLOWED_PERMISSIONS:?}"));
                }
            } else if line.starts_with("[[set]]")
                || line.starts_with("[default]")
                || line.starts_with("scope")
            {
                problems.push(format!(
                    "{place}: `{line}` (permission sets, defaults and scopes are outside the list)"
                ));
            }
        }
    }

    // 4. Where a command or a plugin would enter.
    let build = read(&root.join("build.rs"));
    let cmds = listed_names(&build, ".commands(", ')');
    if cmds != ALLOWED_COMMANDS {
        problems.push(format!(
            "build.rs: app commands {cmds:?} differ from the list {ALLOWED_COMMANDS:?}"
        ));
    }
    let lib = read(&root.join("src").join("lib.rs"));
    let handlers = listed_names(&lib, "generate_handler![", ']');
    if handlers != ALLOWED_COMMANDS {
        problems.push(format!(
            "src/lib.rs: handlers {handlers:?} differ from the list {ALLOWED_COMMANDS:?}"
        ));
    }
    if lib.contains(".plugin(") {
        problems.push("src/lib.rs: no plugin may be registered".into());
    }
    let cargo = read(&root.join("Cargo.toml"));
    for (section, allowed) in [
        ("[dependencies]", ALLOWED_DEPENDENCIES),
        ("[build-dependencies]", ALLOWED_BUILD_DEPENDENCIES),
    ] {
        for dep in dependency_names(&cargo, section) {
            if !allowed.contains(&dep.as_str()) {
                problems.push(format!(
                    "Cargo.toml {section}: `{dep}` is outside the list {allowed:?}"
                ));
            }
        }
    }

    // 5. One way to start a program: exactly one `Command::new`, in src/engine.rs.
    let mut starts = Vec::new();
    for entry in fs::read_dir(root.join("src")).unwrap() {
        let p = entry.unwrap().path();
        let n = read(&p).matches("Command::new(").count();
        if n > 0 {
            starts.push((p.file_name().unwrap().to_string_lossy().to_string(), n));
        }
    }
    if starts != [("engine.rs".to_string(), 1)] {
        problems.push(format!(
            "src/: program starts {starts:?}; exactly one, in engine.rs, is allowed"
        ));
    }
    problems
}

#[test]
fn the_window_can_start_nothing_and_holds_only_listed_permissions() {
    let problems = all_problems();
    assert!(
        problems.is_empty(),
        "\n{} problem(s):\n  {}\n",
        problems.len(),
        problems.join("\n  ")
    );
}

// The checks themselves can fail: each planted fault is caught (a check that never fires proves nothing).
#[test]
fn a_planted_shell_permission_is_caught() {
    let cap: Value = serde_json::from_str(
        r#"{"identifier":"main","windows":["main"],"permissions":["allow-engine-version","shell:allow-execute"]}"#,
    )
    .unwrap();
    let mut p = Vec::new();
    check_capability(&cap, "planted", &mut p);
    assert!(
        p.iter()
            .any(|m| m.contains("PROGRAM-START PERMISSION `shell:allow-execute`")),
        "{p:?}"
    );
}

#[test]
fn planted_config_faults_are_caught() {
    let conf: Value = serde_json::from_str(
        r#"{"app":{"security":{"csp":"default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.example; object-src 'none'",
            "dangerousDisableAssetCspModification":true,"assetProtocol":{"enable":true}},
            "windows":[{"label":"main","url":"https://example.com"}]},"plugins":{"shell":{"open":true}}}"#,
    )
    .unwrap();
    let mut p = Vec::new();
    check_config(&conf, "planted", &mut p);
    for want in [
        "'unsafe-inline'",
        "https://cdn.example",
        "dangerousDisableAssetCspModification",
        "asset protocol",
        "remote content",
        "plugins",
    ] {
        assert!(p.iter().any(|m| m.contains(want)), "missed {want}: {p:?}");
    }
    let mut p = Vec::new();
    check_capability(
        &serde_json::json!({"identifier":"x","windows":["*"],"remote":{"urls":["https://*"]},"permissions":["core:default"]}),
        "planted",
        &mut p,
    );
    for want in ["`remote`", "window `\"*\"`", "core:default"] {
        assert!(p.iter().any(|m| m.contains(want)), "missed {want}: {p:?}");
    }
}
