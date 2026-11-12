# L8 Maps and social out (C17) — Unreleased

Branch `slice/L8-maps-out`, from `origin/master` 1050687 (0.7.3). No version string was touched; the changelog lines are under
"Unreleased". Plan: `L4-ONWARD.md` section 2 (L8), section 3; `LEADFORGE-ADOPTION.md` row L3d, C17, sections 7 and 8.

## What was built

**The seam (`providers/base.py`).** `get_chain` loads the built-in registers (`dvsa`, `companies_house`) and then calls every
installed package's entry point in the group `leadforge.providers` (`_load_addons`). A hook that fails to load is logged and
skipped, never fatal. A name nobody provides raises `provider '<name>' is not available: ...`. The field-name map every provider
is merged over (`DEFAULT_FIELD_MAP`) now lives here instead of in the Maps module.

**Moved to the private repository** `AbdulrahmanAmer/leadforge-maps` (package `leadforge_maps`, own `pyproject.toml`, README, MIT
licence, tests): the helper-driven provider and the list-first provider (both the same code, import lines and settings access
changed), the pinned helper download with its SHA-256 pins (was `doctor.py`), their settings (`proxies`, `depth`, `concurrency`,
`lang`, `timeout_min`, `stall_s`, the list provider's block), the made-up fixtures and the moved tests. A new console command
`leadforge-maps doctor [--fix]` is now the only thing that downloads the helper. The add-on also registers the plain name `maps`
as an alias of the helper-driven provider (the name the engine's "not available" message is asked for).

**Removed from the public tool:** both Maps modules, the `social` provider module and its test, `SocialCfg`, the social calls in
`enrich/runner.py`, the `[social]` extra and the `yt_dlp` entries of the doctor, the helper's `-email` switch (a red line, section 3;
not carried to the add-on), the helper checks and download in `doctor.py`, the doctor stamp's helper-version key, `GOSOM_VERSION`.
`DiscoveryCfg` lost the Maps keys and now keeps unknown keys (`extra="allow"`) so an add-on reads its own settings from them.

**Behaviour changes that follow:** the default provider is `["dvsa"]` (was the Maps helper); with only registers configured
`build_plan` emits the register queries and no text-search queries (nothing could answer them); the sheet's "Source" legend line
lost its "= Google Maps" gloss.

**Tests.** `tests/fakeprov.py` is a made-up provider (`fakelist`); the autouse fixture in `conftest.py` points the default chain at it
by env override. Every test that patched the Maps provider now patches that one; `source="..."` labels in tests changed; the saved
workspace golden was regenerated with the new label (same schema). `tests/test_provider_seam.py` is new. `test_maps_list.py` and
`test_social.py` left (the first moved). In `test_downloads_pinned.py` the helper tests moved; the "`run` with an old stamp opens no
socket" test now stops on a missing core dependency instead of the missing helper. Fake campaign: the invented list is served by a
harness provider `fixture_list` (was the Maps stand-in), `maps_listings.json` is `listings.json`, and the two steps that existed only
to get past the helper check (`run-unstamped`, `env-stamp`) are gone.

**Goldens that changed, each listed.** `tests/golden/sheet_export.json`: `Source` cell `gosom` -> `fakelist`. `tests/golden/workspace_current.sqlite3`
re-made (one business, source label). `tests/fixtures/e2e/expected.json`: `Source` column `gosom` -> `fixture_list` (7 rows, csv and tab), the
About-tab legend line, two steps removed (10 -> 8). Nothing else moved (refused list, request log, tiers, digests are equal) — the compare
before saving listed exactly those three kinds of difference and no other.

## Pass lines

**1. The C17 search finds nothing in the product tree.**
```
git grep -n -i -E "gosom|maps_list|maps-list|google[_-]maps[_-]scraper|proxies" -- . ':!docs' ':!icm' ':!CHANGELOG.md' ':!.claude/POSITION-HISTORY.md'
(no output)  hits=1 (git grep exit 1 = no match)
git grep -n -i -E "providers[./]social|yt.dlp|SocialCfg|cfg\.social|agent-reach" -- src tests scripts config skills README.md pyproject.toml
(no output)  hits=1
```
Still naming the moved code, listed and excluded on purpose (history, or pages L12 rewrites): `.claude/POSITION-HISTORY.md` 15, `CHANGELOG.md` 4
(old entries), `docs/00-vision.md` 1, `01-research.md` 8, `02-architecture.md` 8, `03-data-model.md` 3, `04-pipeline-behavior.md` 7, `07-compliance.md` 1,
`08-decisions.md` 13 (ADR text), `09-v0.3-build-plan.md` 3, `PIPELINE-MAP.md` 2, `docs/diagrams/02-architecture.mmd` 1, `icm/SCOPE.md` 2.

**2. Asking for Maps without the add-on prints "not available" and starts no browser** —
`tests/test_provider_seam.py::test_asking_for_maps_without_the_add_on_says_not_available_and_starts_nothing`: runs `leadforge --json discover --provider maps`
with `Popen`, `subprocess.run`, `playwright` and `crawl4ai` made to fail on use, asserts nothing was started, exit code non-zero, "not available" in the
output, digest `ok: false`. `tests/test_provider_seam.py`: `6 passed in 0.37s`. Seen red (each: the code it covers broken, test run, restored; the summary line
is `1 failed`, and the patch was checked to apply):
- message changed to "is unknown": the CLI test and the `get_chain` test fail.
- a `subprocess.Popen` call put on the unknown-provider path: the "starts nothing" test fails.
- add-on load error no longer caught: the "never takes the engine down" test fails.
- seam no longer calls the hook: the "found through the seam" test fails.
- registers-only guard removed from `build_plan`: the plan test fails. Default chain changed: the default test fails.

**3. The add-on, installed beside the engine in a throwaway venv, passes its moved tests.** Venv `D:\LeadForge\wt\L8-throwaway-venv`: the engine's hashed lock
with `--require-hashes --only-binary :all:`, then the engine and the add-on each with `--no-deps --no-build-isolation -e`, then pytest (unhashed, wheels only).
```
D:/LeadForge/wt/L8-throwaway-venv/Scripts/python.exe -m pytest -p no:cacheprovider      (in the add-on repository)
37 passed, 2 skipped in 6.45s
```
The two skips are the browser tests (no `playwright` in the venv). The add-on's seam test starts a fresh interpreter, shows `[]` registered before the engine's
seam runs and `['companies_house', 'dvsa', 'gosom', 'maps', 'maps_list']` after. Seen red: entry point pointing at nothing (`tests/test_seam.py` fails); the
add-on's register hook emptied (the fresh-interpreter test fails); the helper's `-email` switch put back (its test fails).

**Gates (public repository).**
```
python -m ruff check src tests                 All checks passed!
node check.mjs --ci   (run through the heavy lock)
  ok versions agree / ok skill frontmatter / ok skill references / ok lint
  812 passed, 5 skipped in 164.00s (0:02:43)
  ok cli digest
  CHECK PASS sha=1050687 tree=dirty steps=6 skipped=0 secs=168
python scripts/e2e_fake_campaign.py
  PASS - result equals tests/fixtures/e2e/expected.json (21 refused-call entries, as saved)
```
`gitleaks protect --staged --no-banner` on the staged tree (87 files): `no leaks found`. Same command in the add-on repository: `no leaks found`.
Not run here: the CI-only jobs (`claude plugin validate`, the Ubuntu and 3.11/3.13/3.14 legs, the non-editable install check); they run on the pull request.

## Plan against code: differences and the reading taken
- The plan says "the C17 search finds nothing in the public tree". Literally it does not: old design pages and history files still name the
  moved providers (list below). Reading taken: the search is held over everything that is product (src, tests, scripts, config, skills,
  README, manifests, CI) — zero hits — and the history files carry a note (docs 00-04, 07, 09, PIPELINE-MAP, icm/SCOPE) or are history by
  nature (changelog entries, ADR text, position history, this folder). L12 rewrites the pages. Not done here: rewriting them.
- The plan names "the proxy setting"; in code it is the `discovery.proxies` key (plus a free-text word "proxy" in unrelated comments and the
  config-redaction test). The key is gone; the unrelated word stays.
- The plan says the provider names are what the search covers; the add-on also registers the plain alias `maps` so a public test can ask
  for Maps without writing the old names. The plan did not ask for an alias; it is three lines in the add-on.
- The plan says the made-up Maps fixtures "move with the add-on". The profile-facts test in the engine (`test_discovery_coverage.py`) needs rows
  of that shape for `normalize` and `enrich`, so its fixture stays public under a neutral name (`profile_sample.ndjson`, made up, same content);
  the add-on carries its own copy. The fake campaign keeps an invented listings file for the same reason (it is what feeds the crawl cases).
- OpenStreetMap count: see below, NOT MEASURED.
- `normalize.py` still builds a `maps_url` from a `place_id` when a listing has one, and the sheet keeps its "Maps" column: that is the sheet
  contract (L7 changes it), not collection from Maps. Left.

## OpenStreetMap count
NOT MEASURED. The plan's count is one trade in one UK county from a downloaded regional extract file against the DVSA garages register for the
same county. Both numbers need a download from a third party (a Geofabrik extract, tens of MB, and the live register) and the brief forbids a live
request to a third party here. Nothing was estimated. To settle: download one county's extract file, count the garage-tagged places, count the register's
rows for the same county, write both numbers and their ratio ("half or more" gives OpenStreetMap its own slice).

## Not done / unproven
- UNPROVEN: entry-point discovery under the plugin launcher's private venv (the plan's named risk). Proven only in a plain venv here; the launcher builds
  its venv from the hashed lock and installs the engine without dependencies, so an add-on has to be installed into that same venv by hand.
  Test that settles it: the launcher's first run on a throwaway home, then `pip install` of the add-on into that venv, then `leadforge plan` with the
  add-on's provider named.
- UNPROVEN: the add-on's browser provider against a real page (`playwright` is not in this venv; two of its tests skip). The helper binary itself was
  never downloaded or run (no download in this slice).
- NOT DONE: the older design pages still describe the moved code (note added, not rewritten; L12).
- NOT DONE: an add-on hook for `leadforge doctor` (the add-on has its own `leadforge-maps doctor`).
- The signal names `stale_social`, `no_social_presence`, `no_video_presence`, `active_social` stay in the ICP vocabulary so old campaign files load; nothing sets
  them now.
- Dev tools (`pytest`, `ruff`, `pytest-xdist`, `pytest-timeout`) were installed unhashed with `--only-binary :all:` in the worktree venv, as CI's `.[dev]` does;
  they are not in the hashed lock.
- Old history keeps the Maps code and the three saved Google fixtures (public, not rewritten).
