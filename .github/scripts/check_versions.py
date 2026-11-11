#!/usr/bin/env python3
"""Every version copy must agree: pyproject == __init__ == both plugin manifests == both skills.

A release tag (GITHUB_REF=refs/tags/vX.Y.Z) or `node check.mjs --version X.Y.Z` (LF_RELEASE_VERSION) is the
external anchor: otherwise stale-but-agreeing strings sail through (happened at v0.1.2/v0.1.3).
Plugin users only receive an update when .claude-plugin/plugin.json changes, so a drift here freezes them.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def skill(rel: str) -> str:
    return re.search(r'version: "([^"]+)"', read(rel)).group(1)


versions = {
    "pyproject": tomllib.loads(read("pyproject.toml"))["project"]["version"],
    "__init__": re.search(r'__version__ = "([^"]+)"', read("src/leadforge/__init__.py")).group(1),
    "claude-plugin": json.loads(read(".claude-plugin/plugin.json"))["version"],
    "codex-plugin": json.loads(read(".codex-plugin/plugin.json"))["version"],
    "skill generate-leads": skill("skills/generate-leads/SKILL.md"),
    "skill send-outreach": skill("skills/send-outreach/SKILL.md"),
}
ref = os.environ.get("GITHUB_REF", "")
if ref.startswith("refs/tags/v"):
    versions["tag"] = ref.removeprefix("refs/tags/v")
if os.environ.get("LF_RELEASE_VERSION"):
    versions["--version"] = os.environ["LF_RELEASE_VERSION"]
print(versions)
if len(set(versions.values())) != 1:
    print("version copies disagree", file=sys.stderr)
    sys.exit(1)
