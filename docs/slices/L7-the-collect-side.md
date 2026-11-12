# L7 The collect side (C8 to C13)

Branch `slice/L7-the-collect-side`. Stage A (this run, `l7a-build`) builds what does not touch the tables, the
exports, the sheets or the send path, and sets no version. Stage B continues the same branch after L6 is merged.

## Findings at the top

The terms of each remaining source, read on 2026-11-12 with a plain GET of each page (saved and stripped to text; every quote below
is a sentence of that text, not from memory). Nothing is removed in this slice. Summary: **3 may stay (one of them only on a condition),
0 must leave, 0 pages that could not be read; user lists have no terms page at all.**

1. **Companies House API - may stay (UNPROVEN: no formal terms page was found).**
   Read: `https://developer.company-information.service.gov.uk/developer-guidelines` (200) and
   `https://developer-specs.company-information.service.gov.uk/guides/developerGuidelines` (200), also the hub's get-started page and the
   specs introduction. They carry no condition on what the data is used for. The only conditions: "You can make up to 600 requests within a
   5 minute period." and "We reserve the right to ban without notice applications that regularly exceed or attempt to bypass the rate limits."
   (plus key-handling advice). The hub's footer has "Policies" with one link, to cookies; a guessed `/terms-and-conditions` answered 404.
   The footer's "Crown copyright" link was not followed. Settled by: Companies House (or a lawyer) saying whether a terms page exists that the
   hub does not link.
2. **DVSA active MOT stations list - may stay, with two conditions.**
   Read: `https://www.data.gov.uk/dataset/87de9bf8-b936-44ff-89c4-f69f8f9bb9c1/mot-test-centres` (200: "Publisher Driver and Vehicle Standards
   Agency ... Licence UK Open Government Licence (OGL)") and the licence, `https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/` (200).
   Quotes: "You are free to: ... exploit the Information commercially and non-commercially for example, by combining it with other Information,
   or by including it in your own product or application." / "You must (where you do any of the above): acknowledge the source of the Information
   in your product or application ..." / "Contains public sector information licensed under the Open Government Licence v3.0." / "This licence
   does not cover: personal data in the Information;".
   Condition A (not met today): the attribution. `git grep -i "Open Government Licence"` finds nothing in the repository; the sentence belongs in
   the README / `docs/COMPLIANCE.md` (L12) and, better, in the export's Summary sheet (stage B touches the sheets). Condition B: the list carries
   telephone numbers of stations, some of which may be a sole trader's; the licence does not cover personal data, so lawful basis stays the
   user's (README, L12).
3. **OpenCorporates - may stay ONLY on the user's own paid key; the head should decide the default.**
   Read: `https://opencorporates.com/terms-of-use-2/` (200) and `https://opencorporates.com/legal-information/enterprise-api-terms-of-service/` (200).
   Quotes: "For the avoidance of doubt, financial institutions, corporations, government departments and regulatory authorities are not Permitted Users."
   / "If you are not a Permitted User, and you wish to use OpenCorporates or access our company data, you must enter into a separate contract with us
   to purchase the right and permission to use OpenCorporates and access or use company data." / "The OpenCorporates API may be used only with an API
   key. API keys are available in two ways: free of charge to Permitted Users (share-alike keys) and for a fee under our non-share-alike API terms
   ... for example for use in commercial or proprietary applications." / "Using any automated system (e.g. scraping) to extract data for any purpose
   other than search engine indexation;" is prohibited. From the API terms: "No product or service usable by any third party may make use of our API
   in order to function" (internal-use licence) and "Where the `restricted_for_marketing` field has been set in any API data returned to you ...
   you ... may not use the restricted data for marketing or advertising purposes in any event."
   So the terms do not forbid this use, but a lead-generation business needs its own paid contract, and the tool must say so. Two things the code
   does not do today (both belong to L9, which already holds the OpenCorporates provider): it does not read `restricted_for_marketing`
   (`git grep restricted_for_marketing` finds nothing), and nothing tells the user a paid key is required. Recommendation: the provider stays off
   unless the user has set their own key AND confirmed a paid contract in the config; rows carrying `restricted_for_marketing` never reach an
   outreach list.
4. **User lists - no terms page exists** (the user's own files). Nothing to read; their lawful basis is theirs (L12's README).

## The one request (item 9)

2026-11-12T09:04:01 (local, UTC+02:00), one GET with the body thrown away, to the address in `discovery.dvsa.url`
(`https://assets.publishing.service.gov.uk/media/69a0638bc497bac082bc7741/active-mot-stations.csv`): **status 200, 2,391,015 bytes, content type
`text/csv`, 1 redirect** to a newer file (`.../media/6abcee45943e890cb55e5d00/active-mot-stations.csv`). The address is live and the loader
(`providers/dvsa.py`, `follow_redirects=True`) follows the redirect, so no change is needed. No other request went to any source.

## Spec

Copied, not reworded.

### The plan's paragraph (`L4-ONWARD.md`, "L7 The collect side (C8 to C13)")

> **L7 The collect side (C8 to C13).** As ADOPT row L3b, plus: the robots check on a cross-site redirect hop tested against the loopback server
> (L2 UNPROVEN); one profile function for every browser the product starts; the terms page of each remaining source (Companies House, DVSA,
> OpenCorporates, user lists) read and quoted in the slice file, and a source whose terms forbid this use leaves (section 3); one request to the
> DVSA list's address to see it is live. Leaves out: Maps (L8). Pass lines: ADOPT's C8 to C13 tests; a 403 starts zero browsers; the redirect test
> fails when the hop's robots check is removed. Fakes: loopback server playing robots 4xx, 5xx, 600 KiB, redirects, protected e-mails. Risk: C12
> changes the sheet contract; goldens change, each listed. Size: 12 h.

### Rows C8 to C13 (`LEADFORGE-ADOPTION.md` section 5)

> | C8 | Robots rules, fully | checked; three gaps | Cache at most 24 hours; parse at least 500 KiB; a 4xx robots answer allows, a 5xx forbids (RFC 9309) | a local server plays each case; a clock is injected for the cache | L3b |
> | C9 | A refusal is final | retried in a browser | No browser retry after 403 or 429. Other cases unchanged | the local server answers 403: zero browser starts | L3b |
> | C10 | No crawl that skips the robots check | a switch allows it | The `-email` switch of the helper program is removed; the config key is refused with a message | a config that sets it is refused; the argument never appears | L3b |
> | C11 | Respect anti-harvesting measures | protected emails decoded | Decoding is off by default | a page with a protected address: the address is not stored | L3b |
> | C12 | Say where each detail came from | stored, not all exported | Every exported email and phone carries its source address and date. This changes the sheet contract; the change is listed in the slice | a fixture export has both for every contact | L3b |
> | C13 | Send rules by country | a rules module exists; nothing calls it | Wire it in: unknown country means no send; Germany needs consent; a UK sole trader needs consent | planted leads for each case come out "not eligible" | L3b |

### Row L3b (section 9) and risk 15

> | **L3b The collect side** (0.9.0) | C8 to C13. One profile function for every browser the product starts (risk 15) | The tests of C8 to C13 against a local server. A new profile folder holds the seeded file before the first start | guardrail | about 1,200 lines; 1.5 days |
>
> | 15 | **Browsers the product starts may cause failed Windows logons** on a machine with an account password (the MASTER-PLAN finding). Not provable here: this laptop has no password | MAP 4.3 | L3b adds one profile function; proven at the setup's last step on the other laptop |

### The L2 UNPROVEN line this slice closes

> Robots on a cross-site redirect hop is tested by reading and by the reviewer agent's loopback probe only.

## Build, stage A

Each item: what must hold (written before the code), then the check by reading after it.

### Item 1 - C8, robots rules in full

Must hold:
1. A robots answer is used for at most 24 hours (`ROBOTS_TTL_S = 86400`) by the same crawler object; after that it is fetched
   again. The clock is injectable (`SiteCrawler(cfg, throttle, clock=...)`, default `time.monotonic`). Just under 24 h: no second fetch;
   at 24 h: a second fetch.
2. At least 500 KiB of a robots file is parsed: a 600 KiB file whose `Disallow` sits around 400 KiB in is honoured. The body is bounded
   (512 KiB, cut at a line end) so a huge file cannot fill memory; a rule beyond the bound is not read (RFC 9309 allows it).
3. 4xx answer: allow (as before). 5xx answer: forbid (as before). Both now have a test with the loopback server; a transport failure
   forbids.
4. robots.txt reached through redirects (same site) is read as the answer; a redirect chain with no end forbids.
5. A redirect hop of a page fetch to ANOTHER site is checked against that other site's robots.txt: a loopback server answers as two
   sites (`127.0.0.1:<port>` and `localhost:<port>`, two site keys); the page on the first redirects to a path the second forbids; the
   crawler must not request that path, and says `robots`. The test fails when the check in `_pace` is removed (the red is pasted below).

### Item 2 - C9, a refusal is final

Must hold:
1. After a 403 or 429 on the home page, `needs_browser` is False and a new `CrawlResult.refused` is True. 401, 405, 406 and 503
   stay browser-eligible ("other cases unchanged").
2. The enrichment path (`runner._process_one`) starts no browser after a 403 or 429: a fake starter in place of the one function that
   imports the browser library counts ZERO starts against the loopback server answering 403 and 429. (Seen red with 403 put back
   into the eligible statuses: one start.)
3. `render-check --force` does not start a browser after a 403/429 either (the `force` path was a second way round).

### Item 3 - C10, no crawl that skips the robots check

Must hold:
1. The `-email` argument is never put on the helper's command line (the `if d.email_crawl: args.append("-email")` is deleted).
2. A config (file or `LEADFORGE_DISCOVERY__EMAIL_CRAWL`) that carries `discovery.email_crawl`, true or false, is refused when it is
   loaded, with a message that names the key and says why. The key leaves the example config.
3. No other path of this code base skips `_allowed`: read and written down in the check.

### Item 4 - C11, protected e-mail addresses are not decoded by default

Must hold:
1. `extract_emails(html, text)` does not decode `data-cfemail`: a page whose only address is protected gives no address.
2. A switch `crawl.decode_protected_emails` (default False) turns it on, and every caller passes `cfg.crawl.decode_protected_emails`.
3. Nothing else decodes it (the `decode_cfemail` helper is only reached with the switch).

### Item 5 - one profile function for every browser start

Must hold:
1. New module `leadforge/browser_profile.py` with `prepare_profile(root, name)`: a folder that does not exist is created and holds
   `Local State` = `{"password_manager":{"os_password_blank":false,"os_password_last_changed":"<N>"}}`, N = (Unix ms + 11644473600000) x 1000 as a
   string, BEFORE it is returned (so before any start); a folder that exists is reused and its `Local State` is not rewritten.
   Recipe from the setup's `ARCHITECTURE.md` 8.5 (tested there by its author on Chrome 157 and Edge 156; here only the file is proven).
2. The crawl4ai start (`enrich/browser.py`) and the Playwright start of `maps_list.py` both get their profile folder from it; the
   Playwright start becomes a persistent context on that folder (`launch_persistent_context(user_data_dir=...)`).
3. A test walks every `.py` under `src/leadforge`, finds each browser start (`AsyncWebCrawler(...)`, `.launch(...)`,
   `.launch_persistent_context(...)`) and fails when the function that holds it does not call `prepare_profile`; planted bad case:
   the same walk on a made-up source that starts a browser without it is flagged.
4. gosom starts its own browser inside the helper program: LeadForge cannot give it a profile. Written under "Plan and code disagree";
   the helper leaves the public tool in L8.

### Checks by reading, after the code (each item against its "Must hold")

- Item 1: `ROBOTS_TTL_S = 86400` is read in `_robots_for` with the injected clock (`now - self._robots_at[host] < ROBOTS_TTL_S`), also for the
  dead-host answer. `_robots_lines` reads at most 512 KiB (524,288 bytes, above 500 KiB), cuts at the last line end, decodes with `replace`.
  4xx -> `rp.parse([])` (allow), 5xx -> disallow, any `httpx.HTTPError` (including too many redirects) -> disallow. The robots request is made with
  `_fetching_robots` set, so its own redirect hops are exempt from the hop check (they are how the answer is found); every other request, hops
  included, is checked in `_pace`. 5 holds, with the red below (M1). Not changed, said plainly: the per-business crawler object means the 24 hour
  life matters little inside one run; it is the contract the row asks for.
- Item 2: `_BLOCK_STATUSES` lost 403 and 429; `refused` is set for them in `crawl()`; `_process_one` has both browser branches behind
  `not res.refused` (a second, redundant guard: with only the runner guard removed the zero-start test stays green, with only the crawler
  change removed `test_c9_the_crawler_marks...` goes red; both removed, the zero-start test goes red: M7 and M8 below); `render-check` has the
  `elif res.refused` branch before `--force`. `render_check` with the 200 control still starts one (the fake works).
- Item 3: the `-email` line is deleted; `DiscoveryCfg` refuses the key in a `mode="before"` validator, so file, environment and `config set`
  all go through it; the message names the key and why. `_allowed` is called in `crawl()`, `_get`, `_crawl_aggregator`, `render-check`, the
  runner's second browser branch and `_pace` (every hop); `resolve_domain` goes through `crawl()`. No path skips it (read: `git grep "_allowed\|\.crawl("`).
- Item 4: `extract_emails(..., decode_protected=False)`; `CFEMAIL_RE` is only iterated when True; the four callers (runner x3, render-check) pass
  `cfg.crawl.decode_protected_emails` (default False). Two older tests that asserted the decoding as a default now pass `decode_protected=True`
  (cause: they encoded the behaviour C11 removes; the assertions are unchanged).
- Item 5: `prepare_profile` creates the folder, and when it is empty writes the file to a temp name and `os.replace`s it, so the file exists whole
  before the path is returned. `browser.fetch_rendered` and `maps_list._ensure_browser` both call it; each live browser takes the lowest free slot
  (`crawl4ai-0`, `maps-list-0` ...), because a browser keeps its folder locked and the render gate allows `browser_concurrency` renders at once.
  Maps moved from `launch()` + `new_context()` to `launch_persistent_context()` with the same locale, viewport, user agent and proxy.

### What the tests are, and the red of each (a line of code broken, the test run, the line restored)

Old tests changed, with cause: `test_crawl_of_blocked_home_flags_browser` and `test_home_block_status_never_fetches_secondary_pages` used a 403 to
stand for "block-shaped, browser-eligible", which C9 removes (they use 406 now); `test_read_timeout_does_not_mark_host_dead` faked a slow server
by patching `client.get`, and robots.txt is now read through `client.stream`, so the fake missed it and a real DNS question went out for the
`.invalid` name (ConnectError, host marked dead): the fake now covers `stream` too.

| mutation (one line of code broken, then restored) | test that went red | first failing line |
|---|---|---|
| M1 hop check removed from _pace (if not self._fetching_robots and not self._allowed(url): -> if False:) | `test_collect_side.py::test_c8_cross_site_redirect_hop_is_checked_against_the_other_sites_robots` | `AssertionError: assert <Response [200 OK]> is None` |
| M2 the 24 hour life ignored | `test_collect_side.py::test_c8_a_robots_answer_lives_24_hours` | `AssertionError: assert (<Response [200 OK]> is None)` |
| M3 5xx no longer forbids | `test_collect_side.py::test_c8_a_5xx_robots_answer_forbids[500]` | `AssertionError: assert <Response [200 OK]> is None` |
| M4 4xx forbids instead of allowing | `test_collect_side.py::test_c8_a_4xx_robots_answer_allows[404]` | `AssertionError: assert None is not None` |
| M5 file cut at 300 KiB instead of 512 KiB | `test_collect_side.py::test_c8_a_robots_file_of_600_kib_is_read_to_at_least_500_kib` | `AssertionError: assert (<Response [200 OK]> is None)` |
| M6 an endless robots redirect allows | `test_collect_side.py::test_c8_a_robots_redirect_without_end_forbids` | `AssertionError: assert (<Response [200 OK]> is None)` |
| M7 403 and 429 offered the browser again at the crawler (statuses back in _BLOCK_STATUSES) | `test_collect_side.py::test_c9_the_crawler_marks_a_refusal_and_does_not_offer_the_browser[403-False-True]` | `assert (True, True) == (False, True)` |
| M9 render-check --force goes round a refusal | `test_collect_side.py::test_c9_render_check_force_does_not_go_round_a_refusal[403-0]` | `AssertionError: assert 1 == 0` |
| M10 the -email argument is put back | `test_collect_side.py::test_c10_the_helper_never_gets_the_email_argument` | `AssertionError: assert (['gosom-fake', '-input', <tmp> '-json', ...] and '-email' not in ['gosom-fake', '-input', <tmp> '-json', ...])` |
| M11 the email_crawl key is accepted again | `test_collect_side.py::test_c10_the_email_crawl_key_is_refused_with_a_message[true]` | `Failed: DID NOT RAISE ValidationError` |
| M13 the switch is ignored by the runner (callers do not pass it) | `test_collect_side.py::test_c11_decoding_is_on_request_only` | `AssertionError: assert 'owner@garage.example' in {}` |
| M8 both layers broken: statuses back in _BLOCK_STATUSES AND the runner's refused guard removed (zero-start test) | `test_collect_side.py::test_c9_a_refusal_starts_zero_browsers[403]` | `AssertionError: assert ['http://127.0.0.1:59037/'] == []` |
| M12 the extractor decodes by default | `test_collect_side.py::test_c11_the_extractor_does_not_decode_unless_told_to` | `AssertionError: assert {'owner@garag...': 'personal'} == {}` |
| M12b the config switch defaults to on | `test_collect_side.py::test_c11_a_protected_address_is_not_stored_by_default` | `AssertionError: assert (True is True and {'owner@garag...age.example'}} == {}` |
| M14 the crawl4ai start no longer sets user_data_dir | `test_browser_profile.py::test_every_browser_start_in_the_product_goes_through_the_profile_function` | `AssertionError: assert ['leadforge/e...ser_data_dir'] == []` |
| M15 Maps goes back to a throw-away launch() | `test_browser_profile.py::test_every_browser_start_in_the_product_goes_through_the_profile_function` | `AssertionError: assert ['leadforge/p...away profile'] == []` |
| M16 the profile is not seeded (prepare_profile writes nothing) | `test_browser_profile.py::test_a_new_profile_folder_holds_the_seeded_file_when_it_is_handed_out` | `FileNotFoundError: [Errno 2] No such file or directory: '<tmp>/test_a_new_profile_folder_hold0\\profiles\\tool-0\\Local State'` |
| M17 render path does not call prepare_profile (profile folder never seeded before the fake start) | `test_collect_side.py::test_c9_other_block_shaped_statuses_still_get_the_browser[406]` | `assert [False] == [True]` |

Not red-tested: the validation of a profile name (six bad names, each raises), the slot numbering, and the second half of the cross-site test
(its control: the same hop to an allowed path is fetched, which keeps the red above from being a broken server).

### Plan and code disagree (3)

1. Plan: "one profile function for every browser the product starts". Code: `gosom` is a downloaded helper program that starts its own browser
   inside itself; LeadForge passes it no profile folder and cannot (`providers/gosom.py` builds its argument list; whether the helper has a
   `-user-data-dir`-like switch is UNKNOWN, and running it to find out is forbidden here). Not built. It leaves the public tool in L8.
2. Plan: same. Code: `doctor --fix --full` runs the library's own `crawl4ai-setup` (`doctor.py`, the `post` step), which downloads browsers and
   may start one to check; that start is not ours to give a profile. Not built; UNPROVEN whether it starts one. `dashboard.py` opens the user's own
   browser on their own profile with `webbrowser.open` (not a new profile; not covered by the scan).
3. Plan (ADOPT C8): "a clock is injected for the cache". Code: the crawler object is created per business (`runner._process_one`), so a 24 hour
   life is only visible to a long-lived crawler object; there is no cross-business robots cache. Built as the row says (injected clock, tested);
   a shared cache would be a design change and is not made.

### UNPROVEN

- The crawl4ai start itself (`BrowserConfig(user_data_dir=..., use_persistent_context=True)`) and the Playwright persistent context of Maps: no
  browser is installed or started on this laptop, and crawl4ai is not installed in this environment. Settled by: a run of `render-check --force` on
  a loopback page, and a Maps test, on a machine with a browser (CI's job has no browser either; "not run on STRIKERFORCE: needs a browser").
  The names `user_data_dir` and `use_persistent_context` are the library's documented ones as far as I know; not checked against the installed version.
- That the seeded `Local State` stops the failed Windows logon: this laptop has no account password (ADOPT risk 15); proof is the one on the other
  laptop at the setup's last step.
- Companies House terms: see finding 1.

## For stage B

Left: C12 (every exported e-mail and phone carries its source address and date; list each golden that changes BEFORE regenerating), C13 (send
rules by country wired in), item 10 (the fake campaign's saved result; C12 moves cells, predict them first), and the version (0.9.0 in every copy
and a dated CHANGELOG heading in place of `## [Unreleased]`, if L6 is merged and everything is done).
What stage B must know about what stage A changed:
- `extract_emails` has a third argument; nothing in the exports calls it. The fake campaign (`scripts/e2e_fake_campaign.py`) was not run in
  stage A; `git grep -il cfemail scripts tests/fixtures` finds nothing, so C11 should not move it (UNPROVEN until it is run).
- A 403 or 429 home page now ends with `needs_browser` False, `refused` True, and `error` `home unreachable (status:403)` as before; nothing
  in `export.py` / `outreach/plan.py` reads `needs_browser`, so the sheets say what they said.
- New config key `crawl.decode_protected_emails` (default False); removed key `discovery.email_crawl` (a config that holds it is refused).
- `Config.browser_profiles_dir` (`leadforge_data/browser-profiles`) is new workspace state; L6's `purge`/`forget` does not touch it (it holds
  browser state, not lead data) - check that when merging.
- The DVSA terms finding (attribution) and the OpenCorporates findings (`restricted_for_marketing`, paid key) need a home: the Summary sheet
  line is stage B's (it touches the sheets); the rest is L9 / L12.
- CI results of stage A are in the pull request and the report, not here.

## Build, stage B (0.9.0)

Stage B (run `l7b-build`) continues the same branch. `origin/master` (0.8.0, L6 merged) was merged in at 0bb5455 (one conflict, `CHANGELOG.md`: both
sides kept). PRs 7 (debts) and 8 (Maps out) were NOT yet merged into `master` when this stage started; the DVSA sample and the locks are untouched
here. Stage A's tests (`test_collect_side`, `test_browser_profile`, `test_l6_suppressed_export`, `test_golden_contracts`) on top of L6: 77 passed.

Each item: what must hold (written before the code), then the check by reading after it.

### Item 6 - C12, every exported e-mail and phone carries its source address and date

Must hold:
1. Eight columns are added, in a new list `SOURCE_COLUMNS`, at the END of `DEFAULT_COLUMNS` and of `ACCOUNT_COLUMNS` (no existing column moves
   position): `Email Source`, `Email Date`, `Email (Inferred) Source`, `Email (Inferred) Date`, `Phone Source`, `Phone Date`, `DM Phone Page`,
   `DM Phone Date`. The Drafts tab gets two more at its end: `To Source`, `To Date`. No table changes: the values are read from rows that already exist.
2. `Email Source` is the page address of the newest `enrichment_observations` row for that address (`field='email'`, `value_json` equal to the address);
   if none, the `url` of the `email_found` evidence of that contact; if none, the words `source not recorded`. `Email Date` is the date (`YYYY-MM-DD`) of
   that observation or evidence, else of the contact's `verified_at`, else `date not recorded`. A row without an address has `-` in both.
3. An inferred address is no published address: `Email (Inferred) Source` says `inferred, not published: <basis>` and the date is the contact's `verified_at`.
4. `Phone Source` / `Phone Date` describe the number in the `Phone` cell. A number from the business listing: the listing's address (`maps_url` for a
   Maps row, the configured list address for `dvsa`, else the provider's name) and the date of `last_seen_at`. A number that came from a contact (fallback
   of the cell): that contact's observation (`source_url`, `observed_at`), else `source not recorded`. No number: `-`.
5. `DM Phone Page` / `DM Phone Date` come from the very observation `_best_dm_phone` picked; none: `-`.
6. The Drafts tab's `To` address gets `To Source` / `To Date` by the same rule as item 2.
7. A suppressed address stays in no cell (the masker runs over the new cells too).
8. Nothing else in a golden moves: the list of goldens that change is written below, with the reason, before any is regenerated.
Test (pass line): a fixture workspace with one address found on a page (observation), one with only evidence, one imported without any record, an inferred
address, a listing phone, a contact phone and a DM phone is exported to CSV; for EVERY non-placeholder e-mail and phone cell the paired source cell and
date cell are present and well formed (a URL or the stated words; `YYYY-MM-DD` or the stated words); the "not recorded" case is stated, never blank.

Goldens and saved results that change (listed BEFORE regenerating):
| file | change | reason |
|---|---|---|
| `tests/golden/sheet_columns.json` | `DEFAULT_COLUMNS` and `ACCOUNT_COLUMNS` gain the 8 columns at the end; new key `SOURCE_COLUMNS` | C12 changes the sheet contract |
| `tests/golden/sheet_export.json` | `csv_header` and `xlsx` header gain the 8 columns; `bare_row` gains the 8 keys (`-`) | same; the bare row has no e-mail and no phone |
| `tests/fixtures/e2e/expected.json` (the fake campaign's saved result) | the Leads tab and the CSV gain the 8 columns; the Drafts tab gains 2; each row's new cells hold the page address and date | same |
No other golden holds a sheet (`dm_handoff`, `draft_handoff`, `provenance`, `workspace_schema`, `campaign_file`, `agent_contract`... carry no sheet columns; the schema golden is unchanged
because no table changes).

### Item 7 - C13, send rules by country

Must hold:
1. New module `leadforge/send_rules.py`, pure functions, no I/O. `country_code(raw)` turns a business's `address_country` into ISO-2 (`GB`, `United Kingdom`,
   `uk`, `england`... all `GB`; `Germany` and `DE` are `DE`: the names `normalize.COUNTRY_TO_REGION` knows, plus a two-letter ISO code itself), or `""`
   when empty or not a country the tool can read.
2. Rules known: `US` (CAN-SPAM: opt-out model, as before), `GB` (PECR: corporate subscribers; a sole trader needs consent), `DE` (UWG section 7: consent
   before any commercial e-mail). Any other country, and an unknown one, has NO rule: no send.
3. `compliance.email_eligibility` applies it, so every caller (the sheet's `Lawful Basis` / `Next Action`, the score's contactability, the draft packet,
   `outreach plan` enrolment, and the live re-check in `outreach send`/`dry_run`) gets it with no change of its own:
   - unknown or rule-less country: `eligible` False, `basis` `none`, reason `country_unknown` (empty) or `country_no_rule`;
   - `DE`: `basis` `consent_required`, `eligible` False (reason `consent_required`);
   - `GB` with entity `unmatched` (the registry looked and found no company: a sole trader or partnership): `basis` `consent_required`, `eligible` False;
     `GB` with `corporate_active` and an own-domain address: unchanged (`b2b_legitimate_interest`, eligible); `US`: unchanged.
4. The country rule can only make a lead LESS sendable than before, never more.
Test (pass line): planted leads (no country, a country with no rule, Germany by name and by code, a UK sole trader, plus the two controls UK company and US) go
through `email_eligibility`, through `outreach send`'s `_recompute_eligibility`, and one DE lead through `dry_run` ends in `skipped_ineligible` with no file in the outbox;
the control leads are eligible. The tests' older fixtures that had no country get one (cause: they were built before the country mattered).

### Item 10 - the fake campaign, prediction (before it is run)

`scripts/e2e_fake_campaign.py` against `tests/fixtures/e2e/expected.json`. Predicted differences, and no others:
- The Leads tab and the CSV: the 8 new columns for all 10 rows. Cells: `Email Source` is the page of the crawl for Harbour Motors (the only row with an address), `-` for the rest;
  `Email Date` a date (`<DATE>` after normalising) for Harbour Motors, `-` for the rest; `Email (Inferred)` columns `-` for all (no row has an inferred address);
  `Phone Source` is the provider's address (a `dvsa` row: the fake list's address; a `gosom` row: the row's maps address if it has one, else the name `gosom`), `Phone Date` the date of
  `last_seen_at` (`<DATE>`); `DM Phone Page` and `DM Phone Date` `-` for all 10 (every row says "none person-owned").
- The Drafts tab: two new columns `To Source`, `To Date` for each drafted row.
- C13 moves NO cell: every row is `GB` or `United Kingdom`, and every `Lawful Basis (Email)` is already `none` (the one address, Harbour Motors', has tier `unknown`).
- C11/C8/C9 (stage A) move no cell either; the requests the fake web server sees are unchanged (no new request is made by an export).
- The date cells are normalised by one new rule in the script's normaliser (a bare `YYYY-MM-DD` becomes `<DATE>`); the saved result is regenerated only for the cells above.
