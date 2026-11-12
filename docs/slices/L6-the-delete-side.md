# L6 The delete side (C4 to C7)

# Spec

Quoted, not reworded. Sources: `L4-ONWARD.md` (the plan) and `LEADFORGE-ADOPTION.md` (ADOPT), as read by run `l6-build` on 2026-11-12.

## The plan's paragraph (L4-ONWARD.md, section 2)

> **L6 The delete side (C4 to C7).** As ADOPT row L3a: the `first_run_id` count first; the schema version read before any write; `forget`,
> `purge` with its three protections, raw scrapes not kept, a suppressed address in no export; the mutation trial result written down. Leaves out:
> the window (L11). Pass lines: ADOPT's C4 to C7 tests (planted person in eight places, byte scan finds nothing); a refused old workspace is
> byte-for-byte unchanged (hash before and after); the first run after the upgrade deletes nothing; G2 still matches. Fakes: injected clock;
> fixture workspaces of invented people. Risk: a purge bug deletes an upgrading user's data with no undo; hence report-only first run and the
> half-workspace stop, each with its own test. Size: 14 h.

## Gate row G2 (L4-ONWARD.md, section 1)

> - G2 Fake campaign [brief; ADOPT section 3]. `python scripts/e2e_fake_campaign.py` on both runners: new campaign file, discovery from the two UK
>   registers and a user list (recorded fixtures of invented data), enrichment against a loopback server of invented `.example` sites, scoring,
>   export of the four tabs, CSV and `report.json`. Every socket to a non-loopback address is refused inside the run; one attempted outside call fails it.
>   The digest and sheet match the goldens.

## ADOPT section 5, rows C4 to C7

| # | Requirement | Today | Task | Test (a planted bad case) | Slice |
|---|---|---|---|---|---|
| C4 | A person can be forgotten | none | `forget <email, domain or name>`: removes them from every table, the cache, the logs, the progress file, the outbox and inbox, the hand-off files (`dm_batch*`, `dm_labels*`), the draft packets and the sheets in the tool's own `exports` folder; adds a suppression row; then cleans the database file so the rows do not stay readable inside it; says plainly that sheets already handed out cannot be reached | a planted person sits in eight places; afterwards a byte scan of the database file, its side files and the data folder finds nothing; a new run does not collect them again | L3a |
| C5 | Data is not kept without limit | a "Stale?" flag only | A business and everything attached to it expires 12 months after the business first entered the workspace. A refresh does not renew. `purge` runs at the start of every `run`, with three protections: the first run after the upgrade only reports; every run prints how many records expire in the next 30 days; an automatic purge never deletes more than half a workspace, it stops and names the explicit command. `purge --everything` deletes the files without opening the database, so it works on a workspace of any age. The user can shorten the period | a 13-month record is gone, an 11-month one stays, a refreshed 13-month one is still gone; the first run after the upgrade deletes nothing; a clock set a year ahead deletes nothing and stops; an old-format workspace is wiped | L3a |
| C6 | Raw scrapes with reviewers' names are not kept | kept for good | Raw scraper output is deleted once parsed (or cut down to business facts, if resuming needs it) | after a fixture run, a file scan finds no reviewer name | L3a |
| C7 | An objection is absolute | address still in the sheet | A suppressed address is absent from every export and every tab | a planted suppressed email is in no output file | L3a |

## ADOPT section 9, row L3a

| Slice | What it does | Proof (each can fail) | Marks | Size |
|---|---|---|---|---|
| **L3a The delete side** (0.8.0) | First step, before any code: does every way of adding a business set `first_run_id`? Count the empty ones on fixtures. (A later merge never changes it: `db.py:362-408`, checked.) If all paths set it: no change to the tables. If not: set it at insert from now on, and treat an empty one as the workspace's first run. A new table, if one is ever needed, is created by the existing create-if-missing script and needs no version change. Then: the version is read before anything is written; C4, C5, C6, C7 | The tests of C4 to C7. An existing workspace still opens after the upgrade. A refused old workspace is byte-for-byte unchanged. Goldens change only where the slice says so, each change listed. The Python mutation trial runs on these modules and its keep-or-cut result is written down. **Undo is not complete:** a revert brings the code back, not records a purge deleted. That is why the first run only reports | guardrail; **owner's word** (it deletes users' data) | about 1,300 lines; 2 days |

## ADOPT section 4, risks 2, 9 and 11

| 1 | **Autopilot.** LeadForge starts the operator's `claude -p` with scraped text in the prompt. Nothing limits its tools. Hooks are switched off for that call, which also switches off the shell guard of the new setup. It runs in the workspace folder and inherits every environment variable; on the other laptop those include two master keys (F12). The prompt says "do not use any tools"; nothing enforces it. Even without bypass mode, a `-p` run may read files in its folder without asking, and `leadforge.yaml` there holds keys in plain text. Whether bypass mode applies to a `-p` run is not clear on the vendor's page: likely, not proven | `agent_runner.py:79-90`, `155-172` (checked) | L2 |

| 9 | **An email opt-out does not hide the address.** The suppression check only feeds the "eligible" label; the row and its address still print | `export.py:310-314` (checked) | L3a |

| 11 | **The schema refuses any other version, and writes before it checks.** A change to the tables locks every existing workspace out, and a workspace the tool cannot open is one it cannot purge. On every open it switches the file to WAL mode and creates missing tables first, and only then reads the version. So even a refused old workspace is written to | `db.py:25`, `149-177` (checked) | L3a, first step |


# Build (0.8.0)

Run `l6-build`, 2026-11-12, one builder, no helpers. Per item: what the change must do, written before the code; the check of the code against that
text by reading, after it. Tests are one per pass line; each was seen failing for the right reason before the line is claimed (the delete commands
also have the "what must stay" test). Clock: every age is computed from a `now` argument (`retention.py`), never from `time.sleep`; the CLI takes
it from one function, `leadforge.util.utcnow()`, which tests patch.

## Item 1 — the `first_run_id` count (before any code)

**Question.** Does every way of adding a business set `first_run_id`?

**Ways of adding a business, read from the code (not from the fixtures).** `INSERT INTO businesses` exists in exactly one place,
`db.upsert_business` (db.py, the `existing is None` branch). It has exactly one production caller, `pipeline._apply_query_result`
(pipeline.py), which feeds it `normalize.to_business(raw, run_id, ...)`; that sets `first_run_id=run_id` (normalize.py). Every provider
(Maps list, the Maps scraper helper, DVSA, Companies House, the user list) reaches the database only through that call. `run_id` there is the id
of a row `db.create_run` wrote into `runs` first. No other statement inserts into `businesses` (`grep -rn "INSERT INTO businesses\|INSERT OR.*businesses"`).
A merge (`upsert_business` merge branch, `merge_business_into`, `merge_phone_duplicates`) never writes `first_run_id`: a merged row keeps the
keeper's value (the keeper is the Maps row, which can be younger than the register row folded into it: see "Decisions").

Measured on the invented workspaces (read-only SQL, `first_run_id IS NULL OR = ''`):
- fake campaign workspace (`scripts/e2e_fake_campaign.py`, sources `gosom` 7 and `dvsa` 3): **0 of 10** empty; 0 name a run that is not in `runs`.
- `tests/golden/workspace_current.sqlite3`: **1 of 1** empty. That row is not a way the product adds a business: `tests/fixtures/make_workspace_golden.py`
  calls `db.upsert_business` with a `Business(...)` that carries no `first_run_id`. It shows `upsert_business` itself accepts none.

**Answer.** Ways of adding a business that leave `first_run_id` empty in the product: **0**. All paths set it, so, as the adoption row says, no change to
the tables. Because `upsert_business` accepts an empty one (fixtures, a database written by other tooling), the expiry rule treats an empty or
dangling `first_run_id` as "the workspace's first run" (the earliest `runs.started_at`), the row's own wording; with no run at all nothing is old
enough to expire. No "plan and code disagree" entry from this item; C5 is not held back.

**Baseline of the fake campaign (G2) before any change, on this laptop, at 1050687.** `python scripts/e2e_fake_campaign.py` (below-normal priority):
```
FAIL - differs from expected.json in: refused  (full result: D:\homelab-work\l6\baseline\run1\result.json)
  .refused: expected 21 entries, got 20
```
The only difference is one entry fewer of `["sendto", "1.1.1.1", 53, "dns"]` (9 against 10): the number of DNS retries the email-validity step makes
inside the resolver's time limit, which depends on timing and on this laptop's resolver (94.140.14.14, not the one in the saved result). It does not
come from this slice. Rule for item 8: the final run is compared cell by cell with this baseline `result.json`; every cell other than that count must be equal.

## Item 2 — the schema version is read before any write

**Must do (written before the code).** Opening a workspace database (`db.connect`) reads `meta.schema_version` first, from a read-only view that
cannot change one byte: `?immutable=1` when no non-empty `-wal` file exists; when one exists, from a throw-away copy of the file and its side files
in a temp folder (an immutable open would ignore the log). Only after that: a file that does not exist or holds no table is new, so `connect`
proceeds as today (WAL, create tables, stamp). A version equal to `SCHEMA_VERSION` proceeds as today. Any other version, a non-integer, a file
that holds tables but no version row, or a file SQLite cannot read: `InputError` (exit 4, the message of today for the version case), and nothing
was opened for writing: no `PRAGMA journal_mode=WAL`, no `-wal`/`-shm`, no create-if-missing. The CLI must not write into the workspace before
that check either: the log file and the log folder are created at the first log record, not at start-up (`util.setup_logging`).
**Pass line:** a workspace of schema 4 with rows, in WAL mode with a live `-wal`, refused by `status`, `suppress list`, `run`, `export`, `forget` and
`purge`; the SHA-256 of every file under the workspace and the list of files are equal before and after.

**Check by reading, after.** `db.connect` now calls `check_schema_before_write` first (db.py); `peek_schema_version` opens `?immutable=1`, or a temp copy
when a non-empty `-wal` exists, and `_version_of` only runs `SELECT`s. New file / zero bytes / no table: passes. Tables without a version row, a
non-integer or a different version: `InputError`, before `PRAGMA journal_mode=WAL` and before `_DDL`. `migrate` keeps its own check (second line of
defence for a caller that bypasses `connect`). `util.setup_logging` uses a handler that makes the folder and file at the first record (`delay=True`);
`cli._root` no longer touches `cfg.logs_dir` (that property creates the folder).
**Seen red first (right reasons).** Before the change: `db.sqlite3-wal` and `db.sqlite3-shm` appeared, the `-shm` hash changed, the DDL raised
`no such column: domain` on a file with tables and no version; after the DB fix alone, `leadforge_data/logs/leadforge.log` (empty) appeared. With the
temp-copy branch disabled the live-`-wal` case fails (an immutable read ignores the log), restored.

## Items 3 and 4 — `forget` (C4) and `purge` (C5): what each must do (written before the code)

Where a person's detail can land (read from the code; the plan counts eight): 1 the database tables (`people`, `contacts`, `evidence`,
`enrichment_observations`, `outcomes`, `messages`, `events`, `outreach_targets`, `scores`, `businesses.enrich_json` and the business's own name,
address and web columns); 2 the cache (`gosom_*.json`, `geocode.json`, the DVSA register copy); 3 the logs (`leadforge.log` and its 3 rotated
copies, `agent_runner.log`, `<run>.detach.log`); 4 the progress feed (`progress.jsonl`, `pace.json`); 5 the outbox (`.eml`) and the inbox (webhook
spool `.json`); 6 the hand-off files in the workspace folder (`dm_batch*`, `dm_labels*`); 7 the draft packets (`drafts_packets*.ndjson`, `drafts/*.txt`);
8 the sheets in the tool's own `exports` folder (`.xlsx`, `.csv`, `report.json`). The database file itself also keeps deleted rows readable
until it is rewritten (free pages, `-wal`).

**`leadforge forget <email | domain | name>`.** The value is classified: contains `@` = email; no space and a dot = domain; else a name. The match is
case-insensitive with word edges (an email does not match inside a longer address, a name not inside a longer word); in JSON text the
escaped spelling is tried too.
- Database: every row that holds the value in a scanned column is deleted (people, contacts, evidence, observations, outcomes, messages, events,
  scores, targets), together with what hangs on it (a deleted person takes their observations, a deleted contact takes its outcomes, targets and
  messages). A business whose own name, address or web columns hold the value (a sole trader named after themself; every business at a forgotten
  domain) is deleted with everything attached. A value found only inside a business's `enrich_json` / `hours_json` is replaced there by
  `[forgotten]`. Not touched: the user's own `sending_identities` and `mailboxes`; the `suppression` table, which must keep the identifier or the objection is
  lost (see "Plan and code disagree").
- A `suppression` row is added (kind `email`, `domain` or `name`) with a blank reason; `add_contact`, `add_person` and discovery then skip a
  suppressed email, name or domain, so a new run does not collect them again.
- Files: under `leadforge_data/` (except `bin/` and the live database) and the hand-off and packet files and `drafts/` of the workspace folder: a
  line-oriented file (`*.log*`, `*.jsonl`, `*.ndjson`, `*.tsv`) loses the lines that hold the value, every other file that holds it (also inside an
  `.xlsx`) is deleted. The command lists the files changed and removed by relative path, never their content.
- Then the database file is cleaned: `secure_delete` on for the deletes, commit, `wal_checkpoint(TRUNCATE)`, `VACUUM`, checkpoint again.
- It says plainly that sheets already handed out cannot be reached. What must stay: another person's row, line and file are untouched.

**Expiry (`purge`).** Age of a business = now minus the `started_at` of its `first_run_id` run (item 1: empty or dangling = the earliest run; no
run = no age = never expires). A business expires when that age is 12 calendar months or more (`retention.months`, 1 to 12; the user can shorten,
not lengthen). A refresh (`last_seen_at`, a merge) never renews. Expiry removes the business and everything attached (same cascade as `forget`).
Protections of the automatic purge, which runs at the start of every `run` (also `run --detach` and `--resume`):
1. **First run after the upgrade only reports.** A workspace without the `retention_armed_at` marker in `meta` gets the marker and a report of what *would*
   expire; nothing is deleted. The explicit command follows the same rule on an unarmed workspace.
2. **Every run prints how many records expire in the next 30 days** (human line and digest `expiring_30d`).
3. **Never more than half.** If the expired businesses are more than half of all businesses the automatic purge deletes nothing, the run stops with exit 4,
   and the message names `leadforge purge --apply` (a clock a year ahead lands here).
4. **A half-upgraded workspace stops the command.** Before anything is deleted the file is checked against the tables and columns this version expects
   (read-only); a missing table or column, or an unreadable marker: the command stops, exit 4, the file unchanged.
`leadforge purge` alone only reports. `purge --apply` is the explicit command (no half limit; same protections 1 and 4). `purge --everything --yes` deletes the
files of the workspace's own data folder without opening the database (any age, any schema); `bin/` (the pinned helper program) stays.
Time comes only from `util.utcnow()` and the `now` argument: tests never sleep.

## Item 5 — raw scrapes (C6): what it must do (written before the code)
The raw file of the Maps scraper (`cache/gosom_*.json`, its `.queries.txt`) is deleted as soon as it was parsed, also when the run stalls and the
parse salvages part of it, and also when nothing could be parsed. Resuming does not need it: a finished query's listings are already rows in the
database. Reviewers' own names and review texts are in that file only; the database keeps the staff first names the owner signs with or customers
credit (business facts the decision-maker step uses).

## Item 6 — a suppressed address is in no export and no tab (C7): what it must do (written before the code)
`db.contacts_for(..., hide_suppressed=True)` leaves out email contacts that are suppressed; the two readers in `export.py` ask for it, so the Leads tab and CSV
`Email` and `Email (Inferred)` columns and the Drafts fallback address behave as if the address did not exist. (First version: the filter was always on. See "Findings of the
one full run".) A last net in `export_run`: any cell of any tab or CSV, and any Drafts-tab
row, that still holds a suppressed address (a draft body, a `To`) has it replaced by `[suppressed]`, and a Drafts row addressed to it is dropped.
Domain-suppressed businesses are already out of the sheet (`scores_for_run`); unchanged.

## Items 3 to 6 — check of the code against the text above, by reading (after the code)

- **`forget`** (`retention.py`, `cli.forget`): `make_needle` classifies by `@` / dot-without-space / else, lower-cases an email or domain, builds a
  pattern with word edges (an address is not matched inside a longer address, a name not inside a longer word) over the raw and the JSON-escaped
  spelling. `forget_in_database` deletes by `ROW_RULES` and `BUSINESS_IDENTITY`, with dependents in `_delete_everything_on` (person → observations,
  contact → outcomes, targets → messages → events), redacts `enrich_json`/`hours_json`, adds the suppression row, then `_scrub_database_file`
  (checkpoint truncate, `VACUUM`) with `secure_delete` on for the deletes. `forget_in_files` walks `leadforge_data/` minus `bin/`, the stamp and the live
  database, plus the hand-off and packet files and `drafts/` of the workspace folder; line files lose lines, everything else (also a sheet whose text is
  compressed inside) is deleted. `db.add_contact` returns 0 for a suppressed email, `db.add_person` skips a suppressed name; a domain was already skipped by
  discovery and enrichment. The value is never printed or logged: the human line and the digest carry kind and counts, the digest lists relative paths.
- **`purge`**: `classify` ages from `runs.started_at` of `first_run_id` (empty/dangling = earliest run; none = never), `due <= now` expires, `due <= now+30d`
  counts as soon. `purge()` order: no database → `no_workspace`; `check_schema_before_write` (old schema stops); `schema_gaps` + marker readable (half upgraded
  stops); marker absent → write it and report only; nothing expired → `nothing`; `auto` and more than half → `stopped_over_half`; else delete and scrub.
  `cli._start_of_run_purge` runs before `--detach` and before `run_pipeline`, prints the 30-day line to stderr, and puts `purged` and `expiring_30d` in the digest.
  `purge --everything --yes` never opens the database (the test makes both `db.connect` and `sqlite3.connect` raise).
- **C6** (`providers/gosom.py`): `fetch` is a wrapper whose `finally` deletes `out_path` and the `.queries.txt` after `_fetch` returned or raised.
- **C7** (`db.contacts_for(hide_suppressed=True)`, `export.py`): see the item text; the draft columns and the Drafts tab drop a draft whose target contact is suppressed; `_masker` replaces a
  suppressed address anywhere in any cell, in any case.

## Tests of this slice (each seen failing for the right reason first)

| File | Pass line it carries | Seen red because |
|---|---|---|
| `tests/test_l6_schema_first.py` | old workspace refused, every file's hash equal (with and without a live `-wal`); tables without a version refused; new, zero-byte and hollow files open | `-wal`/`-shm` appeared and changed, the DDL ran first, the log file appeared; with the temp-copy branch off the live-`-wal` case failed |
| `tests/test_l6_forget.py` | C4: planted person in tables, cache, logs (also rotated), progress, outbox, inbox, hand-off files, packets, sheets (`.xlsx` read inside), exports; the scan finds the value only in the suppression row; a bystander's rows, lines and files byte for byte; look-alike address and name stay; not collected again | each of: line-edit off, zip read off, word edges off, suppression off, secure-delete and VACUUM both off made it fail (removing only one of the last two does not: they back each other up) |
| `tests/test_l6_purge.py` | C5: 13 months gone, 11 stay, refreshed 13 gone; first run only reports; the 30-day line; a clock a year ahead deletes nothing and stops (exit 4; `purge --apply` is what deletes); half-upgraded stops with the file unchanged; old schema refused unchanged; `--everything` without opening the database; period shortened, never lengthened; boundaries | six changes to `retention.py` (first-run report, half rule, half-upgrade check, refresh renews, empty `first_run_id`, 30 days) each failed it |
| `tests/test_l6_raw_scrapes.py` | C6: raw file gone after parse, after a salvage, after nothing parsed, after a failure that wrote no file; the reviewer's name in no file of the workspace | with the old `fetch` the two raw files stayed |
| `tests/test_l6_suppressed_export.py` | C7: suppressed address in no file of the export, also inside the sheet; its draft off the sheet; other rows stay; a quoted address masked | the address was in the Leads tab, the Drafts tab and the CSV |

## Plan and code disagree

1. **C4's own two sentences.** The row says `forget` "adds a suppression row", and its test says a byte scan of the database file, its side files and the data
   folder "finds nothing". A suppression row must hold the identifier, or the objection cannot be honoured on the next run. *Plan:* both. *Code:* the
   identifier is stored once, in clear, in `suppression` (`db.py`, `db.suppress`); the test proves nothing else holds it (a copy with that row deleted and
   rewritten has zero hits). Not built: a hashed suppression list (`is_suppressed` and four SQL sub-selects would change). **Owner's decision needed** if
   "finds nothing" is to be literal.
2. **"first entered the workspace" (C5).** *Plan:* the 12 months run from when the business first entered. *Code:* `businesses.first_run_id` is the run that created
   the row it sits in; `db.merge_phone_duplicates` keeps the Maps row and folds the register row into it, so a business first found through a register can carry its
   younger twin's `first_run_id`. Not changed (the plan says no change to the tables); the expiry can come later than 12 months after the very first sighting in that case.
3. **G2 is red before this slice on this laptop** (Item 1's baseline): the saved result has 21 refused DNS entries, this laptop produces 20 at 1050687. *Plan:* "the digest
   and sheet match the goldens". *Code:* the refused list's count depends on DNS retries. Not changed by this slice.
4. **ADOPT section 3 and SPEC 3.4 name a Linux CI trial of the mutation tool; mutmut does not run on Windows.** A small in-house trial (`scripts/mutation_trial.py`) was run here
   instead; the Linux CI trial is NOT DONE.
5. **The plan counts "eight" places; the row lists more** (tables, cache, logs, progress file, outbox and inbox, hand-off files, packets, sheets). The test plants 14 files and a dozen
   rows and asserts the scan sees the value in at least 12 places before the command and only in the suppression row after.

## Decisions taken on my own

- A stop of the automatic purge for more than half stops the whole `run` (exit 4) and names `purge --apply`; the plan says "it stops and names the explicit command".
- `leadforge purge` alone only reports and never writes (not even the marker); `--apply` is the explicit command and follows protections 1 and 4 but not 3.
- Half-upgraded = a table or column this version expects is missing, or the retention marker is unreadable. Checked read-only before connecting.
- `forget` in an old-schema workspace is refused like every command (nothing changed); `purge --everything --yes` is the way out for such a workspace.
- Files `forget` and `purge --everything` leave alone: `bin/` and the doctor stamp (not personal data), and anything written outside the data folder by `--out`.
- Exports: purge does not delete old export folders (C5's row names the business and what is attached); `forget` does remove sheets that hold the person.
- Sole-trader rule: a business whose name, address or web columns hold the forgotten value is deleted whole. `scores` rows that quote the value are deleted (recomputed by `score`).
- `retention.months` is 1 to 12 (shorten only); `leadforge.example.yaml` lists it.
- The log folder and file are created at the first record, so a refused command leaves the workspace unchanged.
- `uv.lock`'s own entry still says 0.6.14 (an L4 debt that `check_versions.py` does not read); left as is.

## Item 8 — the fake campaign (G2): prediction written before the run

At the end of items 1 to 7, before `scripts/e2e_fake_campaign.py` is run on the finished code. Compared cell by cell with the baseline `result.json` of Item 1 (not with
`expected.json`, which this laptop already misses by the DNS-retry count).
- Predicted to move: the count of `["sendto", "1.1.1.1", 53, "dns"]` entries (timing), as in the baseline, in either direction by one or two; nothing else in `refused`.
- Predicted to move: in the digest of each `run` step that finds an existing database, `counts` gains two keys, `purged` (0) and `expiring_30d` (0), because `run` now
  starts with the retention check (`cli._start_of_run_purge`). The first `run` step, which creates the database, gets none.
- Predicted NOT to move: the request log, the four tabs, the CSV, `report.json`, the digest numbers of every other step. A schema is unchanged (SCHEMA_VERSION stays 7, no
  table or column added), so the workspace golden stays; no `first_run_id` is touched.

## Item 8 — result

`python scripts/e2e_fake_campaign.py` on the finished code (below-normal priority):
```
FAIL - differs from expected.json in: steps  (full result: D:\homelab-work\l6\after\run1\result.json)
.steps[7].digest.counts.expiring_30d: only in got
.steps[7].digest.counts.purged: only in got
```
Exactly the two cells predicted above, and no other cell: this run's `refused` list had the saved 21 entries (the baseline's 20 was therefore timing, not this laptop's resolver:
it is one run at below-normal priority each, so the DNS-retry count is UNPROVEN as stable on this laptop; plan-and-code-disagree entry 3 stands as "the count varies between runs").
`tests/fixtures/e2e/expected.json` was changed in those two cells only (`steps[7].digest.counts`: `expiring_30d: 0`, `purged: 0`); the script that did it asserted that, with
those two cells set, the file equals the run's `result.json` everywhere. G2 on the version-bumped commit is written under "Last gates" below.

## Findings of the one full run (`node check.mjs`, e5e9f86 tree, before the fix below)

```
FAILED tests/test_golden_contracts.py::test_golden_agent_contract
FAILED tests/test_outreach_plan.py::test_plan_suppressed_and_already_enrolled_excluded
FAILED tests/test_outreach_send.py::test_suppressed_address_never_sent_even_if_approved
3 failed, 877 passed, 7 skipped in 172.56s (0:02:52)
CHECK FAIL sha=ee5e9f86 tree=clean steps=5 skipped=0 secs=175
```
Causes, written before any change:
1. `test_golden_agent_contract` pins the list of commands; this slice adds `forget` and `purge`. Deliberate: the golden was re-recorded (`LF_UPDATE_GOLDEN=1`, this one
   test) and its diff is exactly those two names.
2. and 3. The two outreach tests plan and send to a suppressed address and assert that it is *counted as suppressed* (`excluded.suppressed`, `skipped_suppressed`).
   My first version of C7 made `db.contacts_for` hide suppressed emails for every reader, so the planner and the sender no longer saw the address and counted it
   as "no sendable email" instead. The mail was still not sent, but the reason and the counter those guardrail tests pin had changed, and the send-time re-check
   must keep seeing the address. The wrong side was the code: the filter moved from `contacts_for` (default off) to the export's two calls (`hide_suppressed=True`).
   The tests were not touched.

## Item 7 — the mutation trial: result

Tool: `scripts/mutation_trial.py` (in-house; changes one thing at a time in a temp copy of the package, never in `src/`; see its docstring). Targets: all of `retention.py`, the new part of
`db.py` (lines 152-250) and `add_contact`/`add_person` (604-645), `export.py` 92-108 (the masker), `providers/gosom.py` 43-54 (the raw-file wrapper), each against the tests meant to cover it.

| Round | Changes | Killed | Survived | Minutes (this laptop, below-normal priority) |
|---|---|---|---|---|
| 1, before the extra tests | 223 | 145 | 78 | 12.2 |
| 2, after them | 223 | 172 | 51 | 11.4 |
| 3, lines 55-70 of `retention.py` only | 13 | 12 | 1 | 0.7 |

**Real gaps it found (each now has a test, round 2 and 3 show them killed):** the day of expiry and the 30-day edge were not pinned (`<=` against `<`); "exactly half may go, more
than half may not" was not pinned; a workspace with no run (no age) was untested; January plus 12 months (the year carry) was untested; the kind of a value (`Cher` is a name, not a domain)
and the recorded suppression kind were untested; an accented name in its JSON spelling (`ë`) was untested; a look-alike address after a dot was untested; remaining lines of a line
file lost their line ends unnoticed (`keepends`); the reported file lists were unchecked; `--everything` did not check empty folders or its count; an empty file with no table (not zero bytes)
was untested; `missing_ok=False` in the raw-file clean-up would have hidden the scraper's own error behind a `FileNotFoundError`.

**The 51 that remain, read one by one:** equivalent or outside this slice's code. The two disk-rewrite steps (`secure_delete` and the checkpoint + `VACUUM`) back each other, so removing either alone
changes nothing observable (removing both fails the test, shown earlier); chunk sizes 500 against 501 and `1 -> 2` in counters; `close()` of a log handler (needed on Windows for a file this
process holds open: UNPROVEN, no test holds a log file open in the same process); dedupe guards in `candidate_files` (a directory or a duplicate is caught by the `OSError` handler);
`rollback` on an error path; `text.lower()` (the pattern is case-insensitive and `suppress` lower-cases); the `frozen=True` of a dataclass; lines of `db.py` 604-645 and 247 that predate this slice
(`PRAGMA foreign_keys`, `p.origin or p.labeled_by`, `else 0`); the hash length in the raw file's name.

**Keep or cut (SPEC 3.4: it stays only if it finds a real gap and runs under 20 minutes in CI).** Found real gaps: yes (the list above). Run time: 11 to 12 minutes here for these modules; the Linux CI
time is NOT MEASURED. Verdict: KEEP the script as a trial that is run by hand on the delete-side modules; NOT added to CI. The vendor tool (mutmut) was not run (it needs Linux): UNPROVEN.

## Last gates, on commit 0005d4f

- `node check.mjs`: `880 passed, 7 skipped in 183.28s` and `CHECK PASS sha=0005d4f tree=clean steps=6 skipped=0 secs=187`. The 7 skipped are the suite's own skips (the first run had the same 7).
- `python scripts/e2e_fake_campaign.py`: `PASS - result equals tests/fixtures/e2e/expected.json (21 refused-call entries, as saved)`.
- `ruff check src tests scripts/mutation_trial.py`: `All checks passed!`. `python .github/scripts/check_versions.py`: all six copies `0.8.0`.
- `gitleaks detect --log-opts "origin/master..HEAD"` (on the 13 commits before the last two): `no leaks found`.
- Not run on STRIKERFORCE: a test that needs a real browser (none touched by this slice); Linux; hosted CI is read below.

## Hosted CI, read from GitHub (`gh pr checks 6`), commit 44d07cb (run 43165231460, status completed, conclusion success)

13 of 13 jobs pass, no job re-run: Validate plugin manifests · Version strings agree · claude plugin validate · fake campaign ubuntu-latest · fake campaign windows-latest ·
ubuntu-latest py3.11 / py3.12 / py3.13 / py3.14 · windows-latest py3.11 / py3.12 / py3.13 / py3.14 (all `pass`). This table was added in a later commit that changes only this file; that
commit's own run is read and written in the report.
