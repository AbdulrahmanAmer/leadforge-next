# L11a The engine's commands for the window

Started from `origin/slice/L6-the-delete-side` at `b15ef7a3e86156d63028166f1d5f67501e9a168c` (pull request 6 was still open on
2026-11-12 09:45, run `l11a-build`); rebased at 10:39 on `origin/master` `fd2886e` (L6 and L8 merged meanwhile; the only conflict,
CHANGELOG, kept both sides). The window's side (`app/`) is not on this branch and nothing under it is edited here.

# Spec

## The seam (the lead's words, 2026-11-12 09:50; quoted, not reworded)

> One command group `leadforge window <name>`. It reads ONE JSON document from stdin (the arguments object, `{}` when
> there are none), writes ONE JSON document to stdout (the result) and exits 0. On an error it exits non-zero and
> writes `{"kind": "...", "message": "...", "details": ["..."], "next": null or "..."}` to stdout. Nothing else ever
> goes to stdout; logs go to stderr. Arguments never travel in argv. The exception is `run_start`: it writes JSON
> lines to stdout, one RunEvent per line, until the run ends. `run_stop` asks the running run to stop cooperatively
> (a flag the runner checks between businesses) and returns its status.
>
> **The names, exactly these 21**: campaign_create, run_start, run_stop, run_status, campaigns_list, sheet_export,
> sheet_open, people_list, person_forget, address_suppress, purge_report, purge_apply, purge_everything,
> retention_get, retention_set, keys_list, key_save, key_remove, settings_get, settings_set, about.
>
> **The shapes**: every argument and result matches the TypeScript types in `engine.ts` field for field. Where the
> engine cannot supply a field, do NOT invent data: return the field as null and write the gap in the slice file
> with the type change you propose.
>
> **Rules of the seam**
> - `person_forget` takes `"dry_run": true` and then returns what WOULD be deleted and deletes nothing;
>   `purge_report` is the report-first twin of `purge_apply`.
> - `purge_everything` requires `"confirm": true`.
> - `key_save` takes the value on stdin only, stores it in the OS keyring, never echoes or logs it; `keys_list`
>   returns names and "set / not set" only.
> - `sheet_open` opens only a sheet inside the workspace's own exports folder (the path is checked AFTER links are
>   resolved) and nothing else.
> - `people_list` returns each contact with its source and found date when the engine has them (L7's C12), null
>   until then.
> - `about` returns the licence notices (C15) from a generated file.
> - No send or outreach command (C14). The existing command line and the plugin contract stay unchanged.

The contract for every type is `app/ui/src/engine.ts` on `origin/slice/L10-ui` (read with `git show`, 2026-11-12). The argument names
are those of the Tauri command table in `docs/window-actions.md` on the same branch (section "Tauri commands"), plus the two the seam
adds (`dry_run`, `confirm`).

## The 21 commands, their types, and where the engine gets each field

`ws` = the workspace (the folder the command runs in); `cfg` = `load_config(ws)`. "gap" = the engine has no source: returned as null,
see "Gaps and seam changes proposed".

| # | Command | Arguments (stdin) | Result type | Each field: from where |
|---|---|---|---|---|
| 1 | `campaign_create` | `{draft: CampaignDraft}` (`kinds: string[]`, `places: string[]`, `country: string`, `source: SourceId`, `maxLeads: number`) | `CampaignPlan` | answers written to `ws/campaigns/<slug>/answers.yaml`, compiled by `intake.compile_icp`; `campaign` = `icp.campaign`; `searches` = `plan_counts()["queries"]`, `estimatedBusinesses` = `est_max_results`, `estimatedSites` = `est_enrich_sites`, `estimatedMinutes` = `est_total_min` (`grid.build_plan`, `grid.plan_counts`); `warnings` = intake warnings + the `plan` command's warnings (`cli._plan_warnings`); `retentionMonths` = `cfg.retention.months` |
| 2 | `run_start` | `{args: RunArgs}` (`campaign: string`, `resume: boolean`) | `RunHandle` then `RunEvent` lines | `runId` = `pipeline.ensure_run` / `db.create_run`; events from `util.emit_progress` through a listener (`util.set_progress_listener`); the end event from `pipeline.run_pipeline`'s result or exception |
| 3 | `run_stop` | `{runId: string}` | `RunStatus` | writes the stop flag `leadforge_data/window-run.stop`; `util.emit_progress` raises `util.RunStopped` at the next business or query |
| 4 | `run_status` | `{runId: string \| null}` | `RunStatus \| null` | `runs` row (`id`, `stage`, `started_at`, `stats_json`), `cli._status_progress` (progress feed), `businesses`/`contacts` counts |
| 5 | `campaigns_list` | `{}` | `Campaign[]` | every `runs` row, newest first; the icp file at `runs.icp_path`; `businesses.first_run_id`; `contacts`; `scores`; `exports/<runId>/` |
| 6 | `sheet_export` | `{runId: string}` | `Sheet` | `export.export_run` for that run (its own icp), `summarize_for_digest`, `top_hooks`; tabs read back from the written xlsx |
| 7 | `sheet_open` | `{path: string}` | nothing (`null`) | the opener handed in (default `util.open_artifact`); path checked after `Path.resolve(strict=True)` against `cfg.exports_dir` |
| 8 | `people_list` | `{query: PeopleQuery}` (`search: string`, `limit: number`) | `PeoplePage` | `people` + `businesses`; email and phone from `enrichment_observations` whose `person_name` is that person; `source` = `people.source_url`; `foundAt`: gap; `suppressed` = `db.is_suppressed` |
| 9 | `person_forget` | `{value: string, dry_run?: boolean}` | `ForgetResult` | `retention.forget`; dry run: `retention.forget_report` (the same `forget_in_database` on an in-memory copy, the same file test) |
| 10 | `address_suppress` | `{value: string, kind: "email" \| "domain" \| null}` | `SuppressResult` | `db.suppress`, then the count of `suppression` |
| 11 | `purge_report` | `{}` | `PurgeReport` | `retention.purge(cfg, now, "report")`; `suppressed` = count of `suppression` |
| 12 | `purge_apply` | `{}` | `PurgeReport` | `retention.purge(cfg, now, "apply")` |
| 13 | `purge_everything` | `{confirm: true}` | `PurgeEverythingResult` | `retention.purge_everything` |
| 14 | `retention_get` | `{}` | `Retention` | `cfg.retention.months`; `min`/`max` from the field's own limits (`RetentionCfg`, `ge=1, le=12`) |
| 15 | `retention_set` | `{months: number}` | `Retention` | `retention.months` written to `leadforge.yaml` after `load_config` accepts it (as `config set` does) |
| 16 | `keys_list` | `{}` | `KeyStatus[]` | `window.keys` adapter: L9's keyring service; `savedAt`: gap |
| 17 | `key_save` | `{name: KeyName, value: string}` | `KeyStatus` | the adapter |
| 18 | `key_remove` | `{name: KeyName}` | `KeyStatus` | the adapter |
| 19 | `settings_get` | `{}` | `Settings` | `workspace` = `ws` resolved; `sheetFormats` = `cfg.export.formats`; `openSheetWhenDone` = `cfg.export.auto_open`; `theme`, `accent`: gap (the shell's own) |
| 20 | `settings_set` | `{patch: SettingsPatch}` | `Settings` | `export.formats`, `export.auto_open` written to `leadforge.yaml` after `load_config` accepts them |
| 21 | `about` | `{}` | `About` | `engineVersion` = `leadforge.__version__`; `licence` = `pyproject` `license` (`MIT`); `licences` = `src/leadforge/data/licences.json` (made by `scripts/make_licence_notices.py`); `windowVersion`: gap (the shell's own) |

## Error document

`{"kind", "message", "details", "next"}`. `kind` follows `engine.ts` `ErrorKind` and the exit codes in `util.py`: `LeadForgeError` 1
`failed`, a refused value 2 `usage`, `EnvError` 3 `environment`, `InputError` 4 `input`, `ProviderFailed` 5 `source`; the exit code is the
same number. The key commands without L9's keyring answer `not_available` (the brief's word, exit 3). An unknown name is `usage`.

# Build

## What must hold, per command (checked against the code by reading after it was written)

1. `campaign_create`: a draft without kinds, places or country, or with `maxLeads` below 1, is refused (`input`) and writes nothing.
   `source: "companies_house"` is refused (`input`): the engine needs SIC codes for it, the draft has none (seam change 3).
2. `run_start`: first line the `RunHandle`, then one RunEvent per line, the last one `finished`, `stopped` or `failed`. While it runs,
   `sys.stdout` points at stderr, so `LF_PROGRESS`/`LF_DIGEST`/print lines of the engine never reach the stream. `LEADFORGE_NO_UI=1` is
   set for the run: no console window and no automatic opening of the sheet (the window opens it with `sheet_open`).
3. `run_stop`: only a run started by `run_start` whose process is alive can be stopped; else `input`. The flag is a file; the runner
   checks it at every `emit_progress` (one per business in enrich, one per query in discover); the enrich and discover thread pools
   cancel what has not started, so a stopped run does not keep crawling. The stage is not advanced; `run --resume` continues.
4. `run_status`: `null` when the workspace has no run (or no database).
5. `campaigns_list`: `[]` when there is no database.
6. `sheet_export`: unknown run: `input` "no run found".
7. `sheet_open`: refused (`usage`) unless the resolved path is a regular file inside the resolved exports folder; nothing is opened.
8. `people_list`: `limit` 0 to 500; `matching` counts the search hits, `total` all people.
9. `person_forget`: `dry_run: true` changes no byte of the workspace (no database write, no `-wal`/`-shm`, no log file); a file that
   could not be cleaned is `input` with the files named.
10. `address_suppress`: empty value or a kind other than email/domain: `usage`.
11. `purge_report`: changes nothing (the engine's own `report` mode).
12. `purge_apply`: `files_locked` is `input`; `stopped_over_half` cannot happen in `apply` mode.
13. `purge_everything`: anything but `"confirm": true` (the JSON value true) is `usage` and deletes nothing.
14. to 15. retention: a value outside 1 to 12, or not a whole number, is `usage`; the file is not written.
16. to 18. keys: the value is never written to stdout, stderr or a log; without L9 `not_available`.
19. to 20. settings: `theme`/`accent` in a patch are `usage` (the shell keeps them); formats other than xlsx/csv are `usage`.
21. `about`: the notices file lists exactly the packages of `requirements.lock` with their locked versions and the lock's hash.

## Built: the 21 commands

| Command | State | Notes |
|---|---|---|
| campaign_create | done | `source: "companies_house"` refused (seam change 3); offer text is a marker (seam change 2) |
| run_start | done | proved against the fake campaign's loopback world (below) |
| run_stop | done | proved against the loopback world: stops at enrich 3 of 8, stage kept, resumed to the end |
| run_status | done | |
| campaigns_list | done | |
| sheet_export | done | |
| sheet_open | done | the opener is handed in; default `util.open_artifact` |
| people_list | done | one row per named person; see seam change 10 |
| person_forget | done | with `dry_run` |
| address_suppress | done | |
| purge_report | done | |
| purge_apply | done | the engine's state `nothing` is answered as `purged` with `deleted: 0` (the type has no `nothing`) |
| purge_everything | done | |
| retention_get | done | |
| retention_set | done | |
| keys_list | built, waits for L9 | answers `not_available` until L9 is in; tested with a fake backend |
| key_save | built, waits for L9 | as above |
| key_remove | built, waits for L9 | as above |
| settings_get | done | `theme`, `accent` null (seam change 8) |
| settings_set | done | refuses `theme`, `accent` |
| about | done | `windowVersion` null (seam change 9) |

18 of 21 work end to end now; the three key commands are built on the adapter and wait for L9.

## Gaps and seam changes proposed

Fields the engine returns as null because it has no source (never invented):

| Type.field | When null | Why |
|---|---|---|
| `RunStatus.campaign` | the run's campaign file cannot be read | the run row keeps only the file's path |
| `RunStatus.done` | the run is not running, or the progress feed is of another stage | the engine keeps live progress only in `progress.jsonl` while a run goes |
| `RunCounts.purged`, `RunCounts.expiringIn30Days` | a run not started by `window run_start` | `run` puts them in its digest line only; `run_start` records them on the run |
| `Campaign.name` | as `RunStatus.campaign` | |
| `Campaign.source` | a campaign not made by `campaign_create` (and not in company mode) | the engine's campaign file has no source; the window's form answer is kept in `campaigns/<name>/window.json` |
| `Campaign.keptUntil` | a run with no start time | |
| `Person.source` | the engine kept no page for that person | `people.source_url` is empty |
| `Person.foundAt` | always | the engine keeps no date per person (L7, C12) |
| `Person.campaign` | as `RunStatus.campaign` | |
| `KeyStatus.savedAt` | always | the keyring keeps no date (the type already allows null) |
| `Settings.theme`, `Settings.accent` | always | the window's own settings; the engine does not keep them |
| `About.windowVersion` | always | the window's own version |

Seam changes proposed (the lead decides; nothing here changes a name):

1. **`run_start`'s stream starts with the `RunHandle`.** The seam says one RunEvent per line; the `Engine` type also returns a
   `RunHandle`. Built: line 1 is `{"runId": "..."}`, then RunEvents, the last one `finished`, `stopped` or `failed`. Proposed: write this
   into the seam (the shell reads line 1 as the handle, the rest into the channel).
2. **`CampaignDraft` has no offer.** The engine requires `offer.what` (intake.py `_preflight`); it feeds the draft notes. Built: the text
   `not given: the campaign was made in the window`. Proposed: `CampaignDraft.offer: string` (one sentence: what is being sold).
3. **`source: "companies_house"` needs SIC codes.** A Companies House campaign is the engine's company mode, which requires
   `target.sic_codes`. Built: refused with `input`. Proposed: `CampaignDraft.sicCodes: string[]` (required when `source` is
   `companies_house`). Also: the engine takes its discovery providers from `leadforge.yaml` for the whole workspace, not per campaign, so
   `source: "dvsa"` is recorded but does not choose the provider; that is an engine change for a later slice.
4. **`ErrorKind` gains `not_available`** (the brief's word for the key commands before L9; exit 3). Proposed: add it to the union, or
   map it to `missing` in the shell.
5. **`RunStatus.campaign: string | null`, `RunStatus.done: number | null`, `RunCounts.purged: number | null`,
   `RunCounts.expiringIn30Days: number | null`** (the table above).
6. **`Campaign.name: string | null`, `Campaign.source: SourceId | null`, `Campaign.keptUntil: string | null`.**
7. **`Person.source: string | null`, `Person.foundAt: string | null`, `Person.campaign: string | null`.**
8. **`Settings.theme`, `Settings.accent`: the engine answers null and refuses them in `settings_set`** (`usage`). Proposed: the shell
   keeps them and merges; the engine's type is `Omit<Settings, "theme" | "accent">`.
9. **`About.windowVersion: string | null`** from the engine; the shell fills it.
10. **People are the engine's named people, not every contact.** `people_list` returns one `Person` per row of `people` (a named
    person at a business), with an email or phone only where the engine recorded that it belongs to that person
    (`enrichment_observations.person_name`). A business's general addresses (`office@...`) belong to no person and are not listed.
    Proposed: keep it so, or add a `Contact` list type for the unnamed addresses.

Smaller notes, no type change: `Sheet.tabs[].rows` is each tab's row count less its first row (the header of Leads and Drafts; Summary
and About have none). `person_forget` with `dry_run` counts as "removed" a file that `forget` would empty in place if it could not
delete it. `sheet_open` answers JSON `null`.

## After L9 is in

L9 (`origin/slice/L9-keys-and-the-agent-call`) puts `KEYRING_SERVICE = "leadforge"` and `_keyring_get(name)` (entry
`registry.<name>`) into `leadforge/config.py`. Then, exactly:

1. `keys.make_keys()` finds `config.KEYRING_SERVICE` and uses the same service and entry names as L9's `_keyring_get`, so a key saved
   from the window is the key the engine reads. No code change in `window/` for that.
2. The `keyring` package is L9's optional extra and is not in `requirements.lock`; without it the key commands answer `not_available`
   ("the keyring package is not installed"). The window's installer must carry the extra; that changes the lock, so
   `scripts/make_licence_notices.py` must be run again (the test fails until it is).
3. L9's switch `registry.keyring: false` is not read by the adapter. Decide whether `key_save` refuses when it is off.
4. `tests/test_window.py::test_key_commands_without_l9_answer_not_available` fails by design: replace it with a test that
   `make_keys()` uses `KEYRING_SERVICE` with `keys.default_backend` replaced by the fake backend. The other key tests use their own fake
   backend and need no change. No test may read or write the real keyring.
5. L9 changes the intake warning that names `config set registry.companies_house_key`; re-record
   `tests/golden/window/campaign_create.json` (`LF_UPDATE_GOLDEN=1`).

## Plan and code disagree

- `docs/window-actions.md` (on `origin/slice/L10-ui`), "Missing in the engine" item 6, says keys in the Windows keyring are slice
  **L7**; the brief says **L9**, and the keyring code is on `origin/slice/L9-keys-and-the-agent-call` (`config.py`,
  `KEYRING_SERVICE`, `_keyring_get`). Built against L9 as the brief says.
- `docs/window-actions.md` row 2 has the shell run `run` and read `LF_PROGRESS` lines; the seam (the lead, 09:50) has `window run_start`
  stream RunEvents itself. Built as the seam says; the digest lines of `run` are unchanged.
- The brief: "`people_list` returns each contact"; `engine.ts`: `Person` is a named person. See seam change 10.

## Decisions taken in this run

- `window` is dispatched in `cli.main()` before Typer, not registered as a Typer command: the golden of the agent contract
  (`tests/golden/agent_contract.json`, the list of commands) and `leadforge --help` stay unchanged, and no Typer usage text can reach
  stdout. `python -m leadforge window <name>` and the `leadforge` script both go through `main()`.
- The argument names inside the stdin object are those of the Tauri command table in `docs/window-actions.md`
  (`draft`, `args`, `runId`, `path`, `query`, `value`, `kind`, `months`, `name`, `patch`), plus `dry_run` and `confirm`.
- A stop is a flag file `leadforge_data/window-run.stop`; `util.emit_progress` checks it (once per business in enrich, once per query in
  discover) and the pipeline checks it between stages. The command line never sets the flag path, so `run` behaves as before. A stop
  that arrives after the last check (during export) does not stop the run: it finishes, and the stream says `finished`.
- `run_start` sets `LEADFORGE_NO_UI=1` in its own process: no console window, and the engine does not open the sheet; the window opens
  it with `sheet_open` when "open the sheet when done" is on.
- Campaigns made in the window live in `campaigns/<name>/` (`answers.yaml`, `icp.yaml`, `window.json`); `run_start` finds them by name.
- The dry run of `forget` is `retention.forget_report`: `forget_in_database` on an in-memory copy made through `db.readonly_view`, and
  the same file test (`_holds`, `_edits_lines`, the latter split out of `_scrub_file` so both use one rule).
- `ruff 0.17.4` (the version in `uv.lock`) was uploaded 7 days ago, at the line of the 7-day rule; the lint ran with the `ruff 0.15.13`
  already on this laptop instead of installing it.


## Proof (run `l11a-build`, 2026-11-12, STRIKERFORCE, Python 3.12 venv from `requirements.lock` + the hashed pytest set of `uv.lock`)

What each piece should do is written above ("What must hold"); the code was read against it before these ran.

`python -m pytest tests/test_window.py -p no:cacheprovider -rs` (34 tests: one golden and one shape check per command, run_start's
stream, the seam's rules):

```
..................................                                       [100%]
34 passed in 5.72s
```

The guard and key tests, each against a break of the code it covers (`breakrun.py` in the run folder: apply the break, run that
test, restore the file byte for byte). Every one red, for the reason named:

```
### sheet_open: no exports check (src/leadforge/window/commands.py)
exit 1: 3 failed, 30 deselected in 1.88s
E       assert (0 == 2)
E       assert (0 == 2)

### purge_everything: no confirm check (src/leadforge/window/commands.py)
exit 1: 1 failed, 32 deselected in 1.47s
E           AssertionError: {}
E           assert (0 == 2)

### person_forget: dry run deletes (src/leadforge/window/commands.py)
exit 1: 1 failed, 32 deselected in 2.62s
E       AssertionError: assert {'campaigns\\...ae1b6d6e8ed5'} == {'campaigns\\...45177c3', ...}
E         

### argv: arguments accepted (src/leadforge/window/__init__.py)
exit 1: 1 failed, 32 deselected in 10.82s
E       assert (0 == 2)

### stdout: engine prints reach stdout (src/leadforge/window/__init__.py)
exit 1: 1 failed, 32 deselected in 1.03s
E       AssertionError: stdout is not one JSON document: 'LF_DIGEST {"ok": true}\n{"windowVersion":null,"engineVersion":"0.8.0","licence":"MIT","licences":[{"na ...
E       assert (True and 2 == 1)

### keys: a log line holds the value (src/leadforge/window/keys.py)
exit 1: 1 failed, 32 deselected in 3.13s
E       assert not True
E        +  where True = any(<generator object test_a_planted_key_appears_in_no_output_and_no_log.<locals>.<genexpr> at 0x00000245DDBFD2F0>)

### keys: the backend's error text shown (src/leadforge/window/__init__.py)
exit 1: 1 failed, 32 deselected in 24.16s
E       assert not True
E        +  where True = any(<generator object test_a_planted_key_appears_in_no_output_and_no_log.<locals>.<genexpr> at 0x0000025A7B9BD490>)

### run_stop: the flag is never checked (src/leadforge/util.py)
exit 1: 1 failed, 32 deselected in 5.87s
E       AssertionError: assert (0 == 0 and 'finished' == 'stopped'
E         

### licences: the lock moved on (requirements.lock)
exit 1: 1 failed, 32 deselected in 1.11s
E       AssertionError: licences.json is older than requirements.lock: run scripts/make_licence_notices.py
E       assert 'ab72d56fcba3...849ac3da1492c' == 'd151fb48a99d...f159ff6ecdc32'
```

The shape and golden tests were not given a break round (the owner's rule of 14:35: guards and secrets only).

`python scripts/e2e_window_run.py --out <folder>`: the real `run_start`/`run_stop` in child processes against the fake campaign's
loopback world, every outside connection refused by its harness:

```
run_stop exit=0 {"runId":"run_20261112_08410_a7ee","campaign":"bristol-garages-fixture","state":"running","stage":"enrich","done":1,"total":8,"etaSeconds":null,"counts":{"businesses":10,"contacts":0,"purged":null,"ex
PASS  first run ends stopped  exit 0, last {"type": "stopped", "status": {"runId": "run_20261112_08410_a7ee", "campaign": "bristol-garages-fixture", "state": "stopped", "stage": "enrich", "done": null, "total": null, "etaSeconds": ...
PASS  run_status says stopped, stage kept  {"runId":"run_20261112_08410_a7ee","campaign":"bristol-garages-fixture","state":"stopped","stage":"enrich","done":null,"total":null,"etaSeconds":null,"counts":{"businesses":10,"contacts": ...
PASS  no stop flag left  
PASS  resumed run ends finished, same run  exit 0, last {"type": "finished", "status": {"runId": "run_20261112_08410_a7ee", "campaign": "bristol-garages-fixture", "state": "finished", "stage": "export", "done": null, "total": null ...
PASS  campaigns_list answers one JSON document  [{"runId":"run_20261112_08410_a7ee","name":"bristol-garages-fixture","kinds":["car repair"],"places":["Bristol"],"source":null,"state":"finished","stage":"export","startedAt":"2026-1 ...
PASS  sheet_export answers one JSON document  {"runId":"run_20261112_08410_a7ee","writtenAt":"2026-11-12T08:41:26Z","leads":10,"tabs":[{"name":"Leads","rows":10},{"name":"Drafts","rows":5},{"name":"Summary","rows":29},{"name":"Abo ...
PASS  people_list answers one JSON document  {"people":[{"id":"1","name":"Hamish Larkspur","role":"Director","business":"Northgate Tyres","domain":"northgate-tyres.example","email":null,"phone":null,"source":"http://northgate-tyre ...
PASS  no outside attempt beyond the fake campaign's known set  []
E2E WINDOW RUN PASS
```

Two earlier runs of that proof are part of the record: the first failed its "no outside attempt" check on refused DNS lookups of the
email check (`enrich.validate`), which the fake campaign itself expects (its `expected.json` lists them); the check now uses that same
known set. The second failed "first run ends stopped": the `run_stop` child started seconds late on this loaded laptop, after the
run's last check, and the run finished (as built: a stop after the last check does not stop). The proof now starts the stopper early
and releases it on the second enrich event. The third failed after the rebase on `master`: `run_stop` answered `PermissionError`
while the run went. Cause (from the logged traceback): `db.readonly_view` copies the database when its WAL holds data, and on Windows
the running run's SQLite locks refuse that copy; so every read command could fail during a live run, `run_stop` among them, and the
earlier passes were timing. Fixed: `reading()` falls back to SQLite's read-only mode on the live file when the copy is refused, and
the forget dry run answers `input` ("in use by a running run") instead. `test_read_commands_answer_while_a_run_holds_the_database`
forces the refusal; seen red with the fallback broken (`assert (1 == 0)` on run_status) and red on the dry run before
`check_schema_before_write` moved inside the `try` (it reads through `readonly_view` too). The run above is after the fix.

Found on the way, for L6's owners (not changed here): `forget`, `purge` and every command that calls `db.check_schema_before_write`
on Windows fail with `PermissionError` while another process has the database open with data in its WAL (the same refused copy in
`peek_schema_version`, which catches only `sqlite3.DatabaseError`). Not reproduced on the command line in this run.
