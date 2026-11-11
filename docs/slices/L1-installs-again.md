# L1 installs-again
Type: product   Stacks: python   Version: 0.6.15   Size: ~250 lines without uv.lock   Base: 4506fbd
Guardrail: yes (gate files: check.mjs, CI workflow)   Owner: no
## Spec        (LEADFORGE-ADOPTION.md v1.1, section 9, row L1)
Goal: a fresh install works again; every version copy equal; the blueprint files in; no change in the code's behaviour.
Acceptance: the pass lines below. Gate changes: `check.mjs` (new), `.github/workflows/ci.yml`, `.github/scripts/check_versions.py`, `.github/scripts/check_digest.py`.
Out of scope: the three saved Google fixtures (L2, before the goldens), Maps leaving the repo (L3d), `/finalize` and `icm/` (L3c).
Changelog: "Installs again. This is the first update plugin users receive since 0.5.0 ... a workspace made by an older version is refused, as before."
## Build       (builder: Opus 5.5, inline, track E of the parallel build, 2026-11-11)
Branch: slice/L1 in the PRIVATE copy `AbdulrahmanAmer/leadforge-next`. Remote `public-original` has push URL `DISABLED`.
Changes: `selectolax>=0.3.21,<1.0`; `uv.lock` (uv 0.13.7) and `.python-version` 3.12; all six version copies 0.6.15;
`CLAUDE.md` = `@AGENTS.md` + Claude-only lines, old build trigger gone; `check.mjs` (blueprint v1.1.0); CI runs `node check.mjs --ci`,
actions pinned by commit hash, `permissions: contents: read`; `SECURITY.md`; `.claude/settings.json` (`worktree.baseRef: head`);
blueprint `.gitignore`/`.gitattributes` lines; owner wording; two test-only fixes (below). No file under `src/` changed except `__version__`.
Test-only fixes: `test_maps_list.py::test_available_never_launches_browser` skips when the optional `playwright` is absent (CI's `[dev]` never has it);
three `test_autopilot_integration.py` failure tests used `cmd /c` (Windows only) and now use the running Python, so they run on Ubuntu.
Installs (checked first): none system-wide. Project venv `.venv` made by `uv venv --python 3.12` (uv's own CPython 3.12.16, already on the laptop);
packages from PyPI per `pyproject.toml`; remove by deleting `.venv`. Launcher proof venv in the scratchpad, deleted afterwards.

### Baseline, before (commit 4506fbd, Windows 11, Python 3.12.16)
```
> uv pip install .                      -> + selectolax==1.0.2
> python -c "import leadforge.enrich.crawler"
ImportError: Modest backend is deprecated since selectolax 1.0. ...      exit=1
> python -m pytest -q                   -> 15 errors during collection (all: the same selectolax ImportError); 0 tests ran; 7.7 s
> python -m ruff check src tests        -> All checks passed!
```
### After (slice/L1)
```
> node check.mjs
ok  versions agree  0.2
ok  skill frontmatter  0.1
ok  lint  0.2
782 passed, 6 skipped in 182.40s (0:03:02)
ok  tests  184.1
leadforge --json version: 1 LF_DIGEST line(s)
leadforge --json status: 1 LF_DIGEST line(s)
ok  cli digest  1.7
CHECK PASS sha=4506fbd tree=dirty steps=5 skipped=0 secs=186      (run before the first commit: sha is the base, tree dirty)
```
Plugin launcher, empty data folder (`CLAUDE_PLUGIN_DATA` = new empty dir, file count 0):
```
> sh bin/leadforge version
leadforge 0.6.15
LF_DIGEST {"ok":true,"cmd":"version",...}        exit=0   stamp: 0.6.15
> <that venv>/python -c "import leadforge.enrich.crawler"   -> crawler imports; selectolax 0.4.13
```
Frozen user simulated: stamp set to 0.5.0 and 0.6.14 installed into the same venv, then the launcher of the 0.6.15 tree run once:
```
before bump: stamp=0.5.0 installed=leadforge 0.6.14
leadforge 0.6.15
after bump: stamp=0.6.15
```
Watched fails (each reverted at once):
```
send-outreach SKILL.md set to 0.6.14  -> FAIL  versions agree 0.2 / CHECK FAIL sha=6ab7dc3 tree=dirty steps=1 ... exit=1
`import os` appended to __init__.py   -> F401/E402 Found 2 errors. / FAIL  lint 0.3 / CHECK FAIL ... steps=3 ... exit=1
```
Secret alert (public repo alert #1, "Google API Key", open since 2026-09-03), read with the value masked:
the one distinct key sits in `<meta content="https://maps.google.com/maps/api/staticmap?center=...&key=AIza***...&signature=...">`,
i.e. the signed static-map address inside Google's own saved page. It is Google's page key, not the owner's.
The alert on the public repo was NOT dismissed (that repo is not touched); the owner closes it with this evidence. The file leaves in L2.
Map citations: 15 drawn at random (seed 20261111) from the 52 in `leadforge-map.md`: 15 hold; one (`registry.py:206`) is one line early
(the token-in-query line is 207).
Repo settings (private copy): Dependabot alerts ON (`PUT /vulnerability-alerts` -> 204). Private vulnerability reporting: GitHub
answers 404 on a private repo (the feature is for public repos); switched on for the public repo only at publish time (commands below).
Wording search (`partner|Striker|two owners|the owners` over tracked files) after: only intended lines remain:
`dm-labeling.md:33`, `enrich/dm.py:38` ("two owners" of a business), `compliance.py:21` (partnership), `extract.py:71` (job title
"partner"), `tests/test_extract.py` (`cmbpartners` test address), `tests/fixtures/maps_feed.html` (saved page; leaves in L2).

### Pass lines
| Pass line | State |
|---|---|
| Before: fresh `pip install .` fails to import the crawler; after: it imports | HOLDS (above) |
| Plugin launcher installs into an empty folder and prints a version | HOLDS |
| CI green in every job, Ubuntu and Windows, for the exact commit | HOLDS for f6a45d6: run 43012378892, all 11 jobs pass (8 test jobs Ubuntu+Windows py3.11-3.14, versions, manifests, plugin validate). Later commits change only `docs/slices/**` and `.claude/POSITION.md` |
| A session in the repo shows the `AGENTS.md` lines loaded | NOT RUN: no `claude` start in this folder before L2 (adoption plan rule), and the track may not touch the live config. Settle: in a lab `CLAUDE_CONFIG_DIR`, `claude` at the repo root, `/memory` lists `AGENTS.md` |
| The wording search of section 7 | HOLDS |
| The "versions agree" step fails when one copy is changed | HOLDS |
| A plugin install made before the bump updates after it | HOLDS for the launcher (venv reinstalls on the version change). Claude Code's own plugin-cache refresh UNPROVEN: needs `/plugin update` on a real pre-bump install |
| 15 map citations drawn at random hold | HOLDS (15/15) |
| Jay reads the other laptop's clone for unpushed work | NOT DONE: the other laptop is not contacted by this track. Must happen before L1 reaches the public repo |
CI history on this branch: run 43011757825 (6ab7dc3) FAILED: Ubuntu x4 on three `cmd /c` autopilot tests (fixed in f6a45d6);
Windows py3.11 and py3.12 each on one timing test (`test_crawler_politeness.py::test_workers_12_still_serializes_per_host_but_overlaps_across_hosts`
gap 0.25 s < 0.26 s; `test_maps_list.py::test_parallel_queries_is_faster_than_serial` 0.50 s). Those two are flaky on slow runners, not
changed here; the next run passed them. Named for L2's goldens work.
Coverage: not measured (no coverage tool in `[dev]`; not installed). Time: the suite takes 182 s serial on this laptop.
