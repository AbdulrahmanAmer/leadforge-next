# L11 The window, first half: the shell and the screens joined, wired to the engine seam

## Starting list
- From L10: the shell (`app/src-tauri`, PR 11's branch `slice/L10-shell`, install proven with a normal token at ee17ca4) and the
  screens (`app/ui`, branch `slice/L10-ui` at 5e341be). This branch merges both on top of `master`; the only conflict was the
  changelog's Unreleased block (both lines kept). `master` moved to 0.8.0 (the delete side, ece4c8d) during the build and was merged
  in (changelog only); the window's crate follows the engine's version (`Cargo.toml` 0.8.0, `tests/version_agrees.rs`), and the
  bundled engine was rebuilt at 0.8.0.
- The seam (agreed for the engine side, built on the other laptop): one command group `leadforge window <name>`; one JSON document
  on stdin (the arguments object, `{}` when none); one JSON document on stdout and exit 0; on an error a non-zero exit and
  `{"kind","message","details":[...],"next":null|string}` on stdout; nothing else on stdout, logs on stderr; arguments never in
  argv. `run_start` writes JSON lines. The 21 names and the shapes: `app/ui/src/engine.ts`, `app/ui/src/engine.tauri.ts`.
- Left out of this half: the real engine commands (other laptop), the keyring (the stand-in only pretends), opening a sheet
  (the engine's `sheet_open`), the folder dialog for the workspace.

# Build (Unreleased, no version bump)

## Item 1 — one window: the screens' build is the window's page

`build.frontendDist` is `../ui/dist`; `build.beforeBuildCommand` runs `npm ci --ignore-scripts && npm run build` in `app/ui`
before every `tauri build`. The placeholder page is gone. The window is made by the core in `setup` (not from the config), so
the self-test can add its probe; `app.windows` is empty. The CSP in `tauri.conf.json` is the screens' own
(`default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src ipc: http://ipc.localhost`)
plus `object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'`; Vite also writes the screens' policy into
`dist/index.html`, so both apply. `withGlobalTauri` is off (the screens import `@tauri-apps/api`).

**Supply chain.** The screens' lockfile held 17 packages younger than 7 days: `vite` 8.3.7 (2026-11-09), `rolldown` and its 15
platform bindings 1.2.19 (2026-11-11), `@rolldown/pluginutils` 1.1.0 (2026-11-09). OSV lists no vulnerability for `vite` 8.3.6 or
8.3.7. `vite` is now 8.3.6 (2026-11-05) and the lock was regenerated with `npm install --package-lock-only --ignore-scripts
--before=2026-11-05T12:00:00Z`: 68 packages, every one with an integrity hash, none younger than 7 days (checked one by one
against the npm registry's publish time). The only package with an install script is `fsevents` (macOS only, not installed here);
`.npmrc` keeps `ignore-scripts=true`.

`npm ci --ignore-scripts` (68 packages), `npm run typecheck` and `npm run build` in `app/ui`: exit 0 each. The screens' code is
unchanged; they already call the 21 commands through `engine.tauri.ts`.

## Item 2 — the core: 21 commands, one generic path

**Must do (written before the code).** `EngineCommand` holds exactly the 21 names plus `Version` (the core's own). One Tauri
command per name (so the capability can list each one), every one a two-line function into one generic path: take the arguments
object exactly as the window sent it (`Request::body()`, no typed parameters, so nothing is renamed or dropped), start the engine
with the fixed argv `window <name>`, write the object as one JSON document to stdin and close it, read stdout, and answer with the
engine's JSON text untouched (`Response::new(text)`, only checked to be one JSON document). On a non-zero exit the engine's error
object goes back untouched as the rejection; if the engine breaks the contract (no JSON, no `kind`/`message`), the core's own
`{"kind":"failed","message":...,"details":[],"next":null}` does. The core never reads a field of a result.

**Limits.** Arguments at most 1 MiB (refused before the engine starts); a one-document answer at most 8 MiB (past it the engine is
stopped and the window gets an error); a `run_start` line at most 64 KiB, and a line that is not one JSON document or is too long
is not relayed (counted as `dropped=` in the log). Timeouts: `run_start` 12 h; `run_stop`, `run_status`, `about` 30 s;
`sheet_export`, `purge_apply`, `purge_everything`, `person_forget` 600 s; everything else 120 s. On a timeout the engine is stopped.

**One engine at a time.** A gate: a command waits for the one before it. While a `run_start` runs, `run_stop` and `run_status` get
their own engine process beside it (one at a time); every other command is refused at once with an error object ("A run is going
on ..."), not queued for hours.

**`run_start`.** Line 1 of the engine's stdout is the run handle `{"runId": ...}`: the command's answer. Every later line is relayed
as it arrives through the Tauri channel the screens pass as `events` (the core removes `events` from the arguments before they go
to stdin). After `run_stop` answers, the run's engine gets 10 s to end by itself; then the core ends it. Closing the window
(`CloseRequested`/`Destroyed`) and the app's exit stop every engine the core started (log: `exit: every engine stopped`).

**`key_save`'s value.** The arguments live in `EngineInput`, whose `Debug` prints only the byte count; the log line per command holds
the name, sizes, time and the error `kind` (only from a fixed list, else `other`): never arguments, never answers, never the engine's
free text; stderr is never logged; the self-test logs a step's description, never its script.
`tests/key_value_never_leaks.rs` plants `LFKEY-MARKER-0b5e7d1c9a` and searches the stream lines, the engine output's `Debug`, the
answer, the error objects, the log line, the input's `Debug` and a panic message raised while the input is held, for three cases
(saved; refused by the engine; engine missing), plus the stand-in's state file. Seen red: with `EngineInput`'s `Debug` printing its
bytes, `test the_key_value_appears_in_no_output ... FAILED` / `saved: the marker leaked:`; restored: `2 passed`. In the real window
the self-test typed `LF-SELFTEST-KEY-7f3a9c51` into the Keys screen and saved it (`cmd=key_save ... in=66B ... ok out=82B`); the
search of that run's core log: `key marker in this run's log: False`.

## Item 3 — the permission test

The capability `main` grants exactly the 21 `allow-<name>` permissions (generated by `tauri-build` from `build.rs`'s list). The test
(`permission-check`, its own crate) now also fails when one of the 21 is missing (a screen would meet a refusal), compares
`build.rs`'s list and `generate_handler!`'s list with the 21 names, and accepts `default-src 'none'` as well as `'self'`. Still: no
plugin, no permission off the list, one `Command::new(` (in `engine.rs`), no remote origin, no inline script, no `eval`.
Seen red, planted `"shell:allow-execute"` in `capabilities/main.json`:
```
test the_window_can_start_nothing_and_holds_only_listed_permissions ... FAILED
2 problem(s):
  capabilities/main.json: PROGRAM-START PERMISSION `shell:allow-execute`: the window may not start a program
  capabilities/main.json: permission `shell:allow-execute` is not on the allow-list ["allow-campaign-create", ... "allow-about"]
test result: FAILED. 2 passed; 1 failed
```
Removed: `test result: ok. 3 passed; 0 failed`.

## Item 4 — the stand-in engine

`app/src-tauri/test-resources/standin/leadforge_window_standin.py`, named a stand-in in its file name and first line. It answers all
21 names with the made-up data of `app/ui/src/engine.mock.ts` (`.example` domains, Ofcom drama numbers), the same validation errors
(an incomplete campaign: `kind: input` and four `details`), and a timed `run_start` stream (a progress line every 0.25 s through the
six stages) that `run_stop` ends from its own process (a stop file in the workspace). State between calls: `standin-state.json` in
the app's workspace folder. It keeps no key value.
**How `leadforge window <name>` resolves to it.** The core starts the same interpreter with the same flags and argv tail; only the
entry differs: `python -X utf8 -I <stand-in script> window <name>` instead of `python -X utf8 -I -m leadforge window <name>`. In
development the script is the one in the worktree; in the bundle it ships as `engine/standin/leadforge_window_standin.py`.
**The one-line switch:** `pub const STAND_IN: bool = true;` -> `false` in `app/src-tauri/src/engine.rs`. Then
`tests/standin_switch.rs` fails until the stand-in's line is removed from `tauri.bundle.conf.json`, so it cannot ship by mistake;
`tests/engine_dev.rs` then runs the same 21 calls against the real commands.

## Item 5 — proof in the real window (WebView2)

Driving WebView2 from outside would need `tauri-driver` and Edge's WebDriver: two new installs. Not needed: the core got a
`--selftest` mode (`src/selftest.rs`, only on that command-line flag). The window is created with a probe script injected before
the page's own scripts (records `securitypolicyviolation` events, errors, unhandled rejections, `console.error`); the core walks a
fixed list of steps by evaluating short scripts in the page (click a rail item, type into a field, press a button), reads the
`<main>` text back after each step, and logs a `shot` line; `packaging/selftest-window.ps1` takes a `PrintWindow` picture of the
real window at each `shot` line. Debug build, stand-in engine, 2026-11-12, about 40 s on the owner's screen.

| Screen (file under `D:\LeadForge\wt\window-shots\`) | The core's log line(s) for it |
|---|---|
| `01-campaign.png` | `cmd=settings_get origin=dev-venv in=2B ms=115 ok out=139B` |
| `02-campaign-error.png` (error object on screen: "The campaign is not complete.", two fields marked) | `cmd=campaign_create origin=dev-venv in=80B ms=289 error kind=input` |
| `03-campaign-plan.png` (plan: 108 businesses, 23 min) | `cmd=campaign_create origin=dev-venv in=101B ms=221 ok out=164B` |
| `04-run-streaming.png` (Read their websites, 36 of 212) | `cmd=run_start handle relayed; events follow` |
| `05-run-stopped.png` ("Stopped here. What was found is kept.") | `cmd=run_stop origin=dev-venv in=27B ms=413 ok out=283B`; `cmd=run_start origin=dev-venv in=58B ms=5011 ok out=22B lines=22 dropped=0` |
| `06-results.png` | `cmd=campaigns_list origin=dev-venv in=2B ms=444 ok out=2258B` |
| `07-people.png` (12 contacts) | `cmd=people_list origin=dev-venv in=34B ms=330 ok out=3936B` |
| `08-data.png` | `cmd=purge_report ... ok out=132B`; `cmd=retention_get ... ok out=35B` |
| `09-keys.png` | `cmd=keys_list ... ok out=150B`; `cmd=key_save origin=dev-venv in=66B ms=220 ok out=82B` |
| `10-settings.png` | `cmd=settings_get ... ok out=139B`; `cmd=about ... ok out=473B` |

End of the run: `selftest: probe "{\"violations\":[],\"errors\":[]}"`, `exit: every engine stopped`, app exit code 0.
**CSP finding: none.** The screens load and run under both policies (Tauri's header and the `<meta>` Vite writes) with no
violation and no console error. The probe can see one: with a planted step that adds a `data:` image, the same run logged
`selftest: probe "{\"violations\":[\"img-src data\",\"img-src data\"],\"errors\":[]}"` (once per policy); the plant was removed.
Not walked: the dialogs (forget, suppress, purge, delete everything, about), theme changes, `sheet_open`, a failed run's screen.

## Item 6 — one copy at a time

`src/instance.rs`, no plugin and no unsafe code: the first copy holds `%LOCALAPPDATA%\app.leadforge.window\instance.lock` open
with no sharing; a second copy cannot open it, writes `focus.request` beside it and exits before it makes a window or starts an
engine; the first copy checks for that file every 0.4 s and brings its window to the front. It fails open (a folder that cannot be
made lets the app start). `packaging/instance-check.ps1` (debug build, a window for about 5 s):
```
second copy ended by itself: True after 0.12 s, exit code 0
copies running now: 1
1794470280 leadforge-core: instance: a second copy asked for the window; brought it to the front
1794470281 leadforge-core: exit: every engine stopped
copies left after closing: 0
```
Not watched failing (carried over).

## Item 7 — the installer

Under the `heavy` lock, measured by `packaging/run-measured.ps1` (after `npm ci --ignore-scripts` of the Tauri CLI, 2 packages):
`node_modules\@tauri-apps\cli\tauri.js build --config tauri.bundle.conf.json --bundles nsis -- --locked`
First build (0.7.3): `exit 0; duration 169 s; peak working set of the build's process tree 816 MB` (with the screens' Vite build
run by `beforeBuildCommand`: `dist/assets/index-Dtgfbd67.js 291.63 kB`). After the merge of `master` 0.8.0 and the engine rebuilt
by `packaging/build-engine-embed.ps1` (`leadforge 0.8.0`), and a fix to the log (two threads could interleave inside one line:
`... dropped=01794471459 leadforge-core: cmd=run_stop ...`; now one write per line), the last build:
```
exit 0; duration 151 s; peak working set of the build's process tree 814 MB; free RAM before 1930 MB
        D:\LeadForge\wt\target\release\bundle\nsis\LeadForge_0.8.0_x64-setup.exe (34.78 MiB)
```
sha256 `0d9863773390ecfe3d282dac540fe49b3a99982917b6361cf4960777d010807b`. (The release dependencies were already built in the
shared target folder by L10; the cold build there took 404 s and 2,399 MB.) The release app from `target\release` (resources
beside it) passed the same self-test on the bundled engine 0.8.0 and the bundled stand-in: every command `origin=bundled`, the
log lines whole, 10 of 10 pictures in `window-shots\release\`, `selftest: probe "{\"violations\":[],\"errors\":[]}"`,
`key marker in this run's log: False`, `SELFTEST PASS`. (Its Keys step saved nothing: the workspace kept an earlier run's state,
both keys already saved; the debug run above saved one.)

**The install: for the coordinator to run** (this session is elevated; the script refuses an elevated shell, seen:
`REFUSED: this PowerShell is elevated; open an ordinary one`). From an ordinary PowerShell:
`powershell -NoProfile -ExecutionPolicy Bypass -File D:\LeadForge\wt\window\app\src-tauri\packaging\install-proof.ps1 -Setup D:\LeadForge\wt\target\release\bundle\nsis\LeadForge_0.8.0_x64-setup.exe`
It installs to `D:\Temp\lf-install\LeadForge` with `/S /NS`, runs the installed app's self-test (a window for about 40 s; its
smoke step of L10 is replaced, since `engine_version` is gone), uninstalls, and prints `PASS` only if the self-test passed and no
process or file is left in `D:\Temp\lf-install`.

## What the engine side must know (not in the contract text)

1. **stdin is the screens' arguments object as `invoke` sent it**, keys in the screens' spelling (camelCase):
   `campaign_create {"draft": CampaignDraft}`, `run_start {"args": {"campaign","resume"}}`, `run_stop {"runId"}`,
   `run_status {"runId": string|null}`, `sheet_export {"runId"}`, `sheet_open {"path"}`, `people_list {"query": {"search","limit"}}`,
   `person_forget {"value"}`, `address_suppress {"value","kind": string|null}`, `purge_everything {"confirm": true}`,
   `retention_set {"months"}`, `key_save {"name","value"}`, `key_remove {"name"}`, `settings_set {"patch"}`; the rest `{}`.
2. **`run_start`'s first stdout line is the run handle `{"runId": "..."}`**, then one RunEvent per line, and the last line must be a
   `finished`, `stopped` or `failed` event: the core does not read lines, so if the engine dies without one the screen keeps
   showing a running run. A refusal before the run starts: no handle line, the error object, non-zero exit.
3. **`run_stop` runs as a second engine process beside the run** and must make the run's process end within 10 s (the core ends it
   after that). `run_status` also runs beside a run. Nothing else does.
4. **Error `kind` values the screens know:** `failed`, `usage`, `environment`, `input`, `source`, `keyring`, `missing`; any other
   becomes `failed` on screen. `details` are shown as plain sentences; for `campaign_create` the screens mark a field when a detail
   starts with `target.categories`, `target.geography.areas`, `target.geography.country` or `caps.max_leads` followed by `: `.
5. **`sheet_open` returns `null`** on success (one JSON document). Opening a file means the engine starts the program Windows uses
   for it; the window and the core start nothing.
6. **The working folder is `%LOCALAPPDATA%\app.leadforge.window\workspace`**, the environment is cleared down to a short list
   (`SYSTEMROOT`, `TEMP`, `APPDATA`, `LOCALAPPDATA`, `USERPROFILE`, ...), the interpreter runs isolated (`-X utf8 -I`), and stdin is
   closed after the one document. `settings_get`'s `workspace` is shown as text only.
7. **Limits:** 1 MiB in, 8 MiB out, 64 KiB per stream line, the timeouts of item 2; `key_save`'s value must not appear on stdout,
   stderr or in any file but the keyring.

## Carried over (noticed, not done)
- The real `leadforge window` commands (other laptop); then the switch of item 4.
- The keyring (`keys_list`, `key_save`, `key_remove`): the stand-in only pretends.
- The workspace folder dialog (`Settings`): the core has no dialog; the screens show the folder as text.
- If the run's engine dies without an end event, the screen stays on "running" (engine side, item 2 of the list above).
- The self-test walks the seven screens, one error, one run and its stop; not the dialogs, `sheet_open`, a failed run.
- The single-instance guard and the self-test's run stop were not each watched failing.
- No CI job (same reason as L10); the permission-check crate would be the cheap one to add.

## Results of the local runs

All on the final tree, under the `heavy` lock, one at a time:
- `app/src-tauri`: `cargo fmt --check` exit 0; `cargo clippy --all-targets --locked -- -D warnings` exit 0; `cargo test --locked`
  exit 0 (unit 9, `engine_dev` 4: real engine version, the stand-in's 21 commands and its error path, a run streamed and stopped
  by `run_stop` beside it, a run ended by the core's kill; `key_value_never_leaks` 2; `standin_switch` 1; `version_agrees` 1).
- `app/src-tauri/permission-check`: `cargo test --locked` 3 passed; clippy exit 0.
- `app/ui`: `npm run typecheck` exit 0, `npm run build` exit 0, `npm test`: `pass 60, fail 0`.
- Dev venv for this worktree made the CI install job's way (hashed lock, then `--no-deps --no-build-isolation -e .`).
- Windows on the owner's screen (2026-11-12, about 09:56 to 10:07): the debug self-test about 40 s, the instance check about 5 s,
  the planted-CSP self-test about 40 s, the release self-test twice about 40 s each. Every process stopped after each.
