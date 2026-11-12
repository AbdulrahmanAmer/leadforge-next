# LeadForge

> **Internal tool, not a product.** It is not offered to others as a service, and nothing here says it is safe to use on people's data without thought.
> Whether that label changes is the owner's decision.

## What it is, and is not

- LeadForge finds businesses in public registers, reads each business's own public website, scores the businesses against what you offer, and writes a sheet (`.xlsx`, `.csv`, `report.json`).
- Today the registers it ships are the DVSA list of MOT test stations and Companies House (a free key). Both are UK. No text-search source ships; a provider can be added as a separate package.
- The engine is Python with a command line (`leadforge`). The desktop window (Rust and Tauri core, React screens) starts that engine and nothing else.
- It keeps what it found for a set number of months (12 by default, 1 to 12), and can forget a person, suppress an address, purge, and delete everything.
- The window sends nothing and has no send action.
- The engine's command line does have an `outreach` group. `outreach send` writes `.eml` files and sends nothing unless `outreach.armed: true`, `--live` and `--i-am <name>` all agree. Nothing in the window calls it, and `run` never sends.
- It does not log in to anything, probe mailboxes, scrape LinkedIn or evade anti-bot measures. It reads `robots.txt` and leaves a site that answers 403 or 429 alone.
- It does not decide whether you may contact someone, give anyone a notice, or record consent. Those duties are the user's. [`docs/data-and-deletion.md`](docs/data-and-deletion.md) is not legal advice.
- Version 0.9.0, with unreleased work on this branch ([`CHANGELOG.md`](CHANGELOG.md)). Not everything is proven: see [Limits](#limits).

## Install

### The Windows app

**No installer is published yet.** `gh release list` for this repository printed nothing on 2026-11-12. Build it from source: [`docs/development.md`](docs/development.md).

What the installer is, as built today (Tauri's NSIS, `installMode: currentUser`):

- **Per user. No administrator right.** The installer asks for none. A silent install by an ordinary (not elevated) token passed with no administrator prompt (slice L11).
- **It puts** the app and the bundled engine (python.org's embeddable Python 3.12 and the hashed lock's packages) in `%LOCALAPPDATA%\LeadForge` by default. The proof installed into a folder it chose; the default folder is read from the installer's script and was not seen in a double-click install.
- **The app's data** is `%LOCALAPPDATA%\app.leadforge.window\`: the workspace (`workspace\`, with `leadforge_data\` inside), and a lock file. The window's own log and web view profile are kept under the user profile too (exact folders not checked).
- **Not carried:** the quality extras (no name-extraction model, no browser tier) and the `keyring` package, so the window cannot keep a key (see [Keys](#keys)).
- **It is unsigned.** Windows SmartScreen warns.
- **Remove it** with `uninstall.exe` in the install folder. The silent uninstall left no process, no file and no uninstall registry key behind. The uninstaller removes the app data folders only if you tick "delete app data"; otherwise your workspace stays. Use Data, "Delete everything" first if you want it gone. The entry in Windows' installed-apps list was not checked.

### From source, with the hashed lock (as CI does)

Python 3.11 or later.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.venv\Scripts\leadforge.exe --version
```

Optional extras: `.[browser]` (rendering for sites that refuse a plain fetch), `.[ner]` (local name and title extraction; fetch the model with
`leadforge doctor --fix --full`), `.[keyring]`, `.[dev]`. `doctor --fix` installs with pip and no hashes.

### As an agent skill

The repository is also a Claude Code and Codex plugin: manifests in `.claude-plugin/` and `.codex-plugin/`, skills in `skills/generate-leads` and
`skills/send-outreach`. `claude plugin validate` runs in CI. Installing it through a marketplace was not exercised for this repository: not checked.
`python install.py` from a clone installs both skills for the harnesses it finds (`--check` changes nothing). Install both skills together; a single-skill
install is not a supported route.

## The first campaign

### In the window

1. **Campaign:** type a kind of business ("car repair"), a place ("Bristol"), the country (`GB`), and what you offer in one or two lines. Choose "Check the plan". Nothing is collected yet.
2. **Start the run.** The **Run** screen shows six stages. "Stop the run" ends it between two businesses; "Continue the run" resumes it.
3. **Results:** "Open the sheet", or "Write it again".

All seven screens: [`docs/window.md`](docs/window.md).

### On the command line

Run in an empty folder; that folder is the workspace. Save this as `answers.yaml`:

```yaml
version: 1
campaign: bristol-car-repair
offer:
  what: "Online booking for independent garages"
target:
  categories: ["car repair"]
  geography: { areas: ["Bristol"], country: GB }
caps: { max_leads: 50 }
```

```powershell
leadforge intake --answers answers.yaml
leadforge plan --icp icp.yaml
leadforge run --icp icp.yaml
leadforge status
leadforge export --icp icp.yaml
```

`run` finds, reads, labels, scores, drafts notes and exports. By default it asks your own Claude Code in headless mode to label decision makers and write draft
notes (short snippets from business websites are in that prompt); `run --no-autopilot` or `agent.command: []` turns that off. A `run` that is interrupted continues with `leadforge run --icp icp.yaml --resume`.
Every command and option: [`skills/generate-leads/references/cli.md`](skills/generate-leads/references/cli.md).

**The sheet** has a Leads tab (score, tier, business, category, decision maker with title and confidence, phone, e-mail with a validity tier, website,
address, a "why this score" line, company number and status, and for every e-mail and phone the page it came from and the day), a Drafts tab (notes, never sent),
a Summary tab and an About tab that explains the columns.

## Where data lives

In the workspace, under `leadforge_data\` (`db.sqlite3`, `cache\`, `exports\<run>\`, `logs\`, the progress feed, `outbox\`, `inbox\`), plus hand-off and draft
files in the workspace folder itself. In the window the workspace is `%LOCALAPPDATA%\app.leadforge.window\workspace`. The full list, the tables and the sources:
[`docs/data-and-deletion.md`](docs/data-and-deletion.md).

## How to delete

- **Forget** a person or business: `leadforge forget <email, domain or name>`, or People, "Forget". Removes it everywhere the engine writes, then keeps it off new runs.
- **Suppress** an address or domain: `leadforge suppress add <value>`, or People, "Suppress". Deletes nothing; leaves it out of crawling, scoring and every sheet.
- **Purge** what is past the limit: `leadforge purge` (report), `leadforge purge --apply`, or Data. The first pass on a workspace only reports.
- **Retention:** `retention.months`, default 12, 1 to 12, counted from the run that first found a business. The clean-up runs at the start of every run and stops instead of deleting more than half.
- **Delete everything:** `leadforge purge --everything --yes`, or Data, "Delete everything". Sheets you handed to someone and files you wrote with `--out` cannot be reached.

What each one removes and cannot reach: [`docs/data-and-deletion.md`](docs/data-and-deletion.md).

## Keys

Two exist, both optional: the Companies House key (free) and an OpenCorporates token (off by default). **They are never read from `leadforge.yaml`**; a file that holds one is refused.
Set the environment variable `LEADFORGE_REGISTRY__COMPANIES_HOUSE_KEY` (or `..__OPENCORPORATES_TOKEN`), or store the key in the OS keyring (`pip install -e .[keyring]`, then
`keyring set leadforge registry.companies_house_key`). **Today the window cannot save a key**: the bundled engine has no keyring package. Use the environment. The DVSA register needs no key.
[`docs/configuration.md`](docs/configuration.md).

## Limits

Everything the slice files mark unproven, not done or open is in one list: [`docs/limits.md`](docs/limits.md). The ones that matter most:

- The installer is unsigned and not published, and its install is proven only as a silent per-user install into a chosen folder.
- The window cannot keep a key; the real keyring was never exercised.
- Only UK registers ship. No real service was reached by any test: the proofs use a loopback world of invented sites.
- The forgotten value stays, in clear, in the suppression list. A hashed list was not built.
- The Companies House terms, and OpenCorporates' `restricted_for_marketing` flag, are not settled.
- The older pages `docs/00` to `docs/04`, `07` and `09` describe earlier versions and code that has left; these pages and the code win.

## Documents

| Page | What it is for |
|---|---|
| [`docs/window.md`](docs/window.md) | the seven screens and the engine command behind each action |
| [`docs/data-and-deletion.md`](docs/data-and-deletion.md) | what is collected, kept, deleted, and what cannot be reached |
| [`skills/generate-leads/references/cli.md`](skills/generate-leads/references/cli.md) | every command and option |
| [`docs/configuration.md`](docs/configuration.md) | every setting, keys, registers, add-on providers |
| [`docs/development.md`](docs/development.md) | layout, set-up, gates, how a slice is recorded |
| [`docs/limits.md`](docs/limits.md) | everything not proven, not done or open |
| [`docs/slices/`](docs/slices/) | the record of each slice |
| [`docs/window-actions.md`](docs/window-actions.md) | the seam's contract between screens, core and engine |
| [`SECURITY.md`](SECURITY.md) | how to report a vulnerability |

## Licence and notices

MIT: see [LICENSE](LICENSE). Third-party packages keep their own licences; the notices of every package in the hashed lock are in
`src/leadforge/data/licences.json` and shown in the window under Settings, "About and licences". The DVSA list is published under the Open Government Licence v3.0:
"Contains public sector information licensed under the Open Government Licence v3.0." The Summary tab of a sheet repeats that sentence when a DVSA row is exported.
