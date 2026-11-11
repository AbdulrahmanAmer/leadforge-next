"""Write requirements.lock: the hashed lock the plugin launcher (bin/leadforge) installs from (C3).

    uv run python scripts/make_plugin_lock.py

It is `uv export` of the runtime dependencies in uv.lock (no dev, no extras, no project) plus the build
backend from uv.lock, because the launcher builds the project with --no-build-isolation: nothing it
installs is fetched without a hash. Re-run after every change to uv.lock; tests/test_plugin_lock.py
fails while the two disagree.
"""
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_BACKEND = "setuptools"
HEADER = """\
# The plugin launcher's hashed lock (C3). Generated from uv.lock by scripts/make_plugin_lock.py; do not
# edit by hand. bin/leadforge installs it with `pip install --require-hashes`, so a changed file is refused.
"""


def build_backend_block(lock: dict) -> str:
    pkg = next(p for p in lock["package"] if p["name"] == BUILD_BACKEND)
    hashes = [w["hash"] for w in pkg.get("wheels", [])] + ([pkg["sdist"]["hash"]] if "sdist" in pkg else [])
    lines = [f"{BUILD_BACKEND}=={pkg['version']}"] + [f"    --hash={h}" for h in hashes]
    return " \\\n".join(lines) + "\n    # build backend, for pip install --no-build-isolation\n"


def main() -> int:
    exported = subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-header",
         "--format", "requirements-txt"],
        cwd=ROOT, capture_output=True, encoding="utf-8", check=True, timeout=120).stdout
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    text = HEADER + exported
    if f"\n{BUILD_BACKEND}==" not in "\n" + exported:
        text += build_backend_block(lock)
    (ROOT / "requirements.lock").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote requirements.lock ({text.count('==')} pinned packages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
