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
