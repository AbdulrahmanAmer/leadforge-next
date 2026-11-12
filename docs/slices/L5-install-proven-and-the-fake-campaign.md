# L5 install proven and the fake campaign

## Starting list (from the L4 refactor proof)
- ZERO: the fake campaign check runs on `windows-latest` only (L4 merge, 0.7.2). On `ubuntu-latest` it differed in `refused`
  only: 0 entries against the 21 saved. Cause (read from the runner): its `/etc/resolv.conf` names `nameserver 127.0.0.53`,
  a local stub resolver. The guard allows loopback, so the email-validity step's DNS packets (`dns.resolver.Resolver()` reads
  that file) went to the stub, were not refused and were not logged. The path separators and the short Windows temp name
  (`RUNNER~1`) were the other two differences; the compare now absorbs both. For Linux: make the guard see DNS sent to a
  loopback port 53 (refuse and log it, as it does for `getaddrinfo`), or give the campaign its own resolver setting, then
  save a Linux-side result or compare without `refused`. This also means: on a machine with such a stub, the guard as it is
  lets a DNS question reach the outside through the stub.
- FIRST: Companies House's address becomes a setting, so that source can be faked. It is fixed in the code today (`providers/registry.py` `CH_BASE`) and was off in both versions of the proof.
- 0.6.14 installed the way its own README says fails at enrich (`selectolax` 1.0.2 `ImportError`: its open-ended `selectolax>=0.3.21` follows to a release that removed the backend it uses). The upgrade note must say it.
- The socket guard is Python-level: asyncio's Windows `ConnectEx` and native sockets are not covered. One probe through `asyncio.open_connection` inside the guard settles it.
- Not shown at all by the proof: the real sources, the browser, the agent call, sending.

# Build (0.7.3) — first part of L5

Run `l5-build`, 2026-11-12. Items in the order of the brief; per item the text of what the change must do is written before the
code, the reading check after it.

## Item 0 — the Linux DNS gap

**Must do (written before the change).** In `tests/fixtures/e2e/harness/sitecustomize.py` a connection or datagram whose destination
port is 53 (UDP `sendto`, TCP/UDP `connect`/`connect_ex`) is refused and logged exactly like an outside call, whatever the address
(loopback included). A loopback address on any other port stays reachable, so the fake world's own server (port 18765) and the
probe's ephemeral loopback listener are untouched. The log entry has the same shape (`kind`, `host`, `port`, `caller`).

**Which refused-list cells move.**
- Windows (saved result made there): NONE. Its system resolver is not loopback, so its packets were already refused and normalized
  to the one `<system resolver>` entry; the 20 fallback entries (8.8.8.8, 1.1.1.1) are unchanged.
- Linux (`ubuntu-latest`): 0 entries → the same 21 as saved. The stub `127.0.0.53` now refuses the probe question
  (`sendto 127.0.0.53:53`, normalized to `<system resolver>`), `get_resolver()` falls to its public fallbacks, whose refused sends
  are the same 20 entries as on Windows. The saved result stays unchanged; if Linux shows any other difference, that is not predicted.
- Nothing else in the result moves: the request log and the tabs do not depend on DNS packets (names of the `.example` sites resolve
  inside the guard, not by packet).

**Seen red first.** `harness/probe.py` gets two cases (UDP `sendto` and TCP connect to `127.0.0.53:53`) and `--probe` demands that the
guard log holds both (TCP to a closed loopback port is refused by the OS anyway, so the log, not the exception, is the evidence).

## Item 1 — Companies House's address as a setting

**Must do (written before the change).** New setting `registry.companies_house_url` (yaml, or `LEADFORGE_REGISTRY__COMPANIES_HOUSE_URL`,
read the way every other setting is: the `RegistryCfg` pydantic model fed by `leadforge.yaml` then the env overrides). Default is
exactly today's address `https://api.company-information.service.gov.uk`, so with no setting nothing changes. Both users of the
address read it from the config instead of the constant: the officer lookup (`providers/registry.py`, `CompaniesHouseRegistry`,
three requests) and the discovery provider (`providers/companies_house.py`, two requests).
Decision on other values (own decision, reason): the DVSA setting (`discovery.dvsa.url`) accepts any address because the request
carries nothing secret. This one carries the Companies House API key as basic-auth user name on every request, so a setting that
pointed to a stranger's host would send the key there. Therefore the config refuses at load (`ValueError` from a pydantic
validator, which `load_config` and `config set` both go through) every address except the default and an `http`/`https` address
whose host is `localhost` or a loopback IP (with or without a port or a path prefix); an address with embedded credentials, a query
or a fragment is refused too. A trailing `/` is dropped. No change anywhere else.
Seen red first: a test that sets a non-default, non-loopback value and expects a refusal, and a test that a loopback value reaches
the officer lookup's request (checked via an httpx transport double: URL of the request). Break: validator accepts everything /
code still reads the constant → each test fails.

**Check by reading, after.** `RegistryCfg.companies_house_url` (config.py) matches the text: default = the real address; validator drops a
trailing `/`, returns the default unchanged, accepts only http/https + `localhost`/loopback IP (`urlsplit().hostname`, so
`127.0.0.1.evil.example` and `user@` forms are refused) with no credentials/query/fragment, refuses a bad port. One addition not in the
text above: an empty value means the default. `config set` validates through `load_config` before writing, so a refused value is never
saved. `CH_BASE` is gone (nothing else read it; `git grep CH_BASE` finds only this file). The five request sites read `self.base` /
`cfg.registry.companies_house_url`. Red/green: with the validator's default-return removed and the officer search pinned to the real
address again, 10 of the new tests failed (refusal ×8, env override, configured-address request); restored → 43 passed in test_registry.py.
New dev packages for local test runs only (nothing added to the project): `pytest 9.2.0` (uploaded 2026-10-27), `pytest-timeout 2.4.0`
(2025-05-05), `iniconfig 2.3.1` (2026-10-06), `pluggy 1.7.0` (2026-10-15), exactly the versions in the repo's own `uv.lock`,
all older than 7 days, published on PyPI by pytest-dev; `osv-scanner` on `uv.lock`: no issues.

## Item 2 — the fake for it (written before the change and before the run)

**Must do.** `tests/fixtures/e2e/companies_house.json` holds four invented companies (numbers `ZZ0000nn`: no register issues that
prefix; people made up). `scripts/e2e_fake_campaign.py` serves them on its own loopback server under `/ch/` (`search/companies`,
`company/<n>`, `company/<n>/officers`, basic auth with the fixture key or 401) and the campaign's `leadforge.yaml` gets
`registry.companies_house_key: fixture-key` and `registry.companies_house_url: http://127.0.0.1:<port>/ch`. The source in use
is the officer/registry lookup (`CompaniesHouseRegistry`); the company-mode *discovery* provider is not switched on (it needs a
second, company-mode ICP): carried over. What the four invented companies exercise: HARBOUR MOTORS LTD (active, one active
individual + one resigned → matched, one registry DM auto-picked); NORTHGATE TYRES LIMITED (active, two individuals → matched, no
auto-pick); PENNINE MOTORS LIMITED (dissolved → rejected, `active_only`); HARBOUR MOTORS BATH LTD (same name, other town → listed
first in the search answer for Harbour Motors, rejected by the locality gate).

**Cells that may move in `expected.json`, and why** (every business in `GB` is now looked up, `registry_checked` becomes true):
1. `steps[intake].digest.warnings`: the "a free Companies House key adds registry-verified directors" line goes (the key is set).
2. Leads tab and CSV, ALL ten rows: `Company No`, `Registry Name` change from `not looked up` to either the company (matched rows) or
   `not matched in registry`; `Registry Match` from `n/a` to the similarity for matched rows. Matched rows (Harbour Motors,
   Northgate Tyres): also `Incorporated`, `Company Status`, `SIC Codes`.
3. Harbour Motors only: `DM Name`/`DM Title`/`DM Conf` (registry director `Tamsin Verrill`, `Director`, 0.9) and what follows from a
   named DM: `Call Readiness`, `Next Action`, `Score`/`Why This Score`/`Tier` if the rubric reads a DM, the Drafts row (`DM Name`,
   greeting), Summary counts (`With decision maker`, Tier line, Next Action breakdown), `report.json` (`with_dm`, `tiers`).
   Northgate Tyres keeps "not identified": two individuals are never auto-picked. Pennine Motors and the other seven: DM cells unchanged.
4. `steps[run-resume|status|export].digest.counts`: registry/DM counters (`dm_labeled`, `dm_unlabeled`, tier counts) follow 3.
5. `requests`: new entries `127.0.0.1 /ch/... <status>` (the loopback server logs them): search, profile and officers calls for
   each business that reaches that point.
6. NOT moving: `refused` (all CH traffic is loopback and not port 53), every other business's DM/score/draft cells, `files`.
Anything outside this list that moves: stop and write the cause first.

**First run (saved nowhere; compared with `expected.json`) — what moved beyond the list above, and the cause (written before the second run).**
- `Entity Type` moves in all ten rows (`unchecked` → `unmatched` / `corporate_active`) and `Score`, `Tier`, `Fit`, `Why This Score`
  also in the second matched row (Northgate Tyres): a registry match adds the rubric's "registry-corroborated" factor; I had tied the
  score move to the DM only. Same family as items 2 and 3, so it is added to the list, not a surprise.
- Pennine Motors was matched to HARBOUR MOTORS LTD (similarity 0.46, same city), got its director and a draft saying "trading since
  2011". Cause: my fake search answered every company sharing ONE word of the query, and the tool's lookup then `continue`s past
  the dissolved PENNINE MOTORS LIMITED to the next hit, which clears `min_name_similarity` 0.45 on a 0.46 character-ratio score.
  The second half is a real property of the tool (a wrong-company match the code's own comment calls worse than none): NOT
  changed here ("no other behaviour changes"), written under carried over. The fixture's search now answers only companies whose title
  holds every word of the query (as a name search does for an exact name), so Pennine meets only its dissolved company.
- Second-run expectation, replacing the list above where it differs: Pennine Motors moves only `Company No`, `Registry Name`,
  `Entity Type` (`not matched in registry`/`unmatched`); Harbour Motors and Northgate Tyres move the registry, score and (Harbour
  only) DM/contact/draft cells; the other seven move `Company No`, `Registry Name`, `Entity Type` only.

**Second run, diffed per business and per section against the old `expected.json` (script: leaf diff of the normalized results).**
Moved, all inside the list above: Company No / Registry Name / Entity Type in all ten rows; Harbour Motors (registry DM Tamsin Verrill,
Director, 0.9, `READY - named contact`, score 72→80, Tier B→A); Northgate Tyres (registry fields, score 72→80, Tier B→A, no DM: two
individuals); Pennine Motors only `not matched in registry` (dissolved company rejected); `steps[intake]` loses the key-hint warning;
`dm_candidates` 5→8 (Tamsin, Fenn, Larkin; the resigned director is not counted), `dm_auto_picked` 1 (new key), `dm_unlabeled` 2→1,
tiers A/B/C 0/5/5 → 2/3/5; Summary with-DM 3→4 and the tier / next-action lines; the Drafts tab: Harbour's row names the DM and the
rows reorder because Northgate is now tier A; `requests` gains 10 `/ch/search/companies` and the profile and officers calls for the
two matched companies, all 200. NOT moved: `refused` (same 21), `About`, every other DM/score/draft cell. Saved result rewritten from
that run; a third run compared against it: `PASS - result equals tests/fixtures/e2e/expected.json (21 refused-call entries, as saved)`.
The old saved result already fails on the new campaign (the diff above is that failure), so the saved result does see the source.

**Check by reading, after.** Server: 401 without the fixture key's basic-auth header (the key goes only to this loopback address, in line
with item 1), search answers only companies holding every word of the query, profile/officers by number, unknown number 404; all
CH traffic is logged in `requests`. Config: key and `http://127.0.0.1:<port>/ch` set through the same settings a user has.
