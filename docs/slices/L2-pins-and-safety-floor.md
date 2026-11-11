# L2 pins-and-safety-floor   (IN PROGRESS: stopped at the track's time box)
Type: product   Stacks: python   Version: 0.7.0 (not bumped yet)   Base: 882aed8 (L1 merged)
Guardrail: yes   Owner: no
## Spec        (LEADFORGE-ADOPTION.md v1.1, section 9, row L2; may split into L2a / L2b)
Goal: made-up fixtures first; golden tests for every contract of section 3, each watched failing; then C1, C2 (printing), C3.
Gate changes: `tests/golden/**` (new).
## Build       (builder: Opus 5.5, inline, track E, 2026-11-11). Branch: slice/L2 in the PRIVATE copy.

### Done
1. **Fixtures made up (C17 part, ANSWERS Q1).** `tests/fixtures/maps_feed.html` (saved Google page, 202 KB, carried the alerted key) is now
   written by `tests/fixtures/make_maps_feed.py`: 12 invented cards, `.example` sites, Ofcom drama numbers (0115 496 0xxx), no Google script,
   no key (`git grep -c AIza` over the tree: 0 hits outside this proof's masked prefix). `gosom_sample.ndjson` (real Guildford firms) keeps
   its keys and value types with invented values (020 7946 0xxx, `FAKE_PLACE_ID_000n`). `gosom_gbp_sample.ndjson` was read: already made up
   (`.example`, 0161 496 0xxx, single invented first names); unchanged. The old bytes stay in history (not rewritten).
   Browser-free stand-in for the fixture test (selectolax walk + the real `parse_card`, same assertions):
   ```
   before (saved Google page): cards 40 parsed 40 cid 40 phone 40 website 25 unwrapped True rating 40 street 40 -> PASS
   after (made-up):            cards 12 parsed 12 cid 12 phone 12 website 8 unwrapped True rating 12 street 12 -> PASS
   ```
   Watched fail: one row's city set to Woking -> `AssertionError: assert 'Woking' == 'Guildford'`, 1 failed.
2. **Goldens** `tests/test_golden_contracts.py` + `tests/golden/*.json`: plugin contract (item 8), agent contract (item 2: the 22 command
   names, exit codes 1/3/4/5 and agent 4, the `LF_DIGEST ` prefix), sheet columns and order (item 4), scoring rules data by SHA-256 (item 9).
   Watched fail, all at once (codex plugin name, `InputError` exit code, first two columns swapped, one comment line in the scoring YAML):
   `4 failed, 4 passed`; reverted: `8 passed`.
2b. **Golden item 11** `test_golden_agent_command`: an operator's `agent.command` comes back verbatim; today's built-in autopilot argv is
   pinned in `tests/golden/autopilot_builtin_command.json` (it shows the hole C1 closes: no `--tools ""`, hooks disabled). Watched fail:
   `+ ["--x"]` appended in `resolve_command` -> `AssertionError ... == [...]`, 1 failed; reverted: 10 passed.
3. **C2 printing.** `config set|get` print `<hidden, N chars>` for any key ending key/token/secret/password; the value is still written.
   `tests/test_config_secrets.py` plants a fake key. On the old `cli.py`: `FAILED ...never_print_a_key, 1 failed, 1 passed`; after: `2 passed`.

### Check
```
792 passed, 6 skipped in 153.35s (0:02:33)
CHECK PASS sha=66c16d8 tree=dirty steps=5 skipped=0 secs=157      (dirty = this slice file only)
```
Tests: 782 passed at L1 -> 792 passed (10 new: 8 golden, 2 C2; +2 golden for item 11 after that run, file run: 10 passed), 6 skipped. CI not run on this branch (CI runs on pull requests; none opened).

### Not done (in order)
- Goldens still missing for section 3 items 1 (campaign file + hash), 3 (hand-off files), 4 (four tabs, "a cell is never empty", CSV mirror,
  `report.json` by running an export on a made-up workspace), 5 (resume), 6 (guardrails), 7 (provenance), 10 (a saved current workspace),
  (item 11 done, see 2b).
- C1 (autopilot tools off): its first step is the probe on today's code with `claude -p`; not run by this track (no `claude` starts here).
- C2 rest: the OpenCorporates token in the address (`registry.py:207`) - needs a check of the API's header support.
- C3 (pinned helper binary + SHA-256, model revision, no download inside `run`, hashed launcher lock).
- `test_crawler_politeness.py::test_workers_12_still_serializes_per_host_but_overlaps_across_hosts` failed again on CI (PR 2, Windows
  py3.12, sha 7230595; 793 passed): host A's FIRST gap was 0.25 s against a 0.4 s delay, exactly 0.25 in all three failures seen. Likely not
  noise but a real short first gap (robots.txt then the first page?). Investigate before calling it flaky. Other CI jobs on PR 2: green.
- Version 0.7.0 and the changelog line; CI on the branch; review; merge.

## Build (part B)   (builder: Opus 5.5, run l2b-build, 2026-11-11). Branch: slice/L2b from slice/L2 (4ed66ee).
C3, "nothing downloaded unchecked". Part A's files (politeness code and tests, goldens, C1) not touched.

### Done
1. **Helper binary pinned by version and SHA-256.** `doctor.GOSOM_SHA256` holds the three v1.17.4 assets (GitHub's asset
   digests; the Windows asset downloaded once into scratch, never run: `A1538350...FFB48`, the same). `gosom_verified` deletes a
   file whose hash differs before anything runs it; `download_gosom` uses only the pinned release URL (the API lookup and
   its fuzzy match are gone), hashes the `.part` file and deletes it on a mismatch. arm64 now asks for the amd64 asset by
   name (the pinned release ships no arm64 file; the old fuzzy match fetched the same file under an arm64 name).
2. **Model pinned by revision.** `ner_worker.MODEL_REVISIONS` (`urchade/gliner_small-v2.1` @ `4e091416cf7c3481db542c2a3d26156916f3a47f`,
   read from the Hub's model record, last modified 2024-04-10); the worker and the in-thread path both pass `revision=`;
   a model name without a pin is refused.
3. **`run` never downloads.** `ensure_ready` with an old stamp runs `run_doctor(cfg, network=False)`: no fix, no download, no
   pip, no GitHub probe, no DNS; a missing or refused binary stops the run with `gosom-binary (leadforge doctor --fix)`.
4. **Locked user install.** `requirements.lock` (uv export of uv.lock, runtime only, plus setuptools 84.2.1 from uv.lock as
   build backend; `scripts/make_plugin_lock.py` writes it). `bin/leadforge` installs `--require-hashes -r requirements.lock`,
   then the package `--no-deps --no-build-isolation`; it no longer upgrades pip. Real install from the committed tree into
   an empty folder (PyPI, pip cache inside the scratch area):
   ```
   > sh bin/leadforge --json version
   leadforge 0.6.15
   LF_DIGEST {"ok":true,"cmd":"version","run":null,"counts":{},"warnings":[],"artifacts":[],"next":null}
   exit=0 secs=481
   ```
5. Troubleshooting rows in both skills for the two new messages.

### Tests (11 new) and watched fails
`tests/test_downloads_pinned.py` (8) and `tests/test_plugin_lock.py` (3). Each guarded line was broken by a script that
asserts its target exists, the file run, then restored with `git checkout`:
```
=== 1. hash check removed (gosom_verified trusts any file)
FAILED tests/test_downloads_pinned.py::test_doctored_binary_is_refused_deleted_and_never_run
1 failed, 7 passed in 7.35s
=== 1b. download keeps a file whatever its hash
E       Failed: DID NOT RAISE EnvError
FAILED tests/test_downloads_pinned.py::test_download_with_wrong_hash_is_refused_and_deleted
=== 2. ensure_ready back to the fixing, networked doctor
E       AssertionError: run opened the network: ['create_connection(60,)', 'create_connection(8,)', "socket.sendto(b'...gmail\x03com...
FAILED tests/test_downloads_pinned.py::test_run_with_old_stamp_makes_no_network_call
FAILED tests/test_downloads_pinned.py::test_old_stamp_with_a_good_install_passes_offline_and_refreshes
=== 3. model loaded without its revision
FAILED tests/test_downloads_pinned.py::test_model_is_loaded_by_pinned_revision
=== A. a failed lock install is ignored (|| true): a changed hash no longer stops the launcher
E       AssertionError: an install with a changed lock hash must fail
FAILED tests/test_plugin_lock.py::test_launcher_install_refuses_a_changed_hash
=== B. the old launcher: upgrade pip, install the package with open-ended dependencies
E       AssertionError: the locked package was not installed from the lock
2 failed, 1 passed in 96.23s (0:01:36)
=== restored (script 1)
8 passed in 18.78s
```
(Socket list cut for width. Lines of the two scripts selected by a filter; full logs in the run's scratch area. The
`test_plugin_lock.py` restored state is the CI run below.)
The launcher test runs the real `bin/leadforge` under sh against a made-up plugin (local wheel, `PIP_NO_INDEX`), about
140 s on this laptop. Fake-key scan: `gitleaks git --log-opts="origin/slice/L2..HEAD"` -> `no leaks found`; pattern
search over the changed files: no match.

### Check
CI (workflow_dispatch, run 43024553507, sha 11ae970): all 11 jobs success; every test job
`805 passed, 6 skipped` and `CHECK PASS sha=11ae970`, Ubuntu and Windows, py3.11 to 3.14.
Local on STRIKERFORCE: `CHECK FAIL sha=11ae970 tree=clean steps=4 skipped=0 secs=1399` (pytest stopped at 80% with no
summary, the laptop shared with two other test runs); `pytest -n 4`: `5 failed, 799 passed, 6 skipped, 1 error` = 4+1 in
`test_ner_worker.py` (`worker did not become ready within 10.0s`, the same on the base code under the same load) and
`test_maps_list.py::test_parallel_queries_is_faster_than_serial` (timing). No test needs a browser here.

### Not done
- C3 still has one download inside `run`: GLiNER fetches the (now pinned) model on first use when the `[ner]` extra is
  installed. Closing it: load with `local_files_only=True` and fetch the model in `doctor --fix --full`. Not built.
- `scripts/bench/gliner_bench.py` still loads the model unpinned (a bench script; L3c deletes it).
- A local `CHECK PASS` on an idle laptop.
