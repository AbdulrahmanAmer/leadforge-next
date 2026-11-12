//! The stand-in ships exactly while the core uses it: `STAND_IN = true` needs its resource line in the bundle
//! overlay, `STAND_IN = false` (the switch, once the real `leadforge window` commands exist) forbids it.
use std::fs;
use std::path::Path;

#[test]
fn the_stand_in_ships_only_while_the_core_uses_it() {
    let overlay =
        fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("tauri.bundle.conf.json"))
            .unwrap();
    let shipped = overlay.contains("leadforge_window_standin");
    if leadforge_window::engine::STAND_IN {
        assert!(
            shipped,
            "STAND_IN is on: the bundle must carry the stand-in"
        );
    } else {
        assert!(
            !shipped,
            "STAND_IN is off: remove the stand-in's line from tauri.bundle.conf.json"
        );
    }
}
