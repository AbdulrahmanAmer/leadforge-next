#!/usr/bin/env python3
"""CI guard: a skill must open every file it names after it is installed ALONE.

A skills tool (`npx skills add`, a hand copy) copies one skill's folder and nothing else, so a path that climbs out of
the folder (`../generate-leads/references/x.md`) is a dead link there. For each skill this installs it alone (that
folder, copied into an empty one) and requires that every `references/<file>.md` its SKILL.md names exists beside it,
and that no path in it uses `../`. Reference files that live in more than one skill must stay byte-identical.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NAMED = re.compile(r"(?<![\w.-])((?:\.\./)*references/[\w.-]+\.md)")
CLIMB = re.compile(r"\.\./[\w.-]+/(?:[\w.-]+/)*[\w.-]+\.md")

skills = sorted(p.parent for p in REPO.glob("skills/*/SKILL.md"))
if not skills:
    print("no SKILL.md files found under skills/", file=sys.stderr)
    raise SystemExit(1)

failures: list[str] = []
for skill in skills:
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    failures += [f"{skill.name}: SKILL.md names {m} which leaves the skill's own folder" for m in sorted(set(CLIMB.findall(text)))]
    with tempfile.TemporaryDirectory() as td:
        alone = Path(td) / "skills" / skill.name  # the only thing in this skills folder
        shutil.copytree(skill, alone)
        for rel in sorted({m.removeprefix("../") for m in NAMED.findall(text)}):
            if not (alone / rel).is_file():
                failures.append(f"{skill.name}: SKILL.md names {rel} but it is not in the skill's own folder when installed alone")

seen: dict[str, list[Path]] = {}
for skill in skills:
    for f in sorted((skill / "references").glob("*.md")) if (skill / "references").is_dir() else []:
        seen.setdefault(f.name, []).append(f)
for name, copies in sorted(seen.items()):
    first = copies[0].read_bytes()
    failures += [f"references/{name}: {c.parent.parent.name} differs from {copies[0].parent.parent.name} (copies must be identical)"
                 for c in copies[1:] if c.read_bytes() != first]

if failures:
    print("skill references broken:\n  " + "\n  ".join(failures), file=sys.stderr)
    raise SystemExit(1)
print(f"ok: {len(skills)} skills open every file they name when installed alone; shared reference copies are identical")
