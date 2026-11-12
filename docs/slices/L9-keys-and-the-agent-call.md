# L9 Keys and the agent call (C2 rest)

## Spec

From the plan (`L4-ONWARD.md`, section 2), copied:

> **L9 Keys and the agent call (C2 rest).** The OpenCorporates token moves from the address (`registry.py:207`) to a header if the API's
> documentation says it accepts one; if not, the provider is off by default and the token never appears in logs or errors. Registry keys come from
> the environment or the OS keyring only, never `leadforge.yaml`; `AgentFailed` messages redact `agent.command` arguments. `--tools ""` through a
> `claude.cmd` npm shim proven with a fake shim that records its argv; whether `--restricted` works with a subscription login probed once with
> `claude -p` in a lab config on D:. Leaves out: the window's key screen (L11). Pass lines: the fake-key scan over every output; the fake endpoint
> asserts no token in the URL; the recorded argv equals the golden. Fakes: loopback OpenCorporates endpoint; fake `claude.cmd`; keyring backend
> replaced in tests (never the real one). Risk: the API may refuse a header. Size: 8 h.

From the adoption document (`LEADFORGE-ADOPTION.md`, section 5), row C2, copied:

> | C2 | No key printed or stored in the open | printed; plain file | `config` never prints a key value; the token leaves the web address if the API allows a header; later the product's users' keys move to the Windows keyring | a fake key is planted; no command output and no log contains it | L2, L7 |

Carried over from the L2 slice file: UNPROVEN "`--tools ""` through a `claude.cmd` (npm) shim on Windows"; the token in the address; the
operator's `agent.command` printed in an `AgentFailed` message.

Version: none on this branch (the 08:55 correction: `master` is 0.7.3; CHANGELOG lines go under `## [Unreleased]`).

## Build

Run `l9-build`, 2026-11-12, STRIKERFORCE. `registry.py:207` checked: still `params = {"q": ..., "api_token": self.token}`.
Each item: what must hold, written before its code; the check of the code against that text by reading, after it.

### Item 1 — the OpenCorporates token

**The documentation, read 2026-11-12 at https://api.opencorporates.com/documentation/API-Reference** (HTTP 200, 110,067 bytes), section
"Authentication", quoted:

> Authentication is through a simple API token at present (see API accounts, below), and this should be submitted with each request in the query parameters.

The page names no header for the token (the words "Authorization" and "X-API" appear 0 times in its text; "header" appears only inside
the page's own analytics script). So the token stays where the API wants it, and the provider is **off by default**.

**Must hold (written before the code).**
- New setting `registry.opencorporates_enabled` (default `false`). With the default, no request goes to OpenCorporates even when a
  token is set; one warning line (no value) says why it is off and how to switch it on.
- With the setting on, the token goes in the address (the only way the API documents) and never appears in a log line or an error:
  the run's own log prints only the exception's type name (already so), and the `httpx` logger's request line has the
  `api_token` value cut before any handler sees it.
- Test (loopback OpenCorporates endpoint, its address set by the test): with a planted fake token and the default setting, the
  endpoint asserts no address it saw holds the token (it sees none at all); with the setting on and the endpoint failing, no log record
  at any level and no output holds the token.

**Check by reading (after the code).** `get_registries` (the one door every enrich path uses: `runner.py` lines 376, 501, 580) adds
`OpenCorporatesRegistry` only when the token is set AND `opencorporates_enabled`; otherwise one warning with no value. The provider's own
error path logs `type(e).__name__` only (unchanged); `raise_for_status`'s text (which holds the address) never reaches a log. The filter
sits on the `httpx` logger, so it runs before the record propagates to any handler; it rewrites the formatted message, cutting
everything after `api_token=` up to `&`, a quote or a space. Holds. Not covered: a third-party handler attached directly to `httpcore`
(it logs no address, read in the captured records: `connect_tcp`, `send_request_headers` lines carry host and port only).

**Proof.** `tests/test_l9_opencorporates_token.py`, 2 tests. Seen red first, each for its reason:
- default switched to `True` in `config.py`:
```
E       AssertionError: ['/v0.4/companies/search?q=Acme+Widgets+Ltd&api_token=FAKE-oc-token-0123456789-not-real&jurisdiction_code=gb']
E       assert not True
1 failed, 1 passed in 1.30s
```
- the `addFilter` line removed:
```
E       assert 'FAKE-oc-tok...789-not-real' not in 'DEBUG    ht...tatusError\n'
E         'FAKE-oc-token-0123456789-not-real' is contained here:
E           api_token=FAKE-oc-token-0123456789-not-real&jurisdiction_code=gb "HTTP/1.0 500 Internal Server Error"
```
- restored: `2 passed in 1.31s`; with `tests/test_registry.py`: `45 passed in 2.00s`.

### Item 2 — registry keys from the environment or the OS keyring only

**Must hold (written before the code).**
- `registry.companies_house_key` and `registry.opencorporates_token` are read from `LEADFORGE_REGISTRY__COMPANIES_HOUSE_KEY` /
  `LEADFORGE_REGISTRY__OPENCORPORATES_TOKEN` (taken as written, not parsed as YAML), else from the OS keyring (service `leadforge`,
  name `registry.companies_house_key` / `registry.opencorporates_token`), else empty.
- A non-empty value for either in `leadforge.yaml` is refused: loading the config fails with a message that names the setting, the
  environment variable and the keyring entry, never the value. Every command reports it (the root callback keeps the whole message).
- `config set` of a key setting (directly or through its section) is refused with that message and writes nothing; `config get` of a
  key setting says whether it is set and where from (`environment` or `OS keyring`), never the value.
- The keyring is optional: the extra `keyring` pins one exact version; without the package the environment still works; a keyring
  backend error counts as "not set" with one warning (no value). `registry.keyring: false` switches the lookup off (the fake campaign
  uses it so that it never reads a real keyring).
- In tests the keyring lookup is replaced by a fake for EVERY test (an autouse fixture in `tests/conftest.py`): the laptop's real
  keyring is never read or written.
- Every message that told the user to `config set` a key now says the environment variable or the keyring.

**Supply chain (read `supply-chain-2026-10.md` first).** `keyring==25.7.0`: uploaded 2025-11-16 (360 days old), the newest release,
publisher the long-standing jaraco/keyring project (maintainer Jason R. Coombs), not on the never-install list. Added only as the
optional extra `keyring`; NOT installed anywhere in this run (the tests never import it: they use a fake module or the fake lookup).
`osv-scanner` was not run on it: there is no lockfile entry for it (requirements.lock does not carry extras). `uv.lock` was NOT
regenerated (it would need a network resolve; nothing checks it — the L2 review already notes it lags). Test tools installed into
this run's venv (not in the lock): pytest 9.2.0 (2026-10-27, 15 days), pytest-timeout 2.4.0 (2025-05-05), iniconfig 2.3.1
(2026-10-06), pluggy 1.7.0 (2026-10-15): all older than 7 days.

**Check by reading (after the code).**
- `load_config`: the file is read; a non-empty `registry.companies_house_key` / `registry.opencorporates_token` raises
  `KeyInConfigFile(key_refusal(name))` before anything is merged or validated (so pydantic's own error, which can echo an input value,
  is never reached for a key). `key_refusal` is built from the name only. Holds.
- The two names are popped from the YAML-parsed environment overrides and read again from `os.environ` as written (stripped); if
  empty and `registry.keyring`, from `_keyring_get`. Sources recorded in `cfg._key_sources` (a fresh dict per load). Holds.
- `_keyring_get`: `ImportError` -> None; any backend error -> None plus one warning with the exception's type only. Holds.
- Root callback: `KeyInConfigFile` keeps its whole message (others still cut at 100). `config set`: the validation load of the
  would-be file raises `KeyInConfigFile` for a direct or a section set; the message is printed and nothing is written; setting `""`
  still works (it clears an old key). `config get registry.<key>`: from the loaded config, "<hidden, n chars> (from the ...)" or
  "'' (not set; ...)". `config get registry` (the section) reads the file and hides as before. Holds.
- `Config` is never dumped to disk or output anywhere in `src` (searched `model_dump`, `.dict()`, `vars(cfg`): the key read from the
  environment reaches only the two providers.
- Not changed: `discovery.proxies` may still carry `user:password@` in `leadforge.yaml` (printed hidden since L2); it is not a registry
  key and the plan's item names registry keys only.
- Deliberate contract changes in older tests: `tests/test_config_secrets.py` (a key set is now refused and nothing is written, where
  before it was written and only not echoed; the section-hiding check now plants the key by writing the file, as an old workspace
  would have it) and `tests/test_cli_contract.py::test_config_set_get_roundtrip` (round trip on `agent.model`; a key set is refused,
  `get` reports `key_set: 0`).

**Proof.** `tests/test_l9_keys_from_env_or_keyring.py` (8 tests) plus the two changed tests: `32 passed in 29.72s` (with
`tests/test_config_secrets.py` and `tests/test_cli_contract.py`). Each new test seen red first (`breakrun.py`, the break applied,
the test run, the file restored byte for byte):
```
### yaml refusal removed (broken: src/leadforge/config.py)
E       Failed: DID NOT RAISE KeyInConfigFile
### environment not read (broken: src/leadforge/config.py)
E       AssertionError: assert '' == 'FAKE-registr...cdef-not-real'
### keyring switch ignored (broken: src/leadforge/config.py)
E       AssertionError: assert 'FAKE-registr...cdef-not-real' == ''
### config set refusal branch removed (broken: src/leadforge/cli.py)
E           assert ('must not be in leadforge.yaml' in 'LF_DIGEST {"ok":false,"cmd":"config","run":null,"counts":{},"warnings":["invalid value for registry.companies_house_key: KeyInConfigFile"],"artifacts":[],"next":null}\n')
### config get key branch removed (broken: src/leadforge/cli.py)
E       assert (0 == 0 and 'not set' in 'registry.companies_house_key = {}\nLF_DIGEST {"ok":true,"cmd":"config","run":null,"counts":{},"warnings":[],"artifacts":[],"next":null}\n')
### keyring import failure not caught (broken: src/leadforge/config.py)
E           ModuleNotFoundError: import of keyring halted; None in sys.modules
restored all
```
The first commit of this item carried a fake value with a hex run that `gitleaks` flags (`generic-api-key`, the fake built from
pieces in the test; not a real key). The constant was changed to plain words and the commit rewritten on this branch before any
review; the two checks that print the constant were seen red again with the new value:
```
### environment not read (broken: src/leadforge/config.py)
E       AssertionError: assert '' == 'FAKE-registr...scan-not-real'
### keyring switch ignored (broken: src/leadforge/config.py)
E       AssertionError: assert 'FAKE-registr...scan-not-real' == ''
restored all
```

### Item 3 — `AgentFailed` redacts the arguments of `agent.command`

**Must hold (written before the code).**
- Every `AgentFailed` message (could not start, timed out, exited non-zero, empty stdout) names the program and the NUMBER of
  arguments, never an argument's text.
- The stderr tail kept in the message has every argument of 4 characters or more replaced by `<argument hidden>` (a wrapper may echo
  its own arguments).
- The exception is raised `from None`, so a traceback logged at debug level (`exc_info=True` in the callers) does not carry
  `TimeoutExpired`, whose text holds the whole argv.

**Check by reading (after the code).** The four `raise AgentFailed` in `run_agent` are the only places the argv met a message
(`grep -n "join(cmd)" src/leadforge/agent_runner.py`: none left). `_shown_command` prints `cmd[0]` and the count; `_without_arguments`
cuts every argument of 4+ characters and the part after its first `=`, longest first (so a whole `--api-key=...` goes before its
value). The stderr cut applies to the last 2,000 characters only, as before. `from None` on the two `except` paths; the exit and
empty paths raise outside any `except`. `_log_invocation` already wrote `cmd[0]` only (unchanged). The callers (`enrich/dm.py:190`,
`draft/service.py:367,394`) log `%s` of the exception and, at debug, its traceback: both now free of the argv. Not covered: an
argument shorter than 4 characters (no key is that short), and a key the program prints in another form (encoded, or split).
The program path itself (`cmd[0]`) is still shown: a path is not a key.

**Proof.** `tests/test_l9_agent_failed_redacts.py`, 4 cases (`exit` with a program that echoes its arguments on stderr, `empty`,
`timeout`, `cannot start`): `52 passed in 19.44s` with `tests/test_agent_runner.py`, `tests/test_autopilot_integration.py`,
`tests/test_c1_no_tools.py`. Seen red first, each case broken on its own (`breakrun.py`, file restored after each):
```
### exit message prints the argv (broken: src/leadforge/agent_runner.py)
E       AssertionError: agent command exited 3: D:\homelab-work\l9\venv\Scripts\python.exe C:\Users\DELL\AppData\Local\Temp\pytest-of-DELL\pytest-846\test_agent_failed_never_holds_0\fake_agent.py --api-key=FAKE-agent-planted-for-the-scan-not-real FAKE-agent-pl
1 failed in 0.25s
### stderr kept as it is (broken: src/leadforge/agent_runner.py)
E       AssertionError: agent command exited 3: D:\homelab-work\l9\venv\Scripts\python.exe <3 arguments hidden>
E         usage error, I was given: --api-key=FAKE-agent-planted-for-the-scan-not-real FAKE-agent-planted-for-the-scan-not-real and FAKE-agent-planted-for-the-scan-not-real
1 failed in 0.23s
### empty-stdout message prints the argv (broken: src/leadforge/agent_runner.py)
E       AssertionError: agent command produced empty stdout: D:\homelab-work\l9\venv\Scripts\python.exe C:\Users\DELL\AppData\Local\Temp\pytest-of-DELL\pytest-849\test_agent_failed_never_holds_0\fake_agent.py --api-key=FAKE-agent-planted-for-the-scan-not-real 
1 failed in 0.31s
### timeout chained to TimeoutExpired (broken: src/leadforge/agent_runner.py)
E       AssertionError: agent command timed out after 1.2s (limit 1s): D:\homelab-work\l9\venv\Scripts\python.exe <3 arguments hidden>
E         Traceback (most recent call last):
E           File "D:\homelab-work\l9\leadforge-next\src\leadforge\agent_runner.py", line 213, in run_agent
E             stdout, stderr = proc.communicate(input=prompt, timeout=effective_timeout)
1 failed in 1.49s
### could-not-start message prints the argv (broken: src/leadforge/agent_runner.py)
E       AssertionError: agent command could not be started: C:\Users\DELL\AppData\Local\Temp\pytest-of-DELL\pytest-852\test_agent_failed_never_holds_0\no-such-program.exe --api-key=FAKE-agent-planted-for-the-scan-not-real FAKE-agent-planted-for-the-scan-not-re
1 failed in 0.16s
restored all
```
(The timeout case fails on the same first assertion, `FAKE not in text`: the message is clean, the chained `TimeoutExpired` in the
traceback is not.)

### Item 4 — `--tools ""` through an npm `claude.cmd` shim

**Must hold (written before the code).** On Windows, a fake `claude.cmd` (same last line as npm's shim: it starts an interpreter with
a script and `%*`) found first on `PATH` is what `resolve_command` picks; `run_agent` starts it; the script records its argv; the
recorded arguments equal `tests/golden/autopilot_builtin_command.json`'s `argv[1:]`, including the empty string after `--tools`.
Skipped elsewhere (no `.cmd` outside Windows).

**Check by reading (after the code).** No product code changed for this item: the test drives the real `resolve_command` (auto-detect,
`shutil.which` restored to the real one, `PATH` holding only the shim's folder) and the real `run_agent` (`Popen` with a list:
Python joins it with `list2cmdline`, which writes the empty argument as `""`; cmd.exe passes `%*` as raw text; the interpreter's
command-line parser reads `""` back as one empty argument). The shim is npm's layout with two swaps: this Python for `node.exe`,
`record_argv.py` for `cli.js`; the last line (`endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%" ... %*`) is npm's.
Still UNPROVEN: the real npm `claude.cmd` with `node.exe` reading the line (node's parser, not Python's). Settled by: on a machine
where `claude` is the npm shim, one call with a `--settings` hook that writes `process.argv`, or the stand-in above with `node.exe`
and a three-line `record_argv.js`.

**Proof.** `tests/test_l9_tools_through_cmd_shim.py`: `1 passed in 0.31s` (Windows, this laptop). Seen red with the empty argument
dropped before the start (`cmd = [a for a in cmd if a != ""]` in `run_agent`), restored after:
```
### the empty argument dropped on its way to the program (broken: src/leadforge/agent_runner.py)
E       AssertionError: assert ['-p', '--mod...istence', ...] == ['-p', '--mod...istence', ...]
E         At index 10 diff: '--disallowedTools' != ''
E         Right contains one more item: '--restricted'
1 failed in 0.38s
restored all
```

### Item 5 — `--restricted` with a subscription login, one probe

**Must hold.** One `claude -p --restricted` call with `CLAUDE_CONFIG_DIR=D:\homelab-work\l9\lab-config` (an empty folder; nothing
copied from the real profile), a one-word prompt on stdin, API-key variables removed from the child's environment. What it prints is
written here as printed.

**Result: UNPROVEN.** The probe (`D:\homelab-work\l9\probe-restricted.mjs`, outside the repository; `claude` 2.1.312 at
`C:\Users\DELL\.local\bin\claude.exe`, the argv LeadForge builds today, prompt `hello` on stdin) printed, 2026-11-12 09:07:
```
lab folder D:\homelab-work\l9\lab-config, entries before: []
variables removed from the child's environment: 11 (names not printed)
exit: 1 signal: null error: none seconds: 1.6
--- stdout ---
Not logged in · Please run /login

--- stderr ---

--- end ---
lab folder entries after: [".claude.json","backups","plugins","sessions"]
```
An empty lab folder has no login, so the question (does `--restricted` work with a SUBSCRIPTION login) cannot be answered from it.
What would settle it: the owner logs in once inside the lab folder (`CLAUDE_CONFIG_DIR=D:\homelab-work\l9\lab-config`, `claude`,
`/login`; a browser is needed, so not in an unattended run on this laptop), then the same probe is run again. The L2 slice's probe
of 2026-11-11 (the real profile, not a lab folder) printed exit 0 with `--restricted`; that remains the only positive reading.
What this probe does show: with no login the call exits 1 at once, so `run_agent` raises `AgentFailed` and the callers fall back.

### Item 6 — the fake-key scan over every output

**Must hold (written before the code).** A fake key is planted in every key setting (both registry keys through the environment, both
through the fake keyring, one in `leadforge.yaml`, one inside `agent.command`'s arguments), then every command the CLI has is run
and its output, every file under the workspace's `logs` folder and every error text is scanned: the fake key appears nowhere. The fake
campaign scans its step logs, the workspace's logs and exports for its fixture key and the planted OpenCorporates token: none appears.

**What the scan found, and the fix.** Its first run was red on a real leak not listed in the plan: `config get agent` and
`config get agent.command` printed the operator's `agent.command` list whole, the planted key argument with it:
```
E       AssertionError: ["config get agent: ['agent.command argument']", "config get agent.command: ['agent.command argument']"]
1 failed in 21.05s
```
Cause: `cli._redacted` hides values by the setting's NAME (`key|token|secret|pass...`); `command` is not such a name and its value is
a list of plain strings. Fix: `config` shows `agent.command` as `[program, "<n arguments hidden>"]`, as `AgentFailed` does. After it:
`fake-key scan: 118 command runs, 8 files, 9 log records; refused by the guard: ["dns 'github.com'"]` / `1 passed in 9.91s`.

**Check by reading (after the code).** `tests/test_l9_fake_key_scan.py` walks typer's command tree (every leaf: 37, of which 35 run; `dashboard`
and `watch` are not run because they serve or follow until stopped, and the test fails if either name disappears), runs each with no
arguments and with `--json`, then a list of runs with arguments (each `config get/set` form of a key, `intake` of a UK campaign so the
key hint prints, `plan`, `doctor --json`, `status`, `enrich --stage registry`, `run`), then the real labeling path with the failing agent
(`auto_label` -> `make_ndjson_runner` -> `run_agent`; asserted `agent_failures == 1`, so the planted argument really went through a
failed call and its debug traceback), then every command again with a key written in `leadforge.yaml`. Scanned: every output and
exception text, every log record at DEBUG and up (`caplog`), every file the workspace got (logs, database, exports, icp.yaml) except
`leadforge.yaml` itself and the fake agent script. The guard refuses every outside connection and name lookup and every program except
the fake agent. The guard refused one thing: `doctor` asks `github.com` for its connectivity check (`doctor.py:313`, a HEAD request,
no download); not changed, outside this slice.

**Proof.** `1 passed in 9.91s`. Seen red first: the real leak above (before the fix), and two breaks (`breakrun.py`, restored after):
```
### AgentFailed prints the argv again (broken: src/leadforge/agent_runner.py)
E       AssertionError: ["log record: ['agent.command argument']", "leadforge_data\\logs\\leadforge.log: ['agent.command argument']"]
1 failed in 14.73s
### config get of a key prints its value (broken: src/leadforge/cli.py)
E       AssertionError: ["config get registry.companies_house_key: ['Companies House key']", "config get registry.opencorporates_token: ['OpenCorporates token']"]
1 failed in 12.97s
restored all
```

### Item 7 — the fake campaign still matches its saved result

**Prediction (written before the run).** The campaign's Companies House key moves from `leadforge.yaml` to the environment and
`registry.keyring: false` is added; the planted OpenCorporates token is ignored (provider off). No cell of `expected.json` moves.

**Result.** `scripts/e2e_fake_campaign.py --out D:\homelab-work\l9\e2e1` at below-normal priority, Windows, 2026-11-12 09:13 (tail):
```
  [10] export         exit=0 {"ok": true, "cmd": "export", "run": "run_20261112_07130_1c4b", "counts": {"leads": 10, "tier_a": 2, "tier_b": 3, "tier_c": 5, "dq": 0, "drafted": 5, "drafts_by
fake-key scan: clean (27 files: step outputs, guard and request logs, workspace logs, database, exports)
PASS - result equals tests/fixtures/e2e/expected.json (21 refused-call entries, as saved)
```
The prediction held: no cell moved. The key from the environment is really used: the fake Companies House answers 200 only to the
exact key, and its request log shows 10 `/ch/search/companies`, 2 `/ch/company/...` and 2 `.../officers`, all `200`.
The campaign's scan seen red: one line added to `CompaniesHouseRegistry.__init__` that logs the key at INFO, the campaign run once,
the line removed (`git diff --stat` of the file empty after):
```
FAIL - fake-key scan: a planted key is in 1 place(s): ['ws\\leadforge_data\\logs\\leadforge.log: Companies House key']
```

## Gate (run once, below-normal priority, 2026-11-12 09:17-09:21)

`node check.mjs` with this run's venv first on `PATH` (Python 3.12, `requirements.lock` with hashes, the package `-e` without deps,
pytest 9.2.0 and ruff 0.15.13 pinned on top) at 740433a; the tree was dirty by this slice file only (edited while the gate ran):
```
ok  versions agree  0.2
ok  skill frontmatter  0.2
ok: 2 skills open every file they name when installed alone; shared reference copies are identical
ok  skill references  0.3
ok  lint  0.2
862 passed, 6 skipped in 259.82s (0:04:19)
ok  tests  261.3
ok  cli digest  1.6
CHECK PASS sha=740433a tree=dirty steps=6 skipped=0 secs=264
```
`gitleaks` on every commit of the branch (`gitleaks detect --log-opts="origin/master..HEAD"`): no leaks (after the rewrite noted in
item 2). `python .github/scripts/check_versions.py`: all six copies `0.7.3` (unchanged, as the correction asks).

## Hosted CI

PR 11, commit f7c2f75 (the last commit with code and tests), run 43174815361 (`pull_request`): conclusion `success`, 13 of 13 jobs:
```
Version strings agree: success
fake campaign · windows-latest: success
claude plugin validate: success
windows-latest · py3.12: success
fake campaign · ubuntu-latest: success
ubuntu-latest · py3.14: success
ubuntu-latest · py3.13: success
Validate plugin manifests: success
windows-latest · py3.14: success
ubuntu-latest · py3.12: success
windows-latest · py3.11: success
ubuntu-latest · py3.11: success
windows-latest · py3.13: success
```
Both campaign jobs' logs: `fake-key scan: clean (27 files: ...)` and `PASS - result equals tests/fixtures/e2e/expected.json (21
refused-call entries, as saved)`. On Ubuntu the shim test (item 4) is skipped by design (Windows only).

## Plan and code disagree

None. `registry.py:207` held the token in `params` as the plan says. Two notes that are not disagreements: the plan's pass line "the
fake endpoint asserts no token in the URL" was written for the header case; with no documented header it holds for the default
(provider off), and when an operator switches the provider on the token is in the address by the API's own rule (tested: not in any
log or error). The L2 code comment on `NO_TOOLS_ARGS` says `--restricted` works with a subscription login (real profile, 2026-11-11);
this slice's lab probe could not log in, so it neither confirms nor contradicts it.

## Not done
- The plugin launcher's locked install (`requirements.lock`) does not carry the `keyring` extra: plugin users have the environment only.
  Adding it means regenerating the hashed lock (`scripts/make_plugin_lock.py` from `uv.lock`), which needs a network resolve; not done.
- `uv.lock` not regenerated for the new extra (nothing checks it).
- No version (the 08:55 correction): CHANGELOG under `## [Unreleased]`.

## UNPROVEN
- `--restricted` with a subscription login from a lab folder (item 5): needs one login inside the lab folder, by the owner.
- The empty `--tools` argument through the REAL npm `claude.cmd` with `node.exe` (item 4 used the same shim with Python reading
  the line).
- The real `keyring` package against a real OS backend: never imported in this run by design (the brief: the real keyring is never
  read or written). Settled by: on a throwaway user account, `pip install -e .[keyring]`, `keyring set leadforge
  registry.companies_house_key`, `leadforge config get registry.companies_house_key` prints `(from the OS keyring)`.

## Review

Run `l9-read`, 2026-11-12 09:34-10:00, STRIKERFORCE, independent reader (did not build this slice; the builder's run files
not read before the verdict). Own clone, own venv (`requirements.lock` with hashes, `-e .` without deps; pytest 9.2.0,
pytest-timeout 2.4.0, ruff 0.15.13 on top, the same pins the builder used). The whole diff against `master` (1050687) read
line by line.

1. **Token.** Followed from `RegistryCfg.opencorporates_token` to `OpenCorporatesRegistry.lookup`: the only request is
   `httpx.get(..., params=...)` (no `follow_redirects`, so a redirect is not followed and `raise_for_status` raises); no
   retry path; the error path logs `type(e).__name__` only; the `httpx` request line is cut by the filter on the `httpx`
   logger. `get_registries` adds the provider only with `opencorporates_enabled` (default `false`). Holds. The documentation
   page read once by the reader (`curl`, 2026-11-12 09:36): `HTTP 200 bytes 110067 url
   https://api.opencorporates.com/documentation/API-Reference`; the quoted sentence is there word for word:
   "Authentication is through a simple API token at present (see API accounts, below), and this should be submitted with
   each request in the query parameters." `Authorization` 0 times, `X-API` 0 times in the page. The builder's conclusion
   (no documented header, so off by default) follows from it.
2. **Keys.** No path reads a registry key from `leadforge.yaml`: `load_config` raises `KeyInConfigFile` on a non-empty
   value before merging, the message is built from the setting's name only (`key_refusal`), the root callback keeps it
   whole, `config set` refuses it and writes nothing; `config get registry.<key>` prints `<hidden, n chars> (from the ...)`.
   No other key-like setting exists in `config.py` (the proxies' `user:password@` stays, hidden since L2, as the slice
   says). `keyring==25.7.0` is an optional extra, one exact version; PyPI shows its wheel uploaded 2025-11-16 (older than 7
   days). The supply-chain note does not name `keyring` (searched: no hit), so it is neither on its never-install list
   nor listed as cleared; the builder's check (publisher, version, age) is in item 2 above. Tests replace `_keyring_get` for
   every test (autouse fixture).
3. **`AgentFailed`.** Reader's probe (outside the repository, fake keys built at run time; one key as `--api-key=<key>`,
   a second as `Authorization: Bearer <key2>`, the program echoing all arguments and then only `<key2>`), at 81c9f43:
   ```
   [exit] message:
   agent command exited 3: D:\homelab-work\l9-read\venv\Scripts\python.exe <4 arguments hidden>
   whole: <argument hidden> | <argument hidden> | <argument hidden>
   token only: FAKE-header-value-not-real
   [exit] fake key in message: False; second fake (header value) in message: True
   [cannot start] message:
   agent command could not be started: D:\homelab-work\l9-read\probe\l9read-4toapv74\no-such.exe <1 argument hidden> ([WinError 2] The system cannot find the file specified)
   [cannot start] fake key in message: False; second fake (header value) in message: False
   ```
   Cause: `_without_arguments` cut each whole argument and the part after `=`, never a word of an argument with spaces
   (the slice had listed "split" as not covered). **Fixed by the reader in 3b8acd6**: each whitespace-separated word of an
   argument is cut too. New test `test_agent_failed_cuts_a_word_of_an_argument_with_spaces`, seen red before the fix:
   ```
   E           bad token FAKE-agent-planted-for-the-scan-not-real
   FAILED tests/test_l9_agent_failed_redacts.py::test_agent_failed_cuts_a_word_of_an_argument_with_spaces
   1 failed, 4 deselected in 0.95s
   ```
   After it: `39 passed in 15.25s` (`test_l9_agent_failed_redacts.py`, `test_agent_runner.py`, `test_c1_no_tools.py`); the
   probe again: `token only: <argument hidden>` / `[exit] fake key in message: False; second fake (header value) in message:
   False`. Still not covered: a key the program prints encoded, or a word shorter than 4 characters.
4. **Fake shim.** The test drives the real `resolve_command` (real `shutil.which`, `PATH` = the shim's folder only) and the
   real `run_agent`; it compares the recorded argv with the golden's `argv[1:]`, and the golden holds `""` as its own
   element after `--tools`; one more assert checks that element. Holds. The real npm shim with `node.exe` stays UNPROVEN,
   as the slice says.
5. **`--restricted`.** The slice prints the probe's output (lab folder entries before: `[]`; `Not logged in · Please run
   /login`) and says UNPROVEN, with what would settle it. No claim beyond the output. Holds.
6. **Fake-key scan.** It walks typer's command tree (every leaf, not a chosen list) and runs each with no arguments and
   with `--json`, plus named runs with arguments. Outputs it misses: `dashboard` (the pages it serves) and `watch` are not
   run (named in `NOT_RUN`); commands needing arguments are scanned mostly at their usage error (the fake campaign covers
   the full pipeline); a word-only echo by the agent (item 3) was outside the scan's planted shape (`--api-key=<key>`).
7. **Version.** None on this branch, as the 08:55 correction asks (`master` 0.7.3): `check_versions.py` prints all six
   copies `0.7.3`; CHANGELOG under `## [Unreleased]`. `gitleaks detect --log-opts="origin/master..HEAD"` at 3b8acd6:
   `no leaks found`. Every key in the tests is built from pieces at run time; fixtures invented.
8. **Hosted CI** on 3b8acd6, run 43176859490 (`pull_request`), 13 of 13 jobs `success`:
   Validate plugin manifests, claude plugin validate, fake campaign · windows-latest, Version strings agree, fake campaign ·
   ubuntu-latest, ubuntu-latest · py3.12, ubuntu-latest · py3.11, windows-latest · py3.13, ubuntu-latest · py3.14,
   windows-latest · py3.14, windows-latest · py3.11, ubuntu-latest · py3.13, windows-latest · py3.12.

9. **Local gate**, once, `node check.mjs` at below-normal priority on 3b8acd6 (tree dirty by this Review part only), last lines:
   ```
   E           RuntimeError: worker did not become ready within 10.0s
   FAILED tests/test_ner_worker.py::test_worker_predict_returns_same_entities_it_was_given
   1 failed, 862 passed, 6 skipped in 659.28s (0:10:59)
   FAIL  tests  693.0
   CHECK FAIL sha=3b8acd6 tree=dirty steps=5 skipped=0 secs=695
   ```
   Cause: the NER worker's 10 s start limit on a laptop shared by other builders (the suite took 11 min here, 4 min in the
   builder's run); `ner_worker.py` is not touched by this slice. Re-run once alone at normal priority, as the rules say:
   `1 passed in 3.22s`. Hosted CI ran the same suite green on 13 jobs (item 8).

Verdict: PASS 3b8acd6

Merge waits for L6 and L7 (the 08:55 correction): not merged by the reader. No version on this branch.

## Brought onto master (0.9.0)

Run `l9-rebase`, 2026-11-12 11:38-, STRIKERFORCE. One merge, `git merge origin/master` (1d741bc, 0.9.0) into 00cd52d: merge commit
8362c87. No rebase, no forced push. The Spec, Build and Review parts above are left as they were written; where they name
`discovery.proxies` or `proxy.example` they describe the branch before this merge.

**Settled, file by file** (both sides read against their base 1050687):

| File | L9 wanted | master wanted | Written |
|---|---|---|---|
| `pyproject.toml` | the extra `keyring = ["keyring==25.7.0"]` (its old block still carried `social`) | `social` and `codeindex` extras gone (L8, debts) | master's block plus the one `keyring` line; nothing master removed comes back |
| `scripts/e2e_fake_campaign.py` | the Companies House key and a planted OpenCorporates token in the child's environment | `LF_FAKE_MAPS` / `maps_listings.json` renamed `LF_FAKE_LISTINGS` / `listings.json` | master's line, then L9's two environment variables and their comment |
| `skills/generate-leads/references/cli.md` | "registry keys" out of the `leadforge.yaml` line (keys are refused there) | "proxies passthrough" out of the same line | both words out: "provider order, politeness knobs, validation.staleness_days ..." |
| `tests/test_config_secrets.py` | the section check of `config get registry` with a key planted by writing the file, as a pre-L9 workspace holds it | `discovery.proxies` / `proxy.example` renamed `discovery.upstreams` / `upstream.example` | master's `upstreams` assert, then L9's planted-file check (L9's order: the file is written after the `upstreams` read) |
| `CHANGELOG.md` | its paragraph under `## [Unreleased]` | its two paragraphs (Maps out, debts) under `## [Unreleased]` | all three kept: L9's first, master's two after it |

`uv.lock`, `requirements.lock` and `tests/fixtures/dvsa_sample.csv` are master's byte for byte (`git diff --quiet origin/master --` on
the three: no difference). **Locks: master's, keyring not added.** `requirements.lock` is "no dev, no extras, no project"
(`scripts/make_plugin_lock.py`), so an extra never enters it; no test reads `uv.lock`'s extras (`tests/test_plugin_lock.py` checks only
that each pinned package and hash of `requirements.lock` is in `uv.lock`), and no test imports `keyring` (the fake from
`tests/conftest.py`). So the extra stays out of the locked install without breaking a test, as the brief allows. Left as before: `uv.lock`'s
`provides-extras` does not list `keyring` (a `uv lock` would add keyring and its dependencies; that needs a network resolve).

**Other uses of renamed names** (step 4): `git diff origin/master` over the merged tree, added lines only, searched for `LF_FAKE_MAPS`,
`maps_listings`, `proxies`, `proxy.example`, `gosom`, `social`, `codeindex`, `tenacity`, `maps`: 0 hits (the hits for `keyring` are L9's
own). The tree-wide hits for `gosom` and `social` are master's own (docs pages under their L8 note, `.claude/POSITION-HISTORY.md`). Fixed: 0.
Read too: master's new commands `forget` and `purge` (L6) are now walked by the fake-key scan like every other leaf.

**Written before any test ran** (11:42): the L9 tests and the two older changed test files pass; the fake campaign moves no cell of
master's `expected.json` (the key moves to the environment with the same value; the keyring is off; the OpenCorporates provider is off).

**L9 tests** (below-normal priority, this run's venv: `requirements.lock` with hashes, `-e .` without deps, pytest 9.2.0,
pytest-timeout 2.4.0, ruff 0.15.13), the five `test_l9_*` files plus `test_config_secrets.py` and `test_cli_contract.py`:
```
..........................................                               [100%]
42 passed in 38.41s
```
**Fake campaign** (`scripts/e2e_fake_campaign.py --out D:\homelab-work\l9-rebase\e2e1`, below-normal), tail:
```
fake-key scan: clean (25 files: step outputs, guard and request logs, workspace logs, database, exports)
PASS - result equals tests/fixtures/e2e/expected.json (3 refused-call entries, as saved)
```
The prediction held: no cell moved. The key from the environment is used: the fake Companies House's request log has 10
`/ch/search/companies`, 2 `/ch/company/...`, 2 `.../officers`, all `"status": 200`.

**Static checks.** `ruff check pyproject.toml scripts/e2e_fake_campaign.py tests/test_config_secrets.py`: `All checks passed!`.
`python .github/scripts/check_versions.py`: all six copies `0.9.0` (master's; this branch sets none). `gitleaks detect
--log-opts="origin/master..HEAD"` (8.30.1): `10 commits scanned.` / `no leaks found`.

**Gate**, once, `node check.mjs` at below-normal priority with this run's venv first on `PATH`, on 8362c87 (tree dirty by this part
only, written while the gate ran), 11:45-11:50:
```
ok  versions agree  0.2
ok  skill frontmatter  0.1
ok  skill references  0.3
ok  lint  1.2
967 passed, 3 skipped in 294.62s (0:04:54)
ok  tests  296.0
ok  cli digest  2.4
CHECK PASS sha=8362c87 tree=dirty steps=6 skipped=0 secs=300
```

**Hosted CI on 8362c87** (the merge commit), read with `gh run view`:
- run 43193533865 (`pull_request`), `completed success`, 13 of 13 jobs `success`: claude plugin validate, fake campaign ·
  windows-latest, Validate plugin manifests, Version strings agree, ubuntu-latest · py3.11, fake campaign · ubuntu-latest,
  ubuntu-latest · py3.14, windows-latest · py3.12, ubuntu-latest · py3.13, windows-latest · py3.11, windows-latest · py3.14,
  windows-latest · py3.13, ubuntu-latest · py3.12.
- run 43193527061 (`push`, the mutation trial: the merge brings master's L6 delete modules into the branch's diff), `completed
  success`, 1 job: "mutmut on the delete modules · ubuntu-latest: success". 14 checks on 8362c87, 0 failed, 0 pending.

The CI of the commit that adds this part (slice file only) is read by the run and written in its report and on the pull request,
not here (a commit cannot hold its own CI result).

Not done here: no merge into `master` (the brief: an independent reader re-judges and merges). The Review part's verdict
(PASS 3b8acd6) was given before this merge; it needs refreshing on the new head.

## Review 2 (on master 0.9.0)

Run `l9-reread`, 2026-11-12 11:58-, STRIKERFORCE, an independent reader who saw neither the build nor the merge being written. Read
on 00bd92b (merge 8362c87 = 00cd52d + master 1d741bc, then the slice-file commit). `origin/master` is still 1d741bc, an ancestor of
the branch.

**The merge, read three ways.** `git merge-tree --write-tree 00cd52d 1d741bc` conflicts in exactly the five files the part above
lists (CHANGELOG.md, pyproject.toml, scripts/e2e_fake_campaign.py, skills/generate-leads/references/cli.md,
tests/test_config_secrets.py); `git diff <that tree> 8362c87` touches only those five, so every other file is git's own merge,
nothing hand-written. Each of the five read against both parents (`git show --cc 8362c87`): master's names kept
(`LF_FAKE_LISTINGS`, `listings.json`, `discovery.upstreams`, `upstream.example`), master's removals stay removed (`social`,
`codeindex` extras), L9's lines kept (the `keyring` extra, both planted environment keys, the planted-file check, its CHANGELOG
paragraph). Auto-merged files where both sides moved (cli.py `_root` and `_redacted`, config.py imports, intake.py, the example
yaml) read too: both sides' lines present.

**Names master removed** (`git grep -i -F` over src, scripts, tests, skills, config, pyproject, manifests, .github): `LF_FAKE_MAPS`,
`maps_listings`, `discovery.proxies`, `proxy.example`, `gosom`, `codeindex`, `tenacity`: 0 files. `social`: hits only in code
master already has (social links, scoring signals). Added lines of `git diff origin/master HEAD` (outside docs and CHANGELOG)
searched for `maps|gosom|social|codeindex|tenacity|proxies|proxy.example`: 0.

**L9's five behaviours on the merged code** (read first; the gate and the fake campaign below settle what reading could not):
1. Token in no address, log or error: OpenCorporates is off unless `registry.opencorporates_enabled`; switched on, httpx's
   request line has `api_token=` cut (`_CutApiToken`), a failed lookup logs the exception's type name only, the evidence address is
   the response's `opencorporates_url`. Companies House sends its key as basic auth, never in the address. Holds.
2. No key from `leadforge.yaml`: the only readers of that file in `src` are `load_config` (refuses `registry.<key>` by name before
   merging) and `config set` (writes to a temporary copy, loads it, writes nothing on `KeyInConfigFile`). Master's delete and collect
   sides (retention.py, browser_profile.py, send_rules.py, the new export code) take `cfg` from `load_config`; none parses the yaml.
   Holds.
3. `AgentFailed`: every raise shows `_shown_command` (program plus a count) and passes stderr / OS error through
   `_without_arguments`, which also cuts each word of an argument with spaces; `from None` on the two re-raises. Holds.
4. Empty `--tools`: `tests/golden/autopilot_builtin_command.json` still has `"--tools", ""`; the shim test compares the recorded argv
   to it. Holds (Windows only; it ran in the gate here).
5. Fake-key scan: walks every leaf command (39 on the merged CLI, `forget`, `purge`, `suppress`, `export` among them; `dashboard`
   and `watch` named as not run) twice, then again with a key in the file; the fake campaign scans the exports with master's new
   source and date columns filled. Holds. Limit, not a defect: in the unit scan `forget` and `suppress` run without an argument
   (usage message), so their work path is scanned only through the code they share with the rest.

**Locks.** `git diff --stat origin/master HEAD` lists neither `uv.lock` nor `requirements.lock`: master's, byte for byte. pyproject
moves by one line (the `keyring` extra). No other version moved: `python .github/scripts/check_versions.py`:
```
{'pyproject': '0.9.0', '__init__': '0.9.0', 'claude-plugin': '0.9.0', 'codex-plugin': '0.9.0', 'skill generate-leads': '0.9.0', 'skill send-outreach': '0.9.0'}
```

**Keys in tests.** Every planted key is built at run time from pieces (`"-".join(["FAKE", ...])`); the Companies House key of the
fake campaign is master's fixture value `fixture-key`. The real keyring is replaced for every test (`tests/conftest.py`
`_never_the_real_keyring`, autouse). `gitleaks detect --log-opts="origin/master..HEAD"` (8.30.1):
```
12:06PM INF 11 commits scanned.
12:06PM INF scanned ~77156 bytes (77.16 KB) in 378ms
12:06PM INF no leaks found
```
(12 commits in the range; gitleaks' `git log -p` shows no diff for the merge commit, whose lines come from the 11.)
`ruff check` on the eleven touched Python files: `All checks passed!`

**Gate**, once, this run's venv (`requirements.lock` with hashes, `-e .` without deps, pytest 9.2.0, pytest-timeout 2.4.0, ruff
0.15.13), below-normal priority, 12:01-12:06:
```
967 passed, 3 skipped in 270.63s (0:04:30)
ok  tests  272.7
leadforge --json version: 1 LF_DIGEST line(s)
leadforge --json status: 1 LF_DIGEST line(s)
ok  cli digest  1.5
CHECK PASS sha=00bd92b tree=clean steps=6 skipped=0 secs=277
```
**Fake campaign** (`scripts/e2e_fake_campaign.py --out D:\homelab-work\l9-reread\e2e`), tail:
```
fake-key scan: clean (25 files: step outputs, guard and request logs, workspace logs, database, exports)
PASS - result equals tests/fixtures/e2e/expected.json (3 refused-call entries, as saved)
```
`tests/fixtures/e2e/expected.json` is master's (not in the branch's diff).

**Hosted CI on 00bd92b** (`gh pr checks 11`, run 43195131934, `pull_request`, headSha 00bd92b76a2f…): 13 of 13 pass: Validate
plugin manifests, Version strings agree, claude plugin validate, fake campaign · ubuntu-latest, fake campaign · windows-latest,
ubuntu-latest · py3.11, py3.12, py3.13, py3.14, windows-latest · py3.11, py3.12, py3.13, py3.14. 0 failed, 0 pending.

Fixed by the reader: nothing. The commit that adds this part changes this file only; its own CI is read before the merge and stated
in the run's report and on the pull request.

Verdict: PASS 00bd92b
