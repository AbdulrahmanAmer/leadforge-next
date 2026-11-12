# Configuration

Every setting of `leadforge.yaml`, with its default, taken from `src/leadforge/config.py`. A setting you leave out has its default.
[`config/leadforge.example.yaml`](../config/leadforge.example.yaml) is a shorter, commented copy (one value in it differs from the code: see the end).

## Where settings come from

In this order, the last one winning:

1. the defaults below;
2. `leadforge.yaml` in the workspace folder (the folder you run `leadforge` in; in the window, `%LOCALAPPDATA%\app.leadforge.window\workspace`);
3. environment variables named `LEADFORGE_<SECTION>__<KEY>` (two underscores between the parts), for example `LEADFORGE_POLITENESS__DELAY_S=3`. The value is read as a YAML scalar.

Read or write one value without editing the file:

```powershell
leadforge config get retention.months
leadforge config set retention.months 6
```

`leadforge.yaml` is in `.gitignore`. An unknown key at the top of a section is ignored, except under `discovery:` (see below). A key in the wrong type is refused with a message.

## Keys (never in the file)

Two secrets exist, both in the `registry` section: `companies_house_key` and `opencorporates_token`.

- **They are refused in `leadforge.yaml`.** A workspace whose file holds one is refused with a message that names the setting, never the value. `leadforge config set registry.companies_house_key ""` clears one.
- **Environment:** `LEADFORGE_REGISTRY__COMPANIES_HOUSE_KEY` and `LEADFORGE_REGISTRY__OPENCORPORATES_TOKEN`. The environment is read first.
- **OS keyring:** read when the environment has no value and `registry.keyring` is true. Service `leadforge`, entry `registry.companies_house_key` or `registry.opencorporates_token`. The `keyring` Python package is an optional extra (`pip install -e .[keyring]`); without it only the environment works. It is in neither hashed lock, so the plugin's locked install and the window's bundled engine have no keyring: see [`limits.md`](limits.md).

```powershell
$env:LEADFORGE_REGISTRY__COMPANIES_HOUSE_KEY = "<your key>"
keyring set leadforge registry.companies_house_key
```

`config get` on a key says only whether it is set and where from. Nothing prints a key. A Companies House key is sent with every request to
`registry.companies_house_url`, so that setting accepts only the default address or one on this machine.

## Settings

### Top level

| Key | Default | Meaning |
|---|---|---|
| `data_dir` | `leadforge_data` | folder for all state, relative to the workspace. Keep it a plain name: a full path or `..` is taken too, and "Delete everything" deletes every file under it ([`limits.md`](limits.md)) |
| `default_region` | `US` | two-letter fallback for reading phone numbers |
| `progress_window` | `true` | a headless run opens a console with the live bar (Windows; skipped in CI and when `LEADFORGE_NO_UI=1`) |

### `discovery`

| Key | Default | Meaning |
|---|---|---|
| `providers` | `[dvsa]` | the registers, in order: `dvsa`, `companies_house`, or a name an installed add-on provides |
| `grid_mode` | `off` | `off` or `auto`; tiled queries, used only by a provider that supports tiles. `auto` also uses the public geocoder |
| `grid_cell_km` | `3.0` | tile size |
| `area_bbox` | `{}` | `[minLng, minLat, maxLng, maxLat]` per area name; skips the geocoder |
| `subdivide_at` | `100` | a tiled query returning this many listings is split into 4 |
| `max_subdivisions` | `2` | depth of splitting |
| `subdivide_min_new` | `3` | split only when the tile added this many new businesses (0 = always) |
| `est_min_per_query` | `2.0` | minutes per query, for the plan's estimate |
| `est_min_per_tiled_query` | `4.0` | minutes per tiled query |
| `parallel_queries` | `1` | discovery queries in flight at once |
| `dvsa.url` | the gov.uk CSV address | where the DVSA list is read |
| `dvsa.refresh_days` | `90` | age at which the cached copy is fetched again |
| `companies_house.page_size` | `100` | results per page |
| `companies_house.max_hits_per_shard` | `9000` | the API stops paging at 10,000, so a bigger slice is split |
| `companies_house.exclude_sic` | `["82200"]` | SIC codes left out of company mode |

`discovery.email_crawl` was removed and a file that holds it is refused. Other unknown keys under `discovery:` are kept: an add-on reads its own settings there.

### `crawl`, `politeness`, `validation`, `enrich`

| Key | Default | Meaning |
|---|---|---|
| `crawl.pages_per_site` | `6` | pages read per site |
| `crawl.headed_browser` | `false` | the browser tier opens a visible window (debugging) |
| `crawl.stale_after_years` | `2` | a copyright year older than this marks a site stale |
| `crawl.timeout_s` | `10.0` | the home page fetch |
| `crawl.page_timeout_s` | `6.0` | each other page |
| `crawl.site_budget_s` | `45.0` | wall-clock budget for one site's crawl |
| `crawl.max_text_bytes` | `400000` | text kept per page |
| `crawl.decode_protected_emails` | `false` | decode Cloudflare-protected addresses (an anti-harvesting measure; off) |
| `politeness.delay_s` | `2.0` | minimum gap between requests to one host, plus or minus 30 % |
| `politeness.workers` | `24` | different hosts crawled at once |
| `politeness.user_agent` | `LeadForgeBot/0.1 (internal lead research)` | sent to every site |
| `validation.dns_timeout_s` | `5.0` | MX look-up time limit |
| `validation.staleness_days` | `90` | drives the sheet's Stale? column |
| `validation.infer_emails` | `false` | propose a likely address, in its own column, never counted as found; no mail server is contacted |
| `validation.freemail_policy` | `linked` | which free-mail addresses count as the business's own: `linked`, `any` or `none` |
| `enrich.browser_concurrency` | `4` | browser renders at once |
| `enrich.rendered_pages_per_site` | `2` | rendered pages per site |
| `enrich.render_timeout_s` | `20.0` | one rendered fetch |
| `enrich.overlap_stages` | `true` | registry and validation overlap the crawl in `enrich --stage all` |
| `enrich.dns_workers` | `8` | MX look-up threads |
| `enrich.ner` | `true` | local name and title extraction; `false` uses the plain extractor. Needs the `ner` extra and a model fetched by `doctor --fix --full`; without them one warning and the plain extractor |
| `enrich.ner_parallel`, `ner_threads` | `2`, `2` | the in-thread fallback only |
| `enrich.ner_device` | `auto` | `auto`, `cpu` or `cuda` |
| `enrich.ner_batch` | `8` | requests grouped per model call |
| `enrich.ner_batch_wait_ms` | `25.0` | wait to fill a batch |
| `enrich.ner_timeout_s` | `30.0` | per request; on expiry the plain extractor is used |
| `enrich.est_website_share` | `0.64` | share of businesses assumed to have a site, for the plan |
| `enrich.est_crawl_rate_per_min` | `25.0` | sites per minute, for the plan |

### `registry`

| Key | Default | Meaning |
|---|---|---|
| `companies_house_key` | empty | see "Keys" above |
| `companies_house_url` | `https://api.company-information.service.gov.uk` | the default or a loopback address only |
| `opencorporates_token` | empty | see "Keys" |
| `opencorporates_enabled` | `false` | OpenCorporates takes its token only in the web address, so it is off unless you switch it on; its terms need your own paid contract |
| `keyring` | `true` | look in the OS keyring when the environment has no key |
| `min_name_similarity` | `0.45` | a registry hit must resemble the business name this much |
| `active_only` | `true` | dissolved companies are never matched |

### `export`, `retention`, `pipeline`

| Key | Default | Meaning |
|---|---|---|
| `export.formats` | `[xlsx, csv]` | files written (`report.json` is always written) |
| `export.auto_open` | `true` | open the sheet when an export finishes (skipped in CI) |
| `retention.months` | `12` | 1 to 12; shorten only. See [`data-and-deletion.md`](data-and-deletion.md) |
| `pipeline.autopilot` | `true` | `run` goes on through labelling, scoring, drafting and export without pausing |

### `agent`, `draft`

| Key | Default | Meaning |
|---|---|---|
| `agent.command` | `null` | `null` finds `claude` on the PATH; `[]` turns the agent off (built-in rules only); a list is run exactly as written, and what it lets the model do is yours |
| `agent.model` | `sonnet` | used only for the found command |
| `agent.timeout_s` | `900` | per call |
| `agent.batch` | `40` | items per call |
| `agent.max_batches` | `50` | hard stop per stage per run |
| `agent.isolate` | `true` | adds `--strict-mcp-config` and a settings string that disables hooks, for the found command |
| `agent.max_concurrent` | `2` | simultaneous calls |
| `draft.auto` | `true` | write draft notes during `run` |
| `draft.auto_purpose` | `client_campaign` | which skeleton the drafts use |
| `draft.auto_tiers` | `[A, B]` | tiers drafted |
| `draft.auto_max` | `500` | targets drafted per run |
| `draft.template_fallback` | `true` | template drafts when no agent is available |
| `draft.retries` | `1` | ask again once for drafts the gate rejected |
| `draft.packet_max_tokens` | `350` | size of one evidence packet |
| `draft.name_policy` | `gated` | `gated`, `never` or `always` |
| `draft.max_observation_words` | `45` | length cap of the observation |
| `draft.max_subject_chars` | `60` | length cap of the subject |

The found command is built with no tools. See [`data-and-deletion.md`](data-and-deletion.md) for what the agent is sent.

### `outreach`

Used only by the `outreach` command group. Nothing is sent unless `armed` is true and `--live` and `--i-am` agree.

| Key | Default | Meaning |
|---|---|---|
| `armed` | `false` | allow `outreach send --live` |
| `transport` | `file` | `file` writes `.eml` files; `smtp`; or a registered adapter |
| `require_corporate` | `false` | |
| `require_email_confirmation` | `false` | only addresses confirmed by licensed-provider check, delivery, reply or the operator |
| `send_window` | `09:00-17:00` | local time of `timezone` |
| `timezone` | `Europe/London` | |
| `follow_up_days` | `5` | |
| `bounce_rate_pause` | `0.03` | hard bounces over the last 100 live sends that pause sending |
| `complaint_rate_pause` | `0.001` | |
| `inbox_dir`, `outbox_dir` | `inbox`, `outbox` | under the data folder |

## Registers and add-on providers

`discovery.providers` lists what discovers businesses. The public tool ships two registers: `dvsa` (the DVSA MOT stations list, no key) and
`companies_house` (company mode, a free key). They run once per area, in the order listed.

A provider can live in a separate package. The engine calls every installed package that declares an entry point in the group `leadforge.providers`. The
entry point is a function; it registers its provider classes with `leadforge.providers.base.register` (a class with a `name`, `available()` and
`fetch()`). Then the provider's name works in `discovery.providers` and `leadforge discover --provider <name>`, and the package reads its own settings from
extra keys under `discovery:`. An add-on that fails to load is logged and left out. A name nobody provides stops with `provider '<name>' is not available` and
starts nothing.

An add-on has to be installed into the same environment as the engine. The plugin launcher builds its own environment from the hashed lock, so an add-on
must be put there by hand; that was proven only in a plain environment ([`limits.md`](limits.md)). No add-on is published with this repository.

## Where the example file differs from the code

`config/leadforge.example.yaml` says `crawl.timeout_s: 15` and calls its values the defaults; `config.py` has `10.0`. The code wins.
