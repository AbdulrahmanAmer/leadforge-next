# debts   (the plan's "L4 Debts"; the file the plan's list never got)
Type: cleanup   Stacks: python   Version: 0.7.3 (not changed; changelog lines are under "Unreleased")   Base: 1050687 (`origin/master`)
Guardrail: no   Owner: no

## Spec
Source: `design/leadforge/L4-ONWARD.md` section 2, paragraph "L4 Debts", and the reader's finding of 2026-11-12 that `tenacity`, `code_index`,
`v03_gate.py` were still there and that the paid-adapter removal (0.7.1) had no recorded check. The earlier slice files named `L4-refactor-proof.md` and
`L4-the-window-on-paper.md` are other slices; this one never had a file, and this is it.
Out of this slice (named in the brief): the sweep of the old sender/skeleton name across the tree (done last by the integrator), the three
timing tests of the plan's first sentence, the `AGENTS.md` load proof, the version-string edits.

## Item 1 — `tenacity` (and `rich`)
Claim checked: `git grep -w -E "tenacity|rich" -- src tests scripts bin install.py .github check.mjs skills` found only `pyproject.toml` (both declared) and
`src/leadforge/doctor.py:36` (`"tenacity"` in `CORE_IMPORTS`). NO module imports either. So the plan's "replace its uses" has nothing to replace and no retry helper
was written (a helper with no caller would be new dead code). Plan and code differ in `docs/02-architecture.md:115` and `docs/04-pipeline-behavior.md:86`, which
claimed tenacity retries (3 tries, exponential): no such retry exists; both lines now say so.
Done: both declarations removed from `pyproject.toml`; `"tenacity"` removed from `CORE_IMPORTS`; `uv lock --offline` (uv 0.13.7; it only removed packages, it
fetched nothing; the added lines are the project's own version and `provides-extras`) then `scripts/make_plugin_lock.py` (the script's own documented command, run with
the venv's python because `uv run` would sync an environment). `requirements.lock` lost exactly `tenacity` (3 lines) and the `via` comment of `typer`.
`rich` stays in the lock as typer's own dependency (so `git grep -w rich` still hits the lock; the declaration is gone).
`uv.lock`'s own `leadforge` entry now says 0.7.3 (it said 0.6.14); that is the "real version", not a bump.

## Item 2 — `code_index`, `v03_gate.py`, `codeindex` extra
Proof nothing used them: search `git grep -n -i -w -E "code_index|v03_gate|codeindex"` (excluding the lock) found: the files themselves, `tests/test_code_index.py`
(skipped unless faiss is installed), `.githooks/post-commit` (runs the index only if faiss is importable), `pyproject.toml`'s extra, README line 243 (release gate),
`docs/UPGRADE-PLAN.md` 50-55 (a dated log), and history lines in CHANGELOG and `.claude/POSITION-HISTORY.md`. Not in `skills/`, `.claude-plugin/`, `.codex-plugin/`,
`.agents/`, `.github/`, `check.mjs`, `bin/`, `install.py`. `v03_gate.py` used `dvsa_sample.csv` (item 3), nothing else.
Removed: `scripts/code_index.py`, `scripts/code_index_eval.json`, `tests/test_code_index.py`, `.githooks/post-commit` (the folder is gone), `scripts/v03_gate.py`, the
`codeindex` extra (and with it faiss-cpu, sentence-transformers, torch and numpy-only entries in `uv.lock`: 149 lines gone). README's gate line now says `node check.mjs --ci`.
`docs/UPGRADE-PLAN.md` carries a note that the tools were removed (the dated log is kept). CHANGELOG and POSITION-HISTORY lines are history and stay.
`.gitignore` keeps `.vector_index/` (harmless; the folder may still exist in old clones). Kept: `icm/SCOPE.md`.

## Item 3 — `tests/fixtures/dvsa_sample.csv`
Used by `tests/test_providers_dvsa.py` (two places) and formerly `v03_gate.py`. Origin UNPROVEN, so treated as real: its six rows had trading names, street
addresses and phone numbers outside the Ofcom drama ranges, i.e. they looked like real businesses (not quoted here). Replaced by six invented rows of the same shape
(same columns, same towns, same classes, same cp1252 apostrophe byte that the encoding test needs; made-up names and streets; phones in the drama ranges
`0113 496 01xx`, `0114 496 01xx`, `0117 496 01xx`). The postcodes were kept (they name an area, not a firm). The test file's expected names were changed with them;
`test_providers_dvsa.py`: 27 passed before and after. Two invented names first failed the acronym rule of `_title_case_name` (any word of up to three letters is
read as an acronym), so the fixture avoids short words. Old rows remain in git history (the repository is public; history rewriting is the owner's call: UNPROVEN
whether he wants that).

## Item 4 — `leadforge --version`
`cli.py`: one eager option on the root callback that prints `leadforge <version>`, the `version` command's digest line, and exits 0 (+9 lines). Test
`test_version_flag_prints_package_version` (`tests/test_cli_contract.py`) runs the real module in a subprocess. Seen red once: with `cli.py` stashed it failed
(`AssertionError`, no such option), with the change it passes.

## Item 5 — the check owed for the paid-adapter removal (0.7.1)
Old copy read only: `D:\LeadForge\leadforge` at 4506fbd.
- `src/leadforge/enrich/adapters.py` (`PaidEnrichmentAdapter`, `AdapterRegistry`, `register_builtin_adapters`): imported by NOTHING in `src/`, `scripts/`, `bin/`, `skills/`,
  `config/`; only `tests/test_paid_adapters.py`. `register_builtin_adapters` returned without doing anything in every branch; the default registry was empty.
  Its only reader of configuration was `Config.paid_enrichment` (`PaidEnrichmentCfg`), which nothing else read.
- `src/leadforge/enrich/policy.py` (`policy_for`, `JurisdictionPolicy`): imported by NOTHING except `tests/test_policy.py`.
- No command-line flag, no `leadforge.example.yaml` key and no skill text named either. (Search: `adapters|enrich.policy|policy_for|AdapterRegistry|PaidEnrichment|paid_enrichment`
  over every file of the old copy outside `.git`: only the four files above and `config.py`.)
- Result: removal was safe. The `licensed_provider` value of `email_stage` (models.py, email_gate.py) is a label, not an adapter, and stays.
- Dangling references in the NEW copy, all prose, fixed: `README.md:119` (said paid adapters are optional and disabled: now says there is no paid-provider code),
  `docs/10-enrichment-phase0-baseline.md` rows 28 and 30, `docs/UPGRADE-MERGE-PROMPT.md:74` (told an agent to preserve the boundary), `docs/DM-PHONE-RESEARCH-ITERATIONS.md:106`.
  Not changed, on purpose: `CHANGELOG.md` and `docs/slices/L3c-cleanup.md` (history), ADR-007's text in `docs/08-decisions.md` (it speaks of free registry adapters, Companies
  House and OpenCorporates, which exist), the `licensed-provider` wording of the email gate (a verification stage).
- A leftover `paid_enrichment:` key in an old user `leadforge.yaml` is ignored (`Config` has no `extra="forbid"`; recorded in L3c).

## Item 6 — this file
`docs/slices/debts.md`.

## The old sender/skeleton name (counted, not changed)
30 files hold the name (case-insensitive `git grep -l -i`, counted before this file was written; this file adds a 31st by listing them): `.claude/POSITION-HISTORY.md`,
`CHANGELOG.md`, `config/icp.company.example.yaml`, `docs/03-data-model.md`, `docs/08-decisions.md`, `docs/09-v0.3-build-plan.md`, `docs/slices/L3c-cleanup.md`,
`docs/slices/L4-the-window-on-paper.md`, `docs/specs/skill-v2.md`, `skills/generate-leads/references/drafting.md`, `skills/send-outreach/references/drafting.md`,
`src/leadforge/config.py`, `src/leadforge/data/skeletons/client_campaign.yaml`, `src/leadforge/data/skeletons/` (the skeleton file itself, named with it),
`src/leadforge/draft/skeletons.py`, `tests/fixtures/draft/expected_no_website.txt`, `tests/fixtures/draft/expected_registry_ltd.txt`,
`tests/fixtures/draft/expected_stale_site.txt`, `tests/golden/draft_handoff.json`, `tests/outreach_helpers.py`, `tests/test_autopilot_integration.py`,
`tests/test_company_mode.py`, `tests/test_config_autopilot.py`, `tests/test_db_v3.py`, `tests/test_draft_cli.py`, `tests/test_draft_gate.py`, `tests/test_draft_packet.py`,
`tests/test_draft_service.py`, `tests/test_draft_template.py`, `tests/test_golden_contracts.py`. Case-sensitive lowercase only: 27 files (the three prose-only
`GainLev` files `docs/08-decisions.md` and the two `drafting.md` differ). The two goldens and three expected texts are the ones the integrator will regenerate.

## Not done
- The three timing tests, the `gainlev_leadgen` rename, the `AGENTS.md` load proof: other slices or the integrator (see Spec).
- The plan's pass line `git grep -w -E "tenacity|rich|gainlev_leadgen|code_index|v03_gate"` finds only CHANGELOG lines: it still hits the lock (`rich`, via typer), the
  history docs (`docs/slices/*`, `.claude/POSITION-HISTORY.md`, `docs/UPGRADE-PLAN.md`) and the rename's files. Reading taken: history files are records and stay.
