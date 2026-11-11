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
- The flaky timing tests named in L1's slice file.
- Version 0.7.0 and the changelog line; CI on the branch; review; merge.
