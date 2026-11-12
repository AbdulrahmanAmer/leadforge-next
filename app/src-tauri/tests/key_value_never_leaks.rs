//! `key_save`'s value never reaches a log, an error string or a crash message. A marker value is planted and
//! every output of the core's path is searched for it: the answer, the error objects, the log line, the `Debug`
//! form of the input, and a panic's message while the input is alive.
use std::fs;
use std::path::PathBuf;

use leadforge_window::engine::{self, EngineCommand, EngineInput, EngineProgram};
use leadforge_window::log_entry;
use serde_json::{json, Value};

const MARKER: &str = "LFKEY-MARKER-0b5e7d1c9a";

fn workdir() -> PathBuf {
    let d = std::env::temp_dir().join(format!("lf-window-test-key-{}", std::process::id()));
    let _ = fs::remove_dir_all(&d);
    fs::create_dir_all(&d).unwrap();
    d
}

/// Everything the core produces for one `key_save`, as text.
fn everything(p: &EngineProgram, args: Value, dir: &std::path::Path) -> String {
    let input = EngineInput::from_args(&args).unwrap();
    let mut seen = vec![format!("{input:?}")];
    let res = engine::run(
        p,
        EngineCommand::KeySave,
        &input,
        dir,
        |l| seen.push(l.to_string()),
        |_| {},
    );
    let outcome: Result<usize, Value> = match &res {
        Ok(out) => {
            seen.push(format!("{out:?}"));
            engine::answer(out).map(|t| {
                seen.push(t.clone());
                t.len()
            })
        }
        Err(e) => {
            seen.push(format!("{e:?}"));
            Err(e.to_value())
        }
    };
    if let Err(e) = &outcome {
        seen.push(e.to_string());
    }
    seen.push(log_entry(
        EngineCommand::KeySave,
        p.origin,
        &outcome,
        input.len(),
        1,
    ));
    // a crash while the value is held: the panic message is what a crash report would carry
    let caught = std::panic::catch_unwind(|| {
        let held = EngineInput::from_args(&args).unwrap();
        panic!("simulated crash holding {held:?}");
    });
    let msg = caught
        .err()
        .and_then(|e| e.downcast_ref::<String>().cloned())
        .unwrap_or_default();
    assert!(msg.contains("bytes"), "the simulated crash ran: {msg}");
    seen.push(msg);
    seen.join("\n")
}

#[test]
fn the_key_value_appears_in_no_output() {
    let dir = workdir();
    // the stand-in pretends to keep the key (no real keyring is touched by a test)
    let p = EngineProgram::standin();
    let cases = [
        (
            "saved",
            json!({"name": "opencorporates_token", "value": MARKER}),
        ),
        (
            "engine refuses: unknown key",
            json!({"name": "no_such_key", "value": MARKER}),
        ),
    ];
    for (what, args) in cases {
        let text = everything(&p, args, &dir);
        assert!(!text.contains(MARKER), "{what}: the marker leaked:\n{text}");
        assert!(
            text.contains("cmd=key_save"),
            "{what}: the log line was produced"
        );
    }
    // the real engine refusing an unknown key name (refused before it looks for a keyring, so no keyring is touched)
    let text = everything(
        &EngineProgram::dev_venv(),
        json!({"name": "no_such_key", "value": MARKER}),
        &dir,
    );
    assert!(
        !text.contains(MARKER),
        "real engine, unknown key: the marker leaked:\n{text}"
    );
    assert!(
        text.contains("error kind=usage"),
        "real engine, unknown key: refused with kind usage:\n{text}"
    );
    // the engine missing: the core's own error path
    let missing = EngineProgram {
        program: "Z:/nowhere/python.exe".into(),
        prefix: vec![],
        origin: "test",
    };
    let text = everything(
        &missing,
        json!({"name": "opencorporates_token", "value": MARKER}),
        &dir,
    );
    assert!(
        !text.contains(MARKER),
        "engine missing: the marker leaked:\n{text}"
    );
    // the stand-in's own state file holds no value either
    let state = fs::read_to_string(dir.join("standin-state.json")).unwrap_or_default();
    assert!(!state.contains(MARKER), "the stand-in kept the value");
    let _ = fs::remove_dir_all(&dir);
}

/// The check can fail: the same search finds the marker where it is (a check that never fires proves nothing).
#[test]
fn the_search_finds_a_planted_leak() {
    let leaky = format!("cmd=key_save value={MARKER}");
    assert!(leaky.contains(MARKER));
    let input = EngineInput::from_args(&json!({"value": MARKER})).unwrap();
    assert!(!format!("{input:?}").contains(MARKER));
}
