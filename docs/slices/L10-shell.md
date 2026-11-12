# L10 The window's shell (the Rust half of "Window: screens and shell")

## Starting list
- The plan (blueprint ADOPT 8, L4-ONWARD L10): a Tauri 2 window whose Rust core starts the bundled Python engine; the window can start
  nothing; no remote content, a content security policy; one test reads the permission files; both packagings measured (size,
  start-up three times, Defender) and one chosen; per-user install with no admin prompt; the build under the `heavy` lock with its peak
  memory recorded. Leaves out: any flow. The screens (`app/ui`) are built in parallel by `designer`; this slice owns `app/src-tauri`.
- Nothing in `src/leadforge` changes: `leadforge --json version` already prints `leadforge X.Y.Z` and an `ok` `LF_DIGEST` line,
  which is all the core reads.

# Build (Unreleased, no version bump)

## Item 1 — the core and its one way to start a program

**Must do (written before the code).** `app/src-tauri` is a Tauri 2 app. `src/engine.rs` holds the crate's only `Command::new(`.
The program is a fixed path: release builds `<resources>/engine/python/python.exe` (the bundled engine), debug builds the worktree's
`.venv/Scripts/python.exe` (compiled into debug builds only). Its leading arguments are fixed (`-X utf8 -I -m leadforge`: UTF-8,
isolated mode, the engine module); the rest come only from `EngineCommand`, a closed enum (today `Version` -> `--json version`).
The window sends no string that becomes a path or an argument. The engine runs with a cleared environment plus a short list
(`SYSTEMROOT`, `TEMP`, `APPDATA`, ...), no console window, stdin closed, its working folder the app's own local data folder
(`%LOCALAPPDATA%\app.leadforge.window\workspace`), a timeout per command (60 s for `Version`), output capped. One engine at a time
(a gate in the core; a second call while one runs gets `busy`).

**For the next slice.** `engine::run` already hands every stdout line to a callback as it arrives: L11's `Run` variant relays each
`LF_PROGRESS` line as a Tauri event from there. New variants carry typed, validated fields (planned in the enum's doc comment:
`NewCampaign`, `Run`, `Results`, `People`, `Forget`, `Suppress`, `Purge`, `RetentionGet`, `RetentionSet`, `KeysStatus`; no send
command, C14). Each new window command also needs its name in `build.rs`, a permission in `capabilities/main.json` and a line in the
permission test's list: three places, on purpose.

**The window's surface (for `app/ui`).** One Tauri command, `engine_version`, no arguments:
`invoke('engine_version')` resolves to `{ version: string, origin: "bundled" | "dev-venv", millis: number }` or rejects with
`{ kind: "not_found" | "busy" | "start_failed" | "timeout" | "failed" | "bad_output", message: string }`.
`app.withGlobalTauri` is on, so a page without a bundler can call `window.__TAURI__.core.invoke`; the React build can use
`@tauri-apps/api/core` instead. No event is emitted yet. The page is `app/src-tauri/placeholder/` until the screens replace it:
then `build.frontendDist` becomes `../ui/dist` (the permission test keeps any `devUrl` on loopback).

**Permission files.** `capabilities/main.json` grants window `main` exactly `allow-engine-version` (generated from `build.rs`'s
app manifest, so the command is denied unless granted). No plugin at all (no shell, opener, fs, http, dialog); `Cargo.toml`
depends on `tauri`, `serde`, `serde_json` only. CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:;
font-src 'self'; connect-src ipc: http://ipc.localhost; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'`
(no remote origin, no inline script or style, no `eval`); `freezePrototype` on; the asset protocol off.

**Tests of the core.** `cargo test --locked` in `app/src-tauri`: 7 unit tests in `engine.rs` (fixed arguments, isolated
interpreter flags, a good reply parsed, a failed digest / a non-zero exit / a strange version refused, a missing engine is
`not_found`); `tests/engine_dev.rs` starts the real dev engine through `engine::run` and requires pyproject.toml's version back
(it fails, not skips, without the `.venv`); `tests/version_agrees.rs` requires `Cargo.toml`'s version to equal pyproject.toml's.
`#![forbid(unsafe_code)]` in the crate. Not watched failing one by one in this slice: the engine tests (carried over).

## Item 2 — the permission test

`app/src-tauri/permission-check/tests/permissions.rs`, its own small crate (`serde_json` only), run by `cargo test` in that folder.
Why its own crate (found while watching it fail): planted inside the app's own tests, `shell:allow-execute` never reached the test,
because the app's build script refuses an unknown permission first (`tauri build script failed: Permission shell:allow-execute not
found, expected one of allow-engine-version, deny-engine-version, core:default, ...`). That refusal is a second guard, but it only
holds while the shell plugin is not a dependency; the test must fail on its own. As its own crate it runs in seconds without
building Tauri, so CI can run it on every push.
It reads every file under `capabilities/`, `tauri.conf.json` and the bundle
overlay `tauri.bundle.conf.json`, every file under `permissions/` (including the set `tauri-build` generates: only allow/deny of a listed command), `build.rs`'s command list, `lib.rs`'s `generate_handler!` list, the
`[dependencies]` of `Cargo.toml`, and counts `Command::new(` in `src/`. It fails on: a permission off the list
(`ALLOWED_PERMISSIONS = ["allow-engine-version"]`), with a separate "PROGRAM-START PERMISSION" line for anything naming shell,
process, execute, spawn, sidecar, command or open; a capability key off the list (`remote` included), a window wildcard; a CSP with
`unsafe-inline`, `unsafe-eval`, `wasm-unsafe-eval`, `*`, a scheme or any `://` origin except `http://ipc.localhost`, or without
`default-src 'self'` / `script-src 'self'` / `object-src 'none'`; any `dangerous*` key; the asset protocol on; a plugin config; a
remote window URL or a non-loopback `devUrl`; a command, handler or dependency off its list; a `.plugin(` registration; anything
but exactly one `Command::new(`, in `engine.rs`. Two more tests plant faults in memory and require each to be caught.

**Seen red, then green** (2026-11-12, `scratchpad` script: plant, `cargo test --locked`, restore, `cargo test --locked`).
Planted: `"permissions": ["allow-engine-version", "shell:allow-execute"]` in `capabilities/main.json`. Red:
```
test the_window_can_start_nothing_and_holds_only_listed_permissions ... FAILED
2 problem(s):
  capabilities/main.json: PROGRAM-START PERMISSION `shell:allow-execute`: the window may not start a program
  capabilities/main.json: permission `shell:allow-execute` is not on the allow-list ["allow-engine-version"]
test result: FAILED. 2 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```
Removed again, green: `test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s`.

## Item 3 — the built app shows the engine's version

The dev engine: `.venv` made the CI install job's way (`pip install --require-hashes --only-binary :all: -r requirements.lock`,
then `--no-deps --no-build-isolation -e .`), `leadforge version` -> `leadforge 0.7.3`. The debug app (`cargo build --locked`) run by
`app/src-tauri/packaging/smoke-window.ps1`: starts it with `--smoke`, waits for the core's log line, captures the app's own window
with `PrintWindow`, and the app exits by itself 4 s after the window's call (a smoke run that hears nothing exits 1 after 90 s).
Output of the run (the window was on the owner's screen for about 5 s):
```
window 'LeadForge' 968x667, screenshot True
app exit code: 0
core.log lines of this run:
1794468105 leadforge-core: started (smoke=true)
1794468105 leadforge-core: page Started: http://tauri.localhost/
1794468105 leadforge-core: page Finished: http://tauri.localhost/
1794468106 leadforge-core: engine_version ok: version=0.7.3 origin=dev-venv millis=498
1794468110 leadforge-core: smoke: exiting
```
The screenshot shows the placeholder page with `Engine: leadforge 0.7.3 (dev-venv, 498 ms)`. Afterwards: no `leadforge-window`
process, no WebView2 process of the app. A first try read the page through WebView2's DevTools port
(`WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS`): no target ever answered, so it was replaced by `PrintWindow`.

## Item 4 — the two packagings, measured

Both built from the same hashed lock (`requirements.lock`, wheels only) and the engine's own wheel, on this laptop (8 GB, Windows 11,
Defender real-time protection on, no exclusion). Each measured from a fresh copy in `D:\Temp\lf-measure\`: size on disk, three runs of
`--json version` (the first is the first start of that copy), then a Defender custom scan of the folder (`MpCmdRun -Scan -ScanType 3`),
`Get-MpThreatDetection` since the start, and whether the program file still exists. Script: `app/src-tauri/packaging/measure-engine.ps1`.

| Packaging | Size on disk | `version`, three starts (first = first start of the copy) | Defender |
|---|---|---|---|
| (a) one PyInstaller file (`--onefile`, 6.22.3) | 40.5 MB, 1 file | 5.26 s, 5.36 s, 5.00 s | scan: no threats; no detection; file present after |
| (b) embeddable Python 3.12.10 + packages beside it (bytecode compiled at build) | 166.4 MB, 8,311 files | 1.75 s, 0.91 s, 0.96 s | scan: no threats; no detection; files present after |

Raw lines (`measure-engine.ps1`):
```
pyinstaller: 40.5 MB in 1 files; starts: 5.26s(exit 0, 'leadforge 0.7.3'), 5.36s(exit 0, 'leadforge 0.7.3'), 5.00s(exit 0, 'leadforge 0.7.3'); Defender scan: Scanning D:\Temp\lf-measure\pyinstaller found no threats.; detections since start: no detection; program file present after: True
embed: 166.4 MB in 8311 files; starts: 1.75s(exit 0, 'leadforge 0.7.3'), 0.91s(exit 0, 'leadforge 0.7.3'), 0.96s(exit 0, 'leadforge 0.7.3'); Defender scan: Scanning D:\Temp\lf-measure\embed found no threats.; detections since start: no detection; program file present after: True
```
**Chosen: (b), embeddable Python.** The plan's rule is size, start-up and Defender. Defender treats both alike (clean). Start-up
decides: the one-file build unpacks itself into a temp folder on every start, about 5 s each time, every time (right at the plan's
"about 5 seconds" line), while (b) starts in under 1 s warm and 1.75 s cold. The price of (b) is size: 4 times the bytes and 8,311
files (the installer compresses both; installer size below). (b) also runs as one process (`python.exe -I -m leadforge`), so the
core's timeout stops the whole engine; the one-file build is a bootloader plus a child, and stopping the parent alone can leave the
child running. **The trigger of the plan (ADOPT 8) is not met:** under (b) the engine starts in well under 5 s and Defender
quarantined nothing. Scripts: `packaging/build-engine-embed.ps1`, `packaging/build-engine-pyinstaller.ps1` (kept so the
measurement can be repeated, for example on the other laptop or after an engine change).

## Item 5 — the per-user installer

**Built.** `npm ci --ignore-scripts`, then under the `heavy` lock, measured by `packaging/run-measured.ps1` (sum of the working sets
of the build's whole process tree, sampled every second):
`node_modules\@tauri-apps\cli\tauri.js build --config tauri.bundle.conf.json --bundles nsis -- --locked`
```
exit 0; duration 404 s; peak working set of the build's process tree 2,399 MB; free RAM before 3036 MB
    Finished `release` profile [optimized] target(s) in 4m 28s
        D:\LeadForge\wt\target\release\bundle\nsis\LeadForge_0.7.3_x64-setup.exe (34.57 MiB)
```
(cold release build, `-j 2`; the bundle overlay adds the chosen engine as resources `engine/python/`.) The installer carries the
core engine only: the hashed lock's packages, none of the extras (no NER model, no browser rescue, no Maps tooling).
The release app, before installing, from `target\release` (resources beside it), smoke run (window on screen about 5 s):
`engine_version ok: version=0.7.3 origin=bundled millis=1035`, app exit code 0, screenshot taken, no process left.

**Read from the generated script** (`target\release\nsis\x64\installer.nsi`): `!define INSTALLMODE "currentUser"`, so
`RequestExecutionLevel user` (line 105; `admin` only under `perMachine`); default folder `$LOCALAPPDATA\LeadForge`; `/D=` overrides
it; `/NS` skips every shortcut (Start menu and desktop, line 506 and 18644); the uninstaller removes the app data folders only when
the user ticks "delete app data".

**The install itself: UNPROVEN.** This session's token is elevated (`IsInRole(Administrator)` = True), and an elevated run shows no
prompt whatever the installer needs, so it was not run here. `packaging/install-proof.ps1` refuses an elevated shell (seen:
`REFUSED: this PowerShell is elevated; open an ordinary one`, exit 2, nothing installed). What settles it, one command from an
ordinary PowerShell:
`powershell -NoProfile -ExecutionPolicy Bypass -File D:\LeadForge\wt\shell\app\src-tauri\packaging\install-proof.ps1 -Setup D:\LeadForge\wt\target\release\bundle\nsis\LeadForge_0.7.3_x64-setup.exe`
It installs silently to `D:\Temp\lf-install\LeadForge` with `/S /NS`, runs the installed app's smoke (a window for about 5 s),
uninstalls silently, and prints `PASS` only if no process runs from and no file is left in `D:\Temp\lf-install`. A UAC prompt during
it means the pass line failed.

## Item 6 — CI (not added in this slice)

The public repository's runners would build Tauri on every push. What I would add, two jobs, both only when `app/src-tauri/**`
changes (`on.push.paths` / `on.pull_request.paths`), actions pinned by SHA, read-only token:
1. `window permissions` (ubuntu-latest): `cargo test --locked` in `app/src-tauri/permission-check`. Measured here: 4.6 s compile
   from a warm registry, 12 crates; on a runner well under a minute with the toolchain step. Cheap enough for every push.
2. `window core` (windows-latest): the `.venv` the install job's way, then in `app/src-tauri`: `cargo fmt --check`,
   `cargo clippy --all-targets --locked -- -D warnings`, `cargo test --locked` (the engine test needs the `.venv`). Measured here,
   cold, `-j 2` on this laptop: clippy 182 s with a peak of 2,059 MB; a runner has 4 cores, so roughly 3 to 5 minutes cold and
   about 1 minute with a cargo cache keyed on `Cargo.lock`. Release builds and the installer stay local (`heavy` lock) until a
   release job is decided.

## Installs (what was checked before each)

Nothing machine-wide, nothing needing administrator rights, no Defender exclusion. Rule used for every pin: no version younger
than 7 days (supply-chain rule 1).
- `@tauri-apps/cli` 2.12.4 (npm, published 2026-10-21 by the tauri-apps maintainers; `app/src-tauri/package.json` exact, lockfile
  committed), integrity `sha512-JI9bHfudSRJikGOrjbXEm6RjzzvmKuLc+JixB1NE8hNzQkNlCCIC3pTES3uypkR9lxHrsbxzcnSwhI2IxBQphw==`; its
  binary `@tauri-apps/cli-win32-x64-msvc` 2.12.4 `sha512-DJhDeCqjLDNMWYFy7ZS8cfeAHX2RK0RbQMLiA3bMVVkXRDJ4NBYiHriGqsUhsr9iG41aTb+dJGkFPmPw1gWwVw==`
  (an optional dependency, no install script). Installed with `npm ci --ignore-scripts` (2 packages).
- Rust crates: `tauri` =2.12.5 (2026-10-21), `tauri-build` =2.7.4 (2026-10-21), `serde`, `serde_json`; 419 crates in
  `app/src-tauri/Cargo.lock`, each with crates.io's sha256. All 419 checked against crates.io's publish date: 18 were younger than 7
  days and were moved to the newest older compatible version (`cargo update --precise`): bit-vec 0.10.1, brotli-decompressor 6.2.0,
  cc 1.11.0, crc32fast 1.5.4, flate2 1.1.10, itoa 1.0.18, jiff/jiff-static 0.2.39, jiff-core 0.1.2, mime 0.3.17, serde_spanned
  1.1.2, smallvec 1.16.4, syn 3.0.9, toml 1.2.0, toml_edit 0.25.18, toml_datetime 1.1.2, uuid 1.29.0, wry 0.57.1. The
  permission-check crate's own lock (12 crates) uses the same versions.
- PyInstaller 6.22.3 (PyPI, 2026-09-12) and its five dependencies, in a throwaway build venv outside the repo, from
  `app/src-tauri/packaging/requirements-pyinstaller.txt` (PyPI's sha256 per wheel, `--require-hashes --only-binary :all:`).
- python.org's embeddable Python 3.12.10 (`python-3.12.10-embed-amd64.zip`, 11,133,606 bytes, from python.org/ftp): SHA-256
  `4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3` as published in python.org's SBOM for that file
  (`.spdx.json`; the release page and the download API list no SHA-256 for 3.12.10), MD5 `fe8ef205f2e9c3ba44d0cf9954e1abd3` as in
  python.org's download API; both matched before unpacking, and `build-engine-embed.ps1` checks the SHA-256 again.
- NSIS for the installer: fetched by the Tauri CLI itself on the first bundle, into `%LOCALAPPDATA%\tauri\NSIS` (per user):
  `nsis-3.13.zip` from `github.com/tauri-apps/binary-releases` and `nsis_tauri_utils.dll` v0.5.3 from
  `github.com/tauri-apps/nsis-tauri-utils`, each checked by the CLI against the hash built into it (`Info validating hash`). Not
  checked by me before the download (the CLI does it inside the build); afterwards: `makensis.exe` sha256
  `4ec390d0f96f9728507fbc2f4e91311dd90bfc6c8ddfe2159357b3651ae151c0`, `Bin\makensis.exe`
  `65343c225ec88393cc4453b0963caf63f763f42f48cb55736d51893ff2e29d4a`, `nsis_tauri_utils.dll`
  `5ba143b5db4a87d32d6e7802e033330aae56cbceabe0d1e3ba41948385ad4709`.

## Carried over (noticed, not done)

- `rust-toolchain.toml` not added: pinning `1.99.1` by name makes rustup fetch a second copy of the toolchain it already has as
  `stable` (the laptop's disk); pin it when CI is added.
- The engine tests of the core were not each watched failing (only the permission test was).
- No single-instance guard: two copies of the app would each start their own engine. The core's gate holds one engine per app;
  L11 needs one per machine before any flow writes data (a lock file the engine already respects, or the single-instance plugin
  after the permission test's list is reviewed).
- The embeddable package carries `setuptools` (in `requirements.lock` as the build backend) and the bytecode next to the sources:
  both could be trimmed for size; not measured.
- PyInstaller (a) was measured on `version` only; whether every engine module (data files of `trafilatura`, `dateparser`,
  `babel`, `tld`, `phonenumbers`) works frozen is unknown, and moot while (b) is chosen.
- `app.withGlobalTauri` is on for the placeholder page; the React screens can import `@tauri-apps/api` and the global can go.
- WebView2: the installer keeps Tauri's default (download the WebView2 bootstrapper only if WebView2 is missing). Windows 11 has it.
- The app is unsigned (0.x, as the stack standard says): Windows SmartScreen warns on the installer.

## Results of the local runs

- `cargo clippy --all-targets --locked -- -D warnings` (app, first cold run under `run-measured.ps1`): `exit 0; duration 182 s; peak
  working set of the build's process tree 2,059 MB`; again after the last change: `Finished`, exit 0. Permission-check crate: exit 0.
- `cargo fmt --check`: exit 0. `cargo test --locked` (app): 7 + 1 + 1 passed, exit 0; (permission-check): 3 passed, exit 0.
- Free disk on D: at the start 8.2 GB; other sessions freed space during the run; at the end 45 GB (`df`: 129G size, 85G used).
- Every build ran through the `heavy` lock, one at a time; it was held by other sessions' jobs for about 10 minutes in total.
