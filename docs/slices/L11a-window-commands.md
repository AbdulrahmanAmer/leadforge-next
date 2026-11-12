# L11a The engine's commands for the window

Started from `origin/slice/L6-the-delete-side` at `b15ef7a3e86156d63028166f1d5f67501e9a168c` (pull request 6 was still open on
2026-11-12 09:45, run `l11a-build`); rebased at 10:39 on `origin/master` `fd2886e` (L6 and L8 merged meanwhile; the only conflict,
CHANGELOG, kept both sides); rebased again at 10:55 on `origin/master` `9dc295c` (the debts slice: `tenacity` left `requirements.lock`, so `licences.json` was made again and the `about` golden lost that one package; CHANGELOG again kept both sides). The window's side (`app/`) is not on this branch and nothing under it is edited here.

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

## Gate and hosted CI

`node check.mjs` once, at below-normal priority, on 4c1cda4 (the venv's Scripts first on PATH; ruff 0.15.13 in the venv, see Decisions):

```
ok  versions agree  0.4
ok — 2 skill(s) have portable frontmatter
ok  skill frontmatter  0.2
ok: 2 skills open every file they name when installed alone; shared reference copies are identical
ok  skill references  0.3
All checks passed!
ok  lint  0.2
899 passed, 4 skipped in 260.83s (0:04:20)
ok  tests  262.5
ok  cli digest  2.2
CHECK PASS sha=4c1cda4 tree=clean steps=6 skipped=0 secs=266
```

Hosted CI, run 43185276515 on 4c1cda4 (pull request 14), read with `gh run view`: 13 jobs, 13 success.

```
claude plugin validate  success
fake campaign · windows-latest  success
Validate plugin manifests  success
windows-latest · py3.12  success
ubuntu-latest · py3.14  success
ubuntu-latest · py3.12  success
ubuntu-latest · py3.13  success
Version strings agree  success
windows-latest · py3.13  success
fake campaign · ubuntu-latest  success
windows-latest · py3.11  success
windows-latest · py3.14  success
ubuntu-latest · py3.11  success
```

The commit that adds this section has its own run; its result is in the pull request and the run report, not here.

After the second rebase (on `9dc295c`) the full gate was NOT run again (one full gate per run): `python -m pytest tests/test_window.py
tests/test_golden_contracts.py tests/test_cli_contract.py` gave `81 passed in 40.41s`, `ruff check src tests` `All checks passed!`,
`check_versions.py` all 0.8.0, `make_licence_notices.py --check` `licence notices match the lock`. The full suite of the rebased
commit is the hosted CI's.

# Build 2: matching the window core (run `l11a-match`, 2026-11-12)

The authority for stdin is the object `app/ui/src/engine.tauri.ts` passes to `invoke` on `origin/slice/L11-window` (`7e655b0`); the
core (`app/src-tauri/src/lib.rs`, `engine.rs` there) passes it on unchanged, with two edits: `run_start` drops `events` (the Tauri
channel), and a call without arguments becomes `{}`. `engine.ts` on `slice/L11-window` is byte-identical to the one on
`slice/L10-ui` that Build 1 read (sha256 compared): no type moved.

## The stdin keys, command by command

| # | Command | Keys `engine.tauri.ts` sends (after the core) | Keys the command read before this build | Equal |
|---|---|---|---|---|
| 1 | campaign_create | `draft` {kinds, places, country, source, maxLeads} | `draft` {the same five} | yes |
| 2 | run_start | `args` {campaign, resume} (`events` dropped by the core) | `args` {campaign, resume} | yes |
| 3 | run_stop | `runId` | `runId` | yes |
| 4 | run_status | `runId` (string or null) | `runId` (string or null) | yes |
| 5 | campaigns_list | none (`{}`) | none | yes |
| 6 | sheet_export | `runId` | `runId` | yes |
| 7 | sheet_open | `path` | `path` | yes |
| 8 | people_list | `query` {search, limit} | `query` {search, limit} | yes |
| 9 | person_forget | `value` | `value` (+ `dry_run`, the engine's own, optional) | yes |
| 10 | address_suppress | `value`, `kind` (null when not given) | `value`, `kind` (null allowed) | yes |
| 11 | purge_report | none | none | yes |
| 12 | purge_apply | none | none | yes |
| 13 | purge_everything | `confirm` (true) | `confirm` | yes |
| 14 | retention_get | none | none | yes |
| 15 | retention_set | `months` | `months` | yes |
| 16 | keys_list | none | none | yes |
| 17 | key_save | `name`, `value` | `name`, `value` | yes |
| 18 | key_remove | `name` | `name` | yes |
| 19 | settings_get | none | none | yes |
| 20 | settings_set | `patch` {any of theme, accent, sheetFormats, openSheetWhenDone} | `patch` {sheetFormats, openSheetWhenDone}; theme and accent REFUSED (`usage`) | **no** |
| 21 | about | none | none | yes |

Top-level keys were equal for 21 of 21; inside them, 20 of 21: `settings_set` refused the two keys of `SettingsPatch` the screens
own. Fixed in this build (below). The key commands read the right keys but answer an error until L9 is in (point 5).

## The five points: what must hold

1. **Keys.** Each of the 21, fed the object `engine.tauri.ts` sends, answers a result (exit 0, one JSON document), never `usage`.
   `settings_set` accepts `theme` (light, dark, system) and `accent` (cobalt, brass, celadon, ember) and keeps them in the workspace
   (`leadforge_data/window-settings.json`); `settings_get` returns them (`system` and `cobalt` until set: the first value of
   the window's own choice, not data about anyone).
2. **run_start.** The core takes stdout line 1 as the handle (any line, it does not look inside) and relays every later line.
   So: once a run exists, line 1 is `{"runId"}` and the last line is `finished`, `stopped` or `failed` on every way out the code
   can reach: normal end, stop, a `LeadForgeError`, any other exception, an interrupt (BaseException), the planning step failing
   after the run row exists, and the run's end bookkeeping failing (then the end event is built from the status read at the
   start). A start refused before any run exists (no such campaign, bad arguments, the start-of-run clean-up refusing) has no
   run id to give: it answers the seam's error document alone, non-zero exit, as the stand-in does. When the process is ended
   from outside nothing can be written; `run_status` then reports the run `failed` ("The engine process ended before the
   run did."), never `running`: the run row keeps the run's process id and `window_state = running`, and a dead process id
   with that state reads as failed.
3. **run_stop from a second process.** The stop is the file `leadforge_data/window-run.stop` (crosses processes); the run checks
   it at every progress report and between stages; the run ends within 10 s of the stop with a `stopped` event last, and the
   workspace opens cleanly after (run_status answers, the flag file is gone).
4. **run_status beside a run.** A second process answers within 30 s while the run writes, and neither side meets a database
   lock error.
5. **Kinds and limits.** Every error the window commands can emit has one of the seven kinds `failed, usage, environment, input,
   source, keyring, missing`. `not_available` becomes `keyring` ("the shell could not reach the Windows keyring" is what the
   screens say for it; `missing` means "no command for this", which is not the case). An arguments document over 1 MiB is
   refused with `input`. No `run_start` line exceeds 64 KiB: a text field longer than 4,000 characters is cut and ends
   with `[cut]`. `sheet_open` answers `null` and calls the opener; the real opener (`util.open_artifact`) only outside tests.

## Built in Build 2

- `settings_set` takes `theme` and `accent` (the values of `ThemeSetting`, `AccentSetting`; anything else is `usage`) and keeps
  them in `leadforge_data/window-settings.json`; `settings_get` answers them, `system` and `cobalt` until set. This replaces
  Build 1's seam change 8 (the engine no longer refuses them and no longer answers null). Goldens re-recorded because of it:
  `tests/golden/window/settings_get.json`, `tests/golden/window/settings_set.json` (theme and accent, nothing else).
- The kind `not_available` is gone: the key commands answer `keyring` before L9 (exit 1, as the stand-in's `keyring`).
  This replaces Build 1's seam change 4. "After L9 is in" item 4 now names
  `test_key_commands_without_l9_answer_keyring` (renamed from `..._not_available`).
- `KINDS` in `window/__init__.py` is `engine.ts` `ErrorKind`; `EXIT_CODES` holds exactly those seven.
- Arguments over 1 MiB (UTF-8 bytes of stdin): `input`, "The arguments are larger than 1 MiB."
- `run_start`: every line goes through `write_line`, which cuts any text over 4,000 characters (then 200 if the line is still
  64 KiB or more) and marks it ` [cut]`; lists in a line keep their first 20 items. A progress message is already cut to 120
  characters by `util.emit_progress` (util.py line 410), so in practice the cut meets a failure's details or a notice.
- `run_start`: the handle is written as soon as the run row exists; planning (`_plan_into_db`), the run's start bookkeeping and
  the notice are inside the `try`; `BaseException` (an interrupt) ends the stream with `failed`; when the end cannot be recorded
  in the database the end event is built from the status read when the run began (state, reason set; done, total null).
- `RunStatus.done`/`total` after a run: `run_start` records its last progress line (`window_progress_stage`, `window_done`,
  `window_total` in the run's stats) and `status_doc` answers them when that stage is the run's stage. Before, a finished or
  stopped run always answered null (`engine.ts` says `done: number`, as the stand-in does).
- `Person.foundAt` is the time the engine recorded the shown email (else phone) for that person (`enrichment_observations.observed_at`); null when it holds neither. This narrows Build 1's gap ("always null") and seam change 7 to people with no email or phone of their own. Golden re-recorded because of it: `tests/golden/window/people_list.json` (Priya's `foundAt`, nothing else).
- `scripts/e2e_window_run.py` prints the time from `run_stop`'s answer to the run's end and the longest wait between two
  stream lines.

## Proof (run `l11a-match`, STRIKERFORCE, Python 3.12 venv from `requirements.lock` + the hashed pytest set of `uv.lock`)

What each piece should do is written above ("The five points: what must hold"); the code was read against it before the tests ran.

New tests, first run against the code BEFORE this build (the source changes set aside with `git diff src > patch; git checkout
-- src`, then `git apply`): red for the change they cover:

```
FAILED tests/test_window.py::test_key_commands_without_l9_answer_keyring
FAILED tests/test_window.py::test_each_command_answers_what_the_screens_send[settings_get]
FAILED tests/test_window.py::test_each_command_answers_what_the_screens_send[settings_set]
FAILED tests/test_window.py::test_the_error_kinds_are_the_seven_the_screens_know
FAILED tests/test_window.py::test_arguments_over_1_mib_are_refused_with_input
FAILED tests/test_window.py::test_no_run_start_line_exceeds_64_kib
FAILED tests/test_window.py::test_run_start_ends_with_an_end_event_on_every_way_out[planning]
FAILED tests/test_window.py::test_run_start_ends_with_an_end_event_on_every_way_out[end_bookkeeping]
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
D:\homelab-work\l11a-match\leadforge-next\tests\test_window.py:553: KeyboardInterrupt
```

(the last two lines are `[interrupt]` on the old code: the interrupt left `run_start` without an end event and ended pytest.)
Green already on the old code, because Build 1 had that behaviour: the other 19 `screens_send` cases, `[engine_error]`,
`[exception]`, `test_a_start_refused_before_a_run_exists_is_one_error_document`,
`test_after_the_run_process_is_ended_from_outside_status_is_not_running`,
`test_run_stop_from_a_second_process_ends_the_run_within_10_s_and_status_answers_beside_it`. No break round beyond this (the
owner's rule of 14:35). Two of the new tests failed once on the new code, both for a test-side cause, written before the fix:
`test_no_run_start_line_exceeds_64_kib` read line 2 as the progress event (it is the start-of-run clean-up notice), then
expected the progress message cut at 4,000 (the engine already cuts it at 120, `util.py:410`); the test now finds the progress
line by type and checks the failure's details for the mark.

`python -m pytest tests/test_window.py -p no:cacheprovider -s` (the last code change, `done` after a run, came after this run;
the full gate below covers it):

```
..run_stop answered to the run's end: 0.00 s; run_stop started to the run's end: 1.51 s
66 passed in 13.36s
```

(0.00 s: with the test's stand-in pipeline (one business every 0.2 s) the run had ended before the `run_stop` process exited.)

`python scripts/e2e_window_run.py --out <folder>` (the real `run_start`/`run_stop`/`run_status` processes, the fake campaign's
loopback world, every outside connection refused):

```
  run_stop exit=0 {"runId":"run_20261112_09210_fa79","campaign":"bristol-garages-fixture","state":"running","stage":"enrich","done":1,"total":8,"etaSeconds":null,"counts":{"businesses":10,"contacts":0,"purged":null,"ex
  run_stop answered to the run's end: 8.41 s
  longest wait between two stream lines (two checks of the stop flag): 8.28 s
  longest wait between two stream lines (two checks of the stop flag): 5.94 s
PASS  first run ends stopped  exit 0, last {"type": "stopped", "status": {"runId": "run_20261112_09210_fa79", "campaign": "bristol-garages-fixture", "state": "stopped", "stage": "enrich", "done": 1, "total": 8, "etaSeconds": null, "counts": {"businesses": 10, "contacts": 0, "purged": null, "expiringIn30Days": null}, "startedAt": "2026-11-12T
PASS  run_status says stopped, stage kept  {"runId":"run_20261112_09210_fa79","campaign":"bristol-garages-fixture","state":"stopped","stage":"enrich","done":1,"total":8,"etaSeconds":null,"counts":{"businesses":10,"contacts":0,"purged":null,"expiringIn30Days":null},"startedAt":"2026-11-12T09:21:06Z","reason":null}
PASS  no stop flag left
PASS  resumed run ends finished, same run  exit 0, last {"type": "finished", "status": {"runId": "run_20261112_09210_fa79", "campaign": "bristol-garages-fixture", "state": "finished", "stage": "export", "done": null, "total": null, "etaSeconds": null, "counts": {"businesses": 10, "contacts": 10, "purged": 0, "expiringIn30Days": 0}, "startedAt": "2026-11-
PASS  campaigns_list answers one JSON document  [...]
PASS  sheet_export answers one JSON document  {...}
PASS  people_list answers one JSON document  {...}
PASS  no outside attempt beyond the fake campaign's known set  []
E2E WINDOW RUN PASS
```

**run_stop from a second process: the fake campaign's run ended 8.41 s after `run_stop` answered**, with `stopped` last, and the
workspace opened cleanly (run_status answered, no flag left, the resume finished the same run). That is inside the core's 10 s,
by a thin margin. The longest wait between two checks of the flag was 8.28 s: one business in enrich. On a real site it can be
longer: one business's enrich is bounded by `crawl.site_budget_s` 45 s (config.py line 72) plus rendered pages
(`render_timeout_s` 20 s, 2 pages) and the NER call (30 s), so a stop can wait well over 10 s; then the core ends the engine and
`run_status` answers `failed` ("The engine process ended before the run did."), not `stopped`. A check inside one site's crawl
(between two page fetches) is where it would go, but it is NOT small: a `RunStopped` raised in a pool worker is caught by
`except Exception` in `enrich/runner.py` (lines 414 and 590) and recorded as a failed site, and the pool's exit waits for the
fetches in flight. Not added; seam change 11.

**run_status beside a run**: the second-process test above asks `run_status` three times while the run writes its database
every 0.2 s: each answered `running` within 30 s, no "locked" on either side's stderr. The e2e proof's `run_stop` read the
same way during the real run.

**After a killed run**: `test_after_the_run_process_is_ended_from_outside_status_is_not_running` kills the real `run_start`
process after its first progress line; `run_status` then answers `failed`, reason "The engine process ended before the run
did." Limit: the check is the process id being alive (`util.pid_alive`); if Windows hands the same id to another process
before `run_status` asks, the run reads `running`. UNPROVEN either way; settling it needs the process's start time stored
beside its id.

### Sizes and times on 10,000 invented businesses

`measure_and_compare.py` (run folder `D:\homelab-work\l11a-match\measure\`, not in the repo): a workspace of 10,000 invented
businesses, each with a contact, a named person, a person-linked email and a score; each command in its own
`python -X utf8 -I -m leadforge window <name>` process, as the core starts it, at below-normal priority on a shared laptop:

| Command | arguments | exit | stdout | core limit | time | core timeout | note |
|---|---|---|---|---|---|---|---|
| people_list | `{"query": {"search": "", "limit": 500}}` | 0 | 141,187 B | 8,388,608 B | 1.03 s | 120 s | people 500, matching 10000, total 10000 |
| people_list | `{"query": {"search": "priya", "limit": 50}}` | 0 | 14,148 B | 8,388,608 B | 13.27 s | 120 s | people 50, matching 1000, total 10000 |
| sheet_export | `{"runId": "run_20261101_090000_ab12"}` | 0 | 721 B | 8,388,608 B | 28.11 s | 600 s |  |
| purge_report | `{}` | 0 | 120 B | 8,388,608 B | 7.55 s | 120 s |  |
| about | `{}` | 0 | 309,587 B | 8,388,608 B | 3.17 s | 30 s |  |

Every one inside its limits. `people_list` cannot pass 8 MiB: `limit` is at most 500. Its search took 13 s on 10,000 people
(the plain page 1 s; the cause was not looked into). Both read every person first, so the time grows with the workspace; how fast is UNPROVEN beyond 10,000 (seam change 12). The core gives
`purge_report` 120 s (`engine.rs` `timeout()`), not the 600 s of "purges" in the brief; `person_forget` gets 600 s there.

### Shape against the stand-in

Same input to the stand-in (`leadforge_window_standin.py` of `slice/L11-window`, run as the core runs it) and to the engine
(in one process, keys on an in-memory backend, the opener a no-op, `run_start` on a stand-in pipeline that ends at `exported`);
keys and kinds compared at every depth (a list by its first element):

```
| campaign_create | equal |
| run_start | $.event progress.etaSeconds: engine "null", stand-in "number" |
| run_status | equal |
| run_stop | $.done: engine "null", stand-in "number"; $.total: engine "null", stand-in "number" |
| sheet_export | equal |
| campaigns_list | equal |
| sheet_open | equal |
| people_list | $.people[0].phone: engine "null", stand-in "string" |
| address_suppress | equal |
| person_forget | equal |
| purge_report | equal |
| purge_apply | equal |
| retention_get | equal |
| retention_set | equal |
| keys_list | $[0].savedAt: engine "null", stand-in "string" |
| key_save | $.savedAt: engine "null", stand-in "string" |
| key_remove | equal |
| settings_get | equal |
| settings_set | equal |
| about | $.windowVersion: engine "null", stand-in "string" |
| purge_everything | equal |

equal for 15 of 21
```

Three earlier runs of the compare are part of the record (the third, before `foundAt` below, also 15 of 21 with `people_list` differing on `foundAt` too): the first had 13 of 21 (`done` null after every run: fixed in the
engine, above; `purge_everything` exit 1 on a `PermissionError` on `db.sqlite3-wal`: the compare's own process still held the
in-process `run_start`'s connections, which a real engine process closes by ending; the compare now collects them first).
The second had 14 of 21 (its stand-in pipeline left the run at stage `planned`; the real pipeline leaves `exported`).

The six that remain, each a null where the stand-in has a value (`people_list` counts once):

| Command | Field | `engine.ts` | Why the engine has null | Where |
|---|---|---|---|---|
| run_start | progress `etaSeconds` | `number \| null` | the engine's progress line carries no estimate | allowed by the type |
| run_stop | `done`, `total` | `done: number`, `total: number \| null` | the compare marks a run `running` without a live progress feed; the real run in the e2e proof answered `"done":1,"total":8` | the compare's set-up, not the engine |
| people_list | `phone` | `string \| null` | the invented person has no phone of their own | data, allowed by the type |
| keys_list, key_save | `savedAt` | `string \| null` | the keyring keeps no date | allowed by the type |
| about | `windowVersion` | `string` | the window's own version; the engine does not know it | seam change 9 (Build 1): the core fills it |

Still null where `engine.ts` says `number`: `RunStatus.done` of a finished run whose last progress line is of an earlier stage
(the fake campaign's resumed run: its export stage sends no progress line, so `done` and `total` are null at `finished`), and
of a running run whose progress feed is of another stage. Seam change 5 (Build 1) stands for those.

## Plan and code disagree (Build 2)

- **The core takes ANY first line of `run_start` as the handle.** `lib.rs` `run_start` (slice/L11-window) sends line 1 to the
  window as the `RunHandle` without looking inside; its comment says "no handle line: the engine refused the run (its error
  object)", but in stream mode that error object IS line 1, so a refused start (no such campaign, the start-of-run clean-up
  refusing) reaches the screen as a `RunHandle` with no `runId`, and the screen waits on "running". The stand-in does the same
  (its `Refused` before the handle is written as line 1). The engine cannot fix this alone: before a run exists it has no run
  id to hand over. Not built; seam change 13.
- The brief: "600 s for export, purges and forget"; `engine.rs`: `PurgeReport` is not in the 600 s list (120 s).
- The brief, point 5: "`run_stop`, `run_status` and `about`" 30 s; `engine.rs` agrees (and `version`).

## Seam changes proposed (Build 2; the lead decides)

11. **A stop that waits for one slow business.** The run checks the stop flag once per business; one business can take more
    than 10 s (bounded by `crawl.site_budget_s` 45 s plus render and NER time). Either the core gives the run longer than 10 s
    after `run_stop` (the stop is clean and resumable, the kill is not), or a later engine slice checks the flag between page
    fetches (needs `RunStopped` re-raised before the `except Exception` of `enrich/runner.py` lines 414 and 590).
12. **`people_list` search on a large workspace.** 13 s on 10,000 people; larger workspaces were not measured. Proposed:
    an index on the searched fields in a later engine slice, or the core's timeout for `people_list` raised; no type change.
13. **A refused start in the core.** `lib.rs` `run_start`: when line 1 is an error object (`is_error_object`) and the engine
    exits non-zero, reject with it instead of relaying it as the handle. The engine already writes exactly that document.
14. **`RunStatus.done: number | null`** (extends seam change 5): a finished run's last progress line may be of an earlier stage.

## Rebase on master `1d741bc` (L7, 0.9.0), during this run

`origin/master` moved while this build ran (L7 merged, 0.9.0). The branch was rebased on it; the one conflict, CHANGELOG, kept
both sides (L11a's lines under `[Unreleased]`, master's `[0.9.0]` entry below them). Goldens re-recorded because of master, not
this work: `tests/golden/window/about.json` (`engineVersion` 0.9.0) and `tests/golden/window/sheet_export.json` (the sheet's
About tab has 27 rows, one more since L7). `make_licence_notices.py --check`: "licence notices match the lock" (L7 changed no
lock). The full gate was run before the rebase (on `11f83f6`, below); after it, `tests/test_window.py` and hosted CI.

`node check.mjs` once, at below-normal priority, on `11f83f6` (before the rebase; the venv's Scripts first on PATH, ruff 0.15.13):

```
ok  versions agree  0.2
ok — 2 skill(s) have portable frontmatter
ok  skill frontmatter  0.2
ok: 2 skills open every file they name when installed alone; shared reference copies are identical
ok  skill references  0.2
All checks passed!
ok  lint  0.9
932 passed, 3 skipped in 240.24s (0:04:00)
ok  tests  241.6
ok  cli digest  2.2
CHECK PASS sha=11f83f6 tree=clean steps=6 skipped=0 secs=246
```

## Hosted CI (Build 2)

Run 43190035018 on `bfc022b` (the first push of this build): 11 of 13 success, `ubuntu-latest · py3.11` and
`ubuntu-latest · py3.12` failure:

```
FAILED tests/test_window.py::test_after_the_run_process_is_ended_from_outside_status_is_not_running - ValueError: I/O operation on closed file.
FAILED tests/test_window.py::test_run_stop_from_a_second_process_ends_the_run_within_10_s_and_status_answers_beside_it - AttributeError: 'Popen' object has no attribute '_fileobj2output'
```

Cause (from the log, `subprocess.py:2067`): the tests closed the run process's stdin after writing the arguments and later
called `communicate()`; on Linux, Python 3.11 and 3.12 flush stdin there and a closed file raises (Windows and 3.13+ do not,
so it was green on this laptop). The test side was wrong, not the engine: the closed handle is now dropped from the `Popen`
(`p.stdin = None`). No assertion changed.

Run 43192533842 on `1acb53f` (after the fix and the rebase on `1d741bc`), read with `gh run view`: 13 jobs, 13 success.

```
windows-latest · py3.14  success
ubuntu-latest · py3.11  success
ubuntu-latest · py3.12  success
Version strings agree  success
claude plugin validate  success
windows-latest · py3.11  success
ubuntu-latest · py3.14  success
fake campaign · windows-latest  success
windows-latest · py3.12  success
Validate plugin manifests  success
ubuntu-latest · py3.13  success
fake campaign · ubuntu-latest  success
windows-latest · py3.13  success
```

The commit that adds these lines has its own run; its result is in the pull request comment and the run report.

# Build 3: the decisions, and after L7 and L9 (run `l11a-final`, 2026-11-12)

Base: the branch rebased on `origin/master` `0f2d3ff` (0.9.0: L7 merged at `1d741bc`, L9 merged at `0f2d3ff`); the rebase had no
conflict. Both "After L7 is in" and "After L9 is in" apply. The window's types for reference: `app/ui/src/engine.ts` on
`origin/slice/L11-window` `0256c42` (read with `git show`); they already carry the decisions below (`CampaignDraft.offer`,
`CampaignDraft.sicCodes`, `Settings.sources`, no `theme`/`accent` in `Settings`, no `windowVersion` in `About`). Where they and the
decisions differ, the decisions win; no difference was found.

## What must hold, per decision (written before the code; the diff was read against it after)

1. **run_start** (accepted as built): line 1 the `RunHandle`, then RunEvents, the last one `finished`, `stopped` or `failed`. No change.
   13 (accepted as built): a start refused before a run exists writes the error document as line 1 and exits non-zero, no handle;
   `test_a_start_refused_before_a_run_exists_is_one_error_document` stays.
2. **offer**: `draft.offer` is required text. Missing, not text, or blank: refused with `input`, a detail naming `offer`, nothing
   written. The given text (trimmed) is the campaign's `offer.what`; the constant "not given: the campaign was made in the window"
   is gone from the code.
3. **sicCodes and source**: `draft.sicCodes` is read only when `source` is `companies_house`; then a missing, empty or non-text list
   is refused with `input`, a detail naming `sicCodes`; a code that is not five digits is refused with `input` by the engine's own
   check (`Target._sic_codes`). A `companies_house` draft compiles to the engine's company mode (`target.mode: company`,
   `target.sic_codes`). For any other source `sicCodes` is ignored, whatever it holds. Then, before anything is written: a source
   that is not among the providers the workspace's `leadforge.yaml` enables (`discovery.providers`) is refused with `input`, a
   detail naming `source`, and `next` saying which ones this workspace is set to. `settings_get` returns `sources`: the entries of
   `discovery.providers` that are a `SourceId` (`dvsa`, `companies_house`), in the file's order, each once.
4. **not_available maps to missing**: no window command emits `not_available`, nor `keyring` for "L9 is not there"; after L9 that
   case is gone (see "After L9 is in" below). `missing` stays among the seven kinds and no command emits it today.
5. **Nullable** (present, may be null): `RunStatus.campaign`, `RunStatus.done`, `RunCounts.purged`, `RunCounts.expiringIn30Days`.
   14: `done` may be null for a finished run too. Already so; no change.
6. **Nullable**: `Campaign.name`, `Campaign.source`, `Campaign.keptUntil`. Already so; no change.
7. **Nullable**: `Person.source`, `Person.foundAt`, `Person.campaign`; with L7 in, see "After L7 is in" below.
8. **theme and accent leave the engine**: `settings_get` returns `workspace`, `sheetFormats`, `openSheetWhenDone`, `sources`; the
   keys `theme` and `accent` are ABSENT. `settings_set` takes `patch` with `sheetFormats` and `openSheetWhenDone` only and has no
   rule of its own for `theme` or `accent` any more: like any other key that is not an argument they are `usage` ("not an argument
   of this command"). `leadforge_data/window-settings.json` is neither written nor read.
9. **about**: `engineVersion`, `licence`, `licences`; the key `windowVersion` is ABSENT.
10. **people_list** = the engine's named people, an email or phone only where recorded as that person's. Already so; no change.
- `KeyStatus.savedAt` null: as it is.
- 11 (stop between page fetches) and 12 (people_list search): below, each with what must hold.

## After L7 is in (master 0.9.0)

L7's C12 keeps where and when a detail was found in `enrichment_observations` (`source_url`, `observed_at`; no table change, L7
slice file item 6). The person's own find is the observation `field = 'person.name'` that `enrich/runner.py` writes with the
person's id when it stores a person from a page.
- `Person.source` and `Person.foundAt` come from ONE record, never mixed: the newest observation of the shown email (else the shown
  phone) recorded as that person's; when the person has neither, the newest `person.name` observation of that person (by
  `person_id`, else by name at the business). `source` is that record's page address (`source_url`), else its `source` name, as
  C12 does in the sheet; `foundAt` is its `observed_at`; an empty value is null.
- Added after the first e2e run (below): a person from a register (`providers/registry.py`) has no observation; the register
  writes an `evidence` row (`ref_table = 'people'`, `fact = 'registry_officer'`, the register page, the time it was read) with no
  person id and no name, and the same page as the person's `people.source_url`. So, when a person has no observation: the newest
  `evidence` row of `ref_table = 'people'` at that business whose `url` is the person's `people.source_url` (a `dm_candidate` row
  only when its snippet starts with the person's name, since a site page names several people); `source` its `url`, `foundAt`
  its `observed_at`. Every officer read from one register page gets that page and that time: they were read in that one fetch.
- A person with no such record (stored before the engine kept one, or planted) has `source` null and `foundAt` null: the screen says
  "not recorded". `people.source_url` alone (a page with no date) is no longer used: a source without its date is not C12.
- Test seen red first: a person stored by the engine's own persist step (`enrich.runner._persist`, the step a run takes after a
  site's crawl) with no email or phone has both; a planted person with no record has both null.

## After L9 is in (master 0.9.0)

L9 keeps registry keys in the OS keyring under service `config.KEYRING_SERVICE` (`leadforge`), entry `registry.<name>`, and reads
them with `config._keyring_get(name)`; `tests/conftest.py` replaces that function with a fake for every test.
- `keys_list`, and the status `key_save`/`key_remove` answer, read through L9's `config._keyring_get`: the window shows exactly what
  the engine will read. `key_save` writes and `key_remove` deletes through the `keyring` package's `set_password`/`delete_password`
  under `config.KEYRING_SERVICE`, entry `registry.<name>` (`keys.default_backend()`; tests replace it with a fake).
- The "L9 is not in this build" answer and `keys.l9_service` are gone; `make_keys()` cannot fail for that reason any more.
- Without the `keyring` package (L9's optional extra, not in `requirements.lock`): `environment` (exit 3, "something on this
  computer is missing"), `next` naming the extra. A backend that raises while saving or removing: `keyring`, the details only the
  exception's type name (never its text: a backend may quote the value).
- L9's switch `registry.keyring: false` is not read by the key commands: it decides whether the engine READS the keyring; the
  window's key screen manages the store either way. (Decision of this run.)
- Tests: a fake backend that writes into conftest's fake store, never the real keyring: key_save stores (and `config._keyring_get`
  then returns it, so the engine reads what the window saved), keys_list says set, key_remove removes, a planted value appears in
  no output and no log. All 21 commands are then done.

## 11: a stop between page fetches (CONTAINED: built)

Must hold: `util.check_stop()` is called before every page fetch of one site (`SiteCrawler.crawl`: before the home page and before
each further page) and before each page's people extraction and each rendered page (`enrich/runner._process_one`), so a stop is
seen within one fetch, one extraction or one render; `RunStopped` raised in a pool worker is re-raised, not recorded as a failed
site, at both `except Exception` sites (`_run_overlapped._crawl_driver`, `_crawl_stage`), and the work not started is cancelled
(`pool.shutdown(cancel_futures=True)`). The command line never sets the stop file, so `run` and the fake campaign behave as
before (the fake campaign's saved result is the CI job's check). Test: a loopback site whose further pages each take 2 s; the stop
flag is written when the first further page is asked for; `run_enrich` (both the overlapped `all` path and `site`) raises
`RunStopped` within 4 s of the stop, and the business is not recorded as failed.

## 12: people_list search (measured first)

Must hold: measure on the generated 10,000-business workspace (the generator of run `l11a-match`, copied to
`D:\homelab-work\l11a-final\measure\people_measure.py`), each call its own engine process as the core starts it. Change the query
or add an index only if the 13 s is there; an index only through the existing create-if-missing DDL and only without a schema
version change.

## The 21 commands, final keys (P = present, never null; N = present, may be null; A = absent)

| # | Command | Arguments (stdin) | Result keys |
|---|---|---|---|
| 1 | campaign_create | `draft` {kinds, places, country, source, offer, sicCodes, maxLeads} | CampaignPlan: campaign, searches, estimatedBusinesses, estimatedSites, estimatedMinutes, warnings, retentionMonths (all P) |
| 2 | run_start | `args` {campaign, resume} | line 1 RunHandle {runId P}; then RunEvent lines; the end event's `status` is a RunStatus (row 4) |
| 3 | run_stop | `runId` | RunStatus (row 4) |
| 4 | run_status | `runId` (text or null) | RunStatus or null: runId P, campaign N, state P, stage P, done N, total N, etaSeconds N, counts {businesses P, contacts P, purged N, expiringIn30Days N}, startedAt P, reason N |
| 5 | campaigns_list | none | Campaign[]: runId P, name N, kinds P, places P, source N, state P, stage P, startedAt P, keptUntil N, businesses P, withEmail P, withPhone P, tiers {a, b, c} P, sheet N |
| 6 | sheet_export | `runId` | Sheet: runId, writtenAt, leads, tabs [{name, rows}], files [{kind, path}], highlights (all P) |
| 7 | sheet_open | `path` | null |
| 8 | people_list | `query` {search, limit} | PeoplePage: people P, total P, matching P; Person: id, name, role, business, domain P; email N, phone N, source N, foundAt N, campaign N; suppressed P |
| 9 | person_forget | `value`, `dry_run` (optional) | ForgetResult: kind, value, rows, filesRemoved, filesEdited, warnings (all P) |
| 10 | address_suppress | `value`, `kind` (text or null) | SuppressResult: kind, value, suppressed (all P) |
| 11 | purge_report | none | PurgeReport: state, months, total, expired, expiringIn30Days, deleted, armed, suppressed (all P) |
| 12 | purge_apply | none | PurgeReport (as 11) |
| 13 | purge_everything | `confirm` (true) | PurgeEverythingResult: filesRemoved P |
| 14 | retention_get | none | Retention: months, min, max (all P) |
| 15 | retention_set | `months` | Retention (as 14) |
| 16 | keys_list | none | KeyStatus[]: name P, saved P, savedAt N (always null) |
| 17 | key_save | `name`, `value` | KeyStatus (as 16) |
| 18 | key_remove | `name` | KeyStatus (as 16) |
| 19 | settings_get | none | Settings: workspace, sheetFormats, openSheetWhenDone, sources (all P); theme A, accent A |
| 20 | settings_set | `patch` {sheetFormats, openSheetWhenDone} (each optional) | Settings (as 19) |
| 21 | about | none | About: engineVersion, licence, licences [{name, version, licence, notice}] (all P); windowVersion A |

Every error: `{kind, message, details, next}`, `kind` one of the seven of `engine.ts` `ErrorKind`.

## Built in Build 3 (commit `e217650`), and the diff read against "What must hold"

| Item | State | Where | Proof (test, seen red first unless said) |
|---|---|---|---|
| 1, 13 run_start | as built before, unchanged | `window/run.py` | `test_run_start_streams_events_and_finishes`, `test_a_start_refused_before_a_run_exists_is_one_error_document` (green before and after: nothing changed) |
| 2 offer required | built | `commands.campaign_create` | `test_campaign_create_refuses_..._source[change0-offer]`, `[change1-offer]`, `[no offer-offer]`; `test_campaign_create_keeps_the_offer_and_makes_a_companies_house_campaign` |
| 3 sicCodes, source refusal, `sources` | built | `commands.campaign_create`, `workspace_sources`, `settings_get` | `[change3-sicCodes]`, `[change4-sicCodes]`, `[change5-source]`; `test_settings_carry_the_configured_sources_and_not_the_windows_own` |
| 4 not_available -> missing | built: the case is gone with L9 in | `window/keys.py`, `commands._keys` | `test_key_commands_without_the_keyring_package_answer_environment`; `test_the_error_kinds_are_the_seven_the_screens_know` |
| 5, 14, 6, 7 nullable | as built before (nullable, present) | | `test_command_golden_and_shape[*]`, `TYPES` in `tests/test_window.py` |
| 8 theme, accent absent | built | `commands.settings_get`, `settings_set` | `test_command_golden_and_shape[settings_get]`, `[settings_set]`; `test_settings_carry_...` |
| 9 windowVersion absent | built | `commands.about` | `test_command_golden_and_shape[about]` |
| 10 people_list | as built before | | `test_command_golden_and_shape[people_list]` |
| After L7 | built | `commands.people_list`, `_evidence_of` | `test_people_list_says_where_and_when_from_c12`; `scripts/e2e_window_run.py` "every person found by this run has source and foundAt" |
| After L9 | built | `window/keys.py`, `commands._keys`, `_in_keyring` | `test_key_commands_keep_the_key_where_l9_reads_it` (green on the old adapter too, so a break round: below), `test_a_planted_key_appears_in_no_output_and_no_log` |
| 11 stop between page fetches | built (contained: 7 lines in `enrich/`) | `enrich/crawler.py` `crawl`, `enrich/runner.py` `_process_one`, `_run_overlapped`, `_crawl_stage` | `tests/test_l11a_stop_between_pages.py` `[all]`, `[site]` |
| 12 people_list search | measured, no change needed | | numbers below |

All 21 commands are done: the three key commands run on L9's keyring functions.

Goldens changed, each for the reason named (nothing else moved in them; `git diff` read line by line):
- `tests/golden/window/about.json`: `windowVersion` gone (decision 9).
- `tests/golden/window/settings_get.json`, `settings_set.json`: `theme` and `accent` gone (decision 8), `sources: ["dvsa"]` added (decision 3).
- `tests/golden/window/campaign_create.json`: (a) L9's intake warning names the environment variable and the keyring instead of
  `config set` (predicted in "After L9 is in" item 5); (b) `estimatedBusinesses` 120 -> 0, `estimatedSites` 77 -> 0,
  `estimatedMinutes` 5 -> 0: the test workspace now enables `dvsa` (decision 3: a campaign must be for a configured source; before,
  the tests ran on conftest's made-up text-search provider), and the engine's own `grid.plan_counts` (lines 371-384) estimates 120
  results per text-search query and none for a register query. Seam change (2) 15.

Test-side causes found on the way (written before the fix, no assertion loosened):
- The first green run had `sources: []` everywhere: `tests/conftest.py` sets `LEADFORGE_DISCOVERY__PROVIDERS=[fakelist]` for every
  test, and the environment wins over `leadforge.yaml` (`config.py` line 3: defaults, then the file, then the environment; the
  conftest comment "leadforge.yaml still wins" says the opposite). The `ws` fixture now names `dvsa` in its file and drops that
  variable for the window tests (none of them discovers).
- `[change5-source]` first sent `sicCodes: []` with `companies_house`, so the (right) `sicCodes` refusal came first; the case now
  sends a valid code, so it tests the source refusal alone.
- The first e2e run below failed "every person ... has source and foundAt" for a register's officer: the register writes no
  observation, only person evidence. The rule was extended (After L7, second bullet) and a register officer added to the C12 test,
  seen red with the evidence step removed.

## The upper bound of one business (decision 11), from the code and the config defaults (`config.py`)

Inside one crawl worker (`enrich/runner._process_one`):
- the crawl (`SiteCrawler.crawl`): `crawl.site_budget_s` 45 s is checked before each further page, and the last one may start just
  before it: + `crawl.page_timeout_s` 6 s + its pacing `politeness.delay_s` 2.0 s (+30% jitter, 2.6 s) = **53.6 s**. The robots file
  (client timeout `crawl.timeout_s` 10 s), the home page (10 s) and the sitemap probe (6 s), each paced (3 x 2.6 s), are 33.8 s and
  fall inside the 45 s.
- people extraction: `enrich.ner_timeout_s` 30 s per page (queue wait included), up to `crawl.pages_per_site` 6 pages = **180 s**
  (only with the `ner` extra; the heuristics otherwise take milliseconds).
- the rendered fallback (only with the `browser` extra, and only when the static pages gave no email and no person):
  `enrich.rendered_pages_per_site` 2 x (2.6 s pacing + `enrich.render_timeout_s` 20 s + NER 30 s) = **105.2 s**, plus the wait for the
  render gate (`enrich.browser_concurrency` 4), which no setting bounds.

So one business can take **338.8 s** under the defaults, before render-gate waits; the registry lookup and the email checks
(`validation.dns_timeout_s` 5 s per address) run outside the worker. Not a hard wall clock: httpx applies its timeout per phase
(connect, read, write, pool) and a read timeout per chunk, and follows redirects, each hop paced; a server that answers slowly but
steadily can go past the configured figure. UNPROVEN as a wall clock; it would need a total deadline per fetch.

With the stop checks of this build, a stop waits only for the step in flight in each worker (the workers run side by side, so the
longest one counts): a home page with its robots file 22.6 s, a further page 8.6 s, one page's NER 30 s, one rendered page with its
NER **52.6 s** (+ the render-gate wait). That is inside the window's 90 s under the defaults; the two exceptions are the render-gate
wait and the per-phase httpx timeouts above. Measured: the loopback slow site below 2.02 to 2.03 s from the stop to the end (13.41 s and
11.28 s on the code before); the fake campaign's run 2.27 to 2.56 s from `run_stop`'s answer to the run's end (Build 2: 8.41 s).

## Seam changes proposed (2) (the lead decides; nothing here changes a name or a shape)

15. **A register campaign's plan estimates 0.** `CampaignPlan.estimatedBusinesses`, `estimatedSites`, `estimatedMinutes` are 0 for a
    `dvsa` or `companies_house` campaign: `grid.plan_counts` counts 120 results per text-search query and none per register query.
    The screen would show "0 businesses" for a campaign that will find some. Proposed: the three become `number | null` (null: the
    engine cannot estimate a register), or an engine slice estimates register queries (e.g. from the register file's matching rows).
16. **The keyring switch.** L9's `registry.keyring: false` stops the engine READING the keyring; `keys_list` reads through
    `config._keyring_get`, which does not look at the switch, so with the switch off the screen says "saved" for a key the run will
    not use. Proposed: `keys_list` answers `saved: false` while the switch is off and `key_save` says so in an error (`input`, naming
    `registry.keyring`), or the window offers the switch. Not built (no decision covers it).

## Proof (run `l11a-final`, STRIKERFORCE, Python 3.12 venv from `requirements.lock` + pytest 9.2.0, pytest-timeout 2.4.0, pytest-xdist 3.8.0 and their locked dependencies from `uv.lock`'s hashes)

New and changed tests first run against the code BEFORE this build (only the tests changed; `src/` as at `51c66ca`), lines as printed:

```
FAILED tests/test_window.py::test_command_golden_and_shape[about] - assert ["...
FAILED tests/test_window.py::test_command_golden_and_shape[campaign_create]
FAILED tests/test_window.py::test_command_golden_and_shape[settings_get] - as...
FAILED tests/test_window.py::test_command_golden_and_shape[settings_set] - as...
FAILED tests/test_window.py::test_a_planted_key_appears_in_no_output_and_no_log
FAILED tests/test_window.py::test_key_commands_without_the_keyring_package_answer_environment
FAILED tests/test_window.py::test_each_command_answers_what_the_screens_send[campaign_create]
FAILED tests/test_window.py::test_each_command_answers_what_the_screens_send[settings_get]
FAILED tests/test_window.py::test_each_command_answers_what_the_screens_send[settings_set]
FAILED tests/test_window.py::test_each_command_answers_what_the_screens_send[about]
FAILED tests/test_window.py::test_campaign_create_refuses_a_missing_offer_sic_codes_or_an_unconfigured_source[change0-offer]
FAILED tests/test_window.py::test_campaign_create_refuses_a_missing_offer_sic_codes_or_an_unconfigured_source[change1-offer]
FAILED tests/test_window.py::test_campaign_create_refuses_a_missing_offer_sic_codes_or_an_unconfigured_source[no offer-offer]
FAILED tests/test_window.py::test_campaign_create_refuses_a_missing_offer_sic_codes_or_an_unconfigured_source[change3-sicCodes]
FAILED tests/test_window.py::test_campaign_create_refuses_a_missing_offer_sic_codes_or_an_unconfigured_source[change4-sicCodes]
FAILED tests/test_window.py::test_campaign_create_refuses_a_missing_offer_sic_codes_or_an_unconfigured_source[change5-source]
FAILED tests/test_window.py::test_campaign_create_keeps_the_offer_and_makes_a_companies_house_campaign
FAILED tests/test_window.py::test_settings_carry_the_configured_sources_and_not_the_windows_own
FAILED tests/test_window.py::test_people_list_says_where_and_when_from_c12 - ...
FAILED tests/test_l11a_stop_between_pages.py::test_a_stop_during_a_slow_site_ends_the_enrich_within_seconds[all]
FAILED tests/test_l11a_stop_between_pages.py::test_a_stop_during_a_slow_site_ends_the_enrich_within_seconds[site]
21 failed, 57 passed in 44.13s
```

with, from the same run: `stage all: the stop to the end of enrich: 13.41 s (one further page takes 2.0 s, the site 5 of them)` and
`stage site: the stop to the end of enrich: 11.28 s (...)`; the planted-key test's line
`E   AssertionError: assert (1 == 1 and 'failed' == 'keyring'`. The two test-side fixes above came after this run; the run on the
old code was NOT repeated after them. Green on the old code: `test_key_commands_keep_the_key_where_l9_reads_it` (the old adapter
read and wrote through the same fake). Its break round: `keys.entry` made to answer `registry-<name>`, the test run, the file
restored byte for byte:

```
D:\homelab-work\l11a-final\leadforge-next\tests\test_window.py:418: AssertionError: assert (0 == 0 and {'name': 'com...avedAt': None} == {'name': 'com...avedAt': None}
FAILED tests/test_window.py::test_key_commands_keep_the_key_where_l9_reads_it
```

The register case of the C12 test, with `or _evidence_of(evidence, r)` taken out of `people_list`, then put back:

```
D:\homelab-work\l11a-final\leadforge-next\tests\test_window.py:791: AssertionError: assert (None, None) == ('https://reg...01T09:12:00Z')
FAILED tests/test_window.py::test_people_list_says_where_and_when_from_c12 - ...
```

`python -m pytest tests/test_window.py tests/test_l11a_stop_between_pages.py -p no:cacheprovider -s` on the new code:

```
..................................................................run_stop answered to the run's end: 0.00 s; run_stop
started to the run's end: 0.78 s
..........stage all: the stop to the end of enrich: 2.03 s (one further page takes 2.0 s, the site 5 of them)
.stage site: the stop to the end of enrich: 2.02 s (one further page takes 2.0 s, the site 5 of them)
78 passed in 21.75s
```

(the C12 test gained its register case after this run; it passed alone, above, and the full gate below covers all.)

`python scripts/e2e_window_run.py --out <folder>` (the real `run_start`/`run_stop`/`run_status` processes on the fake campaign's
loopback world, every outside connection refused). First run, before the register rule (lines cut at 220 characters by the reader):

```
FAIL  every person found by this run has source and foundAt  [["Odell Prewitt", "http://kestrel-garage.example:18765/team", "2026-11-12T10:38:47Z"], ["Ysolde Fenwick", "http://millbrook-autos.example:18765/contact", "2026-11-12T10:38:47Z"], ["Hamish Larkspur", "http://northgate-tyres.example:18765/team", "2026-11-12T10:38:47Z"], ["Ottoline Fenn", null, null],
E2E WINDOW RUN FAIL
```

Last run (`people_list` asked for all people, `limit` 500):

```
  run_stop answered to the run's end: 2.50 s
  longest wait between two stream lines (two checks of the stop flag): 2.38 s
  longest wait between two stream lines (two checks of the stop flag): 4.27 s
PASS  first run ends stopped  exit 0, last {"type": "stopped", "status": {"runId": "run_20261112_10405_2000", "campaign": "bristol-garages-fixture", "state": "stopped", "stage": "enrich", "done": 1, "total": 8, "etaSecon
PASS  run_status says stopped, stage kept  {"runId":"run_20261112_10405_2000","campaign":"bristol-garages-fixture","state":"stopped","stage":"enrich","done":1,"total":8,"etaSeconds":null,"counts":{"businesses":10,"contac
PASS  no stop flag left
PASS  resumed run ends finished, same run  exit 0, last {"type": "finished", "status": {"runId": "run_20261112_10405_2000", "campaign": "bristol-garages-fixture", "state": "finished", "stage": "export", "done": null, "to
PASS  campaigns_list answers one JSON document  [{"runId":"run_20261112_10405_2000","name":"bristol-garages-fixture","kinds":["car repair"],"places":["Bristol"],"source":null,"state":"finished","stage":"export","startedA
PASS  sheet_export answers one JSON document  {"runId":"run_20261112_10405_2000","writtenAt":"2026-11-12T10:41:17Z","leads":10,"tabs":[{"name":"Leads","rows":10},{"name":"Drafts","rows":5},{"name":"Summary","rows":31},{"
PASS  people_list answers one JSON document  {"people":[{"id":"1","name":"Hamish Larkspur","role":"Director","business":"Northgate Tyres","domain":"northgate-tyres.example","email":null,"phone":null,"source":"http://nort
PASS  every person found by this run has source and foundAt  [["Hamish Larkspur", "http://northgate-tyres.example:18765/team", "2026-11-12T10:41:07Z"], ["Ottoline Fenn", "https://find-and-update.company-information.servi
PASS  no outside attempt beyond the fake campaign's known set  []
E2E WINDOW RUN PASS
8 8 [('Hamish Larkspur', True, True), ('Ottoline Fenn', True, True), ('Barnaby Larkin', True, True), ('Ysolde Fenwick', True, True), ('Odell Prewitt', True, True), ('Corin Ashdown', True, True), ('Tamsin Verrill', True, True), ('Linnet Aldous', True, True)]
```

(the last line: the run folder's `people_list.json` read back: 8 people listed of 8, each with source and foundAt.)

### 12: people_list on 10,000 invented businesses

`people_measure.py out 10000`, each call its own `python -X utf8 -I -m leadforge window people_list` process, below-normal
priority. Before this build (`src/` at `51c66ca`):

```
workspace of 10000 businesses made in 1.1 s
| people_list | `{"query": {"search": "", "limit": 500}}` | 0 | 150,187 B | 0.92 s | people 500, matching 10000, total 10000 |
| people_list | `{"query": {"search": "priya", "limit": 50}}` | 0 | 15,048 B | 0.84 s | people 50, matching 1000, total 10000 |
| people_list | `{"query": {"search": "", "limit": 500}}` | 0 | 150,187 B | 0.97 s | people 500, matching 10000, total 10000 |
| people_list | `{"query": {"search": "priya", "limit": 50}}` | 0 | 15,048 B | 0.95 s | people 50, matching 1000, total 10000 |
```

After (`e217650`, one more read of `evidence` and of the `person.name` observations):

```
| people_list | `{"query": {"search": "", "limit": 500}}` | 0 | 150,187 B | 1.26 s | people 500, matching 10000, total 10000 |
| people_list | `{"query": {"search": "priya", "limit": 50}}` | 0 | 15,048 B | 1.05 s | people 50, matching 1000, total 10000 |
| people_list | `{"query": {"search": "", "limit": 500}}` | 0 | 150,187 B | 1.91 s | people 500, matching 10000, total 10000 |
| people_list | `{"query": {"search": "priya", "limit": 50}}` | 0 | 15,048 B | 1.14 s | people 50, matching 1000, total 10000 |
```

The 13 s of Build 2 did not come back on the same generated workspace: the search took 0.84 to 0.95 s before and 1.05 to 1.14 s
after; the search and the plain page do the same work (every person is read, then filtered), so a 13-fold gap between them is not
in the code. No index and no query change was made. Its cause is UNPROVEN; two candidates, neither tested: the laptop's load during
Build 2's run, or `db.readonly_view` copying a database whose WAL holds data (the generated workspace has none). The time still grows
with the workspace (all people are read); beyond 10,000 it is UNPROVEN.

## Decisions taken in this run (Build 3)

- No helper agents (the brief: "You work alone"); the owner's rule of 14:35 asks for a second reader of the diff: that is the
  independent reader who follows this run.
- Without the `keyring` package the key commands answer `environment` (exit 3: "something on this computer is missing"), not
  `keyring` (which `engine.ts` reserves for "could not reach the Windows keyring") and not `missing` (the command exists). A backend
  that raises while saving or removing answers `keyring`, with the exception's type name only.
- `keys_list` reads through L9's `config._keyring_get` (the engine's own read), not through the backend's `get_password`.
- L9's `registry.keyring` switch is not read by the key commands (seam change 16).
- `campaign_create` checks the draft's own fields first and the workspace's sources after (the second needs `leadforge.yaml`); a
  draft wrong in both is told the field problems first.
- A person with no observation takes the newest person evidence of their own page (a site page's row only when it names them);
  every officer of one register page gets that page and the time it was read.
- `sicCodes` is ignored, whatever it holds, for any source but `companies_house` (the decision's "ignored otherwise").
- An existing `leadforge_data/window-settings.json` (written by Build 2) is left in place and no longer read.
- `scripts/e2e_window_run.py` now lists all people (`limit` 500, was 5) and checks each has source and foundAt.
- Lint with ruff 0.15.13 (already on this laptop), as Builds 1 and 2: `ruff check src tests` passes; `ruff check scripts` reports
  one B905 in `scripts/e2e_compare.py`, a file this branch does not touch (the same with this build's changes set aside).
  `check.mjs` runs `python -m ruff` from the venv, so ruff 0.15.13 (PyPI, 2026-05-14) was installed into the run's venv pinned to
  PyPI's sha256 of its Windows wheel; `uv.lock`'s ruff 0.17.4 (uploaded 2026-11-05 18:51 UTC) was 6 days 16 hours old: refused by
  the 7-day rule.

## Gate and hosted CI (Build 3)

`node check.mjs` on `fb354ff` (the venv's Scripts first on PATH, below-normal priority). Three attempts, said plainly:
1. Stopped at lint after 8 s: ruff was not yet in the venv (`No module named ruff`, `CHECK FAIL sha=fb354ff tree=clean steps=4`).
   No test ran.
2. Stopped from outside by this run's own tool limit (10 minutes, too short for this loaded laptop) during the tests, at
   `[ 82%]`, every test until then passing (2 skipped). No result line.
3. The run that counts:

```
ok  versions agree  0.4
ok  skill frontmatter  0.3
ok  skill references  0.3
All checks passed!
ok  lint  0.3
+++++++++++++++++++++++++++++++++++ Timeout +++++++++++++++++++++++++++++++++++
  File "D:\homelab-work\l11a-final\leadforge-next\tests\test_draft_cli.py", line 325, in test_worked_example_registry_matched_ltd_with_own_domain_email
FAIL  tests  347.9
CHECK FAIL sha=fb354ff tree=clean steps=5 skipped=0 secs=352
```

**The local gate is RED: CHECK FAIL, by a timeout.** pytest-timeout (60 s per test, `pyproject.toml` line 68) stopped the whole
pytest process inside `tests/test_draft_cli.py::test_worked_example_registry_matched_ltd_with_own_domain_email`, while its child
`python -m leadforge draft render` ran; so no summary line was printed and the tests after it did not run in this attempt. Cause, by
reading: the test drives `draft render`, which this branch does not change (`git diff origin/master --stat` touches no draft code);
the laptop's processor read 100% load at the time (other sessions' processes). Re-run once alone, at normal priority:

```
.                                                                        [100%]
1 passed in 9.09s
```

The full gate was not run a fourth time (one per run). Locally the whole suite is therefore NOT proven on `fb354ff`: attempt 2
passed its first 82%, attempt 3 stopped at the timeout, and the tail after 82% did not run locally. The full suite's verdict is
hosted CI's, below. `tests/test_window.py` and `tests/test_l11a_stop_between_pages.py` ran on their own (78 passed, above) and the C12
test alone after its last change.

Hosted CI, run 43203210807 on `fb354ff` (pull request 14), read with `gh run view`: 13 jobs, 13 success, none pending (`gh pr checks
14`: 13 checks):

```
claude plugin validate  success
fake campaign · ubuntu-latest  success
Validate plugin manifests  success
windows-latest · py3.14  success
ubuntu-latest · py3.12  success
Version strings agree  success
windows-latest · py3.11  success
fake campaign · windows-latest  success
windows-latest · py3.12  success
ubuntu-latest · py3.14  success
ubuntu-latest · py3.13  success
windows-latest · py3.13  success
ubuntu-latest · py3.11  success
```

The two fake-campaign jobs compare the fake campaign's run with its saved result: unchanged by the stop checks.

The commit that adds this section has its own run; its result is in the pull request comment and the run report.
