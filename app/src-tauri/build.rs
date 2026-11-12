// The app's own commands are declared here, so each one needs a permission in capabilities/ before the window
// can call it (deny by default). permission-check/tests/permissions.rs reads this list.
fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "campaign_create",
            "run_start",
            "run_stop",
            "run_status",
            "campaigns_list",
            "sheet_export",
            "sheet_open",
            "people_list",
            "person_forget",
            "address_suppress",
            "purge_report",
            "purge_apply",
            "purge_everything",
            "retention_get",
            "retention_set",
            "keys_list",
            "key_save",
            "key_remove",
            "settings_get",
            "settings_set",
            "about",
        ]),
    ))
    .expect("tauri build script failed");
}
