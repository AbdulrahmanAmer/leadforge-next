// The app's own commands are declared here, so each one needs a permission in capabilities/ before the window
// can call it (deny by default). permission-check/tests/permissions.rs reads this list.
fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["engine_version"])),
    )
    .expect("tauri build script failed");
}
