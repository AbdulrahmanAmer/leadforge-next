//! The REAL engine's 21 window commands, each once, through the core's own code path (`engine::run`, `engine::answer`,
//! `engine::run_stream`), against a throwaway workspace wired to the repository's loopback fakes. Ignored by default:
//! it needs the fakes running and the workspace prepared (`packaging/real-shapes.ps1` does both, then gives the collected
//! answers to `app/ui/tests/seam-shape.test.mjs` with LF_REAL_ANSWERS). The two variables are read by this test binary
//! only; the app reads neither.
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use leadforge_window::engine::{self, EngineCommand, EngineInput, EngineProgram, KillHandle};
use serde_json::{json, Map, Value};

fn call(p: &EngineProgram, cmd: EngineCommand, args: Value, ws: &Path) -> Value {
    let input = EngineInput::from_args(&args).unwrap();
    let r = engine::run(p, cmd, &input, ws, |_| {}, |_| {})
        .map_err(|e| e.to_value())
        .and_then(|out| engine::answer(&out).map(|t| serde_json::from_str::<Value>(&t).unwrap()));
    match r {
        Ok(doc) => json!({"ok": true, "doc": doc}),
        Err(doc) => json!({"ok": false, "doc": doc}),
    }
}

/// One `run_start` through `engine::run_stream`. With `stop_after` the core's `run_stop` path runs beside it once that many
/// progress lines arrived. Returns (the answer, every relayed line, the stop's answer).
fn run(
    p: &EngineProgram,
    ws: &Path,
    campaign: &str,
    resume: bool,
    stop_after: Option<usize>,
) -> (Value, Vec<Value>, Option<Value>) {
    let lines: Arc<Mutex<Vec<Value>>> = Arc::default();
    let answer: Arc<Mutex<Option<Value>>> = Arc::default();
    let handle: Arc<Mutex<Option<KillHandle>>> = Arc::default();
    let (p2, ws2, l2, a2, h2) = (
        p.clone(),
        ws.to_path_buf(),
        lines.clone(),
        answer.clone(),
        handle.clone(),
    );
    let campaign = campaign.to_string();
    let runner = std::thread::spawn(move || {
        let input =
            EngineInput::from_args(&json!({"args": {"campaign": campaign, "resume": resume}}))
                .unwrap();
        engine::run_stream(
            &p2,
            &input,
            &ws2,
            |a| {
                *a2.lock().unwrap() = Some(match a {
                    Ok(t) => json!({"ok": true, "doc": serde_json::from_str::<Value>(&t).unwrap()}),
                    Err(e) => json!({"ok": false, "doc": e}),
                })
            },
            |l| l2.lock().unwrap().push(serde_json::from_str(&l).unwrap()),
            |h| *h2.lock().unwrap() = Some(h),
        )
    });
    let mut stopped = None;
    if let Some(n) = stop_after {
        let t0 = Instant::now();
        loop {
            let progress = lines
                .lock()
                .unwrap()
                .iter()
                .filter(|l| l["type"] == "progress")
                .count();
            if progress >= n || runner.is_finished() || t0.elapsed() > Duration::from_secs(300) {
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        let id = answer
            .lock()
            .unwrap()
            .as_ref()
            .map(|a| a["doc"]["runId"].clone());
        if let Some(id) = id {
            let stop = call(p, EngineCommand::RunStop, json!({"runId": id}), ws);
            let as_result = if stop["ok"] == true {
                Ok(stop["doc"].to_string())
            } else {
                Err(stop["doc"].clone())
            };
            let h = handle.lock().unwrap().clone();
            engine::after_stop(&as_result, h.as_ref(), engine::STOP_WAIT);
            stopped = Some(stop);
        }
    }
    let summary = runner.join().unwrap();
    eprintln!("run {stop_after:?}: {summary:?}");
    let a = answer.lock().unwrap().clone().unwrap_or(Value::Null);
    let l = lines.lock().unwrap().clone();
    (a, l, stopped)
}

fn status_of_last(lines: &[Value]) -> Value {
    match lines.last() {
        Some(l) if l.get("status").is_some() => json!({"ok": true, "doc": l["status"]}),
        Some(l) => json!({"ok": false, "doc": l}),
        None => json!({"ok": false, "doc": null}),
    }
}

#[test]
#[ignore = "needs the loopback fakes and a prepared workspace: packaging/real-shapes.ps1"]
fn the_real_engine_answers_all_21_commands() {
    let ws = PathBuf::from(std::env::var("LF_REAL_WS").expect("LF_REAL_WS"));
    let out = PathBuf::from(std::env::var("LF_REAL_OUT").expect("LF_REAL_OUT"));
    fs::create_dir_all(&out).unwrap();
    let p = EngineProgram::dev_venv();
    assert_eq!(p.prefix.last().unwrap(), "leadforge", "the real engine");
    let mut a = Map::new();
    let mut put = |k: &str, v: Value| {
        eprintln!("{k}: {}", &v.to_string()[..v.to_string().len().min(240)]);
        a.insert(k.to_string(), v);
    };
    put(
        "settings_get",
        call(&p, EngineCommand::SettingsGet, json!({}), &ws),
    );
    // the incomplete form, on purpose (an error document)
    let mut bad = call(
        &p,
        EngineCommand::CampaignCreate,
        json!({"draft": {"kinds": [], "places": [], "country": "", "source": "dvsa", "offer": "", "sicCodes": [], "maxLeads": 0}}),
        &ws,
    );
    bad["expectError"] = json!(true);
    put("campaign_create_incomplete", bad);
    let draft = json!({"kinds": ["car repair"], "places": ["Bristol"], "country": "GB", "source": "dvsa",
        "offer": "Online booking for independent garages", "sicCodes": [], "maxLeads": 50});
    let plan = call(
        &p,
        EngineCommand::CampaignCreate,
        json!({"draft": draft}),
        &ws,
    );
    let campaign = plan["doc"]["campaign"].as_str().unwrap_or("").to_string();
    put("campaign_create", plan);
    // the run, stopped by run_stop beside it after its second progress line (scripts/e2e_window_run.py's way), then
    // continued to its end
    let (first, lines1, stop) = run(&p, &ws, &campaign, false, Some(2));
    put("run_start_first_handle", first);
    put(
        "run_stop",
        stop.unwrap_or(json!({"ok": false, "doc": null})),
    );
    put("run_stop_end_status", status_of_last(&lines1));
    let (handle, mut lines, _) = run(&p, &ws, &campaign, true, None);
    let run_id = handle["doc"]["runId"].clone();
    put("run_start_handle", handle);
    put("run_end_status", status_of_last(&lines));
    lines.splice(0..0, lines1);
    put("run_start_events", Value::Array(lines));
    put(
        "run_status",
        call(&p, EngineCommand::RunStatus, json!({"runId": run_id}), &ws),
    );
    put(
        "run_status_latest",
        call(&p, EngineCommand::RunStatus, json!({"runId": null}), &ws),
    );
    put(
        "campaigns_list",
        call(&p, EngineCommand::CampaignsList, json!({}), &ws),
    );
    let sheet = call(
        &p,
        EngineCommand::SheetExport,
        json!({"runId": run_id}),
        &ws,
    );
    put("sheet_export", sheet);
    // sheet_open with a path outside the exports folder: refused (an accepted one opens a program on the owner's screen)
    let mut open = call(
        &p,
        EngineCommand::SheetOpen,
        json!({"path": "C:\\Windows\\win.ini"}),
        &ws,
    );
    open["expectError"] = json!(true);
    put("sheet_open", open);
    let people = call(
        &p,
        EngineCommand::PeopleList,
        json!({"query": {"search": "", "limit": 500}}),
        &ws,
    );
    let someone = people["doc"]["people"]
        .as_array()
        .and_then(|l| {
            l.iter()
                .find_map(|x| x["email"].as_str().map(str::to_string))
        })
        .unwrap_or_else(|| "nobody@nowhere.example".into());
    put("people_list", people);
    // report first, as the People screen does: the dry run (`dry_run`, snake_case) changes nothing and answers the same
    // shape; then the real call, with the same value
    put(
        "person_forget_dry",
        call(
            &p,
            EngineCommand::PersonForget,
            json!({"value": someone, "dry_run": true}),
            &ws,
        ),
    );
    put(
        "person_forget_dry_again",
        call(
            &p,
            EngineCommand::PersonForget,
            json!({"value": someone, "dry_run": true}),
            &ws,
        ),
    );
    put(
        "person_forget",
        call(
            &p,
            EngineCommand::PersonForget,
            json!({"value": someone, "dry_run": false}),
            &ws,
        ),
    );
    put(
        "address_suppress",
        call(
            &p,
            EngineCommand::AddressSuppress,
            json!({"value": "kestrel-garage.example", "kind": null}),
            &ws,
        ),
    );
    put(
        "purge_report",
        call(&p, EngineCommand::PurgeReport, json!({}), &ws),
    );
    put(
        "purge_apply",
        call(&p, EngineCommand::PurgeApply, json!({}), &ws),
    );
    put(
        "retention_get",
        call(&p, EngineCommand::RetentionGet, json!({}), &ws),
    );
    put(
        "retention_set",
        call(&p, EngineCommand::RetentionSet, json!({"months": 6}), &ws),
    );
    let mut keys = call(&p, EngineCommand::KeysList, json!({}), &ws);
    // key_save and key_remove only where no keyring can be reached (a keyring reached is point 7's guarded proof)
    let no_keyring = keys["ok"] == false;
    if no_keyring {
        keys["expectError"] = json!(true); // the shape of KeyStatus is then not seen: reported, not hidden
    }
    put("keys_list", keys);
    if no_keyring {
        let mut s = call(
            &p,
            EngineCommand::KeySave,
            json!({"name": "opencorporates_token", "value": "LF-SHAPES-MADE-UP-0001"}),
            &ws,
        );
        s["expectError"] = json!(true);
        put("key_save", s);
        let mut r = call(
            &p,
            EngineCommand::KeyRemove,
            json!({"name": "opencorporates_token"}),
            &ws,
        );
        r["expectError"] = json!(true);
        put("key_remove", r);
    }
    put(
        "settings_set",
        call(
            &p,
            EngineCommand::SettingsSet,
            json!({"patch": {"openSheetWhenDone": false}}),
            &ws,
        ),
    );
    put("about", call(&p, EngineCommand::About, json!({}), &ws));
    put(
        "purge_everything",
        call(
            &p,
            EngineCommand::PurgeEverything,
            json!({"confirm": true}),
            &ws,
        ),
    );
    fs::write(
        out.join("answers.json"),
        serde_json::to_string_pretty(&Value::Object(a)).unwrap(),
    )
    .unwrap();
}
