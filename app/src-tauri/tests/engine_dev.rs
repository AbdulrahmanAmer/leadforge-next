//! The core's one program start, end to end in a debug build: the worktree's `.venv` engine answers `version`
//! through `engine::run`, and the core reads pyproject.toml's version out of it. Needs the `.venv` made the way CI's
//! install job makes it (docs/slices/L10-shell.md item 3); without it this test fails, it does not skip.
use std::fs;
use std::path::Path;

use leadforge_window::engine::{self, EngineCommand, EngineProgram};

#[test]
fn the_dev_engine_reports_the_project_version() {
    let program = EngineProgram::dev_venv();
    assert!(
        program.program.is_file(),
        "no dev engine at {} (make the .venv first)",
        program.program.display()
    );
    let work = std::env::temp_dir().join("lf-window-engine-test");
    fs::create_dir_all(&work).unwrap();
    let mut seen = 0;
    let out =
        engine::run(&program, EngineCommand::Version, &work, |_| seen += 1).expect("engine ran");
    let version = engine::parse_version(&out).expect("a version");
    let pyproject =
        fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../pyproject.toml"))
            .unwrap();
    assert!(
        pyproject.contains(&format!("version = \"{version}\"")),
        "engine says {version}, pyproject.toml disagrees"
    );
    assert_eq!(
        seen,
        out.stdout_lines.len(),
        "every stdout line went through the callback"
    );
    let _ = fs::remove_dir_all(&work);
}
