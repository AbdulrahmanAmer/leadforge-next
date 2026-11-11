# L3c cleanup   (BUILT, review pending)
Type: product   Stacks: python   Version: 0.7.0 (not changed here; a patch version comes later, not from this slice)   Base: 4bb9e30 (tip of `slice/L2` when this branch was cut)
Guardrail: no   Owner: no
## Spec        (LEADFORGE-ADOPTION.md v1.1, section 9, row L3c; "mostly deletions")
Goal: dead modules and unused dependencies out; the old build plan (`icm/`, `docs/05-icm-build-plan.md`), `/finalize` and the bench scripts out
(with the "Build trigger" block of `AGENTS.md`); `fallback_rest` out; the owner's business names out of the defaults (examples stay examples); the
four duplicated skill reference files become one. Deletions only: nothing that stays is refactored, renamed or improved.
Pass lines: every golden still green and `node check.mjs` ends CHECK PASS; the built wheel still carries the scoring data; a search for the business
names finds only examples; for each deleted module a search shows nothing refers to it; additions are only this file and the merged reference file.
Gate changes: none.
Kept clear of the runs on `slice/L2` and `slice/L2b`: no edit to the politeness code, the golden tests, the agent command, the download/install code.

## Build       (builder: Sonnet 5.5, run l3c-build, 2026-11-11 16:15-17:00). Branch: `slice/L3c`, cut from `origin/slice/L2` (stacked: L2 is not merged yet).

### Commits (one per kind of deletion)
1. `bd17d3b` dead modules: `enrich/policy.py`, `enrich/adapters.py`, `tests/test_policy.py`, `tests/test_paid_adapters.py`, and `PaidEnrichmentCfg` / `Config.paid_enrichment`
   (only `adapters.py` read it). "Dead" proof: no import in `src/`, `bin/`, `scripts/`, `install.py`, `.github/`, skills or plugin manifests; the only importers
   were the two test files that exist for nothing else; `leadforge/enrich/__init__.py` re-exports nothing. A scan of every `src/leadforge/**/*.py` for importers
   (by dotted name, relative import, `-m`) listed exactly these two plus `__main__` (the `python -m` entry), `companies_house`, `dvsa`, `maps_list` and
   `fallback_rest`; the last four are loaded by name in `providers/base.py::_import_builtins` and are live providers (not dead), except `fallback_rest`, below.
2. `3214c13` `fallback_rest`: module, `FallbackRestCfg` and `discovery.fallback_rest`, the name in `_import_builtins`, its 3 tests in `tests/test_providers.py`
   (and the import block only they used), its mention in `tests/test_smoke.py`, the example config block. An old `leadforge.yaml` that still has a
   `discovery.fallback_rest:` block still loads (pydantic ignores unknown keys); one that lists `fallback_rest` in `providers:` now fails with
   `unknown provider 'fallback_rest'` (that is the removal). A generic test that uses a fake provider named "fallback_rest" now calls it "text_only".
3. `ae87a84` old build plan: `icm/` except `icm/SCOPE.md` (see decisions), `docs/05-icm-build-plan.md`, its diagram (`05-icm-stages.mmd/.png` and the README row),
   `.claude/commands/finalize.md`, the "Build trigger" block and the "read docs/05 first" bullet in `AGENTS.md`, the "old plan, do not follow" line in `CLAUDE.md`;
   dangling pointers fixed in `README.md`, `.claude/POSITION.md` line 5, the headers of `__init__.py`, `enrich/browser.py`, `providers/registry.py`, `providers/social.py`.
4. `04f8089` bench scripts: `scripts/bench/` (6 files), `scripts/bench_enrich.py`, `scripts/bench_speed.py` (one hard-coded the owner's campaign folder), plus the two
   comments in `config.py` and `enrich/extract.py` that named them.
5. `b283e5b` business names: the unused `GAINLEV_ICP_SIC` list in `company.py` (no reader anywhere; `config/icp.company.example.yaml` already carries the codes), and
   wording in docstrings, comments, skeleton headers, `README.md`, `icp-guide.md` ("GainLev's own ..." -> "an operator's own ...", "WE SCORE spec" -> "account_fit").
6. `beb2f03` skill references: `skills/send-outreach/references/{cli,drafting,outreach,troubleshooting}.md` were byte-identical copies of the `generate-leads` ones
   (same MD5 in pairs, checked). Deleted; `send-outreach/SKILL.md` points at `../generate-leads/references/...` (5 lines). `send-outreach/references/cli.md` was not linked from its SKILL.md.
7. `80fcd8a` three doc lines that named `fallback_rest` (`docs/02`, `docs/04`, `docs/PIPELINE-MAP.md`).

### Check
Before any change (tip of slice/L2, this laptop, uv-synced `.venv`, Python 3.12). First run, below-normal priority: the 60 s per-test timeout fired in
`tests/test_cli_contract.py::test_intake_error_digest` (a subprocess start starved on the busy laptop) and pytest-timeout killed the run:
```
FAIL  tests  674.1
CHECK FAIL sha=4bb9e30 tree=clean steps=4 skipped=0 secs=765
```
Run once more alone at normal priority, `PYTEST_ADDOPTS=--timeout=300` (only the per-test limit raised, for this laptop's load):
```
833 passed, 6 skipped in 332.91s (0:05:32)
CHECK PASS sha=4bb9e30 tree=clean steps=5 skipped=0 secs=340
```
After the change (same way). The run began at `beb2f03`; the three doc-only lines of `80fcd8a` were edited while it ran (no test reads `docs/`), so `sha=` below is the
final commit but the tests saw the code of `beb2f03`, which is identical in code:
```
826 passed, 6 skipped in 245.93s (0:04:05)
CHECK PASS sha=80fcd8a tree=clean steps=5 skipped=0 secs=254
```
833 - 826 = 7 = the tests of the deleted code (test_policy 2, test_paid_adapters 2, fallback_rest 3). Goldens, run alone afterwards:
```
tests/test_golden_contracts.py  26 passed in 6.75s
```
`gitleaks detect --log-opts origin/slice/L2..HEAD` (the 5 commits then): `no leaks found`. `ruff check src tests`: `All checks passed!` (inside check.mjs).
No new test was written (deletions only); no break-on-purpose round, per the owner's 14:35 rule.

### Proof output
Produced by `bash D:\homelab-work\l3c-b\proof.sh <clone>` (sections 1 to 3) and `uv build --wheel --out-dir dist` + `wheel_list.py` (section 4); build output deleted afterwards.
Hits that remain in sections 1 are in `docs/` pages that are history or plans (listed, not edited): `docs/08-decisions.md` (ADR evidence paths), `docs/UPGRADE-PLAN.md`,
`docs/specs/laya-integration.md`, `docs/09-v0.3-build-plan.md`; `CHANGELOG.md`, `.claude/POSITION-HISTORY.md` and the other slice files are excluded as history.
Section 2 hits: `config/icp.*.example.yaml`, `skills/.../drafting.md` ("GainLev tech" as an example sender) are examples; `tests/` use "GainLev" as a made-up sender name (examples);
the rest are pinned or listed under NOT DONE.

```
### 1. nothing refers to a deleted module (git grep at HEAD; history files CHANGELOG.md, POSITION-HISTORY.md and docs/slices excluded; docs/ listed separately)
--- enrich.policy / jurisdiction policy : git grep -n -i -E 'enrich[./]policy|JurisdictionPolicy|policy_for'
    hits: 0
--- enrich.adapters / paid enrichment : git grep -n -i -E 'enrich[./]adapters|AdapterRegistry|PaidEnrichment|paid_enrichment'
    hits: 0
--- fallback_rest : git grep -n -i -E 'fallback_rest|FallbackRest'
    hits: 0
--- icm build plan (everything but icm/SCOPE.md) : git grep -n -i -E 'icm/(HANDOFF|STATE|PROMPT|stages)|05-icm-build-plan|05-icm-stages|BUILD LEADFORGE'
docs/09-v0.3-build-plan.md:118:- Docs: `docs/02`, `03`, `04`, `06`, `07`, `08`; `README.md`; `AGENTS.md`; `skills/generate-leads/SKILL.md` (+ references); `CHAN
    hits: 1
--- /finalize : git grep -n -i -E '/finalize|finalize\.md'
    hits: 0
--- bench scripts : git grep -n -i -E 'scripts/bench|bench_enrich|bench_speed|gliner_bench|laya_bench|laya_dm_shadow|claude_proc_probe|worker_device_probe'
docs/08-decisions.md:138:(scripts/bench/laya_dm_shadow.py; copy of the parked UK campaign DB; 150 businesses, seed 7, with â‰¥2 distinct
docs/08-decisions.md:147:**Update 2026-09-25 â€” attempt 2** (scripts/bench/laya_dm_shadow_v2.py): attempt 1 overflowed Laya's documented
docs/UPGRADE-PLAN.md:37:Scripts: `scripts/bench/` (added with Layer 3).
docs/UPGRADE-PLAN.md:81:  and a per-call timeout. Probe: scripts/bench/claude_proc_probe.ps1.
docs/UPGRADE-PLAN.md:91:  `ner_fallback: 0`); startup ~30 s once per enrichment. Probe: scripts/bench/worker_device_probe.py.
docs/specs/laya-integration.md:909:- [ ] Benchmark: `python scripts/bench_laya.py` â€” verify targets met
    hits: 6
--- GAINLEV_ICP_SIC : git grep -n -i -E 'GAINLEV_ICP_SIC'
    hits: 0

### 2. owner's business names in tracked files (case-insensitive: gainlev, wescore, we score) - counts per file, then every hit under src/ config/ bin/ skills/ README AGENTS CLAUDE pyproject
.claude/POSITION-HISTORY.md:7
CHANGELOG.md:10
config/icp.company.example.yaml:4
config/icp.wescore.example.yaml:3
docs/03-data-model.md:3
docs/08-decisions.md:2
docs/09-v0.3-build-plan.md:3
docs/10-enrichment-phase0-baseline.md:2
docs/DM-PHONE-RESEARCH-ITERATIONS.md:4
docs/UPGRADE-MERGE-PROMPT.md:1
docs/specs/skill-v2.md:1
skills/generate-leads/references/drafting.md:1
skills/generate-leads/references/icp-guide.md:1
src/leadforge/config.py:1
src/leadforge/data/skeletons/client_campaign.yaml:1
src/leadforge/data/skeletons/gainlev_leadgen.yaml:2
src/leadforge/draft/skeletons.py:1
tests/fixtures/draft/expected_no_website.txt:2
tests/fixtures/draft/expected_registry_ltd.txt:2
tests/fixtures/draft/expected_stale_site.txt:2
tests/golden/draft_handoff.json:2
tests/outreach_helpers.py:1
tests/test_account_profile.py:3
tests/test_autopilot_integration.py:2
tests/test_company_mode.py:3
tests/test_config_autopilot.py:1
tests/test_db_v3.py:1
tests/test_draft_cli.py:13
tests/test_draft_gate.py:2
tests/test_draft_packet.py:22
tests/test_draft_service.py:8
tests/test_draft_template.py:2
tests/test_golden_contracts.py:1
--- hits in product paths:
config/icp.company.example.yaml:1:# Company-mode ICP (docs/09 Wave 2 H): GainLev's own client pipeline on Companies House, not Google Maps.
config/icp.company.example.yaml:6:campaign: gainlev-own-pipeline
config/icp.company.example.yaml:10:  sender: "GainLev"
config/icp.company.example.yaml:45:notes: "GainLev's own client-acquisition pipeline, scored with the company rubric (leadforge/company.py) â€” SIC overlap, incorporation age, new-director triggers, h
config/icp.wescore.example.yaml:1:# WE SCORE-style prospecting ICP (account_fit profile) â€” MENA, six target industries.
config/icp.wescore.example.yaml:6:campaign: wescore-mena-prospects
config/icp.wescore.example.yaml:10:  sender: "WE SCORE"
skills/generate-leads/references/drafting.md:17: "offer": {"what": "...", "value_prop": "..."}, "sender": {"from_name": "GainLev tech"},
skills/generate-leads/references/icp-guide.md:115:Full worked example: `config/icp.wescore.example.yaml` (MENA, six target industries).
src/leadforge/config.py:199:                                             # "gainlev_leadgen" is GainLev's own branded skeleton, not
src/leadforge/data/skeletons/client_campaign.yaml:2:# contract as gainlev_leadgen.yaml (see that file's header comment).
src/leadforge/data/skeletons/gainlev_leadgen.yaml:7:purpose: gainlev_leadgen
src/leadforge/data/skeletons/gainlev_leadgen.yaml:10:  - GainLev
src/leadforge/draft/skeletons.py:18:PURPOSES = ("gainlev_leadgen", "client_campaign", "follow_up", "re_engagement", "referral")

### 3. diff size vs origin/slice/L2
 60 files changed, 41 insertions(+), 2281 deletions(-)
files with added lines:
1	1	.claude/POSITION.md
4	4	README.md
1	3	config/leadforge.example.yaml
1	1	docs/02-architecture.md
1	1	docs/04-pipeline-behavior.md
1	1	docs/PIPELINE-MAP.md
2	6	skills/generate-leads/references/icp-guide.md
5	5	skills/send-outreach/SKILL.md
1	1	src/leadforge/__init__.py
1	17	src/leadforge/company.py
1	14	src/leadforge/config.py
1	1	src/leadforge/data/skeletons/client_campaign.yaml
1	1	src/leadforge/data/skeletons/gainlev_leadgen.yaml
1	1	src/leadforge/enrich/benchmark.py
1	1	src/leadforge/enrich/browser.py
1	1	src/leadforge/enrich/extract.py
1	1	src/leadforge/enrich/profile.py
2	2	src/leadforge/enrich/runner.py
2	2	src/leadforge/export.py
1	1	src/leadforge/intake.py
1	1	src/leadforge/models.py
2	2	src/leadforge/pipeline.py
1	1	src/leadforge/providers/base.py
1	1	src/leadforge/providers/registry.py
1	1	src/leadforge/providers/social.py
1	1	src/leadforge/score.py
1	1	tests/test_discovery_coverage.py
2	66	tests/test_providers.py
1	1	tests/test_smoke.py
```

### 4. the built wheel (`uv build --wheel`, 0.7.0), files and the scoring data
```
76 files in the wheel:
  leadforge/__init__.py
  leadforge/__main__.py
  leadforge/agent_runner.py
  leadforge/cli.py
  leadforge/company.py
  leadforge/compliance.py
  leadforge/config.py
  leadforge/dashboard.py
  leadforge/db.py
  leadforge/doctor.py
  leadforge/export.py
  leadforge/grid.py
  leadforge/intake.py
  leadforge/models.py
  leadforge/normalize.py
  leadforge/pipeline.py
  leadforge/score.py
  leadforge/util.py
  leadforge/data/category_aliases.yaml
  leadforge/data/scoring.default.yaml
  leadforge/data/skeletons/client_campaign.yaml
  leadforge/data/skeletons/follow_up.yaml
  leadforge/data/skeletons/gainlev_leadgen.yaml
  leadforge/data/skeletons/re_engagement.yaml
  leadforge/data/skeletons/referral.yaml
  leadforge/draft/__init__.py
  leadforge/draft/cli.py
  leadforge/draft/gate.py
  leadforge/draft/packet.py
  leadforge/draft/service.py
  leadforge/draft/skeletons.py
  leadforge/draft/template.py
  leadforge/enrich/__init__.py
  leadforge/enrich/benchmark.py
  leadforge/enrich/browser.py
  leadforge/enrich/byol.py
  leadforge/enrich/crawler.py
  leadforge/enrich/dm.py
  leadforge/enrich/extract.py
  leadforge/enrich/infer_email.py
  leadforge/enrich/metrics.py
  leadforge/enrich/ner_worker.py
  leadforge/enrich/profile.py
  leadforge/enrich/resolve_domain.py
  leadforge/enrich/runner.py
  leadforge/enrich/validate.py
  leadforge/outreach/__init__.py
  leadforge/outreach/approve.py
  leadforge/outreach/cli.py
  leadforge/outreach/doctor.py
  leadforge/outreach/email_gate.py
  leadforge/outreach/identity.py
  leadforge/outreach/plan.py
  leadforge/outreach/render.py
  leadforge/outreach/send.py
  leadforge/outreach/states.py
  leadforge/outreach/status.py
  leadforge/outreach/sync.py
  leadforge/outreach/transport/__init__.py
  leadforge/outreach/transport/base.py
  leadforge/outreach/transport/file.py
  leadforge/outreach/transport/smtp.py
  leadforge/providers/__init__.py
  leadforge/providers/base.py
  leadforge/providers/companies_house.py
  leadforge/providers/dvsa.py
  leadforge/providers/gosom.py
  leadforge/providers/maps_list.py
  leadforge/providers/registry.py
  leadforge/providers/social.py
  leadforge-0.7.0.dist-info/licenses/LICENSE
  leadforge-0.7.0.dist-info/METADATA
  leadforge-0.7.0.dist-info/WHEEL
  leadforge-0.7.0.dist-info/entry_points.txt
  leadforge-0.7.0.dist-info/top_level.txt
  leadforge-0.7.0.dist-info/RECORD

data files: ['leadforge/data/category_aliases.yaml', 'leadforge/data/scoring.default.yaml', 'leadforge/data/skeletons/client_campaign.yaml', 'leadforge/data/skeletons/follow_up.yaml', 'leadforge/data/skeletons/gainlev_leadgen.yaml', 'leadforge/data/skeletons/re_engagement.yaml', 'leadforge/data/skeletons/referral.yaml']

leadforge/data/scoring.default.yaml: 3148 bytes, sha256 57ca6009501c66c5cc3df98c62ef936661a17995d605d2b375fc06ce2ff0e8f2
--- first 12 lines:
# Default scoring rubric (docs/01 §5, docs/03, docs/09 "D — Scoring and export truth" v0.3).
# ICP `scoring.weights_override` merges over `factors.*.weight`.
#
# v2 (v0.3): `fit` is the ONLY thing that feeds `total`/tier. Reachability (DM/email/phone/registry) is
# no longer blended into fit — it is graded separately as `contactability` (0-100, a meta ScoreFactor,
# computed in score.py, never affecting total) so a hot-but-uncontactable lead and a lukewarm-but-
# call-ready one are never confused by one blended number.
version: 2
tiers: { a_min: 80, b_min: 60 }
negatives_cap: -40

factors:
leadforge/providers/fallback_rest.py in wheel: False
leadforge/enrich/policy.py in wheel: False
leadforge/enrich/adapters.py in wheel: False

source file sha256 (git, same bytes):
57ca6009501c66c5cc3df98c62ef936661a17995d605d2b375fc06ce2ff0e8f2 *src/leadforge/data/scoring.default.yaml
(build output dist/ and build/ deleted afterwards; `git status --ignored` shows neither)
```

### NOT DONE (left, with the reason)
- **Unused dependencies (`tenacity`, `rich`) stay declared.** Both are never imported (searched: `git grep -w -E "rich|tenacity"` over `src tests scripts bin install.py .github` finds only
  `src/leadforge/doctor.py:36`, which lists `"tenacity"` in `CORE_IMPORTS`). Dropping them needs a change to `doctor.py` (the install code owned by the L2b run) and a regenerated
  `uv.lock` + hashed `requirements.lock` (C3 files, same owner). `rich` is also pulled in by `typer`, so removing it only drops the declaration. Do it after L2b merges: delete the two
  lines in `pyproject.toml`, `"tenacity"` from `CORE_IMPORTS`, `uv lock`, `python scripts/make_plugin_lock.py`.
- **The `gainlev_leadgen` skeleton keeps its name and its `literals: - GainLev`.** The purpose id is pinned by `tests/golden/draft_handoff.json` and used in 6 test files; renaming it
  needs a golden change (L2's territory). Same for the "GainLev" test sender in `tests/`. The neutral default (`auto_purpose: client_campaign`) already exists. After L2: rename the
  skeleton, update the goldens, and delete the `config.py:199` comment that explains it.
- `config/icp.wescore.example.yaml` and `config/icp.company.example.yaml` keep the business names (examples stay examples). Renaming the wescore file would show as an addition.
- `scripts/code_index.py`, `scripts/code_index_eval.json`, `tests/test_code_index.py`, `.githooks/post-commit` and the `codeindex` extra: MAP 9.2 lists them as build-process leftovers, but the
  row L3c does not name them and removing the extra means editing `uv.lock`. `scripts/v03_gate.py` (named in README and CHANGELOG as the release gate) also stays. Owner's call.
- `social`, `dashboard`, `watch`, run-time installs: other slices (L3d, L3 later), not this row.
- Prose that still describes a REST fallback provider in general terms: `docs/02-architecture.md` lines 85 and 123, `docs/04-pipeline-behavior.md` line 92. A doc pass should rewrite them.
- `docs/09-v0.3-build-plan.md`, `docs/UPGRADE-PLAN.md`, `docs/UPGRADE-MERGE-PROMPT.md`, `docs/specs/*` are older plans; not named by the row; untouched.
- Dead-looking code in the L2 / L2b files: none found that was left only because of the fence (the deleted modules and `fallback_rest` live outside it).

### UNPROVEN
- `send-outreach` now reads its references from `../generate-leads/references/`. Works when the plugin is installed as a whole (both skills side by side, as both manifests ship them).
  A harness that copies one skill folder alone would miss them. Test that would settle it: install only `skills/send-outreach` through `npx skills add` on a scratch machine and open a reference.
- CI on GitHub for this branch: not run (no pull request; the reviewer opens it). The Ubuntu job never ran this code.
- The wheel was built with uv's isolated build environment (setuptools resolved from PyPI at build time into `D:\homelab-work\_cache`); its version was not recorded.

### Decisions taken on my own
- **Kept `icm/SCOPE.md`.** It is the scope statement and red-lines document, cited about 25 times by live code (`maps_list.py`, `infer_email.py`, `social.py`, `config.py` ...), skills and `AGENTS.md`; it is not a build plan.
  Moving it to `docs/` would add a file (pass line: additions only this file). Say so if you want it moved or deleted.
- Replaced dangling pointers to deleted files with shorter text instead of leaving them (one line each, listed under commit 3). That is where nearly all of the 38 added lines come from: each is a
  one-line replacement of a deleted-and-rewritten line (`git diff --numstat` in the proof). New files added: none besides this one. The "merged reference file" is not a new file: the surviving
  copy under `generate-leads/references/` is the single one.
- Editing comment lines in `pipeline.py` (2 lines) and `enrich/runner.py` (2 lines): comment text only, no code. These files are fragile and L2 touches nearby code, so a trivial textual conflict is possible at the reviewer's rebase.
- `.claude/POSITION.md` line 5 changed to stop pointing at the deleted `icm/STATE.md`. L2 runs may edit that file too; keep either side on conflict.
- Baseline re-run with `PYTEST_ADDOPTS=--timeout=300` and without below-normal priority after the first run died on the 60 s per-test limit (see Check); the final run used the same setting.
- Supply chain (`uv sync --extra dev --frozen` from the repo's own `uv.lock`, nothing added or upgraded): `osv-scanner scan source --lockfile uv.lock` -> `No issues found` (171 packages);
  none of the never-install list is present. Ages, from the lock's upload times: 5 of the 54 installed packages are younger than the 7-day rule: `typer 0.29.1` (2026-11-11), `annotated-doc 0.0.6`
  (2026-11-10), `markdown-it-py 4.3.0` (2026-11-10), `disposable-email-domains 0.0.293` (2026-11-09), `regex 2026.11.9` (2026-11-09). They come from the repo's lock, not from this slice, and
  were installed into the project `.venv` only. Publisher not checked per package. Worth a decision by whoever owns the lock (L1/L2b).

### Re-run
```
cd <clone>; git checkout slice/L3c; uv sync --extra dev --frozen
node check.mjs                        # tests step may need PYTEST_ADDOPTS=--timeout=300 on a loaded laptop
python -m pytest tests/test_golden_contracts.py
bash proof.sh <clone>                 # sections 1-3 (copy in this run's folder: D:\homelab-work\l3c-b\proof.sh)
uv build --wheel --out-dir dist       # then list the wheel; delete dist/ and build/
git diff --shortstat origin/slice/L2...HEAD
```
