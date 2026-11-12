# L7 The collect side (C8 to C13)

Branch `slice/L7-the-collect-side`. Stage A (this run, `l7a-build`) builds what does not touch the tables, the
exports, the sheets or the send path, and sets no version. Stage B continues the same branch after L6 is merged.

## Findings at the top

(Filled in by item 8, the terms of each source. Nothing is removed in this slice; a source whose terms forbid this use
is written here and leaves the public tool in a later step.)

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

