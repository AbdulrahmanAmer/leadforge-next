# L11a The engine's commands for the window

Started from `origin/slice/L6-the-delete-side` at `b15ef7a3e86156d63028166f1d5f67501e9a168c` (pull request 6 was still open on
2026-11-12 09:45, run `l11a-build`). The window's side (`app/`) is not on this branch and nothing under it is edited here.

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

## Gaps and seam changes proposed

(filled in below as the build finds them)

## After L9 is in

(filled in below)

## Plan and code disagree

(filled in below)
