# L5 install proven and the fake campaign

## Starting list (from the L4 refactor proof)
- ZERO: the fake campaign check runs on `windows-latest` only (L4 merge, 0.7.2). On `ubuntu-latest` it differed in `refused`
  only: 0 entries against the 21 saved. Cause (read from the runner): its `/etc/resolv.conf` names `nameserver 127.0.0.53`,
  a local stub resolver. The guard allows loopback, so the email-validity step's DNS packets (`dns.resolver.Resolver()` reads
  that file) went to the stub, were not refused and were not logged. The path separators and the short Windows temp name
  (`RUNNER~1`) were the other two differences; the compare now absorbs both. For Linux: make the guard see DNS sent to a
  loopback port 53 (refuse and log it, as it does for `getaddrinfo`), or give the campaign its own resolver setting, then
  save a Linux-side result or compare without `refused`. This also means: on a machine with such a stub, the guard as it is
  lets a DNS question reach the outside through the stub.
- FIRST: Companies House's address becomes a setting, so that source can be faked. It is fixed in the code today (`providers/registry.py` `CH_BASE`) and was off in both versions of the proof.
- 0.6.14 installed the way its own README says fails at enrich (`selectolax` 1.0.2 `ImportError`: its open-ended `selectolax>=0.3.21` follows to a release that removed the backend it uses). The upgrade note must say it.
- The socket guard is Python-level: asyncio's Windows `ConnectEx` and native sockets are not covered. One probe through `asyncio.open_connection` inside the guard settles it.
- Not shown at all by the proof: the real sources, the browser, the agent call, sending.

# Build (0.7.3) — first part of L5

Run `l5-build`, 2026-11-12. Items in the order of the brief; per item the text of what the change must do is written before the
code, the reading check after it.

## Item 0 — the Linux DNS gap

**Must do (written before the change).** In `tests/fixtures/e2e/harness/sitecustomize.py` a connection or datagram whose destination
port is 53 (UDP `sendto`, TCP/UDP `connect`/`connect_ex`) is refused and logged exactly like an outside call, whatever the address
(loopback included). A loopback address on any other port stays reachable, so the fake world's own server (port 18765) and the
probe's ephemeral loopback listener are untouched. The log entry has the same shape (`kind`, `host`, `port`, `caller`).

**Which refused-list cells move.**
- Windows (saved result made there): NONE. Its system resolver is not loopback, so its packets were already refused and normalized
  to the one `<system resolver>` entry; the 20 fallback entries (8.8.8.8, 1.1.1.1) are unchanged.
- Linux (`ubuntu-latest`): 0 entries → the same 21 as saved. The stub `127.0.0.53` now refuses the probe question
  (`sendto 127.0.0.53:53`, normalized to `<system resolver>`), `get_resolver()` falls to its public fallbacks, whose refused sends
  are the same 20 entries as on Windows. The saved result stays unchanged; if Linux shows any other difference, that is not predicted.
- Nothing else in the result moves: the request log and the tabs do not depend on DNS packets (names of the `.example` sites resolve
  inside the guard, not by packet).

**Seen red first.** `harness/probe.py` gets two cases (UDP `sendto` and TCP connect to `127.0.0.53:53`) and `--probe` demands that the
guard log holds both (TCP to a closed loopback port is refused by the OS anyway, so the log, not the exception, is the evidence).

## Item 1 — Companies House's address as a setting

**Must do (written before the change).** New setting `registry.companies_house_url` (yaml, or `LEADFORGE_REGISTRY__COMPANIES_HOUSE_URL`,
read the way every other setting is: the `RegistryCfg` pydantic model fed by `leadforge.yaml` then the env overrides). Default is
exactly today's address `https://api.company-information.service.gov.uk`, so with no setting nothing changes. Both users of the
address read it from the config instead of the constant: the officer lookup (`providers/registry.py`, `CompaniesHouseRegistry`,
three requests) and the discovery provider (`providers/companies_house.py`, two requests).
Decision on other values (own decision, reason): the DVSA setting (`discovery.dvsa.url`) accepts any address because the request
carries nothing secret. This one carries the Companies House API key as basic-auth user name on every request, so a setting that
pointed to a stranger's host would send the key there. Therefore the config refuses at load (`ValueError` from a pydantic
validator, which `load_config` and `config set` both go through) every address except the default and an `http`/`https` address
whose host is `localhost` or a loopback IP (with or without a port or a path prefix); an address with embedded credentials, a query
or a fragment is refused too. A trailing `/` is dropped. No change anywhere else.
Seen red first: a test that sets a non-default, non-loopback value and expects a refusal, and a test that a loopback value reaches
the officer lookup's request (checked via an httpx transport double: URL of the request). Break: validator accepts everything /
code still reads the constant → each test fails.

**Check by reading, after.** `RegistryCfg.companies_house_url` (config.py) matches the text: default = the real address; validator drops a
trailing `/`, returns the default unchanged, accepts only http/https + `localhost`/loopback IP (`urlsplit().hostname`, so
`127.0.0.1.evil.example` and `user@` forms are refused) with no credentials/query/fragment, refuses a bad port. One addition not in the
text above: an empty value means the default. `config set` validates through `load_config` before writing, so a refused value is never
saved. `CH_BASE` is gone (nothing else read it; `git grep CH_BASE` finds only this file). The five request sites read `self.base` /
`cfg.registry.companies_house_url`. Red/green: with the validator's default-return removed and the officer search pinned to the real
address again, 10 of the new tests failed (refusal ×8, env override, configured-address request); restored → 43 passed in test_registry.py.
New dev packages for local test runs only (nothing added to the project): `pytest 9.2.0` (uploaded 2026-10-27), `pytest-timeout 2.4.0`
(2025-05-05), `iniconfig 2.3.1` (2026-10-06), `pluggy 1.7.0` (2026-10-15), exactly the versions in the repo's own `uv.lock`,
all older than 7 days, published on PyPI by pytest-dev; `osv-scanner` on `uv.lock`: no issues.

## Item 2 — the fake for it (written before the change and before the run)

**Must do.** `tests/fixtures/e2e/companies_house.json` holds four invented companies (numbers `ZZ0000nn`: no register issues that
prefix; people made up). `scripts/e2e_fake_campaign.py` serves them on its own loopback server under `/ch/` (`search/companies`,
`company/<n>`, `company/<n>/officers`, basic auth with the fixture key or 401) and the campaign's `leadforge.yaml` gets
`registry.companies_house_key: fixture-key` and `registry.companies_house_url: http://127.0.0.1:<port>/ch`. The source in use
is the officer/registry lookup (`CompaniesHouseRegistry`); the company-mode *discovery* provider is not switched on (it needs a
second, company-mode ICP): carried over. What the four invented companies exercise: HARBOUR MOTORS LTD (active, one active
individual + one resigned → matched, one registry DM auto-picked); NORTHGATE TYRES LIMITED (active, two individuals → matched, no
auto-pick); PENNINE MOTORS LIMITED (dissolved → rejected, `active_only`); HARBOUR MOTORS BATH LTD (same name, other town → listed
first in the search answer for Harbour Motors, rejected by the locality gate).

**Cells that may move in `expected.json`, and why** (every business in `GB` is now looked up, `registry_checked` becomes true):
1. `steps[intake].digest.warnings`: the "a free Companies House key adds registry-verified directors" line goes (the key is set).
2. Leads tab and CSV, ALL ten rows: `Company No`, `Registry Name` change from `not looked up` to either the company (matched rows) or
   `not matched in registry`; `Registry Match` from `n/a` to the similarity for matched rows. Matched rows (Harbour Motors,
   Northgate Tyres): also `Incorporated`, `Company Status`, `SIC Codes`.
3. Harbour Motors only: `DM Name`/`DM Title`/`DM Conf` (registry director `Tamsin Verrill`, `Director`, 0.9) and what follows from a
   named DM: `Call Readiness`, `Next Action`, `Score`/`Why This Score`/`Tier` if the rubric reads a DM, the Drafts row (`DM Name`,
   greeting), Summary counts (`With decision maker`, Tier line, Next Action breakdown), `report.json` (`with_dm`, `tiers`).
   Northgate Tyres keeps "not identified": two individuals are never auto-picked. Pennine Motors and the other seven: DM cells unchanged.
4. `steps[run-resume|status|export].digest.counts`: registry/DM counters (`dm_labeled`, `dm_unlabeled`, tier counts) follow 3.
5. `requests`: new entries `127.0.0.1 /ch/... <status>` (the loopback server logs them): search, profile and officers calls for
   each business that reaches that point.
6. NOT moving: `refused` (all CH traffic is loopback and not port 53), every other business's DM/score/draft cells, `files`.
Anything outside this list that moves: stop and write the cause first.

**First run (saved nowhere; compared with `expected.json`) — what moved beyond the list above, and the cause (written before the second run).**
- `Entity Type` moves in all ten rows (`unchecked` → `unmatched` / `corporate_active`) and `Score`, `Tier`, `Fit`, `Why This Score`
  also in the second matched row (Northgate Tyres): a registry match adds the rubric's "registry-corroborated" factor; I had tied the
  score move to the DM only. Same family as items 2 and 3, so it is added to the list, not a surprise.
- Pennine Motors was matched to HARBOUR MOTORS LTD (similarity 0.46, same city), got its director and a draft saying "trading since
  2011". Cause: my fake search answered every company sharing ONE word of the query, and the tool's lookup then `continue`s past
  the dissolved PENNINE MOTORS LIMITED to the next hit, which clears `min_name_similarity` 0.45 on a 0.46 character-ratio score.
  The second half is a real property of the tool (a wrong-company match the code's own comment calls worse than none): NOT
  changed here ("no other behaviour changes"), written under carried over. The fixture's search now answers only companies whose title
  holds every word of the query (as a name search does for an exact name), so Pennine meets only its dissolved company.
- Second-run expectation, replacing the list above where it differs: Pennine Motors moves only `Company No`, `Registry Name`,
  `Entity Type` (`not matched in registry`/`unmatched`); Harbour Motors and Northgate Tyres move the registry, score and (Harbour
  only) DM/contact/draft cells; the other seven move `Company No`, `Registry Name`, `Entity Type` only.

**Second run, diffed per business and per section against the old `expected.json` (script: leaf diff of the normalized results).**
Moved, all inside the list above: Company No / Registry Name / Entity Type in all ten rows; Harbour Motors (registry DM Tamsin Verrill,
Director, 0.9, `READY - named contact`, score 72→80, Tier B→A); Northgate Tyres (registry fields, score 72→80, Tier B→A, no DM: two
individuals); Pennine Motors only `not matched in registry` (dissolved company rejected); `steps[intake]` loses the key-hint warning;
`dm_candidates` 5→8 (Tamsin, Fenn, Larkin; the resigned director is not counted), `dm_auto_picked` 1 (new key), `dm_unlabeled` 2→1,
tiers A/B/C 0/5/5 → 2/3/5; Summary with-DM 3→4 and the tier / next-action lines; the Drafts tab: Harbour's row names the DM and the
rows reorder because Northgate is now tier A; `requests` gains 10 `/ch/search/companies` and the profile and officers calls for the
two matched companies, all 200. NOT moved: `refused` (same 21), `About`, every other DM/score/draft cell. Saved result rewritten from
that run; a third run compared against it: `PASS - result equals tests/fixtures/e2e/expected.json (21 refused-call entries, as saved)`.
The old saved result already fails on the new campaign (the diff above is that failure), so the saved result does see the source.

**Check by reading, after.** Server: 401 without the fixture key's basic-auth header (the key goes only to this loopback address, in line
with item 1), search answers only companies holding every word of the query, profile/officers by number, unknown number 404; all
CH traffic is logged in `requests`. Config: key and `http://127.0.0.1:<port>/ch` set through the same settings a user has.

## Item 3 — the timing-flaky speed test, fixed at its cause

**What the test is meant to prove.** `validate_emails_parallel(rows, cfg)` (`enrich/validate.py`) puts every row through
`validate_email` on a pool of `cfg.enrich.dns_workers` threads: (a) each row exactly once, result mapped to its row id, and (b) the
calls overlap, up to the pool size and never beyond it. The old test proved (b) only through a race against the clock (16 calls of
0.05 s must finish in under 0.4 s); a busy runner stretches the sleeps and the bound fails with correct code (`0.55 < 0.4`, CI run
43045072218). Cause: the assertion measured elapsed time, which depends on the machine, not on the code.

**Must do (written before the change).** The fake `validate_email` waits on a `threading.Barrier(8)` (timeout 5 s, only ever
reached when the code under test fails) and records how many calls are in flight at once under a lock. 16 rows, 8 workers:
each group of 8 calls can only pass the barrier if 8 run at the same moment, so the peak in flight is exactly 8 on any machine, with
no sleep and no clock in the assertion. Assertions: results are the 16 ids once each with the right email; `calls` has 16 entries;
peak in flight == 8 (overlap happens, and the pool bound holds). Test renamed `..._runs_calls_concurrently_up_to_the_pool_size` since it
no longer measures speed. Seen red first: with the pool forced to one worker the barrier breaks and the test fails; restored.

**Check by reading, after; red/green.** The new test has no `time` call in its assertion path; the barrier timeout (5 s) is an upper bound for the
failing case, not a margin. Passes in 0.35 s. With `workers = 1` forced in `validate_emails_parallel`: `1 failed ... threading.BrokenBarrierError`
in 5.64 s (red for the right reason: the calls could not overlap); restored: `1 passed in 0.36s`. The two other wall-clock tests named in the L4
list (`test_crawler_politeness.py::test_workers_12...`, `test_maps_list.py::test_parallel_queries_is_faster_than_serial`) are not in this brief: carried over.

## Item 4 — `send-outreach` installed alone can open its guardrail files

**Read first: can the skill be installed without `generate-leads`?** YES.
- Plugin route (Claude Code, Codex): `source: "./"` / `"skills": "./skills/"` — the whole repo is the plugin, both skills ship together, so
  `../generate-leads/references/...` resolves. Not a hole.
- `python install.py`: installs EVERY folder under `skills/` that has a `SKILL.md` (no per-skill option), as a link/junction or a copy, so both are
  present. Not a hole (as long as nobody deletes one by hand).
- `npx skills add AbdulrahmanAmer/leadforge` (the "any harness" route named in README, AGENTS.md and install.py): copies skill folders into the
  harness's skills folder; that tool is documented to take a chosen skill, and the unit it copies is the skill's own folder, so
  `send-outreach` can land without its sibling. I could not run it (no outside call): UNPROVEN as a run, but by construction the sibling
  path `../generate-leads/...` is outside the folder that is copied. Any hand copy of `skills/send-outreach/` has the same hole.
So the skill points at three files (`outreach.md`, `drafting.md`, `troubleshooting.md`, five places in `SKILL.md`) that are not in its own folder.

**Must do (written before the change).** Copies, not links (a link or junction does not survive a zip, a plain copy or Windows without
rights): `skills/send-outreach/references/{outreach,drafting,troubleshooting}.md`, byte-identical to the `generate-leads` ones; the five
places in `SKILL.md` read `references/<file>.md` (beside the skill). New check `.github/scripts/check_skill_references.py`, run by
`check.mjs` and the manifests CI job: (1) for each skill, install it ALONE (copy only that skill's folder into an empty folder, as a skills
tool does) and require that every `references/<file>.md` its `SKILL.md` names exists there, and that no named path climbs out with `../`;
(2) every reference file that exists in more than one skill is byte-identical in all of them. Fails with the file and the skill named.
Seen red first (three breaks): a path put back to `../generate-leads/...`; a copy deleted; a copy edited by one character.

**Check by reading, after; red/green.** `SKILL.md` of `send-outreach` now names only `references/<file>.md` (5 places); the three files are in
its own folder; `check.mjs` has the step `skill references` and the manifests job runs the script. Output, all three breaks seen red for the
right reason, then restored:
```
break 1 (path back to ../generate-leads):  send-outreach: SKILL.md names ../generate-leads/references/outreach.md which leaves the skill's own folder   exit=1
break 2 (a copy deleted):                  send-outreach: SKILL.md names references/drafting.md but it is not in the skill's own folder when installed alone   exit=1
break 3 (a copy edited by one character):  references/troubleshooting.md: send-outreach differs from generate-leads (copies must be identical)   exit=1
restored:                                  ok: 2 skills open every file they name when installed alone; shared reference copies are identical   exit=0
```
Not covered (carried over): `outreach.md` names two repo docs (`docs/06-token-contract.md`, `docs/07-compliance.md`) that are in no skill folder; the check
looks at what `SKILL.md` names, as the brief says.

## Item 5 (extra, started at minute 14 of the box) — the build backend pinned exactly

**Choice and reason.** From the plan's L5 paragraph I took "the build backend pinned exactly" because it is small, closes a hole on its own
(`pip install .` in CI and any isolated build fetch whatever `setuptools>=77` resolves to today, unhashed), and the hashed lock already carries
`setuptools==84.2.1`. Not taken: `doctor --fix` installing from hashed locks — it needs a new hashed extras lock for torch/GLiNER/crawl4ai/yt-dlp
generated from `uv.lock`, a job of hours: carried over.

**Must do (written before the change).** `[build-system] requires = ["setuptools==84.2.1"]` (the version `requirements.lock` and `uv.lock` pin; uploaded
2026-10-20, older than 7 days; >= 77 so the SPDX licence string still builds). `tests/test_plugin_lock.py` is extended: every build requirement is an
exact `name==version` pin and that version equals the one in `requirements.lock`, so a pin and the lock cannot drift apart. Seen red first: a pin to
another version, and a range put back.

**Check by reading, after; red/green.** `pyproject.toml` `requires = ["setuptools==84.2.1"]` equals the pin in `requirements.lock`; the test now needs an exact pin that
equals the lock. Red: `setuptools==84.2.0` → `AssertionError: build backend setuptools==84.2.0: requirements.lock pins 84.2.1`; `setuptools>=77` → `AssertionError: build backend
setuptools>=77 is not an exact name==version pin`; restored → `2 passed, 1 skipped` (the skip is the POSIX-sh launcher test, as before on this laptop). An isolated build with the pin
is exercised by the CI `pip install .` step (read it on the pull request).

## CI finding — a missing request line on Windows (run 43130540313, job `fake campaign · windows-latest`, commit a84aa37)

Output: `FAIL - differs from expected.json in: requests` / `.requests: expected 45 entries, got 44` / `only in expected: "northgate-tyres.example /about 200"`;
every other part of the result (sheet, steps, report) equal. The same fixture passed on the commit before (run 43130392812) and on Linux in both.
**Cause (written before the fix).** The fake world writes its request log from one handler thread per request, each doing `open(path, "a")` and one write.
On Windows that is not an atomic append: two threads can write at the same offset and one line is overwritten. Measured here with 16 threads x 300 lines,
three runs: `wrote 4800 lines, file holds 4160 / 4186 / 4133`. Adding the Companies House calls (a registry thread running next to the crawl workers)
raised the contention enough to show it on a busy runner. It is a defect of the harness, not of the tool: the page was fetched, its log line was lost.
**Fix at the cause.** The log writes take a module lock (`_LOG_LOCK` in `scripts/e2e_fake_campaign.py`); the same measurement with the lock: `wrote 4800, file holds 4800` ×3.
Not done: widening or ignoring the requests list. Whether the golden is now stable on a busy Windows runner is UNPROVEN until the CI run of the last commit.

## Carried over (noticed, not done)
- `doctor --fix` / `--fix --full` installing from hashed locks with `--require-hashes` (needs a hashed extras lock for torch, GLiNER, crawl4ai, yt-dlp generated from `uv.lock`).
- The NER job (L5 plan): not this slice.
- The company-mode discovery provider (`companies_house` discovery, a second company-mode ICP) is not in the fake campaign; only the registry lookup is.
- Tool behaviour seen in the fake-campaign run, unchanged: a registry hit is accepted at name similarity >= 0.45, and the lookup `continue`s past a dissolved company to the
  next hit. In the first run "Pennine Motors" matched "HARBOUR MOTORS LTD" (0.46, same city) and received its director. The code's own comment calls a wrong match worse than none.
- `outreach.md` names two repo docs (`docs/06-token-contract.md`, `docs/07-compliance.md`) that are in no skill folder.
- The two other wall-clock tests of the L4 list: `test_crawler_politeness.py::test_workers_12...`, `test_maps_list.py::test_parallel_queries_is_faster_than_serial`.
- `uv lock --check --offline` already reports `uv.lock` out of date on `master` (the project's own entry; the L4 list item "uv.lock's own entry to the real version").
- The socket guard still does not cover asyncio's Windows `ConnectEx` / native sockets (from the starting list).
- Item 4: `npx skills add ... --skill send-outreach` was not run (no outside call).

## Results of the local runs
- Whole suite, once, below-normal priority, serial, at the end: `846 passed, 6 skipped in 364.14s (0:06:04)`.
- `ruff check src tests`: `All checks passed!`; `check_versions.py`: all six places `0.7.3`; `check_skill_frontmatter.py`, `check_skill_references.py`, `check_digest.py`: ok; `gitleaks` on every commit: `no leaks found`.
- Fake campaign on Windows (this laptop), compared with the saved result: `PASS - result equals tests/fixtures/e2e/expected.json (21 refused-call entries, as saved)`; probe: `PROBE PASS`.

## CI on the pull request (#5), job by job
Each run is one commit; all 13 jobs per run (`claude plugin validate`, `Validate plugin manifests`, `Version strings agree`, `fake campaign` on ubuntu and windows, `test` on ubuntu/windows x py3.11-3.14).
- 75acdbb (items 0, 1, old saved result): 13/13 success; `fake campaign · ubuntu-latest`: `PASS - result equals tests/fixtures/e2e/expected.json (21 refused-call entries, as saved)`.
- 5dfecc3 (Companies House fake, new saved result): 13/13 success.
- a84aa37 (speed test): 12/13; `fake campaign · windows-latest` FAIL, one request line missing (cause and fix above); not re-run, fixed in 3a5b120.
- 9f5ee20 (send-outreach check): 13/13 success. 02645e5 (backend pin, changelog): 13/13 success.
- 3a5b120 (request log under a lock; ALL code of this slice as pushed): 13/13 success, both fake campaigns included.
- e92a63c (this slice file's carried-over part and one comment line in `config/leadforge.example.yaml`): BLOCKED, 13/13 failed in 5 s without starting. Annotation:
  "The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings."
  Re-run once (attempt 2): the same. Cause is the account's GitHub billing, not the code; nothing I may change. What unblocks it: the owner fixes billing / spending limit, then re-run run 43131901513.
  That commit differs from the green 3a5b120 only by the slice-file text and one YAML comment line (`git diff 3a5b120 e92a63c --stat`: 2 files, 18 insertions).

# Review (0.7.3)

Run `l5-read`, 2026-11-12, independent reader (did not see the build). Read: the brief `l5-build.md`, this file's Build part, the whole diff
`master...5b0a5bb` (26 files) in a fresh clone. Reading first; run only what reading could not settle, one process at a time.

**0. Linux DNS gap.** `sitecustomize.py`: `_is_local(host, port)` = loopback AND port != 53, used by the `connect`/`connect_ex` wrapper and by
`sendto`; a refused call is logged by the same `_refuse` as any outside call. The fake world's server is on port 18765, so it stays reachable.
`probe.py` adds UDP `sendto` and TCP connect to `127.0.0.53:53`; `--probe` now demands both in the guard log. CI read from GitHub, run
43131232137 (commit 3a5b120, the last commit with code): `fake campaign · ubuntu-latest` and `· windows-latest` both success, each log line
`PASS - result equals tests/fixtures/e2e/expected.json (21 refused-call entries, as saved)`. Saved `refused` list: 21 entries in 0.7.2 and in
0.7.3, equal (my leaf diff below). Holds.

**1. Companies House setting.** Default `CH_BASE_DEFAULT = "https://api.company-information.service.gov.uk"`, byte for byte the removed
`CH_BASE`; no other reader of `CH_BASE` is left (`grep`). The five request sites (registry: search, profile, officers; discovery: advanced
search twice) read the setting. The validator accepts only the default or `http`/`https` with host `localhost` or a loopback IP, refuses a
user part, password, query, fragment, bad port; a missing scheme fails (`urlsplit` gives no hostname, or a non-http scheme). `127.0.0.1.evil.example`
and `user@` forms are refused (tested). Redirects: every call is a plain `httpx.get` without `follow_redirects`, and httpx does not follow by
default, so a 3xx goes nowhere. The key is sent only with those five requests, as before; it can now go to the default or to this machine,
nothing else. One remark, not a defect: `localhost` is resolved by the hosts file, so a machine whose hosts file maps `localhost` elsewhere would
send the key there; a loopback IP has no such step.

**2. The fake.** The fake campaign's `leadforge.yaml` sets the fixture key and `http://127.0.0.1:<port>/ch`; the loopback server answers
`/ch/...` and 401s without the key. Source ON: the saved result now holds 14 new `/ch/` request lines (search, and profile + officers of ZZ000001
and ZZ000002). I compared the two saved results myself (`git show master:tests/fixtures/e2e/expected.json` against the branch, leaf diff, rows
matched by business name):
```
Leads/CSV  Harbour Motors: Score, Tier, DM Name, DM Title, DM Conf, Why This Score, Company No, Incorporated, Company Status, SIC Codes,
           Call Readiness, Fit, Contactability, Status, Next Action, Entity Type, Registry Name, Registry Match
Leads/CSV  Northgate Tyres: Score, Tier, Why This Score, Company No, Incorporated, Company Status, SIC Codes, Fit, Contactability,
           Entity Type, Registry Name, Registry Match
Leads/CSV  the other eight: Company No, Entity Type, Registry Name
Drafts     Harbour Motors: DM Name (rows reorder: Northgate now tier A)
Summary    tiers 0/5/5 -> 2/3/5, with DM 3 (30%) -> 4 (40%), next-action counts
steps      intake warning (key hint) gone; dm_unlabeled 2->1, dm_candidates 5->8, dm_auto_picked new (1), tier_a 0->2, tier_b 5->3
report     with_dm 3->4, tiers A 0->2, B 5->3
refused: old 21 entries, new 21, equal=True
requests: old 31, new 45; only in old 0; only in new 5 (distinct lines, all 127.0.0.1 /ch/... 200)
```
All inside the builder's second-run list. One cell named less precisely than the rest: Northgate's `Contactability` 25 -> 30. Cause read in
`score.py` (lines 353-356): an entity type `corporate_active` (from the registry match) adds the "registry-corroborated (active)"
contactability points. It follows from the predicted registry match, deterministically; not a surprise move.

**3. Speed test.** The fake `validate_email` counts in-flight calls under a lock and waits at `threading.Barrier(8, timeout=5)`. With 16 rows and
`max_workers=8`, each group of 8 opens the barrier only if 8 run at once, so the peak is exactly 8 on any machine; the assertion has no clock.
Serial (or any pool below 8): the barrier times out, `BrokenBarrierError` comes out of `fut.result()` in `validate_emails_parallel`, the test
is red. A pool above 8: the peak passes 8, `peak == workers` is red. Settled by reading; not run.

**4. `send-outreach` alone.** All five places in its `SKILL.md` now read `references/{outreach,drafting,troubleshooting}.md`; the three
files are in `skills/send-outreach/references/`, byte-identical to `generate-leads`' (`cmp`). Install routes: plugin (whole repo), `install.py`
(every skill folder, junction/symlink or `copytree` of the whole folder), a skills tool or hand copy (the folder) - in each the folder carries
`references/`, so every line resolves. The check, run here, then with one file taken away, then restored:
```
ok: 2 skills open every file they name when installed alone; shared reference copies are identical
exit=0
skill references broken:
  send-outreach: SKILL.md names references/troubleshooting.md but it is not in the skill's own folder when installed alone
exit=1
```

**5. Version, behaviour, packages, secrets.** `check_versions.py`:
`{'pyproject': '0.7.3', '__init__': '0.7.3', 'claude-plugin': '0.7.3', 'codex-plugin': '0.7.3', 'skill generate-leads': '0.7.3', 'skill send-outreach': '0.7.3'}`.
Tool behaviour: only the new setting (default = old address); the rest is harness, tests, skill text and the build pin `setuptools==84.2.1`
(the version already in `requirements.lock`); `requirements.lock` and runtime dependencies untouched: no new package. `zip(strict=True)` in
the script only runs on equal lengths. `gitleaks git --log-opts="master..slice/L5-install-proven"`: `11 commits scanned` / `no leaks found`.

**6. CI on the last commit.** 5b0a5bb (run 43132134170): 13/13 jobs failed in 2-4 s without starting; annotation `The job was not started
because recent account payments have failed or your spending limit needs to be increased.` Same for e92a63c. The last commit whose jobs ran,
3a5b120, is 13/13 success; 5b0a5bb differs from it only by this file and one comment line in `config/leadforge.example.yaml`. CI on the exact
commit to be merged is therefore NOT green: BLOCKED by the account's GitHub billing, not by the code.

Fixed by the reader: none.

Verdict: PASS 5b0a5bb
