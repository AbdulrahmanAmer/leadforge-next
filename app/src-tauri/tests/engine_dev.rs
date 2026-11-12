//! The core's one program start, end to end in a debug build, against the worktree's `.venv`:
//! the real engine answers `version`, and the stand-in answers all 21 window commands through `engine::run`.
//! Needs the `.venv` made the way CI's install job makes it; without it these tests fail, they do not skip.
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use leadforge_window::engine::{self, EngineCommand, EngineInput, EngineProgram, KillHandle};
use serde_json::{json, Value};

fn workdir(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("lf-window-test-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&d);
    fs::create_dir_all(&d).unwrap();
    d
}

fn call(p: &EngineProgram, cmd: EngineCommand, args: Value, dir: &Path) -> Result<Value, Value> {
    let input = EngineInput::from_args(&args).unwrap();
    let out = engine::run(p, cmd, &input, dir, |_| {}, |_| {}).map_err(|e| e.to_value())?;
    engine::answer(&out).map(|t| serde_json::from_str(&t).unwrap())
}

#[test]
fn the_real_dev_engine_reports_the_project_version() {
    let p = EngineProgram::dev_venv().real();
    assert!(
        p.program.is_file(),
        "no dev engine at {} (make the .venv first)",
        p.program.display()
    );
    let dir = workdir("version");
    let out = engine::run(
        &p,
        EngineCommand::Version,
        &EngineInput::from_args(&Value::Null).unwrap(),
        &dir,
        |_| {},
        |_| {},
    )
    .expect("engine ran");
    let version = engine::parse_version(&out).expect("a version");
    let pyproject =
        fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../pyproject.toml"))
            .unwrap();
    assert!(
        pyproject.contains(&format!("version = \"{version}\"")),
        "engine says {version}"
    );
    let _ = fs::remove_dir_all(&dir);
}

/// Arguments for each command, shaped as app/ui/src/engine.tauri.ts sends them.
fn sample(cmd: EngineCommand) -> Value {
    match cmd {
        EngineCommand::CampaignCreate => {
            json!({"draft": {"kinds": ["MOT garage"], "places": ["Bristol"], "country": "GB", "source": "dvsa", "offer": "Online booking for MOT tests", "sicCodes": [], "maxLeads": 250}})
        }
        EngineCommand::RunStop | EngineCommand::RunStatus | EngineCommand::SheetExport => {
            json!({"runId": "r-20261103-a41c"})
        }
        EngineCommand::SheetOpen => {
            json!({"path": "leadforge_data\\exports\\r-20261103-a41c\\leads.xlsx"})
        }
        EngineCommand::PeopleList => json!({"query": {"search": "", "limit": 50}}),
        EngineCommand::PersonForget => json!({"value": "priya@harbourside-motors.example"}),
        EngineCommand::AddressSuppress => {
            json!({"value": "harbourside-motors.example", "kind": null})
        }
        EngineCommand::PurgeEverything => json!({"confirm": true}),
        EngineCommand::RetentionSet => json!({"months": 6}),
        EngineCommand::KeySave => json!({"name": "opencorporates_token", "value": "made-up-value"}),
        EngineCommand::KeyRemove => json!({"name": "opencorporates_token"}),
        EngineCommand::SettingsSet => json!({"patch": {"openSheetWhenDone": false}}),
        _ => json!({}),
    }
}

#[test]
fn the_stand_in_answers_every_window_command() {
    // with STAND_IN on this is the stand-in; after the switch the same test runs against the real commands
    let p = EngineProgram::dev_venv();
    let dir = workdir("all");
    for cmd in EngineCommand::WINDOW {
        if cmd == EngineCommand::RunStart || cmd == EngineCommand::RunStop {
            continue; // the stream has its own test below
        }
        let got = call(&p, cmd, sample(cmd), &dir);
        assert!(got.is_ok(), "{}: {got:?}", cmd.name());
    }
    // the error path: an incomplete campaign comes back as the engine's error object, untouched
    let err = call(&p, EngineCommand::CampaignCreate, json!({"draft": {"kinds": [], "places": [], "country": "", "source": "dvsa", "offer": "", "sicCodes": [], "maxLeads": 0}}), &dir).unwrap_err();
    assert_eq!(err["kind"], "input");
    assert_eq!(err["details"].as_array().unwrap().len(), 5);
    // Companies House needs SIC codes; a register draft with them is accepted
    let ch = json!({"kinds": ["Plumbing"], "places": ["Taunton"], "country": "GB", "source": "companies_house", "offer": "Online booking", "maxLeads": 50});
    let mut without = ch.clone();
    without["sicCodes"] = json!([]);
    let err = call(
        &p,
        EngineCommand::CampaignCreate,
        json!({"draft": without}),
        &dir,
    )
    .unwrap_err();
    assert!(err["details"].to_string().contains("sicCodes"), "{err}");
    let mut with = ch;
    with["sicCodes"] = json!(["43220"]);
    call(
        &p,
        EngineCommand::CampaignCreate,
        json!({"draft": with}),
        &dir,
    )
    .expect("a Companies House draft with SIC codes");
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn a_run_streams_and_run_stop_beside_it_ends_it() {
    let p = EngineProgram::dev_venv();
    let dir = workdir("run");
    let lines: Arc<Mutex<Vec<Value>>> = Arc::default();
    let handle: Arc<Mutex<Option<KillHandle>>> = Arc::default();
    let (p2, dir2, lines2, handle2) = (p.clone(), dir.clone(), lines.clone(), handle.clone());
    let runner = std::thread::spawn(move || {
        let input = EngineInput::from_args(
            &json!({"args": {"campaign": "bristol-mot-garages", "resume": false}}),
        )
        .unwrap();
        engine::run(
            &p2,
            EngineCommand::RunStart,
            &input,
            &dir2,
            |l| {
                lines2
                    .lock()
                    .unwrap()
                    .push(serde_json::from_str(l).unwrap())
            },
            |h| {
                *handle2.lock().unwrap() = Some(h);
            },
        )
    });
    std::thread::sleep(Duration::from_millis(2500));
    let first = lines
        .lock()
        .unwrap()
        .first()
        .cloned()
        .expect("a handle line");
    let run_id = first["runId"]
        .as_str()
        .expect("line 1 is the run handle")
        .to_string();
    let progress = lines
        .lock()
        .unwrap()
        .iter()
        .filter(|l| l["type"] == "progress")
        .count();
    assert!(progress >= 3, "progress streamed while running: {progress}");
    let stopped = call(&p, EngineCommand::RunStop, json!({"runId": run_id}), &dir)
        .expect("run_stop answered beside the run");
    assert_eq!(stopped["state"], "stopped");
    let out = runner.join().unwrap().expect("the run ended");
    assert_eq!(out.code, Some(0));
    let last = lines.lock().unwrap().last().cloned().unwrap();
    assert_eq!(last["type"], "stopped");
    assert!(
        handle.lock().unwrap().as_ref().unwrap().ended(),
        "nothing left running"
    );
    let _ = fs::remove_dir_all(&dir);
}

#[test]
fn the_core_kills_a_run_that_does_not_stop() {
    let p = EngineProgram::dev_venv();
    let dir = workdir("kill");
    let handle: Arc<Mutex<Option<KillHandle>>> = Arc::default();
    let h2 = handle.clone();
    let (p2, dir2) = (p.clone(), dir.clone());
    let runner = std::thread::spawn(move || {
        let input =
            EngineInput::from_args(&json!({"args": {"campaign": "x", "resume": false}})).unwrap();
        engine::run(
            &p2,
            EngineCommand::RunStart,
            &input,
            &dir2,
            |_| {},
            |h| *h2.lock().unwrap() = Some(h),
        )
    });
    std::thread::sleep(Duration::from_millis(1500));
    let h = handle.lock().unwrap().clone().expect("spawned");
    h.kill(); // what closing the window does
    let out = runner.join().unwrap().expect("returned");
    assert_ne!(out.code, Some(0));
    assert!(h.ended());
    let _ = fs::remove_dir_all(&dir);
}
