"""Golden contracts (slice L2, adoption plan section 3): what users and agents rely on, pinned to files in
tests/golden/. A change here is a contract change: it must be listed in the slice that makes it.

To re-record after a DELIBERATE change:  LF_UPDATE_GOLDEN=1 python -m pytest tests/test_golden_contracts.py
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from importlib.resources import files
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).parent / "golden"


def _check(name: str, actual) -> None:
    path = GOLDEN / f"{name}.json"
    text = json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("LF_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return
    assert path.exists(), f"golden {path.name} missing: record it with LF_UPDATE_GOLDEN=1"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, f"contract '{name}' changed; if deliberate, list it in the slice and re-record"


def _frontmatter(p: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
    return yaml.safe_load(m.group(1))


# --- 8. the plugin contract: plugin name, skill names, both manifests -------------------------------
def test_golden_plugin_contract():
    claude = json.loads((REPO / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    codex = json.loads((REPO / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    agents_market = json.loads((REPO / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    skills = {p.parent.name: _frontmatter(p)["name"] for p in sorted(REPO.glob("skills/*/SKILL.md"))}
    _check("plugin_contract", {
        "claude_plugin_name": claude["name"],
        "codex_plugin_name": codex["name"],
        "claude_marketplace": {"name": market["name"],
                               "plugins": [[p["name"], p.get("source")] for p in market["plugins"]]},
        "agents_marketplace_plugins": [p["name"] for p in agents_market["plugins"]],
        "skills": skills,
        "launcher": "bin/leadforge" if (REPO / "bin/leadforge").exists() else None,
    })


# --- 2. the agent contract: command names and exit codes ---------------------------------------------
def test_golden_agent_contract():
    import typer.main

    from leadforge import util
    from leadforge.agent_runner import AgentFailed, AgentUnavailable
    from leadforge.cli import app

    group = typer.main.get_command(app)
    _check("agent_contract", {
        "commands": sorted(group.commands),
        "exit_codes": {
            "LeadForgeError": util.LeadForgeError.exit_code,
            "EnvError": util.EnvError.exit_code,
            "InputError": util.InputError.exit_code,
            "ProviderFailed": util.ProviderFailed.exit_code,
            "AgentFailed": AgentFailed.exit_code,
            "AgentUnavailable": AgentUnavailable.exit_code,
        },
        "digest_prefix": "LF_DIGEST ",
    })


# --- 4. the sheet: column names and order ------------------------------------------------------------
def test_golden_sheet_columns():
    from leadforge import export

    _check("sheet_columns", {
        "COLUMNS": export.COLUMNS,
        "ACCOUNT_COLUMNS": export.ACCOUNT_COLUMNS,
        "DRAFT_COLUMNS": export.DRAFT_COLUMNS,
        "DEFAULT_COLUMNS": export.DEFAULT_COLUMNS,
    })


# --- 9. the scoring rules data ships in the package, byte for byte ----------------------------------
def test_golden_scoring_rules_data():
    raw = (files("leadforge") / "data" / "scoring.default.yaml").read_bytes()
    data = yaml.safe_load(raw.decode("utf-8"))
    _check("scoring_rules", {
        "sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
        "top_keys": list(data),
        "factors": list(data["factors"]),
    })


@pytest.mark.parametrize("name", ["plugin_contract", "agent_contract", "sheet_columns", "scoring_rules"])
def test_golden_files_are_committed(name):
    assert (GOLDEN / f"{name}.json").exists()
