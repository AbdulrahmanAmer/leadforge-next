"""Write src/leadforge/data/licences.json: the licence notices of every package in requirements.lock (C15, slice L11a).

    python scripts/make_licence_notices.py          # (re)write the file from the installed packages' own metadata
    python scripts/make_licence_notices.py --check  # exit 1 when the file does not match the lock (older than it)

Run it with the interpreter of an environment installed from requirements.lock (`pip install --require-hashes -r
requirements.lock`): each package's licence and notice text are read from its installed metadata (License-Expression,
License, the licence classifiers, and the licence files it ships), never typed by hand. The file records the lock's
SHA-256, so a changed lock makes `--check` and tests/test_window_licences.py fail until the file is made again.
`leadforge window about` returns its packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock"
OUT = ROOT / "src" / "leadforge" / "data" / "licences.json"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")
LICENCE_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$", re.IGNORECASE)


def lock_hash(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def locked(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for ln in text.splitlines() if (m := PIN.match(ln))]


def licence_of(meta) -> str:
    expr = meta.get("License-Expression")
    if expr:
        return expr.strip()
    classifiers = [c.split(" :: ")[-1] for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return " OR ".join(classifiers)
    lic = (meta.get("License") or "").strip()
    return lic.splitlines()[0][:120] if lic else "not stated in the package metadata"


def notice_of(dist) -> str:
    texts = []
    for f in sorted(dist.files or [], key=str):
        if LICENCE_FILE.search(str(f).replace("\\", "/")):
            try:
                texts.append(f"--- {Path(str(f)).name} ---\n" + Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace").strip())
            except OSError:
                continue
    if texts:
        return "\n\n".join(texts)
    lic = (dist.metadata.get("License") or "").strip()
    return lic if len(lic) > 120 else ""


def build(lock_text: str) -> dict:
    packages = []
    for name, version in locked(lock_text):
        entry = {"name": name, "version": version}
        try:
            dist = distribution(name)
        except PackageNotFoundError:
            # a package for another platform only (its lock line has a marker): no metadata on this machine
            entry.update(licence="not installed where this file was made", notice="", installed=False)
            packages.append(entry)
            continue
        if dist.version != version:
            raise SystemExit(f"{name}: installed {dist.version}, locked {version}; install from requirements.lock first")
        entry.update(licence=licence_of(dist.metadata), notice=notice_of(dist), installed=True)
        packages.append(entry)
    return {"made_by": "scripts/make_licence_notices.py", "lock": "requirements.lock", "lock_sha256": lock_hash(lock_text),
            "packages": packages}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    lock_text = LOCK.read_text(encoding="utf-8")
    if a.check:
        have = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
        if have.get("lock_sha256") != lock_hash(lock_text):
            print(f"{OUT.relative_to(ROOT)} is older than requirements.lock: run scripts/make_licence_notices.py", file=sys.stderr)
            return 1
        print("licence notices match the lock")
        return 0
    OUT.write_text(json.dumps(build(lock_text), indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
