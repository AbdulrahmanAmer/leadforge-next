// No console window in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
#![forbid(unsafe_code)]

fn main() {
    leadforge_window::run();
}
