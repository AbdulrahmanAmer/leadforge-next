//! The window carries the engine's version: Cargo.toml's version equals pyproject.toml's.
use std::fs;
use std::path::PathBuf;

fn version_in(path: &PathBuf, section: &str) -> String {
    let text = fs::read_to_string(path).unwrap();
    let mut in_section = false;
    for line in text.lines().map(str::trim) {
        if line.starts_with('[') {
            in_section = line == section;
        } else if in_section && line.starts_with("version") {
            return line.split('"').nth(1).unwrap().to_string();
        }
    }
    panic!("no version in {section} of {}", path.display());
}

#[test]
fn window_and_engine_versions_agree() {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let window = version_in(&here.join("Cargo.toml"), "[package]");
    let engine = version_in(
        &here.join("..").join("..").join("pyproject.toml"),
        "[project]",
    );
    assert_eq!(
        window, engine,
        "app/src-tauri/Cargo.toml and pyproject.toml disagree"
    );
}
