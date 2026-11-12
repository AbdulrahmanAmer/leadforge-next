# The window: every action and the engine command behind it

One page for slices L10 and L11. The window (`app/ui`) never opens the database, a file or the network. Each
action is one method of the `Engine` interface in `app/ui/src/engine.ts`; inside the shell that method is one
Tauri `invoke`; the shell (`app/src-tauri`) runs the engine command in the workspace folder with `--json` and
reads its one `LF_DIGEST {json}` line (`ok`, `cmd`, `run`, `counts`, `warnings`, `artifacts`, `next`) and its exit
code. The window has no send or outreach action, and the shell must expose none (C14).

Checked against `src/leadforge/cli.py` at `origin/master` 1050687 ("master") and, for forget, purge and retention,
at `origin/slice/L6-the-delete-side` ("L6", not merged yet: its line numbers will move).

## Actions

| # | Action in the window | Tauri command | Engine command and arguments | Function, line | The digest returns | While it runs | When it fails |
|---|---|---|---|---|---|---|---|
| 1 | New campaign: check the plan (the form also has the offer, the SIC codes for Companies House, and only the registers `settings_get` lists) | `campaign_create` | the shell writes `answers.yaml` from the form, then `intake --answers answers.yaml --out icp.yaml`, then `plan --icp icp.yaml` | `intake` master:85, `plan` master:111 | intake: `counts.errors`, `counts.categories`, `artifacts[icp.yaml]`; plan: `counts.queries`, `est_max_results`, `est_enrich_sites`, `est_total_min`, `warnings` | the plan card shows placeholder lines, the button reads "Checking the plan" | exit 4: each warning is one problem; the form marks the field it names and the card lists the rest |
| 2 | Run, with live progress | `run_start` (+ channel) | `run --icp icp.yaml` (`--resume` to continue); kept in the foreground by the shell, so stdout carries `LF_PROGRESS {"stage","done","total","msg","ts"}` lines (`util.emit_progress`, util.py:346) and then the digest | `run` master:465 (L6:465, which first calls `_start_of_run_purge` L6:542) | `run`, `counts.stage` and the pipeline counts; on L6 also `counts.purged`, `counts.expiring_30d` | the Run screen: six stages, the current one with its count, bar and last message; time left for the stage; the clean-up notice | exit 3, 4 or 5: the stage it stopped in is marked, the warning is shown, "Continue the run" resumes. Exit 4 with "more than half" (L6:554): the retention stop, shown with its own text |
| 3 | Stop the run | `run_stop` | none: see "Missing" 1. The shell ends the engine process it started; the run stays resumable (`run --resume`) | n/a | the shell answers with a last `status` | the button reads "Stopping" | the error is shown above the stages; the run goes on |
| 4 | Is a run going | `run_status` | `status` or `status --run <id>` | `status` master:571 | `run`, `counts.stage`, `businesses`, `alive`, `progress_stage`, `progress_done`, `progress_total`, `eta_seconds` | nothing (asked once when the window opens) | the Run screen says nothing is running |
| 5 | Open the results | `campaigns_list` | none that lists runs: see "Missing" 2. Today only the latest run: `status` | `status` master:571 | one run | placeholder rows | a banner with the engine's warning and "Try again" |
| 6 | The sheet: write it | `sheet_export` | `export --icp icp.yaml` (`--format xlsx,csv` from Settings) | `export` master:392 | `counts` (`summarize_for_digest`), `artifacts` (the xlsx, csv and `report.json` paths), `warnings` (the top hooks) | the button reads "Writing" | exit 4 "no run found": banner in the card |
| 7 | The sheet: open it | `sheet_open` | none. The shell opens the artifact path from row 6 in the program Windows uses, and only if it lies in the workspace's `exports` folder. (`export` opens it itself when `export.auto_open` is true, master:415.) | n/a | nothing | the button is busy | banner in the card |
| 8 | People: list and search | `people_list` | the engine's named people only, with an email or phone only where recorded as that person's: see "Missing" 3 | n/a | n/a | placeholder rows | banner with "Try again" |
| 9 | Forget a person | `person_forget` | `forget <email, domain or name>` | `forget` L6:573 | `counts.kind`, `rows`, `files_removed`, `files_edited`; `artifacts`; the warning "sheets already handed out cannot be reached" | the confirmation stays open, its button reads "Deleting" | exit 4 (`InputError`: an empty value, a half-upgraded workspace), "nothing was changed": shown inside the confirmation, which stays open |
| 10 | Suppress an address | `address_suppress` | `suppress add <value>` (`--kind email` or `domain`) | `suppress` master:596 | `counts.suppressed` (the size of the list) | the confirmation's button reads "Adding" | exit 2 (empty value, unknown kind): shown inside the confirmation |
| 11 | Purge: the report | `purge_report` | `purge` | `purge` L6:595 | `counts.state` (`report`, `armed`, `no_workspace`), `expired`, `expiring_30d`, `total` | placeholder lines in "The next clean-up" | exit 4 (a half-upgraded workspace): banner with "Try again"; nothing was changed |
| 12 | Purge: delete what is past the limit | `purge_apply` | `purge --apply` | `purge` L6:595 | `counts.state` (`purged` or `armed`), `deleted`, `expired`, `expiring_30d`, `total` | the confirmation's button reads "Deleting" | shown inside the confirmation; nothing was deleted |
| 13 | Purge: delete everything | `purge_everything` | `purge --everything --yes` (without `--yes` the engine refuses, exit 2, L6:604) | `purge` L6:595 | `counts.files_removed`, `everything: true` | the confirmation's button reads "Deleting" | shown inside the confirmation |
| 14 | The retention setting: read | `retention_get` | `config get retention.months` | `config_cmd` master:655 | nothing in the digest: see "Missing" 5 | placeholder lines | banner in the card |
| 15 | The retention setting: change | `retention_set` | `config set retention.months <1 to 12>` | `config_cmd` master:655; the limit is `RetentionCfg.months`, `ge=1, le=12`, config.py L6:282 | `counts.set = 1` | the button is busy | exit 2 "invalid value for retention.months": banner in the card, the old value stays |
| 16 | Keys: which are saved | `keys_list` | none. The shell asks the Windows keyring | n/a | per key: saved or not, and since when. Never the value | placeholder lines | "The Windows keyring did not answer" |
| 17 | Keys: save | `key_save` | none yet: see "Missing" 6. The shell stores the value in the Windows keyring | n/a | the same status as row 16. The value is not returned and no command reads it back | the button reads "Saving"; the field is emptied either way | banner in the key's card |
| 18 | Keys: remove | `key_remove` | none. The shell deletes the keyring entry | n/a | the status | the button is busy | banner in the key's card |
| 19 | Settings: read | `settings_get` | sheet formats and "open when done" are `config get export.formats` and `config get export.auto_open`; `sources` is the registers the workspace is configured for; theme and accent are not here: the window keeps them (`prefs.ts`) | `config_cmd` master:655 | nothing in the digest: see "Missing" 5 | placeholder lines; the window uses its defaults | banner in the card; the defaults stay |
| 20 | Settings: change | `settings_set` | `config set export.formats <list>`, `config set export.auto_open <bool>`; a patch never carries theme or accent | `config_cmd` master:655 | `counts.set = 1` | the control moves at once | banner in the card |
| 21 | About and licences | `about` | `version` for the engine and the bundled notices file (C15); the window's own version is a build-time constant, not part of the answer | `version` master:883 | nothing in the digest: see "Missing" 7 | placeholder lines | banner with "Try again" |

Exit codes the shell maps to the window's error kinds: 1 `failed`, 2 `usage`, 3 `environment` (`EnvError`), 4
`input` (`InputError`), 5 `source` (`ProviderFailed`) (util.py:25 to 38); a keyring fault is `keyring`; a row marked
"Missing" answers `missing` until the engine has the command.

Two things `run` does by itself today, which the shell has to settle before row 2 is true:
- **It pops a console window.** Started without a terminal, `run` opens its own progress console on Windows
  (`_progress_ui`, pipeline.py:47 to 57, when `progress_window` is true, the default, config.py:285). The window replaces
  that console (ADOPT 3, "may go"), so until L11 removes it the shell runs with `config set progress_window false`.
- **It opens the sheet.** At the end of the export stage `run` opens the xlsx in the program Windows uses when
  `export.auto_open` is true (pipeline.py:550 to 553). That is the "Open the sheet when a run finishes" switch in Settings,
  so the engine, not the window, does the opening after a run.

## The seam's contract (decisions of 2026-11-12, final)

The real commands are `leadforge window <name>`: the arguments as one JSON document on stdin, one JSON document on stdout and
exit 0, or a non-zero exit and `{"kind","message","details":[...],"next":null|string}`; logs on stderr only. The types are
`app/ui/src/engine.ts`; `engine.mock.ts` and the stand-in answer in exactly those shapes (`app/ui/tests/seam-shape.test.mjs`).

- **Shape rule.** A field that left a type is ABSENT from the JSON. A nullable field is PRESENT with `null`. Every other field is
  present and not null. `seam-shape.test.mjs` reads the field lists out of `engine.ts` and holds the mock and the stand-in to it.
- **`run_start` (the stream).** stdout line 1 is the `RunHandle` `{"runId": "..."}`; then one `RunEvent` per line (`progress`,
  `stage-done`, `notice`); the last line is exactly one of `finished`, `stopped` or `failed`, each carrying the run's `RunStatus`
  (`failed` also carries `error: {kind, message, details}`). A run that ends without one of the three is an engine fault.
  The core holds the engine to these rules (`engine::run_stream`, `engine::after_stop`; tests `tests/run_seam.rs`):
  1. **Line 1 is the handle only if** it is a JSON object with a non-empty string `runId`; it goes back as the command's answer,
     untouched. **A JSON object with `kind` on line 1 is a refused start** (no such campaign, a clean-up refusing): the core gives
     the process 5 s to end (then ends it) and rejects `run_start` with that document, untouched; nothing is sent on the channel.
     **Anything else on line 1** (not JSON, blank, over 64 KiB, the end of the stream) rejects with the core's own error
     `{"kind":"failed","message":"The engine did not start the run: ...","details":[],"next":null}`, also once the process has
     ended; a handle on a later line is not taken. The Run screen shows its "start refused" state (the message, "Try again").
  2. **A stream that ends without an end event** (the engine died, the core ended it, its last line was over the cap, the time
     limit): the core sends exactly ONE message of its own on the channel, after the last relayed line and never after an engine
     end event: `{"type": "stream-closed", "exitCode": number|null, "reason": "exit"|"ended-by-core"|"line-too-long"|"timeout"}`.
     It is the shell's message, not an engine event (`StreamClosed` in `engine.ts`). `exitCode` is null when the core ended the
     process. `line-too-long`: the process exited by itself and its last non-blank line was over 64 KiB (not relayed). On
     `stream-closed` with no end event seen, the Run screen calls `runStatus(runId)` once and shows what the engine says; if that
     call fails or still says `running`, it shows a failed run: "The engine stopped without saying why." and "Continue the run".
  3. **The wait after a stop.** After a `run_stop` that answered ok, the run gets **90 s** (`engine::STOP_WAIT`) to write its end
     event; then the core ends it (and rule 2 sends `stream-closed`, reason `ended-by-core`). `run_stop` answers at once; the Run
     screen shows "Stopping the run" until the end event or `stream-closed`. A `run_stop` that was refused sets no wait. Closing
     the window still ends every engine at once.
  4. **Time limits** (`EngineCommand::timeout`, pinned per command by `timeouts_are_pinned_per_command`): 12 h `run_start`; 30 s
     `run_stop`, `run_status`, `about`; 600 s `sheet_export`, `purge_report`, `purge_apply`, `purge_everything`,
     `person_forget`; 120 s every other command.
- **What the engine must do for these rules.** Refuse a start by writing its error document as line 1 and exiting non-zero
  (never a handle first and then a refusal). Check the stop flag at least once per business and write `stopped` within 90 s of
  `run_stop`'s answer. After its process was ended from outside, answer `run_status` for that run with `failed` (a status, not
  `running`). Keep every line, the end event included, under 64 KiB.
- **The stand-in's test cases** (`test-resources/standin/leadforge_window_standin.py`, `CASES`), each chosen by a made-up campaign
  name that starts with it: `standin-refuse` (error document as line 1, exit 4), `standin-garbled` (plain text as line 1, then a
  handle that must not count, exit 1), `standin-dies` (handle, a notice, four progress lines, exit 3, no end event),
  `standin-slow-stop` (about 15 s of progress after a stop, then `stopped`), `standin-ignores-stop` (never obeys a stop; ends by
  itself only after 10 minutes), `standin-long-line` (the end event over the 64 KiB cap, exit 0). The window's plan names a
  campaign `<place>-<kind>s`, so the place "Standin refuse" gives `standin-refuse-mot-garages` (the self-test does that).
- **`CampaignDraft`** gains `offer: string` (required: what the user offers these businesses, one or two lines) and
  `sicCodes: string[]` (asked for only when `source` is `companies_house`; `[]` otherwise). Three refusals, all kind `input`, each
  with a `details` line that starts with the field's name and a colon, which the form shows on that field:
  `offer: ...` for an empty offer; `sicCodes: ...` for `companies_house` with no code; `source: ...` for a register that
  `settings_get` does not list, with `next` naming the configured one.
- **`Settings`** is `{workspace, sheetFormats, openSheetWhenDone, sources}`. `sources: SourceId[]` is the registers this workspace is
  configured for; the form offers those and no others. `theme` and `accent` are not in `Settings` or `SettingsPatch`; the window
  keeps them itself (`app/ui/src/prefs.ts`) and `settings_get` / `settings_set` never carry them. The Rust core merges nothing.
- **`About`** is `{engineVersion, licence, licences}`. The window's own version is the build-time constant from
  `app/src-tauri/Cargo.toml` (`app/ui/window-version.mjs`, written by `vite.config.ts`).
- **`people_list`** returns the engine's named people, with an email or phone only where it was recorded as that person's.
  Forget and suppress act on any address or domain, listed or not.
- **No new error kind.** A key command the engine cannot do yet answers `missing`; the Keys screen shows it in words about keys.
- **Nullable:** `RunStatus.campaign`, `RunStatus.done`, `RunCounts.purged`, `RunCounts.expiringIn30Days`; `Campaign.name`,
  `Campaign.source`, `Campaign.keptUntil`; `Person.source`, `Person.foundAt`, `Person.campaign`. What each null shows is the table
  in `docs/slices/L11-window.md`, "Seam decisions of 2026-11-12".

## Tauri commands (for the shell's author)

Types are those of `app/ui/src/engine.ts`. Every command rejects with `{ kind, message, details: string[], next: string | null }`.

| Command | Arguments | Result |
|---|---|---|
| `campaign_create` | `draft: CampaignDraft` | `CampaignPlan` |
| `run_start` | `args: RunArgs`, `events: Channel<RunEvent \| StreamClosed>` | `RunHandle` (the engine's stdout line 1 when it is a handle; the events are the lines after it, the last one `finished`, `stopped` or `failed`, or the core's one `stream-closed`) |
| `run_stop` | `runId: string` | `RunStatus` |
| `run_status` | `runId: string \| null` | `RunStatus \| null` |
| `campaigns_list` | none | `Campaign[]` |
| `sheet_export` | `runId: string` | `Sheet` |
| `sheet_open` | `path: string` | nothing |
| `people_list` | `query: PeopleQuery` | `PeoplePage` |
| `person_forget` | `value: string` | `ForgetResult` |
| `address_suppress` | `value: string`, `kind: "email" \| "domain" \| null` | `SuppressResult` |
| `purge_report` | none | `PurgeReport` |
| `purge_apply` | none | `PurgeReport` |
| `purge_everything` | `confirm: true` | `PurgeEverythingResult` |
| `retention_get` | none | `Retention` |
| `retention_set` | `months: number` | `Retention` |
| `keys_list` | none | `KeyStatus[]` |
| `key_save` | `name: KeyName`, `value: string` | `KeyStatus` |
| `key_remove` | `name: KeyName` | `KeyStatus` |
| `settings_get` | none | `Settings` |
| `settings_set` | `patch: SettingsPatch` | `Settings` |
| `about` | none | `About` |

The window needs no other permission: no file system, no shell or program start, no HTTP, no opener, no dialog
from the page. `dist/index.html` carries the policy it was rendered under (`vite.config.ts`):
`default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src ipc: http://ipc.localhost`.

## Missing in the engine

Said plainly; the window does not pretend. Until each exists, its command answers `missing` and the screen shows that.

1. **No stop command.** The shell must end the process it started; `run --resume` continues. Nothing in `cli.py` cancels a run.
2. **No command lists the runs of a workspace.** `status` (master:571) gives the latest run, or one by id. And `export` (master:392)
   always writes the latest run: it has no `--run`. So Results can be true for one campaign only.
3. **No command returns contacts** (name, role, address, phone, source page, date found), with or without a search. The People
   list has nothing to read. `export` writes them to files only, and the window reads no files.
4. **`forget` has no report-first mode**, and `purge` reports counts but not which businesses. The forget confirmation therefore
   names the kinds of things deleted (from the command's own description, L6:574), not a count.
5. **`config get` puts no value in the digest** (master:699 to 700: the value goes to the human line, which `--json` suppresses),
   and an unset key reads as `{}`, not as its default. The shell would have to parse human output to read `retention.months`.
6. **Keys in the Windows keyring** are slice L7. Today a key is a plain value in `leadforge.yaml` (`config set
   registry.companies_house_key`); the engine cannot take a key from the keyring or from the shell without it touching that file.
7. **`version` puts no version in the digest** (master:886: `counts` is empty; the number is in the human line only).
8. **`suppress list` returns only a count under `--json`** (master:620 to 622), and there is no `suppress remove`. The window
   shows the count and offers no way to lift a suppression.
9. **The campaign comes from a file.** No command takes the kind of business and the place as arguments, and none lists the
   sources a workspace can use; the shell writes `answers.yaml` itself. A list of businesses you bring as the starting set has
   no command either (`byol import`, master:251, only matches contacts to businesses already found).
10. **The licence notices file** does not exist yet (C15, L11).
