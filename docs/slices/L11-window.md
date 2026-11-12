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
`sheet_export`, `purge_report`, `purge_apply`, `purge_everything`, `person_forget` 600 s; everything else 120 s (pinned per
command since "The start, the stop and the end of a run" below). On a timeout the engine is stopped.

**One engine at a time.** A gate: a command waits for the one before it. While a `run_start` runs, `run_stop` and `run_status` get
their own engine process beside it (one at a time); every other command is refused at once with an error object ("A run is going
on ..."), not queued for hours.

**`run_start`.** Line 1 of the engine's stdout is the run handle `{"runId": ...}`: the command's answer. Every later line is relayed
as it arrives through the Tauri channel the screens pass as `events` (the core removes `events` from the arguments before they go
to stdin). After `run_stop` answers ok, the run's engine gets 90 s to end by itself (was 10 s; see "The start, the stop and the
end of a run" below); then the core ends it. Closing the window
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
`master` moved once more (L8, Maps and social out, fd2886e; changelog conflict only) and was merged; the engine was rebuilt again
from the merged source, and the gates rerun (all exit 0). The last build, the installer to install:
```
exit 0; duration 202 s; peak working set of the build's process tree 805 MB; free RAM before 1307 MB
        D:\LeadForge\wt\target\release\bundle\nsis\LeadForge_0.8.0_x64-setup.exe (34.77 MiB)
```
sha256 `63b23e3b96b85ffb9e5be8fb13e8752d5d48cd0967c321c6e2fd12fee3ab491b`. Its release app, on a fresh workspace:
`cmd=campaign_create origin=bundled ... error kind=input`, `cmd=run_stop origin=bundled ... ok`,
`cmd=run_start origin=bundled in=58B ms=4699 ok out=22B lines=22 dropped=0`, `cmd=key_save origin=bundled in=66B ms=89 ok out=82B`,
probe clean, `key marker in this run's log: False`, `SELFTEST PASS`. (The release dependencies were already built in the
shared target folder by L10; the cold build there took 404 s and 2,399 MB.) The release app from `target\release` (resources
beside it) passed the same self-test on the bundled engine 0.8.0 and the bundled stand-in: every command `origin=bundled`, the
log lines whole, 10 of 10 pictures in `window-shots\release\`, `selftest: probe "{\"violations\":[],\"errors\":[]}"`,
`key marker in this run's log: False`, `SELFTEST PASS`.

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
   `finished`, `stopped` or `failed` event. A refusal before the run starts: no handle line, the error object as line 1, non-zero
   exit. The rules the core holds the engine to (line 1, `stream-closed`, the wait after a stop, the time limits) are the
   contract in `docs/window-actions.md`, "The seam's contract".
3. **`run_stop` runs as a second engine process beside the run**; after it answers ok, the run's process has 90 s to write its end
   event (the core ends it after that). `run_status` also runs beside a run, and must answer `failed` for a run whose process was
   ended from outside. Nothing else runs beside a run.
4. **Error `kind` values the screens know:** `failed`, `usage`, `environment`, `input`, `source`, `keyring`, `missing`; any other
   becomes `failed` on screen. `details` are shown as plain sentences; for `campaign_create` the screens mark a field when a detail
   starts with `target.categories`, `target.geography.areas`, `target.geography.country`, `caps.max_leads`, `offer`, `sicCodes` or
   `source` followed by `: ` (the last three are the seam decisions of 2026-11-12, below).
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
- (Settled 2026-11-12: a run whose engine dies without an end event now ends on screen; see "The start, the stop and the end of a run".)
- The self-test walks the seven screens, one error, one run and its stop, and one refused start; not the dialogs, `sheet_open`,
  a failed run.
- The single-instance guard was not watched failing. (The self-test's run and its stop now are: see "The self-test".)
- (Settled 2026-11-12: CI job `window · windows-latest`; see "CI" at the end.)

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

## The install, run with the owner's normal token (2026-11-12, 10:45 to 10:46)

Run by the orchestrator through `packaging\install-proof.ps1` on `LeadForge_0.8.0_x64-setup.exe` (sha256 beginning `63b23e3b`), started with the normal (not elevated) token. Result: PASS.

- Silent per-user install into `D:\Temp\lf-install\LeadForge`: exit 0, no administrator prompt.
- The INSTALLED app's self-test walked the screens on the bundled engine entry (the stand-in): `shots taken: 10 of 10; probe clean: True`, `SELFTEST PASS`; every command line in the core's log reads `origin=bundled ... ok`; the content-security probe reported no violation and no error; `exit: every engine stopped`.
- Uninstall: 0 processes, 0 files or folders left, no uninstall key. Checked separately: no `leadforge-window` process, no Start menu entry, no Defender detection that day.

Not shown by this run: an interactive (double-click) install, the default per-user install folder, and the real `window` commands (the stand-in answered).

## Seam decisions of 2026-11-12

The real engine commands (pull request 14) proposed ten changes; these are final and the engine side is built to them. Types
(`app/ui/src/engine.ts`), mock, stand-in, screens and `docs/window-actions.md` say the same. Shape rule: a field that left a type is
ABSENT from the JSON; a nullable field is PRESENT with `null` (`app/ui/tests/seam-shape.test.mjs` holds the mock and the stand-in to it).

1. `run_start`: stdout line 1 is the `RunHandle` `{"runId"}`, then `RunEvent`s, the last `finished`, `stopped` or `failed` (written as the contract in `docs/window-actions.md`).
2. `CampaignDraft.offer: string`, required; the form has one field for it ("What you offer"); an empty one is refused, kind `input`, detail `offer: ...`, and the form marks that field.
3. `CampaignDraft.sicCodes: string[]` (shown and required only for `companies_house`; refused with `sicCodes: ...`). `Settings.sources: SourceId[]`: the form offers only those, one is fixed text, none is a plain state; a register not listed is refused (`source: ...`, `next` names the configured one) and shown on the field.
4. No new error kind: a key command the engine cannot do yet answers `missing`; the Keys screen reads it in words about keys (title "Keys cannot be managed from this window yet.", no "Try again").
5. Nullable: `RunStatus.campaign`, `RunStatus.done`, `RunCounts.purged`, `RunCounts.expiringIn30Days`.
6. Nullable: `Campaign.name`, `Campaign.source`, `Campaign.keptUntil`.
7. Nullable: `Person.source`, `Person.foundAt`, `Person.campaign`; a null reads "not recorded".
8. `theme` and `accent` left `Settings` and `SettingsPatch`; the window keeps them in `app/ui/src/prefs.ts` (browser storage, every read and write in try/catch, defaults `system` and `cobalt`, the page renders when storage throws). The Rust core merges nothing.
9. `windowVersion` left `About`; the About screen shows `WINDOW_VERSION`, a build-time constant from the `[package]` version of `app/src-tauri/Cargo.toml` (`app/ui/window-version.mjs`, written by `vite.config.ts` `define`); no Tauri permission, no plugin. `tests/window-version.test.mjs` fails when the two differ.
10. `people_list` returns the engine's named people, an email or phone only where recorded as that person's; the People screen says "named people", and that forget and suppress act on any address or domain, listed or not.

### What each null shows

| Field | When null the screen shows |
|---|---|
| `RunStatus.campaign` | the Run screen's title is the run id (`runTitle`) |
| `RunStatus.done` | the stage that stopped or failed shows no progress line at all (changed 2026-11-12, was "progress not known" and an indeterminate bar); while running, the "Done in this stage" figure reads "not known" |
| `RunCounts.purged`, `RunCounts.expiringIn30Days` | the clean-up line ("Clean-up: 4 records deleted at the start, 9 expire in the next 30 days.") leaves out the null part; no line at all when both are null; a zero is a count and is shown |
| `Campaign.name` | the Results detail shows the run id where the name goes |
| `Campaign.source` | the list row says "register not recorded"; the detail's "Register" row says "not recorded" |
| `Campaign.keptUntil` | the "Kept until" row is left out: no claim about a deletion day |
| `Person.source` | "Source not recorded" (no page address) |
| `Person.foundAt` | "Date not recorded" |
| `Person.campaign` | "Campaign not recorded" (after the date, on the same line) |

### Where a decision could not be taken as written

- **Item 3, "none": the engine's `next` text.** `settings_get` carries `sources: []` and nothing else, so the screen has no `next` from the
  engine to show for a workspace with no register. It shows a fixed sentence (`NO_SOURCE_NEXT` in `NewCampaign.tsx`). Proposal:
  `Settings` gains one nullable `sourcesNext: string | null` (present, null while `sources` is not empty), which the form shows in
  the none state. It is a new field, so the engine side must agree before the window adds it; until then the sentence is the window's own.
- **The core's own tests sent the old shapes (settled later the same day).** `engine_dev.rs` and `selftest.rs` now send the new shapes
  (`offer`, `sicCodes` for Companies House, no `theme`; five `details` for an empty draft). The stand-in is as strict as the real engine
  will be: it refuses a missing `offer` key as well as a blank one, and refuses `settings_set` carrying any key but `sheetFormats` and
  `openSheetWhenDone` (kind `usage`). See "The self-test" below for the run that said PASS without having started a run.
- **The form fits 900 x 600 only in a denser layout.** With the offer and the SIC codes the old form (hints under each field, the register as two
  cards) was 687 px tall at 900 x 600 for two registers and 810 px with SIC codes. Without shrinking type: the hints sit on the label's
  line, the register is one row (label left, `SegmentedControl` right; one register is plain text), the form column is wider
  below 1000 px, and the page's bottom padding is 16 px below 700 px of height. Measured by `scrollHeight` against `clientHeight` of
  `<main>` for every form state (two registers, one, none, Companies House with SIC codes, the three refusals) in light and dark at
  1280 x 800 and 900 x 600: 32 of 32 fit. The cards with a line of detail per register are gone.

### Proof of 2026-11-12 (this slice's seam change)

- `app/ui`: `tsc --noEmit` exit 0; `vite build` exit 0 (`dist/assets/index-CrYUJrvt.js`); `npm test` (the six files): `tests 89, pass 89, fail 0`.
  New assertions each seen red once by breaking the code they cover: the offer and SIC refusals (check switched off), `readLook` without
  its try/catch (5 tests red, SecurityError escapes), `windowVersion` returning a different number and a `windowVersion`, `theme` in the
  mock's and the stand-in's `about` (6 tests red).
- 72 renders (18 states, light and dark, 1280 x 800 and 900 x 600) in `D:\LeadForge\wt\window-shots\seam\`, made by a headless Edge
  driven over CDP (exact viewport, one browser at a time, closed after each batch): after looking, the register cards became one row and the
  hints moved onto the label line (the form did not fit), a wrapping label was made `nowrap`, the Keys page's first line no longer
  promises a keyring when the engine says `missing`, and the People render is scrolled to the rows whose fields are null.
- Debug build `cargo build --locked` exit 0 (32 s, peak 480 MB) and the real-window self-test against the stand-in (`window-shots\seam\selftest\`):
  `shots taken: 10 of 10; probe clean: True`, `SELFTEST PASS`. **That PASS was false: no run had started.** The log shows
  `cmd=campaign_create ... error kind=input` for the empty form and again after "fill kind and place" (the offer refusal), and no
  `cmd=run_start`. The self-test judged the pictures and the probe, never the run. Corrected below.

### The self-test (corrected 2026-11-12)

`packaging/selftest-window.ps1` gives the verdict from the core's own log of THIS run; `src/selftest.rs` drives the steps (it now types
kind, place and "What you offer", which is a textarea, so the probe's `type` helper handles textareas). It fails (exit 1, one
`SELFTEST EXPECTATION MISSED: ...` line per miss, then `expectations missed: N`) unless the log shows, in this order:
1. `campaign_create ... error kind=input` (the incomplete form, on purpose) and the 02 screen text showing the field problem ("at least one ...");
2. `campaign_create ... ok`; `cmd=run_start handle relayed`; `run_stop ... ok`; `run_start ... ok ... lines=2` or more (the handle line plus a stream line);
3. after the stop, `ok` for `campaigns_list`, `people_list`, `purge_report`, `retention_get`, `keys_list`, `key_save`, `settings_get`, `about`;
and the earlier checks still hold (10 of 10 pictures, probe clean, key marker not in the log, app exit 0).

Watched fail: the assertions were added first and the old walk (no offer typed) was run against the strict stand-in. Real output
(the run also hung at "start the run", so the app was stopped after the 3-minute bound: `shots taken: 3 of 10`):
`SELFTEST EXPECTATION MISSED: run_start relayed its handle (log pattern: cmd=run_start handle relayed)` ... `expectations missed: 12`, `SELFTEST FAIL`.
A second run with the offer typed was red for a new reason, `key_save answered ok` missing: the stand-in's state file keeps keys
saved by earlier walks, so the Keys screen showed "Replace" and no field. The walk now clicks "Replace" first if it is there.
The same run showed that the picture of step 09 was of the debug build's console window (`MainWindowHandle` may name either); the
script now finds the visible window of the process that is not a console.
Green (third run): `shots taken: 10 of 10; probe clean: True`, `expectations missed: 0`, `SELFTEST PASS`; log: `campaign_create ... ok out=164B`,
`run_start handle relayed`, `run_stop ... ok`, `run_start ... ok out=22B lines=22 dropped=0`, then the eight data commands `ok`.
Not covered: the real engine's wording of the field problem on screen (step 1 looks for "at least one"; the stand-in's text).

## The start, the stop and the end of a run (2026-11-12, after the engine side tested its commands against the core)

The engine side found two cases the core got wrong: a refused start was relayed as a handle with no `runId` (the screen waited on
"running" for ever), and a stream that ended without an end event told the screen nothing. The rules are now the contract in
`docs/window-actions.md`, "The seam's contract" (items 1 to 4 there; the engine side builds to the same text):
1. line 1 is the handle only if it is an object with a non-empty string `runId`; an object with `kind` is the refusal (rejected
   untouched once the process has ended, 5 s bound); anything else is the core's own `failed` error;
2. a stream that ends without `finished`, `stopped` or `failed` gets exactly one `{"type":"stream-closed","exitCode","reason"}` from
   the core (`exit`, `ended-by-core`, `line-too-long`, `timeout`); the Run screen then asks `runStatus` once and shows its answer, or
   "The engine stopped without saying why." with "Continue the run";
3. after `run_stop` answers ok, the run has 90 s (`engine::STOP_WAIT`) to write its end event; `run_stop` answers at once (it used
   to wait up to 10 s for the run before answering); tests pass a short wait to `engine::after_stop` (a parameter, nothing a
   release build reads); the core's deadline lives in the process handle, so the run loop itself ends the process;
4. `purge_report` is in the 600 s class; `timeouts_are_pinned_per_command` lists all 21.

**How.** `engine::run_stream` is the whole `run_start` path (the Tauri command only wires its answer to the invoke and its lines to
the channel); `engine::after_stop` is the stop path. `tests/run_seam.rs` drives both against the stand-in's cases (`CASES` in the
stand-in: `standin-refuse`, `standin-garbled`, `standin-dies`, `standin-slow-stop`, `standin-ignores-stop`, `standin-long-line`);
a unit test runs `standin-ignores-stop` with a 3 s time limit for the `timeout` reason.
**Seen red** (the old rules put back in one build: any line 1 is the handle, no `stream-closed`, a 10 s wait, `purge_report` at 120 s):
`a_refused_start_rejects_with_the_engines_document` (`a refused start is a rejection, not a handle: "{\"kind\": \"input\", ...`),
`a_run_that_dies_closes_the_stream` (last message a `progress`, not `stream-closed`), `an_end_event_over_the_line_cap_closes_the_stream`,
`a_run_that_ignores_the_stop_is_ended_when_the_wait_ends`, `a_slow_stop_is_waited_for` (`the run ended itself` left `progress`
right `stopped`: ended at 10 s), `the_stop_wait_is_ninety_seconds` (left 10s right 90s), `timeouts_are_pinned_per_command`
(`purge_report: time-limit class` left 120s right 600s), `a_run_past_its_time_limit_closes_the_stream_with_timeout`. Restored: all green.
The screen side (`app/ui/src/run.ts`, the run's state out of `App.tsx` so Node tests it; `tests/run-view.test.mjs`) was red with the
old reducer put back (`actual: 'stopped', expected: 'stopping'`; `the screen now asks runStatus once` actual null) and green after.

**The Run screen.** New state "Stopping the run" (from `run_stop`'s answer to the end event or `stream-closed`): "The engine is
finishing the business it is on, then it stops. This can take up to a minute and a half. Nothing found so far is lost."; no Stop
button; the stage keeps its live progress. A stopped or failed run whose `done` is null shows no progress line. Renders (light and
dark, 1280 x 800 and 900 x 600, `D:\LeadForge\wt\window-shots\seam\`): `run-stopping-*`, `run-closed-silent-*`, `run-stopped-null-*`,
`run-failed-null-*`, all fit (`scrollHeight` = `clientHeight`). After looking: the stopping state showed "Time left 3 min" beside
"Stopping the run" (the stage will not run to its end), so it shows only "Done in this stage" now.

**The self-test.** The walk adds a refused start (the place "Standin refuse", picture `05b-run-refused`, 11 pictures now); the
script expects `cmd=run_start rejected: line 1 was not a run handle`, `cmd=run_start ... error kind=input lines=0` and the screen
text (Try again, then the engine's message). Bounds: 20 s with no step of the walk in the log, 120 s for the walk (the script stops
the app, and the app also ends itself at 120 s). Two runs on the owner's screen, about 45 s each: the first missed one expectation
for a wrong check (the page text was cut at 240 characters before the message; and "Try again" comes first in the text): the probe
now keeps 600 characters. The second: `shots taken: 11 of 11; probe clean: True`, `key marker in this run's log: False`,
`expectations missed: 0`, `SELFTEST PASS`.
Not watched: the 20 s and 120 s bounds firing (a walk that hangs on purpose would need a third window).

## `master` 0.9.0 and CI (2026-11-12)

`master` 0f2d3ff (0.9.0, the collect side, and the keys slice) merged without a conflict (7f58146); the crate follows the engine:
`Cargo.toml` `[package] version` 0.9.0, `Cargo.lock` by `cargo update -p leadforge-window --offline` (6e2bc3b).

**CI.** Job `window · windows-latest` in `.github/workflows/ci.yml`: Python 3.12 and a `.venv` made the fake-campaign job's way
(the core's tests start the stand-in and the real engine from it), Node 22 (`npm` cache through `actions/setup-node`, the action the
workflow already used), `npm ci --ignore-scripts`, `tsc --noEmit`, the Vite build (before the tests: `window-version.test.mjs` checks
the built bundle and skips without one), `npm test`, then the Rust toolchain from `app/src-tauri/rust-toolchain.toml` (rustc 1.99.1,
rustfmt and clippy, installed by the runner's own `rustup`; no third-party toolchain action, no cargo cache: no action for it is in
use), `cargo fmt --check`, `cargo clippy --all-targets --locked -- -D warnings`, `cargo test --locked` for the crate and for
`permission-check`. On the laptop the installed `stable` is the same rustc 1.99.1 (builds set `RUSTUP_TOOLCHAIN=stable`, so rustup
does not download a second copy).
**CI does not run** the installer build, the install proof (`packaging/install-proof.ps1`) or the real-window self-test
(`packaging/selftest-window.ps1`): they need a desktop session and show a window. The builder runs the self-test on the laptop; the
coordinator runs the install proof with the owner's normal token.
**Proof, from the job's own log** (run 43201821868 at 61eaf47): `rustc 1.99.1 (58cf8f9c3 2026-10-13)`; `npm test` `# tests 99`,
`# pass 99`, `# fail 0`, `# skipped 0`; `cargo test` unit `14 passed`, `engine_dev` `4 passed`, `key_value_never_leaks` `2 passed`,
`run_seam` `6 passed`, `standin_switch` `1 passed`, `version_agrees` `1 passed`; `permission-check` `3 passed`.
**Red when a test is broken**, on the throwaway branch `ci-probe/window-red` (run by `workflow_dispatch`, deleted on the remote
and locally afterwards; its runs were cancelled once the window job had failed): a Rust assertion broken (run 43201858537):
`test engine::tests::the_stop_wait_is_ninety_seconds ... FAILED`, `left: 90s right: 91s`, `test result: FAILED. 13 passed; 1 failed`,
`Process completed with exit code 101`; a screen assertion broken too (run 43201886158): `not ok 57 - after run_stop answers the run
is stopping until its end event, and stays live`, `expected: 'stopped' actual: 'stopping'`, `# fail 1`, `Process completed with exit
code 1` (the job stops at its first red step, so each break got its own run).
**Required checks.** The repository lists required checks nowhere else, so here: a pull request that touches `app/` needs
`window · windows-latest` green, as well as the existing jobs.

## The switch: the window on the REAL engine (2026-11-12, `master` 8ea0ec0, engine 0.9.0)

**Merge.** `origin/master` 8ea0ec0 merged with no conflict (git merged `CHANGELOG.md` by itself: the engine's L11a lines and the
window's lines both stay under "Unreleased"; released sections untouched).

**The switch (item 4).** `STAND_IN = false`. `EngineProgram::bundled` has no stand-in entry at all (always `-X utf8 -I -m leadforge`);
`EngineProgram::dev_venv` likewise. The stand-in is reached only through `EngineProgram::standin()`, `#[cfg(debug_assertions)]`, used by
`run_seam.rs`, the unit timeout test, `engine_dev.rs` (its stream and kill tests) and `key_value_never_leaks.rs`. Its line left
`tauri.bundle.conf.json`. Seen red first: `test the_stand_in_ships_only_while_the_core_uses_it ... FAILED` / `STAND_IN is off: remove the
stand-in's line from tauri.bundle.conf.json`; green after the line left. **How a release build is shown to start only the bundled
engine:** (1) `interpreter_runs_isolated` pins `bundled(..).prefix` and `dev_venv().prefix` to exactly `-X utf8 -I -m leadforge`;
(2) `locate` in a release build has one branch, `bundled(resource_dir)`; `standin()` and `dev_venv()` are compiled out
(`cfg(debug_assertions)`); (3) the release binary was searched for the stand-in's names (below); (4) the core reads no environment
variable, argument or file that changes the program or argv (`--selftest`/`--selftest-campaign` only choose a walk; the engine stays
the bundled one); the environment the engine gets is the fixed `ENV_KEEP` list; (5) the bundled interpreter's `python312._pth` has no
`import site`, so not even a `.pth` file can add code to it.

**Comparing the shapes for real (item 3).** `tests/real_engine_shapes.rs` (ignored by default) runs the REAL engine's commands through
`engine::run`/`engine::answer`/`engine::run_stream`/`engine::after_stop` in a throwaway workspace (`D:\Temp\lf-real-shapes`) whose
`leadforge.yaml` is the fake campaign's, with the fake world on 127.0.0.1 and the fake campaign's guard
(`packaging/fake_world.py`, `packaging/real-shapes.ps1`); the answers go to `app/ui/tests/seam-shape.test.mjs` (`LF_REAL_ANSWERS`),
which holds each to the screens' types the way it holds the mock and the stand-in (a field that left a type absent, a nullable field
present). Order: settings_get, the incomplete form (error), campaign_create, run_start stopped by run_stop beside it after two progress
lines, run_start resumed to `finished`, run_status (by id and latest), campaigns_list, sheet_export, sheet_open (a path outside the
exports: refused), people_list, person_forget, address_suppress, purge_report, purge_apply, retention_get, retention_set, keys_list,
key_save, key_remove, settings_set, about, purge_everything. Result: `test result: ok. 1 passed`, then the shape check `pass 10, fail 0`,
`REAL SHAPES PASS`; the guard refused and logged 25 outside attempts (the fake campaign's known set: system resolver, public resolvers).
**No shape difference** in the 17 commands whose answer type was seen, nor in any stream line of the two runs (field lists per event type), nor in the five error documents. Not seen: `KeyStatus` (the three key
commands answered `environment`, "the keyring package is not installed"), `sheet_open`'s `null` (it opens a program on the screen).
The first run of the harness was red for a wrong check of mine (the second run of the same campaign had nothing left to do and ended
before `run_stop` reached it: "There is no run to stop."); the run is now stopped and then resumed, as `scripts/e2e_window_run.py` does.

**Rulings 15 and 16 and `About.licence` (item 4, window side).** Types, mock (`estimates`, `keyringOff`, `inUseMissing`, `noLicence`),
stand-in (null estimates; `inUse`), `src/follow.ts` (the screens' rules, tested in Node), the plan card, the Keys card and About.
`docs/window-actions.md`, "Rulings 15 and 16", has the words. **Lines to remove when `slice/L11a-follow` is on `master`** (both in
`app/ui/src/follow.ts`, marked TIGHTEN LATER): the 0/0/0 register plan read as not estimated; `inUse` missing read as true (and
`KeyStatus.inUse?` made required in `engine.ts`, with its assertion in `seam-shape.test.mjs`). Renders (light and dark, 1280 x 800,
`D:\LeadForge\wt\window-shots\follow\`, looked at, all fit 800/800): `plan-not-estimated`, `plan-today-zero`, `keys-saved-not-in-use`,
`keys-save-refused` (the refusal under the field, red), `about-licence-null`.

## The fake campaign through the real window, and the self-test on the real engine (2026-11-12)

**How the fakes reach the engine without weakening the switch.** The core starts the engine isolated (`-X utf8 -I`, environment
cleared to `ENV_KEEP`), so the fake campaign's harness cannot come by `PYTHONPATH`. `packaging/selftest-window.ps1` makes ONE
throwaway folder `D:\Temp\lf-selftest` (its full path checked, refused if it is a link; links inside removed as entries) and starts
the app with `USERPROFILE`, `APPDATA` and `LOCALAPPDATA` pointing into it, so the app's workspace, log and WebView2 profile are fresh
(the owner's workspace is not touched). The workspace's own `leadforge.yaml` is the fake campaign's `CONFIG_YAML`; with `-Campaign`
the script starts the fake world and puts a two-file loader into the DEV venv's site-packages that does nothing unless the engine's
working folder holds `.lf-e2e-harness.json` (then it loads the repository's guard, resolver and `fixture_list` provider); the loader
is removed at the end (`loader off: files present []`). No hook in the core. The bundled engine cannot load it (`._pth` without
`import site`), so the campaign walk is a debug-build walk; the installed app's self-test is the short walk.

**The walks.** `--selftest` (short: the incomplete form, a plan, every screen's data command; no run, no key saved) and
`--selftest-campaign` (the campaign to its end: form error, form with the offer and cap 50, plan, start, wait for "Open the results"
(`Until`, a line every 10 s), Results, "Write it again" (`sheet_export`), People, forget the domain `millbrook-autos.example`, suppress
`kestrel-garage.example`, Data, retention 12 -> 1 month, purge if anything is past the limit, Keys, Settings). Bounds: 20 s with no
step in the log; the whole walk 120 s (short) or 420 s (campaign), in the script and in the core. The walk saves no key (the real
engine would write into the account's real keyring). The stand-in's refused-start step is gone from the walk (the real engine refuses
a start only for a campaign that does not exist, which the form cannot make); `run_seam.rs` keeps that case on the stand-in.
**Verdict** from this run's core log, in order: the real engine started (`engine=dev-venv` or `bundled`, never a stand-in);
`campaign_create ... error kind=input` and screen 02 showing the real engine's words "at least one kind of business"; `campaign_create
... ok`; (campaign) `run_start handle relayed`, "the run finishes: yes", `run_start ... ok ... lines=N` (N >= 2), `sheet_export`,
`person_forget`, `address_suppress`, `retention_set`, `purge_report` ok; the data commands ok; `keys_list` ok or `error kind=environment`;
then (campaign) the forgotten domain gone from People and from the export files (and in them before), the suppressed domain listed as
suppressed, and `packaging/compare_campaign.py` PASS; pictures at least 800 px wide (a minimised window's picture does not count);
probe clean; app exit 0; no process left; the folder gone.

**The fake campaign through the real window** (debug build, real engine `engine=dev-venv`, walk 3, 14:16 to 14:18, 79 s of window):
`cmd=campaign_create ... error kind=input` (screen 02: "at least one kind of business", "at least one place", "one or two lines on what
you offer these businesses", the engine's words), `cmd=campaign_create ... ok out=314B`, `cmd=run_start handle relayed`, "the run
finishes: yes after 7 s", `cmd=run_start origin=dev-venv in=57B ms=10649 ok out=22B lines=22 dropped=0`, `cmd=sheet_export ... ok
out=906B`. **Then the same campaign through the command line** (`compare_campaign.py`: the window's own `campaigns/bristol-car-repair/
icp.yaml` in a second fresh workspace with the same fakes and guard, `leadforge --json run --icp`, then `export --icp --format
xlsx,csv`), compared with `scripts/e2e_fake_campaign.py`'s own `read_exports` and normalizing (clock, run id, workspace path), the
window's sheet taken at picture 06 (after "Write it again", before the delete side):
```
EQUAL  tabs (20701 characters normalized)
EQUAL  csv (12996 characters normalized)
EQUAL  report (244 characters normalized)
EQUAL  businesses (window) = leads (digest): window 10, command line 10
EQUAL  stage: window 'export', command line 'export'
CAMPAIGN COMPARE PASS
```
The engine's digest of the command-line run: `"leads": 10, "tier_a": 2, "tier_b": 3, "tier_c": 5, "drafted": 5`. `expected.json` is
NOT equal to either: it is the CLI campaign with `byol import` and a stop and resume (a different campaign), which the window cannot do.
**The delete side, same walk:** forget, report first (the window has no report-first; the engine's own `window person_forget` with
`dry_run` from the command line, just before): `{"kind":"domain","value":"millbrook-autos.example","rows":13,"filesRemoved":2,
"filesEdited":0,"warnings":["Nothing was deleted: ..."]}`; then for real through the window (`cmd=person_forget ... ok out=232B`):
"millbrook-autos.example or Ysolde Fenwick in people_list after the forget: False"; export files (csv, json) holding the domain:
before 1, after 0. Suppress `kestrel-garage.example` (`cmd=address_suppress ... ok out=65B`): its person listed `"suppressed": true`
(1); not tried in a second run. Retention 12 -> 1 month (`cmd=retention_set ... ok out=29B`): the purge report went from
`"months":12,...,"expiringIn30Days":0` to `"months":1,...,"expiringIn30Days":9`. Purge apply: NOT through the window: nothing was past
the limit (`"expired":0`; the button reads "Nothing to delete" and is disabled); `purge_apply` answered through the core's path in
`real-shapes.ps1` (`"state":"armed","deleted":0`). Verdict: `shots taken: 14 of 14; probe clean: True`, `expectations missed: 0`,
`loader off: files present []`, `processes left: 0`, `throwaway folder left: False`, `SELFTEST PASS`.
**Walks on the owner's screen (4 allowed):** walk 1 (14:11, 79 s): SELFTEST FAIL by two wrong checks of mine (the address chosen to
forget is only in the CLI campaign's `byol` list, so it was in no export; the digest names the count `leads`, not `businesses`), and its
pictures were 160 x 28 title bars (the window started minimised from the lock wrapper's hidden parent); walk 2 (14:14, 79 s): one miss,
the run's status read after the forget (9 businesses against 10): the status is now read at picture 06; pictures still title bars;
walk 3 (14:16, 79 s, `-WindowStyle Normal`, pictures 1188 px wide): PASS; walk 4 (14:23, 36 s): the release build's short walk on
the bundled engine 0.9.0 from `target\release`: `started (selftest=Some(Short), engine=bundled)`, `cmd=campaign_create origin=bundled
... error kind=input`, `cmd=campaign_create origin=bundled ... ok out=600B`, the data commands `ok`, `cmd=keys_list origin=bundled ...
error kind=environment`, `shots taken: 8 of 8; probe clean: True`, `expectations missed: 0`, `processes left: 0`, `throwaway folder
left: False`, `SELFTEST PASS`. Not watched: the 20 s and 420 s bounds firing.

**The installer.** `build-engine-embed.ps1` rebuilt the bundled engine from the merged source (`leadforge 0.9.0`), then under the heavy
lock `run-measured.ps1` ran `tauri.js build --config tauri.bundle.conf.json --bundles nsis -- --locked`: `exit 0; duration 217 s; peak
working set of the build's process tree 809 MB; free RAM before 1394 MB`. `D:\LeadForge\wt\target\release\bundle\nsis\
LeadForge_0.9.0_x64-setup.exe`, 36,523,737 bytes, sha256 `424d42a054dfc076fc08d8bc7de143699db0f118b6ca1af3d7476930b3800ced`. Its NSIS
script (`target\release\nsis\x64\installer.nsi`) names no stand-in (`standin`: 0 lines) and one engine (`leadforge-0.9.0.dist-info`
only); the release `leadforge-window.exe` holds none of `leadforge_window_standin`, `test-resources`, `dev-standin`, `dev-venv`
(byte search: 0). A stale `target\release\engine\standin\` from the 0.8.0 build (Tauri does not clean its target copy) was deleted.
**The install proof, for the orchestrator with the normal token** (this session is elevated):
`powershell -NoProfile -ExecutionPolicy Bypass -File D:\LeadForge\wt\window\app\src-tauri\packaging\install-proof.ps1 -Setup D:\LeadForge\wt\target\release\bundle\nsis\LeadForge_0.9.0_x64-setup.exe`
It installs to `D:\Temp\lf-install\LeadForge`, runs the installed app's SHORT self-test (about 40 s of window; its own throwaway
`D:\Temp\lf-selftest`; it needs this worktree's `.venv` to write the throwaway workspace's `leadforge.yaml`), uninstalls, and prints
`PASS` only if the self-test passed and nothing is left. The short walk leaves out the run, the sheet and the delete side: the bundled
Python cannot load the fakes' guard, and without it a run would reach for the real registers.
**Keys on the real keyring (item 7): NOT RUN.** Not "a key is already saved": the engine has no keyring at all. `keys_list` through the
window: `cmd=keys_list ... error kind=environment`, the Keys screen: "Keys cannot be kept in the keyring on this computer. the keyring
package is not installed Install the keyring extra: pip install leadforge[keyring]"; the same from the command line. The backend never
reported itself (no backend is loaded). Settles it: the `keyring` extra in the lock and the bundle (finding 1 below), then the guarded
proof (`keys_list` first; stop if a key is saved).

**Gates on the final tree (under the heavy lock, one at a time).** `app/src-tauri`: `cargo fmt --check` exit 0; `cargo clippy
--all-targets --locked -- -D warnings` exit 0; `cargo test --locked`: unit `14 passed`, `engine_dev` `4 passed`, `key_value_never_leaks`
`2 passed` (now also the real engine refusing an unknown key name, marker absent), `real_engine_shapes` `1 ignored`, `run_seam` `6
passed`, `standin_switch` `1 passed`, `version_agrees` `1 passed`; `permission-check` `3 passed` (capability, permission test, `build.rs`,
lockfiles: unchanged, `git diff --stat` empty). `app/ui`: `tsc --noEmit` exit 0; `vite build` exit 0; `npm test` `tests 105, pass 104,
fail 0, skipped 1` (the real-answer test, which needs `LF_REAL_ANSWERS`). New ruling assertions seen red once (the 0/0/0 rule removed
and `keyBadge` ignoring `inUse`: `ruling 15 ... actual: true, expected: false`, `ruling 16 ... actual: 'Saved', expected: 'Saved, not
in use'`), then restored. `cargo fmt` (the formatter) rewrote `selftest.rs` and `real_engine_shapes.rs` once.

## Findings for the engine's authors (2026-11-12)

1. **The keyring cannot work in any build.** `keys_list`, `key_save`, `key_remove` answer `environment`, "the keyring package is not
   installed": `keyring` is the optional extra of `pyproject.toml` and is in neither `requirements.lock` nor `uv.lock`, so neither the
   bundled engine (`build-engine-embed.ps1` installs `requirements.lock`) nor a venv made the CI way has it. Expected (L11a "After L9 is
   in", item 2): the installer carries the extra. The window shows the engine's answer; the Keys screen cannot save a key. Not patched.
2. Not a finding, noted: a run started by `window run_start` on a fresh workspace ends with `counts.purged` and
   `counts.expiringIn30Days` null (allowed by the type; L11a's table names only runs not started by `run_start` as null).
## The install on the real engine, run with the owner's normal token (2026-11-12, 14:33 to 14:35)

Run by the orchestrator through `packaging\install-proof.ps1` on `LeadForge_0.9.0_x64-setup.exe` (36,523,737 bytes, sha256 beginning `424d42a054df`), started with the normal (not elevated) token. Result: PASS.

- Silent per-user install into `D:\Temp\lf-install\LeadForge`: exit 0, no administrator prompt.
- The INSTALLED app's short walk on the REAL bundled engine: `shots taken: 8 of 8; probe clean: True`, `expectations missed: 0`, `processes left: 0`, `throwaway folder left: False`, `SELFTEST PASS`; every data command in the core's log reads `origin=bundled ... ok`, with one exception below.
- Uninstall: 0 processes, 0 files or folders left, no uninstall key. Checked separately: no `leadforge-window` process, no Start menu entry, no Defender detection that day.

What this run shows is NOT working in the installed app: `cmd=keys_list origin=bundled ... error kind=environment`, and the Keys screen says keys cannot be kept in the keyring on this computer. Cause: the `keyring` package is in neither `requirements.lock` nor `uv.lock`, so the bundle has no keyring. The short walk accepts that answer today; once the locks and the bundle carry `keyring`, its expectation for `keys_list` must be `ok` again, and the keyring proof (save a made-up marker, search for it, remove it) is still owed.

Not shown by this run: a run, the sheet, forget, suppress, retention and purge in the INSTALLED app (the whole campaign walk is on a debug build); an interactive (double-click) install; the default per-user install folder.

## The last batch before the review (2026-11-12, `master` 2fb6b93 merged as acfaaf7)

**1. `master` in, the two tolerances out.** `origin/master` 2fb6b93 (the engine side of rulings 15 and 16 and `About.licence` null) merged
with no conflict. Removed from `app/ui/src/follow.ts`: "a register plan answering 0/0/0 reads as not estimated" (`planFigures` now
reads only null as not estimated; a zero is a count and is shown) and "a missing `inUse` reads as true" (`keyInUse` is `saved && inUse`).
`KeyStatus.inUse` is required in `engine.ts`, the mock (its `estimates` and `inUseMissing` options and the `&estimates=zero`,
`&inuse=missing` render switches are gone) and the stand-in (it already sent it). Tests: `seam-shape.test.mjs` holds `inUse` as
`{optional: false, nullable: false}`; `engine.mock.test.mjs` asserts a 0/0/0 plan reads as counted zeros and a saved key with
`inUse: false` is not in use. **Seen red** (the 0/0/0 rule and `inUse?:` put back): `ruling 15 ... actual: { counted: false ... }
expected: { counted: true, businesses: 0 ... }` and `engine.ts: rulings 15 and 16 ... actual: { optional: true ... } expected: { optional: false ... }`;
restored, green. **The real-shapes test against the real engine** (through the lock, engine 0.9.0 at master's source,
`packaging/real-shapes.ps1`): `test result: ok. 1 passed`, `cargo test exit: 0`, shape check `ℹ tests 10 ... ℹ pass 10 ... ℹ fail 0`,
`guard: outside attempts refused and logged: 25`, `REAL SHAPES PASS`. Not seen in it: `KeyStatus` (the three key commands still answer
`environment`: item 4), `sheet_open`'s null.

**2. Forget shows what it will delete first.** `app/ui/src/forget.ts` (`ForgetFlow`, tested in Node) and the People screen. The seam:
`forgetPerson(value, dryRun)` sends `{value, dry_run}` (`dry_run`, snake_case; the real engine took `true` and `false`). Both ways in (the
"someone asked to be removed" box and a row's Forget control, which also checks again when another target is chosen in its dialog) open
the confirmation with the engine's dry run running ("Checking what the workspace holds"). Then: the engine's own numbers (rows, files that
would be removed, files that would be edited) and its warnings in its words, and the confirm control; only that control makes the real
call (`dry_run: false`), and the real result is then shown in the "Forgotten:" banner. A dry run with 0 rows and 0 files removed or edited
says "Nothing is held for this value ..." and has a Close button only. A dry run that fails shows the engine's error with "Try again" under a
line saying nothing was deleted, and no delete control. A real call that fails keeps the report and the error, and the confirm can be tried
again. Mock and stand-in honour `dry_run` (the stand-in refuses a non-boolean one, kind `usage`) and use the real engine's dry-run warning,
"Nothing was deleted: this is what forgetting it would delete."

Tests: `tests/forget-flow.test.mjs` (11), `seam-shape.test.mjs` +1 (the stand-in's dry run), and the real-shapes run asks the real engine
for the dry run twice and then the real call and holds the three to the same numbers (a planted mismatch is a finding). **Seen red once**,
five plants at once (the mock's dry run deleting; `holdsNothing` always false; `confirm` allowed from "nothing" and "report-failed"; the seam
sending `dryRun` instead of `dry_run`): 8 tests red, e.g. `nothing changed` (a dry run changed the workspace), `a dry run that finds nothing
... actual: 'report', expected: 'nothing'`, `no real call after a failed report ... actual: [[..., true], [..., false]]`, and the `dry_run` key
test; restored: 11 of 11 green. The stand-in's dry run planted to delete: `a dry run changed the workspace`; restored, green.
`npm test` at the end: `tests 117, pass 116, fail 0, skipped 1` (the real-answer test, which needs `LF_REAL_ANSWERS`).

Renders: 24 pictures (checking, report from a row, report from the box, nothing held, dry run failed, done; light and dark, 1280 x 800 and
900 x 600) in `D:\LeadForge\wt\window-shots\forget\`, made by headless Edge over CDP, one browser, killed afterwards; the dialog fits every
state (at 900 x 600 the tallest, the report with two warnings, ends at y 548 of 600). After looking: a failed dry run showed only the
engine's error, so a line was added above it saying the check did not finish and nothing was deleted (the dry-run-failed pictures were made
again). Same tokens and components (`Dialog`, `Skeleton`, `StatusBanner`, `ErrorBanner`, the warn note); nothing new in the visual language.
The pictures were made before the mock's warning words were changed to the real engine's.

**The campaign walk** (`selftest.rs`, `packaging/selftest-window.ps1`; 15 pictures now): opening the confirmation waits until the dialog
shows "files that would be removed", takes picture `07a-forget-report`, and only then presses "Delete and keep them out". The script
expects, in order: `cmd=person_forget ... ok` (the dry run), `selftest: shows 07a-forget-report: ... DIALOG: ... database rows ... files that would be
removed ... files that would be edited`, `cmd=person_forget ... ok` (the real call), `shows 07b-people-forgotten: ... Forgotten: millbrook-autos.example`;
and the numbers and the first 40 characters of each warning on that screen equal the engine's own dry run taken from its command line
(`forget report on screen must hold: '13 database rows', '2 files that would be removed', '0 files that would be edited'`). Walk 3 of this job:
```
cmd=person_forget origin=dev-venv in=50B ms=519 ok out=296B
selftest: shows 07a-forget-report: "people | DIALOG: Forget millbrook-autos.example? ... 13 database rows 2 files that would be removed 0 files that would be edited (lines taken out) Nothing was deleted: ...
cmd=person_forget origin=dev-venv in=51B ms=535 ok out=232B
selftest: shows 07b-people-forgotten: "people | ... Forgotten: millbrook-autos.example 13 database rows, 2 files deleted, 0 files with lines taken out. ...
shots taken: 15 of 15; probe clean: True / CAMPAIGN COMPARE PASS / expectations missed: 0 / processes left: 0 / throwaway folder left: False / SELFTEST PASS
```
**Three walks on the owner's screen (about 82 s each).** Walks 1 and 2 passed every log expectation (`expectations missed: 0`,
`CAMPAIGN COMPARE PASS`) but the pictures were 160 x 24 title bars (the window was minimised; `shots taken: 1 of 15`, then `0 of 15`):
`SELFTEST FAIL`. The script now restores a minimised window before each picture (`LfWin.Restore`, SW_SHOWNOACTIVATE); seen red and green on a
throwaway minimised WinForms window, not the app: without the restore `picture 160x24 counted: False`, with it `picture 1000x700 counted: True`.
Walk 3: the lines above, `SELFTEST PASS`. Not seen red in a walk: the new order and number expectations (no fourth walk was allowed). Not
run: the short walk on the release build (the install proof runs it).

**3. Three wordings that disagreed with the code (the code is the truth; no code changed).**
- Data screen, retention caption. Code: `retention.classify` takes the age from `runs.started_at` of the run named by `businesses.first_run_id`
  (the run that created the row; an empty or dangling one counts as the workspace's earliest run; no run at all: no age, never expires);
  `last_seen_at` is never read. L6 finding 2: a business first found through a register and merged with a Maps twin can carry the younger
  twin's run, so its expiry can come later. Was: "Counted from the day a business first entered the workspace." Now: "Counted from the start
  of the run that first found the business (the workspace's first run, if that run is not recorded). Finding it again does not extend it."
- `docs/window-actions.md`, "Missing" 6, the history table. Code: `config.key_refusal`: a registry key is read only from its environment
  variable or the OS keyring (service `leadforge`, entry `registry.<name>`) and a key in `leadforge.yaml` is refused. Was: "Today a key is a
  plain value in `leadforge.yaml`". Now says so, marked history. (Also updated there: the report-first forget, the rulings paragraph.)
- `config/leadforge.example.yaml`, `crawl.timeout_s`: `config.py` `CrawlCfg.timeout_s` is `10.0` (home page fetch; was 15.0); the example said 15.
  Now `10.0`. No test pins the example file (`tests/` and `scripts/` read only `icp.wescore.example.yaml`).

**4. The keyring: not done, the lock is not on `master`.** `git cat-file -e origin/master:requirements-keyring.lock` after a fetch at the start
and again at the end: `fatal: path 'requirements-keyring.lock' does not exist in 'origin/master'`. Nothing was improvised: the bundle and the
short walk (which still accepts `environment` for `keys_list`) are unchanged and the keyring proof was not run. When the lock lands: bring `master`
in, build the bundle's environment with the install line in the keyring slice file, change the short walk's `keys_list` expectation back to `ok`,
then the guarded proof (`keys_list` first; stop if a key is saved; marker saved through the Keys screen, searched for in every log, removed,
`keys_list` and the engine's command line checked for nothing left, the backend named).

**Gates on the final tree (through the lock, one at a time).** `app/src-tauri`: `cargo fmt --check` exit 0; `cargo clippy --all-targets --locked
-- -D warnings` exit 0; `cargo test --locked`: unit 14, `engine_dev` 4, `key_value_never_leaks` 2, `real_engine_shapes` 1 ignored, `run_seam` 6,
`standin_switch` 1, `version_agrees` 1, all passed; `permission-check` 3 passed. The capability file, `permission-check` and `build.rs`: `git diff` empty.
`app/ui`: `tsc --noEmit` exit 0, `vite build` exit 0, `npm test` as above. On this laptop the toolchain is `stable-x86_64-pc-windows-msvc`
(`RUSTUP_TOOLCHAIN=stable` resolves to the gnu host and fails at `dlltool`).

**The installer.** `build-engine-embed.ps1` rebuilt the bundled engine from the merged source (`leadforge 0.9.0`; the version is the engine's,
nothing edited by hand), then under the heavy lock `run-measured.ps1` ran `tauri.js build --config tauri.bundle.conf.json --bundles nsis -- --locked`:
`exit 0; duration 206 s; peak working set of the build's process tree 815 MB; free RAM before 1754 MB` (a first try ended `exit 1` at
`parking_lot_core`, `dlltool.exe` not found: no `RUSTUP_TOOLCHAIN` was set). `D:\LeadForge\wt\target\release\bundle\nsis\LeadForge_0.9.0_x64-setup.exe`,
36,513,553 bytes, sha256 `5f846667cc6033d6ca4bbcc74d309a01e46ab16e74a91dfae595f23fb20d3d10`. Its NSIS script names no stand-in, the release
`leadforge-window.exe` holds no `leadforge_window_standin` (byte search 0), and `target\release\engine` holds `python` only.
**The install proof, for the orchestrator with the normal token** (this session is elevated):
`powershell -NoProfile -ExecutionPolicy Bypass -File D:\LeadForge\wt\window\app\src-tauri\packaging\install-proof.ps1 -Setup D:\LeadForge\wt\target\release\bundle\nsis\LeadForge_0.9.0_x64-setup.exe`

## Review of the whole tool (independent reviewer, 2026-11-12, before the window and the pages merge)

Fixed here, each with a test seen red first:
- `sheet_open` started any file inside `exports` with its default program (a planted `run-me.cmd` was handed to the opener: `assert (0 == 2)`
  for `.cmd`, `.exe`, `.html`, `.lnk`, `.xlsx.bat`). It now opens `.xlsx`, `.csv` and `report.json` only.
- `agent_runner.resolve_command` took `.\claude.CMD` from the current folder (Windows' `which` searches it first), and with no `PATH` (the core
  passes none) Python searched `.;C:\bin`. Probe with the bundled `python.exe` and the core's exact variable list: `which claude: .\claude.CMD`.
  Now no `PATH` means no search, and a hit in the current folder is refused. (A first version also refused a bare name; four tests stub `which`
  with one, so it was narrowed to the current folder only: the first `check.mjs --ci` after it read `4 failed, 1048 passed`.)
- A business forgotten by name came back on the next run: discovery checked the suppression list for the domain and the place id only
  (`pipeline.py`), and a register row has no website. Red first: `Extra items in the left set: 'Quillfeather Garage'`.
- The Keys screen's title line said "Kept in the Windows keyring" while the bundled engine answers `environment` (no keyring package).

Probes, loopback only, not fixed (engine changes larger than a review fix; proposals in `docs/limits.md`):
- A business site's `302` to another loopback port was followed and read: `redirect followed to: http://127.0.0.1:65233/admin | body: <html>router
  admin page: admin@router-probe.lan</html>`.
- A 65,271-byte gzip page was read into memory whole: `read into memory: 67108877 bytes; crawl.max_text_bytes: 400000`.
- Forget, on the test workspace of `tests/test_window.py` with Priya's address added to `contacts`: forgetting the address left `people` = `['Priya Nair',
  ...]`; forgetting the name left `contacts` holding `priya@harbourside-motors.example`.

Correction to L11a: `purge_report` has 600 s in `engine.rs` `timeout()` (with export, apply, everything and forget), not the 120 s its proof table and
"Plan and code disagree" say; `docs/window-actions.md` already says 600 s.
