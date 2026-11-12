# POSITION — where LeadForge actually is

Auto-injected at session start / compact / resume. The hook injects the **LAST `## ` block** (max 1400 chars),
so the newest block stays at the BOTTOM and stays short. Older blocks: `.claude/POSITION-HISTORY.md`.
Canonical detail: `CHANGELOG.md` (what shipped).

---

## POSITION — 2026-09-03 ~15:25, RUN PARKED BY OWNER ("stop the run right now and park all this ... we can continue later")

Heartbeat cron c9bd4fc9 DELETED; run process 16940 killed; DB backup leadforge_data/db.sqlite3.parked-backup.
State at park: 15,827 businesses; 1,099 of 10,069 sites crawled/attempted; registry checked ~1.9k; 534 DM-pending.
Run stage set to 'enriched' by hand and campaign draft.auto_max set to 120 (was 1500) so the owner can look at a
sheet now: `run --resume` (log leadforge_data/logs/park_export_stdout.log) -> labeling (runner) -> scoring ->
drafting (<=120) -> export under leadforge_data/exports/run_20260902_22032_7eca/.
TO CONTINUE LATER: in the campaign folder, `python -c "import sqlite3;c=sqlite3.connect('leadforge_data/db.sqlite3');
c.execute(\"update runs set stage='enriching' where id='run_20260902_22032_7eca'\");c.commit()"` then
`leadforge run --icp icp.yaml --resume --json` (enrichment is idempotent: it crawls the ~9k remaining sites, ~20/min
with bounded NER, then re-labels/scores/drafts/exports); restore draft.auto_max 1500 first for full drafting.

## POSITION — 2026-09-25 ~23:00, PARKED BY OWNER mid cleanup batch 2

- Owner: "park your session for the time being ... we will continue another time".
- master = cleanup batch 1 merged (6e06d3f..2f46476): 4 bug fixes + legacy/compat removal, suite 760 passed.
- Batch 2 (PIPELINE-MAP steps 5-13) builder STOPPED mid-work. Partial commits, if any, live on branch
  worktree-agent-ad9c35eb459d7f3ed: steps 5,6,7,8,10,11 committed (eebf7a4..a4b92d6), NOT yet verified by the
  orchestrator; 12 uncommitted file(s) in its worktree. Left to do in batch 2: steps 12, 13. Verify (suite +
  watched-fail) before cherry-picking onto master.
- Remaining: batch 2 (5-13), batch 3 (14-18), batch 4 (19,20,22). Spec: docs/PIPELINE-MAP.md section 6.
- NOT done at park: two stale  watcher processes from the old Laya training runs (started 02:07/02:22,
  ~1.7k CPU-s each) were left running — the owner declined the kill; ask before touching them.
- Owner decisions still binding: old data = statistics only (no compat); fix at source, no repair layers.
- 60+ commits unpushed to GitHub (owner decides).

## POSITION — 2026-11-11, slice L1 (0.6.15) in the private copy leadforge-next

- Work happens in the PRIVATE repo AbdulrahmanAmer/leadforge-next; `public-original` cannot be pushed to.
- L1 "installs again": selectolax<1.0, uv.lock, every version copy 0.6.15, check.mjs, pinned CI. Proof: docs/slices/L1-installs-again.md.
- Check: `node check.mjs` (782 passed, 6 skipped). Plan: claude-migration/design/blueprint/LEADFORGE-ADOPTION.md section 9.
- Next: L2 (fixtures made up first, then goldens, then the autopilot/keys/downloads floor).

## POSITION — 2026-11-11, slice L2 (0.7.0) reviewed, PR 2 open and ready, NOT merged

- slice/L2 = part A + part B (merged 8f388aa) + the review's fixes; head 4bb9e30 + this note. Proof: docs/slices/L2-pins-and-safety-floor.md (Review).
- Check: `node check.mjs` -> `CHECK PASS sha=4bb9e30 tree=clean` (833 passed, 6 skipped). CI run 43035660304: all 11 jobs pass.
- Verdict FIX 4bb9e30: one C3 blocker left, the `[ner]` model (and its unpinned deberta tokenizer) still downloads inside `run`.
- L2 is a guardrail slice: a second look before merge. Do not merge without it.

## POSITION — 2026-11-11, slice L2 (0.7.0): part C (NER download) merged, verdict PASS, PR 2 NOT merged

- slice/L2 = the above + slice/L2-ner (part C, merged 139ddef). Proof: docs/slices/L2-pins-and-safety-floor.md (Review of part C).
- Check: `CHECK PASS sha=7d5a2b1 tree=clean` (837 passed, 6 skipped). CI run 43044120999 on 7d5a2b1: all 11 jobs pass.
- Next: one more reader decides on PR 2. Do not merge master without it.

## POSITION — 2026-11-12, slice L6 (0.8.0) on branch slice/L6-the-delete-side, pull request 6, NOT merged

- Built: C4 forget, C5 purge (records and, since run l6-finish, files under exports and cache), C6, C7; reader's fixes in dc02236; l6-finish added the steady refused-call compare (G2), files expiry, forget on a held file (exit 4 + names), a hosted Linux mutation trial (KEEP).
- Gate: `node check.mjs` (901 passed, 7 skipped) at c5c5963; hosted CI 13 of 13 on c5c5963. Detail: docs/slices/L6-the-delete-side.md, part "Build 2 (0.8.0)".
- Open for the owner: a hashed suppression list (changes the tables; not built). An independent reader follows l6-finish; nobody merges before that.

## POSITION — 2026-11-12, slice L7 (0.9.0) on branch slice/L7-the-collect-side, pull request 9, NOT merged

- Built: C8 to C13 (stage A: robots, refusal final, switch gone, protected addresses off, one profile function; stage B: C12 source and date on every exported e-mail and phone, C13 send rules by country), 0.9.0 in every copy, `master` (0.8.0, debts, L8) merged in.
- Sheet contract changed: 8 columns at the end of Leads/CSV, 2 at the end of Drafts; goldens `sheet_columns`, `sheet_export` and the fake campaign's saved result (C12 cells only). Detail and the "Plan and code disagree" list (8): docs/slices/L7-the-collect-side.md.
- Open for the owner: which countries beyond US, GB, DE get a send rule (`send_rules.RULES`); Companies House terms page (UNPROVEN: none found); OpenCorporates only on the user's own paid key. An independent reader follows; nobody merges before that.
