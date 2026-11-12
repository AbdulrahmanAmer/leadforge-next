# keyring-lock   (a hashed lock for the keyring extra, so the window's bundle can install it)
Type: packaging   Stacks: python   Version: 0.9.0 (not changed; changelog lines are under "Unreleased")   Base: 2fb6b93 (`origin/master`)
Guardrail: no   Owner: no

## Spec
The lead's words (2026-11-12 14:40): the lock the window's bundle installs from must carry keyring 25.7.0 and everything it needs
on Windows, each with hashes, and uv.lock must list the extra; a test that fails when the lock lacks any pin of the extra; the
supply-chain checks on the new packages (publisher, date, wheel-only) written in the slice file. Whether keyring becomes part of the
main lock or a second hashed lock for the window is the builder's choice; say which, and the exact install line the packaging must use.

Why: the window's bundle installs the engine with `pip install --require-hashes --only-binary :all:` from `requirements.lock`, as CI
does. `keyring` is only in pyproject's `keyring` extra (`keyring==25.7.0`), in neither `requirements.lock` nor `uv.lock`, so in the
bundled engine `keys_list`, `key_save` and `key_remove` answer with kind `environment`. The Keys screen is blocked on this.

The decision (Jay, 2026-11-12): a SECOND hashed lock. `requirements.lock` stays as it is: it is what every plugin user installs, and
the extra is optional ("without it, the environment only"). The keyring extra gets its own hashed lock, `requirements-keyring.lock`,
compiled UNDER the main lock as a constraint (no package of the main lock may appear in it at another version), holding `keyring` at
pyproject's pin and its whole dependency closure for Windows AND Linux (environment markers where they differ), every line with
hashes, wheels only. The window's install line is then ONE command with both files. If the closure needs a package without a wheel,
or a different version of something in the main lock: stop, write the reason, do not fall back to the main lock.

The lead's decision (2026-11-12 14:45): the plugin launcher does NOT install the second lock in this release.

## Build
What must hold (written before anything was resolved):
1. `uv.lock` lists the extra `keyring` (in `provides-extras` and as an optional dependency of `leadforge`) with keyring 25.7.0 and its
   closure; regenerated without upgrading: every package already in `uv.lock` keeps its version; the diff only adds.
2. `requirements-keyring.lock` holds `keyring==25.7.0` (pyproject's pin) and every package of the extra's closure that
   `requirements.lock` does not already hold, for Windows and Linux (markers where they differ), each with `--hash` lines; no name in
   it appears in `requirements.lock` (so none can differ in version); a comment at its top says how it was made.
3. `scripts/make_plugin_lock.py` writes both files in one run; `requirements.lock` comes out byte-identical to today's.
4. Every new package: at least 7 days old today (2026-11-12), not on the never-install list, a wheel for Windows x64 and Linux x64
   on CPython 3.11 to 3.14 (pure-python `py3-none-any` counts), so `--only-binary :all:` installs it; nothing runs at install time.
5. A unit test fails when the keyring lock's `keyring` pin differs from pyproject's extra, when a line has no hash, or when a package
   in it differs in version from `requirements.lock`.
6. Hosted CI, inside the existing `fake campaign` jobs (ubuntu-latest and windows-latest; still 13 named jobs): a fresh environment,
   `python -m pip install --require-hashes --only-binary :all: -r requirements.lock -r requirements-keyring.lock`, then
   `python -c "import keyring"`. A missing pin of the closure fails that install.
7. Locally: the same install into `D:\homelab-work\keyring-lock\venv-proof`; `leadforge window keys_list` in a fixture workspace
   answers a list, not kind `environment`, with a fake keyring backend (this laptop's real keyring is never read or written).

### What was built (c78e63b and the docs commit after it)
- `uv.lock`: `uv lock` with uv 0.13.7 (the version the debts slice used; this laptop's own uv 0.11.9 rewrote the lock's
  `revision` 5 -> 3 and the nvidia markers, so that result was thrown away). uv 0.13.7 was installed only into the run's own lab
  environment, hash-pinned (`uv==0.13.7`, publisher Astral, uploaded 2026-11-03, a wheel). Output: `Added backports-tarfile v1.2.0,
  jaraco-classes v3.4.0, jaraco-context v6.1.2, jaraco-functools v4.6.0, jeepney v0.9.0, keyring v25.7.0, more-itertools v11.2.1,
  pywin32-ctypes v0.2.3, secretstorage v3.5.0`, `Updated leadforge v0.8.0 -> v0.9.0` (the project's own entry catching up with
  pyproject, not a bump). `git diff --stat`: `uv.lock | 111 +++-- 1 file changed, 109 insertions(+), 2 deletions(-)`; the two
  removed lines are `version = "0.8.0"` and `provides-extras = ["browser", "ner", "addressing", "dev"]` of leadforge's own entry.
  Name-by-name comparison (`proof/uvlock_diff.py`):
  ```
  packages before 159, after 168
  added (9): backports-tarfile, jaraco-classes, jaraco-context, jaraco-functools, jeepney, keyring, more-itertools, pywin32-ctypes, secretstorage
  removed (0): none
  versions moved (1): leadforge 0.8.0 -> 0.9.0
  ```
- `scripts/make_plugin_lock.py` writes both locks in one run: `requirements.lock` as before (byte-identical: 0 differing lines),
  and `requirements-keyring.lock` = `uv export --extra keyring` less every package `requirements.lock` holds (the script stops if a
  shared package ever had another version). Output: `wrote requirements.lock (46 pinned packages)` / `wrote
  requirements-keyring.lock (15 pinned packages)`.
- `requirements-keyring.lock`, 15 packages: backports-tarfile, cffi, cryptography, importlib-metadata, jaraco-classes,
  jaraco-context, jaraco-functools, jeepney, keyring, lazy-importer, more-itertools, pycparser, pywin32-ctypes, secretstorage, zipp.
  Six of them (cffi, cryptography, importlib-metadata, lazy-importer, pycparser, zipp) were already in `uv.lock` (other extras),
  none in `requirements.lock`: no package appears in both locks, so none can differ in version.
- `tests/test_keyring_lock.py` (2 tests) and the CI step "Install the keyring lock (fresh environment, both locks, wheels only)"
  at the end of the existing `fake campaign` jobs (ubuntu-latest, windows-latest; still 13 named jobs).

### Supply chain (PyPI JSON API read 2026-11-12)
The scripts named `proof/...` below live in the run's lab folder `D:\homelab-work\keyring-lock\proof`, not in the repository.
"days" = whole days from the first upload of that version to 2026-11-12 00:00 UTC. Maintainers = PyPI's `ownership` roles.
Wheel columns: a wheel installable on CPython 3.11, 3.12, 3.13, 3.14 (y/n each) for Windows x64 and Linux x64 (manylinux);
`--only-binary :all:` so no sdist is ever built and nothing runs at install time. Never-install list of
`supply-chain-2026-10.md`: none of the 15 is on it.

| name | version | marker | uploaded | days | PyPI maintainers | win x64 3.11-3.14 | linux x64 3.11-3.14 | wheels | yanked | never-install |
|---|---|---|---|---|---|---|---|---|---|---|
| backports-tarfile | 1.2.0 | python_full_version < '3.12' | 2024-05-28 | 897 | jaraco (Owner) | yyyy | yyyy | 1 | False | False |
| cffi | 2.1.1 | platform_python_implementation != 'PyPy' and sys_platform == 'linux' | 2026-08-03 | 100 | Armin.Rigo (Owner),alexgaynor (Maintainer),fijal (Owner),glyph (Maintainer),mattclay (Owner),nitzmahone (Owner),odidev (Maintainer),reaperhulk (Maintainer) | yyyy | yyyy | 99 | False | False |
| cryptography | 50.0.2 | sys_platform == 'linux' | 2026-09-30 | 42 | reaperhulk (Owner),org pyca | yyyy | yyyy | 58 | False | False |
| importlib-metadata | 10.2.0 | python_full_version < '3.12' | 2026-11-09 | 2 | barry (Owner),brettcannon (Owner),jaraco (Owner) | yyyy | yyyy | 1 | False | False |
| jaraco-classes | 3.4.0 | all | 2024-03-31 | 955 | jaraco (Owner) | yyyy | yyyy | 1 | False | False |
| jaraco-context | 6.1.2 | all | 2026-03-20 | 236 | jaraco (Owner) | yyyy | yyyy | 1 | False | False |
| jaraco-functools | 4.6.0 | all | 2026-07-14 | 120 | jaraco (Owner) | yyyy | yyyy | 1 | False | False |
| jeepney | 0.9.0 | sys_platform == 'linux' | 2025-02-27 | 622 | takowl (Owner) | yyyy | yyyy | 1 | False | False |
| keyring | 25.7.0 | all | 2025-11-16 | 360 | jaraco (Owner) | yyyy | yyyy | 1 | False | False |
| lazy-importer | 0.1.0 | python_full_version < '3.12' | 2026-10-20 | 22 | pganssle (Owner) | yyyy | yyyy | 1 | False | False |
| more-itertools | 11.2.1 | all | 2026-10-14 | 28 | bbayles (Maintainer),erikrose (Owner) | yyyy | yyyy | 1 | False | False |
| pycparser | 3.12 | implementation_name != 'PyPy' and platform_python_implementation != 'PyPy' and sys_platform == 'linux' | 2026-10-22 | 20 | eliben (Owner) | yyyy | yyyy | 1 | False | False |
| pywin32-ctypes | 0.2.3 | sys_platform == 'win32' | 2024-08-14 | 819 | enthought (Owner),itziakos (Maintainer) | yyyy | yyyy | 1 | False | False |
| secretstorage | 3.5.0 | sys_platform == 'linux' | 2025-11-23 | 353 | mitya57 (Owner) | yyyy | yyyy | 1 | False | False |
| zipp | 4.1.2 | python_full_version < '3.12' | 2026-10-21 | 21 | jaraco (Owner) | yyyy | yyyy | 1 | False | False |

**BLOCKED (merge): `importlib-metadata==10.2.0` was uploaded 2026-11-09, under the 7-day floor.** It is in the closure only on
Python 3.11 (`python_full_version < '3.12'`, keyring's own requirement). It was already in master's `uv.lock` (since 4cb3a58,
2026-11-11, through another extra); this branch puts it into an install lock for the first time. The builder did not swap it for
an older version: that would be a hand-made lock that disagrees with `uv.lock`. Unblocked by: 2026-11-16 (7 days), with no change
to the files; or the lead's choice of another way. Nothing in this run installed it (the local proof and both CI install steps run
Python 3.12, where the marker leaves it out).

**Seen, outside this slice:** `regex==2026.11.9` in master's `requirements.lock` was also uploaded 2026-11-09 (PyPI). Not changed here.

### Decisions
- **A second lock, not the main lock** (Jay's decision). Install line of the window's bundle, one command:
  `python -m pip install --require-hashes --only-binary :all: -r requirements.lock -r requirements-keyring.lock`
- **The plugin launcher does not install the second lock in this release** (the lead, 2026-11-12 14:45): `requirements.lock` stays
  what every plugin user installs, and L9's rule holds: without keyring, the environment only. `bin/leadforge` is not changed.
- The builder's own: the keyring lock is derived from the one `uv.lock` (so "under the main lock" holds by construction and is
  checked by the script and the test); the CI proof sits at the end of the `fake campaign` jobs (Python 3.12, both systems) in its
  own `.kr` environment, so the campaign's own install is untouched; the closure test walks `uv.lock` from `keyring` with every
  marker, so a package needed on either system is checked offline too.

### Open items (not built)
- Opt-in keyring for the plugin launcher.
- `src/leadforge/data/licences.json` covers `requirements.lock` only; the window's About does not list the second lock's packages.
- The 3.11 path of the closure (backports-tarfile, importlib-metadata, lazy-importer, zipp) is never installed by CI: the install
  step runs on Python 3.12 only. Settled by running the same step on a 3.11 job after 2026-11-16.

### Proof
Unit tests, then the same two tests against tampered copies of the lock (`proof/red_unit.py`):
```
5 passed in 111.91s (0:01:51)      # tests/test_keyring_lock.py tests/test_plugin_lock.py
RED  a pin of the closure missing (more-itertools): more-itertools (reached from keyring in uv.lock) is in neither lock
RED  a pin without hashes (jeepney): jeepney==0.9.0 has no hash
RED  keyring at another version: lock ('25.6.0', {...}), pyproject ['keyring==25.7.0']
RED  a package at another version than requirements.lock (certifi): certifi: keyring lock 2020.1.1, requirements.lock 2026.10.23
GREEN  both tests on the real lock
```
The install, red with one dependency line removed (more-itertools), in `D:\homelab-work\keyring-lock\venv-proof` (Python 3.12):
```
Collecting more-itertools (from jaraco-classes==3.4.0->-r proof\red\requirements-keyring.lock (line 164))
ERROR: In --require-hashes mode, all requirements must have their versions pinned with ==. These do not:
    more-itertools from https://files.pythonhosted.org/packages/5d/57/3c4b1c6f2e0cc29ba023802458ea3d2a996f87085559e4a5f2192d549532/more_itertools-11.2.1-py3-none-any.whl (from jaraco-classes==3.4.0->-r proof\red\requirements-keyring.lock (line 164))
exit=1
```
then green with the real files (`exit=0`, `... jaraco-classes-3.4.0 jaraco-context-6.1.2 jaraco-functools-4.6.0 ... keyring-25.7.0
... more-itertools-11.2.1 ... pywin32-ctypes-0.2.3 ...`). `leadforge window` in an empty fixture workspace, the keyring backend a
fake (`PYTHON_KEYRING_BACKEND=fakekr.FakeKeyring`, a JSON file; the OS keyring never read or written):
```
--- without the keyring extra (the dev environment, requirements.lock only)
keys_list exit=3  {"kind":"environment","message":"Keys cannot be kept in the keyring on this computer.","details":["the keyring package is not installed"],"next":"Install the keyring extra: pip install leadforge[keyring]"}
--- with requirements.lock + requirements-keyring.lock (venv-proof)
backend in use: fakekr.FakeKeyring
keys_list exit=0  [{"name":"companies_house_key","saved":false,"inUse":false,"savedAt":null},{"name":"opencorporates_token","saved":false,"inUse":false,"savedAt":null}]
key_save exit=0  {"name":"companies_house_key","saved":true,"inUse":true,"savedAt":null}
keys_list exit=0  [{"name":"companies_house_key","saved":true,"inUse":true,"savedAt":null},{"name":"opencorporates_token","saved":false,"inUse":false,"savedAt":null}]
fake store entries: leadforge/registry.companies_house_key
key_remove exit=0  {"name":"companies_house_key","saved":false,"inUse":false,"savedAt":null}
keys_list exit=0  [{"name":"companies_house_key","saved":false,"inUse":false,"savedAt":null},{"name":"opencorporates_token","saved":false,"inUse":false,"savedAt":null}]
```
