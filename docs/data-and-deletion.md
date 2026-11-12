# Data and deletion

What LeadForge collects, where it keeps it, for how long, and what each delete control removes and cannot reach.

**This page describes behaviour and controls. It is not legal advice and it does not claim that using LeadForge complies with any law. The duties are the user's.**

Checked against the code of version 0.9.0 plus the unreleased work on this branch (`src/leadforge/retention.py`, `db.py`, `config.py`,
`cli.py`, `enrich/crawler.py`, `send_rules.py`) and the slice files L6 and L7 in [`slices/`](slices/). What a slice file marks as unproven is in
[`limits.md`](limits.md).

## What is collected, and from where

| Source | What is taken | Needs |
|---|---|---|
| DVSA "Active MOT test stations" list (gov.uk, Open Government Licence v3.0) | business name, address, phone, class; a copy of the list is cached | nothing |
| Companies House API (the registry stage and company mode) | company name, number, incorporation date, status, SIC codes, active officers' names and roles | a free key |
| The businesses' own public websites | up to `crawl.pages_per_site` (default 6) pages per site: e-mail addresses, phone numbers, links, people named on team and about pages (name, title), signals such as "no online booking" | nothing |
| Lists you bring (`byol import`, `benchmark outcomes`, `benchmark dm-fields`) | what is in your file, matched to businesses already found | your file |
| OpenCorporates | company and officer data | off by default; your own key and `registry.opencorporates_enabled: true` |
| A provider add-on you installed | whatever the add-on collects; it is outside this repository | the add-on |
| A public geocoder (OpenStreetMap's Nominatim) | the area names of the campaign, to find a map box | only when `discovery.grid_mode` is `auto` (the default is `off`) |
| DNS | MX look-ups for the e-mail domains found | nothing |

LeadForge does not log in to anything, does not read pages behind a login, does not scrape LinkedIn, does not probe mailboxes (no SMTP check) and
does not decode Cloudflare-protected e-mail addresses unless `crawl.decode_protected_emails` is set.

**Text sent to a model.** With `pipeline.autopilot` on (the default) `run` asks the user's own Claude Code in headless mode (`agent.command`, found on
the PATH when unset) to label decision makers and write draft notes. Short snippets taken from business websites are in that prompt. The call is built
with no tools. Switch it off with `agent.command: []` or `run --no-autopilot`; the built-in rules then do the work. The window starts the engine with a
short environment; whether it finds `claude` there was not checked. What leaves LeadForge this way is outside any delete control below.

## Where it is kept

The workspace is the folder LeadForge runs in. In the window it is `%LOCALAPPDATA%\app.leadforge.window\workspace`. On the command line it is the current
folder. State lives under `leadforge_data\` there (`--data-dir` or `data_dir` change the name).

| Path under the workspace | Holds |
|---|---|
| `leadforge_data\db.sqlite3` (and `-wal`, `-shm`) | the database, schema version 7 |
| `leadforge_data\cache\` | the register copy, the geocoder's answers, cached pages |
| `leadforge_data\exports\<run>\` | the sheet (`.xlsx`), its CSV copy and `report.json` |
| `leadforge_data\logs\` | `leadforge.log` (and 3 rotated copies), `agent_runner.log`, `<run>.detach.log` |
| `leadforge_data\progress.jsonl`, `pace.json` | the live progress feed |
| `leadforge_data\outbox\`, `inbox\` | `.eml` files written by `outreach send` (dry run) and the spool `outreach sync` reads |
| `leadforge_data\browser-profiles\` | browser state, when the browser tier ran |
| `leadforge_data\bin\`, `.doctor_ok.json` | the doctor's stamp; not personal data, kept by every delete control |
| `dm_batch*`, `dm_labels*`, `drafts_packets*`, `drafts*.ndjson`, `drafts\` | hand-off and draft files, in the workspace folder itself |
| `campaigns\<name>\` (window only) | the campaign file the window wrote: `answers.yaml`, `icp.yaml`, `window.json` |
| `leadforge.yaml` | your settings; it never holds a key |

Database tables: `runs`, `queries`, `businesses`, `contacts` (e-mail addresses and phone numbers with a validity tier), `people` (name, title, page,
snippet, label), `evidence`, `enrichment_observations` (each value with its source page, evidence, confidence, verification state and date), `scores`,
`suppression`, and the outreach tables `sending_identities`, `mailboxes`, `outreach_targets`, `messages`, `events`, `outcomes`, plus `meta`. The outreach
tables stay empty unless you use the `outreach` commands.

Every exported e-mail address and phone number says where it came from and when (columns ending `Source` and `Date`; "source not recorded" when the
workspace holds no record).

## How long: retention

- `retention.months`, default **12**, range **1 to 12**. You can shorten it, never lengthen it. The window's Data screen and `leadforge config set retention.months <n>` change it.
- A business and everything attached to it expires when it is that many months past the start of the run that first found it. A refresh does not renew it.
  The records go, and so does every file under the data folder's own `exports` and `cache` that holds it. Nothing else expires: not logs, not the progress feed, not hand-off files.
- The clean-up runs at the start of every `run` (and in the window, at the start of every run it starts). Its three protections:
  1. **Armed.** A workspace is "armed" once it holds the marker `retention_armed_at` in the `meta` table. The first clean-up that finds a database writes the marker and **only reports**: records and files are not deleted. `leadforge purge --apply` on an unarmed workspace does the same.
  2. **A 30-day notice.** Every run says how many records (and files) expire in the next 30 days.
  3. **Never more than half.** If more than half of the businesses, or more than half of the files in `exports` and `cache`, are past the limit, the automatic clean-up deletes nothing and the run stops with exit 4, naming `leadforge purge --apply`. A clock set a year ahead looks like this. The explicit `purge --apply` has no such stop.
- A half-upgraded workspace (a missing table or column, an unreadable marker) stops the command, exit 4, with the file unchanged. A workspace with another schema version is refused by every command and not changed.
- Files go before records. If a file cannot be deleted (another program holds it open), no record is deleted either, the file is named, and the next pass tries again.
- `leadforge purge` alone only reports.

## The four controls

| Control | Command, and in the window | What it removes |
|---|---|---|
| **Forget** one person or business | `leadforge forget <email, domain or name>`; People screen, "Forget" | every row that holds the value, in every table, and what hangs on it; a business whose own name, address or web columns hold it is deleted whole with everything attached; a value found only in a business's `enrich_json` or `hours_json`, a query text or a run's stats is replaced by `[forgotten]`; every line holding it in the logs, progress feed, `.jsonl`, `.ndjson` and `.tsv` files; every other file holding it (also inside an `.xlsx`) is deleted, in the data folder, the outbox and inbox, the hand-off and draft files and the sheets in `exports`. Then the value is added to the suppression list, so a new run does not collect it again. Then the database file is rewritten (`secure_delete`, checkpoint, `VACUUM`). |
| **Suppress** an address or domain | `leadforge suppress add <value> [--kind domain\|email\|place_id]`; People screen, "Suppress" | deletes nothing. The value is kept on a list and left out of crawling, scoring and every export (a suppressed address in any cell of any tab is replaced by `[suppressed]`, and a draft addressed to it is dropped). There is no command to take a value off the list. |
| **Purge** what is past the limit | `leadforge purge` (report), `leadforge purge --apply`; Data screen, "Check again" and the delete button | the expired businesses and their files, as above. |
| **Delete everything** | `leadforge purge --everything --yes`; Data screen, "Delete everything" | every file under the data folder except `bin\` and `.doctor_ok.json`, and the hand-off and draft files in the workspace folder. It does not open the database, so it works on a workspace of any age or schema. It does not delete `leadforge.yaml`, your campaign files or `campaigns\`. |

`forget` names every file it changed or removed (by path, never by content). If a file could not be cleaned it exits non-zero, names the file and never says it
forgot. The engine's window command `person_forget` has a dry run that changes nothing and says what would go; the Forget dialog does not offer it (L11).

## What these controls cannot reach

- **Sheets you already handed to someone**, and any file you wrote elsewhere with `--out`: they are yours and are never touched.
- **Copies you made**: backups, synced folders, e-mail attachments.
- **Text already sent to a model** by your own agent command, and anything your own provider add-on keeps.
- **The suppression list itself.** It holds the forgotten value in clear, because that is how the objection is honoured on the next run. A byte scan of the
  workspace after `forget` finds the value in that one row and nowhere else. A hashed list was not built (an owner's decision, L6).
- **The user's own `sending_identities` and `mailboxes`** are not touched by forget.
- **Look-alikes in both directions.** A name is matched with word edges, not inside a longer word; but a sheet naming only "Brindlewick Motors Ltd" matches an
  expired "Brindlewick Motors" and is deleted whole, and a sheet holding one expired business is deleted with the live rows it holds. Their records stay;
  `leadforge export` writes the latest run's sheet again. `leadforge purge` lists the files before anything goes.
- **The expiry date can be later than 12 months after the first sighting** when a register row was folded into a list row that is younger.
- **Browser state** is not expired; forget and delete-everything walk it as part of the data folder (not tested for a browser profile).

## On the collect side: robots and refusals

- `robots.txt` is read for every address, also one a redirect leads to, with up to 512 KiB read. A 4xx answer means "no rules" and allows; a 5xx or no answer forbids. An answer is kept at most 24 hours.
- One request in flight per host, with at least `politeness.delay_s` (default 2.0 s, plus or minus 30 % jitter) between requests. The user agent says `LeadForgeBot/0.1 (internal lead research)`; `politeness.user_agent` changes it.
- **A refusal is final.** A site that answers 403 or 429 is left alone: no second try in a browser. A site its robots.txt disallows is never fetched or rendered.
- Caps from the campaign (`caps.max_leads`, `max_sites`, `max_tiles`) are hard stops.
- Country is required on every campaign; an area that looks vague (for example "downtown") gets a warning from `intake`.

## What the tool does for the user's duties, and what it does not

It keeps the source and date of every contact detail it exports. It keeps an opt-out list that it honours when it crawls, scores and exports. It expires
what it found and can forget a person. It sends e-mail only to countries it has a rule for: the US (opt-out), the UK (companies; a sole trader needs consent)
and Germany (consent); every other country, and a business with no country, shows "not eligible". It records no consent. It sends nothing from the window.

It does not give anyone a notice that they are in your list. It does not judge whether you may contact a person. It does not decide your lawful basis.
Telephone numbers from a register may belong to a sole trader. Those duties are yours.

The engine's command line has an `outreach` group (identities, mailboxes, plan, approve, send, sync, doctor, outcome). `outreach send` writes `.eml` files
and sends nothing by default; a live send needs `outreach.armed: true` in `leadforge.yaml`, `--live` and `--i-am <approver>`. The window has no send or outreach action.
