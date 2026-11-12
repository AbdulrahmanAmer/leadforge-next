# What is not proven, not done or open

One list. Every item comes from a slice file in [`docs/slices/`](slices/), and the slice is named in brackets. Nothing here is softened:
the words UNPROVEN, NOT DONE and OPEN are the slice files' own. Items a later slice closed are left out (for example the Linux DNS gap,
L5; the OpenCorporates token in the web address, L9; the robots check on a redirect to another site, L7).

Read as of version 0.9.0 plus the unreleased work on this branch. When you settle an item, change this page in the same commit.

## Deleting data

- **The suppression list holds the forgotten identifier in clear.** A hashed list was not built. It is the owner's decision whether
  "finds nothing" should be literal. (L6)
- **Sheets you handed to someone, and files you wrote elsewhere with `--out`, cannot be reached** by forget, purge or delete-everything. (L6)
- **A sheet is deleted whole.** When a sheet holds an expired business, the rows of businesses that have not expired go with it; their
  records stay and `leadforge export` writes the latest run's sheet again. A name inside a longer name matches too ("Brindlewick Motors"
  inside "Brindlewick Motors Ltd"), so a sheet naming only the longer one can be deleted. (L6)
- **The 12 months can run longer than 12 months from the first sighting.** The clock starts at `first_run_id`, the run that created the row.
  When a register row is folded into a list row, the business carries the younger row's run. (L6, "Plan and code disagree" 2)
- **UNPROVEN in use:** in a workspace that repeats the same searches, new sheets list refreshed old businesses. Once those pass the limit,
  most files may hold one, and the automatic clean-up stops the run (the "more than half of the files" rule) until `purge --apply`. (L6)
- **Under `--json`, a start-of-run clean-up that could not delete a held file puts no file name and no warning in the digest.** Records are
  kept and the next pass tries again. (L6)
- **UNPROVEN:** the time to read a very large `exports` folder at the start of every run. (L6)
- **UNPROVEN:** the cost of the copy-based schema read under a live `-wal` file. (L6)
- **UNPROVEN:** the other 252 survivors of the mutation trial were not read one by one; one more run that prints `mutmut show` for them
  would settle it. (L6)
- **UNPROVEN:** one test of the suite is skipped in some runs (7 skips in the builder's run, 6 in the reader's); the cause was not found. (L6)
- **The private add-on's list provider did not get the "delete the raw scraper file once parsed" rule** (C6) when this repository did. C6 is not met
  for that provider until the add-on gets the same change. (L8)
- **Expiry covers `exports` and `cache` only.** Other state under the data folder (logs, the progress feed, hand-off files, browser profiles) is
  reached by forget and delete-everything, not by the retention clean-up. (read from `retention.py`: `EXPIRING_DIRS`; see also L7, which names
  the browser-profiles folder as state its first stage did not wire to purge)
- **`data_dir` is not held inside the workspace.** `leadforge.yaml` or `--data-dir` may name `..\x` or any full path, and `purge --everything` (the window's
  "Delete everything") deletes every file under it: a probe with `data_dir: '../someone-elses-folder'` removed `thesis.docx` and `deep\photos.zip`. OPEN: refuse
  a `data_dir` that is absolute or has a `..` part, or let delete-everything delete only a folder that holds LeadForge's database. (review)
- **Forget on a person's row does not forget the person.** The People screen offers "This address" (the default), "This name" and "The whole domain",
  one value per call. Forgetting the address leaves the person's name, title and page in `people`; forgetting the name leaves their address in `contacts`
  (review probe on the window's test workspace, 2026-11-12). Forget both values to remove both. OPEN: the change proposed is one "this person" target
  that forgets the name and every address tied to it. (review)
- **The retention clean-up does not reach `outbox\` and `inbox\`** (the `.eml` files of a dry-run `outreach send` hold the recipient's address and the
  text) nor the browser profile; only forget and delete-everything do. (review, `retention.py` `EXPIRING_DIRS`)
- **Forget finds a value only in plain bytes and inside `.xlsx` (zip) files.** A compressed file of another kind (a browser profile's cache or
  LevelDB, a `.gz`) that holds it is neither edited nor deleted, and forget still says it forgot. This matters for `browser-profiles\`, which forget
  walks (L7's "purge and forget do not touch it" is no longer true for forget; the retention clean-up does not touch it). UNPROVEN on a real profile. (review)
- **UNPROVEN:** the old rows of a test fixture that looked like real businesses are still in the git history of this public repository. Whether to rewrite
  that history is the owner's call. (L2, L3c, debts)

## Collecting

- **Companies House: UNPROVEN that it may stay as it is.** No formal terms page was found; only a rate limit (600 requests in 5 minutes). Settled by
  Companies House, or a lawyer, saying whether a terms page exists that the developer hub does not link. (L7)
- **OpenCorporates:** its terms need the user's own paid contract for a lead-generation business, and its data may carry a
  `restricted_for_marketing` flag. The code does not read that flag (`git grep restricted_for_marketing` finds nothing), so such rows are not kept out
  of an outreach list. The provider is off unless you switch it on. (L7, L9)
- **DVSA list:** the licence does not cover personal data, and some stations' telephone numbers may be a sole trader's. Lawful basis stays the user's. (L7)
- **The source address in the sheet is not always the address at collection time.** A `dvsa` row gives the list address configured at export time; a row from
  an add-on without an address gives the provider's name. The tables hold no per-row address. (L7)
- **Send rules by country:** only the US, the UK and Germany have a rule; every other country, and a business with no country, is "not eligible". No consent
  is recorded anywhere, so a lead that needs consent is never eligible. The UK rule treats an unmatched business as a sole trader; UNPROVEN how often that
  is wrong. (L7)
- **UNPROVEN by a test:** that the agent hand-off files (`dm export`, draft packets) carry no address cell. (L7)
- **A registry hit is accepted at a name similarity of 0.45 or more.** In the fake campaign "Pennine Motors" matched "HARBOUR MOTORS LTD" (0.46, same city) and
  received its director. The code's own comment calls a wrong match worse than none. (L5)
- **Seen in the fake campaign, not traced:** every crawled site's Site Status reads `redirects to <host>:18765` when the fake sites use an explicit port. (L4)
- **No cross-business robots cache.** The crawler object is made per business, so the 24-hour life of a robots answer shows only inside one business. (L7)
- **No size limit on a fetched page, and no block on private addresses.** A page is read whole into memory (a gzip body decompressed) before it is
  cut to `crawl.max_text_bytes`, and a public site's redirect to `127.0.0.1` or a home-network address is followed if that address has no robots
  rule against it. See the review's loopback probe in [`slices/L11-window.md`](slices/L11-window.md). OPEN: a streamed read with a byte cap, and a
  refusal of loopback, private and link-local addresses after each redirect. (review)
- **Hosts contacted by default:** the businesses' sites, the DVSA list's address, Companies House only with a key, DNS for MX look-ups, and
  Nominatim only with `discovery.grid_mode: auto`. Nothing else was found in the code; no test watches the whole set. (review, by reading)
- **One business can take up to 338.8 s under the defaults**, before waits for the render gate (which no setting bounds). A stop waits for the step in
  flight: 52.6 s in the worst case, plus the render-gate wait. UNPROVEN as a wall clock; a total deadline per fetch would be needed. (L11a)
- **The signal names `stale_social`, `no_social_presence`, `no_video_presence` and `active_social` stay in the campaign vocabulary so old files load.**
  Nothing sets them now. (L8)
- **OpenStreetMap count: NOT MEASURED.** One trade in one county, a downloaded extract against the DVSA register, was never counted; it needs a download from
  a third party. (L8)

## Keys and the agent call

- **The window cannot save a key.** `keyring` is an optional extra and is in neither `requirements.lock` nor `uv.lock`, so the bundled engine has none; the
  Keys screen says so. The plugin launcher's locked install has none either. Fix: regenerate the hashed lock with the extra. NOT DONE. (L9, L11)
  <!-- CHANGE WHEN the keyring lock (pull request 17) is in the bundle. -->
- **The window cannot use a key from the environment either.** The core passes the engine a fixed list of Windows variables and no `LEADFORGE_*` one, so a
  Companies House campaign cannot run from the installed window today. (review, `engine.rs` `ENV_KEEP`)
- **The window's engine has no `PATH`,** so a window run never auto-detects `claude` and uses the built-in rules. Before the review's fix it searched the
  workspace folder and `C:\bin` (a folder any account on the PC may create). Fixed on `slice/L11-window`; `doctor --fix --full`'s `crawl4ai-setup` look-up
  still searches the current folder first (Windows). OPEN for that one. (review)
- **A workspace's `leadforge.yaml` can run any program**: `agent.command` is used as written by every `run` with autopilot on. Run LeadForge only in a folder
  whose `leadforge.yaml` you wrote. (review, `agent_runner.resolve_command`)
- **UNPROVEN:** the real `keyring` package against a real Windows backend. Tests replace the backend; the real one was never read or written. (L9, L11)
- **UNPROVEN:** `--tools ""` through the real npm `claude.cmd` with `node.exe`. The proof used a fake shim with Python reading the argument. (L2, L9)
- **UNPROVEN:** that `--restricted` works with a subscription login. The probe could not log in; it neither confirms nor contradicts the code's comment. (L9)
- **An `agent.command` you set yourself is used exactly as written.** What it lets the model do is your responsibility. (L2, design)
- **Not covered:** a third-party log handler attached directly to `httpcore`. (L9)
- **UNPROVEN against the real libraries:** that the installed GLiNER takes `local_files_only`, that its backbone resolves offline, and that a model fetched
  by `doctor --fix --full` is all a run needs. If any is false the worker does not start and the heuristic extractor runs; nothing is downloaded. (L2)
- **`doctor --fix` and `doctor --fix --full` install with pip and no hashes.** A hashed extras lock was not made. NOT DONE. (L2, L5)

## Install and the window

- **No installer is published.** `gh release list` for the repository printed nothing on 2026-11-12. The installer is built from source. (L12)
- **The installer is unsigned.** Windows SmartScreen warns. (L10)
- **Proven for the installer:** a silent per-user install by a normal (not elevated) token into a folder the proof chose, then uninstall, with no process and no
  file left. **Not shown:** an interactive (double-click) install, the default per-user folder, a run, the sheet, forget, suppress, retention and purge in the
  INSTALLED app. The whole campaign walk is on a debug build. (L11)
- **The window's self-test was not seen to fail when its 20 s and 420 s bounds fire.** (L11)
- **The self-test does not walk** the dialogs, `sheet_open` or a failed run. In the campaign walk, purge-apply was not pressed (nothing was past the limit);
  suppressing was tried once. (L11)
- **The single-instance guard and the core's engine tests were not each watched failing** (the permission test was). (L10, L11)
- **The workspace folder cannot be changed from the window.** The core has no folder dialog; the Settings screen shows the folder as text. (L11)
- **`About.licence` can be null** when the package metadata has no licence field; the page then says the notices were not found. Not reached in an installed
  build. (L11a)
- **`KeyStatus.savedAt` is always null** (the keyring keeps no date) and **`Person.foundAt` was null until L7** wired a date; people without one read "not recorded". (L11a)
- **UNPROVEN:** a run's process id, handed to another process by Windows before `run_status` asks, would make a dead run read `running`. The process's
  start time would have to be stored beside its id. (L11a)
- **`people_list` reads every person.** 10,000 people answer in 1 to 2 s; beyond that UNPROVEN. A search once took 13 s on the same size and the cause was not
  found (two candidates, neither tested). (L11a)
- **The embeddable engine package carries `setuptools` and bytecode next to the sources;** trimming was not measured. PyInstaller was measured on `version` only
  and not chosen. (L10)

## Proofs that were not run

- **The fake campaign touches no real service:** not the real registers' addresses, Companies House, the browser tier, NER, the agent labeller and drafter, or a
  send. Each needs a real service, a key, a browser or a model. (L4)
- **The fake campaign's socket guard is a Python-level guard.** It does not stop a child that is not Python, a native socket call, or asyncio's Windows
  `ConnectEx`. (L4, L5)
- **UNPROVEN:** the crawl4ai start with the profile function's folder, and that the seeded `Local State` stops a failed Windows logon on a machine with an
  account password. No browser was started in these slices. (L7)
- **UNPROVEN whether** `doctor --fix --full` (which runs `crawl4ai-setup`) starts a browser that is not given a profile. (L7)
- **`prepare_profile` seeds only an empty folder.** A folder with a stray file and no `Local State` is handed out unseeded. The scan test asks that the module
  calls `prepare_profile`, not the function that starts the browser. OPEN. (L7)
- **UNPROVEN:** entry-point discovery of an add-on under the plugin launcher's private virtual environment. It is proven in a plain one only; an add-on has to be
  installed into the launcher's environment by hand. (L8)
- **UNPROVEN:** the private add-on's browser provider against a real page; its helper program was never downloaded or run here. (L8)
- **NOT DONE:** a `leadforge doctor` hook for add-ons. (L8)
- **UNPROVEN:** that a plugin update reaches an existing Claude Code install (`/plugin update` on a real pre-bump install). (L1)
- **NOT RUN:** a session in the repository showing the lines of `AGENTS.md` loaded. (L1)
- **Coverage is not measured.** (L1)
- **A fake-key scan limit:** `forget` and `suppress` ran without an argument in the unit scan, so their work path is scanned only through shared code; `dashboard` and
  `watch` were not run. (L9)
- **Wall-clock tests:** two timing tests failed on slow runners at times (`test_crawler_politeness` and a removed Maps one). The politeness one had a real short
  first gap, fixed with a test; `test_enrich_speed` was changed to count overlapping calls instead of a clock. A run on an idle machine is the settlement. (L2, L4, L5)

## Skills and installs of the agent route

- **UNPROVEN:** `send-outreach` installed alone (`npx skills add ... --skill send-outreach`) was not run. The skill now carries copies of the three files it
  points at, so by construction it opens them; a single-skill install is not a supported route. (L3c, L5)
- **`outreach.md` names two repository pages** (`docs/06-token-contract.md`, `docs/07-compliance.md`) that are in no skill folder. OPEN. (L5)

## Repository and old pages

- **NOT DONE:** the older design pages (`docs/00` to `docs/04`, `07`, `09`, `PIPELINE-MAP.md`, the plans and `docs/specs/`) still describe code that has left (the
  Maps and social providers, a REST fallback) or earlier versions. They carry a note, not a rewrite. These pages and the code win. (L3c, L8)
  Statements in them that are false today (review, 22 found, not a complete list): `00-vision` lines 10, 58, 86 (Maps is the source and its cap the
  constraint); `01-research` 55, 63 (gosom primary); `02-architecture` 20, 24, 59, 84, 87 (a gosom provider, the doctor installs gosom, a REST fallback);
  `03-data-model` 66, 126, 284 (`source` gosom, schema version 2: it is 7); `04-pipeline-behavior` 20 to 26, 87, 89 (gosom in the pipeline,
  `providers.discovery: [gosom]`: the key is `discovery.providers`, default `[dvsa]`); `07-compliance` 22 (Maps terms accepted) and 35 (purge on campaign
  end: it is `retention.months`, checked at each run); `08-decisions` ADR-001 (gosom primary); `09-v0.3-build-plan` 45, 54, 59 (schema 2, `providers/gosom.py`,
  `GOSOM_FIELD_MAP`).
- **The public tree still carries the Maps add-on's review path:** `enrich/runner.py` `_apply_gbp` (about lines 816 to 860) and `normalize.gbp_facts` turn a
  listing's reviews into people ("signed an owner reply on Google", a first name credited in three reviews). No provider in this repository fills
  `enrich.gbp`; only an add-on returning the old Maps field names (`providers/base.py` `user_reviews_extended`) does. OPEN, the owner's decision: move it
  into the add-on, or drop the review-name rule. (review)
- **Names a reader can trace:** the slice files name the build laptop's machine name and the private add-on repository. OPEN, the owner's call. A phone
  number in the 01483 area (not Ofcom's drama range) in `export.py` and `docs/03` was replaced by a drama-range one in the review; it stays in history. (review)
- **NOT DONE:** the old sender name is still in 30 files (a draft skeleton, tests, goldens and prose); renaming it moves two goldens and three expected texts. (L3c, debts)
- **The example campaign files keep their author's own business names.** They were left as examples. (L3c)
- **OPEN:** an alert from the secret scanner on an earlier public repository of this project (a Google page key inside a saved page, not a key of the owner) was
  not dismissed; the owner closes it. (L1)
- **NOT DONE:** a check of a second machine's clone for unpushed work before this reached a public repository. (L1)
- **The old public history keeps the removed Maps code and three saved Google fixtures.** Not rewritten. (L8)
- **Dev tools** (`pytest`, `ruff`, `pytest-xdist`, `pytest-timeout`) are installed unhashed with wheels only, as CI's `[dev]` does; they are not in the hashed lock. (L8)
- **Several packages in the lock were younger than 7 days when it was made** (for example `regex 2026.11.9`). Publisher not checked per package. (L3c, L7)

## Words and labels

- **The README calls LeadForge an internal tool, not a product.** Whether that wording changes is the owner's decision. (L12)
- **No lawyer has read these pages.** [`data-and-deletion.md`](data-and-deletion.md) describes controls; it is not legal advice and claims compliance with no law. (L12)
