//! The start, the stop and the end of a run, through the core's own code path (`engine::run_stream`, the same
//! function the `run_start` command calls, and `engine::after_stop`, the same one `run_stop` calls), against the
//! stand-in's test cases (each chosen by a made-up campaign name: `CASES` in the stand-in). The wait after a stop
//! is a parameter of `after_stop`: the app passes `engine::STOP_WAIT` (90 s); these tests pass a short one where
//! the case needs it. Needs the worktree's `.venv`, like `engine_dev.rs`.
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{mpsc, Arc, Mutex};
use std::time::{Duration, Instant};

use leadforge_window::engine::{
    self, EngineCommand, EngineInput, EngineProgram, KillHandle, StreamSummary,
};
use serde_json::{json, Value};

fn workdir(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("lf-window-seam-{name}-{}", std::process::id()));
    let _ = fs::remove_dir_all(&d);
    fs::create_dir_all(&d).unwrap();
    d
}

/// A run started on its own thread, as the `run_start` command does. Everything it gives back is recorded.
struct Started {
    answer: Result<String, Value>,
    relayed: Arc<Mutex<Vec<Value>>>,
    handle: KillHandle,
    done: std::thread::JoinHandle<StreamSummary>,
}

fn start(campaign: &str, dir: &Path) -> Started {
    let p = EngineProgram::standin();
    let input =
        EngineInput::from_args(&json!({"args": {"campaign": campaign, "resume": false}})).unwrap();
    let relayed: Arc<Mutex<Vec<Value>>> = Arc::default();
    let (atx, arx) = mpsc::channel();
    let (htx, hrx) = mpsc::channel();
    let (dir2, relayed2) = (dir.to_path_buf(), relayed.clone());
    let done = std::thread::spawn(move || {
        engine::run_stream(
            &p,
            &input,
            &dir2,
            |a| atx.send(a).unwrap(),
            |line| {
                relayed2
                    .lock()
                    .unwrap()
                    .push(serde_json::from_str(&line).expect("every relayed line is JSON"))
            },
            |h| htx.send(h).unwrap(),
        )
    });
    let handle = hrx
        .recv_timeout(Duration::from_secs(20))
        .expect("the engine started");
    let answer = arx
        .recv_timeout(Duration::from_secs(30))
        .expect("run_start answered");
    Started {
        answer,
        relayed,
        handle,
        done,
    }
}

fn stop(dir: &Path, run: &KillHandle, wait: Duration) -> Value {
    let p = EngineProgram::standin();
    let input = EngineInput::from_args(&json!({"runId": "r-20261112-5e90"})).unwrap();
    let out =
        engine::run(&p, EngineCommand::RunStop, &input, dir, |_| {}, |_| {}).expect("run_stop ran");
    let answer = engine::answer(&out);
    assert!(
        engine::after_stop(&answer, Some(run), wait),
        "a wait was set"
    );
    serde_json::from_str(&answer.unwrap()).unwrap()
}

fn wait_for_lines(s: &Started, n: usize) {
    let until = Instant::now() + Duration::from_secs(20);
    while s.relayed.lock().unwrap().len() < n {
        assert!(Instant::now() < until, "fewer than {n} lines in 20 s");
        std::thread::sleep(Duration::from_millis(50));
    }
}

fn closed_messages(lines: &[Value]) -> usize {
    lines
        .iter()
        .filter(|l| l["type"] == "stream-closed")
        .count()
}

/// Rule 1: an error document on line 1 rejects the command with that document, untouched, after the process
/// ended; nothing is relayed. Plain text on line 1 rejects with the core's own error, even if a handle follows.
#[test]
fn a_refused_start_rejects_with_the_engines_document() {
    let dir = workdir("refuse");
    let s = start("standin-refuse-mot-garages", &dir);
    let doc = s
        .answer
        .clone()
        .expect_err("a refused start is a rejection, not a handle");
    assert_eq!(
        doc,
        json!({"kind": "input", "message": "The engine could not start the run: there is no such campaign.",
               "details": ["campaign: no plan was checked under this name"],
               "next": "Check the plan on the Campaign screen first."}),
        "the engine's document, untouched"
    );
    assert!(s.handle.ended(), "answered only once the process had ended");
    let summary = s.done.join().unwrap();
    assert!(!summary.started);
    assert_eq!(summary.code, Some(4));
    assert!(
        s.relayed.lock().unwrap().is_empty(),
        "nothing relayed for a refused start"
    );

    let g = start("standin-garbled-start", &dir);
    let doc = g
        .answer
        .clone()
        .expect_err("plain text on line 1 is no handle");
    assert_eq!(doc["kind"], "failed");
    assert_eq!(
        doc["message"],
        "The engine did not start the run: its first line was not a run handle."
    );
    assert_eq!(doc["details"], json!([]));
    assert_eq!(doc["next"], Value::Null);
    g.done.join().unwrap();
    assert!(
        g.relayed.lock().unwrap().is_empty(),
        "the later handle was not taken"
    );
    let _ = fs::remove_dir_all(&dir);
}

/// Rule 2: the engine dies after the handle without an end event: one `stream-closed`, after the last line.
#[test]
fn a_run_that_dies_closes_the_stream() {
    let dir = workdir("dies");
    let s = start("standin-dies-mot-garages", &dir);
    let handle: Value = serde_json::from_str(s.answer.as_ref().expect("a handle")).unwrap();
    assert_eq!(handle, json!({"runId": "r-20261112-5e90"}));
    let summary = s.done.join().unwrap();
    let lines = s.relayed.lock().unwrap().clone();
    assert_eq!(
        lines.last().unwrap(),
        &json!({"type": "stream-closed", "exitCode": 3, "reason": "exit"}),
        "the last message is the core's"
    );
    assert_eq!(closed_messages(&lines), 1, "exactly one");
    assert_eq!(lines.iter().filter(|l| l["type"] == "progress").count(), 4);
    assert_eq!(summary.closed, Some("exit"));
    let _ = fs::remove_dir_all(&dir);
}

/// Rule 2: the end event itself was over the line cap: not relayed, and `stream-closed` says why.
#[test]
fn an_end_event_over_the_line_cap_closes_the_stream() {
    let dir = workdir("long");
    let s = start("standin-long-line-mot-garages", &dir);
    assert!(s.answer.is_ok());
    let summary = s.done.join().unwrap();
    let lines = s.relayed.lock().unwrap().clone();
    assert_eq!(
        lines.last().unwrap(),
        &json!({"type": "stream-closed", "exitCode": 0, "reason": "line-too-long"})
    );
    assert_eq!(closed_messages(&lines), 1);
    assert_eq!(summary.dropped, 1);
    let _ = fs::remove_dir_all(&dir);
}

/// Rule 3: a stop that takes about 15 s is waited for with the app's own wait (`STOP_WAIT`): the run writes
/// `stopped` itself, nothing is ended by the core, no `stream-closed`.
#[test]
fn a_slow_stop_is_waited_for() {
    let dir = workdir("slow");
    let s = start("standin-slow-stop-mot-garages", &dir);
    assert!(s.answer.is_ok());
    wait_for_lines(&s, 3);
    let asked = Instant::now();
    let answered = stop(&dir, &s.handle, engine::STOP_WAIT);
    assert_eq!(answered["state"], "stopped");
    assert!(
        asked.elapsed() < Duration::from_secs(8),
        "run_stop answers at once, it does not wait for the run"
    );
    let summary = s.done.join().unwrap();
    let took = asked.elapsed();
    let lines = s.relayed.lock().unwrap().clone();
    assert_eq!(
        closed_messages(&lines),
        0,
        "no stream-closed after an end event: {:?}",
        lines.last()
    );
    assert_eq!(
        lines.last().unwrap()["type"],
        "stopped",
        "the run ended itself"
    );
    assert!(
        took > Duration::from_secs(12),
        "the run really took its time: {took:?}"
    );
    assert_eq!(summary.code, Some(0));
    assert_eq!(summary.closed, None);
    let _ = fs::remove_dir_all(&dir);
}

/// Rule 3: a run that never obeys the stop is ended at the end of the wait, and `stream-closed` says so.
#[test]
fn a_run_that_ignores_the_stop_is_ended_when_the_wait_ends() {
    let dir = workdir("ignores");
    let s = start("standin-ignores-stop-mot-garages", &dir);
    assert!(s.answer.is_ok());
    wait_for_lines(&s, 3);
    let wait = Duration::from_secs(2);
    let asked = Instant::now();
    stop(&dir, &s.handle, wait);
    let summary = s.done.join().unwrap();
    let took = asked.elapsed();
    let lines = s.relayed.lock().unwrap().clone();
    assert_eq!(
        lines.last().unwrap(),
        &json!({"type": "stream-closed", "exitCode": null, "reason": "ended-by-core"})
    );
    assert_eq!(closed_messages(&lines), 1);
    assert!(took >= wait, "not before the wait's end: {took:?}");
    assert!(
        took < Duration::from_secs(12),
        "at the wait's end: {took:?}"
    );
    assert!(s.handle.ended(), "nothing left running");
    assert_eq!(summary.closed, Some("ended-by-core"));
    let _ = fs::remove_dir_all(&dir);
}

/// `after_stop` sets no wait when `run_stop` was refused or when no run is going.
#[test]
fn no_wait_after_a_refused_stop() {
    let refused: Result<String, Value> = Err(json!({"kind": "input", "message": "No run."}));
    assert!(!engine::after_stop(&refused, None, Duration::from_secs(1)));
    assert!(!engine::after_stop(
        &Ok("{}".into()),
        None,
        Duration::from_secs(1)
    ));
}
