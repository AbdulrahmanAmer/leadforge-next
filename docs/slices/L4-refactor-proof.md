# L4 refactor proof   (run l4-proof-build, 2026-11-11 18:07-)
Type: test   Stacks: python   Version: 0.7.1 (not changed here)   Base: e3784c8 (`origin/master`)
Guardrail: no   Owner: no
## Spec        (from the owner's word of 2026-11-11 17:44: "Keep the repo private either way test the refactor results")
Goal: show that the refactored tool (0.7.1) still does its job, by running one invented campaign through it and through the last version before the refactor (4506fbd, 0.6.14).
Both versions run only inside a socket guard that refuses and logs every non-loopback connection or lookup; no real key, site, browser, model or Maps scraper is involved.
Pass lines: the guard is proven by a refused probe; both versions get byte-identical input and every command and digest is recorded; every difference has a reason traced to a commit or slice, or is marked UNEXPLAINED;
the re-run command prints PASS for the new version and FAIL when one fixture page is changed; nothing can be pushed from the old clone.
Gate changes: none (this is the first form of G2's `scripts/e2e_fake_campaign.py`; goldens, Linux/Windows CI and the two UK registers are L4 onward).

## Build   (builder: Sonnet 5.5, inline, run l4-proof-build). Branch: slice/L4-refactor-proof from master e3784c8.

### What was built
- `scripts/e2e_fake_campaign.py`: starts a loopback web server (127.0.0.1:18765) playing 8 invented garages (normal x4, robots disallow-all, home redirect into a disallowed path, 404, slow) plus an invented DVSA register CSV;
  writes a fresh workspace and a `leadforge.yaml` (`agent.command: []`, `enrich.ner: false`, `social.enabled: false`, DVSA url on loopback, delay 0.2 s); runs `intake, plan, run, (env stamp), discover, byol import (preview, apply), run --resume, status, export`
  as child processes with an environment stripped of every key/token/proxy variable; saves, normalizes and compares the result with `tests/fixtures/e2e/expected.json`.
  Options: `--python <py>` to run another install, `--label`, `--out`, `--no-golden`, `--update-golden`, `--probe`.
- `tests/fixtures/e2e/harness/sitecustomize.py` (on `PYTHONPATH` of every child): refuses and logs (JSON line: kind, host, port, calling package, leadforge frame) every `getaddrinfo`, `connect`, `connect_ex`, `sendto` that is not loopback;
  resolves the 8 invented `*.example` names to 127.0.0.1 inside the process only; replaces the `gosom` provider by a subclass that reads `maps_listings.json` (gosom's JSON shape) through the real `GosomProvider._parse`.
- `scripts/e2e_compare.py`: side-by-side of two normalized results (commands, tabs: only-in-old / only-in-new / changed cells, CSV, report.json, refused calls, requests the fake server saw).
- Fixtures: `tests/fixtures/e2e/` (`answers.yaml`, `user_list.csv`, `dvsa_register.csv`, `maps_listings.json`, `world.json`, `sites/<host>/...`, `expected.json`). All names invented, addresses `.example`, phones in Ofcom's 0117 496 0xxx drama range.

### Harness decisions (same for both versions)
1. The Maps scraper cannot be used (SHA-256 pinned binary, never downloaded here). The Maps source is a fixture-fed stand-in for the `gosom` provider (same parse path, same field map). The two UK registers: DVSA's address is configurable and points to the fake server; Companies House's base address is a module constant (`providers/registry.py CH_BASE`), so it is NOT used (no key either) in either version.
2. `run` cannot start without the scraper binary (the doctor check is unconditional), so the harness writes the doctor's ok-stamp (`.doctor_ok.json`) before `discover`. The unstamped `run` is recorded first (step `run-unstamped`) and is itself a result.
3. The "user list" is `byol import` (it attaches contacts to businesses that already exist; it cannot create businesses).
4. Both versions run from the same fixtures, the same config bytes, the same port. The old version is also run in a second environment with the dependency versions of the new `requirements.lock` (see result 2); both old runs are shown.

### Guard proven (probe, `python scripts/e2e_fake_campaign.py --probe`)
```
refused: create_connection 203.0.113.9:80 -> gaierror [Errno 11001] LF_GUARD: name lookup refused (not loopback)
refused: raw connect 203.0.113.9:80 -> ConnectionRefusedError LF_GUARD: connect to 203.0.113.9:80 refused (not loopback)
refused: lookup www.example.org -> gaierror [Errno 11001] LF_GUARD: name lookup refused (not loopback)
refused: udp send 192.0.2.53:53 -> ConnectionRefusedError LF_GUARD: sendto 192.0.2.53:53 refused (not loopback)
loopback allowed: 127.0.0.1 59162
{"t": 1794413709.388, "pid": 29888, "kind": "connect", "host": "203.0.113.9", "port": 80, "caller": "__main__", "leadforge": ""}
PROBE PASS
```
(The probe was written with the raw-connect case after a first probe showed an IP literal is refused at the lookup, not the connect.)

### Results
1. **New 0.7.1** (env: hashed `requirements.lock`): all 10 commands exit as designed; run `exported`, 10 leads (5 tier B, 5 tier C), 5 sites crawled, 5 drafts (template), 32 refused outside attempts (all DNS packets of the email-validity step to 6 resolver addresses).
2. **Old 0.6.14 installed the way its README says** (`uv pip install -e . --exclude-newer 2026-11-04`; resolved selectolax 1.0.2): installs and runs through `discover` and `byol`, then `run --resume` and `export` exit 1:
   `ImportError: Modest backend is deprecated since selectolax 1.0. The engine has not been updated since 2021, while lexbor has been ava...`. Cause: its open-ended `selectolax>=0.3.21` follows to a release that removed the backend it uses; the new lock pins 0.4.13. This is the "installs again" result of L1, seen on the code path.
3. **Old 0.6.14 with the new lock's dependency versions** (`venv-old-pinned`, same hashes as the new environment): all 10 commands exit 0; this is the code-against-code comparison below.

### Side by side (old-pinned vs new; normalized: timestamps, run ids, workspace paths)
| # | What differs | Old | New | Reason |
|---|---|---|---|---|
| D1 | `run` before the environment is ready | tries github.com / api.github.com (3 refused calls: 2x github.com, 1x api.github.com); message `...download the asset manually...; network (check connectivity...)` | exit 3, `environment not ready: gosom-binary (leadforge doctor --fix)`, no network | e9b4847 `run never downloads` (C3; `ensure_ready` is local-only) |
| D2 | Pennine Motors: home redirects into a path robots.txt disallows | follows it: fake server saw `/private/welcome 200` and `/about /contact /team 404`; site status `redirects to ...` | not fetched; `not crawlable (robots)`; server saw only `/` 302 and `/robots.txt` | d99dc1e (every redirect hop asks robots.txt, a disallowed one is not followed), a7540f2 (a robots-refused home reads as robots-disallowed) |
| D3 | Pennine row in Leads: Score 72 -> 56, Tier B -> C, Email `none published` -> `site not crawled`, Hook, Why This Score, Fit, Site Status, All Hooks (8 cells) | crawled, got a "no social profile" hook | not crawled, no hooks | follows from D2 |
| D4 | Summary tab (`6x` -> `5x` hook count, tier line `0/6/4/0/0` -> `0/5/5/0/0`), `report.json` tiers B 6 -> 5, C 4 -> 5, CSV (Pennine row), digest `tier_b` 6 -> 5, `tier_c` 4 -> 5, `sites_crawled` 6 -> 5 | | | follows from D2 |
| D5 | digest `draft_abstained` 1 -> 0 | | | INFERRED to follow from D2 (Pennine is the only row that differs; no per-draft abstain record exists to read) |
| D6 | refused DNS packets 43 vs 32 (minus the 3 of D1: 40 vs 32) | 12/12/4/4/4/4 per resolver | 10/10/3/3/3/3 | INFERRED: one more domain looked up in old (Pennine crawled, so its address was validated); the guard logs the resolver address, not the name asked |

Identical: `intake`, `plan`, `discover` (10 businesses: 8 stand-in listings + 3 DVSA rows, 1 merged by phone), `byol import` (1 matched by domain, 2 unmatched), the About and Drafts tabs, 9 of the 10 Leads rows, the DVSA request, the 5 normally crawled sites' requests.
UNEXPLAINED differences: none found. Full outputs: `D:\homelab-work\l4\out-new\`, `out-old\` (not committed).

### Seen in both versions (not differences, worth knowing)
- Every crawled site's `Site Status` reads `redirects to <host>:18765` although no redirect happened. It appears only because the fake sites use an explicit port; the host comparison for `offsite_redirect` seems to include the port. Not traced; no effect on production URLs without a port is shown.
- `.example` email addresses never reach the sheet as "found": the Email column says `none published` for the sites that publish one. Reserved domains are refused by the email validator, so the validity tiers (`valid`, `risky`...) are not exercised by this campaign.
- `leadforge --version` is "No such option" in both 0.6.14 and 0.7.1; only `leadforge version` works. G1 of L4-ONWARD says `leadforge --version` prints the release number: as written that row fails on 0.7.1.
- With no agent (`agent.command: []`) the labeler decides 3 of 5 candidates; 2 stay `not identified`.

### Re-run
`python scripts/e2e_fake_campaign.py` (interpreter with the new version installed) prints `PASS - result equals tests/fixtures/e2e/expected.json (32 refused outside attempts, as saved)`.
Seen FAIL once: `Odell Prewitt` changed to `Odell Prewick` in `sites/kestrel-garage.example/team.html` printed `FAIL - differs from expected.json in: csv, tabs`; the page was restored with `git checkout`.
The old half: `python scripts/e2e_fake_campaign.py --python <old venv python> --label old --out <fresh dir> --no-golden` then `python scripts/e2e_compare.py <old result.json> <new result.json>`.

### NOT DONE / UNPROVEN
- Not run: the Maps scraper, the browser tier, NER, the agent labeler and drafter, the two registers' real addresses, Companies House (no loopback address possible), a send. Each needs a real service, a key, a browser or a model.
- UNPROVEN: the golden is stable across machines (it was equal on two consecutive runs here: run4 saved, run5 PASS); Linux has not run it. Settle with the G2 CI job on `ubuntu-latest`.
- UNPROVEN: D5 and D6 causes (see table).
- The guard is a Python-level guard: it does not stop a child that is not Python or a native socket call; the campaign starts no such child (`runner: none`, no `claude` process).

## Review
(none yet; an independent reader checks this proof)
