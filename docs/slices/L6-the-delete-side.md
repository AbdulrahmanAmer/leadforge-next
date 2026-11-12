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
