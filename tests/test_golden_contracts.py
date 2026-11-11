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


@pytest.mark.parametrize("name", ["plugin_contract", "agent_contract", "sheet_columns", "scoring_rules", "autopilot_builtin_command",
                                  "campaign_file", "guardrail_defaults", "provenance", "workspace_schema"])
def test_golden_files_are_committed(name):
    assert (GOLDEN / f"{name}.json").exists()


# --- 11. an operator's own agent command is used as written; today's built-in call is pinned -----------
def test_golden_agent_command(tmp_path, monkeypatch):
    from leadforge.agent_runner import resolve_command
    from leadforge.config import load_config

    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    own = ["my-wrapper.cmd", "--flag", "value with spaces"]
    monkeypatch.setattr(cfg.agent, "command", own)
    assert resolve_command(cfg) == own  # verbatim: nothing added, nothing removed

    monkeypatch.setattr(cfg.agent, "command", None)
    monkeypatch.setattr("shutil.which", lambda _: "CLAUDE")
    # C1 changes this call on purpose (tools off); that change must be listed in its slice.
    _check("autopilot_builtin_command", {"argv": resolve_command(cfg), "isolate": cfg.agent.isolate})


# --- 1. the campaign file: its fields, "country required", and the hash that ignores caps ---------------
def _schema_shape(schema: dict) -> dict:
    """Field names and the required list of every object in a JSON schema (not types or descriptions)."""
    defs = {"ICP": schema, **schema.get("$defs", {})}
    return {name: {"fields": sorted(d.get("properties", {})), "required": sorted(d.get("required", []))}
            for name, d in sorted(defs.items()) if d.get("type") == "object"}


def test_golden_campaign_file(sample_icp):
    from pydantic import ValidationError

    from leadforge.models import ICP, Answers

    base = sample_icp.icp_hash()
    capped = sample_icp.model_copy(update={"caps": sample_icp.caps.model_copy(update={"max_leads": 9999}),
                                          "notes": "raised the cap"})
    moved = sample_icp.model_validate({**sample_icp.model_dump(mode="json"),
                                       "target": {**sample_icp.target.model_dump(mode="json"),
                                                  "geography": {"areas": ["Leeds"], "country": "GB"}}})
    assert capped.icp_hash() == base  # caps and notes are not part of the campaign's identity
    assert moved.icp_hash() != base
    no_country = sample_icp.model_dump(mode="json")
    del no_country["target"]["geography"]["country"]
    with pytest.raises(ValidationError, match="country"):
        ICP.model_validate(no_country)
    assert Answers.model_json_schema()["properties"] == ICP.model_json_schema()["properties"]
    _check("campaign_file", {"shape": _schema_shape(ICP.model_json_schema()), "sample_hash": base})


# --- 6. the guardrails that exist: their defaults ---------------------------------------------------------
def test_golden_guardrail_defaults():
    from leadforge.config import Config
    from leadforge.models import Caps
    from leadforge.util import HostThrottle

    cfg = Config()
    out = cfg.outreach
    _check("guardrail_defaults", {
        "politeness": {"delay_s": cfg.politeness.delay_s, "user_agent": cfg.politeness.user_agent},
        "throttle": {"jitter": HostThrottle(1.0).jitter},
        "caps": Caps().model_dump(),
        "outreach": {"armed": out.armed, "transport": out.transport,
                     "bounce_rate_pause": out.bounce_rate_pause, "complaint_rate_pause": out.complaint_rate_pause,
                     "require_email_confirmation": out.require_email_confirmation},
    })


# --- 7. where every fact came from: the provenance records and their tables --------------------------------
def _fresh_tables(tmp_path: Path) -> dict:
    from leadforge import db

    conn = db.connect(tmp_path / "fresh.sqlite3")
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    tables = {n: [r[1] for r in conn.execute(f"PRAGMA table_info('{n}')")] for n in names}
    conn.close()
    return tables


def test_golden_provenance(tmp_path):
    from leadforge.models import EnrichmentObservation, Evidence

    tables = _fresh_tables(tmp_path)
    _check("provenance", {
        "Evidence": sorted(Evidence.model_fields),
        "EnrichmentObservation": sorted(EnrichmentObservation.model_fields),
        "tables": {n: cols for n, cols in tables.items() if n in ("evidence", "enrichment_observations")},
    })


# --- 10. a workspace made by the current version still opens ------------------------------------------------
SAVED_WORKSPACE = GOLDEN / "workspace_current.sqlite3"


def test_golden_saved_workspace_opens(tmp_path):
    """`workspace_current.sqlite3` was made by this version (schema 7) with one made-up business in it. A
    new version that cannot open it breaks every user's workspace. Re-make it only together with a
    schema change that the slice lists."""
    import shutil

    from leadforge import db

    copy = tmp_path / "db.sqlite3"
    shutil.copyfile(SAVED_WORKSPACE, copy)
    conn = db.connect(copy)  # refuses any other schema_version
    row = conn.execute("SELECT name, website FROM businesses WHERE id='biz_golden'").fetchone()
    assert tuple(row) == ("Golden Example Plumbing", "https://plumbing.example")
    conn.close()
    _check("workspace_schema", _fresh_tables(tmp_path))
