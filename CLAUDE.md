@AGENTS.md

# Claude-only notes

LeadForge: a B2B lead-generation engine (Python CLI) driven by agents through two plugin skills.
Check everything with one command: `node check.mjs` (last line `CHECK PASS|FAIL ...`). CI runs `node check.mjs --ci`.

- This repo is a Claude Code plugin **and** its own marketplace: `/plugin marketplace add AbdulrahmanAmer/leadforge` ->
  `/plugin install leadforge@leadforge`. Local dev: `claude --plugin-dir .` and `claude plugin validate .`.
- The skill is namespaced `/leadforge:generate-leads` and auto-triggers on lead-gen requests via its description.
- Release = version bump. Plugin users stay on their cached copy until `.claude-plugin/plugin.json` `version` changes,
  so every version copy (pyproject, `__init__`, both plugin manifests, both skills) moves together; `check.mjs` fails otherwise.
- Rollback: before merge delete the slice branch; after merge `git revert -m 1 <merge>` plus a new patch version.
- Work is planned in slices: `docs/slices/`. Where the work stands: `.claude/POSITION.md`.
- `icm/`, `/finalize` and `docs/05-icm-build-plan.md` are the old, finished build plan. Do not follow them.
