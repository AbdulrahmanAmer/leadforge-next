# leadforge CLI reference (agent-facing)

Global: `--json` (digest line only) · `--data-dir PATH` (default `./leadforge_data`) · `--verbose` (debug log to the logfile) · `--version` (prints
`leadforge <version>` and exits) · exit codes: 0 ok (warnings allowed), 1 bug, 2 usage, 3 env, 4 input, 5 provider-fatal.

Checked against `leadforge --help` and each subcommand's `--help` (version 0.9.0). The settings are in `docs/configuration.md` of the repository, what
`forget`, `purge` and `suppress` remove is in `docs/data-and-deletion.md` (not links: a skill installed alone does not carry them).

Digest line (always last): `LF_DIGEST {"ok":bool,"cmd":str,"run":str|null,"counts":{...},"warnings":[...],"artifacts":[...],"next":str|null}`

| Command | Purpose | Key flags | Digest counts to watch |
|---|---|---|---|
| `doctor` | verify environment (pip deps, optional extras, network, disk); light/read-only by default | `--fix` (installs missing core deps), `--full` (with `--fix`: also NER + browser extras — several hundred MB, get consent first), `--strict` | `checks`, `fixed`, `failed` |
| `intake` | compile + validate `answers.yaml` → `icp.yaml` | `--answers F`, `--out F` | `errors` (0 required) |
| `plan` | show run plan without scraping | `--icp F` | `tiles`, `queries`, `est_max_results`, `est_runtime_min` (discovery), `est_enrich_sites`, `est_enrich_min` (crawl/enrich), `est_total_min` |
| `discover` | scrape listings → normalize → upsert | `--icp F`, `--limit N`, `--provider NAME` | `businesses`, `new`, `tiles_degraded` |
| `enrich` | crawl sites, extract + validate contacts, build DM candidates | `--icp F`, `--limit N`, `--stage all\|site\|registry\|validate\|backfill\|recheck` (default `all`) | `sites_crawled`, `contacts`, `dm_candidates`, `needs_browser` |
| `forget VALUE` | remove an e-mail address, a domain or a name from every table, the cache, logs, progress file, outbox, inbox, hand-off and draft files and the sheets in `exports`, then suppress it; exit 4 and the file named when a file could not be cleaned | the value (required) | `kind`, `rows`, `files_removed`, `files_edited` |
| `purge` | report (default) or delete the businesses past `retention.months` and the files that hold them; the first pass on a workspace only arms and reports | `--apply`; `--everything --yes` (wipes the data folder without opening the database; without `--yes` exit 2) | `state` (`report`, `armed`, `purged`, `nothing`, `no_workspace`), `expired`, `expiring_30d`, `total`, `deleted`, `files_removed` |
| `dedupe` | fold register rows into a list row with the same phone that looks like the same business; chains are never merged | `--dry-run` | counts |
| `byol import` | preview, or with `--apply` write, operator-supplied contacts matched conservatively to businesses already found | `--in CSV` (required), `--apply` | the import result's counts |
| `benchmark outcomes` / `benchmark dm-fields` | preview, or with `--apply` write, called-lead outcomes / confirmed decision-maker fields from a CSV, TSV or XLSX | `--in F` (required), `--apply` | `rows`, `matched`, `imported`, `duplicates`, `ambiguous`, `unmatched` |
| `window NAME` | the window's side of its seam: one JSON document on stdin, one on stdout; not for typing (see `docs/window-actions.md`) | none on the command line | none |
| `version` | print the version (same as `--version`, with a digest line) | — | digest only |
| `dm export` | write NDJSON batch of DM candidates for labeling | `--max N` (default 60), `--tsv`, `--out F` | `businesses`, `remaining`; artifact = batch path |
| `dm apply` | ingest labels | `--in F` | `applied`, `rejected`, `skipped` |
| `score` | rubric scoring + hooks | `--icp F` | `scored`, `tier_a/b/c`, `dq` |
| `export` | write XLSX + CSV + report.json | `--out DIR`, `--format xlsx,csv` | artifacts = file paths |
| `config set\|get KEY [VALUE]` | read/write one `leadforge.yaml` value (e.g. `agent.model`); a registry key is refused there, `get` says only whether it is set | — | counts.set |
| `run` | orchestrated: discover→enrich→**label→score→draft→export (autopilot, v0.4 default)**, resumable | `--icp F`, `--resume`, `--from-stage STAGE` (forces resume to start from STAGE; requires `--resume`), `--detach` (returns run id/pid/log immediately instead of blocking), `--limit N`, `--skip-dm`, `--autopilot`/`--no-autopilot` | `stage`, `dm_labeled`, `dm_unlabeled`, `drafted`, `draft_rejected`, `draft_abstained`, `runner` (`agent`\|`none`); `--detach` returns `pid`, `detached:true` and the log path as an artifact; use `status --run <run_id>` to follow it |
| `status` | current/last run snapshot: stage, whether a `--detach`'d process is alive, live progress | `--run ID` | `stage`, `businesses`, `pid`, `alive` (when detached), `progress_stage`, `progress_done`, `progress_total`, `eta_seconds` |
| `suppress add\|list` | opt-out list (domain/email/place_id); there is no remove action | value, `--kind domain\|email\|place_id` (default: guessed from the value) | `suppressed` |
| `dashboard` | local read-only status page: machine stages (discover/enrich/registry/validate) with measured pace + ETA, human/agent stages with item counts, every count behind them; `--open` opens the browser | `--port` (8765), `--open` | JSON at `/api/status` |
| `watch` | live bar for this workspace's run; pace and ETA from the feed's own clock (identical in every window) | — | prints a one-line summary on attach |
| `render-check URL` | diagnose one site: robots → plain fetch → browser → contacts; a URL robots.txt disallows is never fetched | `--force` (render even if the plain fetch worked) | `emails`, `blocked`, `rendered` |
| `outreach identity add\|list` | sending identities (from name/email, postal address, privacy URL, opt-out channel) | `--label`, `--from-email`, … | `id`, `live_complete` |
| `outreach mailbox add\|list` | mailboxes that send for an identity; secrets by env var NAME only | `--identity`, `--address`, `--transport file\|smtp`, `--config k=ENV`, `--daily-cap` | `id` |
| `prune-tiles` | skip queued subdivision children whose parent tile found nothing new (ADR-016) | `--min-new N` (3), `--all-children`, `--dry-run` | `pending`, `children`, `skipped`, `kept_parent_yielded`, `kept_parent_unknown` |
| `outreach plan` | enrol scored leads as outreach targets (entity type, lawful basis, suppression, chain dedupe) | `--campaign`, `--tier A,B`, `--identity` (all three required), `--icp`, `--run`, `--limit`, `--client` | `enrolled`, `no_sendable_email`, `entity_gate`, `chain_duplicate`, `suppressed` |
| `draft export` | one evidence packet per enrolled target for you to draft from | `--campaign` and `--purpose` (both required), `--icp`, `--max` (40), `--out`, `--redo`, `--run`/`--tier` (standalone) | `targets`, `grade_a/b/c`, `insufficient_evidence`; artifact = packet path |
| `draft apply` | ingest your drafts through the no-fabrication gate | `--in F`, `--packets F` | `drafted`, `rejected`, `abstained` |
| `draft render` / `draft check` | reviewable files / gate-only dry check | `--campaign`, `--out DIR` / `--in F` | counts |
| `outreach approve` | bind a human approval to each draft's content hash | `--campaign` and `--approver` (required), `--tier`/`--ids`/`--all-drafted` | `approved` |
| `outreach send` | **dry-run by default** (.eml files to the outbox); `--live` needs `outreach.armed` + `--i-am` | `--campaign`, `--dry-run`/`--live`, `--i-am`, `--mailbox`, `--max` | `would_send` / `sent`, `unknown`, `skipped_*`, `breaker_paused` |
| `outreach sync` | ingest bounces / complaints / unsubscribes / replies → suppression + states | — | `events`, `suppressed`, `replies` |
| `outreach status` | counts by state, caps consumed, breaker | `--campaign` | per-state counts |
| `outreach doctor` | SPF / DKIM / DMARC / MX / identity / warm-up checks, fails closed | `--identity` | per-check ok/FAIL |
| `outreach outcome add` | record a call/email result (feeds the outcome loop); `--result opt_out` also writes a suppression row | `--business`, `--channel`, `--result` (required), `--notes`, `--campaign`, `--by` | `outcomes` |

Notes
- **v0.4 autopilot (ADR-015):** `run` labels decision makers and drafts messages itself by default
  (`pipeline.autopilot: true`) — through the operator's own headless Claude Code (`agent.command` auto-detects
  `claude` on PATH; `agent.command: []` disables it) with deterministic fallbacks (`heuristic_labels`,
  template drafts) when no runner is available. `--no-autopilot` restores the v0.3 pause at `stage=dm_pending`.
  `agent.batch` / `agent.max_batches` bound how much the runner does per stage per run; `draft.auto_tiers` /
  `draft.auto_max` / `draft.auto_purpose` bound autopilot drafting; `draft.template_fallback: false` disables
  the deterministic drafter (autopilot then just skips drafting when no runner is available).
- `run` picks up an interrupted run for the same ICP hash automatically with `--resume`.
- `--limit N` caps NEW businesses processed this invocation — use for smoke tests (`--limit 10`); `caps.max_leads` is the
  per-run hard stop across resumes.
- `--json` may be written before or after the subcommand (v0.3); both spellings work.
- v0.3 discovery: `discovery.providers: [dvsa]` (the default) runs the DVSA MOT-station register as its own planned query per area; `discovery.grid_mode: auto` tiles areas and splits any tile that returns ≥ `subdivide_at`
  results; `discovery.area_bbox` bypasses the geocoder for a named area; `plan` reports `registry_queries`, `tiled_queries`,
  `est_runtime_min` and a worst-case subdivided estimate.
- v0.3 company mode (a named provider mode, not a default): `target.mode: company` + `sic_codes` in the ICP and
  `discovery.providers: [companies_house]` discover companies from Companies House by SIC × location; see `icp-guide.md`.
- Provider add-ons: a package that declares an entry point in the group `leadforge.providers` adds provider names to
  `discovery.providers`; without one installed, asking for such a name prints "not available" and nothing is started.
  The public tool ships no text-search provider.
- `discovery.parallel_queries: N` (any provider) fans discover queries across N provider-chain instances (each its own
  browser/subprocess) instead of one query at a time.
- Optional extras change behavior when installed: `[browser]` auto-covers `needs_browser` sites; configured registry keys add
  officer cross-checks. Digest `warnings` tell you when an extra would have helped.
- Config file `leadforge.yaml` (workspace, optional): provider order, politeness knobs, validation.staleness_days (drives the sheet's Stale? column). Write values with `leadforge config set <dotted.key> <value>`.
  Don't edit it unless the user asks; defaults are sane.
