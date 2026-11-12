"""Write the two hashed locks from uv.lock: requirements.lock (C3) and requirements-keyring.lock (slice keyring-lock).

    uv run python scripts/make_plugin_lock.py

requirements.lock is what the plugin launcher (bin/leadforge) installs: `uv export` of the runtime dependencies in uv.lock
(no dev, no extras, no project) plus the build backend from uv.lock, because the launcher builds the project with
--no-build-isolation: nothing it installs is fetched without a hash.

requirements-keyring.lock is the `keyring` extra on top of it, for the window's bundle: `uv export` with that extra, less
every package requirements.lock already holds. Both come from the one uv.lock, so a package in both would have the same
version; the script stops if one ever does not. Install both with one command:

    python -m pip install --require-hashes --only-binary :all: -r requirements.lock -r requirements-keyring.lock

Re-run after every change to uv.lock; tests/test_plugin_lock.py and tests/test_keyring_lock.py fail while they disagree.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_BACKEND = "setuptools"
KEYRING_EXTRA = "keyring"
HEADER = """\
# The plugin launcher's hashed lock (C3). Generated from uv.lock by scripts/make_plugin_lock.py; do not
# edit by hand. bin/leadforge installs it with `pip install --require-hashes`, so a changed file is refused.
"""
KEYRING_HEADER = """\
# The `keyring` extra's hashed lock, on top of requirements.lock (slice keyring-lock). Generated from uv.lock by
# scripts/make_plugin_lock.py (`uv export --extra keyring`, less every package requirements.lock holds); do not edit
# by hand. The window's bundle installs both in one command:
#   python -m pip install --require-hashes --only-binary :all: -r requirements.lock -r requirements-keyring.lock
"""


def build_backend_block(lock: dict) -> str:
    pkg = next(p for p in lock["package"] if p["name"] == BUILD_BACKEND)
    hashes = [w["hash"] for w in pkg.get("wheels", [])] + ([pkg["sdist"]["hash"]] if "sdist" in pkg else [])
    lines = [f"{BUILD_BACKEND}=={pkg['version']}"] + [f"    --hash={h}" for h in hashes]
    return " \\\n".join(lines) + "\n    # build backend, for pip install --no-build-isolation\n"


def export(*extra: str) -> str:
    return subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-header",
         "--format", "requirements-txt", *extra],
        cwd=ROOT, capture_output=True, encoding="utf-8", check=True, timeout=120).stdout


def blocks(text: str) -> list[tuple[str, str, str]]:
    """(name, version, block) of each pinned package in uv export's layout (a pin line, its hashes, its `via` comments)."""
    out = []
    for block in re.split(r"\n(?=[A-Za-z0-9])", text):
        m = re.match(r"([A-Za-z0-9_.\-]+)==([^\s;\\]+)", block)
        if m:
            out.append((m.group(1).lower(), m.group(2), block.rstrip("\n") + "\n"))
    return out


def keyring_lock(main: str) -> str:
    held = {name: version for name, version, _ in blocks(main)}
    own = []
    for name, version, block in blocks(export("--extra", KEYRING_EXTRA)):
        if name in held:
            if held[name] != version:   # cannot happen from one uv.lock; stop rather than write two versions
                raise SystemExit(f"{name}: requirements.lock pins {held[name]}, the keyring extra {version}")
            continue
        own.append(block)
    return KEYRING_HEADER + "".join(own)


def main() -> int:
    exported = export()
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    text = HEADER + exported
    if f"\n{BUILD_BACKEND}==" not in "\n" + exported:
        text += build_backend_block(lock)
    (ROOT / "requirements.lock").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote requirements.lock ({text.count('==')} pinned packages)")
    extra = keyring_lock(text)
    (ROOT / "requirements-keyring.lock").write_text(extra, encoding="utf-8", newline="\n")
    print(f"wrote requirements-keyring.lock ({len(blocks(extra))} pinned packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
