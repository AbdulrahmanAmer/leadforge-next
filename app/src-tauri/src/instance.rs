//! One copy of the app at a time, so two windows never start two engines on one workspace.
//! The first copy holds `%LOCALAPPDATA%\<identifier>\instance.lock` open with no sharing; a second copy cannot open
//! it, writes `focus.request` beside it and exits; the first copy sees that file and brings its window to the front.
//! Fails open: if the folder cannot be made, the app starts (a guard never stops the app from starting).

use std::fs::{self, File};
use std::path::PathBuf;
use std::time::Duration;

use tauri::{AppHandle, Manager};

pub struct Instance {
    _lock: Option<File>,
    focus: Option<PathBuf>,
}

/// `None`: another copy runs and has been asked to come to the front; this copy must exit.
pub fn claim(identifier: &str) -> Option<Instance> {
    let Some(base) = std::env::var_os("LOCALAPPDATA") else {
        return Some(Instance {
            _lock: None,
            focus: None,
        });
    };
    let dir = PathBuf::from(base).join(identifier);
    if fs::create_dir_all(&dir).is_err() {
        return Some(Instance {
            _lock: None,
            focus: None,
        });
    }
    let focus = dir.join("focus.request");
    match open_exclusive(&dir.join("instance.lock")) {
        Ok(f) => {
            let _ = fs::remove_file(&focus);
            Some(Instance {
                _lock: Some(f),
                focus: Some(focus),
            })
        }
        Err(e) if is_sharing_violation(&e) => {
            let _ = fs::write(&focus, b"focus");
            eprintln!("leadforge-core: another copy is running; asked it to come to the front");
            None
        }
        Err(_) => Some(Instance {
            _lock: None,
            focus: None,
        }),
    }
}

#[cfg(windows)]
fn open_exclusive(path: &std::path::Path) -> std::io::Result<File> {
    use std::os::windows::fs::OpenOptionsExt;
    fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .share_mode(0)
        .open(path)
}

#[cfg(not(windows))]
fn open_exclusive(path: &std::path::Path) -> std::io::Result<File> {
    fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)
}

fn is_sharing_violation(e: &std::io::Error) -> bool {
    // ERROR_SHARING_VIOLATION (32) or ERROR_LOCK_VIOLATION (33)
    matches!(e.raw_os_error(), Some(32) | Some(33))
}

impl Instance {
    /// Watches for a second copy's request and brings the main window to the front.
    pub fn watch_for_focus(self, app: AppHandle) {
        let Some(focus) = self.focus.clone() else {
            return;
        };
        std::thread::spawn(move || {
            let _keep = self; // the lock lives as long as this thread, which lives as long as the app
            loop {
                std::thread::sleep(Duration::from_millis(400));
                if focus.exists() {
                    let _ = fs::remove_file(&focus);
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.unminimize();
                        let _ = w.show();
                        let _ = w.set_focus();
                    }
                    crate::core_log(
                        &app,
                        "instance: a second copy asked for the window; brought it to the front",
                    );
                }
            }
        });
    }
}
