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

### Item 5 — `--restricted` with a subscription login, one probe

**Must hold.** One `claude -p --restricted` call with `CLAUDE_CONFIG_DIR=D:\homelab-work\l9\lab-config` (an empty folder; nothing
copied from the real profile), a one-word prompt on stdin, API-key variables removed from the child's environment. What it prints is
written here as printed.

### Item 6 — the fake-key scan over every output

**Must hold (written before the code).** A fake key is planted in every key setting (both registry keys through the environment, both
through the fake keyring, one in `leadforge.yaml`, one inside `agent.command`'s arguments), then every command the CLI has is run
and its output, every file under the workspace's `logs` folder and every error text is scanned: the fake key appears nowhere. The fake
campaign scans its step logs, the workspace's logs and exports for its fixture key and the planted OpenCorporates token: none appears.

### Item 7 — the fake campaign still matches its saved result

**Prediction (written before the run).** The campaign's Companies House key moves from `leadforge.yaml` to the environment and
`registry.keyring: false` is added; the planted OpenCorporates token is ignored (provider off). No cell of `expected.json` moves.

## Plan and code disagree

(none yet)
