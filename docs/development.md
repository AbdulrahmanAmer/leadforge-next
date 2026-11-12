# Development

How the repository is laid out, how to set it up, the gates, which of them CI runs, and how a slice is recorded. Windows PowerShell commands unless stated.

## Layout

| Path | What is in it |
|---|---|
| `src/leadforge/` | the engine: `cli.py` (the commands), `pipeline.py`, `config.py`, `db.py` (schema 7), `retention.py` (forget, purge), `export.py`, `score.py`, `compliance.py` and `send_rules.py`, `providers/` (registers and the add-on seam), `enrich/` (crawler, extraction, registry, browser tier), `draft/`, `outreach/`, `window/` (the 21 commands of the window's seam) |
| `app/src-tauri/` | the window's core (Rust, Tauri 2): starts the bundled engine, holds the permission files and `packaging/` (installer and proof scripts) |
| `app/ui/` | the screens (React, TypeScript, Vite) and `src/engine.ts`, the one seam between screens and engine |
| `tests/` | the Python suite; `tests/golden/` and `tests/fixtures/` (made-up data only: `.example` addresses, Ofcom drama phone numbers); `tests/fixtures/e2e/` is the fake campaign |
| `scripts/` | `e2e_fake_campaign.py`, `e2e_window_run.py`, `e2e_compare.py`, `make_plugin_lock.py`, `make_licence_notices.py`, `mutation_trial.py` |
| `skills/` | the two agent skills (`generate-leads`, `send-outreach`) and `generate-leads/references/cli.md` |
| `bin/leadforge`, `install.py` | the plugin launcher and the skill installer |
| `config/` | the example settings and example campaign files |
| `.github/` | the CI workflow, the mutation workflow and the small check scripts |
| `docs/` | these pages; `docs/slices/` is the record of each slice; `docs/00` to `docs/10` and the plans are older design pages |
| `requirements.lock`, `uv.lock` | the hashed lock (what the launcher, the installer and CI install) and the uv lock it is made from |
| `check.mjs` | the one gate command |

## Set up

From source with the hashed lock, the way CI and the plugin launcher do it. Python 3.11 or later (CI runs 3.11 to 3.14).

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
```

The lock holds no dev tools. CI's test job installs `-e ".[dev]"` (unhashed, wheels from PyPI); do the same for `pytest` and `ruff`:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Do not regenerate a lock by hand: `uv lock`, then `python scripts/make_plugin_lock.py` (needs a network resolve). A change to the locked packages must also
re-make the licence notices: `scripts/make_licence_notices.py` (a test fails until it is).

The window needs Node 22 (`npm ci --ignore-scripts` in `app/ui` and in `app/src-tauri`) and the Rust toolchain that `app/src-tauri/rust-toolchain.toml` pins.

## The gates

| Gate | Command | What it proves | Run by CI |
|---|---|---|---|
| The one gate | `node check.mjs` (`--ci` in CI) | six steps in order: versions agree (`pyproject.toml`, `__init__.py`, both plugin manifests, both skills), skill front matter, skill references (each skill opens every file it names when installed alone), `ruff check src tests`, the Python suite, the digest contract (`leadforge --json version` and `status` each print one `LF_DIGEST` line) | yes: `test` job, Ubuntu and Windows, Python 3.11 to 3.14 |
| Non-editable install | `python -m pip install .` then `python -m leadforge version` and a read of the packaged scoring rubric | the wheel carries its data | yes, inside the `test` job |
| The fake campaign | `python scripts/e2e_fake_campaign.py` | one invented campaign through the command line against a loopback world (invented sites, registers, Companies House); every outside connection is refused and logged; the result equals `tests/fixtures/e2e/expected.json`; `--probe` shows the guard refusing an outside address | yes: `fake campaign` job, Ubuntu and Windows |
| The window, screens and core | in `app/ui`: `npm run typecheck`, `npm run build`, `npm test`; in `app/src-tauri`: `cargo fmt --check`, `cargo clippy --all-targets --locked -- -D warnings`, `cargo test --locked`; in `app/src-tauri/permission-check`: `cargo test --locked` | types, the screens' tests, the seam's shapes against the mock and the real engine's commands, the permission list (no send command) | yes: `window` job, Windows |
| Plugin manifests | `claude plugin validate .` | both manifests are valid | yes: `claude plugin validate` job |
| Mutation trial | the `mutation-trial` workflow, by hand or when its own files change | whether the delete-side tests notice one change at a time in `retention.py`, `db.py`, `export.py` | not on every push |
| The window's self-test | `app\src-tauri\packaging\selftest-window.ps1 -Exe <app.exe> -Shots <folder>` (short walk on the bundled engine); `-Campaign` (debug build): the fake campaign through the real window, compared with the same campaign on the command line | the seven screens, one error, one run and its stop, and (campaign walk) the delete side | no: needs a desktop; run on the laptop |
| The campaign walk and shape check | `app\src-tauri\packaging\real-shapes.ps1`, `scripts/e2e_window_run.py` | the real engine's 21 commands answer in the shapes the screens expect | no |
| The install proof | `app\src-tauri\packaging\install-proof.ps1 -Setup <installer.exe>` from an ordinary (not elevated) PowerShell; it refuses an elevated one | a silent per-user install with no administrator prompt, the installed app's short walk, uninstall, and no process or file left | no |

Heavy gates need memory: the build of the window peaked near 2.4 GB on a cold release build. Run one at a time. Slice L5 and L11 record the numbers.

Build the installer (after the engine is embedded by `app\src-tauri\packaging\build-engine-embed.ps1 <python.org embeddable zip>`, which checks the zip's SHA-256 and
installs the hashed lock into it):

```powershell
cd app\src-tauri
npm ci --ignore-scripts
node node_modules\@tauri-apps\cli\tauri.js build --config tauri.bundle.conf.json --bundles nsis -- --locked
```

The result is `target\release\bundle\nsis\LeadForge_<version>_x64-setup.exe`. It is not signed. The `target` folder is shared by every build of the crate.

## Rules that hold in the code

- A test never reads a real keyring, never reaches the internet, and uses made-up data only.
- A guardrail is never weakened to make a test pass: robots.txt, one request in flight per host, caps, suppression, no SMTP probing, no login-gated scraping, no anti-bot evasion.
- The window starts the engine and nothing else, and has no send action: `src/engine.rs` holds the crate's only `Command::new(`, and the permission test fails on anything outside its list.
- Time comes from `leadforge.util.utcnow()` and a `now` argument; tests set the date instead of waiting.
- No secret value in any file. `gitleaks protect --staged --no-banner` before a commit.

## How a slice is recorded

A slice is one piece of work with a name and a number (L1 to L12, plus `L11a`). Its record is one file in `docs/slices/`:

1. **Header:** type, stacks, version (or "Unreleased"), base commit.
2. **Spec:** what the slice must do, copied from the plan, not reworded.
3. **Build:** per item, what must hold (written before the code), the check of the code against that text by reading afterwards, and the proof: the real command and its real output. A new test is seen to fail for the right reason once, then pass.
4. **Plan and code disagree:** where they did, and which won.
5. **Not done / UNPROVEN:** plainly, each with the test or step that would settle it.
6. **Review:** an independent reader, who did not see the build, with a verdict and the commit it judged.

A change under "Unreleased" in `CHANGELOG.md` gets one line there; released sections are never edited. Version strings change only in a release commit, in the six places `check_versions.py` reads.
[`limits.md`](limits.md) collects every unproven, not-done or open item from the slice files; update it when a slice settles one.
